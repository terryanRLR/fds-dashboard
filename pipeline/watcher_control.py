"""
watcher_control — 대시보드에서 워처를 켜고 끄기  ✨ v17 신규

⚠️ 보안이 먼저다
  대시보드는 ngrok / Streamlit Cloud 로 팀에 공유된다. 시작·중지 버튼은
  **URL을 아는 누구나 이 PC에서 프로세스를 켜고 끌 수 있다**는 뜻이다.
  그래서 기본은 잠겨 있고, 아래 두 조건이 모두 맞을 때만 열린다.

    ① 같은 PC에서 대시보드가 돌고 있다 (watcher.py 가 실제로 보인다)
    ② .env 또는 환경변수에  FDS_ALLOW_WATCHER_CONTROL=1  이 설정돼 있다

  ②를 기본값으로 켜지 않는 이유: 로컬에서만 쓰다가 어느 날 ngrok으로
  공유했을 때 조용히 위험해지는 것을 막기 위해서다. 켜는 것은 명시적 행동이어야 한다.

중지 방식
  프로세스를 죽이지 않고 `.watcher.stop` 신호 파일을 만든다.
  워처는 폴링 루프에서 이를 감지해 **현재 처리 중인 행을 마치고 커서를 저장한 뒤**
  종료한다. 강제 종료였다면 그 파일의 남은 행이 다음 기동 때 중복 처리될 수 있다.

시작 방식
  run_watcher.bat 을 새 콘솔로 분리 실행한다. conda 활성화·인코딩·HF 오프라인
  설정이 배치에 들어 있으므로 python 을 직접 부르지 않는다.
"""

from __future__ import annotations

import os
import json
import time
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CONTROL_VERSION = "v17"
_PROJ = Path(__file__).resolve().parent.parent

STOP_FLAG = _PROJ / ".watcher.stop"
# 예약 재개 시각. 워처는 멈춰 있으므로 스스로 살아날 수 없다 →
# 이미 10분마다 돌고 있는 데드맨 스위치(작업 스케줄러)가 이 파일을 보고 되살린다.
RESUME_PATH = _PROJ / ".watcher.resume_at"
LOCK_FILE = _PROJ / ".watcher.lock"
LAUNCHER = _PROJ / "run_watcher.bat"
WATCHER_PY = _PROJ / "watcher.py"

ALLOW_ENV = "FDS_ALLOW_WATCHER_CONTROL"


# ══════════════════════════════════════════════════════════
# 권한 판정
# ══════════════════════════════════════════════════════════

def is_local_deployment() -> bool:
    """대시보드가 워처와 같은 파일시스템 위에서 돌고 있는가.

    Streamlit Cloud 같은 원격 배포에서는 watcher.py 가 존재하지 않으므로
    (또는 존재해도 그 컨테이너의 사본이므로) 제어는 무의미하다.
    """
    return WATCHER_PY.exists()


def control_enabled() -> tuple[bool, str]:
    """(제어 가능 여부, 사유)"""
    if not is_local_deployment():
        return False, ("이 대시보드는 워처와 다른 서버에서 실행 중입니다 "
                       "(Streamlit Cloud 등). 워처가 있는 PC의 대시보드에서 조작하세요.")
    if str(os.getenv(ALLOW_ENV, "")).strip().lower() not in ("1", "true", "yes", "on"):
        return False, (f"안전을 위해 잠겨 있습니다. 켜려면 .env 에 "
                       f"`{ALLOW_ENV}=1` 을 추가하고 대시보드를 다시 시작하세요.")
    if not LAUNCHER.exists():
        return False, f"run_watcher.bat 을 찾을 수 없습니다: {LAUNCHER}"
    return True, ""


def is_running() -> bool:
    """락 파일 존재 = 워처 생존. (어떤 정상 종료에서도 atexit가 지운다)"""
    return LOCK_FILE.exists()


def stop_pending() -> bool:
    """중지 요청을 보냈고 아직 워처가 처리하지 않은 상태."""
    return STOP_FLAG.exists()


# ══════════════════════════════════════════════════════════
# 동작
# ══════════════════════════════════════════════════════════

def pending_resume() -> dict | None:
    """예약된 자동 재개 정보. 없으면 None."""
    try:
        if not RESUME_PATH.exists():
            return None
        data = json.loads(RESUME_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def clear_resume():
    try:
        RESUME_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _notify(text: str) -> bool:
    """중지·재개 사실을 Slack에 알린다.

    ⚠️ 이게 없으면 위험하다. 데드맨 스위치는 note='stopped'를 '의도적 중지'로 보고
    조용히 넘어가므로, 대화 중에 껐다가 잊어버리면 며칠 동안 탐지 공백이 생긴다.
    끈 사실 자체를 팀이 알아야 한다.
    """
    try:
        from pipeline.notifier import Notifier
    except ImportError:
        try:
            from notifier import Notifier
        except ImportError:
            return False
    try:
        return bool(Notifier().send_slack(text))
    except Exception as e:
        log.debug(f"제어 알림 실패: {e}")
        return False


def request_stop(reason: str = "", resume_after_min: int = 0,
                 actor: str = "대시보드") -> tuple[bool, str]:
    """중지 신호 + (선택) 자동 재개 예약 + Slack 통지."""
    ok, why = control_enabled()
    if not ok:
        return False, why
    if not is_running():
        return False, "워처가 실행 중이 아닙니다."
    try:
        STOP_FLAG.write_text("stop", encoding="utf-8")
    except Exception as e:
        return False, f"중지 요청 실패: {type(e).__name__}: {e}"

    mins = max(0, int(resume_after_min or 0))
    if mins:
        due = time.time() + mins * 60
        try:
            RESUME_PATH.write_text(json.dumps({
                "resume_at": due,
                "resume_at_text": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due)),
                "requested_by": actor, "reason": reason,
                "requested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning(f"재개 예약 기록 실패: {e}")
            mins = 0
    else:
        clear_resume()

    when = (f"{mins}분 뒤 자동 재개 예정"
            if mins else "*무기한 — 직접 다시 켜야 탐지가 재개됩니다*")
    _notify("🟡 *FDS 워처 수동 중지*\n"
            f"> 요청: {actor}" + (f" · 사유: {reason}" if reason else "") + "\n"
            f"> {when}\n"
            "> 중지 중에는 inbox 파일이 쌓여도 탐지·알림이 나가지 않습니다.")

    msg = ("중지 요청을 보냈습니다. 처리 중인 행을 마치고 몇 초 안에 종료됩니다 "
           "(강제 종료가 아니라 커서가 안전하게 저장됩니다). ")
    msg += (f"{mins}분 뒤 자동으로 다시 켜집니다."
            if mins else
            "⚠️ 자동 재개가 예약되지 않았습니다 — 직접 다시 켜야 탐지가 재개됩니다.")
    return True, msg


def start_watcher(extra_args: str = "", actor: str = "대시보드",
                  notify: bool = True) -> tuple[bool, str]:
    ok, why = control_enabled()
    if not ok:
        return False, why
    if is_running():
        return False, "이미 실행 중입니다. 중복 실행하면 알림이 두 번 갑니다."
    try:
        if os.name == "nt":
            # cmd /c start → 새 콘솔로 분리. Streamlit 프로세스가 붙잡지 않는다.
            cmd = ["cmd", "/c", "start", "FDS watcher", "/D", str(_PROJ),
                   str(LAUNCHER)] + ([extra_args] if extra_args else [])
            subprocess.Popen(cmd, cwd=str(_PROJ), close_fds=True)
        else:                                   # 개발용 (Linux/macOS)
            subprocess.Popen(["bash", str(LAUNCHER)], cwd=str(_PROJ),
                             start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        clear_resume()
        if notify:
            _notify(f"🟢 *FDS 워처 재시작* — 요청: {actor}")
        return True, ("워처를 시작했습니다. 모델 로드에 5~10초 걸립니다. "
                      "새로 열린 콘솔 창에서 진행 상황을 볼 수 있습니다.")
    except Exception as e:
        return False, f"시작 실패: {type(e).__name__}: {e}"


def status_text() -> str:
    if not is_local_deployment():
        return "원격 배포 — 제어 불가"
    if stop_pending():
        return "중지 요청 처리 중…"
    if is_running():
        return "실행 중"
    r = pending_resume()
    if r:
        return f"정지됨 · {r.get('resume_at_text', '?')} 자동 재개 예정"
    return "정지됨"


# ══════════════════════════════════════════════════════════
# Streamlit UI
# ══════════════════════════════════════════════════════════

def _do_reprocess(filename: str, db_path: str = "fds_results.db") -> tuple[bool, str]:
    """감시 파일의 커서를 지워 전량 재처리시킨다.

    ⚠️ 되돌릴 수 없다. 다음 폴링에서 그 파일을 처음부터 다시 읽으므로,
    24시간 중복 억제(notified)에 걸리지 않는 건은 알림이 다시 나갈 수 있다.
    """
    import sqlite3
    fp = Path(db_path)
    if not fp.is_absolute():
        fp = _PROJ / db_path
    if not fp.exists():
        return False, f"DB를 찾을 수 없습니다: {fp}"
    try:
        con = sqlite3.connect(str(fp), timeout=10)
        rows = con.execute(
            "SELECT path, rows_done FROM watch_cursor WHERE path LIKE ?",
            (f"%{filename}",)).fetchall()
        if not rows:
            con.close()
            return False, f"'{filename}' 커서를 찾지 못했습니다. 파일명을 확인하세요."
        con.execute("DELETE FROM watch_cursor WHERE path LIKE ?", (f"%{filename}",))
        con.commit()
        con.close()
        n = sum(r[1] or 0 for r in rows)
        _notify(f"♻️ *FDS 파일 재처리 요청* — `{filename}`\n"
                f"> 커서 {len(rows)}건 삭제 (누적 {n:,}행) · 다음 폴링에서 전량 재처리됩니다\n"
                "> 24시간 중복 억제에 걸리지 않는 건은 알림이 다시 나갈 수 있습니다.")
        return True, (f"'{filename}' 커서를 지웠습니다 (누적 {n:,}행). "
                      "다음 폴링에서 처음부터 다시 읽습니다.")
    except Exception as e:
        return False, f"재처리 실패: {type(e).__name__}: {e}"


def render_pending_request(st, key_prefix: str = "wc") -> bool:
    """🤖 에이전트가 올린 제어 요청의 승인 카드. 표시했으면 True.

    에이전트는 요청만 남기고 실제 실행은 여기서 사람이 버튼을 눌러야 일어난다.
    자연어는 "꺼줘"와 "끄면 어떻게 돼?"를 헷갈릴 수 있으므로 한 번 더 확인한다.
    """
    req = st.session_state.get("_watcher_request")
    if not req:
        return False

    op = req.get("op")
    ok, why = control_enabled()
    title = {"watcher_stop": "⏹ 워처 중지 요청",
             "watcher_start": "▶ 워처 시작 요청",
             "reprocess_file": "♻️ 파일 재처리 요청"}.get(op, "제어 요청")

    with st.container(border=True):
        st.markdown(f"**🤖 {title}** &nbsp;<span style='opacity:.6;font-size:12px'>"
                    f"AI 에이전트가 요청함 · {req.get('at','')}</span>",
                    unsafe_allow_html=True)

        if op == "watcher_stop":
            mins = int(req.get("minutes") or 0)
            if mins:
                st.info(f"워처를 중지하고 **{mins}분 뒤 자동으로 다시 켭니다.** "
                        f"중지 동안에는 inbox에 파일이 쌓여도 탐지·알림이 나가지 않습니다.")
            else:
                st.warning("워처를 **무기한 중지**합니다. 자동 재개가 없으므로 "
                           "직접 다시 켜기 전까지 탐지·알림이 전혀 나가지 않습니다. "
                           "가능하면 자동 재개 시간을 정하는 편이 안전합니다.")
        elif op == "reprocess_file":
            st.warning(f"**`{req.get('file','')}`** 의 처리 커서를 지웁니다. "
                       "다음 폴링에서 파일을 처음부터 다시 읽으므로, "
                       "24시간 중복 억제에 걸리지 않는 건은 **알림이 다시 나갈 수 있습니다.** "
                       "이 작업은 되돌릴 수 없습니다.")
        else:
            st.info("워처를 시작합니다.")

        if not ok:
            st.error(why)

        c1, c2 = st.columns(2)
        if c1.button("승인하고 실행", key=f"{key_prefix}_req_ok", type="primary",
                     width="stretch", disabled=not ok):
            if op == "watcher_stop":
                r_ok, msg = request_stop(reason="AI 에이전트 요청",
                                         resume_after_min=int(req.get("minutes") or 0),
                                         actor="AI 에이전트 (사람 승인)")
            elif op == "watcher_start":
                r_ok, msg = start_watcher(actor="AI 에이전트 (사람 승인)")
            else:
                r_ok, msg = _do_reprocess(req.get("file", ""))
            st.session_state.pop("_watcher_request", None)
            (st.success if r_ok else st.error)(msg)

        if c2.button("취소", key=f"{key_prefix}_req_no", width="stretch"):
            st.session_state.pop("_watcher_request", None)
            st.info("요청을 취소했습니다.")
    return True


def render_controls(st, key_prefix: str = "wc"):
    """패널에 삽입되는 시작/중지 UI. 어떤 실패도 밖으로 던지지 않는다."""
    try:
        ok, why = control_enabled()
        running = is_running()
        pending = stop_pending()

        pend = render_pending_request(st, key_prefix)

        with st.expander(f"🔌 워처 시작·중지 — {status_text()}", expanded=pend):
            res = pending_resume()
            if res:
                st.info(f"⏱ 자동 재개 예약됨 — **{res.get('resume_at_text','?')}** "
                        f"(요청: {res.get('requested_by','?')})  ·  "
                        f"데드맨 스위치가 그 시각에 다시 켭니다.")
            if not ok:
                st.info(why)
                if is_local_deployment():
                    st.caption(
                        "이 잠금은 의도적입니다. 대시보드를 ngrok이나 Streamlit Cloud로 "
                        "공유하면 링크를 아는 누구나 이 PC의 프로세스를 켜고 끌 수 있게 되기 "
                        "때문입니다. 로컬 전용으로 쓰는 것이 확실할 때만 여세요."
                    )
                return

            if pending:
                st.warning("중지 요청을 보냈습니다. 워처가 곧 종료됩니다 — 잠시 후 새로고침하세요.")

            c1, c2, c3 = st.columns(3)
            if c1.button("▶ 시작", key=f"{key_prefix}_start", width="stretch",
                         disabled=running or pending, type="primary"):
                s_ok, msg = start_watcher()
                (st.success if s_ok else st.error)(msg)

            if c2.button("⏹ 중지", key=f"{key_prefix}_stop", width="stretch",
                         disabled=(not running) or pending):
                s_ok, msg = request_stop()
                (st.success if s_ok else st.error)(msg)

            if c3.button("🔄 새로고침", key=f"{key_prefix}_refresh2", width="stretch"):
                st.rerun()

            st.caption(
                "중지는 강제 종료가 아니라 신호(.watcher.stop) 방식입니다. "
                "처리 중인 행을 마치고 커서를 저장한 뒤 멈추므로, 재시작해도 "
                "중복 처리나 누락이 생기지 않습니다."
            )
    except Exception as e:
        log.warning(f"워처 제어 UI 렌더 실패(무시): {type(e).__name__}: {e}")
        try:
            st.caption(f"⚠️ 제어 UI를 표시할 수 없습니다 — {type(e).__name__}")
        except Exception:
            pass

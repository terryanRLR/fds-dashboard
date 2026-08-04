"""
check_watcher — 데드맨 스위치 (워처 사망 감지)  ✨ v17 신규

문제
  워처가 죽어도 아무도 모른다. 대시보드 패널에 🔴가 뜨긴 하지만
  **누군가 그 화면을 봐야** 알 수 있다. 새벽에 죽으면 아침까지 탐지 공백이다.

해결
  Windows 작업 스케줄러가 10분마다 이 스크립트를 돌린다.
  워처의 하트비트(watcher_status.last_poll)가 오래됐으면 Slack으로 알린다.
  **별도 상주 데몬을 만들지 않는 것이 핵심** — 감시자도 죽을 수 있기 때문이다.
  작업 스케줄러는 OS가 관리하므로 우리 코드보다 훨씬 안 죽는다.

가볍게 유지한다
  모델·Chroma·LLM을 일절 건드리지 않는다. sqlite 읽기 + 웹훅 전송뿐이라
  10분마다 돌아도 부담이 없다. (detect_service를 import하면 안 된다)

알림 폭탄 방지
  · 다운 감지 즉시 1회 → 이후 쿨다운(기본 60분) 간격으로만 재알림
  · 복구되면 '복구됨' 1회 발송 후 상태 초기화
  · 사용자가 의도적으로 중지한 경우(note='stopped')는 알리지 않는다

사용법
  python -m tools.check_watcher                    # 점검만
  python -m tools.check_watcher --stale-minutes 15
  python -m tools.check_watcher --restart          # 죽었으면 자동 재시작까지
  python -m tools.check_watcher --dry-run -v       # 발송 없이 판정만

종료 코드
  0 = 정상 / 1 = 워처 다운(알림 보냄) / 2 = 점검 실패
"""

from __future__ import annotations

import sys
import json
import time
import sqlite3
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

_PROJ = Path(__file__).resolve().parent.parent
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

# 작업 스케줄러는 임의의 작업 디렉토리에서 실행되므로 모든 경로를 절대경로로 고정한다
DB_PATH = _PROJ / "fds_results.db"
STATE_PATH = _PROJ / ".deadman_state.json"
LOCK_FILE = _PROJ / ".watcher.lock"
RESUME_PATH = _PROJ / ".watcher.resume_at"
LAUNCHER = _PROJ / "run_watcher.bat"

DEFAULT_STALE_MIN = 10
DEFAULT_COOLDOWN_MIN = 60
DEFAULT_MAX_RESTARTS = 3          # 1시간 내 최대 재시작 횟수


# ══════════════════════════════════════════════════════════
# 상태 파일
# ══════════════════════════════════════════════════════════

def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st: dict):
    try:
        STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception as e:
        print(f"[!] 상태 저장 실패: {e}")


# ══════════════════════════════════════════════════════════
# 하트비트 조회
# ══════════════════════════════════════════════════════════

def read_heartbeat() -> dict | None:
    """watcher_status 1행. 없으면 None."""
    if not DB_PATH.exists():
        return None
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=10)
        con.execute("PRAGMA busy_timeout=10000")
        cur = con.execute("""
            SELECT last_poll, polls, rows_done, anomalies, notified, errors, note,
                   CAST(strftime('%s','now') - strftime('%s', last_poll) AS INTEGER)
            FROM watcher_status WHERE id = 1""")
        r = cur.fetchone()
        con.close()
        if not r:
            return None
        return {"last_poll": r[0], "polls": r[1], "rows_done": r[2], "anomalies": r[3],
                "notified": r[4], "errors": r[5], "note": (r[6] or "").strip(),
                "age_sec": r[7]}
    except sqlite3.OperationalError:
        return None                       # 테이블 없음 = 워처를 한 번도 안 돌림
    except Exception as e:
        print(f"[!] 하트비트 조회 실패: {e}")
        return None


# ══════════════════════════════════════════════════════════
# 알림
# ══════════════════════════════════════════════════════════

def send_slack(text: str, dry_run: bool = False) -> tuple[bool, str]:
    if dry_run:
        print("[DRY-RUN] Slack 발송 생략:")
        print("  " + text.replace("\n", "\n  "))
        return True, "dry-run"
    try:
        from pipeline.notifier import Notifier      # 가벼움 (requests/smtplib만)
        n = Notifier()
        ok = n.send_slack(text)
        return bool(ok), (n.last_error or "")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _fmt_age(sec) -> str:
    try:
        s = int(sec)
    except (TypeError, ValueError):
        return "?"
    if s < 60:
        return f"{s}초"
    if s < 3600:
        return f"{s//60}분"
    if s < 86400:
        return f"{s//3600}시간 {(s%3600)//60}분"
    return f"{s//86400}일"


def down_message(hb: dict, restarted: bool, n_alert: int) -> str:
    return (
        "🔴 *FDS 워처 응답 없음 — 탐지가 멈췄을 수 있습니다*\n"
        f"> 마지막 폴링: `{hb['last_poll']}` (UTC) · *{_fmt_age(hb['age_sec'])} 전*\n"
        f"> 누적: {hb['polls']:,}폴링 · {hb['rows_done']:,}행 · "
        f"이상 {hb['anomalies']:,} · 발송 {hb['notified']:,} · 오류 {hb['errors']:,}\n"
        f"> 상태값: `{hb['note'] or '-'}`"
        + (f"\n> ♻️ 자동 재시작을 시도했습니다 (곧 복구 알림이 오지 않으면 직접 확인하세요)"
           if restarted else
           "\n> 확인: 워처 콘솔 창 · `watcher.log` · 대시보드 세션5 패널")
        + (f"\n> _(이 장애에 대한 {n_alert}번째 알림)_" if n_alert > 1 else "")
    )


def up_message(hb: dict, down_since: str | None) -> str:
    dur = ""
    if down_since:
        try:
            secs = int(time.time() - float(down_since))
            dur = f" (약 {_fmt_age(secs)} 동안 중단)"
        except (TypeError, ValueError):
            pass
    return ("🟢 *FDS 워처 복구됨*" + dur + "\n"
            f"> 마지막 폴링: {_fmt_age(hb['age_sec'])} 전 · "
            f"{hb['polls']:,}폴링 · {hb['rows_done']:,}행 처리")


# ══════════════════════════════════════════════════════════
# 재시작
# ══════════════════════════════════════════════════════════

def try_restart(state: dict, max_restarts: int, dry_run: bool) -> tuple[bool, str]:
    """1시간 내 재시작 횟수를 제한한다 — 설정 오류로 무한 재시작하며
    Slack을 도배하는 상황을 막기 위해서다."""
    now = time.time()
    hist = [t for t in state.get("restarts", []) if now - float(t) < 3600]
    if len(hist) >= max_restarts:
        return False, f"1시간 내 재시작 {len(hist)}회 도달 — 더 시도하지 않습니다"
    if not LAUNCHER.exists():
        return False, f"run_watcher.bat 없음: {LAUNCHER}"
    if dry_run:
        return True, "dry-run (실제 실행 안 함)"
    try:
        subprocess.Popen(["cmd", "/c", "start", "FDS watcher", "/D", str(_PROJ),
                          str(LAUNCHER)], cwd=str(_PROJ), close_fds=True)
        hist.append(now)
        state["restarts"] = hist
        return True, f"재시작 시도 ({len(hist)}/{max_restarts} within 1h)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ══════════════════════════════════════════════════════════
# 예약 재개 — 멈춘 워처는 스스로 살아날 수 없다
# ══════════════════════════════════════════════════════════

def read_resume() -> dict | None:
    try:
        if not RESUME_PATH.exists():
            return None
        d = json.loads(RESUME_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def handle_resume(state: dict, max_restarts: int, dry_run: bool, log) -> int | None:
    """예약 재개를 처리한다. 처리했으면 종료코드, 아니면 None.

    "30분만 꺼줘" 로 중지한 경우 워처는 프로세스가 없으므로 스스로 못 켜진다.
    이미 10분마다 도는 이 스크립트가 대신 되살린다.
    """
    r = read_resume()
    if not r:
        return None
    due = float(r.get("resume_at") or 0)
    left = due - time.time()

    if LOCK_FILE.exists():                      # 사람이 이미 켰다면 예약 해제
        RESUME_PATH.unlink(missing_ok=True)
        log("이미 실행 중 — 예약 재개 해제")
        return 0

    if left > 0:
        log(f"예약 재개까지 {_fmt_age(left)} 남음 (의도적 중지 — 알림 없음)")
        return 0                                # 계획된 중지이므로 다운 알림을 내지 않는다

    ok, why = try_restart(state, max_restarts, dry_run)
    if ok:
        if not dry_run:
            RESUME_PATH.unlink(missing_ok=True)
        send_slack("🟢 *FDS 워처 자동 재개*\n"
                   f"> 예약 시각 도달 ({r.get('resume_at_text', '?')})\n"
                   f"> 요청자: {r.get('requested_by', '?')}"
                   + (f" · 사유: {r.get('reason')}" if r.get("reason") else ""), dry_run)
        print(f"  🟢 예약 재개 실행 — {why}")
        save_state(state)
        return 0

    send_slack("🔴 *FDS 워처 자동 재개 실패*\n"
               f"> 예약 시각이 지났지만 재시작하지 못했습니다: {why}\n"
               "> 직접 run_watcher.bat 을 실행해 주세요.", dry_run)
    print(f"  🔴 예약 재개 실패 — {why}")
    save_state(state)
    return 1


# ══════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════

def run(stale_min=DEFAULT_STALE_MIN, cooldown_min=DEFAULT_COOLDOWN_MIN,
        restart=False, max_restarts=DEFAULT_MAX_RESTARTS,
        dry_run=False, verbose=False) -> int:

    def log(msg):
        if verbose or dry_run:
            print(f"  {msg}")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] 워처 점검 — {DB_PATH.name}")

    hb = read_heartbeat()
    state = load_state()

    # ── 예약 재개가 걸려 있으면 그것부터 (계획된 중지는 다운으로 보지 않는다) ──
    _r = handle_resume(state, DEFAULT_MAX_RESTARTS, dry_run, log)
    if _r is not None:
        return _r

    # ── 판정 ──
    if hb is None:
        log("하트비트 없음 — 워처를 한 번도 실행하지 않았습니다. 알림 없음.")
        return 0

    if hb["note"] == "stopped":
        # 예약 재개가 없는 '무기한 중지'는 잊히기 쉽다.
        # 6시간 넘게 꺼져 있으면 하루 1회 상기시킨다 (탐지 공백을 방치하지 않도록).
        stopped_for = hb["age_sec"] or 0
        last_remind = float(state.get("stopped_reminder_at") or 0)
        if stopped_for > 6 * 3600 and (time.time() - last_remind) > 24 * 3600:
            ok, _ = send_slack(
                "🟡 *FDS 워처가 계속 꺼져 있습니다*\n"
                f"> {_fmt_age(stopped_for)} 동안 중지 상태입니다. 그동안 탐지·알림이 없습니다.\n"
                "> 의도한 것이라면 무시하세요.", dry_run)
            if ok:
                state["stopped_reminder_at"] = time.time()
                save_state(state)
            print(f"  🟡 장기 중지 상기 알림 ({_fmt_age(stopped_for)})")
            return 0
        log(f"의도적으로 중지된 상태(note=stopped, {_fmt_age(stopped_for)}) — 알림 없음.")
        if state.get("down_since"):
            state.pop("down_since", None)
            state.pop("last_alert_at", None)
            state.pop("alert_count", None)
            save_state(state)
        return 0

    if hb["note"] == "once":
        log("1회 실행 모드(note=once) — 상시 감시 대상이 아님. 알림 없음.")
        return 0

    age = hb["age_sec"]
    if age is None:
        log("last_poll을 읽지 못했습니다 — 알림 없음.")
        return 0

    stale_sec = stale_min * 60
    alive = age <= stale_sec
    log(f"마지막 폴링 {_fmt_age(age)} 전 · 기준 {stale_min}분 · "
        f"락파일 {'있음' if LOCK_FILE.exists() else '없음'}")

    # ── 정상 ──
    if alive:
        if state.get("down_since"):
            ok, why = send_slack(up_message(hb, state.get("down_since")), dry_run)
            print(f"  🟢 복구 감지 → 알림 {'성공' if ok else '실패: ' + why}")
            save_state({})
        else:
            log("정상 동작 중.")
        return 0

    # ── 다운 ──
    now = time.time()
    last_alert = float(state.get("last_alert_at") or 0)
    n_alert = int(state.get("alert_count") or 0)
    first_down = state.get("down_since") or now

    restarted, r_why = (False, "")
    if restart:
        restarted, r_why = try_restart(state, max_restarts, dry_run)
        log(f"자동 재시작: {'시도' if restarted else '건너뜀'} — {r_why}")

    in_cooldown = (n_alert > 0) and (now - last_alert < cooldown_min * 60)
    if in_cooldown:
        left = int(cooldown_min * 60 - (now - last_alert))
        print(f"  🔴 워처 다운 ({_fmt_age(age)} 전 마지막 폴링) — "
              f"쿨다운 중, {_fmt_age(left)} 후 재알림")
        state.update({"down_since": first_down, "last_alert_at": last_alert,
                      "alert_count": n_alert})
        save_state(state)
        return 1

    n_alert += 1
    ok, why = send_slack(down_message(hb, restarted, n_alert), dry_run)
    print(f"  🔴 워처 다운 ({_fmt_age(age)} 전 마지막 폴링) → "
          f"알림 {'성공' if ok else '실패: ' + why}")
    state.update({"down_since": first_down,
                  "last_alert_at": now if ok else last_alert,
                  "alert_count": n_alert if ok else n_alert - 1})
    save_state(state)
    return 1


def main():
    ap = argparse.ArgumentParser(description="FDS 워처 데드맨 스위치")
    ap.add_argument("--stale-minutes", type=int, default=DEFAULT_STALE_MIN,
                    help=f"이 시간 이상 하트비트가 없으면 다운 (기본 {DEFAULT_STALE_MIN}분)")
    ap.add_argument("--cooldown-minutes", type=int, default=DEFAULT_COOLDOWN_MIN,
                    help=f"재알림 간격 (기본 {DEFAULT_COOLDOWN_MIN}분)")
    ap.add_argument("--restart", action="store_true", help="다운이면 자동 재시작 시도")
    ap.add_argument("--max-restarts", type=int, default=DEFAULT_MAX_RESTARTS,
                    help="1시간 내 최대 재시작 횟수")
    ap.add_argument("--dry-run", action="store_true", help="발송하지 않고 판정만")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--reset", action="store_true", help="장애 상태 파일 초기화 후 종료")
    a = ap.parse_args()

    if a.reset:
        STATE_PATH.unlink(missing_ok=True)
        print("상태 파일을 초기화했습니다.")
        return 0

    try:
        return run(a.stale_minutes, a.cooldown_minutes, a.restart,
                   a.max_restarts, a.dry_run, a.verbose)
    except Exception as e:
        print(f"[X] 점검 실패: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())

"""
watcher_panel — 대시보드용 워처 상태 패널 (읽기 전용)  ✨ v15 신규

설계 원칙
  · **읽기 전용** — 이 모듈은 DB에 절대 쓰지 않는다. 워처가 남긴
    watcher_status / watch_cursor / transactions / notified 를 조회만 한다.
  · **대시보드를 죽이지 않는다** — 테이블이 아직 없거나(워처 미실행) DB가
    잠겨 있어도 조용히 빈 상태를 그린다. 모든 조회가 try/except로 격리된다.
  · **의존성 최소** — dashboard.py의 테마 헬퍼(csec/kpi_card/t)에 기대지 않고
    기본 Streamlit 위젯만 쓴다. 대시보드가 개편돼도 이 파일은 안 깨진다.
    (dashboard.py는 5,000줄이 넘고 백업이 130개다 — 최소 침습이 원칙)

⏱ 시각 처리 주의
  워처는 sqlite의 datetime('now')로 기록한다 = **UTC**.
  파이썬 로컬시각과 직접 빼면 9시간이 어긋나므로,
  경과 시간은 반드시 SQL 안에서 strftime('%s') 끼리 계산한다.

dashboard.py 연동 (2줄)
    from pipeline.watcher_panel import render_watcher_panel   # ← 상단 import 근처
    render_watcher_panel()                                    # ← 원하는 세션 안
"""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

PANEL_VERSION = "v15"
_PROJ = Path(__file__).resolve().parent.parent

DEFAULT_DB = "fds_results.db"
DEFAULT_LOG = "watcher.log"


# ══════════════════════════════════════════════════════════
# 조회 (Streamlit 무관 — 테스트·MCP에서도 재사용 가능)
# ══════════════════════════════════════════════════════════

def _conn(db_path: str):
    con = sqlite3.connect(db_path, timeout=5)
    try:
        con.execute("PRAGMA busy_timeout=5000")
    except Exception:
        pass
    return con


def _table_exists(con, name: str) -> bool:
    try:
        cur = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return cur.fetchone() is not None
    except Exception:
        return False


def read_status(db_path: str = DEFAULT_DB) -> dict | None:
    """워처 하트비트. 워처를 한 번도 안 돌렸으면 None."""
    try:
        con = _conn(db_path)
        if not _table_exists(con, "watcher_status"):
            con.close()
            return None
        cur = con.execute("""
            SELECT started_at, last_poll, polls, rows_done, anomalies, notified, errors, note,
                   CAST(strftime('%s','now') - strftime('%s', last_poll) AS INTEGER) AS age_sec,
                   CAST(strftime('%s','now') - strftime('%s', started_at) AS INTEGER) AS uptime_sec
            FROM watcher_status WHERE id = 1""")
        r = cur.fetchone()
        con.close()
        if not r:
            return None
        keys = ("started_at", "last_poll", "polls", "rows_done", "anomalies",
                "notified", "errors", "note", "age_sec", "uptime_sec")
        return dict(zip(keys, r))
    except Exception as e:
        log.debug(f"워처 상태 조회 실패: {e}")
        return None


def read_cursors(db_path: str = DEFAULT_DB, limit: int = 50) -> list[dict]:
    """감시 중인 파일별 처리 진행도."""
    try:
        con = _conn(db_path)
        if not _table_exists(con, "watch_cursor"):
            con.close()
            return []
        cur = con.execute("""
            SELECT path, size, rows_done, updated_at,
                   CAST(strftime('%s','now') - strftime('%s', updated_at) AS INTEGER) AS age_sec
            FROM watch_cursor ORDER BY updated_at DESC LIMIT ?""", (limit,))
        rows = cur.fetchall()
        con.close()
        return [{"파일": Path(r[0]).name, "크기(KB)": round((r[1] or 0) / 1024, 1),
                 "처리행": r[2], "마지막 갱신": r[3], "_age": r[4],
                 "_full_path": r[0]} for r in rows]
    except Exception as e:
        log.debug(f"커서 조회 실패: {e}")
        return []


def read_recent_detections(db_path: str = DEFAULT_DB, limit: int = 30,
                           only_anomaly: bool = True) -> list[dict]:
    """워처가 처리한 최근 거래. 대시보드/워처 어느 스키마든 동작한다."""
    try:
        con = _conn(db_path)
        if not _table_exists(con, "transactions"):
            con.close()
            return []
        cols = {r[1] for r in con.execute("PRAGMA table_info(transactions)")}
        ts = "detected_at" if "detected_at" in cols else (
             "processed_at" if "processed_at" in cols else "id")
        has_mode = "input_mode" in cols
        sel = f"transaction_id, fraud_type, risk_score, is_anomaly, {ts}" + \
              (", input_mode" if has_mode else "")
        q = f"SELECT {sel} FROM transactions WHERE 1=1 "
        if has_mode:
            q += "AND input_mode LIKE 'watcher%' "     # 워처가 넣은 행만
        if only_anomaly:
            q += "AND is_anomaly = 1 "
        q += "ORDER BY id DESC LIMIT ?"
        rows = con.execute(q, (limit,)).fetchall()
        con.close()
        out = []
        for r in rows:
            d = {"거래 ID": r[0], "유형": r[1], "위험점수": round(r[2] or 0, 4),
                 "이상": "🚨" if r[3] else "✅", "시각": r[4]}
            if has_mode:
                d["출처"] = r[5]
            out.append(d)
        return out
    except Exception as e:
        log.debug(f"탐지 이력 조회 실패: {e}")
        return []


def read_notified(db_path: str = DEFAULT_DB, limit: int = 20) -> list[dict]:
    try:
        con = _conn(db_path)
        if not _table_exists(con, "notified"):
            con.close()
            return []
        rows = con.execute(
            "SELECT txn_id, tier, sent_at FROM notified ORDER BY sent_at DESC LIMIT ?",
            (limit,)).fetchall()
        con.close()
        _icon = {"confirm": "🚨 확정", "review": "⚠️ 검토요청", "single": "🚨 경보"}
        return [{"거래 ID": r[0], "등급": _icon.get(r[1], r[1]), "발송(UTC)": r[2]} for r in rows]
    except Exception as e:
        log.debug(f"발송 이력 조회 실패: {e}")
        return []


def tail_log(log_path: str = DEFAULT_LOG, n: int = 25) -> str:
    """watcher.log 꼬리. 서비스로 돌릴 땐 콘솔이 없으므로 유일한 관측 창구다."""
    p = Path(log_path)
    if not p.is_absolute():
        p = _PROJ / log_path
    try:
        if not p.exists():
            return ""
        # 큰 로그 대비 — 뒤쪽 64KB만 읽는다
        size = p.stat().st_size
        with open(p, "rb") as f:
            if size > 65536:
                f.seek(size - 65536)
                f.readline()          # 잘린 첫 줄 버림
            data = f.read().decode("utf-8", errors="replace")
        lines = data.splitlines()
        return "\n".join(lines[-n:])
    except Exception as e:
        return f"(로그 읽기 실패: {e})"


def liveness(status: dict | None, expected_interval: float = 5.0) -> tuple[str, str]:
    """(아이콘 상태, 설명). 하트비트가 폴링 간격의 4배를 넘으면 죽은 것으로 본다."""
    if status is None:
        return "⚫", "워처를 아직 실행한 적이 없습니다"
    age = status.get("age_sec")
    note = (status.get("note") or "").strip()
    if note == "stopped":
        return "🔴", f"정상 종료됨 ({_ago(age)} 전)"
    if note == "once":
        return "🔵", f"1회 실행 모드로 동작함 ({_ago(age)} 전) — 상시 감시 중이 아닙니다"
    if age is None:
        return "⚫", "하트비트 시각을 읽지 못했습니다"
    limit = max(30, expected_interval * 4)
    if age <= limit:
        return "🟢", f"정상 동작 중 (마지막 폴링 {_ago(age)} 전)"
    return "🔴", (f"응답 없음 — 마지막 폴링이 {_ago(age)} 전입니다. "
                  f"프로세스가 죽었거나 멈췄을 수 있습니다")


def _ago(sec) -> str:
    try:
        s = int(sec)
    except (TypeError, ValueError):
        return "?"
    if s < 60:
        return f"{s}초"
    if s < 3600:
        return f"{s // 60}분"
    if s < 86400:
        return f"{s // 3600}시간"
    return f"{s // 86400}일"


def summary_line(db_path: str = DEFAULT_DB, expected_interval: float = 5.0) -> str:
    """사이드바·헤더용 한 줄 요약 (MCP 도구에서도 그대로 재사용 가능)."""
    st_ = read_status(db_path)
    icon, desc = liveness(st_, expected_interval)
    if st_ is None:
        return f"{icon} 워처 미실행"
    return (f"{icon} 워처 · {st_['polls']:,}폴링 · {st_['rows_done']:,}행 · "
            f"이상 {st_['anomalies']:,} · 발송 {st_['notified']:,}"
            + (f" · 오류 {st_['errors']:,}" if st_["errors"] else ""))


# ══════════════════════════════════════════════════════════
# 렌더링
# ══════════════════════════════════════════════════════════

def render_watcher_panel(db_path: str = DEFAULT_DB,
                         log_path: str = DEFAULT_LOG,
                         expected_interval: float = 5.0,
                         key_prefix: str = "wp",
                         expanded: bool = True):
    """대시보드에 워처 상태 패널을 그린다. 어떤 실패도 밖으로 던지지 않는다."""
    try:
        import streamlit as st
    except ImportError:
        print(summary_line(db_path, expected_interval))
        return

    try:
        _render(st, db_path, log_path, expected_interval, key_prefix, expanded)
    except Exception as e:
        log.warning(f"워처 패널 렌더 실패(무시): {type(e).__name__}: {e}")
        try:
            st.caption(f"⚠️ 워처 패널을 표시할 수 없습니다 — {type(e).__name__}: {e}")
        except Exception:
            pass


def _render(st, db_path, log_path, expected_interval, key_prefix, expanded):
    status = read_status(db_path)
    icon, desc = liveness(status, expected_interval)

    st.markdown(f"### {icon} 워처 상태 &nbsp;<span style='font-size:13px;opacity:.6'>"
                f"{PANEL_VERSION}</span>", unsafe_allow_html=True)

    # ── 미실행 안내 ──
    if status is None:
        # DB 파일 자체가 없으면 '미실행'이 아니라 '다른 서버'일 가능성이 높다
        import os as _os
        if not _os.path.exists(db_path):
            st.info(
                "이 대시보드에서는 워처 상태를 볼 수 없습니다.\n\n"
                f"`{db_path}` 를 찾을 수 없습니다. Streamlit Cloud 등 **워처와 다른 서버**에서 "
                "실행 중이라면 정상입니다 — 워처는 사내 PC의 DB에 기록하므로, "
                "그 PC에서 대시보드를 열어야 상태가 보입니다.")
            return
        st.info(
            "워처를 아직 실행한 적이 없습니다.\n\n"
            "```\nconda activate qaqc_st\n"
            "set HF_HUB_OFFLINE=1\n"
            "python watcher.py --interval 5 --startup-ping\n```\n"
            "처음이라면 `--once --dry-run` 으로 먼저 확인하세요.")
        return

    if icon == "🔴":
        st.error(desc)
    elif icon == "🟢":
        st.success(desc)
    elif icon == "🔵":
        st.info(desc)          # 1회 실행은 '경고'가 아니라 상태 안내
    else:
        st.warning(desc)

    # ── KPI ──
    c = st.columns(5)
    c[0].metric("폴링", f"{status['polls']:,}")
    c[1].metric("처리 행", f"{status['rows_done']:,}")
    c[2].metric("이상거래", f"{status['anomalies']:,}")
    c[3].metric("알림 발송", f"{status['notified']:,}")
    c[4].metric("오류", f"{status['errors']:,}",
                delta=None if not status["errors"] else "확인 필요",
                delta_color="inverse")

    st.caption(f"가동 시작 {_ago(status.get('uptime_sec'))} 전 · "
               f"마지막 폴링 {_ago(status.get('age_sec'))} 전 · "
               f"상태 `{status.get('note') or '-'}`")

    # ── 🔌 시작·중지 (기본 잠김 — watcher_control 참고) ──
    try:
        try:
            from pipeline.watcher_control import render_controls
        except ImportError:
            from watcher_control import render_controls
        render_controls(st, key_prefix)
    except Exception as _wce:
        log.debug(f"제어 UI 생략: {_wce}")

    # ── ⚙️ 워처 설정 (즉시 반영) ──
    _render_settings(st, db_path, key_prefix, expected_interval)

    # ── 탐지 이력 ──
    with st.expander("🚨 워처 탐지 이력", expanded=True):
        only_anom = st.checkbox("이상거래만 보기", value=True,
                                key=f"{key_prefix}_only_anom")
        rows = read_recent_detections(db_path, limit=50, only_anomaly=only_anom)
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.caption("아직 탐지 이력이 없습니다.")

    # ── 발송 이력 ──
    with st.expander("📨 알림 발송 이력 (중복 억제 기준)"):
        sent = read_notified(db_path)
        if sent:
            st.dataframe(sent, width="stretch", hide_index=True)
            st.caption("같은 거래 ID로는 설정된 시간(기본 24h) 안에 "
                       "동급 이하 알림이 재발송되지 않습니다.")
        else:
            st.caption("발송 이력이 없습니다.")

    # ── 파일 커서 ──
    with st.expander("📂 감시 파일 진행도"):
        curs = read_cursors(db_path)
        if curs:
            view = [{k: v for k, v in c_.items() if not k.startswith("_")} for c_ in curs]
            st.dataframe(view, width="stretch", hide_index=True)
            st.caption("행이 추가된 파일은 '처리행' 이후 분만 다시 읽습니다. "
                       "전량 재처리하려면 해당 파일의 커서를 삭제하세요.")
        else:
            st.caption("등록된 파일이 없습니다. inbox 폴더에 CSV를 넣어보세요.")

    # ── 로그 ──
    with st.expander("📜 watcher.log (최근 25줄)"):
        txt = tail_log(log_path, 25)
        if txt:
            st.code(txt, language="log")
        else:
            st.caption(f"로그 파일이 없습니다: {log_path}")

    if st.button("🔄 새로고침", key=f"{key_prefix}_refresh"):
        st.rerun()


def _render_settings(st, db_path, key_prefix, expected_interval):
    """워처 임계값·알림 설정 편집. 저장하면 다음 폴링에 워처가 스스로 다시 읽는다."""
    try:
        from pipeline import watcher_config as wcfg
    except ImportError:
        try:
            import watcher_config as wcfg
        except ImportError:
            return

    cur = wcfg.load()
    with st.expander(f"⚙️ 워처 임계값·알림 설정 — {wcfg.describe(cur)}", expanded=False):
        if not cur:
            st.caption("아직 `watcher_config.json` 이 없습니다. "
                       "워처를 한 번 실행하면 현재 설정으로 자동 생성되고, "
                       "여기서 저장해도 새로 만들어집니다.")

        dual = st.toggle("이중 임계값 사용", value=bool(cur.get("dual_threshold", True)),
                         key=f"{key_prefix}_dual",
                         help="ON: 1차는 Slack만(검토 요청), 2차는 Slack+Email(확정 통보). "
                              "OFF: 단일 임계값으로 한 번에 발송")
        if dual:
            c1, c2 = st.columns(2)
            th_r = c1.slider("1차 · 검토 요청 (Slack)", 0.0, 1.0,
                             float(cur.get("th_review", 0.45)), 0.01, key=f"{key_prefix}_thr")
            th_c = c2.slider("2차 · 확정 통보 (Slack+Email)", 0.0, 1.0,
                             float(cur.get("th_confirm", 0.80)), 0.01, key=f"{key_prefix}_thc")
            if th_c < th_r:
                st.caption(f"⚠️ 2차가 1차보다 낮습니다 → 저장 시 {th_r:.2f} 로 보정됩니다.")
            th_single = float(cur.get("threshold", 0.5))
            st.caption(f"위험 {th_r:.2f} 이상 → Slack · {max(th_r, th_c):.2f} 이상 → Slack+Email · "
                       f"점수가 낮아도 **예측 유형이 사기면 검토 요청**으로 올라갑니다 "
                       f"(이 모델의 사기 재현율은 검증셋 기준 0.53이라 미탐 안전망이 필요합니다)")
        else:
            th_single = st.slider("임계값", 0.0, 1.0, float(cur.get("threshold", 0.5)), 0.01,
                                  key=f"{key_prefix}_ths")
            th_r = float(cur.get("th_review", 0.45))
            th_c = float(cur.get("th_confirm", 0.80))

        c3, c4 = st.columns(2)
        pii = c3.selectbox(
            "마스킹 레벨", wcfg.PII_LEVELS,
            index=(list(wcfg.PII_LEVELS).index(cur.get("pii_level", "standard"))
                   if cur.get("pii_level", "standard") in wcfg.PII_LEVELS else 2),
            key=f"{key_prefix}_pii",
            help="LLM·Slack·Email로 나가기 전과 DB 적재 전에 적용됩니다")
        dedup = c4.number_input("같은 거래 재알림 억제(시간)", 0, 720,
                                int(cur.get("dedup_hours", 24)), 1, key=f"{key_prefix}_dedup")

        c5, c6, c7 = st.columns(3)
        n_slack = c5.toggle("Slack 발송", value=bool(cur.get("notify_slack", True)),
                            key=f"{key_prefix}_slack")
        n_email = c6.toggle("Email 발송", value=bool(cur.get("notify_email", True)),
                            key=f"{key_prefix}_email")
        use_llm = c7.toggle("LLM 분석", value=bool(cur.get("use_llm", True)),
                            key=f"{key_prefix}_llm",
                            help="OFF면 기본 양식으로만 발송합니다 (빠르지만 원인 분석 없음)")

        dry = st.toggle("🧪 DRY-RUN (판정만 하고 발송 안 함)",
                        value=bool(cur.get("dry_run", False)), key=f"{key_prefix}_dry")

        b1, b2 = st.columns([1, 1])
        if b1.button("💾 저장 (즉시 반영)", key=f"{key_prefix}_save", type="primary",
                     width="stretch"):
            ok, msg = wcfg.save({
                "dual_threshold": dual, "threshold": th_single,
                "th_review": th_r, "th_confirm": th_c,
                "pii_level": pii, "dedup_hours": dedup,
                "notify_slack": n_slack, "notify_email": n_email,
                "use_llm": use_llm, "dry_run": dry,
            })
            if ok:
                st.success(f"{msg}\n\n워처가 다음 폴링(최대 {expected_interval:.0f}초) 안에 "
                           f"스스로 다시 읽습니다. 재시작 불필요.")
            else:
                st.error(msg)

        if b2.button("⬅️ 사이드바 설정 복사", key=f"{key_prefix}_copy", width="stretch",
                     help="사이드바의 이중 임계값 슬라이더 값을 워처 설정으로 가져옵니다"):
            st.session_state[f"{key_prefix}_dual"] = bool(
                st.session_state.get("dual_threshold", True))
            st.session_state[f"{key_prefix}_thr"] = float(
                st.session_state.get("th_review", 0.45))
            st.session_state[f"{key_prefix}_thc"] = float(
                st.session_state.get("th_confirm", 0.80))
            st.rerun()

        st.caption("⚠️ 모델 경로·감시 폴더·폴링 간격은 여기서 바꿀 수 없습니다 "
                   "(프로세스 시작 시점에만 쓰이는 값이라 워처 재시작이 필요합니다).")


def render_watcher_badge(db_path: str = DEFAULT_DB, expected_interval: float = 5.0):
    """사이드바용 한 줄 배지 (선택)."""
    try:
        import streamlit as st
        st.caption(summary_line(db_path, expected_interval))
    except Exception:
        pass


# ── CLI 확인용:  python -m pipeline.watcher_panel ──
if __name__ == "__main__":
    print(summary_line())
    s = read_status()
    if s:
        print(f"  마지막 폴링: {s['last_poll']} (UTC) · {_ago(s['age_sec'])} 전")
    for r in read_recent_detections(limit=10):
        print("  ", r)

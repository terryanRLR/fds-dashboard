"""
agent_facts — 챗 에이전트에 주입할 '검증된 사실' 공급기  ✨ v18 신규

왜 필요한가
  현재 ChatAgent는 화면 스냅샷만 보고 답한다. 그래서 워처·DB·알림에 대해
  물어보면 "화면에 표시되지 않았다"밖에 답할 수 없다.
  이 모듈은 DB와 설정 파일에서 **실제 수치**를 읽어 컨텍스트에 넣어 준다.

설계 원칙 — 사실은 파이썬이, 설명은 LLM이
  진단(왜 알림이 안 오는가)을 LLM이 추론하게 두면 그럴듯한 원인을 지어낸다.
  그래서 판정 로직은 전부 여기 파이썬에 있고, LLM은 그 결과를 사람 말로 풀어줄 뿐이다.
  (이 프로젝트가 '판정은 ML, 설명은 규칙'으로 나눈 것과 같은 이유)

가벼워야 한다
  챗 한 턴마다 호출되므로 모델·Chroma·LLM을 절대 건드리지 않는다.
  sqlite 읽기 + 설정 파일 읽기 + (로컬 LLM일 때만) 소켓 1회가 전부다.

핵심 API
  watcher_facts()      → 워처·DB 현황 dict
  today_summary()      → 오늘 탐지 집계 dict
  diagnose()           → [{level, title, detail, fix}] 진단 체인
  context_lines(lang)  → _chat_context()에 그대로 넣을 문자열 리스트
"""

from __future__ import annotations

import os
import socket
import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

FACTS_VERSION = "v18"
_PROJ = Path(__file__).resolve().parent.parent

DEFAULT_DB = "fds_results.db"
STALE_MIN = 10                 # 하트비트가 이 시간 이상 끊기면 '응답 없음'
RECENT_LIMIT = 5


# ══════════════════════════════════════════════════════════
# 낮은 수준 조회
# ══════════════════════════════════════════════════════════

def _conn(db_path: str):
    con = sqlite3.connect(db_path, timeout=3)
    try:
        con.execute("PRAGMA busy_timeout=3000")
    except Exception:
        pass
    return con


def _has(con, table: str) -> bool:
    try:
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None
    except Exception:
        return False


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


# ══════════════════════════════════════════════════════════
# 사실 수집
# ══════════════════════════════════════════════════════════

def watcher_facts(db_path: str = DEFAULT_DB) -> dict:
    """워처 생존·처리량·감시 파일 현황."""
    out = {"db_exists": False, "ran_before": False, "alive": None, "note": "",
           "age_sec": None, "polls": 0, "rows_done": 0, "anomalies": 0,
           "notified": 0, "errors": 0, "files": [], "pending_files": 0}
    p = Path(db_path)
    if not p.is_absolute():
        p = _PROJ / db_path
    if not p.exists():
        return out
    out["db_exists"] = True
    try:
        con = _conn(str(p))
        if _has(con, "watcher_status"):
            r = con.execute("""
                SELECT last_poll, polls, rows_done, anomalies, notified, errors, note,
                       CAST(strftime('%s','now') - strftime('%s', last_poll) AS INTEGER)
                FROM watcher_status WHERE id = 1""").fetchone()
            if r and r[0]:
                out.update(ran_before=True, polls=r[1] or 0, rows_done=r[2] or 0,
                           anomalies=r[3] or 0, notified=r[4] or 0, errors=r[5] or 0,
                           note=(r[6] or "").strip(), age_sec=r[7])
                out["alive"] = (r[7] is not None and r[7] <= STALE_MIN * 60
                                and (r[6] or "").strip() not in ("stopped", "once"))
        if _has(con, "watch_cursor"):
            for row in con.execute(
                    "SELECT path, rows_done FROM watch_cursor ORDER BY updated_at DESC LIMIT 8"):
                out["files"].append({"name": Path(row[0]).name, "rows": row[1] or 0})
        con.close()
    except Exception as e:
        log.debug(f"워처 사실 조회 실패: {e}")
    return out


def today_summary(db_path: str = DEFAULT_DB) -> dict:
    """오늘(로컬 날짜) 탐지 집계. detections 테이블 기준."""
    out = {"available": False, "total": 0, "anomaly": 0, "by_type": [],
           "recent": [], "notified_today": 0, "last_detection": ""}
    p = Path(db_path)
    if not p.is_absolute():
        p = _PROJ / db_path
    if not p.exists():
        return out
    try:
        con = _conn(str(p))
        if not _has(con, "detections"):
            con.close()
            return out
        out["available"] = True
        r = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_anomaly),0) FROM detections "
            "WHERE date(detected_at) = date('now','localtime')").fetchone()
        out["total"], out["anomaly"] = int(r[0] or 0), int(r[1] or 0)

        out["by_type"] = [(t, int(n)) for t, n in con.execute(
            "SELECT fraud_type, COUNT(*) FROM detections "
            "WHERE date(detected_at) = date('now','localtime') AND is_anomaly = 1 "
            "GROUP BY fraud_type ORDER BY COUNT(*) DESC LIMIT 6")]

        out["recent"] = [
            {"id": a, "type": b, "risk": round(c or 0, 4), "at": d, "model": e or ""}
            for a, b, c, d, e in con.execute(
                "SELECT transaction_id, fraud_type, risk_score, detected_at, model "
                "FROM detections WHERE is_anomaly = 1 "
                "ORDER BY detected_at DESC LIMIT ?", (RECENT_LIMIT,))]
        if out["recent"]:
            out["last_detection"] = out["recent"][0]["at"]

        if _has(con, "notified"):
            out["notified_today"] = int(con.execute(
                "SELECT COUNT(*) FROM notified "
                "WHERE date(sent_at) = date('now','localtime')").fetchone()[0] or 0)
        con.close()
    except Exception as e:
        log.debug(f"오늘 집계 실패: {e}")
    return out


def config_facts() -> dict:
    """워처 설정(임계값 등). 파일이 없으면 기본값 표기."""
    out = {"exists": False, "dual": True, "th_review": 0.45, "th_confirm": 0.80,
           "threshold": 0.5, "pii": "standard", "slack": True, "email": True,
           "use_llm": True, "dry_run": False, "dedup_hours": 24}
    try:
        try:
            from pipeline import watcher_config as wcfg
        except ImportError:
            import watcher_config as wcfg
        v = wcfg.load()
        if v:
            out["exists"] = True
            out.update(dual=bool(v.get("dual_threshold", True)),
                       th_review=float(v.get("th_review", 0.45)),
                       th_confirm=float(v.get("th_confirm", 0.80)),
                       threshold=float(v.get("threshold", 0.5)),
                       pii=str(v.get("pii_level", "standard")),
                       slack=bool(v.get("notify_slack", True)),
                       email=bool(v.get("notify_email", True)),
                       use_llm=bool(v.get("use_llm", True)),
                       dry_run=bool(v.get("dry_run", False)),
                       dedup_hours=int(v.get("dedup_hours", 24)))
    except Exception as e:
        log.debug(f"설정 조회 실패: {e}")
    return out


def channel_facts() -> dict:
    """Slack/SMTP 설정 여부 (네트워크 호출 없음)."""
    out = {"slack_configured": False, "smtp_configured": False, "email_to": ""}
    try:
        try:
            from pipeline.notifier import Notifier
        except ImportError:
            from notifier import Notifier
        st_ = Notifier().check_status()
        out["slack_configured"] = bool(st_.get("slack_configured"))
        out["smtp_configured"] = bool(st_.get("smtp_configured"))
    except Exception as e:
        log.debug(f"채널 조회 실패: {e}")
    out["email_to"] = (os.getenv("FDS_NOTIFY_EMAIL") or "").strip()
    return out


def llm_facts(timeout: float = 0.4) -> dict:
    """로컬 LLM 서버가 떠 있는지 — 소켓 연결만 확인(HTTP 요청 없음)."""
    out = {"provider": (os.getenv("USE_LLM_PROVIDER") or "local").strip().lower(),
           "local_up": None, "url": os.getenv("LLAMA_CPP_URL", "")}
    if out["provider"] != "local":
        return out
    host, port = "127.0.0.1", 8080
    url = out["url"]
    if "://" in url:
        try:
            hp = url.split("://", 1)[1].split("/", 1)[0]
            host = hp.split(":")[0] or host
            port = int(hp.split(":")[1]) if ":" in hp else 80
        except Exception:
            pass
    try:
        with socket.create_connection((host, port), timeout=timeout):
            out["local_up"] = True
    except Exception:
        out["local_up"] = False
    return out


# ══════════════════════════════════════════════════════════
# 임계값 영향 예측 — tools/threshold_report.py 실측 결과 인용
# ══════════════════════════════════════════════════════════

REPORT_CSV = "threshold_report.csv"
_SHOW_THRESHOLDS = (0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90)


def threshold_table(csv_path: str = REPORT_CSV) -> list[dict]:
    """실측 리포트 표. 없으면 빈 리스트.

    모델을 다시 돌리지 않는다 — 챗 한 턴마다 추론하면 대시보드가 멈춘다.
    tools/threshold_report.py 가 남긴 CSV를 읽어 인용만 한다.
    """
    p = Path(csv_path)
    if not p.is_absolute():
        p = _PROJ / csv_path
    if not p.exists():
        return []
    try:
        import csv as _csv
        with open(p, encoding="utf-8-sig") as fh:
            rows = list(_csv.DictReader(fh))
        out = []
        for r in rows:
            try:
                out.append({
                    "th": float(r.get("임계값", 0)),
                    "alerts": int(float(r.get("알림건수", 0))),
                    "tp": int(float(r.get("적중TP", 0))),
                    "fn": int(float(r.get("미탐FN", 0))),
                    "fp": int(float(r.get("오탐FP", 0))),
                    "recall": float(r.get("재현율", 0)),
                    "precision": float(r.get("정밀도", 0)),
                    "daily": float(r.get("하루예상알림", 0)),
                })
            except (TypeError, ValueError):
                continue
        return out
    except Exception as e:
        log.debug(f"임계값 리포트 읽기 실패: {e}")
        return []


def _nearest(table: list[dict], th: float) -> dict | None:
    if not table:
        return None
    return min(table, key=lambda r: abs(r["th"] - th))


def threshold_impact(current: float, target: float,
                     csv_path: str = REPORT_CSV) -> dict | None:
    """현재값 → 목표값 변경 시 예상 변화. 리포트가 없으면 None."""
    t = threshold_table(csv_path)
    a, b = _nearest(t, current), _nearest(t, target)
    if not a or not b:
        return None
    return {
        "from": a["th"], "to": b["th"],
        "daily_from": a["daily"], "daily_to": b["daily"],
        "tp_from": a["tp"], "tp_to": b["tp"],
        "fp_from": a["fp"], "fp_to": b["fp"],
        "recall_from": a["recall"], "recall_to": b["recall"],
        "d_tp": b["tp"] - a["tp"], "d_fp": b["fp"] - a["fp"],
        "d_daily": round(b["daily"] - a["daily"], 2),
    }


def threshold_lines(current_review: float, csv_path: str = REPORT_CSV) -> list[str]:
    """컨텍스트에 넣을 임계값 영향 표 (있을 때만)."""
    t = threshold_table(csv_path)
    if not t:
        return ["임계값 실측표 없음 — `python -m tools.threshold_report` 를 실행하면 "
                "임계값별 예상 알림 건수를 근거로 안내할 수 있다"]
    lines = ["── 임계값 실측표 (tools/threshold_report.py 결과 · 이 수치를 그대로 인용할 것) ──"]
    cur = _nearest(t, current_review)
    for th in _SHOW_THRESHOLDS:
        r = _nearest(t, th)
        if not r or abs(r["th"] - th) > 0.03:
            continue
        mark = "  ← 현재 워처 검토 임계값" if cur and abs(r["th"] - cur["th"]) < 1e-6 else ""
        lines.append(
            f"  임계값 {r['th']:.2f} → 하루 알림 {r['daily']:.1f}건 · "
            f"사기 탐지 {r['tp']}건 · 미탐 {r['fn']}건 · 오탐 {r['fp']}건 · "
            f"재현율 {r['recall']:.1%}{mark}")
    lines.append("  ※ 임계값 변경을 안내할 때는 반드시 위 표에서 '현재값 → 목표값'의 "
                 "하루 알림·탐지·미탐 변화를 함께 알려주고, 사용자 확인을 받은 뒤 실행할 것")
    return lines


# ══════════════════════════════════════════════════════════
# 진단 체인 — "왜 알림이 안 오는가" / "왜 이렇게 많은가"
# ══════════════════════════════════════════════════════════

def diagnose(db_path: str = DEFAULT_DB, check_llm: bool = True) -> list[dict]:
    """확인 순서대로 점검한 결과. level: ok | warn | error

    순서에 의미가 있다. 위쪽 항목이 막혀 있으면 아래는 볼 필요도 없다.
    """
    f = watcher_facts(db_path)
    c = config_facts()
    ch = channel_facts()
    today = today_summary(db_path)
    out: list[dict] = []

    def add(level, title, detail, fix=""):
        out.append({"level": level, "title": title, "detail": detail, "fix": fix})

    # ① 워처 생존 — 이게 막히면 나머지는 의미 없다
    if not f["db_exists"]:
        add("error", "DB 없음", f"{db_path} 파일을 찾을 수 없습니다.",
            "워처와 다른 서버에서 대시보드를 실행 중일 수 있습니다.")
        return out
    if not f["ran_before"]:
        add("error", "워처 미실행", "워처를 한 번도 실행한 적이 없습니다.",
            "run_watcher.bat 또는 start_fds_team.bat 으로 시작하세요.")
        return out
    if f["note"] == "stopped":
        add("error", "워처 중지됨",
            f"의도적으로 중지된 상태입니다 ({_ago(f['age_sec'])} 전).",
            "다시 시작해야 탐지가 재개됩니다.")
    elif f["note"] == "once":
        add("warn", "1회 실행 모드",
            "--once 로 한 번만 돌았고 상시 감시 중이 아닙니다.",
            "상시 감시하려면 옵션 없이 실행하세요.")
    elif f["alive"]:
        add("ok", "워처 정상",
            f"마지막 폴링 {_ago(f['age_sec'])} 전 · {f['polls']:,}회 폴링 · "
            f"{f['rows_done']:,}행 처리")
    else:
        add("error", "워처 응답 없음",
            f"마지막 폴링이 {_ago(f['age_sec'])} 전입니다 (기준 {STALE_MIN}분).",
            "프로세스가 죽었을 수 있습니다. 콘솔 창과 watcher.log 를 확인하세요.")

    # ② 새 데이터가 들어오고 있나
    if f["files"]:
        tot = sum(x["rows"] for x in f["files"])
        add("ok", "감시 파일",
            f"{len(f['files'])}개 파일 · 누적 {tot:,}행 처리 완료")
    else:
        add("warn", "감시 파일 없음",
            "inbox 폴더에 처리된 CSV가 없습니다.",
            "파일이 실제로 들어오고 있는지 확인하세요. 알림이 없는 가장 흔한 원인입니다.")

    # ③ 임계값
    thr_desc = (f"이중 · 검토 {c['th_review']} / 확정 {c['th_confirm']}"
                if c["dual"] else f"단일 · {c['threshold']}")
    if c["dual"] and c["th_review"] >= 0.9:
        add("warn", "임계값이 매우 높음", f"{thr_desc} — 웬만해선 알림이 나가지 않습니다.",
            "검토 임계값을 낮추면 탐지가 늘어납니다.")
    elif c["dual"] and c["th_review"] <= 0.05:
        add("warn", "임계값이 매우 낮음", f"{thr_desc} — 알림이 과다할 수 있습니다.",
            "오탐이 많으면 검토 임계값을 올리세요.")
    else:
        add("ok", "임계값", thr_desc)

    # ④ 발송이 꺼져 있지 않은가
    if c["dry_run"]:
        add("error", "DRY-RUN 모드",
            "판정만 하고 실제 발송은 하지 않는 설정입니다.",
            "워처 설정에서 DRY-RUN 을 끄세요.")
    if not c["slack"] and not c["email"]:
        add("error", "알림 채널 전부 꺼짐", "Slack·Email 발송이 모두 비활성화되어 있습니다.",
            "워처 설정에서 채널을 켜세요.")

    # ⑤ 채널 설정
    if c["slack"] and not ch["slack_configured"]:
        add("error", "Slack 미설정", "SLACK_WEBHOOK_URL 이 비어 있어 발송이 전부 실패합니다.",
            ".env 에 웹훅 URL 을 설정하세요.")
    elif c["slack"]:
        add("ok", "Slack", "웹훅 설정됨")
    if c["email"] and not (ch["smtp_configured"] and ch["email_to"]):
        add("warn", "Email 미완성",
            "SMTP 계정 또는 수신 주소가 비어 있어 이메일이 나가지 않습니다.",
            ".env 의 SMTP_USER/SMTP_PASS/FDS_NOTIFY_EMAIL 을 확인하세요.")

    # ⑥ LLM (알림 자체는 나가지만 AI 분석이 빠진다)
    if check_llm and c["use_llm"]:
        l = llm_facts()
        if l["provider"] == "local" and l["local_up"] is False:
            add("warn", "로컬 LLM 응답 없음",
                "llama.cpp 서버가 떠 있지 않습니다. 알림은 나가지만 AI 분석 없이 "
                "기본 양식으로 발송됩니다.",
                "start_fds_team.bat 으로 llama.cpp 를 먼저 띄우세요.")
        elif l["provider"] == "local":
            add("ok", "로컬 LLM", "llama.cpp 응답 가능")

    # ⑦ 중복 억제
    if today["available"] and today["anomaly"] > 0 and today["notified_today"] == 0:
        add("warn", "탐지는 됐는데 발송 이력 없음",
            f"오늘 이상거래 {today['anomaly']}건이 잡혔지만 발송 기록이 없습니다. "
            f"{c['dedup_hours']}시간 중복 억제에 걸렸을 수 있습니다.",
            "같은 거래 ID로 이미 보냈다면 정상 동작입니다.")

    return out


def verdict(findings: list[dict]) -> str:
    """진단 한 줄 요약."""
    errs = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]
    if errs:
        return f"문제 {len(errs)}건 — 가장 먼저 볼 것: {errs[0]['title']}"
    if warns:
        return f"주의 {len(warns)}건 — {warns[0]['title']}"
    return "이상 없음 — 전 항목 정상"


# ══════════════════════════════════════════════════════════
# 컨텍스트 블록 (에이전트 프롬프트에 주입)
# ══════════════════════════════════════════════════════════

_ICON = {"ok": "OK", "warn": "주의", "error": "문제"}


def context_lines(db_path: str = DEFAULT_DB, include_diagnosis: bool = True,
                  check_llm: bool = True) -> list[str]:
    """_chat_context() 에 그대로 append 할 문자열 리스트.

    ⚠️ 여기 담기는 값은 '조회된 사실'이다. 에이전트는 이 수치를 그대로 인용해야 하며
       재계산하거나 추정해서는 안 된다 (프롬프트에서 그렇게 지시한다).
    """
    lines: list[str] = []
    f = watcher_facts(db_path)
    c = config_facts()
    t = today_summary(db_path)

    lines.append("── 워처(무인 감시) 현황 ──")
    if not f["db_exists"]:
        lines.append("이력 DB를 찾을 수 없음 (워처와 다른 서버에서 실행 중일 수 있음)")
        return lines
    if not f["ran_before"]:
        lines.append("워처를 실행한 적 없음")
    else:
        state = ("정상 동작 중" if f["alive"] else
                 "의도적으로 중지됨" if f["note"] == "stopped" else
                 "1회 실행 모드(상시 감시 아님)" if f["note"] == "once" else
                 "응답 없음(죽었을 가능성)")
        lines.append(f"상태: {state} · 마지막 폴링 {_ago(f['age_sec'])} 전")
        lines.append(f"누적: {f['polls']:,}폴링 · {f['rows_done']:,}행 처리 · "
                     f"이상거래 {f['anomalies']:,}건 · 알림 발송 {f['notified']:,}건 · "
                     f"오류 {f['errors']:,}건")
        if f["files"]:
            lines.append("감시 파일: " + " · ".join(
                f"{x['name']}({x['rows']:,}행)" for x in f["files"][:5]))

    lines.append("워처 임계값: " + (
        f"이중 — 검토(Slack) {c['th_review']} / 확정(Slack+Email) {c['th_confirm']}"
        if c["dual"] else f"단일 — {c['threshold']}"))
    lines.append(f"워처 마스킹: {c['pii']} · Slack {'ON' if c['slack'] else 'OFF'} · "
                 f"Email {'ON' if c['email'] else 'OFF'}"
                 + (" · DRY-RUN(발송 안 함)" if c["dry_run"] else ""))
    lines.append("※ 이 임계값은 워처(무인) 전용이며, 화면 상단의 임계값(대시보드 수동 탐지)과 별개다")

    if t["available"]:
        lines.append(f"오늘 탐지: 총 {t['total']:,}건 중 이상거래 {t['anomaly']:,}건 · "
                     f"알림 발송 {t['notified_today']:,}건")
        if t["by_type"]:
            lines.append("오늘 유형별: " + " · ".join(f"{k}형 {n}건" for k, n in t["by_type"]))
        if t["recent"]:
            lines.append("최근 이상거래(최대 5건):")
            for r in t["recent"]:
                lines.append(f"  · {r['id']} · {r['type']}형 · 위험 {r['risk']} · {r['at']}")

    lines.extend(threshold_lines(c["th_review"] if c["dual"] else c["threshold"]))

    if include_diagnosis:
        d = diagnose(db_path, check_llm=check_llm)
        lines.append("── 자가진단 (파이썬이 실제로 점검한 결과) ──")
        lines.append(f"종합: {verdict(d)}")
        for item in d:
            line = f"[{_ICON[item['level']]}] {item['title']}: {item['detail']}"
            if item["fix"] and item["level"] != "ok":
                line += f" → 조치: {item['fix']}"
            lines.append(line)

    return lines


# ── CLI 확인:  python -m pipeline.agent_facts ──
if __name__ == "__main__":
    for ln in context_lines():
        print(ln)

"""
watcher_config — 워처 튜닝값 공유 설정 파일  ✨ v16 신규

문제
  임계값을 바꾸려면 워처를 껐다 켜야 했다. 서비스로 등록하면 더 번거롭고,
  껐다 켜는 사이에 들어온 거래는 탐지 공백이 된다.

해결
  watcher_config.json 하나를 두고 **워처가 폴링마다 mtime을 확인해 다시 읽는다.**
  대시보드 패널에서 저장하면 다음 폴링(기본 5초) 안에 반영된다. 재시작 불필요.

우선순위
  CLI 명시 인자  >  watcher_config.json  >  .env  >  코드 기본값
  (워처 최초 기동 시 파일이 없으면 현재 설정으로 자동 생성한다)

핫 리로드 되는 값 / 안 되는 값
  ✅ 임계값·마스킹 레벨·알림 채널·LLM 사용 여부·중복 억제 시간
  ❌ 모델 경로·DB 경로·감시 폴더·폴링 간격 → 이것들은 워처 재시작이 필요하다
     (프로세스 시작 시점에만 쓰이는 값이라 중간에 바꾸면 상태가 꼬인다)

의존성 없음(json/pathlib만) — 대시보드가 무거운 파이프라인 모듈을 끌어오지 않고
직접 import할 수 있어야 하므로 의도적으로 가볍게 유지한다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_VERSION = "v16"
DEFAULT_PATH = "watcher_config.json"

# 핫 리로드 허용 키 → (형변환, 설명)
TUNABLES: dict[str, tuple] = {
    "dual_threshold": (bool,  "이중 임계값 사용 여부"),
    "threshold":      (float, "단일 모드 임계값"),
    "th_review":      (float, "1차 — Slack만 (검토 요청)"),
    "th_confirm":     (float, "2차 — Slack+Email (확정 통보)"),
    "pii_level":      (str,   "마스킹 레벨 off|basic|standard|strict"),
    "notify_slack":   (bool,  "Slack 발송"),
    "notify_email":   (bool,  "Email 발송"),
    "email_to":       (str,   "수신 이메일 (빈 값이면 .env)"),
    "use_llm":        (bool,  "LLM 분석 사용"),
    "use_rag":        (bool,  "RAG 컨텍스트 사용"),
    "rich_visuals":   (bool,  "Slack/Email 시각화"),
    "dedup_hours":    (int,   "같은 거래 재알림 억제 시간"),
    "dry_run":        (bool,  "발송하지 않고 판정만"),
}

PII_LEVELS = ("off", "basic", "standard", "strict")


def path_of(p: str | Path | None = None) -> Path:
    return Path(p or DEFAULT_PATH)


def load(p: str | Path | None = None) -> dict:
    """설정 파일 읽기. 없거나 깨졌으면 {} (호출부가 기본값을 쓰도록)."""
    fp = path_of(p)
    if not fp.exists():
        return {}
    try:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning(f"watcher_config.json 읽기 실패(기본값 사용): {e}")
        return {}


def save(values: dict, p: str | Path | None = None,
         meta: dict | None = None) -> tuple[bool, str]:
    """튜닝 가능한 키만 걸러서 저장. (성공여부, 메시지)

    meta: 감사 기록용 '_' 접두 키 (_changed_by / _changed_at / _reason).
      워처 임계값은 무인 운영의 기준값이라, 몇 달 뒤 "왜 이 값이지?"를
      되짚을 수 있어야 한다.
    """
    fp = path_of(p)
    clean, dropped = sanitize(values)
    # 기존 파일의 주석성 메타(_note 등)는 보존한다
    prev = load(fp)
    for k, v in prev.items():
        if k.startswith("_") and k != "_version":
            clean[k] = v
    for k, v in (meta or {}).items():
        clean[k if k.startswith("_") else f"_{k}"] = v
    clean["_version"] = CONFIG_VERSION
    try:
        # 원자적 쓰기 — 워처가 반쯤 쓰인 파일을 읽는 것을 방지
        tmp = fp.with_suffix(fp.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        tmp.replace(fp)
        msg = f"저장 완료: {fp}"
        if dropped:
            msg += f" (무시된 키: {', '.join(dropped)})"
        return True, msg
    except Exception as e:
        return False, f"저장 실패: {type(e).__name__}: {e}"


def sanitize(values: dict) -> tuple[dict, list[str]]:
    """튜닝 허용 키만 남기고 형변환·범위 보정."""
    out, dropped = {}, []
    for k, v in (values or {}).items():
        if k.startswith("_"):
            continue
        if k not in TUNABLES:
            dropped.append(k)
            continue
        caster = TUNABLES[k][0]
        try:
            out[k] = caster(v)
        except (TypeError, ValueError):
            dropped.append(k)

    # 범위 보정
    for k in ("threshold", "th_review", "th_confirm"):
        if k in out:
            out[k] = min(1.0, max(0.0, float(out[k])))
    if "pii_level" in out and out["pii_level"] not in PII_LEVELS:
        out["pii_level"] = "standard"
    if "dedup_hours" in out:
        out["dedup_hours"] = max(0, int(out["dedup_hours"]))
    # 2차가 1차보다 낮으면 무의미 — 대시보드와 동일하게 max로 보정
    if "th_review" in out and "th_confirm" in out and out["th_confirm"] < out["th_review"]:
        out["th_confirm"] = out["th_review"]
    return out, dropped


def apply_to(cfg, values: dict) -> list[str]:
    """DetectConfig에 반영. 실제로 바뀐 항목을 '키: 이전→이후' 문자열로 반환."""
    changed = []
    clean, _ = sanitize(values)
    for k, v in clean.items():
        old = getattr(cfg, k, None)
        if old != v:
            setattr(cfg, k, v)
            changed.append(f"{k}: {old}→{v}")
    return changed


def snapshot(cfg) -> dict:
    """현재 DetectConfig에서 튜닝값만 뽑아낸다 (파일 자동 생성용)."""
    return {k: getattr(cfg, k) for k in TUNABLES if hasattr(cfg, k)}


def seed_if_missing(cfg, p: str | Path | None = None) -> bool:
    """파일이 없으면 현재 설정으로 만들어 준다. 만들었으면 True."""
    fp = path_of(p)
    if fp.exists():
        return False
    ok, _ = save(snapshot(cfg), fp)
    return ok


def describe(values: dict | None = None, p: str | Path | None = None) -> str:
    """사람이 읽을 한 줄 요약."""
    v = values if values is not None else load(p)
    if not v:
        return "(설정 파일 없음 — 기본값 사용)"
    if v.get("dual_threshold", True):
        return (f"이중 · 검토 {v.get('th_review', '?')} / 확정 {v.get('th_confirm', '?')}"
                f" · 마스킹 {v.get('pii_level', '?')}")
    return f"단일 · {v.get('threshold', '?')} · 마스킹 {v.get('pii_level', '?')}"

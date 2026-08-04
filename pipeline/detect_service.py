"""
DetectService — 헤드리스 탐지 코어 (Streamlit 무관)  ✨ v15 신규

배경
  탐지→분석→발송 로직이 dashboard.py 안에만 존재했다.
  (_do_llm_analysis / _notify_tier / _compose_slack_single / _build_masker …)
  이들은 전부 st.session_state 를 읽고 t()·st.toast() 를 호출하므로
  **Streamlit 없이는 한 줄도 재사용할 수 없다.**
  워처·n8n·MCP가 각자 로직을 복붙하면 판정이 갈라져
  "대시보드는 정상인데 알림은 왔어요" 사고가 난다.

  → 이 모듈은 session_state 대신 DetectConfig(dataclass)를 주입받는
    **단일 판정 엔진**이다. 대시보드/워처/API/MCP가 전부 이걸 호출한다.

핵심 API
  svc = DetectService(DetectConfig(...))     # 생성 시 모델 하드 가드
  det = svc.detect(row)                      # 분류→마스킹→LLM→발송→DB, 전 과정
  svc.healthcheck()                          # 기동 전 자가진단 dict

🚨 무인 운영 안전장치 (대시보드와 가장 다른 부분)
  1. 더미 모드 금지 — MLClassifier는 모델 로드 실패 시 조용히
     _dummy_predict()(15% 확률 랜덤 사기 판정)로 빠진다. 사람이 보는
     대시보드에선 배지로 알 수 있지만 무인 워처는 새벽에 가짜 알림을 쏜다.
     → allow_dummy=False(기본)면 ModelNotReadyError로 **기동 자체를 거부**한다.
  2. cloud_fallback 기본 False — 로컬 LLM 실패 시 미마스킹 데이터가
     외부 API로 자동 전송되는 경로를 무인 모드에선 원천 차단.
  3. 알림 중복 방지 — notified 테이블로 같은 거래 재알림을 억제.
     (등급이 review→confirm으로 올라간 경우만 재발송)
"""

from __future__ import annotations

import os
import time
import sqlite3
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

log = logging.getLogger(__name__)

SERVICE_VERSION = "v15"

_PROJ = Path(__file__).resolve().parent.parent

# ── 내부 모듈 임포트 (pipeline 패키지 / 단독 실행 양쪽 지원) ──
try:
    from pipeline.pii_masker import PIIMasker
    from pipeline.notifier import Notifier
    from pipeline.llm_analyzer import LLMAnalyzer
except ImportError:  # pragma: no cover
    from pii_masker import PIIMasker
    from notifier import Notifier
    from llm_analyzer import LLMAnalyzer


class ModelNotReadyError(RuntimeError):
    """모델을 못 불러온 상태 — 무인 운영에서는 기동을 중단해야 한다."""


# 유형 코드 → 한국어 유형명 (llm_analyzer 폴백 테이블과 동일 — 단일 소스가 없어 최소 사본 유지)
FRAUD_TYPE_NAMES = {
    'a': '원격제어 사기', 'b': '단말 탈취 사기', 'c': '명의 도용 사기',
    'd': '대출 빙자 사기', 'e': 'ATM 사기', 'f': '피싱 사기',
    'g': '스미싱 사기', 'h': '계좌 이상 사기', 'i': '다중 시도 사기',
    'j': '수취 정지 사기', 'k': '오픈뱅킹 사기', 'l': '기타 사기', 'm': '정상 거래',
}

# 등급 서열 — 재알림 판단용 (낮음 → 높음)
_TIER_RANK = {"none": 0, "review": 1, "single": 2, "confirm": 3}

_TIER_SUBJECT = {
    "confirm": "[FDS 확정] {ft}형 이상거래 탐지 — 위험 {risk:.2f} (거래 {tid})",
    "review":  "[FDS 검토요청] {ft}형 의심거래 — 위험 {risk:.2f} (거래 {tid})",
    "single":  "[FDS 경보] {ft}형 이상거래 탐지 — 위험 {risk:.2f} (거래 {tid})",
}

_TIER_HEAD = {
    "confirm": "🚨 *[확정] 즉시 대응 필요*",
    "review":  "⚠️ *[검토 요청] 담당자 확인 바랍니다*",
    "single":  "🚨 *[이상거래 탐지]*",
}


# ══════════════════════════════════════════════════════════
# 설정
# ══════════════════════════════════════════════════════════

@dataclass
class DetectConfig:
    """워처·API·MCP가 공유하는 판정 설정. 대시보드의 session_state 대체."""

    # ── 모델 ──
    model_dir: str = "models/"
    model_path: str | None = None          # None이면 resolve_model_path 자동 탐색
    allow_dummy: bool = False              # 🚨 True는 절대 운영 금지 (개발 테스트 전용)

    # ── 임계값 ──
    threshold: float = 0.5                 # 단일 모드 기준
    dual_threshold: bool = True            # 무인 운영 기본 ON
    th_review: float = 0.45                # 1차: Slack만 (검토 요청)
    th_confirm: float = 0.80               # 2차: Slack+Email (확정 통보)

    # ── PII ──
    pii_level: str = "standard"            # off | basic | standard | strict

    # ── LLM ──
    use_llm: bool = True
    llm_provider: str | None = None        # None이면 .env의 USE_LLM_PROVIDER
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_url: str | None = None
    llm_max_tokens: int = 1024
    cloud_fallback: bool = False           # 무인 기본 False — 외부 자동 전송 차단
    llm_breaker_fails: int = 3             # 연속 실패 N회 → LLM 일시 우회
    llm_breaker_cooldown: float = 300.0    # 우회 지속 시간(초)

    # ── RAG ──
    use_rag: bool = True
    rag_top_k: int = 3

    # ── 알림 ──
    notify_slack: bool = True
    notify_email: bool = True
    email_to: str | None = None            # None이면 .env FDS_NOTIFY_EMAIL
    rich_visuals: bool = True              # notify_visuals 사용 (실패 시 평문 폴백)
    dry_run: bool = False                  # True면 발송하지 않고 로그만

    # ── 저장 ──
    db_path: str = "fds_results.db"
    dedup_hours: int = 24                  # 같은 거래 재알림 억제 시간

    lang: str = "ko"

    @classmethod
    def from_env(cls, **overrides) -> "DetectConfig":
        """.env 값을 반영한 기본 설정. 명시 인자가 항상 우선."""
        def _f(key, default):
            try:
                return float(os.getenv(key, "") or default)
            except ValueError:
                return default
        cfg = cls(
            threshold=_f("FDS_THRESHOLD", 0.5),
            th_review=_f("FDS_TH_REVIEW", 0.45),
            th_confirm=_f("FDS_TH_CONFIRM", 0.80),
            pii_level=os.getenv("FDS_PII_LEVEL", "standard"),
            email_to=os.getenv("FDS_NOTIFY_EMAIL") or None,
        )
        for k, v in overrides.items():
            if v is not None and hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


# ══════════════════════════════════════════════════════════
# 서비스
# ══════════════════════════════════════════════════════════

class DetectService:
    """단건 거래 dict → 분류 → (임계값 초과 시) LLM 분석 → 알림 → DB 저장."""

    def __init__(self, cfg: DetectConfig | None = None):
        self.cfg = cfg or DetectConfig()
        self.clf = None
        self.clf_mode = ""
        self._masker = None
        self._notifier = None
        self._analyzer = None
        self._rag = None
        self._rag_tried = False
        self.stats = {"seen": 0, "anomaly": 0, "notified": 0, "llm_fail": 0,
                      "errors": 0, "db_fail": 0}
        self._db_warned = False
        self._tx_cols = None                 # transactions 실제 컬럼 캐시
        # LLM 서킷 브레이커 — llama.cpp가 죽어 있으면 1건당 12초(3콜×4초)를 헛되이 쓴다.
        #   연속 실패가 쌓이면 일정 시간 LLM을 건너뛰고 폴백 양식으로 즉시 발송한다.
        self._llm_fail_streak = 0
        self._llm_off_until = 0.0

        self._init_db()
        self._build_classifier()     # 🚨 실패 시 여기서 ModelNotReadyError

    # ══════════════════════════════════════════════════════
    # 기동 — 모델 하드 가드
    # ══════════════════════════════════════════════════════

    def _build_classifier(self):
        cfg = self.cfg

        # ① 배포 번들 경로 — verify_bundle에서 ✅ 확인된 결정론적 변환 (권장)
        try:
            try:
                from pipeline.preprocessor import RawRowClassifier
            except ImportError:
                from preprocessor import RawRowClassifier
            clf = RawRowClassifier.from_bundle(cfg.model_dir, cfg.model_path)
            if getattr(clf, "model", None) is not None:
                self.clf = clf
                self.clf_mode = f"bundle/RawRowClassifier · {len(clf.feature_cols)}피처"
                log.info(f"분류기 준비 완료 — {self.clf_mode}")
                return
        except Exception as e:
            log.warning(f"번들 경로(RawRowClassifier) 사용 불가 → MLClassifier 폴백: "
                        f"{type(e).__name__}: {e}")

        # ② MLClassifier 폴백
        try:
            from pipeline.ml_classifier import MLClassifier
        except ImportError:
            from ml_classifier import MLClassifier
        mp = cfg.model_path or str(Path(cfg.model_dir) / "lgbm_13class(최종).pkl")
        clf = MLClassifier(mp)

        if getattr(clf, "model", None) is None:
            if not cfg.allow_dummy:
                raise ModelNotReadyError(
                    "❌ 모델을 불러오지 못했습니다 — 무인 운영을 중단합니다.\n"
                    f"   모델 경로 : {mp}\n"
                    "   확인 순서 :\n"
                    "     1) 올바른 파이썬인가?  python -c \"import sys,lightgbm;print(sys.executable)\"\n"
                    "        → 반드시 envs\\qaqc_st\\python.exe 여야 합니다.\n"
                    "        (서비스 등록 시 PATH를 물려받지 못해 시스템 파이썬이 잡히는 사고가 잦습니다)\n"
                    "     2) 번들 검증 통과했는가?  python -m tools.verify_bundle\n"
                    "     3) models/ 에 label_encoders.pkl · le_target.pkl · feature_cols.json 이 있는가?\n"
                    "   ※ 이 가드가 없으면 MLClassifier가 더미 모드로 빠져 "
                    "랜덤 사기 판정을 알림으로 발송합니다."
                )
            log.error("🚨 allow_dummy=True — 더미(랜덤) 예측으로 계속합니다. 절대 운영 금지!")

        self.clf = clf
        self.clf_mode = ("MLClassifier(더미)" if getattr(clf, "model", None) is None
                         else f"MLClassifier · {len(getattr(clf, 'feature_cols', []) or [])}피처")
        log.info(f"분류기 준비 완료 — {self.clf_mode}")

    def healthcheck(self) -> dict:
        """기동 전/중 자가진단. 워처가 시작 로그에 그대로 찍는다."""
        cfg = self.cfg
        out = {
            "service_version": SERVICE_VERSION,
            "classifier": self.clf_mode,
            "model_ok": getattr(self.clf, "model", None) is not None,
            "threshold": (f"dual · review {cfg.th_review} / confirm {cfg.th_confirm}"
                          if cfg.dual_threshold else f"single · {cfg.threshold}"),
            "pii_level": cfg.pii_level,
            "llm": "off",
            "rag": "off",
            "slack": False,
            "email": False,
            "db": cfg.db_path,
            "dry_run": cfg.dry_run,
            "warnings": [],
        }
        if cfg.use_llm:
            a = self._get_analyzer()
            out["llm"] = f"{a.provider}" + (f" · {a.model_override}" if a.model_override else "")
            # ⚠️ .env의 LLAMA_CPP_URL이 /completion 이면 Gemma 채팅 템플릿이 적용되지 않는다
            if a.provider == "local" and str(a.llama_cpp_url).rstrip("/").endswith("/completion"):
                out["warnings"].append(
                    "LLAMA_CPP_URL이 /completion 입니다 → /v1/chat/completions 로 바꾸세요 "
                    "(채팅 템플릿 미적용 시 출력 품질이 크게 떨어집니다)")
            if not cfg.cloud_fallback and a.provider == "local":
                out["llm"] += " (외부 폴백 차단)"
        if cfg.use_rag:
            r = self._get_rag()
            out["rag"] = ("dummy(미설치/초기화실패)" if r is None or getattr(r, "collection", None) is None
                          else f"chroma · {r.collection.count()}청크")
        n = self._get_notifier()
        st = n.check_status()
        out["slack"] = st["slack_configured"]
        out["email"] = st["smtp_configured"]
        if cfg.notify_slack and not st["slack_configured"]:
            out["warnings"].append("SLACK_WEBHOOK_URL 미설정 — Slack 발송이 전부 실패합니다")
        if cfg.notify_email and not (st["smtp_configured"] and self._email_to()):
            out["warnings"].append("SMTP 계정 또는 수신 이메일 미설정 — Email 발송이 전부 실패합니다")
        if cfg.allow_dummy:
            out["warnings"].append("🚨 allow_dummy=True — 랜덤 예측 위험. 운영에서는 반드시 False")
        return out

    # ══════════════════════════════════════════════════════
    # 지연 생성 (무거운 객체는 처음 필요할 때 한 번만)
    # ══════════════════════════════════════════════════════

    def _get_masker(self) -> PIIMasker:
        if self._masker is None:
            self._masker = PIIMasker(level=self.cfg.pii_level)
        return self._masker

    def _get_notifier(self) -> Notifier:
        if self._notifier is None:
            self._notifier = Notifier()
        return self._notifier

    def _get_analyzer(self) -> LLMAnalyzer:
        if self._analyzer is None:
            c = self.cfg
            self._analyzer = LLMAnalyzer(
                max_tokens=c.llm_max_tokens,
                llama_cpp_url=c.llm_url,
                model=c.llm_model,
                provider=c.llm_provider,
                api_key=c.llm_api_key,
                cloud_fallback=c.cloud_fallback,
            )
        return self._analyzer

    def _get_rag(self):
        """Chroma는 다중 프로세스 접근에 취약 — 실패해도 더미로 계속 간다."""
        if not self._rag_tried:
            self._rag_tried = True
            try:
                try:
                    from pipeline.rag_searcher import RAGSearcher
                except ImportError:
                    from rag_searcher import RAGSearcher
                self._rag = RAGSearcher(top_k=self.cfg.rag_top_k)
            except Exception as e:
                log.warning(f"RAG 초기화 실패 → 컨텍스트 없이 진행: {type(e).__name__}: {e}")
                self._rag = None
        return self._rag

    def _email_to(self) -> str:
        return (self.cfg.email_to or os.getenv("FDS_NOTIFY_EMAIL") or "").strip()

    # ══════════════════════════════════════════════════════
    # 등급 판정
    # ══════════════════════════════════════════════════════

    def notify_tier(self, fraud_type: str, risk_score: float) -> str:
        """'none' | 'review' | 'single' | 'confirm'

        ⚠️ 재현율 보정: 이 모델의 사기 재현율은 검증셋 기준 0.53이다.
        점수가 낮아도 **예측 유형이 사기(m이 아님)면 review로 올린다** —
        사람이 없는 무인 경로에서 미탐은 되돌릴 수 없기 때문.
        """
        cfg = self.cfg
        r = float(risk_score or 0)
        is_fraud_type = (fraud_type or "") != "m"

        if not cfg.dual_threshold:
            return "single" if (is_fraud_type or r >= cfg.threshold) else "none"

        t2 = max(float(cfg.th_confirm), float(cfg.th_review))   # 역전 설정 보정
        if r >= t2:
            return "confirm"
        if r >= float(cfg.th_review) or is_fraud_type:
            return "review"
        return "none"

    # ══════════════════════════════════════════════════════
    # 메인 — 단건 처리
    # ══════════════════════════════════════════════════════

    def detect(self, row: dict, source: str = "watcher") -> dict:
        """거래 1건 전 과정 처리. 예외를 밖으로 던지지 않는다(루프 보호)."""
        t0 = time.time()
        cfg = self.cfg
        det = {
            "txn_id": str(row.get("transaction_id") or row.get("ID") or f"ROW_{int(t0*1000)}"),
            "fraud_type": "", "fraud_name": "", "risk_score": 0.0, "proba": {},
            "is_anomaly": False, "tier": "none",
            "llm": {}, "llm_used": False,
            "sent_slack": False, "sent_email": False, "deduped": False,
            "source": source, "errors": [], "elapsed": 0.0,
        }
        self.stats["seen"] += 1

        # ── ① 분류 ──
        try:
            clean = {k: v for k, v in row.items() if not str(k).startswith("_")}
            ft, risk, proba = self.clf.predict(clean)
        except Exception as e:
            det["errors"].append(f"분류 실패: {type(e).__name__}: {e}")
            self.stats["errors"] += 1
            det["elapsed"] = time.time() - t0
            log.error(f"[{det['txn_id']}] 분류 실패: {e}")
            return det

        det["fraud_type"] = ft
        det["fraud_name"] = FRAUD_TYPE_NAMES.get(ft, f"유형 {str(ft).upper()}")
        det["risk_score"] = float(risk)
        det["proba"] = proba
        det["tier"] = tier = self.notify_tier(ft, risk)
        det["is_anomaly"] = tier != "none"

        if not det["is_anomaly"]:
            self._save_db(row, det)
            det["elapsed"] = time.time() - t0
            return det

        self.stats["anomaly"] += 1
        log.warning(f"⚠️ 이상거래 [{det['txn_id']}] {ft}({det['fraud_name']}) "
                    f"위험 {risk:.4f} → 등급 {tier}")

        # ── ② 중복 알림 억제 ──
        if self._already_notified(det["txn_id"], tier):
            det["deduped"] = True
            log.info(f"  ↷ 최근 {cfg.dedup_hours}시간 내 동일/상위 등급 알림 이력 — 발송 생략")
            self._save_db(row, det)
            det["elapsed"] = time.time() - t0
            return det

        # ── ③ PII 마스킹 (LLM·알림 경로 진입 전 필수) ──
        masker = self._get_masker()
        masked = masker.mask_row(clean)

        # ── ④ RAG + LLM ──
        if cfg.use_llm and time.time() < self._llm_off_until:
            wait = int(self._llm_off_until - time.time())
            det["errors"].append(f"LLM 일시 중단 중(연속 실패) — {wait}초 후 재시도")
            log.info(f"  ↷ LLM 서킷 열림 — 폴백 양식으로 즉시 발송 ({wait}초 후 재시도)")
        elif cfg.use_llm:
            rag_ctx = []
            if cfg.use_rag:
                rag = self._get_rag()
                if rag is not None:
                    try:
                        rag_ctx = rag.search(
                            f"사기유형 {ft} {det['fraud_name']} 이상거래 탐지 원인 분석", ft)
                    except Exception as e:
                        det["errors"].append(f"RAG 검색 실패: {e}")
            try:
                res = self._get_analyzer().analyze(
                    row=masked, fraud_type=ft, risk_score=risk,
                    rag_context=rag_ctx, lang=cfg.lang)
                det["llm"] = res if isinstance(res, dict) else {
                    "analysis": str(res), "slack": str(res)[:500], "email": str(res)}
                det["llm_used"] = True
                self._llm_fail_streak = 0
            except Exception as e:
                self.stats["llm_fail"] += 1
                det["errors"].append(f"LLM 분석 실패: {type(e).__name__}: {e}")
                log.error(f"  LLM 분석 실패 → 폴백 본문으로 발송: {e}")
                self._trip_llm_breaker()

        # LLM이 예외 없이 '폴백 텍스트'만 돌려준 경우도 실패로 센다
        #   (llm_analyzer는 서버가 죽어도 예외 대신 폴백 문자열을 반환한다)
        if cfg.use_llm and det["llm_used"]:
            if getattr(self._get_analyzer(), "_fallback_count", 0):
                self._trip_llm_breaker(soft=True)
            else:
                self._llm_fail_streak = 0

        if not det["llm"]:
            det["llm"] = self._fallback_texts(det, masked)

        # ── ⑤ 발송 ──
        self._notify(det, masker)

        # ── ⑥ 저장 (raw_json에는 마스킹본을 넣는다) ──
        self._save_db(row, det, masked)
        det["elapsed"] = time.time() - t0
        return det

    # ══════════════════════════════════════════════════════
    # 발송
    # ══════════════════════════════════════════════════════

    def _notify(self, det: dict, masker):
        cfg = self.cfg
        tier = det["tier"]
        # review 등급은 Slack만 (담당자 검토 요청) · confirm/single은 Slack+Email
        slack_go = cfg.notify_slack
        email_go = cfg.notify_email and tier in ("single", "confirm")

        if cfg.dry_run:
            log.info(f"  [DRY-RUN] 발송 생략 — slack={slack_go} email={email_go} tier={tier}")
            return

        n = self._get_notifier()

        if slack_go:
            try:
                text = self._compose_slack(det)
                det["sent_slack"] = bool(n.send_slack(masker.mask_text(text)))
                if not det["sent_slack"]:
                    det["errors"].append(f"Slack 발송 실패: {n.last_error}")
            except Exception as e:
                det["errors"].append(f"Slack 발송 예외: {e}")

        if email_go:
            to = self._email_to()
            if not to:
                det["errors"].append("수신 이메일 미설정 — Email 발송 생략")
            else:
                try:
                    body, html = self._compose_email(det, masker)
                    subj = _TIER_SUBJECT.get(tier, _TIER_SUBJECT["single"]).format(
                        ft=str(det["fraud_type"]).upper(), risk=det["risk_score"],
                        tid=det["txn_id"])
                    det["sent_email"] = bool(n.send_email(to, subj, body, html=html))
                    if not det["sent_email"]:
                        det["errors"].append(f"Email 발송 실패: {n.last_error}")
                except Exception as e:
                    det["errors"].append(f"Email 발송 예외: {e}")

        if det["sent_slack"] or det["sent_email"]:
            self.stats["notified"] += 1
            self._mark_notified(det["txn_id"], det["tier"])

    def _compose_slack(self, det: dict) -> str:
        head = _TIER_HEAD.get(det["tier"], _TIER_HEAD["single"])
        body = (det.get("llm") or {}).get("slack", "").strip()
        thr = (self.cfg.th_review if self.cfg.dual_threshold else self.cfg.threshold)
        parts = [head]
        if self.cfg.rich_visuals:
            try:
                try:
                    from pipeline.notify_visuals import slack_visual_single
                except ImportError:
                    from notify_visuals import slack_visual_single
                parts.append(slack_visual_single(
                    {}, det["fraud_type"], det["fraud_name"],
                    det["risk_score"], thr, det.get("proba"), self.clf_mode))
            except Exception as e:
                log.debug(f"Slack 시각화 생략: {e}")
        parts.append(f"거래 ID: `{det['txn_id']}`  ·  출처: {det['source']}")
        if body:
            parts.append(body)
        return "\n".join(p for p in parts if p)

    def _compose_email(self, det: dict, masker) -> tuple[str, str | None]:
        raw = (det.get("llm") or {}).get("email", "").strip()
        body = masker.mask_text(raw) or self._fallback_texts(det, {})["email"]
        if not self.cfg.rich_visuals:
            return body, None
        try:
            try:
                from pipeline.notify_visuals import email_html_single, wrap_email
            except ImportError:
                from notify_visuals import email_html_single, wrap_email
            thr = (self.cfg.th_review if self.cfg.dual_threshold else self.cfg.threshold)
            kpi = email_html_single({}, det["fraud_type"], det["fraud_name"], True,
                                    det["risk_score"], thr, det.get("proba"), self.clf_mode)
            title = ("FDS 이상거래 확정 통보" if det["tier"] == "confirm"
                     else "FDS 이상거래 탐지")
            return body, wrap_email({}, title, kpi, body)
        except Exception as e:
            log.debug(f"Email 시각화 생략 → 평문 발송: {e}")
            return body, None

    def _fallback_texts(self, det: dict, masked: dict) -> dict:
        """LLM 미사용/실패 시에도 알림은 반드시 나가야 한다."""
        tid = det["txn_id"]
        ft = str(det["fraud_type"]).upper()
        amt = masked.get("Transaction_Amount", "N/A")
        ch = masked.get("Channel", "N/A")
        line = (f"{ft}형({det['fraud_name']}) 의심 · 위험점수 {det['risk_score']:.4f}\n"
                f"거래 {tid} · 금액 {amt} · 채널 {ch}")
        email = (f"FDS 자동 탐지 결과입니다.\n\n"
                 f"거래 ID: {tid}\n예측 유형: {ft} ({det['fraud_name']})\n"
                 f"위험 점수: {det['risk_score']:.4f}\n발송 등급: {det['tier']}\n"
                 f"금액: {amt} / 채널: {ch}\n\n"
                 f"※ LLM 분석을 사용하지 못해 기본 양식으로 발송되었습니다.\n"
                 f"   상세 근거는 대시보드에서 해당 거래를 조회하세요.")
        return {"analysis": email, "slack": line, "email": email}

    def _trip_llm_breaker(self, soft: bool = False):
        """연속 실패가 임계치를 넘으면 LLM 호출을 일정 시간 건너뛴다.

        llama.cpp가 죽어 있으면 1건당 4초 timeout × 3콜 = 12초를 헛되이 쓴다.
        이상거래가 몰리면 워처가 사실상 멈추므로, 탐지·발송은 계속하되
        LLM만 잠시 우회한다(폴백 양식으로 발송 — 알림은 절대 멈추지 않는다).
        """
        self._llm_fail_streak += 1
        if self._llm_fail_streak >= self.cfg.llm_breaker_fails:
            self._llm_off_until = time.time() + self.cfg.llm_breaker_cooldown
            self._llm_fail_streak = 0
            log.warning(
                f"🔌 LLM 서킷 차단 — 연속 실패 {self.cfg.llm_breaker_fails}회. "
                f"{int(self.cfg.llm_breaker_cooldown)}초간 폴백 양식으로만 발송합니다. "
                f"(llama.cpp 서버가 떠 있는지 확인하세요)"
                + ("" if not soft else " [응답은 왔으나 폴백 텍스트였음]"))

    # ══════════════════════════════════════════════════════
    # DB — WAL + busy_timeout (대시보드와 동시 접근 대비)
    # ══════════════════════════════════════════════════════

    def _conn(self):
        con = sqlite3.connect(self.cfg.db_path, timeout=30)
        try:
            con.execute("PRAGMA journal_mode=WAL")     # 🐛 워처+대시보드 동시 접근 시 'database is locked' 방지
            con.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        return con

    def _init_db(self):
        con = self._conn()
        # transactions 스키마는 data_streamer._init_db와 동일하게 유지 (대시보드 이력 뷰어 호환)
        con.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT,
                fraud_type     TEXT,
                risk_score     REAL,
                is_anomaly     INTEGER DEFAULT 0,
                input_mode     TEXT,
                true_label     TEXT,
                processed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS notified (
                txn_id  TEXT PRIMARY KEY,
                tier    TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        self._migrate_transactions(con)
        con.commit()
        con.close()

    # 구버전 DB 호환 — 기존 fds_results.db에는 input_mode/true_label이 없을 수 있다.
    #   CREATE TABLE IF NOT EXISTS는 '이미 있는' 테이블을 손대지 않으므로
    #   컬럼이 빠진 채로 INSERT가 계속 실패한다(무인 운영에서 조용한 데이터 유실).
    #   ALTER TABLE ADD COLUMN은 비파괴적이라 기존 데이터는 그대로 보존된다.
    _TX_ADD_COLUMNS = (
        ("transaction_id", "TEXT"),
        ("fraud_type", "TEXT"),
        ("risk_score", "REAL"),
        ("is_anomaly", "INTEGER DEFAULT 0"),
        ("input_mode", "TEXT"),
        ("true_label", "TEXT"),
        ("processed_at", "TIMESTAMP"),   # ※ ALTER는 CURRENT_TIMESTAMP 기본값을 못 받는다
    )

    def _migrate_transactions(self, con):
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(transactions)")}
        except Exception as e:
            log.debug(f"스키마 확인 실패: {e}")
            return
        if not cols:
            return
        added = []
        for name, ddl in self._TX_ADD_COLUMNS:
            if name in cols:
                continue
            try:
                con.execute(f"ALTER TABLE transactions ADD COLUMN {name} {ddl}")
                added.append(name)
            except Exception as e:
                log.warning(f"transactions.{name} 컬럼 추가 실패: {e}")
        if added:
            log.warning(f"🔧 구버전 DB 감지 — transactions에 컬럼 추가: {', '.join(added)} "
                        f"(기존 데이터는 보존됩니다)")

    def _already_notified(self, txn_id: str, tier: str) -> bool:
        """최근 dedup_hours 내에 같은 거래로 **동급 이상** 알림을 보냈으면 True."""
        try:
            con = self._conn()
            cur = con.execute(
                "SELECT tier FROM notified WHERE txn_id=? "
                "AND sent_at > datetime('now', ?)",
                (txn_id, f"-{int(self.cfg.dedup_hours)} hours"))
            r = cur.fetchone()
            con.close()
            if not r:
                return False
            return _TIER_RANK.get(r[0], 0) >= _TIER_RANK.get(tier, 0)
        except Exception as e:
            log.debug(f"중복 확인 실패(발송 진행): {e}")
            return False

    def _mark_notified(self, txn_id: str, tier: str):
        try:
            con = self._conn()
            con.execute(
                "INSERT INTO notified (txn_id, tier, sent_at) VALUES (?,?,datetime('now')) "
                "ON CONFLICT(txn_id) DO UPDATE SET tier=excluded.tier, sent_at=excluded.sent_at",
                (txn_id, tier))
            con.commit()
            con.close()
        except Exception as e:
            log.debug(f"알림 이력 기록 실패: {e}")

    def _tx_columns(self) -> set:
        """transactions 테이블의 실제 컬럼 (1회만 조회해 캐시).

        대시보드가 만든 테이블은 detected_at·model·threshold 를 쓰고,
        data_streamer가 만든 테이블은 processed_at·input_mode·true_label 을 쓴다.
        어느 쪽이든 **존재하는 컬럼에만** INSERT하도록 맞춘다.
        """
        if self._tx_cols is None:
            try:
                con = self._conn()
                self._tx_cols = {r[1] for r in con.execute("PRAGMA table_info(transactions)")}
                con.close()
            except Exception:
                self._tx_cols = set()
        return self._tx_cols

    # 대시보드(dashboard._save_detection_to_db)가 실제로 읽고 쓰는 테이블은
    # transactions 가 아니라 **detections** 다. 스키마·UPSERT 규칙을 그대로 맞춰
    # 워처 탐지가 기존 '누적 탐지 이력' 뷰어에 함께 나타나게 한다.
    _DETECTIONS_DDL = (
        "CREATE TABLE IF NOT EXISTS detections ("
        "transaction_id TEXT PRIMARY KEY, fraud_type TEXT, risk_score REAL, "
        "is_anomaly INTEGER, model TEXT, threshold REAL, "
        "detected_at TEXT DEFAULT (datetime('now','localtime')), raw_json TEXT)")

    def _save_db(self, row: dict, det: dict, masked: dict | None = None):
        self._save_detections(det, masked if masked is not None else row)
        self._save_transactions(row, det)

    def _save_detections(self, det: dict, row_for_json: dict):
        """대시보드 이력 뷰어용. transaction_id UPSERT (대시보드와 동일 규칙)."""
        import json
        thr = (self.cfg.th_review if self.cfg.dual_threshold else self.cfg.threshold)
        # ⚠️ raw_json에는 반드시 마스킹본을 넣는다. 대시보드 경로는 원본을 넣지만,
        #    워처는 무인으로 대량 적재하므로 DB에 평문 PII가 쌓이면 위험이 훨씬 크다.
        try:
            safe = self._get_masker().mask_row(
                {k: v for k, v in row_for_json.items() if not str(k).startswith("_")})
        except Exception:
            safe = {}
        payload = json.dumps({k: str(v) for k, v in safe.items()},
                             ensure_ascii=False)[:4000]
        try:
            con = self._conn()
            con.execute(self._DETECTIONS_DDL)
            con.execute(
                "INSERT INTO detections VALUES (?,?,?,?,?,?,datetime('now','localtime'),?) "
                "ON CONFLICT(transaction_id) DO UPDATE SET "
                "fraud_type=excluded.fraud_type, risk_score=excluded.risk_score, "
                "is_anomaly=excluded.is_anomaly, model=excluded.model, "
                "threshold=excluded.threshold, detected_at=datetime('now','localtime'), "
                "raw_json=excluded.raw_json",
                (det["txn_id"], det["fraud_type"], round(float(det["risk_score"]), 6),
                 int(det["is_anomaly"]), f"👁 워처 · {self.clf_mode}", float(thr), payload))
            con.commit()
            con.close()
        except Exception as e:
            det["errors"].append(f"detections 저장 실패: {e}")
            if not self._db_warned:
                self._db_warned = True
                log.warning(f"⚠️ detections 저장 실패 — 이후 동일 오류는 생략: {e}")
            self.stats["db_fail"] = self.stats.get("db_fail", 0) + 1

    def _save_transactions(self, row: dict, det: dict):
        cols = self._tx_columns()
        if not cols:
            return
        now = time.strftime("%Y-%m-%d %H:%M:%S")     # 대시보드 기존 행과 같은 로컬시각
        thr = (self.cfg.th_review if self.cfg.dual_threshold else self.cfg.threshold)
        payload = {
            "transaction_id": det["txn_id"],
            "fraud_type": det["fraud_type"],
            "risk_score": float(det["risk_score"]),
            "is_anomaly": int(det["is_anomaly"]),
            "input_mode": det["source"],
            "true_label": str(row.get("_true_label", "") or row.get("Fraud_Type", "") or ""),
            "model": self.clf_mode,
            "threshold": float(thr),
            "detected_at": now,
            "processed_at": now,
        }
        use = {k: v for k, v in payload.items() if k in cols}
        if not use:
            return
        sql = (f"INSERT INTO transactions ({', '.join(use)}) "
               f"VALUES ({', '.join('?' * len(use))})")
        try:
            con = self._conn()
            con.execute(sql, tuple(use.values()))
            con.commit()
            con.close()
        except Exception as e:
            det["errors"].append(f"DB 저장 실패: {e}")
            # 🐛 FIX: 기존엔 log.debug라 -v 없이는 보이지 않았다. 무인 운영에서
            #   "탐지는 되는데 DB에 한 건도 안 쌓이는" 상태를 아무도 모르게 된다.
            #   최초 1회는 WARNING으로 크게 남기고, 이후는 조용히 카운트만 한다.
            if not self._db_warned:
                self._db_warned = True
                log.warning(f"⚠️ DB 저장 실패 — 이후 동일 오류는 생략합니다: {e}\n"
                            f"   시도한 컬럼: {', '.join(use)}")
            self.stats["db_fail"] = self.stats.get("db_fail", 0) + 1

    # ── 편의 ──
    def config_dict(self) -> dict:
        return asdict(self.cfg)

"""
BatchAnalyzer — 데이터 묶음(2건 이상) 일괄 분석 (신규)

흐름:
  ① rows(list[dict]) → MLClassifier 일괄 분류
  ② 유형별 집계 ("정상 n건, A형 2건, C형 4건 …")
  ③ PII 마스킹 후 상위 위험 거래 요약 추출
  ④ 배치 전용 내부 프롬프트 1회 LLM 호출 → 통합 보고서
  ⑤ Slack 1줄 요약 + 이메일 본문 폴백 자동 생성

LLM 실패 시에도 집계 기반 폴백 보고서를 반드시 반환하므로
대시보드가 죽지 않는다.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# ── i18n (✨ v9.3 폴백 다국어화) — 없으면 한국어(기존 동작) 유지 ──
try:
    from i18n_data import make_t as _make_t, FRAUD_TYPE_DETAILS_I18N as _FTD_I18N
    _I18N_OK = True
except Exception:
    _I18N_OK = False
    _FTD_I18N = {}

def _bt(lang):
    """lang용 t 헬퍼 (i18n 없으면 None)."""
    return _make_t({'lang': lang}) if _I18N_OK else None

def _bname(ft, lang):
    """배치 폴백용 유형명 — i18n 우선, 없으면 모듈 FRAUD_TYPE_NAMES(한국어)."""
    try:
        if _I18N_OK and lang in _FTD_I18N and ft in _FTD_I18N[lang]:
            return _FTD_I18N[lang][ft]['name']
    except Exception:
        pass
    return FRAUD_TYPE_NAMES.get(ft, '-')

# ══════════════════════════════════════════════════════════
# 🔴 v16: 유형명 전면 교체 — 기존 이름은 데이터와 무관한 일반 명칭이었다.
#   (예: f='피싱 사기' → 실측은 Others채널 100% · 고액입금 100% · 단말흔적 0% =
#    "정상거래로 위장된 최종 인출". 이름이 실제 패턴과 어긋나면 AI 분석과 담당자
#    판단이 동시에 오염된다.)
#   팀 EDA 정의 + 120,000행 전수 검증 결과를 반영한 이름.
# ══════════════════════════════════════════════════════════
FRAUD_TYPE_NAMES = {
    'a': '원거리 즉시이체 (계정탈취)',
    'b': '저신용층 표적 계좌탈취',
    'c': '악성앱 정보탈취 → ATM 출금',
    'd': '약신호 미분류 (조사 필요)',
    'e': '원격제어 대량입금 → ATM 전액인출',
    'f': '위장 최종인출 (자금세탁 의심)',
    'g': '대량입금 인출 중간단계',
    'h': '휴면계좌 재개 → 잔액부족 실패',
    'i': '고액 이체 (확신도 낮음)',
    'j': '대포통장 초기 자금유입',
    'k': '계좌 재사용 반복거래 · 인증변경',
    'l': '고령층 표적 명의도용',
    'm': '정상 거래',
}

# 유형별 한 줄 근거 (세션1 분포 차트·툴팁·AI 프롬프트 공용)
FRAUD_TYPE_EVIDENCE = {
    'a': '접속거리 273km 초과가 100% (타 유형 11%) · 단말 악성흔적 없음 → 외부 침입',
    'b': '신용등급 C/D/E 100% (A/B/S 0%) · 모바일 55% · 루팅 51% · VPN 42%',
    'c': '단말 악성행위 플래그 평균 1.74개 (전체 0.58) · ATM 54% · Windows 45%',
    'd': '인터넷뱅킹 45% · 미사용단말 100% · 위협흔적 거의 없음 · 거래실패 0%',
    'e': '고액입금 100% + ATM 100% · 루팅 2.4배 → 감염 단말로 입금 유입 후 현금화',
    'f': '고액입금 100% + Others채널 100% · 루팅 0% 악성 0% → 흔적 없는 은밀 인출',
    'g': '고액입금 100% · 채널 혼합 · 수취계좌 이력 없음 → e·f 사이 중간 단계',
    'h': '1개월 표준편차 10만원 미만 100% · 거래실패 17%(최고) · 잔액부족 에러 17%(최고)',
    'i': '거래금액 z=1.97(최고) · 1개월 최대이체 z=0.87(최고) · 인증변경 3.83(최고)',
    'j': '수취계좌 정지 100% + 미사용계좌 100% 동시 · 수취계좌 거래이력 z=-0.72(최저)',
    'k': '동일 수취계좌 거래 z=2.17(최고) · 미사용계좌 0%(활성) · 인증변경 3.59',
    'l': '출생연도 1955~1965 편중 (z=-1.18) · 단말 악성흔적 최저 → 심리 조작 정황',
    'm': '잔액 대비 소액 이체 · 단말 위협신호 없음',
}

# 🐛 FIX(v10): 배치 프롬프트의 '모든 내용은 한국어' 하드코딩이 lang_suffix(다국어 지시문)와
#   모순되던 문제 → UI 언어로 파라미터화. (폴백 템플릿은 이미 현지화돼 있었고, LLM 생성분만 문제였음)
_PROMPT_LANG_NAME = {"ko": "한국어", "en": "영어(English)",
                     "ja": "일본어(日本語)", "zh": "중국어(简体中文)"}

# ══════════════════════════════════════════════════════════
# 🖊 v14: 대시보드 "프롬프트 편집" 기능용 — 배치 종합보고서 기본 템플릿(단일 진실 공급원)
#   llm_analyzer.py의 DEFAULT_*_PROMPT_TEMPLATE와 같은 패턴. .format(**vars)로 채워진다.
#   단건(analysis/slack/email)과 자리표시자 세트가 다르므로(집계값 위주) 별도로 문서화.
# ══════════════════════════════════════════════════════════
PROMPT_VARS_HELP_BATCH = (
    "사용 가능한 자리표시자 — "
    "{total} 전체거래수 · {summary} 탐지요약문 · {anomaly_count} 이상거래수 · "
    "{threshold} 임계값 · {avg_risk} 평균위험점수 · {max_risk} 최고위험점수 · "
    "{min_risk} 최저위험점수 · {median_risk} 중앙위험점수 · "
    "{type_lines} 유형별분포목록 · {risky_lines} 위험상위거래목록 · "
    "{row_lines} ✨행별 위험점수·임계초과여부 전체목록 · {row_lines_note} 생략건수안내 · "
    "{risk_hist} 위험도 구간별 분포 · {rag_block} 참고문서 · {lang_name} 응답언어명"
)

# ✨ v11: 프롬프트에 넣을 행별 목록의 최대 건수 — 초과분은 위험도 내림차순 상위만 남기고
#   나머지는 {row_lines_note}로 "이하 N건 생략(위험도 X 이하)" 안내를 붙인다.
MAX_PROMPT_ROWS = 60

DEFAULT_BATCH_PROMPT_TEMPLATE = (
    "당신은 전자금융 FDS 전문 분석 AI입니다. 아래는 거래 묶음(배치)의 일괄 탐지 결과입니다.\n\n"
    "[배치 개요]\n"
    " - 전체 거래 수: {total}건\n"
    " - 탐지 요약: {summary}\n"
    " - 이상거래: {anomaly_count}건 (임계값 {threshold} 기준)\n"
    " - 평균 위험점수: {avg_risk} / 최고 위험점수: {max_risk}\n\n"
    " - 위험점수 분포: 최저 {min_risk} · 중앙 {median_risk} · 평균 {avg_risk} · 최고 {max_risk}\n"
    " - 구간별 건수: {risk_hist}\n\n"
    "[유형별 이상거래 분포]\n{type_lines}\n\n"
    "[행별 판정 결과 — 거래 한 건마다의 위험점수와 임계값({threshold}) 대비 결과]\n"
    "{row_lines}\n{row_lines_note}\n\n"
    "[위험 상위 거래 — 개인정보 마스킹 완료]\n{risky_lines}\n\n"
    "[참고 문서]\n{rag_block}\n\n"
    "아래 양식을 반드시 지켜 【📋AI 배치 분석 보고서】를 한 장만 작성하세요. "
    "(마크다운 기호 사용 금지, 반복 작성 금지, 모든 내용은 {lang_name})\n"
    "---\n"
    "【📋AI 배치 분석 보고서】\n\n"
    "【탐지 요약】 첫 문장은 반드시 위의 '탐지 요약' 문구를 그대로 인용해 시작하고, "
    "전체 배치의 위험 수준을 2문장으로 총평\n"
    "【행별 위험도 판정】 위 [행별 판정 결과]를 근거로, 전체 평균이 아니라 **거래 건별 "
    "위험점수를 그대로 인용**해 서술하십시오. 임계값을 넘은 거래는 각각 거래ID와 위험점수를 "
    "명시하고, 임계값 ±0.1 구간의 경계 거래가 있으면 따로 지목하십시오. "
    "절대 평균값 하나로 뭉개지 마십시오. (각 항목 줄바꿈)\n"
    "【유형별 패턴 분석】 탐지된 이상 유형별로 1~2문장씩, 해당 유형의 특징적 패턴과 "
    "이번 배치에서의 의미를 분석 (불릿, 각각 줄바꿈)\n"
    "【우선 조치 대상】 위험 상위 거래 중 즉시 확인이 필요한 거래를 순서대로 지목하고 사유를 1문장씩 (각각 줄바꿈)\n"
    "【권장 조치】 즉시/단기/장기 각 1문장 (각각 줄바꿈)"
)


def _mask_txn_id(masker, raw_id) -> str:
    """✨ v11: 거래ID만 저렴하게 마스킹.
    행별 목록을 LLM 프롬프트에 넣으므로 **전 행의 ID를 마스킹해야 한다**(기존엔 상위 5건만
    마스킹됐다). mask_row()는 행 전체를 훑어 느리므로 ID 마스커만 직접 호출한다."""
    sid = str(raw_id)
    if masker is None or getattr(masker, "level", "off") == "off":
        return sid
    try:
        try:
            from pipeline.pii_masker import COLUMN_MASKERS
        except ImportError:
            from pii_masker import COLUMN_MASKERS
        if "ID" in getattr(masker, "target_columns", ()) and "ID" in COLUMN_MASKERS:
            return str(COLUMN_MASKERS["ID"](sid))
    except Exception:
        pass
    return sid


def _risk_hist(risks: list, bins=(0.0, 0.2, 0.4, 0.6, 0.8, 1.01)) -> dict:
    """위험도 구간별 건수 — LLM이 '평균 하나'가 아닌 분포를 보게 한다."""
    out = {}
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        out[f"{lo:.1f}~{min(hi,1.0):.1f}"] = sum(1 for r in risks if lo <= r < hi)
    return out


def build_row_lines(res: "BatchResult", threshold: float,
                    limit: int = None, lang: str = "ko") -> tuple[str, str]:
    """✨ v11: 행별 위험점수·임계 대비 판정 목록 → (본문, 생략안내).

    요청 반영: 배치 리포트가 '전체 평균'만 말하던 문제 → 거래 한 건마다
    위험점수와 임계 초과 여부를 프롬프트에 직접 넣어 LLM이 건별로 서술하게 한다.
    건수가 많으면 위험도 내림차순 상위 limit건만 넣고 나머지는 안내로 요약한다.
    """
    limit = MAX_PROMPT_ROWS if limit is None else limit
    rows = res.rows_out
    if not rows:
        return " (판정된 거래 없음)", ""
    ordered = sorted(rows, key=lambda r: r.get("risk_score", 0.0), reverse=True)
    shown, rest = ordered[:limit], ordered[limit:]
    _t = _bt(lang)
    lines = []
    for r in shown:
        risk = float(r.get("risk_score", 0.0))
        ft = str(r.get("fraud_type", "?")).upper()
        margin = risk - threshold
        if _t:
            verdict = _t("fb.row_over") if risk >= threshold else _t("fb.row_under")
            near = _t("fb.row_near") if abs(margin) <= 0.1 else ""
        else:
            verdict = "임계 초과 → 이상" if risk >= threshold else "임계 미만 → 정상"
            near = " ⚠경계" if abs(margin) <= 0.1 else ""
        _rid = r.get('txn_id_masked', r.get('txn_id', '-'))
        _i = r.get('idx', 0) + 1
        if _t:      # ✨ v11: 행 라인 자체도 현지화
            lines.append(_t("fb.row_line", i=_i, id=_rid, ft=ft, r=f"{risk:.4f}",
                            d=f"{margin:+.4f}", verdict=verdict, near=near))
        else:
            lines.append(f" {_i:>4}. {_rid:<18} | {ft}형 | 위험 {risk:.4f} "
                         f"({margin:+.4f}) | {verdict}{near}")
    note = ""
    if rest:
        cut = float(rest[0].get("risk_score", 0.0))
        n_over = sum(1 for r in rest if float(r.get("risk_score", 0.0)) >= threshold)
        if _t:
            note = _t("fb.row_omitted", n=len(rest), cut=f"{cut:.4f}", over=n_over)
        else:
            note = (f" … 이하 {len(rest)}건 생략 (위험점수 {cut:.4f} 이하, "
                    f"그 중 임계 초과 {n_over}건)")
    return ("\n".join(lines) or " (없음)"), note


@dataclass
class BatchResult:
    total: int = 0
    counts: dict = field(default_factory=dict)        # {'m': 94, 'a': 2, 'c': 4}
    anomaly_count: int = 0
    avg_risk: float = 0.0
    max_risk: float = 0.0
    min_risk: float = 0.0          # ✨ v11
    median_risk: float = 0.0       # ✨ v11
    risk_hist: dict = field(default_factory=dict)   # ✨ v11 위험도 구간별 건수
    rows_out: list = field(default_factory=list)      # 건별 결과 [{txn_id, fraud_type, risk_score, is_anomaly, true_label}]
    top_risky: list = field(default_factory=list)     # 위험 상위 k건 (마스킹 완료)
    summary_line: str = ""                            # "정상 94건, A형 2건, C형 4건으로 측정되었습니다"
    analysis: str = ""                                # LLM 통합 보고서 (또는 폴백)
    slack: str = ""
    email: str = ""
    llm_used: bool = False
    errors: list = field(default_factory=list)
    elapsed_sec: float = 0.0


# ══════════════════════════════════════════════════════════
# 메인 실행
# ══════════════════════════════════════════════════════════

def run_batch(
    rows: list[dict],
    classifier,                    # MLClassifier
    threshold: float = 0.5,
    analyzer=None,                 # LLMAnalyzer | None → None이면 폴백 보고서만
    masker=None,                   # PIIMasker | None
    rag=None,                      # RAGSearcher | None
    top_k_risky: int = 5,
    lang_suffix: str = "",         # 다국어 응답 지시문 (LLM 프롬프트에 부착)
    lang: str = "ko",              # ✨ v9.3: UI 언어 — 폴백 템플릿(요약/보고서/Slack/Email) 현지화
    progress_cb=None,              # (i, n) → None  대시보드 진행바 콜백
) -> BatchResult:
    t0 = time.time()
    res = BatchResult(total=len(rows))
    if not rows:
        res.errors.append("입력 행이 비어 있음")
        return res

    # ── ① 일괄 분류 ─────────────────────────────────────
    risks = []
    for i, row in enumerate(rows):
        try:
            ft, risk, _proba = classifier.predict(row)
        except Exception as e:
            res.errors.append(f"row {i} 분류 실패: {e}")
            if progress_cb:                 # 🐛 FIX(v10): 실패 행에서 진행바가 멈추던 문제
                progress_cb(i + 1, len(rows))
            continue
        is_anom = (ft != "m") or (risk >= threshold)
        res.counts[ft] = res.counts.get(ft, 0) + 1
        res.anomaly_count += int(is_anom)
        risks.append(risk)
        _raw_id = str(row.get("transaction_id", row.get("ID", f"ROW_{i}")))
        res.rows_out.append({
            "idx": i,
            "txn_id": _raw_id,
            # ✨ v11: 행별 목록이 LLM 프롬프트로 나가므로 전 행 ID를 마스킹해 함께 보관
            "txn_id_masked": _mask_txn_id(masker, _raw_id),
            "fraud_type": ft,
            "risk_score": round(float(risk), 4),
            "is_anomaly": is_anom,
            "true_label": str(row.get("_true_label", "")),
            "_row": row,
        })
        if progress_cb:
            progress_cb(i + 1, len(rows))

    if risks:
        _sorted = sorted(risks)
        res.avg_risk = round(sum(risks) / len(risks), 4)
        res.max_risk = round(max(risks), 4)
        res.min_risk = round(_sorted[0], 4)                                  # ✨ v11
        _n = len(_sorted)
        res.median_risk = round((_sorted[_n // 2] if _n % 2 else
                                 (_sorted[_n // 2 - 1] + _sorted[_n // 2]) / 2), 4)
        res.risk_hist = _risk_hist(risks)

    # ── ② 집계 요약문 ("정상 n건, A형 2건, C형 4건 …") ──
    res.summary_line = build_summary_line(res.counts, lang)

    # ── ③ 상위 위험 거래 (마스킹) ───────────────────────
    ranked = sorted((r for r in res.rows_out if r["is_anomaly"]),
                    key=lambda r: r["risk_score"], reverse=True)[:top_k_risky]
    for r in ranked:
        raw = {k: v for k, v in r["_row"].items() if not k.startswith("_")}
        masked = masker.mask_row(raw) if masker else raw
        # 거래ID도 마스킹본 사용 (ID는 Level 1 직접 식별자 — LLM 전달 전 마스킹 필수)
        masked_id = masked.get("ID", masked.get("transaction_id", r["txn_id"]))
        res.top_risky.append({
            "txn_id": str(masked_id),
            "fraud_type": r["fraud_type"],
            "risk_score": r["risk_score"],
            "amount": masked.get("Transaction_Amount", "N/A"),
            "channel": masked.get("Channel", "N/A"),
            "distance": masked.get("Distance", "N/A"),
        })

    # 내부 참조 row 제거 (세션 저장 시 메모리 절약)
    for r in res.rows_out:
        r.pop("_row", None)

    # ── ④ LLM 통합 보고서 (1회 호출) ────────────────────
    rag_ctx = []
    if rag is not None and res.anomaly_count:
        try:
            top_types = [ft for ft, _ in sorted(
                ((k, v) for k, v in res.counts.items() if k != "m"),
                key=lambda x: x[1], reverse=True)[:2]]
            for ft in top_types:
                rag_ctx += rag.search(f"사기유형 {ft} 이상거래 대응", ft)[:2]
        except Exception as e:
            res.errors.append(f"RAG 검색 실패: {e}")

    prompt, _batch_prompt_err = build_batch_prompt(
        res, threshold, rag_ctx, lang,
        # 🖊 v14: analyzer(LLMAnalyzer)가 이미 들고 있는 prompt_overrides 중 'batch' 슬롯만 사용 —
        #   단건 편집기와 동일한 저장소를 공유하므로 새 인자·새 UI 배선이 따로 필요 없다.
        override=getattr(analyzer, 'prompt_overrides', {}).get('batch') if analyzer is not None else None,
    )
    prompt = prompt + lang_suffix
    if _batch_prompt_err:
        res.errors.append(_batch_prompt_err)
    if analyzer is not None:
        try:
            # 🐛 FIX(v10): _call()은 _errors를 비우지 않는다(analyze()/test_connection()만 비움).
            #   → 직전 단건 분석에서 남은 오류가 배치 결과 화면에 유령처럼 섞여 나왔다.
            if hasattr(analyzer, "_errors"):
                analyzer._errors.clear()
            out = analyzer._call(prompt, max_tokens=1536, timeout=180)
            if out and out.strip():
                res.analysis = out.strip()
                res.llm_used = True
            else:
                res.errors += getattr(analyzer, "_errors", [])
        except Exception as e:
            res.errors.append(f"LLM 호출 실패: {e}")

    if not res.analysis:
        res.analysis = build_fallback_report(res, threshold, lang)

    # ── ⑤ Slack/이메일 (집계 기반 — 배치는 템플릿이 안정적) ──
    res.slack = build_slack(res, threshold, lang)
    res.email = build_email(res, threshold, lang)
    res.elapsed_sec = round(time.time() - t0, 2)
    return res


# ══════════════════════════════════════════════════════════
# 요약문 · 프롬프트 · 폴백
# ══════════════════════════════════════════════════════════

def build_summary_line(counts: dict, lang: str = "ko") -> str:
    """{'m':94,'a':2,'c':4} → '정상 94건, A형 2건, C형 4건으로 측정되었습니다' (언어별)"""
    _t = _bt(lang)   # ✨ v9.3
    if _t:
        parts = []
        if counts.get("m"):
            parts.append(_t("fb.summary_normal", n=counts["m"]))
        for ft in "abcdefghijkl":
            if counts.get(ft):
                parts.append(_t("fb.summary_type", ft=ft.upper(), n=counts[ft]))
        return _t("fb.summary_line", parts=", ".join(parts)) if parts else _t("fb.summary_none")
    # i18n 미가용 → 기존 한국어
    parts = []
    if counts.get("m"):
        parts.append(f"정상 {counts['m']}건")
    for ft in "abcdefghijkl":
        if counts.get(ft):
            parts.append(f"{ft.upper()}형 {counts[ft]}건")
    return (", ".join(parts) + "으로 측정되었습니다") if parts else "측정된 거래가 없습니다"


def build_batch_prompt(res: BatchResult, threshold: float, rag_ctx: list[str],
                       lang: str = "ko", override: str | None = None) -> tuple[str, str | None]:
    """배치 전용 내부 프롬프트 — 단건 프롬프트와 달리 '집계 → 패턴 → 우선순위' 구조.
    🖊 v14: override(대시보드 프롬프트 편집기 저장값)가 있으면 DEFAULT_BATCH_PROMPT_TEMPLATE
    대신 사용(.format(**vars)). 형식 오류(오타 자리표시자 등) 시 기본 템플릿으로 안전 복귀하고
    (프롬프트, 오류메시지) 튜플을 반환 — 호출부(run_batch)가 res.errors에 기록해 화면에 보여준다."""
    _lang_name = _PROMPT_LANG_NAME.get(lang, "한국어")   # 🐛 FIX(v10)
    type_lines = "\n".join(
        f" - {ft.upper()}형 ({FRAUD_TYPE_NAMES.get(ft, '알 수 없음')}): {n}건"
        for ft, n in sorted(res.counts.items(), key=lambda x: (x[0] == 'm', -x[1]))
        if ft != "m"
    ) or " - (이상 유형 없음)"

    risky_lines = "\n".join(
        f" {i+1}. 거래ID {r['txn_id']} | {r['fraud_type'].upper()}형 | 위험점수 {r['risk_score']:.4f} | "
        f"금액 {r['amount']} | 채널 {r['channel']}"
        for i, r in enumerate(res.top_risky)
    ) or " (없음)"

    rag_block = "\n".join(f" - {c}" for c in rag_ctx) if rag_ctx else " - (참고 문서 없음)"

    # ✨ v11: 행별 판정 목록 — '전체 평균'만 보던 LLM에게 건별 위험점수를 직접 제공
    row_lines, row_lines_note = build_row_lines(res, threshold, lang=lang)
    risk_hist = ", ".join(f"{k} {v}건" for k, v in (res.risk_hist or {}).items()) or "(없음)"

    _vars = dict(total=res.total, summary=res.summary_line, anomaly_count=res.anomaly_count,
                 threshold=f"{threshold:.2f}", avg_risk=f"{res.avg_risk:.4f}",
                 max_risk=f"{res.max_risk:.4f}", min_risk=f"{res.min_risk:.4f}",
                 median_risk=f"{res.median_risk:.4f}", type_lines=type_lines,
                 row_lines=row_lines, row_lines_note=row_lines_note, risk_hist=risk_hist,
                 risky_lines=risky_lines, rag_block=rag_block, lang_name=_lang_name)

    _ov = (override or "").strip()
    if _ov:
        try:
            return _ov.format(**_vars), None
        except Exception as e:
            log.warning(f"커스텀 배치 프롬프트 형식 오류 → 기본 프롬프트 사용: {e}")
            return (DEFAULT_BATCH_PROMPT_TEMPLATE.format(**_vars),
                    f"[프롬프트 편집] batch 커스텀 템플릿 오류로 기본값 사용 — {e}")
    return DEFAULT_BATCH_PROMPT_TEMPLATE.format(**_vars), None


def build_fallback_report(res: BatchResult, threshold: float, lang: str = "ko") -> str:
    """LLM 실패 시 집계 기반 폴백 보고서.

    🐛 FIX(v11): `_t = _bt(lang)`은 i18n_data가 설치돼 있으면 lang='ko'에서도 항상 참이라,
      아래에 있던 '한국어 리터럴 분기'는 사실상 **도달 불가한 죽은 코드**였다.
      → 행별 판정 블록은 두 분기 공통으로 조립해 어느 언어에서도 반드시 포함되게 한다.
    """
    _t = _bt(lang)
    # ✨ v11: LLM이 실패해도 '행별 위험점수'가 보고서에 남는다 (요청 1)
    _rl, _rn = build_row_lines(res, threshold, lang=lang)
    _hist = ", ".join(f"{k} {v}" + ("건" if not _t else "") for k, v in (res.risk_hist or {}).items()) or "-"
    if _t:
        _rows_block = _t("fb.batch_rows_block", rows=_rl, note=_rn,
                         lo=f"{res.min_risk:.4f}", mid=f"{res.median_risk:.4f}",
                         hi=f"{res.max_risk:.4f}", hist=_hist)
    else:
        _rows_block = (f"【행별 위험도 판정】\n"
                       f"위험점수 최저 {res.min_risk:.4f} · 중앙 {res.median_risk:.4f} · "
                       f"최고 {res.max_risk:.4f} · 구간별 {_hist}\n{_rl}\n{_rn}")

    if _t:
        risky = "\n".join(
            _t("fb.batch_risky_line", i=i + 1, id=r['txn_id_masked'] if 'txn_id_masked' in r else r['txn_id'],
               ft=r['fraud_type'].upper(), r=f"{r['risk_score']:.4f}")
            for i, r in enumerate(res.top_risky)
        ) or _t("fb.batch_risky_none")
        type_lines = "\n".join(
            _t("fb.batch_type_line", ft=ft.upper(), name=_bname(ft, lang), n=n)
            for ft, n in sorted(res.counts.items()) if ft != "m"
        ) or _t("fb.batch_no_types")
        base = _t("fb.batch_report", summary=res.summary_line, total=res.total,
                  anomaly=res.anomaly_count, thr=f"{threshold:.2f}", avg=f"{res.avg_risk:.4f}",
                  type_lines=type_lines, risky=risky)
        # 【유형별 분포】 앞에 행별 블록을 끼워 넣는다 (없으면 맨 끝에 붙임)
        for _mk in ("【유형별 분포】", "【Breakdown by type】", "【類型別分布】", "【按类型分布】"):
            if _mk in base:
                return base.replace(_mk, _rows_block + "\n\n" + _mk, 1)
        return base + "\n\n" + _rows_block

    risky = "\n".join(
        f" {i+1}. {r.get('txn_id_masked', r['txn_id'])} — {r['fraud_type'].upper()}형 (위험점수 {r['risk_score']:.4f})"
        for i, r in enumerate(res.top_risky)
    ) or " (없음)"
    type_lines = "\n".join(
        f" • {ft.upper()}형 ({FRAUD_TYPE_NAMES.get(ft,'-')}): {n}건"
        for ft, n in sorted(res.counts.items()) if ft != "m"
    ) or " • 이상 유형 없음"
    return (
        f"【📋AI 배치 분석 보고서】\n\n"
        f"【탐지 요약】\n{res.summary_line}. "
        f"전체 {res.total}건 중 이상거래 {res.anomaly_count}건 "
        f"(임계값 {threshold:.2f}), 평균 위험점수 {res.avg_risk:.4f}입니다.\n\n"
        f"{_rows_block}\n\n"
        f"【유형별 분포】\n{type_lines}\n\n"
        f"【우선 조치 대상】\n{risky}\n\n"
        f"【권장 조치】\n"
        f" 즉시: 위험 상위 거래를 보류하고 담당자 수동 검토를 진행하십시오.\n"
        f" 단기: 다건 탐지된 유형에 대해 고객 본인 확인 절차를 강화하십시오.\n"
        f" 장기: 해당 배치의 오탐/미탐 여부를 라벨링하여 모델 재학습 데이터로 축적하십시오."
    )

def build_slack(res: BatchResult, threshold: float, lang: str = "ko") -> str:
    lvl = "🔴" if res.max_risk >= 0.9 else "🟠" if res.max_risk >= 0.7 else "🟡"
    _t = _bt(lang)   # ✨ v9.3
    if _t:
        return _t("fb.batch_slack", lvl=lvl, summary=res.summary_line, total=res.total,
                  anomaly=res.anomaly_count, avg=f"{res.avg_risk:.4f}",
                  max=f"{res.max_risk:.4f}", thr=f"{threshold:.2f}")
    return (
        f"{lvl} *[배치 탐지] {res.summary_line}*\n"
        f"> 전체 {res.total}건 | 이상 {res.anomaly_count}건 | "
        f"평균 위험 {res.avg_risk:.4f} | 최고 {res.max_risk:.4f} (임계값 {threshold:.2f})"
    )


def build_email(res: BatchResult, threshold: float, lang: str = "ko") -> str:
    line = "━" * 35
    _t = _bt(lang)   # ✨ v9.3
    if _t:
        return _t("fb.batch_email", anomaly=res.anomaly_count, total=res.total,
                  summary=res.summary_line, thr=f"{threshold:.2f}",
                  avg=f"{res.avg_risk:.4f}", max=f"{res.max_risk:.4f}",
                  analysis=res.analysis, line=line)
    return (
        f"제목: [FDS 배치 경보] 이상거래 {res.anomaly_count}건 / 전체 {res.total}건\n\n"
        f"담당자 귀중,\n\nFDS 배치 분석 결과를 보고드립니다.\n\n"
        f"{line}\n■ 배치 개요\n{line}\n"
        f"  탐지 요약  : {res.summary_line}\n"
        f"  전체 거래  : {res.total}건\n"
        f"  이상 거래  : {res.anomaly_count}건 (임계값 {threshold:.2f})\n"
        f"  평균 위험  : {res.avg_risk:.4f} / 최고 {res.max_risk:.4f}\n\n"
        f"{line}\n■ AI 분석 결과\n{line}\n{res.analysis}\n\n"
        f"{line}\n본 메일은 FDS 자동화 시스템에 의해 발송되었습니다.\n"
        f"FDS QA 자동화 시스템 드림"
    )

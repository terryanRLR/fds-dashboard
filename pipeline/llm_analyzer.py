"""
LLMAnalyzer — 3단계 분리 호출 + 대시보드 오버라이드
  1호출: 분석 리포트 (판정 근거 + 이상 패턴 + 오탐 체크 + 권장 조치)
  2호출: Slack 알림 (2줄 요약)
  3호출: 이메일 본문 (구조화 전문 양식)

v3 — (a) 3단계 아키텍처 + 패치 대시보드 오버라이드 병합
"""

import os
import re
import sys
import logging
import requests

# 🐛 FIX: 대시보드 없이 단독 사용 시에도 .env의 API 키를 읽을 수 있도록
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── 콘솔/로그 인코딩 강제 UTF-8 ──────────────────────────
# 실행 환경(Windows 콘솔, 일부 서비스/크론 환경 등)에서 기본 인코딩이
# UTF-8이 아닐 경우, 한글이 포함된 문자열을 print/log 하는 과정에서
# "'ascii' codec can't encode characters..." 형태의 UnicodeEncodeError가
# 발생할 수 있다 (anthropic/httpx SDK 내부 로깅 경로에서도 동일하게 발생 가능).
for _stream in (sys.stdout, sys.stderr):
    try:
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

log = logging.getLogger(__name__)


def _trim_repeats(text: str, anchor_pattern: str) -> str:
    """anchor_pattern으로 찾은 '문서 시작' 마커가 2회 이상 등장하면 첫 번째 블록만 남긴다.
    llama.cpp가 stop 시퀀스를 만나지 못해 동일 문서(분석 리포트/이메일 등)를
    연달아 여러 번 생성하는 현상(예: 이메일 3연속 생성)을 방지한다."""
    if not text:
        return text
    matches = list(re.finditer(anchor_pattern, text))
    if len(matches) <= 1:
        return text
    return text[:matches[1].start()].rstrip()


def _is_degenerate(text: str, repeat_threshold: int = 6) -> bool:
    """토큰 반복 루프('de de de de...', '(approx. 0.7374)' 무한반복 등)나
    챗 템플릿 특수/채널 토큰 누출(<|channel|> 등)로 손상된 출력인지 감지한다.
    감지되면 상위 호출부에서 이 출력을 폐기하고 폴백으로 대체해야 한다."""
    if not text:
        return False
    # 동일한 짧은 토큰(단어)이 연속으로 repeat_threshold회 이상 반복되는 패턴
    if re.search(r"(\S{1,20})(?:\s+\1){" + str(repeat_threshold - 1) + r",}", text):
        return True
    # 공백/개행을 포함한 임의의 짧은 구(phrase)가 연속으로 여러 번 반복되는 패턴
    # 예: "(approx. 0.7374)\n(approx. 0.7374)\n..." 처럼 단어 경계로는 안 잡히는 반복.
    # 단, "━━━━━━━━━" 같은 순수 기호 구분선은 정상 서식(이메일/보고서 템플릿에서 사용)이므로
    # 실제 문자/숫자(영문·한글·숫자)를 포함한 구간이 반복될 때만 손상으로 판단한다.
    for _m in re.finditer(r"(.{4,60}?)\1{3,}", text, re.DOTALL):
        if re.search(r"[0-9A-Za-z가-힣]", _m.group(1)):
            return True
    # 챗 템플릿 특수 토큰 누출 (예: gpt-oss/harmony 계열의 <|channel|>, <|message|> 등)
    if re.search(r"<\|(channel|message|start|end|return|call)\b", text):
        return True
    return False


def _trim_before_header(text: str) -> str:
    """【📋AI 분석 보고서】 헤더가 있으면 그 앞의 쓰레기 텍스트를 제거한다.
    헤더가 없으면 원문 그대로 반환. 빈 문자열을 반환하지 않음.
    헤더가 여러 번 반복 생성된 경우(런어웨이 생성) 첫 번째 블록만 남긴다."""
    if not text:
        return text
    m = re.search(r"【📋?AI\s*분석\s*보고서】", text)
    if m:
        text = text[m.start():].strip()
    return _trim_repeats(text, r"【📋?AI\s*분석\s*보고서】")

# ── 프롬프트 모듈 임포트 ────────────────────────────────
try:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from prompts.analysis_prompt import get_prompts, FRAUD_TYPE_NAMES
    _PROMPT_MODULE_OK = True
    log.info("프롬프트 모듈 로드 완료")
except (ImportError, SyntaxError, Exception) as e:
    _PROMPT_MODULE_OK = False
    log.warning(f"프롬프트 모듈 사용 불가 → 기본 프롬프트 사용: {e}")

# ── i18n (✨ v9.3 폴백 템플릿 다국어화) ────────────────────
#   없거나 실패하면 _I18N_OK=False → 모든 폴백은 한국어(기존 동작) 유지 = 모듈 독립성 보존
try:
    from i18n_data import (make_t as _make_t, llm_lang_directive as _lang_directive,
                           FRAUD_TYPE_DETAILS_I18N as _FTD_I18N)
    _I18N_OK = True
except Exception as _e:
    _I18N_OK = False
    _FTD_I18N = {}
    def _lang_directive(lang):   # 프롬프트 언어 지시문 (i18n 없어도 동작)
        _n = {"en": "English", "ja": "日本語 (Japanese)", "zh": "简体中文 (Simplified Chinese)"}.get(lang)
        return f"\n\n(Please write your entire response in {_n}.)" if _n else ""
    log.warning(f"i18n_data 사용 불가 → 폴백 템플릿은 한국어로 출력: {_e}")

def _loc_name(fraud_type, lang, default):
    """유형명 현지화 — i18n 있으면 언어별 name, 없으면 default(한국어)."""
    try:
        if _I18N_OK and lang in _FTD_I18N and fraud_type in _FTD_I18N[lang]:
            return _FTD_I18N[lang][fraud_type]['name']
    except Exception:
        pass
    return default

# ── 기본 URL ─────────────────────────────────────────────
# ⚠️ /completion(raw)이 아닌 /v1/chat/completions를 사용해야 --jinja로 등록된
# Gemma 4 전용 채팅 템플릿(턴/채널 경계)이 실제로 적용됩니다.
LLAMA_CPP_URL_DEFAULT = "http://localhost:8080/v1/chat/completions"
OPENAI_URL_DEFAULT    = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_URL_DEFAULT  = "https://api.deepseek.com/v1/chat/completions"
MOONSHOT_URL_DEFAULT  = "https://api.moonshot.cn/v1/chat/completions"

# ── 사기 유형명 (프롬프트 모듈 미설치 시 폴백) ──────────
_FRAUD_TYPE_NAMES_FALLBACK = {
    'a':'원격제어 사기','b':'단말 탈취 사기','c':'명의 도용 사기',
    'd':'대출 빙자 사기','e':'ATM 사기','f':'피싱 사기',
    'g':'스미싱 사기','h':'계좌 이상 사기','i':'다중 시도 사기',
    'j':'수취 정지 사기','k':'오픈뱅킹 사기','l':'기타 사기','m':'정상 거래',
}

# ══════════════════════════════════════════════════════════
# 🖊 v13: 대시보드 "프롬프트 편집" 기능용 — 기본 템플릿(단일 진실 공급원)
#   이 모듈이 prompts/analysis_prompt.py(get_prompts) 없이 단독 동작할 때 쓰는
#   폴백 프롬프트와, 대시보드 프롬프트 편집기의 "기본값/초기화" 내용이 이 상수를
#   함께 참조한다 — 같은 문구가 두 곳에 따로 존재하며 드리프트하는 것을 방지.
#   .format(**vars)로 채워지며, {중괄호} 안 이름이 플레이스홀더다.
# ══════════════════════════════════════════════════════════
PROMPT_VARS_HELP = (
    "사용 가능한 자리표시자 — "
    "{fraud_type} 예측유형코드 · {type_name} 유형명 · {risk_score} 위험점수 · "
    "{amount} 거래금액 · {channel} 채널 · {os_name} OS · {distance} 거리(km) · "
    "{balance} 잔액 · {flags_str} 활성플래그 · {rule_block} ✨규칙대조결과(충족지표+실제값) · {rag} 참고문서 · {tx_id} 거래ID · "
    "{datetime} 거래일시 · {analysis} 직전 단계 분석 리포트 전문(Slack/Email 전용) · "
    "{analysis_head} 분석 리포트 앞부분 400자(Slack 기본값에서 사용)"
)

_FLAG_LABEL_MAP = {
    'Customer_rooting_jailbreak_indicator': '루팅/탈옥',
    'Customer_VPN_Indicator': 'VPN',
    'Unused_terminal_status': '미사용단말',
    'Unused_account_status': '미사용계좌',
    'Recipient_account_suspend_status': '수취계좌정지',
    'Transaction_Failure_Status': '거래실패',
    'Another_Person_Account': '타인계좌',
    'Flag_deposit_more_than_tenMillion': '1천만원↑입금',
}

def _compute_flags_str(row: dict) -> str:
    """활성화된 위험 플래그를 한글 라벨 콤마 목록으로. 기본 분석 프롬프트와
    오버라이드 프롬프트의 {flags_str} 자리표시자가 이 함수 하나를 공유한다."""
    flags = [label for col, label in _FLAG_LABEL_MAP.items()
             if str(row.get(col, '0')) in ('1', '1.0', 'True')]
    return ', '.join(flags) if flags else '없음'

DEFAULT_ANALYSIS_PROMPT_TEMPLATE = (
    "당신은 전자금융 FDS 전문 분석 AI입니다.\n"
    "거래 금액: {amount}원 / 잔액: {balance}원\n"
    "채널: {channel} / OS: {os_name} / 거래 거리: {distance}km\n"
    "활성 플래그: {flags_str}\n"
    "예측: {fraud_type}형 / 위험 점수: {risk_score}\n"
    "[규칙 대조 결과 — 각 지표의 충족 여부와 실제 값]\n{rule_block}\n\n"
    "참고문서:\n{rag}\n\n"
    "다음 정보들을 이용하여 분석하고, 아래 양식에 따라 적절한 문단 부호와 줄바꿈을 사용하여 예시와 같이 거래의 이상 판정 이유와 권장 조치를 담은 【📋AI 분석 보고서】를 한장만 작성하세요. (반복해서 작성하지 마시오)\n"
    "【📋AI 분석 보고서】부터 출력해서 시작하는 분석 보고서 생성)\n"
    "---\n"
    "# 양식(하단의 양식을 꼭 반드시 지키시오)\n"
    "【📋AI 분석 보고서】\n\n"
    "【판정 근거】 위 [규칙 대조 결과]에서 **✅충족으로 표시된 항목만** 근거로 인용하고, "
    "각 항목의 실제 값(예: Distance=338km)을 그대로 적으십시오. ⬜미충족·❔확인불가 항목을 "
    "근거처럼 서술하거나, 표시되지 않은 사실을 추가하지 마십시오. 3문장 (각각 줄바꿈)\n"
    "【이상 패턴 요약】 불릿 3개 (각각 줄바꿈)\n"
    "【권장 조치】 즉시/단기/장기 각 1문장 (각각 줄바꿈)"
    "---\n"
    "# 출력 예시(하단의 예시보다 더욱 상세하고 풍부하고 깊이 있게 모든 내용을 *한국어*로 작성, 절대 해당 숫자들에 매몰되지 마시오)\n"
    "【📋AI 분석 보고서】\n\n"
    "【판정 근거】\n\n"
    " 위험 점수 0.9309로 M형 사기 패턴이 탐지되었습니다.\n"
    " 거래 금액 70000원, 채널 ATM, 거래 거리 253.53km 등 주요 지표가 해당 사기 유형의 특성과 일치합니다.\n"
    " 이는 정상적인 금융 활동 범위를 벗어난 자산 세탁 및 명의 도용 의심 사례로 판단됩니다.\n"
    "【이상 패턴 요약】\n\n"
    " High-Risk Combination: 1천만 원 이상의 고액 이체와 계좌 정지 관련 플래그가 결합된 극위험 유형(H형) 탐지\n"
    " Identity Mismatch: 미사용 단말기 및 타인 명의 계좌 활용을 통한 신원 도용 의심 패턴 발생\n"
    " Geographic Anomaly: 정상적인 이용 환경과 동떨어진 223km 이상의 물리적 거리 이격 발생\n"
    "【권장 조치】\n\n"
    " 즉시: 해당 거래를 즉각 차단(Hold)하고, 시스템에 의한 자동 지급 정지 및 실시간 모니터링 대기 상태로 전환하십시오.\n"
    " 단기: 고객 본인 확인을 위한 화상 통화 또는 유선 인증을 실시하여 명의 도용 여부를 철저히 검증해야 합니다.\n"
    " 장기: 미사용 단말/계좌 기반의 고액 이체 패턴에 대한 탐지 로직 가중치를 상향하고, 해당 유형(H형)의 블랙리스트 데이터베이스를 업데이트하십시오."
)

DEFAULT_SLACK_PROMPT_TEMPLATE = (
    "아래 FDS 분석 결과를 Slack 알림 2줄로 요약해주세요. "
    "첫 줄: 위험 레벨 이모지 + 유형 + 거래 요약, "
    "둘째 줄: 위험점수 + 조치 필요:\n\n{analysis_head}"
)

DEFAULT_EMAIL_PROMPT_TEMPLATE = (
    "아래 FDS 탐지 결과를 담당자에게 보낼 공식 이메일로 작성하세요.\n"
    "마크다운 기호(**, ##, -, *, ```, > 등)는 절대 사용하지 마세요. 순수 텍스트만 출력하세요.\n"
    "아래 형식을 한 글자도 벗어나지 말고 그대로 따르세요 (구분선과 필드명 그대로 유지):\n\n"
    "제목: [FDS 긴급] {fraud_type}형 이상거래 탐지 (거래ID: {tx_id})\n\n"
    "담당자 귀중,\n\n"
    "FDS 시스템에서 이상거래를 탐지하였습니다.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "■ 탐지 개요\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "  사기 유형  : {fraud_type}형\n"
    "  위험 점수  : {risk_score}\n"
    "  거래 ID   : {tx_id}\n"
    "  거래 금액  : {amount}원\n"
    "  거래 채널  : {channel}\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "■ AI 분석 결과\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "(아래 AI 분석 결과를 자연스럽게 다듬어 이 자리에 넣으세요)\n"
    "{analysis}\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "■ 권장 조치\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "(즉시/단기/장기 조치를 각 1문장으로 작성)\n\n"
    "본 메일은 FDS 자동화 시스템에 의해 발송되었습니다.\n"
    "FDS QA 자동화 시스템 드림"
)


class LLMAnalyzer:
    """
    대시보드에서 오버라이드 가능한 3단계 LLM 분석기.

    Parameters
    ----------
    max_tokens : int
    llama_cpp_url : str | None  — None이면 .env → 기본값
    provider : str              — 'local'|'anthropic'|'openai'|'deepseek'|'moonshot'
    api_key : str | None        — None이면 .env에서 해당 프로바이더 키를 읽음
    """

    def __init__(
        self,
        max_tokens: int = 1024,
        llama_cpp_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        custom_url: str | None = None,
        custom_model: str | None = None,
        cloud_fallback: bool = True,
        prompt_overrides: dict | None = None,
    ):
        # 🛡 FIX(v9): cloud_fallback=False면 local 실패 시 Anthropic 자동 폴백 금지
        #   대시보드가 '로컬=마스킹 생략' 상태일 때 미마스킹 데이터의 외부 전송 차단용
        self.cloud_fallback = bool(cloud_fallback)
        self.max_tokens    = max_tokens
        self.llama_cpp_url = llama_cpp_url or os.getenv("LLAMA_CPP_URL", LLAMA_CPP_URL_DEFAULT)
        # 대시보드 사이드바 '모델 이름' 오버라이드 — 값이 있으면 모든 제공자
        #   (local/anthropic/openai/deepseek/moonshot/custom)의 기본 모델보다 우선한다.
        #   비어 있으면 None → 각 제공자별 기존 기본값·환경변수 동작을 그대로 보존.
        self.model_override = (model or "").strip() or None
        self.provider      = provider or os.getenv("USE_LLM_PROVIDER", "local")
        self.api_key       = api_key
        # 🌐 커스텀(OpenAI 호환) 엔드포인트 — OpenRouter·Together·Groq·vLLM·LM Studio 등
        self.custom_url    = custom_url
        self.custom_model  = custom_model
        # 🖊 v13: 대시보드 "프롬프트 편집" — {'analysis':..,'slack':..,'email':..} 중 값이 있는
        #   슬롯만 get_prompts()/기본 폴백 대신 사용(.format(**vars)). 형식 오류 시 안전하게
        #   기존 프롬프트로 자동 복귀(아래 _apply_prompt_override 참고) — 파이프라인은 절대 안 죽는다.
        self.prompt_overrides = {k: v for k, v in (prompt_overrides or {}).items() if (v or "").strip()}
        self._errors: list[str] = []
        self._fallback_count: int = 0
        log.info(f"LLM 제공자: {self.provider}")

    def _apply_prompt_override(self, slot: str, default_prompt: str, fmt_vars: dict) -> str:
        """대시보드가 slot(analysis/slack/email)에 커스텀 템플릿을 저장해뒀으면 그걸로 교체.
        .format(**fmt_vars) 실패(오타 자리표시자 등) 시 오류를 self._errors에 남기고
        default_prompt로 안전하게 되돌아간다 — 실무자가 편집하다 실수해도 탐지가 멈추지 않는다."""
        _tpl = self.prompt_overrides.get(slot)
        if not _tpl:
            return default_prompt
        try:
            return _tpl.format(**fmt_vars)
        except Exception as e:
            log.warning(f"커스텀 {slot} 프롬프트 형식 오류 → 기본 프롬프트로 대체: {e}")
            self._errors.append(f"[프롬프트 편집] {slot} 커스텀 템플릿 오류로 기본값 사용 — {e}")
            return default_prompt

    # ══════════════════════════════════════════════════════
    # 메인 분석 — 3단계 분리 호출
    # ══════════════════════════════════════════════════════
    def analyze(
        self,
        row: dict,
        fraud_type: str,
        risk_score: float,
        rag_context,
        lang: str = "ko",
    ) -> dict:
        """
        Returns dict: {"analysis", "slack", "email", "ctx"}

        lang : UI 언어('ko'|'en'|'ja'|'zh'). ko가 아니면 세 프롬프트 모두에
               '해당 언어로 응답하라'는 지시문을 붙이고, 폴백 템플릿도 해당 언어로 출력.
        """
        _dir = _lang_directive(lang)   # ✨ v9.3: 비-한국어면 LLM 출력 언어 전환 지시문
        # 🐛 FIX(v13): errors.clear()가 원래 "1호출" 직전(프롬프트 생성 다음)에 있어서,
        #   이번에 추가한 프롬프트 오버라이드 형식오류(_apply_prompt_override)가 여기서
        #   지워지고 있었다. 프롬프트 생성보다 먼저(맨 앞으로) 옮겨 오류가 살아남게 한다.
        self._errors.clear()
        # rag_context 정규화
        if isinstance(rag_context, str):
            rag_context = [rag_context] if rag_context else []
        elif rag_context is None:
            rag_context = []

        # 유형명
        if _PROMPT_MODULE_OK:
            type_names = FRAUD_TYPE_NAMES
        else:
            type_names = _FRAUD_TYPE_NAMES_FALLBACK
        type_name = type_names.get(fraud_type, f'유형 {fraud_type.upper()}')

        # 🖊 v13: 오버라이드 템플릿(.format())용 공통 자리표시자 — 3단계 전부에서 공유(단일 진실 공급원).
        #   PROMPT_VARS_HELP에 문서화된 이름과 정확히 일치해야 한다.
        _fmt_vars = {
            'amount': row.get('Transaction_Amount', 'N/A'),
            'channel': row.get('Channel', 'N/A'),
            'os_name': row.get('Operating_System', 'N/A'),
            'distance': row.get('Distance', 'N/A'),
            'balance': row.get('Account_balance', 'N/A'),
            'flags_str': _compute_flags_str(row),
            'fraud_type': fraud_type.upper(),
            'type_name': type_name,
            'risk_score': f"{risk_score:.4f}",
            'tx_id': row.get('ID', row.get('transaction_id', 'N/A')),
            'datetime': row.get('Transaction_Datetime', 'N/A'),
            'rag': '\n'.join(f'- {d}' for d in rag_context),
            'analysis': '',        # 분석 리포트 생성 전 — 1단계에서는 의미 없음(비어있음)
            'analysis_head': '',
        }

        # ── 프롬프트 생성 ──────────────────────────────
        _use_module = False
        if _PROMPT_MODULE_OK:
            try:
                prompts = get_prompts(row, fraud_type, risk_score, rag_context)
                p_analysis = prompts['analysis']
                ctx        = prompts.get('ctx', {})
                _use_module = True
            except Exception as e:
                log.warning(f"get_prompts 실패 → 폴백 프롬프트 사용: {e}")
        if not _use_module:
            ctx        = {}
            p_analysis = self._build_fallback_analysis_prompt(
                row, fraud_type, risk_score, rag_context
            )
        # 🖊 v13: 대시보드 커스텀 분석 프롬프트가 저장돼 있으면 module/폴백보다 우선 사용
        p_analysis = self._apply_prompt_override('analysis', p_analysis, _fmt_vars)

        # ── 1호출: 분석 리포트 (가장 중요, 넉넉하게) ───
        log.info("  [LLM 1/3] 분석 리포트 생성 중...")
        _fallback_fields = []
        _step_errors = {}

        analysis = self._call(p_analysis + _dir, max_tokens=1536, timeout=180)
        analysis = _trim_before_header(analysis)  # 헤더 앞 쓰레기 제거 + 반복 블록 절단
        if analysis and _is_degenerate(analysis):
            log.warning("분석 리포트가 반복 루프/특수토큰 손상으로 감지되어 폴백으로 대체")
            self._errors.append("[품질] 분석 리포트 출력이 반복 루프/특수토큰 손상으로 감지되어 폴백 처리")
            analysis = None
        _step_errors["analysis"] = list(self._errors)
        if not analysis:
            _fallback_fields.append("analysis")
            analysis = self._build_fallback_analysis(
                fraud_type, type_name, risk_score, row, lang
            )

        # ── 2호출: Slack 포맷 ──────────────────────────
        log.info("  [LLM 2/3] Slack 메시지 포맷 중...")
        _fmt_vars['analysis'] = analysis
        _fmt_vars['analysis_head'] = analysis[:400]
        if _use_module:
            try:
                prompts2 = get_prompts(row, fraud_type, risk_score, rag_context, analysis)
                p_slack  = prompts2['slack']
            except Exception as e:
                log.warning(f"get_prompts(slack/email) 실패 → 폴백 프롬프트 사용: {e}")
                _use_module = False  # 이후 이메일 단계도 일관되게 폴백으로 전환
                p_slack = DEFAULT_SLACK_PROMPT_TEMPLATE.format(**_fmt_vars)
        else:
            p_slack = DEFAULT_SLACK_PROMPT_TEMPLATE.format(**_fmt_vars)
        # 🖊 v13: 대시보드 커스텀 Slack 프롬프트가 저장돼 있으면 module/폴백보다 우선 사용
        p_slack = self._apply_prompt_override('slack', p_slack, _fmt_vars)
        slack = self._call(p_slack + _dir, max_tokens=200, timeout=45)
        if slack and _is_degenerate(slack):
            log.warning("Slack 요약이 반복 루프/특수토큰 손상으로 감지되어 폴백으로 대체")
            self._errors.append("[품질] Slack 출력이 반복 루프/특수토큰 손상으로 감지되어 폴백 처리")
            slack = None
        _step_errors["slack"] = list(self._errors)[len(_step_errors.get("analysis", [])):]
        if not slack:
            _fallback_fields.append("slack")
            slack = self._build_fallback_slack(fraud_type, risk_score, row, ctx, lang)

        # ── 3호출: 이메일 본문 ─────────────────────────
        log.info("  [LLM 3/3] 이메일 본문 포맷 중...")
        # (v10) _amount/_channel/_tx_id 죽은 변수 제거 — 이메일 단계는 _fmt_vars로 통합됨
        if _use_module:
            try:
                p_email = prompts2['email']
            except Exception as e:
                log.warning(f"prompts2['email'] 조회 실패 → 폴백 프롬프트 사용: {e}")
                _use_module = False
        if not _use_module:
            p_email = DEFAULT_EMAIL_PROMPT_TEMPLATE.format(**_fmt_vars)
        # 🖊 v13: 대시보드 커스텀 Email 프롬프트가 저장돼 있으면 module/폴백보다 우선 사용
        p_email = self._apply_prompt_override('email', p_email, _fmt_vars)
        _pre_email_cnt = len(self._errors)
        email = self._call(p_email + _dir, max_tokens=1536, timeout=180)
        email = _trim_repeats(email, r"\[FDS")  # 이메일 본문 반복 생성 방지 (✨ v9.3: 언어 무관 앵커)
        if email and _is_degenerate(email):
            log.warning("이메일 본문이 반복 루프/특수토큰 손상으로 감지되어 폴백으로 대체")
            self._errors.append("[품질] 이메일 출력이 반복 루프/특수토큰 손상으로 감지되어 폴백 처리")
            email = None
        _step_errors["email"] = list(self._errors)[_pre_email_cnt:]
        if not email:
            _fallback_fields.append("email")
            email = self._build_fallback_email(fraud_type, risk_score, row, analysis, ctx, lang)

        self._fallback_count += len(_fallback_fields)
        return {
            "analysis": analysis,
            "slack":    slack,
            "email":    email,
            "ctx":      ctx,
            "_diag": {
                "fallback_fields": _fallback_fields,
                "is_all_fallback": len(_fallback_fields) == 3,
                "errors": list(self._errors),
                "step_errors": _step_errors,
                "provider": self.provider,
            },
        }

    # ══════════════════════════════════════════════════════
    # 제공자 라우터 (대시보드 오버라이드 반영)
    # ══════════════════════════════════════════════════════
    def _call(self, prompt: str, max_tokens: int | None = None,
              timeout: int | None = None) -> str | None:
        _mt = max_tokens or self.max_tokens
        _to = timeout or 60
        if self.provider == "fallback":
            return None
        if self.provider == "local":
            result = self._call_llama_cpp(prompt, _mt, _to)
            if result:
                return result
            if not self.cloud_fallback:
                # 🛡 FIX(v9): 마스킹 생략(로컬 전제) 데이터가 클라우드로 새는 경로 차단
                self._errors.append("llama.cpp 실패 — 클라우드 폴백 비활성(PII 보호: 미마스킹 데이터 외부 전송 차단)")
                log.warning("llama.cpp 실패 — cloud_fallback=False → Anthropic 폴백 건너뜀")
                return None
            self._errors.append("llama.cpp 실패 → Anthropic 시도")
            log.warning("llama.cpp 실패 → Anthropic fallback")
            return self._call_anthropic(prompt, _mt)
        if self.provider == "anthropic":
            return self._call_anthropic(prompt, _mt)
        if self.provider in ("openai", "deepseek", "moonshot", "custom"):
            return self._call_openai_compat(prompt, _mt, _to)
        log.error(f"알 수 없는 LLM 제공자: {self.provider}")
        return None

    def test_connection(self) -> dict:
        self._errors.clear()
        result = self._call("Hi", max_tokens=32, timeout=12)  # 🐛 FIX(v5): thinking 계열 로컬 모델이 4토큰 내 빈 content 반환 → 정상 연결도 실패로 오탐
        if result:
            return {"ok": True, "provider": self.provider,
                    "message": f"연결 성공 ✅ — 응답: {result[:60]}", "errors": []}
        return {"ok": False, "provider": self.provider,
                "message": "연결 실패 ❌", "errors": list(self._errors)}

    # ── llama.cpp ──────────────────────────────────────
    # ⚠️ 중요: Gemma 4(26B-A4B)는 구형 Gemma(1~3)의 <start_of_turn>/<end_of_turn>가
    #    아니라 <|turn>role\n ... <turn|> 형식의 새 턴 포맷과, thinking mode용
    #    <|channel>thought\n ... <channel|> 델리미터를 씁니다.
    #    이 템플릿은 llama.cpp 서버가 --jinja 옵션으로 자동 적용하는데,
    #    단 "/v1/chat/completions" (messages 배열) 엔드포인트에만 적용되고
    #    "/completion" (raw prompt 문자열) 엔드포인트는 이를 완전히 우회합니다.
    #    즉 이전 코드가 /completion에 가공한 prompt 문자열을 그대로 보내던 방식은
    #    모델이 한 번도 학습한 적 없는 "포맷 없는 텍스트"를 준 것과 같아서,
    #    턴 경계를 못 찾고(3연속 생성) thinking 채널이 그대로 새는(<|channel|> 노출)
    #    근본 원인이었습니다. → /v1/chat/completions로 전환.
    def _call_llama_cpp(self, prompt: str, max_tokens: int = 1024,
                         timeout: int = 60) -> str | None:
        try:
            _body = {
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  max_tokens,
                # Gemma 4 thinking mode를 꺼서 분석 채널 내용이 content로
                # 새는 것을 최대한 방지 (서버/빌드에 따라 무시될 수 있음 —
                # llama.cpp의 Gemma4 thinking-off 지원은 아직 안정화 중인
                # 이슈로 확인됨. 안 먹히면 서버 실행 시 --reasoning off 또는
                # --reasoning-budget 0 플래그를 추가로 시도해보세요).
                "chat_template_kwargs": {"enable_thinking": False},
                # 위 옵션이 서버에서 무시되는 경우를 대비한 2차 방어선.
                # (정확한 토큰 철자는 문서 확인 기준이며 빌드에 따라 다를 수 있음)
                "stop": ["<turn|>", "<channel|>", "<|turn>", "<|channel>"],
            }
            # 모델 이름이 지정되면 요청 본문에 포함(다중 모델을 로드한 서버·게이트웨이용).
            # 비어 있으면 필드를 생략해 단일 모델 서버의 기존 동작을 그대로 보존한다.
            if self.model_override:
                _body["model"] = self.model_override
            resp = requests.post(
                self.llama_cpp_url,
                headers={
                    # 팀 공유 ngrok 터널 사용 시 방어적으로 추가(공식 문서상 프로그램적
                    # 요청엔 영향 없다고 하나, 무해하므로 안전하게 포함)
                    "ngrok-skip-browser-warning": "true",
                },
                json=_body,
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message", choice)  # 구버전 호환: message 없으면 choice 자체 사용
                content = (msg.get("content") or "").strip()
                reasoning = (msg.get("reasoning_content") or "").strip()
                if reasoning:
                    log.debug(f"[llama.cpp] thinking 채널 {len(reasoning)}자 수신 → 폐기(사용 안 함)")
                if content:
                    return content
                self._errors.append("[llama.cpp] 200 OK이나 응답 본문이 비어 있음")
                return None
            self._errors.append(f"[llama.cpp] HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.exceptions.ConnectionError:
            self._errors.append(f"[llama.cpp] 연결 실패 ({self.llama_cpp_url})")
            log.warning("llama.cpp 서버 미실행")
        except requests.exceptions.Timeout:
            self._errors.append(f"[llama.cpp] 타임아웃 ({timeout}초)")
            log.warning(f"llama.cpp 타임아웃 ({timeout}초)")
        except Exception as e:
            self._errors.append(f"[llama.cpp] {type(e).__name__}: {e}")
            log.error(f"llama.cpp 오류: {e}")
        return None

    # ── Anthropic ──────────────────────────────────────
    def _call_anthropic(self, prompt: str, max_tokens: int = 1024) -> str | None:
        key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            self._errors.append("ANTHROPIC_API_KEY 미설정")
            return None
        try:
            import anthropic
            # 🐛 FIX: 타임아웃 추가 (기본은 매우 김 → UI가 오래 멈출 수 있음)
            client = anthropic.Anthropic(api_key=key, timeout=120.0)
            # 모델 오버라이드는 '명시적으로 anthropic을 고른 경우'에만 적용한다.
            #   provider=local에서 llama.cpp 실패로 넘어온 폴백 경로에서는 로컬 모델명이
            #   Anthropic에 그대로 넘어가 실패하는 것을 막기 위함(안전망 오염 방지).
            _anth_model = (self.model_override if self.provider == "anthropic" else None) \
                          or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
            message = client.messages.create(
                model      = _anth_model,
                max_tokens = max_tokens,
                messages   = [{"role": "user", "content": prompt}],
            )
            # 🐛 FIX: content[0]이 text 블록이 아닐 수 있음 → text 블록만 추출
            parts = [b.text for b in message.content if getattr(b, "type", "") == "text"]
            text = "\n".join(parts).strip()
            if text:
                return text
            self._errors.append("Anthropic 응답에 text 블록 없음")
            return None
        except UnicodeEncodeError as e:
            self._errors.append(
                f"Anthropic API 인코딩 오류: {e} — "
                f"해결: PYTHONIOENCODING=utf-8 설정 또는 pip install --upgrade anthropic httpx")
        except Exception as e:
            self._errors.append(f"Anthropic API 오류: {e}")
        return None

    # ── OpenAI 호환 (openai / deepseek / moonshot) ────
    def _call_openai_compat(self, prompt: str, max_tokens: int = 1024,
                             timeout: int = 60) -> str | None:
        PROVIDER_CFG = {
            "openai":   {"env_key": "OPENAI_API_KEY",   "url_env": "OPENAI_API_URL",   "url_default": OPENAI_URL_DEFAULT,   "model_env": "OPENAI_MODEL",   "model_default": "gpt-4o-mini"},
            "deepseek": {"env_key": "DEEPSEEK_API_KEY", "url_env": "DEEPSEEK_API_URL", "url_default": DEEPSEEK_URL_DEFAULT, "model_env": "DEEPSEEK_MODEL", "model_default": "deepseek-chat"},
            "moonshot": {"env_key": "MOONSHOT_API_KEY",  "url_env": "MOONSHOT_API_URL",  "url_default": MOONSHOT_URL_DEFAULT, "model_env": "MOONSHOT_MODEL", "model_default": "moonshot-v1-8k"},
            # 🌐 OpenAI 호환이면 무엇이든 (기본값: OpenRouter)
            "custom":   {"env_key": "CUSTOM_LLM_API_KEY", "url_env": "CUSTOM_LLM_URL", "url_default": "https://openrouter.ai/api/v1/chat/completions", "model_env": "CUSTOM_LLM_MODEL", "model_default": "openrouter/auto"},
        }
        cfg = PROVIDER_CFG.get(self.provider)
        if not cfg:
            return None

        key   = self.api_key or os.getenv(cfg["env_key"], "")
        url   = os.getenv(cfg["url_env"], cfg["url_default"])
        model = os.getenv(cfg["model_env"], cfg["model_default"])
        if self.provider == "custom":
            # 대시보드 입력 > .env > 기본값(OpenRouter)
            url   = self.custom_url or url
            model = self.custom_model or model
        # 사이드바 '모델 이름'(전 제공자 공통) 오버라이드가 있으면 최우선 적용
        if self.model_override:
            model = self.model_override

        if not key:
            # 🐛 FIX: self._errors에도 기록 — 대시보드 진단 패널에 사유 표시
            self._errors.append(f"{cfg['env_key']} 미설정")
            log.warning(f"{cfg['env_key']} 미설정")
            return None
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "max_tokens":  max_tokens,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                if content and content.strip():
                    return content.strip()
                self._errors.append(f"[{self.provider}] 200 OK이나 응답 본문이 비어 있음")
                return None
            self._errors.append(f"[{self.provider}] HTTP {resp.status_code}: {resp.text[:200]}")
            log.error(f"API 오류 {resp.status_code}: {resp.text[:200]}")
        except requests.exceptions.Timeout:
            self._errors.append(f"[{self.provider}] 타임아웃 ({timeout}초)")
            log.error(f"{self.provider} 타임아웃")
        except Exception as e:
            self._errors.append(f"[{self.provider}] {type(e).__name__}: {e}")
            log.error(f"{self.provider} API 호출 오류: {e}")
        return None

    # ══════════════════════════════════════════════════════
    # LLM 미연결 시 폴백 메시지
    # ══════════════════════════════════════════════════════
    def _build_fallback_analysis(self, fraud_type, type_name,
                                  risk_score, row, lang="ko") -> str:
        amount   = row.get('Transaction_Amount', 'N/A')
        channel  = row.get('Channel', 'N/A')
        distance = row.get('Distance', 'N/A')
        flags = [k for k in [
            'Customer_rooting_jailbreak_indicator','Customer_VPN_Indicator',
            'Unused_terminal_status','Another_Person_Account',
            'Account_release_suspention','Flag_deposit_more_than_tenMillion',
        ] if str(row.get(k, 0)) in ('1','1.0')]
        if _I18N_OK and lang != "ko":       # ✨ v9.3: 비-한국어 → i18n 템플릿
            _t = _make_t({'lang': lang})
            _flags = '\n'.join(f'• {f}' for f in flags) if flags else _t("fb.no_flags")
            return _t("fb.analysis_single", ft=fraud_type.upper(),
                      name=_loc_name(fraud_type, lang, type_name),
                      r=f"{risk_score:.4f}", amt=amount, ch=channel, dist=distance, flags=_flags)
        return (
            f"⚠️ {fraud_type.upper()}형 이상거래 탐지 — {type_name}\n\n"
            f"【판정 근거】\n"
            f"위험 점수 {risk_score:.4f}로 {fraud_type.upper()}형 사기 패턴이 탐지되었습니다. "
            f"거래 금액 {amount}원, 채널 {channel}, 거래 거리 {distance}km 등 "
            f"주요 지표가 해당 사기 유형의 특성과 일치합니다.\n\n"
            f"【이상 패턴 요약】\n"
            + ('\n'.join(f'• {f}' for f in flags) if flags else '• 위험 플래그 없음') + "\n\n"
            f"【권장 조치】\n"
            f"즉시: 거래 보류 후 담당자 수동 검토\n"
            f"단기: 고객 본인 확인 후 처리\n"
            f"장기: 해당 패턴 모니터링 강화"
        )

    def _build_fallback_slack(self, fraud_type, risk_score,
                               row, ctx, lang="ko") -> str:
        amount  = row.get('Transaction_Amount', 'N/A')
        channel = row.get('Channel', 'N/A')
        tx_id   = row.get('ID', row.get('transaction_id', 'N/A'))
        level   = "🔴 CRITICAL" if risk_score >= 0.9 else \
                  "🟠 HIGH" if risk_score >= 0.7 else "🟡 ELEVATED"
        if _I18N_OK and lang != "ko":       # ✨ v9.3
            return _make_t({'lang': lang})("fb.slack_single", level=level,
                      ft=fraud_type.upper(), id=tx_id, amt=amount, ch=channel, r=f"{risk_score:.4f}")
        return (
            f"{level} *{fraud_type.upper()}형 이상거래 탐지* | "
            f"거래ID: `{tx_id}` | 금액: `{amount}원` | 채널: `{channel}`\n"
            f"> 위험점수 {risk_score:.4f} — 즉시 확인 및 조치 필요"
        )

    def _build_fallback_email(self, fraud_type, risk_score,
                               row, analysis, ctx, lang="ko") -> str:
        tx_id    = row.get('ID', row.get('transaction_id', 'N/A'))
        amount   = row.get('Transaction_Amount', 'N/A')
        channel  = row.get('Channel', 'N/A')
        datetime = row.get('Transaction_Datetime', 'N/A')
        if _I18N_OK and lang != "ko":       # ✨ v9.3
            return _make_t({'lang': lang})("fb.email_single", ft=fraud_type.upper(),
                      id=tx_id, dt=datetime, amt=amount, ch=channel,
                      r=f"{risk_score:.4f}", analysis=analysis, line="━"*35)
        return (
            f"제목: [FDS 긴급] {fraud_type.upper()}형 이상거래 탐지 (거래ID: {tx_id})\n\n"
            f"담당자 귀중,\n\n"
            f"FDS 시스템에서 이상거래를 탐지하였습니다.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"■ 탐지 개요\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  사기 유형  : {fraud_type.upper()}형\n"
            f"  위험 점수  : {risk_score:.4f}\n"
            f"  거래 ID   : {tx_id}\n"
            f"  거래 일시  : {datetime}\n"
            f"  거래 금액  : {amount}원\n"
            f"  거래 채널  : {channel}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"■ AI 분석 결과\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{analysis}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"본 메일은 FDS 자동화 시스템에 의해 발송되었습니다.\n"
            f"FDS QA 자동화 시스템 드림"
        )

    @staticmethod
    def _rule_block(row, fraud_type, lang="ko") -> str:
        """✨ v16: 규칙 체크리스트 근거 블록.

        환각 방지의 핵심 — LLM이 "새벽 고액 이체가 관찰됩니다" 같은 문장을 지어내는 이유는
        근거로 쓸 **구체적 값**이 프롬프트에 없기 때문이다. 이 블록은 각 지표의
        충족/미충족과 **실제 값**(Distance=338km 등)을 함께 제공한다.
        모듈이 없거나 실패하면 빈 문자열 → 프롬프트는 기존대로 동작한다.
        """
        try:
            try:
                from pipeline.rule_checker import RuleChecker
            except ImportError:
                from rule_checker import RuleChecker
            return RuleChecker(lang).explain_text(row, fraud_type)
        except Exception as e:
            log.debug(f"규칙 블록 생성 생략: {e}")
            return ""

    def _build_fallback_analysis_prompt(self, row, fraud_type,
                                         risk_score, rag_context) -> str:
        """🖊 v13: DEFAULT_ANALYSIS_PROMPT_TEMPLATE(모듈 상단, 대시보드 편집기와 공유하는
        단일 진실 공급원)을 채워서 반환 — 문구 자체는 그 상수 하나에만 존재한다."""
        _vars = {
            'amount': row.get('Transaction_Amount', 'N/A'),
            'channel': row.get('Channel', 'N/A'),
            'os_name': row.get('Operating_System', 'N/A'),
            'distance': row.get('Distance', 'N/A'),
            'balance': row.get('Account_balance', 'N/A'),
            'flags_str': _compute_flags_str(row),
            'fraud_type': fraud_type.upper(),
            'risk_score': f"{risk_score:.4f}",
            'rag': '\n'.join(f'- {d}' for d in rag_context),
            'rule_block': self._rule_block(row, fraud_type, getattr(self, 'lang', 'ko')),
        }
        return DEFAULT_ANALYSIS_PROMPT_TEMPLATE.format(**_vars)

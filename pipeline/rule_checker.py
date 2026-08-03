"""
RuleChecker — 사기 유형별 규칙 체크리스트 (판정 근거 설명기)  ✨ v16 신규

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이 모듈은 "사기냐 정상이냐"를 판정하지 않는다. 그건 ML 모델의 일이다.
   이 모듈은 **"사기라고 할 때 어느 유형의 특징에 얼마나 맞는가"**만 답한다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

왜 이렇게 설계했나 (실측 근거, 120,000행 전수)
  팀 EDA가 찾아낸 유형별 특징은 **유형 간 구분**에는 유효하지만,
  **사기/정상 구분**에는 쓸 수 없다. 정상 거래가 전체의 99%(118,800행)이고,
  같은 특징을 정상 거래도 흔하게 갖기 때문이다.

    특징                     정상(m)에서    j형에서
    수취계좌 정지            49.2%          100%
    미사용 계좌              51.2%          100%
    고액입금 1천만↑          42.3%          32%
    미사용 단말              92.1%          95%

  그래서 "수취정지 AND 미사용계좌 → j형" 규칙은
    · 전체 모집단에서 : 29,864건 적중 · 정밀도 0.3%  ← 탐지용으로 쓰면 재앙
    · 사기 내부에서   :    304건 적중 · 정밀도 32.9% ← 유형 설명용으로는 유효
                                        (12지선다 무작위 8.3% 대비 4배)

  사기 내부 정밀도 실측 (무작위 기준선 8.3%)
    Distance>408 → a          66.7%    고액입금&Others&무흔적 → f   51.3%
    신용C/D/E&모바일 → b      48.7%    거래횟수>=2 → k              48.5%
    고액입금&ATM → e          43.9%    시간차>59만초 → h            50.0%
    수취정지&미사용계좌 → j   32.9%    금액>1.7억 → i               33.3%
    악성행위>=2 → c           27.0%    출생1955~65 → l              18.8%

용도
  ① 설명 가능성 — 모델이 "e형 0.87"이라 할 때, 그 근거를 사람 말로 제시
  ② 근거 일치도 — 모델 예측 유형의 특징을 이 거래가 몇 개 만족하는지
  ③ 검토 우선순위 — 모델과 규칙이 불일치하는 건이 수동 검토 대상
  ④ 라벨 없는 입력 — 세션5 직접입력·합성(random)은 정답이 없어 규칙이 유일한 대조축

핵심 API
  rc = RuleChecker()
  rc.check(row, predicted_type="e")   → 근거 리포트 dict
  rc.rank(row)                        → [(유형, 점수), ...] 특징 적합도 순위
  rc.explain_text(row, "e", lang)     → LLM 프롬프트/화면용 텍스트 블록
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

RULE_VERSION = "v16 (팀 EDA 검증판 · 120,000행 전수 대조)"

_MB = [f"Customer_flag_terminal_malicious_behavior_{i}" for i in range(1, 7)]
_AU = [f"Customer_flag_change_of_authentication_{i}" for i in range(1, 5)]

# 인코딩 코드 (Preprocessor와 동일 규약: sorted() 인덱스)
CH_ATM, CH_OTHERS, CH_INTERNET, CH_MOBILE = 0, 1, 2, 3
CR_C, CR_D, CR_E = 2, 3, 4          # 신용등급 A,B,C,D,E,S → 0..5
OS_WINDOWS = 3
ERR_C = 1                           # Error_Code a,c → 0,1  (c = 잔액부족)


# ── 값 접근 헬퍼 ─────────────────────────────────────────
def _f(row, key, default=None):
    """수치 추출. 없거나 변환 불가면 None (규칙은 '판정 보류'로 처리)."""
    v = row.get(key, None)
    if v is None:
        return default
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return default if v != v else v          # NaN → default


def _flag(row, key):
    v = _f(row, key)
    return None if v is None else (v == 1)


def _sum_flags(row, keys):
    vals = [_f(row, k) for k in keys]
    got = [v for v in vals if v is not None]
    return sum(got) if got else None


def _ch(row):
    """Channel — 코드(0~3) 또는 원문 문자열 모두 허용."""
    v = row.get("Channel", None)
    if v is None:
        return None
    if isinstance(v, str):
        m = {"atm": CH_ATM, "others": CH_OTHERS, "internet": CH_INTERNET, "mobile": CH_MOBILE}
        s = v.strip().lower()
        if s in m:
            return m[s]
        try:
            return int(float(s))
        except ValueError:
            return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════
# 유형별 시그니처
#   weight : 3=결정적(실측 정밀도 40%+) · 2=강함 · 1=보조
#   test   : row → True / False / None(판정 보류)
#   ev     : row → 근거 문자열 (실제 값을 보여준다 = 환각 방지)
# ══════════════════════════════════════════════════════════
def _ind(iid, weight, test, label, ev):
    return {"id": iid, "weight": weight, "test": test, "label": label, "ev": ev}


TYPE_SIGNATURES: dict[str, dict] = {
    "a": {
        "title": {"ko": "계정탈취 후 원거리 즉시 이체", "en": "Account takeover → immediate remote transfer"},
        "indicators": [
            # 실측: a형 100%가 273km 초과 · 타 사기유형은 11% → 리프트 8.8배 (주 지표)
            _ind("far", 3, lambda r: (lambda d: None if d is None else d > 273)(_f(r, "Distance")),
                 {"ko": "원거리 접속 (273km 초과 · a형 실측 100% · 타 유형 11% = 8.8배)",
                  "en": "Long-distance access (>273km; 100% of type a vs 11% others = 8.8×)"},
                 lambda r: f"Distance={_f(r,'Distance',0):,.0f}km (전체 중앙 156km)"),
            # 극단 구간은 정밀도 66.7%로 가장 확실 (리프트 19.6배)
            _ind("far_extreme", 2, lambda r: (lambda d: None if d is None else d > 408)(_f(r, "Distance")),
                 {"ko": "접속 거리 극단 (408km 초과 · 리프트 19.6배)",
                  "en": "Extreme distance (>408km, lift 19.6×)"},
                 lambda r: f"Distance={_f(r,'Distance',0):,.0f}km"),
            _ind("no_device_trace", 1,
                 lambda r: (lambda s: None if s is None else s == 0)(_sum_flags(r, _MB)),
                 {"ko": "단말 악성행위 흔적 없음 (외부 침입 정황)", "en": "No device-malware trace (external intrusion)"},
                 lambda r: f"악성행위 플래그 합={_sum_flags(r,_MB)}"),
        ],
    },
    "b": {
        "title": {"ko": "원격제어 앱 설치 후 저신용층 표적 계좌탈취",
                  "en": "Remote-control app → low-credit-segment account takeover"},
        "indicators": [
            _ind("credit_cde", 3,
                 lambda r: (lambda c: None if c is None else int(c) in (CR_C, CR_D, CR_E))(_f(r, "Customer_credit_rating")),
                 {"ko": "신용등급 C/D/E (b형은 실측 100% · A/B/S 0%)",
                  "en": "Credit rating C/D/E (100% of type b; A/B/S never)"},
                 lambda r: f"등급코드={_f(r,'Customer_credit_rating',-1):.0f} (0=A…5=S)"),
            _ind("mobile", 2, lambda r: (lambda c: None if c is None else c == CH_MOBILE)(_ch(r)),
                 {"ko": "모바일 채널 (b형 55% · 전체 24%)", "en": "Mobile channel (55% of type b vs 24% overall)"},
                 lambda r: f"Channel={_ch(r)}"),
            _ind("root", 3, lambda r: _flag(r, "Customer_rooting_jailbreak_indicator"),
                 {"ko": "루팅·탈옥 단말 (b형 51% · 전체 7% = 7배)",
                  "en": "Rooted/jailbroken device (51% of b vs 7% overall)"},
                 lambda r: "rooting=1"),
            _ind("vpn", 3, lambda r: _flag(r, "Customer_VPN_Indicator"),
                 {"ko": "VPN 사용 (b형 42% · 전체 7% = 6배)", "en": "VPN in use (42% of b vs 7% overall)"},
                 lambda r: "VPN=1"),
            _ind("low_limit", 1,
                 lambda r: (lambda v: None if v is None else v <= 1_000_000)(_f(r, "Account_amount_daily_limit")),
                 {"ko": "일일 이체한도 낮음 (100만원 이하 · b형 중앙값)",
                  "en": "Low daily limit (≤1M KRW, median of type b)"},
                 lambda r: f"일일한도={_f(r,'Account_amount_daily_limit',0):,.0f}원"),
            _ind("not_others", 1, lambda r: (lambda c: None if c is None else c != CH_OTHERS)(_ch(r)),
                 {"ko": "Others 채널 아님 (b형 실측 0%)", "en": "Not the Others channel (0% of type b)"},
                 lambda r: f"Channel={_ch(r)}"),
        ],
    },
    "c": {
        "title": {"ko": "악성앱 설치 → 키로깅/파밍 후 ATM 직접 출금",
                  "en": "Malicious app → keylogging/pharming → direct ATM withdrawal"},
        "indicators": [
            _ind("malware2", 3, lambda r: (lambda s: None if s is None else s >= 2)(_sum_flags(r, _MB)),
                 {"ko": "단말 악성행위 플래그 2개 이상 (c형 평균 1.74 · 전체 0.58 = 3배)",
                  "en": "≥2 device-malware flags (c avg 1.74 vs 0.58 overall)"},
                 lambda r: f"악성행위 합={_sum_flags(r,_MB)}"),
            _ind("malware1", 1, lambda r: (lambda s: None if s is None else s >= 1)(_sum_flags(r, _MB)),
                 {"ko": "단말 악성행위 플래그 존재", "en": "Any device-malware flag present"},
                 lambda r: f"악성행위 합={_sum_flags(r,_MB)}"),
            _ind("atm", 2, lambda r: (lambda c: None if c is None else c == CH_ATM)(_ch(r)),
                 {"ko": "ATM 채널 (c형 54% · 전체 24%)", "en": "ATM channel (54% of c vs 24% overall)"},
                 lambda r: f"Channel={_ch(r)}"),
            _ind("windows", 1,
                 lambda r: (lambda o: None if o is None else int(o) == OS_WINDOWS)(_f(r, "Operating_System")),
                 {"ko": "Windows 환경 (c형 45% · 전체 32%)", "en": "Windows (45% of c vs 32% overall)"},
                 lambda r: f"OS코드={_f(r,'Operating_System',-1):.0f}"),
            _ind("not_others", 1, lambda r: (lambda c: None if c is None else c != CH_OTHERS)(_ch(r)),
                 {"ko": "Others 채널 아님 (c형 실측 0%)", "en": "Not Others channel (0% of c)"},
                 lambda r: f"Channel={_ch(r)}"),
        ],
    },
    "d": {
        "title": {"ko": "신호 약한 미분류형 (추가 조사 필요)", "en": "Weak-signal, unresolved type (needs investigation)"},
        "indicators": [
            _ind("internet", 2, lambda r: (lambda c: None if c is None else c == CH_INTERNET)(_ch(r)),
                 {"ko": "인터넷뱅킹 채널 (d형 45% · 전체 24%)", "en": "Internet banking (45% of d vs 24%)"},
                 lambda r: f"Channel={_ch(r)}"),
            _ind("unused_terminal", 2, lambda r: _flag(r, "Unused_terminal_status"),
                 {"ko": "미사용 단말 접속 (d형 실측 100%)", "en": "Unused terminal (100% of type d)"},
                 lambda r: "미사용단말=1"),
            _ind("clean_device", 2,
                 lambda r: (lambda s, rt: None if (s is None or rt is None) else (s <= 1 and not rt))(
                     _sum_flags(r, _MB), _flag(r, "Customer_rooting_jailbreak_indicator")),
                 {"ko": "단말 위협 흔적 거의 없음 (악성 0.64 · 루팅 4%)",
                  "en": "Almost no device threat trace"},
                 lambda r: f"악성합={_sum_flags(r,_MB)} · 루팅={_f(r,'Customer_rooting_jailbreak_indicator',0):.0f}"),
            _ind("no_fail", 1, lambda r: (lambda v: None if v is None else v == 0)(_f(r, "Transaction_Failure_Status")),
                 {"ko": "거래 실패 없음 (d형 실측 0%)", "en": "No transaction failure (0% of d)"},
                 lambda r: "실패=0"),
        ],
    },
    "e": {
        "title": {"ko": "원격제어 단말감염 → 대량 입금 유입 후 ATM 전액 인출",
                  "en": "Remote-control infection → large inflow → full ATM withdrawal"},
        "indicators": [
            _ind("big_deposit", 3, lambda r: _flag(r, "Flag_deposit_more_than_tenMillion"),
                 {"ko": "1천만원 이상 입금 플래그 (e형 실측 100%)",
                  "en": "Deposit ≥10M KRW flag (100% of type e)"},
                 lambda r: "고액입금=1"),
            _ind("atm_only", 3, lambda r: (lambda c: None if c is None else c == CH_ATM)(_ch(r)),
                 {"ko": "ATM 채널 (e형 실측 100% · 모바일/iOS/Android 0%)",
                  "en": "ATM channel (100% of type e)"},
                 lambda r: f"Channel={_ch(r)}"),
            _ind("root", 2, lambda r: _flag(r, "Customer_rooting_jailbreak_indicator"),
                 {"ko": "루팅·원격제어 흔적 (e형 17% · 전체 7% = 2.4배)",
                  "en": "Rooting/remote-control trace (2.4× baseline)"},
                 lambda r: "rooting=1"),
            _ind("low_balance_after", 1,
                 lambda r: (lambda v: None if v is None else v >= 0.5)(_f(r, "Amount_vs_remaining_balance")),
                 {"ko": "거래 후 잔액을 크게 비움 (잔액 대비 50% 이상)",
                  "en": "Drains most of the balance (≥50% of balance)"},
                 lambda r: f"잔액대비={_f(r,'Amount_vs_remaining_balance',0):.2f}"),
        ],
    },
    "f": {
        "title": {"ko": "정상거래로 위장된 최종 인출단계 (자금세탁 의심)",
                  "en": "Final withdrawal disguised as normal (possible laundering)"},
        "indicators": [
            _ind("big_deposit", 3, lambda r: _flag(r, "Flag_deposit_more_than_tenMillion"),
                 {"ko": "1천만원 이상 입금 플래그 (f형 실측 100%)", "en": "Deposit ≥10M flag (100% of f)"},
                 lambda r: "고액입금=1"),
            _ind("others_only", 3, lambda r: (lambda c: None if c is None else c == CH_OTHERS)(_ch(r)),
                 {"ko": "Others(비표준) 채널 (f형 실측 100% · ATM/모바일 0%)",
                  "en": "Others channel (100% of type f)"},
                 lambda r: f"Channel={_ch(r)}"),
            _ind("no_trace", 3,
                 lambda r: (lambda s, rt: None if (s is None or rt is None) else (s == 0 and not rt))(
                     _sum_flags(r, _MB), _flag(r, "Customer_rooting_jailbreak_indicator")),
                 {"ko": "단말 위협 흔적 완전 없음 (f형 루팅 0% · 악성 0%) — 은밀한 채널의 징표",
                  "en": "Zero device-threat trace (0% rooting, 0% malware) — the tell of a covert channel"},
                 lambda r: f"루팅=0 · 악성합={_sum_flags(r,_MB)}"),
            _ind("drain", 2,
                 lambda r: (lambda v: None if v is None else v >= 0.5)(_f(r, "Amount_vs_remaining_balance")),
                 {"ko": "잔액을 가장 크게 비움 (f형 금액 z=0.83으로 사기 중 2위)",
                  "en": "Largest balance drain (amount z=0.83, 2nd among fraud)"},
                 lambda r: f"잔액대비={_f(r,'Amount_vs_remaining_balance',0):.2f}"),
        ],
    },
    "g": {
        "title": {"ko": "대량 입금 → 인출 중간 단계 (e·f 사이)",
                  "en": "Intermediate stage between large inflow and withdrawal (between e and f)"},
        "indicators": [
            _ind("big_deposit", 3, lambda r: _flag(r, "Flag_deposit_more_than_tenMillion"),
                 {"ko": "1천만원 이상 입금 플래그 (g형 실측 100%)", "en": "Deposit ≥10M flag (100% of g)"},
                 lambda r: "고액입금=1"),
            _ind("mixed_channel", 2,
                 lambda r: (lambda c: None if c is None else c not in (CH_ATM, CH_OTHERS))(_ch(r)),
                 {"ko": "ATM·Others 전용이 아님 (e·f와 갈리는 지점 — g형은 채널 혼합)",
                  "en": "Not ATM/Others-exclusive (this is what separates g from e and f)"},
                 lambda r: f"Channel={_ch(r)}"),
            _ind("low_recipient_hist", 2,
                 lambda r: (lambda v: None if v is None else v <= 0)(_f(r, "Transaction_history_with_the_account")),
                 {"ko": "수취계좌 거래이력 없음 (g형 z=-0.35)", "en": "No history with recipient account (z=-0.35)"},
                 lambda r: f"수취계좌 이력={_f(r,'Transaction_history_with_the_account',0):.0f}건"),
            _ind("unused_account", 1, lambda r: _flag(r, "Unused_account_status"),
                 {"ko": "미사용 계좌 (g형 63% · 전체 51%)", "en": "Dormant account (63% of g vs 51%)"},
                 lambda r: "미사용계좌=1"),
        ],
    },
    "h": {
        "title": {"ko": "장기 휴면 계좌 재개 시도 후 잔액 부족 반복 실패",
                  "en": "Dormant account reactivation → repeated insufficient-balance failures"},
        "indicators": [
            # 실측: h형 100%가 표준편차 10만원 미만 (타 유형 32%) → 주 지표
            _ind("flat_history", 3,
                 lambda r: (lambda v: None if v is None else v < 100_000)(_f(r, "Account_one_month_std_dev")),
                 {"ko": "거래금액 변동 거의 없음 (1개월 표준편차 10만원 미만 · h형 실측 100% · 타 유형 32%)",
                  "en": "Almost flat amount history (1-month σ <100K; 100% of h vs 32% others)"},
                 lambda r: f"1개월 표준편차={_f(r,'Account_one_month_std_dev',0):,.0f}원"),
            _ind("long_gap", 2,
                 lambda r: (lambda v: None if v is None else v > 594_555)(_f(r, "Time_difference_seconds")),
                 {"ko": "직전 거래와 시간차 극대 (약 7일 초과 · 리프트 11배)",
                  "en": "Huge gap since last transaction (>~7 days, lift 11×)"},
                 lambda r: f"시간차={_f(r,'Time_difference_seconds',0)/86400:.1f}일"),
            _ind("fail", 3, lambda r: _flag(r, "Transaction_Failure_Status"),
                 {"ko": "거래 실패 (h형 17% · 전 유형 최고 · 전체 2%)",
                  "en": "Transaction failed (17% of h — highest of all types vs 2% overall)"},
                 lambda r: "거래실패=1"),
            _ind("err_c", 3, lambda r: (lambda v: None if v is None else int(v) == ERR_C)(_f(r, "Error_Code")),
                 {"ko": "에러코드 c = 잔액 부족 (h형 17% · 전 유형 최고)",
                  "en": "Error code c = insufficient balance (17% of h, highest)"},
                 lambda r: f"Error_Code={_f(r,'Error_Code',-1):.0f} (1=c 잔액부족)"),
            # 실측: 500만원 미만이 h형 74% (타 유형 18%) → 리프트 4.1배
            _ind("small_account", 3,
                 lambda r: (lambda v: None if v is None else v < 5_000_000)(_f(r, "Account_one_month_max_amount")),
                 {"ko": "평소 소액 계좌 (1개월 최대이체 500만원 미만 · h형 74% · 타 유형 18%) — 이번 거래만 유별남",
                  "en": "Normally small-amount account (1-month max <5M; 74% of h vs 18%) — this transaction is the outlier"},
                 lambda r: f"1개월 최대={_f(r,'Account_one_month_max_amount',0):,.0f}원"),
        ],
    },
    "i": {
        "title": {"ko": "고액 이체형 (확신도 낮음)", "en": "Large-amount transfer (low confidence)"},
        "indicators": [
            # 실측: 금액>3천만 AND 1개월최대>5천만 → i형 43% · 타 유형 10% = 리프트 4.5배 (주 지표)
            _ind("high_value_account", 3,
                 lambda r: (lambda a, b: None if (a is None or b is None) else
                            (a > 30_000_000 and b > 50_000_000))(
                     _f(r, "Transaction_Amount_abs"), _f(r, "Account_one_month_max_amount")),
                 {"ko": "고액 거래 + 평소에도 고액 계좌 (금액 3천만↑ & 1개월최대 5천만↑ · i형 43% · 타 유형 10%)",
                  "en": "Large amount on a habitually high-value account (>30M & 1-month max >50M; 43% of i vs 10%)"},
                 lambda r: f"금액={_f(r,'Transaction_Amount_abs',0):,.0f}원 · "
                           f"1개월최대={_f(r,'Account_one_month_max_amount',0):,.0f}원"),
            _ind("big_amount", 2,
                 lambda r: (lambda v: None if v is None else v > 30_000_000)(_f(r, "Transaction_Amount_abs")),
                 {"ko": "거래금액 3천만원 초과 (i형 52% · 타 유형 14% = 3.8배 · z=1.97 사기 중 1위)",
                  "en": "Amount >30M KRW (52% of i vs 14% = 3.8×; z=1.97 highest among fraud)"},
                 lambda r: f"금액={_f(r,'Transaction_Amount_abs',0):,.0f}원"),
            _ind("huge_amount", 1,
                 lambda r: (lambda v: None if v is None else v > 170_381_800)(_f(r, "Transaction_Amount_abs")),
                 {"ko": "거래금액 극단 (1.7억 초과 · 리프트 5.5배)", "en": "Extreme amount (>170M, lift 5.5×)"},
                 lambda r: f"금액={_f(r,'Transaction_Amount_abs',0):,.0f}원"),
            _ind("auth_change", 2,
                 lambda r: (lambda s: None if s is None else s >= 4)(_sum_flags(r, _AU)),
                 {"ko": "인증수단 변경 이력 많음 (i형 합계 3.83 · 전 유형 최고)",
                  "en": "Many authentication changes (i sum 3.83, highest of all types)"},
                 lambda r: f"인증변경 합={_sum_flags(r,_AU)}"),
        ],
    },
    "j": {
        "title": {"ko": "대포통장 개설 초기 자금 유입 시도", "en": "Initial inflow into a freshly opened mule account"},
        "indicators": [
            _ind("recip_suspend", 3, lambda r: _flag(r, "Recipient_account_suspend_status"),
                 {"ko": "수취계좌 거래중지 이력 (j형 실측 100%)",
                  "en": "Recipient account suspended (100% of type j)"},
                 lambda r: "수취계좌정지=1"),
            _ind("unused_account", 3, lambda r: _flag(r, "Unused_account_status"),
                 {"ko": "미사용(휴면) 계좌 (j형 실측 100%) — 위 항목과 동시 충족이 j형의 지문",
                  "en": "Dormant account (100% of j) — the pair with the item above is j's fingerprint"},
                 lambda r: "미사용계좌=1"),
            _ind("no_recip_hist", 3,
                 lambda r: (lambda a, b: None if (a is None and b is None) else
                            ((a or 0) <= 0 and (b or 0) <= 0))(
                     _f(r, "Number_of_transaction_with_the_account"),
                     _f(r, "Transaction_history_with_the_account")),
                 {"ko": "수취계좌와 거래 이력 전무 (j형 z=-0.72 최저) — 첫 송금",
                  "en": "Zero history with recipient (z=-0.72, lowest) — a first-ever transfer"},
                 lambda r: f"거래횟수={_f(r,'Number_of_transaction_with_the_account',0):.0f} · "
                           f"이력={_f(r,'Transaction_history_with_the_account',0):.0f}"),
            _ind("fail_or_err", 1,
                 lambda r: (lambda fs, ec: None if (fs is None and ec is None) else
                            (bool(fs) or int(ec or 0) == ERR_C))(
                     _f(r, "Transaction_Failure_Status"), _f(r, "Error_Code")),
                 {"ko": "거래 실패 또는 잔액부족(에러 c)", "en": "Transaction failure or insufficient-balance error"},
                 lambda r: f"실패={_f(r,'Transaction_Failure_Status',0):.0f} · Error={_f(r,'Error_Code',-1):.0f}"),
        ],
    },
    "k": {
        "title": {"ko": "계좌 재사용 반복거래 · 계좌탈취 후 인증변경",
                  "en": "Repeated reuse of the same recipient · takeover with auth changes"},
        "indicators": [
            _ind("repeat_tx", 3,
                 lambda r: (lambda v: None if v is None else v >= 2)(_f(r, "Number_of_transaction_with_the_account")),
                 {"ko": "동일 수취계좌 거래 2건 이상 (k형 z=2.17 사기 중 1위 · 실측 정밀도 48.5%)",
                  "en": "≥2 transactions with the same recipient (z=2.17, highest; 48.5% precision)"},
                 lambda r: f"동일계좌 거래={_f(r,'Number_of_transaction_with_the_account',0):.0f}건"),
            _ind("repeat_hist", 2,
                 lambda r: (lambda v: None if v is None else v >= 2)(_f(r, "Transaction_history_with_the_account")),
                 {"ko": "수취계좌 거래이력 2건 이상 (k형 z=1.01 사기 중 1위)",
                  "en": "≥2 history entries with recipient (z=1.01, highest)"},
                 lambda r: f"수취계좌 이력={_f(r,'Transaction_history_with_the_account',0):.0f}건"),
            _ind("auth_change", 3,
                 lambda r: (lambda s: None if s is None else s >= 4)(_sum_flags(r, _AU)),
                 {"ko": "인증수단 변경 이력 전반 최고 (k형 합계 3.59)",
                  "en": "Authentication changes across the board (k sum 3.59)"},
                 lambda r: f"인증변경 합={_sum_flags(r,_AU)}"),
            _ind("active_account", 2,
                 lambda r: (lambda v: None if v is None else v == 0)(_f(r, "Unused_account_status")),
                 {"ko": "활성 계좌 (k형 미사용계좌 실측 0% · 다른 유형은 40~63%) — 강한 배제 조건",
                  "en": "Active account (0% dormant in k vs 40-63% elsewhere) — strong exclusion signal"},
                 lambda r: "미사용계좌=0"),
            _ind("not_others", 1, lambda r: (lambda c: None if c is None else c != CH_OTHERS)(_ch(r)),
                 {"ko": "Others 채널 아님 (k형 실측 0% · ATM 36%)", "en": "Not Others channel (0% of k; ATM 36%)"},
                 lambda r: f"Channel={_ch(r)}"),
        ],
    },
    "l": {
        "title": {"ko": "고령층 표적 명의도용 (확신도 낮음)", "en": "Elderly-targeted identity theft (low confidence)"},
        "indicators": [
            _ind("elderly", 3,
                 lambda r: (lambda v: None if v is None else 1955 <= v <= 1965)(_f(r, "Customer_Birthyear")),
                 {"ko": "출생연도 1955~1965 (l형 z=-1.18 · 전 유형 중 유일한 연령 편중)",
                  "en": "Born 1955-1965 (z=-1.18; the only type with an age concentration)"},
                 lambda r: f"출생={_f(r,'Customer_Birthyear',0):.0f}년"),
            _ind("elderly_wide", 1,
                 lambda r: (lambda v: None if v is None else v <= 1970)(_f(r, "Customer_Birthyear")),
                 {"ko": "1970년 이전 출생 (고령층)", "en": "Born before 1970 (elderly)"},
                 lambda r: f"출생={_f(r,'Customer_Birthyear',0):.0f}년"),
            _ind("low_recip", 2,
                 lambda r: (lambda v: None if v is None else v <= 0)(_f(r, "Number_of_transaction_with_the_account")),
                 {"ko": "수취계좌 거래횟수 없음", "en": "No prior transactions with recipient"},
                 lambda r: f"동일계좌 거래={_f(r,'Number_of_transaction_with_the_account',0):.0f}건"),
            _ind("clean_device", 1,
                 lambda r: (lambda s: None if s is None else s <= 0)(_sum_flags(r, _MB)),
                 {"ko": "단말 악성행위 없음 (l형 0.34 · 사기 중 최저 수준) — 기술 침입이 아닌 심리 조작 정황",
                  "en": "No device malware (l 0.34, near lowest) — suggests social engineering, not intrusion"},
                 lambda r: f"악성행위 합={_sum_flags(r,_MB)}"),
        ],
    },
    "m": {
        "title": {"ko": "정상 — 소액·여유잔액 패턴", "en": "Normal — small amount with ample balance"},
        "indicators": [
            _ind("small_ratio", 3,
                 lambda r: (lambda v: None if v is None else v < 0.2)(_f(r, "Amount_vs_remaining_balance")),
                 {"ko": "잔액 대비 소액 이체 (20% 미만)", "en": "Small relative to balance (<20%)"},
                 lambda r: f"잔액대비={_f(r,'Amount_vs_remaining_balance',0):.2f}"),
            _ind("no_threat", 2,
                 lambda r: (lambda s, rt, vp: None if None in (s, rt, vp) else (s == 0 and not rt and not vp))(
                     _sum_flags(r, _MB), _flag(r, "Customer_rooting_jailbreak_indicator"),
                     _flag(r, "Customer_VPN_Indicator")),
                 {"ko": "단말 위협 신호 없음 (악성·루팅·VPN 모두 0)",
                  "en": "No device threat signals (malware, rooting, VPN all zero)"},
                 lambda r: "악성/루팅/VPN 모두 0"),
            _ind("in_limit", 1,
                 lambda r: (lambda v: None if v is None else v < 0.8)(_f(r, "Amount_vs_daily_limit")),
                 {"ko": "일일 한도 대비 여유 (80% 미만)", "en": "Well within the daily limit (<80%)"},
                 lambda r: f"한도대비={_f(r,'Amount_vs_daily_limit',0):.2f}"),
            _ind("no_fail", 1, lambda r: (lambda v: None if v is None else v == 0)(_f(r, "Transaction_Failure_Status")),
                 {"ko": "거래 실패 없음", "en": "No transaction failure"},
                 lambda r: "실패=0"),
        ],
    },
}

# 화면 배지용 유형 한 줄 요약
TYPE_TITLES = {k: v["title"] for k, v in TYPE_SIGNATURES.items()}

# ══════════════════════════════════════════════════════════
# 시그니처별 기준선 — "사기 전반에서 이 시그니처가 받는 평균 점수" (사기 1,200건 실측)
#   D/F/K 시그니처는 항목이 흔해서 아무 사기 행에도 0.5~0.68을 준다.
#   그래서 원점수(score)로 유형을 겨루면 D/F/K가 항상 이겨 a·h·i형이 묻힌다.
#   → 기준선으로 나눈 **적합도 지수(index)** 로 비교한다. 실측 개선:
#        Top-1  37.2% → 43.7%   (무작위 8.3% 대비 5.2배)
#        Top-3  74.6% → 81.1%   (무작위 25.0% 대비 3.2배)
#        a형 Top-1 12% → 84% · h형 12% → 77% · i형 11% → 47%
# ══════════════════════════════════════════════════════════
SIGNATURE_BASELINE = {
    "a": 0.1971, "b": 0.2431, "c": 0.3260, "d": 0.6775, "e": 0.4058, "f": 0.5048,
    "g": 0.5018, "h": 0.1515, "i": 0.2415, "j": 0.4439, "k": 0.4236, "l": 0.4016,
    "m": 0.5500,
}

_L = {
    "hit": {"ko": "충족", "en": "met", "ja": "該当", "zh": "符合"},
    "miss": {"ko": "미충족", "en": "not met", "ja": "非該当", "zh": "不符"},
    "unknown": {"ko": "확인 불가(값 없음)", "en": "unknown (missing)", "ja": "確認不可", "zh": "无法确认"},
}


class RuleChecker:
    """유형 시그니처 대조기. **사기 여부는 판정하지 않는다.**"""

    def __init__(self, lang: str = "ko"):
        self.lang = lang if lang in ("ko", "en", "ja", "zh") else "ko"

    # ── 단일 유형 대조 ─────────────────────────────────
    def check(self, row: dict, type_code: str) -> dict:
        tc = str(type_code or "").lower()
        sig = TYPE_SIGNATURES.get(tc)
        if sig is None:
            return {"type": tc, "known": False, "hits": [], "misses": [], "unknowns": [],
                    "score": 0.0, "n_hit": 0, "n_total": 0, "title": ""}
        hits, misses, unknowns = [], [], []
        w_hit = w_total = 0
        for ind in sig["indicators"]:
            try:
                res = ind["test"](row)
            except Exception:
                res = None
            item = {"id": ind["id"], "weight": ind["weight"],
                    "label": ind["label"].get(self.lang, ind["label"]["ko"])}
            if res is None:
                unknowns.append(item)
                continue
            w_total += ind["weight"]
            if res:
                try:
                    item["evidence"] = ind["ev"](row)
                except Exception:
                    item["evidence"] = ""
                hits.append(item)
                w_hit += ind["weight"]
            else:
                misses.append(item)
        return {
            "type": tc, "known": True,
            "title": sig["title"].get(self.lang, sig["title"]["ko"]),
            "hits": hits, "misses": misses, "unknowns": unknowns,
            "n_hit": len(hits), "n_total": len(hits) + len(misses),
            "score": round(w_hit / w_total, 4) if w_total else 0.0,
            # 적합도 지수 = 원점수 / 기준선. 1.0이면 '사기 전반 평균 수준', 2.0이면 2배 특징적
            "index": round((w_hit / w_total) / SIGNATURE_BASELINE.get(tc, 0.4), 3) if w_total else 0.0,
        }

    # ── 전 유형 적합도 순위 ────────────────────────────
    def rank(self, row: dict, exclude_normal: bool = True) -> list[tuple[str, float]]:
        """적합도 지수(기준선 정규화) 내림차순. 원점수로 겨루면 D/F/K가 독식한다."""
        out = []
        for tc in TYPE_SIGNATURES:
            if exclude_normal and tc == "m":
                continue
            r = self.check(row, tc)
            if r["n_total"]:
                out.append((tc, r["index"]))
        out.sort(key=lambda x: (-x[1], x[0]))
        return out

    # ── 종합 리포트 ────────────────────────────────────
    def report(self, row: dict, predicted_type: str) -> dict:
        """모델 예측 유형에 대한 근거 + 규칙이 더 잘 맞는 유형 제시."""
        main = self.check(row, predicted_type)
        rk = self.rank(row, exclude_normal=(str(predicted_type).lower() != "m"))
        best = rk[0] if rk else (None, 0.0)
        agree = (best[0] == main["type"]) if best[0] else None
        main.update({
            "ranking": rk[:4],
            "best_rule_type": best[0],
            "best_rule_index": best[1],
            "agreement": agree,
            # 지수 배율. 1.4 이상이면 "규칙은 다른 유형을 더 강하게 지지" → 검토 권장
            "gap": round(best[1] / main["index"], 3) if (best[0] and main["index"]) else 1.0,
        })
        return main

    # ── LLM/화면용 텍스트 ──────────────────────────────
    def explain_text(self, row: dict, predicted_type: str, max_items: int = 6) -> str:
        """AI 프롬프트에 넣을 근거 블록.
        실제 값(evidence)을 함께 제공해 **모델이 없는 근거를 지어내는 것을 막는다.**"""
        r = self.report(row, predicted_type)
        if not r["known"]:
            return ""
        L = self.lang
        lines = [f"[규칙 대조 — {str(r['type']).upper()}형: {r['title']}]",
                 f" 근거 일치도: {r['n_hit']}/{r['n_total']}개 충족 "
                 f"(가중 점수 {r['score']:.2f} · 적합도 지수 {r['index']:.2f}배)"]
        for h in r["hits"][:max_items]:
            lines.append(f"  ✅ {_L['hit'][L]}: {h['label']}  →  {h.get('evidence','')}")
        for mi in r["misses"][:max_items]:
            lines.append(f"  ⬜ {_L['miss'][L]}: {mi['label']}")
        if r["unknowns"]:
            lines.append(f"  ❔ {_L['unknown'][L]}: "
                         + ", ".join(u["label"] for u in r["unknowns"][:3]))
        if r["best_rule_type"] and r["agreement"] is False and r["gap"] >= 1.3:
            lines.append(f" ⚠ 규칙상으로는 {str(r['best_rule_type']).upper()}형이 더 잘 맞습니다 "
                         f"(적합도 지수 {r['best_rule_index']:.2f} vs {r['index']:.2f} = {r['gap']:.1f}배) "
                         f"— 수동 검토 권장")
        lines.append(" ※ 위 항목은 '사기 여부'가 아니라 '어느 유형의 특징에 맞는지'만 나타냅니다. "
                     "사기 여부 판정은 ML 모델 결과를 따르십시오.")
        return "\n".join(lines)


def make_rule_checker(lang: str = "ko") -> RuleChecker:
    return RuleChecker(lang)

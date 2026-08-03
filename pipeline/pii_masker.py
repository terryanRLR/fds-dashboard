"""
PIIMasker — 개인정보 마스킹 모듈
FDS 대시보드에서 LLM / Slack / Email 전달 전에 민감 정보를 마스킹합니다.
v1 — 컬럼명 기반 + 패턴 기반 이중 안전장치
"""

import re
import hashlib
import logging

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════
# 마스킹 대상 컬럼 정의
# ══════════════════════════════════════════════════════════

# Level 1: 직접 식별자 — 무조건 마스킹
DIRECT_IDENTIFIERS = {
    "Customer_personal_identifier",   # 고객 이름
    "Customer_identification_number", # 식별번호
    "ID",                             # 거래 ID
}

# Level 2: 네트워크/위치
NETWORK_LOCATION = {
    "IP_Address",
    "MAC_Address",
    "Location",
}

# Level 3: 계좌/금융 식별자
ACCOUNT_IDS = {
    "Account_account_number",
    "Recipient_Account_Number",
}

# Level 4: 준식별자
QUASI_IDENTIFIERS = {
    "Customer_Birthyear",
}

# Level 5: 시간 정보 (정밀도 축소)
DATETIME_FIELDS = {
    "Transaction_Datetime",
    "Customer_registration_datetime",
    "Account_creation_datetime",
    "Last_atm_transaction_datetime",
    "Last_bank_branch_transaction_datetime",
    "Transaction_resumed_date",
}

# 레벨별 그룹핑
LEVEL_MAP = {
    "off":  set(),                                                            # 마스킹 없음
    "basic": DIRECT_IDENTIFIERS,                                              # Level 1만
    "standard": DIRECT_IDENTIFIERS | NETWORK_LOCATION | ACCOUNT_IDS,          # Level 1~3
    "strict": DIRECT_IDENTIFIERS | NETWORK_LOCATION | ACCOUNT_IDS             # Level 1~5 전부
              | QUASI_IDENTIFIERS | DATETIME_FIELDS,
}

# 레벨 표시 이름
LEVEL_LABELS = {
    "off":      "🔓 OFF — 마스킹 없음 (내부 테스트)",
    "basic":    "🟡 기본 — 이름·식별번호만",
    "standard": "🟠 표준 — + IP·위치·계좌",
    "strict":   "🔴 강화 — + 생년·시간 전체",
}

# ══════════════════════════════════════════════════════════
# 패턴 기반 자동 감지 (컬럼명 무관)
# ══════════════════════════════════════════════════════════
REGEX_PATTERNS = {
    "ip_v4":      (re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b'),
                   lambda m: f"{m.group(1)}.{m.group(2)}.*.*"),
    "mac_addr":   (re.compile(r'([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}):[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}'),
                   lambda m: f"{m.group(1)}:**:**:**"),
    "email":      (re.compile(r'([\w])[.\w]*@([\w])[.\w]*\.(\w+)'),
                   lambda m: f"{m.group(1)}***@{m.group(2)}***.{m.group(3)}"),
    "phone_kr":   (re.compile(r'(01[016789])-?(\d{3,4})-?(\d{4})'),
                   lambda m: f"{m.group(1)}-****-{m.group(3)}"),
    "coordinates":(re.compile(r'(\d{2})\.\d{4,}\s+(\d{3})\.\d{4,}'),
                   lambda m: f"**.***** ***.*****"),
    "korean_name":(re.compile(r'^[가-힣]{2,4}$'),
                   lambda m: m.group()[0] + "○" * (len(m.group()) - 1)),
}


# ══════════════════════════════════════════════════════════
# 개별 마스킹 함수
# ══════════════════════════════════════════════════════════

def _mask_name(value: str) -> str:
    """이름 마스킹: 이상호 → 이○○"""
    s = str(value).strip()
    if not s or s in ('nan', 'None', 'N/A'):
        return s
    # 한글 이름 (2~4자)
    if re.match(r'^[가-힣]{2,4}$', s):
        return s[0] + "○" * (len(s) - 1)
    # 영문 등
    if len(s) > 2:
        return s[0] + "*" * (len(s) - 2) + s[-1]
    return "*" * len(s)


def _mask_id_number(value: str) -> str:
    """식별번호 마스킹: BJWQxd-WBASPLJ → BJ****-******LJ"""
    s = str(value).strip()
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


def _mask_transaction_id(value: str) -> str:
    """거래 ID: TRAIN_000000 → TXN_***000"""
    s = str(value).strip()
    if len(s) > 6:
        return "TXN_" + "*" * (len(s) - 6) + s[-3:]
    return "TXN_***"


def _mask_ip(value: str) -> str:
    """IP: 171.237.22.26 → 171.237.*.*"""
    s = str(value).strip()
    m = re.match(r'^(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}$', s)
    if m:
        return f"{m.group(1)}.{m.group(2)}.*.*"
    return s


def _mask_mac(value: str) -> str:
    """MAC: 44:b3:37:b1:2e:ce → 44:b3:37:**:**:**"""
    s = str(value).strip()
    parts = s.split(":")
    if len(parts) == 6:
        return ":".join(parts[:3] + ["**", "**", "**"])
    return s


def _mask_location(value: str) -> str:
    """위치: 강원도 고성군 죽왕면 38.354486 128.509098 → 강원도 ***"""
    s = str(value).strip()
    # 좌표 제거
    s = re.sub(r'\d{2}\.\d{4,}\s+\d{3}\.\d{4,}', '', s).strip()
    # 시도만 유지
    parts = s.split()
    if parts:
        return parts[0] + " ***"
    return "***"


def _mask_account(value: str) -> str:
    """계좌: oVZASOzgcm → oV******cm"""
    s = str(value).strip()
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


def _mask_birthyear(value) -> str:
    """생년: 1980 → 1980년대"""
    try:
        year = int(value)
        decade = (year // 10) * 10
        return f"{decade}년대"
    except (ValueError, TypeError):
        return str(value)


def _mask_datetime(value: str) -> str:
    """시간: 2003-01-25 22:20:34 → 2003-01-25 (날짜만)"""
    s = str(value).strip()
    # YYYY-MM-DD HH:MM:SS → YYYY-MM-DD
    m = re.match(r'(\d{4}-\d{2}-\d{2})', s)
    if m:
        return m.group(1)
    return s


# 컬럼별 마스킹 함수 매핑
COLUMN_MASKERS = {
    "Customer_personal_identifier":   _mask_name,
    "Customer_identification_number": _mask_id_number,
    "ID":                             _mask_transaction_id,
    "IP_Address":                     _mask_ip,
    "MAC_Address":                    _mask_mac,
    "Location":                       _mask_location,
    "Account_account_number":         _mask_account,
    "Recipient_Account_Number":       _mask_account,
    "Customer_Birthyear":             _mask_birthyear,
}
# datetime 컬럼 일괄 등록
for _dt_col in DATETIME_FIELDS:
    if _dt_col not in COLUMN_MASKERS:
        COLUMN_MASKERS[_dt_col] = _mask_datetime


# ══════════════════════════════════════════════════════════
# 메인 마스커 클래스
# ══════════════════════════════════════════════════════════

class PIIMasker:
    """
    개인정보 마스킹기.

    Parameters
    ----------
    level : str
        'off' | 'basic' | 'standard' | 'strict'
    enable_regex : bool
        True면 컬럼명 목록에 없어도 값 패턴으로 자동 감지·마스킹
    """

    def __init__(self, level: str = "standard", enable_regex: bool = True):
        self.level = level
        self.enable_regex = enable_regex
        self.target_columns = LEVEL_MAP.get(level, LEVEL_MAP["standard"])
        self._masked_log = []  # 마스킹된 필드 기록

    def mask_row(self, row: dict) -> dict:
        """
        row dict를 마스킹하여 새 dict 반환 (원본 변경 없음).
        내부 키(_로 시작)는 건너뜀.
        """
        if self.level == "off":
            self._masked_log = []   # 🐛 FIX: 이전 호출 로그 잔존 방지
            return dict(row)

        masked = {}
        self._masked_log = []

        for key, value in row.items():
            # 내부 키는 그대로
            if key.startswith('_'):
                masked[key] = value
                continue

            val_str = str(value) if value is not None else ""

            # ① 컬럼명 기반 마스킹
            if key in self.target_columns and key in COLUMN_MASKERS:
                masked[key] = COLUMN_MASKERS[key](value)
                if masked[key] != val_str:
                    self._masked_log.append(key)
                continue

            # ② 패턴 기반 자동 감지 (standard 이상에서만)
            if self.enable_regex and self.level in ("standard", "strict"):
                new_val = self._regex_mask(val_str)
                if new_val != val_str:
                    masked[key] = new_val
                    self._masked_log.append(f"{key}(패턴)")
                    continue

            # 마스킹 불필요
            masked[key] = value

        return masked

    def mask_text(self, text: str) -> str:
        """
        자유 텍스트 (Slack 메시지, 이메일 본문) 내의 민감 패턴 마스킹.
        """
        if self.level == "off":
            return text

        result = text
        for name, (pattern, replacer) in REGEX_PATTERNS.items():
            if name == "korean_name":
                continue  # 텍스트에서 한글 이름 자동 감지는 오탐 위험 → 스킵
            result = pattern.sub(replacer, result)
        return result

    def get_log(self) -> list[str]:
        """마지막 mask_row 호출에서 마스킹된 필드 목록"""
        return self._masked_log.copy()

    def _regex_mask(self, value: str) -> str:
        """값에서 민감 패턴을 감지하여 마스킹"""
        result = value
        for name, (pattern, replacer) in REGEX_PATTERNS.items():
            if name == "korean_name":
                # 🐛 FIX: 2~4자 한글 일반 값('명의도용' 등)을 이름으로 오인하는 오탐 방지.
                #        이름 컬럼은 COLUMN_MASKERS(컬럼명 기반)가 이미 처리함.
                continue
            result = pattern.sub(replacer, result)
        return result

    @staticmethod
    def hash_value(value: str, length: int = 8) -> str:
        """SHA256 해시 (비가역 가명화)"""
        return hashlib.sha256(str(value).encode()).hexdigest()[:length]

    def summary(self) -> dict:
        """현재 설정 요약"""
        return {
            "level": self.level,
            "level_label": LEVEL_LABELS.get(self.level, self.level),
            "target_columns": sorted(self.target_columns),
            "regex_enabled": self.enable_regex,
            "column_count": len(self.target_columns),
        }

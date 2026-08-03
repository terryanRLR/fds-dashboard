"""
FDS 이상거래탐지 QA 검증 대시보드 — Streamlit + CSS 인젝션
v4 — 7 테마 모드, 사이드바 아이콘 수정, RAG 유형 해설, LLM 설정 세션5
     디버깅·최적화·에러바운더리·헬퍼함수·캐시·OS테마감지 개선
"""

import json, random, time, traceback, os, logging
import html as _html_esc  # 🐛 FIX(v5): LLM 출력 HTML 이스케이프용
import importlib.util
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# .env 파일에서 환경변수 로딩 (python-dotenv 설치 시)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log = logging.getLogger("fds_dashboard")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

st.set_page_config(
    page_title="FDS QA Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 의존성 체크 ──────────────────────────────────────────
_REQUIRED_PKGS = {
    "lightgbm":             "pip install lightgbm",
    "sklearn":              "pip install scikit-learn",
    "plotly":               "pip install plotly",
    "chromadb":             "pip install chromadb",
    "sentence_transformers":"pip install sentence-transformers",
    "anthropic":            "pip install anthropic",
    "openai":               "pip install openai",
    "dotenv":               "pip install python-dotenv",
}
# ⚡ 최적화: 실제 import 대신 find_spec — torch 등 무거운 패키지를 로드하지 않고
#    설치 여부만 확인 → 초기 로딩 수십 초 단축
_missing = []
for pkg, cmd in _REQUIRED_PKGS.items():
    if importlib.util.find_spec(pkg) is None:
        _missing.append((pkg, cmd))

# ══════════════════════════════════════════════════════════
# 다국어(i18n) 초기화 — KO(기본) / EN / JA / ZH
# ══════════════════════════════════════════════════════════
from i18n_data import (
    LANG_OPTIONS, LANG_DISPLAY, make_t,
    FRAUD_LABELS_I18N, FRAUD_SHORT_I18N, FRAUD_TYPE_DETAILS_I18N,
    ACCESS_MEDIUM_MAP_I18N, FLAG_LABELS_I18N, FLAG_HELP_I18N,
    SESSION_LABELS_I18N, MODEL_DESC_I18N, THEME_LABEL_I18N,
    NEW_THEME_META_I18N, NEW_THEME_ORDER, HYPOTHESES_I18N,
    model_display_name, llm_lang_directive,
)
if 'lang' not in st.session_state:
    st.session_state['lang'] = 'ko'
t = make_t(st.session_state)
LANG = st.session_state['lang']

if _missing:
    with st.expander(t("pkg.expander", n=len(_missing)), expanded=True):
        st.markdown(t("pkg.desc"))
        for pkg, cmd in _missing:
            st.code(cmd, language="bash")
        all_cmds = " && ".join(cmd for _, cmd in _missing)
        st.markdown(t("pkg.install_all"))
        st.code(f"pip install {' '.join(pkg for pkg,_ in _missing)}", language="bash")

# ══════════════════════════════════════════════════════════
# 테마 시스템 정의 — 7개 모드
# ══════════════════════════════════════════════════════════
THEMES = {
    "🌊 Cyber Teal": {
        "label": THEME_LABEL_I18N["🌊 Cyber Teal"][LANG],
        "bg_base": "#080e1a", "bg_surface": "#0d1626", "bg_card": "#111d30", "bg_card_hover": "#152238",
        "accent": "#00d2c8", "accent_dim": "#00a89f", "accent_rgb": "0,210,200",
        "red": "#ff3b5c", "red_dim": "#cc2244",
        "amber": "#f59e0b", "green": "#10d98c", "blue": "#3b82f6", "purple": "#8b5cf6",
        "text_primary": "#e8f0fe", "text_secondary": "#8899b4", "text_muted": "#4a5a72",
        "plotly_colors": ["#00d2c8","#3b82f6","#8b5cf6","#f59e0b","#ff3b5c","#10d98c"],
    },
    "🔥 Crimson Matrix": {
        "label": THEME_LABEL_I18N["🔥 Crimson Matrix"][LANG],
        "bg_base": "#0a0505", "bg_surface": "#140a0a", "bg_card": "#1f0f0f", "bg_card_hover": "#2a1414",
        "accent": "#ff3b5c", "accent_dim": "#cc2244", "accent_rgb": "255,59,92",
        "red": "#ff6b6b", "red_dim": "#e04040",
        "amber": "#ff9f43", "green": "#26de81", "blue": "#45aaf2", "purple": "#a55eea",
        "text_primary": "#fce4ec", "text_secondary": "#b07a7a", "text_muted": "#6b4444",
        "plotly_colors": ["#ff3b5c","#ff9f43","#a55eea","#45aaf2","#26de81","#fce4ec"],
    },
    "🌌 Nebula Purple": {
        "label": THEME_LABEL_I18N["🌌 Nebula Purple"][LANG],
        "bg_base": "#0b0714", "bg_surface": "#110d1f", "bg_card": "#1a1330", "bg_card_hover": "#231a3f",
        "accent": "#b388ff", "accent_dim": "#9060e0", "accent_rgb": "179,136,255",
        "red": "#ff5277", "red_dim": "#d4365e",
        "amber": "#ffca28", "green": "#69f0ae", "blue": "#40c4ff", "purple": "#ea80fc",
        "text_primary": "#ede7f6", "text_secondary": "#9575cd", "text_muted": "#5c4a8a",
        "plotly_colors": ["#b388ff","#40c4ff","#ea80fc","#ffca28","#ff5277","#69f0ae"],
    },
    "🏔️ Arctic Frost": {
        "label": THEME_LABEL_I18N["🏔️ Arctic Frost"][LANG],
        "bg_base": "#f0f4f8", "bg_surface": "#e2e8f0", "bg_card": "#ffffff", "bg_card_hover": "#f7fafc",
        "accent": "#0284c7", "accent_dim": "#0369a1", "accent_rgb": "2,132,199",
        "red": "#dc2626", "red_dim": "#b91c1c",
        "amber": "#d97706", "green": "#059669", "blue": "#2563eb", "purple": "#7c3aed",
        "text_primary": "#0f172a", "text_secondary": "#475569", "text_muted": "#94a3b8",
        "plotly_colors": ["#0284c7","#2563eb","#7c3aed","#d97706","#dc2626","#059669"],
    },
    "🌿 Forest Terminal": {
        "label": THEME_LABEL_I18N["🌿 Forest Terminal"][LANG],
        "bg_base": "#050a05", "bg_surface": "#0a140a", "bg_card": "#0f1f0f", "bg_card_hover": "#142814",
        "accent": "#39ff14", "accent_dim": "#22cc00", "accent_rgb": "57,255,20",
        "red": "#ff4444", "red_dim": "#cc2222",
        "amber": "#ccff00", "green": "#00ff88", "blue": "#00ccff", "purple": "#cc77ff",
        "text_primary": "#d4ffd4", "text_secondary": "#66aa66", "text_muted": "#336633",
        "plotly_colors": ["#39ff14","#00ccff","#cc77ff","#ccff00","#ff4444","#00ff88"],
    },
    "🌅 Solar Gold": {
        "label": THEME_LABEL_I18N["🌅 Solar Gold"][LANG],
        "bg_base": "#0c0a05", "bg_surface": "#16120a", "bg_card": "#211c10", "bg_card_hover": "#2c2515",
        "accent": "#f59e0b", "accent_dim": "#d48806", "accent_rgb": "245,158,11",
        "red": "#ef4444", "red_dim": "#dc2626",
        "amber": "#fbbf24", "green": "#34d399", "blue": "#60a5fa", "purple": "#c084fc",
        "text_primary": "#fef3c7", "text_secondary": "#a8956a", "text_muted": "#6b5c3a",
        "plotly_colors": ["#f59e0b","#fbbf24","#c084fc","#60a5fa","#ef4444","#34d399"],
    },
    "🎭 Phantom Noir": {
        "label": THEME_LABEL_I18N["🎭 Phantom Noir"][LANG],
        "bg_base": "#000000", "bg_surface": "#0a0a0a", "bg_card": "#141414", "bg_card_hover": "#1e1e1e",
        "accent": "#e0e0e0", "accent_dim": "#b0b0b0", "accent_rgb": "224,224,224",
        "red": "#ff4757", "red_dim": "#d63031",
        "amber": "#ffa502", "green": "#2ed573", "blue": "#70a1ff", "purple": "#a29bfe",
        "text_primary": "#f5f5f5", "text_secondary": "#888888", "text_muted": "#444444",
        "plotly_colors": ["#e0e0e0","#70a1ff","#a29bfe","#ffa502","#ff4757","#2ed573"],
    },
}

# session_state 초기화 (모든 기본값을 한곳에서 관리)
_DEFAULTS = {
    'session_idx': 0,
    'lang': 'ko',
    'ui_mode': "new",               # new | old (우측 상단 ⋮에서 전환)
    'new_theme': "dark",            # 신 UI 전용 테마 (내부 ID)
    'theme_name': "🌊 Cyber Teal",
    'selected_model': "LightGBM (기본)",
    'run_with_llm': True,
    'auto_slack': False,
    'auto_email': False,
    'pii_mask_level': 'standard',
    'pii_skip_local': True,
    'notify_email': os.getenv('FDS_NOTIFY_EMAIL', os.getenv('SMTP_USER', '')),
    # ✨ v9.1: 신 UI 컴팩트 오버뷰 (한 세션 = 한 화면)
    'compact_view': False,
    # ✨ v9.1: 이중 임계값 발송 (1차=의심→Slack 검토요청 · 2차=확정→Slack+Email 통보)
    'dual_threshold': False,
    'th_review': 0.6,
    'th_confirm': 0.8,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ══════════════════════════════════════════════════════════
# 🎛 기본 선택값 설정 (여기 세 줄만 바꾸면 기본값이 바뀝니다)
#   · 파일명/데이터셋명의 '일부 조각'으로 매칭합니다 (대소문자·공백·밑줄 무시).
#   · 매칭되는 항목이 없으면 자동으로 기존 기본 동작으로 되돌아갑니다(안전).
#   · 사용자가 화면에서 직접 바꾼 선택은 그대로 유지되며, 아래 값은 '최초 진입 시'에만 적용됩니다.
# ══════════════════════════════════════════════════════════
DEFAULT_DETECT_MODEL_MATCH  = "lgbm_13class"   # 사이드바 '탐지 모델(전역)' 기본  → lgbm_13class(모델).pkl
DEFAULT_DATASET_MATCH       = "parquet:tr"     # 사이드바 '평가 데이터셋' 기본     → X_tr.parquet + y_tr.parquet
DEFAULT_COMPARE_MODEL_MATCH = "lgbm_13class"   # 세션2 '비교할 모델' 기본(하나만) → lgbm_13class(모델).pkl

def _norm_key(s):
    """매칭 정규화 — 대소문자·공백·밑줄 차이를 무시 (auto-discovery의 title() 변형에도 강함)."""
    return str(s).lower().replace(" ", "").replace("_", "")

def _pick_key(keys, fragment, fallback=None):
    """keys 중 fragment(정규화 비교)를 포함하는 첫 키. 없으면 fallback."""
    frag = _norm_key(fragment)
    for k in keys:
        if frag in _norm_key(k):
            return k
    return fallback

def _pick_model_key(models_dict, fragment, fallback=None):
    """모델 dict에서 '키 또는 path'에 fragment가 든 첫 키. (path 기준이라 표시명이 바뀌어도 안전)"""
    frag = _norm_key(fragment)
    for k, info in models_dict.items():
        if frag in _norm_key(k) or frag in _norm_key((info or {}).get('path', '')):
            return k
    return fallback

# ══════════════════════════════════════════════════════════
# ✨ 신 UI 테마 — "정제된 금융 계기판(Instrument Console)"
#    네온 글로우 제거 · 단일 액센트 · 헤어라인 보더 · 좌측 컬러 스파인
# ══════════════════════════════════════════════════════════
NEW_THEMES = {
    'dark': {
        "label": NEW_THEME_META_I18N["dark"]["label"][LANG],
        "bg_base": "#0b0f17", "bg_surface": "#10151f", "bg_card": "#141b28", "bg_card_hover": "#1a2233",
        "accent": "#6c8cff", "accent_dim": "#5272e8", "accent_rgb": "108,140,255",
        "red": "#ef5872", "red_dim": "#d43f5c",
        "amber": "#eab24a", "green": "#3ecf8e", "blue": "#58a6ff", "purple": "#a78bfa",
        "text_primary": "#e8edf7", "text_secondary": "#8b96ab", "text_muted": "#535e73",
        "plotly_colors": ["#6c8cff","#58a6ff","#a78bfa","#eab24a","#ef5872","#3ecf8e"],
    },
    'light': {
        "label": NEW_THEME_META_I18N["light"]["label"][LANG],
        "bg_base": "#f6f8fb", "bg_surface": "#edf0f6", "bg_card": "#ffffff", "bg_card_hover": "#f7f9fc",
        "accent": "#3b5bdb", "accent_dim": "#2f4ac2", "accent_rgb": "59,91,219",
        "red": "#d6455f", "red_dim": "#b83350",
        "amber": "#b07310", "green": "#0e9f6e", "blue": "#1d6fd8", "purple": "#7c5cd6",
        "text_primary": "#131b2c", "text_secondary": "#4b566b", "text_muted": "#96a0b5",
        "plotly_colors": ["#3b5bdb","#1d6fd8","#7c5cd6","#b07310","#d6455f","#0e9f6e"],
    },
    'amber': {
        "label": NEW_THEME_META_I18N["amber"]["label"][LANG],
        "bg_base": "#101216", "bg_surface": "#15181e", "bg_card": "#1a1e26", "bg_card_hover": "#212631",
        "accent": "#e0a13f", "accent_dim": "#c78a2c", "accent_rgb": "224,161,63",
        "red": "#e85d75", "red_dim": "#cc4560",
        "amber": "#e8c063", "green": "#4fc48f", "blue": "#6aa7e8", "purple": "#a68fe0",
        "text_primary": "#ece7dd", "text_secondary": "#9a948a", "text_muted": "#5d594f",
        "plotly_colors": ["#e0a13f","#6aa7e8","#a68fe0","#e8c063","#e85d75","#4fc48f"],
    },
    'evergreen': {
        "label": NEW_THEME_META_I18N["evergreen"]["label"][LANG],
        "bg_base": "#0c1310", "bg_surface": "#101a15", "bg_card": "#14211b", "bg_card_hover": "#1a2a22",
        "accent": "#35c28f", "accent_dim": "#27a377", "accent_rgb": "53,194,143",
        "red": "#e56176", "red_dim": "#c74a60",
        "amber": "#d9a842", "green": "#52d6a2", "blue": "#57b3d9", "purple": "#9d92e0",
        "text_primary": "#e2efe8", "text_secondary": "#8aa396", "text_muted": "#4e6157",
        "plotly_colors": ["#35c28f","#57b3d9","#9d92e0","#d9a842","#e56176","#52d6a2"],
    },
    'ivory': {
        "label": NEW_THEME_META_I18N["ivory"]["label"][LANG],
        "bg_base": "#faf7f2", "bg_surface": "#f1ece3", "bg_card": "#ffffff", "bg_card_hover": "#faf8f4",
        "accent": "#1f3a68", "accent_dim": "#16294c", "accent_rgb": "31,58,104",
        "red": "#b3324b", "red_dim": "#93263c",
        "amber": "#8a6410", "green": "#1a7d5c", "blue": "#2456a8", "purple": "#6a4fa8",
        "text_primary": "#201c14", "text_secondary": "#5a5344", "text_muted": "#a39a88",
        "plotly_colors": ["#1f3a68","#2456a8","#6a4fa8","#8a6410","#b3324b","#1a7d5c"],
    },
    'crimson': {
        "label": NEW_THEME_META_I18N["crimson"]["label"][LANG],
        "bg_base": "#120d0e", "bg_surface": "#181114", "bg_card": "#1e1518", "bg_card_hover": "#271b1f",
        "accent": "#e0405a", "accent_dim": "#c22e47", "accent_rgb": "224,64,90",
        "red": "#ff7454", "red_dim": "#e05a3e",
        "amber": "#e5aa4e", "green": "#3fc98e", "blue": "#6b9fe8", "purple": "#b08cf0",
        "text_primary": "#f2e9eb", "text_secondary": "#a89298", "text_muted": "#63535a",
        "plotly_colors": ["#e0405a","#6b9fe8","#b08cf0","#e5aa4e","#ff7454","#3fc98e"],
    },
    'slate': {
        "label": NEW_THEME_META_I18N["slate"]["label"][LANG],
        "bg_base": "#0e0f16", "bg_surface": "#13141d", "bg_card": "#181a26", "bg_card_hover": "#1f2130",
        "accent": "#9d8cff", "accent_dim": "#8272e6", "accent_rgb": "157,140,255",
        "red": "#ee5d7d", "red_dim": "#d24565",
        "amber": "#e0ac52", "green": "#46c99a", "blue": "#64a5f0", "purple": "#bd9df5",
        "text_primary": "#eae9f5", "text_secondary": "#9694ad", "text_muted": "#585670",
        "plotly_colors": ["#9d8cff","#64a5f0","#bd9df5","#e0ac52","#ee5d7d","#46c99a"],
    },
}

IS_NEW_UI = st.session_state.get('ui_mode', "new") == "new"
if IS_NEW_UI:
    _nt = st.session_state.get('new_theme', "dark")
    T = NEW_THEMES.get(_nt, NEW_THEMES["dark"])
else:
    T = THEMES.get(st.session_state['theme_name'], THEMES["🌊 Cyber Teal"])

# ══════════════════════════════════════════════════════════
# CSS 인젝션 (테마 동적 반영)
# ══════════════════════════════════════════════════════════
# ── ✨ v7 DESIGN: 테마 파생 RGB 상수 (하드코딩 색상 제거 → 7테마 전부 일관) ──
def _rgb(hexc: str) -> str:
    """'#rrggbb' → 'r,g,b' (rgba() 조립용)"""
    return f"{int(hexc[1:3],16)},{int(hexc[3:5],16)},{int(hexc[5:7],16)}"
_RED_RGB, _GRN_RGB = _rgb(T['red']), _rgb(T['green'])
_AMB_RGB, _BLU_RGB = _rgb(T['amber']), _rgb(T['blue'])
def _is_dark(hexc: str) -> bool:
    """🔧 FIX(v9.1): 기존 `T['bg_base'] < '#8'` 문자열 사전순 비교는 첫 hex 자릿수(0~7=다크)에만
    의존해, 배경이 '#80..'~'#ff..' 라도 첫 글자가 소문자/대문자냐에 따라 오판할 여지가 있었음.
    → 실제 상대 휘도(sRGB 근사)로 판별해 신규 테마 추가 시에도 안전. 현행 15개 테마 결과는 동일."""
    try:
        r, g, b = (int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16))
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 128
    except Exception:
        return True   # 파싱 실패 시 다크 가정 (기존 기본 동작 유지)
_IS_DARK_BG = _is_dark(T['bg_base'])

# ── CSS 블록 1: 폰트 + CSS 변수 + 기본 레이아웃 ──────────
_css_vars = f"""<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{--bg-base:{T['bg_base']};--bg-surface:{T['bg_surface']};--bg-card:{T['bg_card']};--bg-card-hover:{T['bg_card_hover']};--border:rgba({T['accent_rgb']},0.12);--border-glow:rgba({T['accent_rgb']},0.35);--accent:{T['accent']};--accent-dim:{T['accent_dim']};--red:{T['red']};--red-dim:{T['red_dim']};--amber:{T['amber']};--green:{T['green']};--blue:{T['blue']};--purple:{T['purple']};--text-primary:{T['text_primary']};--text-secondary:{T['text_secondary']};--text-muted:{T['text_muted']};--font-body:'Inter',sans-serif;--font-mono:'JetBrains Mono',monospace;--radius:10px;--radius-lg:16px;}}
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{{background:var(--bg-base)!important;font-family:var(--font-body)!important;color:var(--text-primary)!important;}}
[data-testid="stHeader"]{{background:transparent!important;}}
[data-testid="stSidebar"]{{background:var(--bg-surface)!important;border-right:1px solid var(--border)!important;}}
[data-testid="stSidebar"] *{{font-family:var(--font-body)!important;color:var(--text-primary)!important;}}
.main .block-container{{padding:1rem 2.5rem 2rem!important;max-width:1400px!important;}}
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"]{{background:var(--accent)!important;border-color:var(--accent)!important;}}
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stThumbValue"]{{color:var(--accent)!important;font-family:var(--font-mono)!important;}}
.stButton>button{{background:linear-gradient(135deg,var(--accent-dim),var(--accent))!important;color:var(--bg-base)!important;border:none!important;border-radius:var(--radius)!important;font-weight:700!important;font-family:var(--font-body)!important;font-size:13px!important;padding:8px 20px!important;letter-spacing:0.02em!important;transition:all 0.18s!important;box-shadow:0 0 16px rgba({T['accent_rgb']},0.20)!important;}}
.stButton>button:hover{{box-shadow:0 0 24px rgba({T['accent_rgb']},0.40)!important;transform:translateY(-1px)!important;}}
.stButton>button[kind="secondary"]{{background:transparent!important;border:1px solid var(--border-glow)!important;color:var(--accent)!important;box-shadow:none!important;}}
[data-baseweb="select"]>div,[data-baseweb="input"]>div{{background:var(--bg-card)!important;border-color:var(--border)!important;border-radius:var(--radius)!important;color:var(--text-primary)!important;font-family:var(--font-body)!important;}}
[data-baseweb="select"]>div:focus-within,[data-baseweb="input"]>div:focus-within{{border-color:var(--border-glow)!important;box-shadow:0 0 0 2px rgba({T['accent_rgb']},0.12)!important;}}
[data-testid="stTextInput"] input{{background:var(--bg-card)!important;border-color:var(--border)!important;color:var(--text-primary)!important;font-family:var(--font-mono)!important;font-size:13px!important;}}
/* 🐛 FIX(v9.1): 라이트 테마 입력 글자 가독성 — Streamlit 네이티브(다크) 테마가 입력 글자를
   흰색으로 강제해 라이트 배경에서 안 보이던 문제. number/textarea/select 검색창/date까지
   전부 테마 텍스트 색으로 통일 + 캐럿·플레이스홀더·자동완성(autofill)까지 커버 */
[data-testid="stNumberInput"] input,[data-testid="stTextArea"] textarea,[data-baseweb="textarea"] textarea,[data-baseweb="select"] input,[data-testid="stDateInput"] input,[data-testid="stTimeInput"] input{{background:var(--bg-card)!important;color:var(--text-primary)!important;}}
.stApp input,.stApp textarea{{color:var(--text-primary)!important;-webkit-text-fill-color:var(--text-primary)!important;caret-color:var(--accent)!important;}}
.stApp input::placeholder,.stApp textarea::placeholder{{color:var(--text-muted)!important;-webkit-text-fill-color:var(--text-muted)!important;opacity:1!important;}}
.stApp input:-webkit-autofill,.stApp input:-webkit-autofill:hover,.stApp input:-webkit-autofill:focus{{-webkit-box-shadow:0 0 0 1000px var(--bg-card) inset!important;-webkit-text-fill-color:var(--text-primary)!important;}}
[data-testid="stNumberInput"] input{{font-family:var(--font-mono)!important;}}
[data-testid="stCheckbox"] label{{font-size:12.5px!important;color:var(--text-secondary)!important;}}
[data-testid="stCheckbox"] [data-baseweb="checkbox"] div{{border-color:var(--border-glow)!important;}}
[data-testid="stDataFrame"]{{border:1px solid var(--border)!important;border-radius:var(--radius)!important;overflow:hidden!important;}}
[data-testid="stDataFrame"] th{{background:var(--bg-surface)!important;color:var(--accent)!important;font-family:var(--font-mono)!important;font-size:11px!important;letter-spacing:0.05em!important;text-transform:uppercase!important;}}
[data-testid="stDataFrame"] td{{background:var(--bg-card)!important;color:var(--text-primary)!important;font-family:var(--font-mono)!important;font-size:12px!important;}}
[data-testid="stTabs"] [data-baseweb="tab-list"]{{background:var(--bg-surface)!important;border-radius:var(--radius)!important;padding:4px!important;gap:2px!important;border:1px solid var(--border)!important;}}
[data-testid="stTabs"] [data-baseweb="tab"]{{background:transparent!important;color:var(--text-secondary)!important;border-radius:7px!important;font-size:13px!important;font-weight:500!important;padding:6px 16px!important;}}
[data-testid="stTabs"] [aria-selected="true"]{{background:rgba({T['accent_rgb']},0.12)!important;color:var(--accent)!important;}}
[data-testid="stExpander"]{{background:var(--bg-card)!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;}}
[data-testid="stExpander"] summary{{color:var(--text-primary)!important;font-weight:600!important;}}
hr{{border-color:var(--border)!important;margin:1.5rem 0!important;}}
::-webkit-scrollbar{{width:5px;height:5px;}}
::-webkit-scrollbar-track{{background:var(--bg-base);}}
::-webkit-scrollbar-thumb{{background:var(--border-glow);border-radius:4px;}}
</style>"""
if not IS_NEW_UI:
    st.markdown(_css_vars, unsafe_allow_html=True)

# ── CSS 블록 2: 커스텀 컴포넌트 + 사이드바 아이콘 수정 ───
_css_components = f"""<style>
[data-testid="stSidebar"] [data-testid="stIconMaterial"],[data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"]{{visibility:hidden!important;width:0!important;height:0!important;overflow:hidden!important;display:none!important;}}
.kpi-card{{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px 22px;position:relative;overflow:hidden;transition:border-color 0.2s,box-shadow 0.2s;}}
.kpi-card:hover{{border-color:var(--border-glow);box-shadow:0 0 20px rgba({T['accent_rgb']},0.08);}}
.kpi-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--kpi-accent,var(--accent));opacity:0.8;}}
.kpi-label{{color:var(--text-secondary);font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;margin:0 0 8px;}}
.kpi-value{{color:var(--text-primary);font-size:28px;font-weight:700;font-family:var(--font-mono);margin:0;line-height:1.1;}}
.kpi-delta{{color:var(--text-muted);font-size:12px;margin:6px 0 0;font-family:var(--font-mono);}}
.kpi-icon{{position:absolute;top:18px;right:18px;font-size:22px;opacity:0.25;}}
.section-header{{display:flex;align-items:center;gap:10px;margin:2rem 0 1rem;}}
.section-header-line{{flex:1;height:1px;background:linear-gradient(90deg,var(--border-glow),transparent);}}
.section-title{{color:var(--text-primary);font-size:15px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;}}
.section-badge{{background:rgba({T['accent_rgb']},0.10);color:var(--accent);border:1px solid var(--border-glow);border-radius:4px;font-size:10px;font-weight:700;padding:2px 8px;letter-spacing:0.06em;font-family:var(--font-mono);}}
.badge-danger{{display:inline-block;background:rgba({_RED_RGB},0.15);color:var(--red);border:1px solid rgba({_RED_RGB},0.4);border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;}}
.badge-safe{{display:inline-block;background:rgba({_GRN_RGB},0.12);color:var(--green);border:1px solid rgba({_GRN_RGB},0.4);border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;}}
.badge-warn{{display:inline-block;background:rgba({_AMB_RGB},0.12);color:var(--amber);border:1px solid rgba({_AMB_RGB},0.4);border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;}}
.result-panel{{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:24px 28px;margin:1rem 0;}}
.result-panel.anomaly{{border-color:rgba({_RED_RGB},0.5);box-shadow:0 0 30px rgba({_RED_RGB},0.08),inset 0 0 30px rgba({_RED_RGB},0.03);}}
.result-panel.normal{{border-color:rgba({_GRN_RGB},0.4);box-shadow:0 0 20px rgba({_GRN_RGB},0.05);}}
.gauge-wrap{{text-align:center;padding:8px 0;}}
.gauge-label{{font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-secondary);}}
.feature-tag{{display:inline-block;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:11.5px;font-family:var(--font-mono);color:var(--text-secondary);margin:2px;}}
.feature-tag.danger{{border-color:rgba({_RED_RGB},0.5);color:var(--red);}}
.feature-tag.safe{{border-color:rgba({_GRN_RGB},0.4);color:var(--green);}}
.alert-box{{border-radius:var(--radius);padding:14px 18px;font-size:13.5px;line-height:1.6;margin:8px 0;border-left:3px solid;}}
.alert-info{{background:rgba({_BLU_RGB},0.08);border-color:var(--blue);color:{T['blue']};}}
.alert-warn{{background:rgba({_AMB_RGB},0.08);border-color:var(--amber);color:{T['amber']};}}
.alert-error{{background:rgba({_RED_RGB},0.08);border-color:var(--red);color:{T['red']};}}
.alert-ok{{background:rgba({_GRN_RGB},0.08);border-color:var(--green);color:{T['green']};}}
.hypo-card{{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;margin-bottom:8px;transition:border-color 0.2s;}}
.hypo-card:hover{{border-color:var(--border-glow);}}
.hypo-code{{font-family:var(--font-mono);font-size:11px;font-weight:700;color:var(--accent);letter-spacing:0.06em;}}
.hypo-text{{font-size:13.5px;color:var(--text-secondary);margin:5px 0 0;line-height:1.5;}}
.prob-bar-wrap{{margin:3px 0;}}
.prob-bar-label{{display:flex;justify-content:space-between;font-size:11.5px;font-family:var(--font-mono);color:var(--text-secondary);margin-bottom:3px;}}
.prob-bar-bg{{background:var(--bg-surface);border-radius:3px;height:6px;overflow:hidden;}}
.prob-bar-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--accent-dim),var(--accent));transition:width 0.4s ease;}}
.prob-bar-fill.danger{{background:linear-gradient(90deg,var(--red-dim),var(--red));}}
.tag-pass{{background:rgba({_GRN_RGB},0.12);color:var(--green);border:1px solid rgba({_GRN_RGB},0.4);border-radius:5px;padding:2px 9px;font-size:11px;font-weight:700;font-family:var(--font-mono);}}
.tag-fail{{background:rgba({_RED_RGB},0.12);color:var(--red);border:1px solid rgba({_RED_RGB},0.4);border-radius:5px;padding:2px 9px;font-size:11px;font-weight:700;font-family:var(--font-mono);}}
[data-testid="stCode"]{{background:var(--bg-surface)!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;font-family:var(--font-mono)!important;font-size:12px!important;}}
.fraud-type-card{{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;margin:6px 0;transition:all 0.2s;}}
.fraud-type-card:hover{{border-color:var(--border-glow);box-shadow:0 0 12px rgba({T['accent_rgb']},0.06);}}
/* ── 🐛 FIX: 사이드바 토글 버튼 상시 가시성 (JS 타이밍 무관, 라이트 테마 포함) ── */
[data-testid="stSidebarCollapsedControl"]{{opacity:1!important;z-index:999999!important;}}
[data-testid="stSidebarCollapsedControl"] button,[data-testid="stSidebar"] button:has(span[data-testid="stIconMaterial"]){{background:linear-gradient(135deg,var(--accent-dim),var(--accent))!important;border:none!important;border-radius:10px!important;min-width:40px!important;min-height:40px!important;opacity:1!important;box-shadow:0 0 14px rgba({T['accent_rgb']},0.45),0 2px 6px rgba(0,0,0,0.25)!important;transition:box-shadow 0.2s!important;}}
[data-testid="stSidebarCollapsedControl"] button:hover,[data-testid="stSidebar"] button:has(span[data-testid="stIconMaterial"]):hover{{box-shadow:0 0 22px rgba({T['accent_rgb']},0.65)!important;}}
/* 숨겨진 기본 아이콘 대신 CSS 화살표 주입 — JS가 이미 교체한 버튼(:has 미매칭)엔 중복 적용 안 됨 */
[data-testid="stSidebarCollapsedControl"] button:has(span[data-testid="stIconMaterial"])::after{{content:'▶';color:{T['bg_base']};font-size:16px;font-weight:900;font-family:monospace;line-height:1;}}
[data-testid="stSidebar"] button:has(span[data-testid="stIconMaterial"])::after{{content:'◀';color:{T['bg_base']};font-size:16px;font-weight:900;font-family:monospace;line-height:1;}}
/* 🐛 FIX: 최신 Streamlit 버튼 testid(stExpandSidebarButton/stCollapseSidebarButton) 대응 */
[data-testid="stExpandSidebarButton"],[data-testid="stCollapseSidebarButton"]{{background:linear-gradient(135deg,var(--accent-dim),var(--accent))!important;border:none!important;border-radius:10px!important;min-width:40px!important;min-height:40px!important;box-shadow:0 0 14px rgba({T['accent_rgb']},0.45)!important;opacity:1!important;}}
[data-testid="stExpandSidebarButton"] span[data-testid="stIconMaterial"],[data-testid="stCollapseSidebarButton"] span[data-testid="stIconMaterial"]{{visibility:visible!important;display:inline-flex!important;width:auto!important;height:auto!important;overflow:visible!important;color:{T['bg_base']}!important;font-size:20px!important;}}
[data-testid="stExpandSidebarButton"]::after,[data-testid="stCollapseSidebarButton"]::after{{content:none!important;}}
/* ⋮ 설정 팝오버 버튼 (구 ⚙ 대체) */
[data-testid="stPopover"] button{{background:var(--bg-card)!important;border:1px solid var(--border-glow)!important;color:var(--accent)!important;border-radius:10px!important;font-weight:900!important;font-size:16px!important;box-shadow:none!important;}}
[data-testid="stPopoverBody"]{{background:var(--bg-card)!important;border:1px solid var(--border)!important;border-radius:12px!important;}}
span[data-testid="stIconMaterial"]{{font-family:"Material Symbols Rounded","Material Symbols Outlined","Material Symbols Sharp"!important;font-weight:400!important;letter-spacing:normal!important;}}
div[data-baseweb="popover"]>div>div{{background:var(--bg-card)!important;border:1px solid var(--border)!important;border-radius:12px!important;}}
[data-testid="stPopoverBody"] *{{color:var(--text-primary);}}
[data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] p{{color:var(--text-muted)!important;}}
div[role="tooltip"]{{background:var(--bg-card)!important;border:1px solid var(--border)!important;}}
div[role="tooltip"] *{{color:var(--text-primary)!important;background:transparent!important;}}
/* 테마 전환 시 부드러운 트랜지션 */
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{{transition:background-color 0.3s ease,color 0.3s ease;}}
.kpi-card,.result-panel,.fraud-type-card,.alert-box,.hypo-card{{transition:all 0.3s ease;}}
</style>"""
if not IS_NEW_UI:
    st.markdown(_css_components, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# ✨ 신 UI CSS — Instrument Console 디자인 시스템
#   원칙: 글로우 제거 · 헤어라인 보더 · 좌측 컬러 스파인(시그니처) ·
#         타이포 위계 정돈(과도한 uppercase/자간 축소) · 부드러운 엘리베이션
# ══════════════════════════════════════════════════════════
_css_new = f"""<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {{--bg-base:{T['bg_base']};--bg-surface:{T['bg_surface']};--bg-card:{T['bg_card']};--bg-card-hover:{T['bg_card_hover']};--border:rgba({T['accent_rgb']},0.14);--border-strong:rgba({T['accent_rgb']},0.30);--border-hair:{'rgba(148,163,184,0.14)' if _IS_DARK_BG else 'rgba(16,24,40,0.10)'};--accent:{T['accent']};--accent-dim:{T['accent_dim']};--red:{T['red']};--red-dim:{T['red_dim']};--amber:{T['amber']};--green:{T['green']};--blue:{T['blue']};--purple:{T['purple']};--text-primary:{T['text_primary']};--text-secondary:{T['text_secondary']};--text-muted:{T['text_muted']};--font-body:'Inter',sans-serif;--font-mono:'JetBrains Mono',monospace;--radius:12px;--radius-lg:16px;--shadow-1:0 1px 2px rgba(8,12,24,0.18);--shadow-2:0 4px 14px rgba(8,12,24,0.22);--shadow-accent:0 6px 22px rgba({T['accent_rgb']},0.30);}}
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{{background:radial-gradient(1100px 520px at 85% -12%,rgba({T['accent_rgb']},{'0.07' if _IS_DARK_BG else '0.05'}),transparent 60%),radial-gradient(820px 460px at -8% 108%,rgba({T['accent_rgb']},{'0.05' if _IS_DARK_BG else '0.035'}),transparent 55%),var(--bg-base)!important;background-attachment:fixed!important;font-family:var(--font-body)!important;color:var(--text-primary)!important;}}
[data-testid="stHeader"]{{background:transparent!important;}}
.main .block-container{{padding:1.2rem 3rem 2.5rem!important;max-width:1440px!important;}}
::selection{{background:rgba({T['accent_rgb']},0.30);color:var(--text-primary);}}
:focus-visible{{outline:2px solid var(--accent)!important;outline-offset:2px;border-radius:4px;}}
[data-testid="stDataFrame"] tr:hover td{{background:var(--bg-card-hover)!important;transition:background .12s;}}
[data-testid="stSidebar"]{{background:var(--bg-surface)!important;border-right:1px solid var(--border-hair)!important;}}
[data-testid="stSidebar"] *{{font-family:var(--font-body)!important;color:var(--text-primary)!important;}}
/* ── 사이드바 확장/축소 버튼 — 항상 또렷하게 (신 UI: 고스트 스퀘어) ── */
[data-testid="stExpandSidebarButton"],[data-testid="stCollapseSidebarButton"],[data-testid="stSidebarCollapsedControl"] button{{background:var(--bg-card)!important;border:1px solid var(--border-strong)!important;border-radius:10px!important;min-width:38px!important;min-height:38px!important;box-shadow:var(--shadow-1)!important;opacity:1!important;transition:border-color .15s!important;}}
[data-testid="stExpandSidebarButton"]:hover,[data-testid="stCollapseSidebarButton"]:hover{{border-color:var(--accent)!important;}}
[data-testid="stExpandSidebarButton"] span[data-testid="stIconMaterial"],[data-testid="stCollapseSidebarButton"] span[data-testid="stIconMaterial"],[data-testid="stSidebarCollapsedControl"] span[data-testid="stIconMaterial"]{{visibility:visible!important;display:inline-flex!important;width:auto!important;height:auto!important;color:var(--accent)!important;font-size:20px!important;}}
/* ── 버튼 ── */
.stButton>button{{background:linear-gradient(135deg,var(--accent),var(--accent-dim))!important;color:{'#0b0f17' if _IS_DARK_BG else '#ffffff'}!important;border:none!important;border-radius:10px!important;font-weight:600!important;font-family:var(--font-body)!important;font-size:13px!important;padding:8px 18px!important;box-shadow:var(--shadow-1)!important;transition:filter .15s, transform .15s, box-shadow .2s!important;letter-spacing:0!important;}}
.stButton>button:hover{{filter:brightness(1.08)!important;transform:translateY(-1px)!important;box-shadow:var(--shadow-accent)!important;}}
.stButton>button:active{{transform:translateY(0) scale(0.98)!important;box-shadow:var(--shadow-1)!important;}}
.stButton>button[kind="secondary"],.stButton button[data-testid="stBaseButton-secondary"]{{background:var(--bg-card)!important;border:1px solid var(--border-hair)!important;color:var(--text-secondary)!important;box-shadow:none!important;}}
.stButton>button[kind="secondary"]:hover,.stButton button[data-testid="stBaseButton-secondary"]:hover{{border-color:var(--accent)!important;color:var(--accent)!important;}}
[data-testid="stPopover"] button{{background:var(--bg-card)!important;border:1px solid var(--border-hair)!important;color:var(--text-secondary)!important;border-radius:10px!important;font-weight:800!important;font-size:16px!important;box-shadow:none!important;}}
[data-testid="stPopover"] button:hover{{border-color:var(--accent)!important;color:var(--accent)!important;}}
[data-testid="stPopoverBody"]{{background:var(--bg-card)!important;border:1px solid var(--border-hair)!important;border-radius:14px!important;box-shadow:var(--shadow-2)!important;}}
/* ── 입력 위젯 ── */
[data-baseweb="select"]>div,[data-baseweb="input"]>div{{background:var(--bg-card)!important;border-color:var(--border-hair)!important;border-radius:10px!important;color:var(--text-primary)!important;}}
[data-baseweb="select"]>div:focus-within,[data-baseweb="input"]>div:focus-within{{border-color:var(--accent)!important;box-shadow:0 0 0 3px rgba({T['accent_rgb']},0.14)!important;}}
[data-testid="stTextInput"] input{{background:var(--bg-card)!important;color:var(--text-primary)!important;font-family:var(--font-mono)!important;font-size:13px!important;}}
/* 🐛 FIX(v9.1): 라이트(light/ivory) 테마 입력 글자 가독성 — Streamlit 네이티브 다크 테마가
   입력 글자를 흰색으로 칠해 흰 카드 배경과 겹치던 문제. 모든 입력 요소를 테마 텍스트 색으로
   강제 + 캐럿(accent)·플레이스홀더(muted)·크롬 자동완성 배경까지 통일 */
[data-testid="stNumberInput"] input,[data-testid="stTextArea"] textarea,[data-baseweb="textarea"] textarea,[data-baseweb="select"] input,[data-testid="stDateInput"] input,[data-testid="stTimeInput"] input{{background:var(--bg-card)!important;color:var(--text-primary)!important;}}
.stApp input,.stApp textarea{{color:var(--text-primary)!important;-webkit-text-fill-color:var(--text-primary)!important;caret-color:var(--accent)!important;}}
.stApp input::placeholder,.stApp textarea::placeholder{{color:var(--text-muted)!important;-webkit-text-fill-color:var(--text-muted)!important;opacity:1!important;}}
.stApp input:-webkit-autofill,.stApp input:-webkit-autofill:hover,.stApp input:-webkit-autofill:focus{{-webkit-box-shadow:0 0 0 1000px var(--bg-card) inset!important;-webkit-text-fill-color:var(--text-primary)!important;}}
[data-testid="stNumberInput"] input{{font-family:var(--font-mono)!important;}}
[data-testid="stCheckbox"] label{{font-size:12.5px!important;color:var(--text-secondary)!important;}}
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"]{{background:var(--accent)!important;border-color:var(--accent)!important;box-shadow:var(--shadow-1)!important;}}
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stThumbValue"]{{color:var(--accent)!important;font-family:var(--font-mono)!important;}}
/* ── 탭 · 확장 · 데이터프레임 · 코드 ── */
[data-testid="stTabs"] [data-baseweb="tab-list"]{{background:var(--bg-surface)!important;border-radius:12px!important;padding:4px!important;gap:2px!important;border:1px solid var(--border-hair)!important;}}
[data-testid="stTabs"] [data-baseweb="tab"]{{background:transparent!important;color:var(--text-secondary)!important;border-radius:9px!important;font-size:13px!important;font-weight:500!important;padding:6px 16px!important;}}
[data-testid="stTabs"] [aria-selected="true"]{{background:var(--bg-card)!important;color:var(--accent)!important;box-shadow:inset 0 -2px 0 var(--accent),var(--shadow-1)!important;font-weight:600!important;}}
[data-testid="stExpander"]{{background:var(--bg-card)!important;border:1px solid var(--border-hair)!important;border-radius:12px!important;}}
[data-testid="stExpander"] summary{{color:var(--text-primary)!important;font-weight:600!important;}}
[data-testid="stDataFrame"]{{border:1px solid var(--border-hair)!important;border-radius:12px!important;overflow:hidden!important;}}
[data-testid="stDataFrame"] th{{background:var(--bg-surface)!important;color:var(--text-secondary)!important;font-family:var(--font-mono)!important;font-size:11px!important;}}
[data-testid="stDataFrame"] td{{background:var(--bg-card)!important;color:var(--text-primary)!important;font-family:var(--font-mono)!important;font-size:12px!important;}}
[data-testid="stCode"]{{background:var(--bg-surface)!important;border:1px solid var(--border-hair)!important;border-radius:10px!important;font-family:var(--font-mono)!important;font-size:12px!important;}}
hr{{border-color:var(--border-hair)!important;margin:1.4rem 0!important;}}
::-webkit-scrollbar{{width:6px;height:6px;}}
::-webkit-scrollbar-track{{background:transparent;}}
::-webkit-scrollbar-thumb{{background:linear-gradient(180deg,var(--border-strong),rgba({T['accent_rgb']},0.38));border-radius:4px;}}
::-webkit-scrollbar-thumb:hover{{background:var(--accent);}}
/* ── 마이크로 모션: 카드 페이드인 (접근성: 모션 축소 설정 존중) ── */
@keyframes fdsFade{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
@keyframes fdsPulse{{0%,100%{{opacity:1}}50%{{opacity:0.6}}}}
@keyframes fdsGlow{{0%{{box-shadow:0 0 5px rgba({T['accent_rgb']},0.2)}}50%{{box-shadow:0 0 20px rgba({T['accent_rgb']},0.4)}}100%{{box-shadow:0 0 5px rgba({T['accent_rgb']},0.2)}}}}
@keyframes fdsSlideIn{{from{{opacity:0;transform:translateX(-8px)}}to{{opacity:1;transform:none}}}}
.kpi-card,.result-panel,.hypo-card,.fraud-type-card{{animation:fdsFade .35s ease both;}}
.kpi-card:nth-child(2){{animation-delay:.06s}}.kpi-card:nth-child(3){{animation-delay:.12s}}.kpi-card:nth-child(4){{animation-delay:.18s}}.kpi-card:nth-child(5){{animation-delay:.24s}}
.kpi-card.anomaly{{animation:fdsGlow 2s ease-in-out infinite;}}
.alert-box{{animation:fdsSlideIn .3s ease both;}}
@media (prefers-reduced-motion: reduce){{.kpi-card,.result-panel,.hypo-card,.fraud-type-card,.alert-box{{animation:none;}}}}
/* ── 시그니처: 좌측 컬러 스파인 카드 ── */
.kpi-card{{background:var(--bg-card);border:1px solid var(--border-hair);border-left:3px solid var(--kpi-accent,var(--accent));border-radius:var(--radius);padding:18px 20px;position:relative;overflow:hidden;box-shadow:var(--shadow-1);transition:box-shadow .2s,transform .2s,border-color .2s;}}
.kpi-card:hover{{box-shadow:var(--shadow-2),0 0 0 1px rgba({T['accent_rgb']},0.10);transform:translateY(-2px);}}
.kpi-card::before{{content:none;}}
.kpi-card::after{{content:'';position:absolute;top:-45%;right:-18%;width:58%;height:130%;background:radial-gradient(closest-side,rgba({T['accent_rgb']},{'0.09' if _IS_DARK_BG else '0.06'}),transparent 72%);pointer-events:none;}}
.kpi-label{{color:var(--text-muted);font-size:11px;font-weight:600;letter-spacing:0.03em;margin:0 0 6px;}}
.kpi-value{{color:var(--text-primary);font-size:26px;font-weight:700;font-family:var(--font-mono);margin:0;line-height:1.15;font-variant-numeric:tabular-nums;}}
.kpi-delta{{color:var(--text-muted);font-size:12px;margin:5px 0 0;font-family:var(--font-mono);}}
.kpi-icon{{position:absolute;top:16px;right:16px;font-size:18px;opacity:0.45;filter:grayscale(0.3);}}
/* ── 섹션 헤더: 좌측 틱 + 차분한 라벨 ── */
.section-header{{display:flex;align-items:center;gap:10px;margin:2.2rem 0 1rem;}}
.section-header::before{{content:'';width:4px;height:16px;border-radius:2px;background:linear-gradient(180deg,var(--accent),var(--accent-dim));box-shadow:0 0 8px rgba({T['accent_rgb']},0.45);}}
.section-header-line{{flex:1;height:1px;background:linear-gradient(90deg,var(--border-strong),var(--border-hair) 55%,transparent);}}
.section-title{{color:var(--text-primary);font-size:15px;font-weight:700;letter-spacing:0;text-transform:none;white-space:nowrap;}}
.section-badge{{background:var(--bg-surface);color:var(--text-muted);border:1px solid var(--border-hair);border-radius:6px;font-size:10px;font-weight:600;padding:2px 8px;letter-spacing:0.04em;font-family:var(--font-mono);}}
/* ── 뱃지 · 태그 ── */
.badge-danger{{display:inline-block;background:rgba({int(T['red'][1:3],16)},{int(T['red'][3:5],16)},{int(T['red'][5:7],16)},0.12);color:var(--red);border:1px solid rgba({int(T['red'][1:3],16)},{int(T['red'][3:5],16)},{int(T['red'][5:7],16)},0.35);border-radius:7px;padding:3px 10px;font-size:12px;font-weight:700;}}
.badge-safe{{display:inline-block;background:rgba({int(T['green'][1:3],16)},{int(T['green'][3:5],16)},{int(T['green'][5:7],16)},0.12);color:var(--green);border:1px solid rgba({int(T['green'][1:3],16)},{int(T['green'][3:5],16)},{int(T['green'][5:7],16)},0.35);border-radius:7px;padding:3px 10px;font-size:12px;font-weight:700;}}
.badge-warn{{display:inline-block;background:rgba({int(T['amber'][1:3],16)},{int(T['amber'][3:5],16)},{int(T['amber'][5:7],16)},0.12);color:var(--amber);border:1px solid rgba({int(T['amber'][1:3],16)},{int(T['amber'][3:5],16)},{int(T['amber'][5:7],16)},0.35);border-radius:7px;padding:3px 10px;font-size:12px;font-weight:700;}}
.feature-tag{{display:inline-block;background:var(--bg-surface);border:1px solid var(--border-hair);border-radius:7px;padding:4px 10px;font-size:11.5px;font-family:var(--font-mono);color:var(--text-secondary);margin:2px;}}
.feature-tag.danger{{border-color:var(--red);color:var(--red);background:transparent;}}
.feature-tag.safe{{border-color:var(--green);color:var(--green);background:transparent;}}
.tag-pass{{background:transparent;color:var(--green);border:1px solid var(--green);border-radius:6px;padding:2px 9px;font-size:11px;font-weight:700;font-family:var(--font-mono);}}
.tag-fail{{background:transparent;color:var(--red);border:1px solid var(--red);border-radius:6px;padding:2px 9px;font-size:11px;font-weight:700;font-family:var(--font-mono);}}
/* ── 패널 · 알림 ── */
.result-panel{{background:var(--bg-card);border:1px solid var(--border-hair);border-radius:var(--radius-lg);padding:22px 26px;margin:1rem 0;box-shadow:var(--shadow-1);}}
.result-panel.anomaly{{border-left:4px solid var(--red);}}
.result-panel.normal{{border-left:4px solid var(--green);}}
.alert-box{{border-radius:10px;padding:13px 16px;font-size:13.5px;line-height:1.65;margin:8px 0;border:1px solid var(--border-hair);border-left:3px solid;background:var(--bg-card);}}
.alert-info{{border-left-color:var(--blue);color:var(--text-secondary);background:linear-gradient(90deg,rgba({_BLU_RGB},0.07),var(--bg-card) 45%);}}
.alert-warn{{border-left-color:var(--amber);color:var(--text-secondary);background:linear-gradient(90deg,rgba({_AMB_RGB},0.08),var(--bg-card) 45%);}}
.alert-error{{border-left-color:var(--red);color:var(--red);background:linear-gradient(90deg,rgba({_RED_RGB},0.09),var(--bg-card) 45%);}}
.alert-ok{{border-left-color:var(--green);color:var(--text-secondary);background:linear-gradient(90deg,rgba({_GRN_RGB},0.07),var(--bg-card) 45%);}}
/* ── 가설 · 유형 카드 · 게이지 · 확률바 ── */
.hypo-card{{background:var(--bg-card);border:1px solid var(--border-hair);border-left:3px solid var(--accent);border-radius:var(--radius);padding:14px 16px;margin-bottom:8px;transition:box-shadow .15s;}}
.hypo-card:hover{{box-shadow:var(--shadow-1);}}
.hypo-code{{font-family:var(--font-mono);font-size:11px;font-weight:700;color:var(--accent);}}
.hypo-text{{font-size:13.5px;color:var(--text-secondary);margin:5px 0 0;line-height:1.55;}}
.fraud-type-card{{background:var(--bg-card);border:1px solid var(--border-hair);border-radius:var(--radius);padding:14px 18px;margin:6px 0;}}
.gauge-wrap{{text-align:center;padding:8px 0;}}
.gauge-label{{font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-secondary);font-weight:700;}}
.prob-bar-wrap{{margin:3px 0;}}
.prob-bar-label{{display:flex;justify-content:space-between;font-size:11.5px;font-family:var(--font-mono);color:var(--text-secondary);margin-bottom:3px;}}
.prob-bar-bg{{background:var(--bg-surface);border-radius:3px;height:6px;overflow:hidden;}}
.prob-bar-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--accent-dim),var(--accent));box-shadow:0 0 10px rgba({T['accent_rgb']},0.30);transition:width .6s cubic-bezier(.22,1,.36,1);}}
.prob-bar-fill.danger{{background:linear-gradient(90deg,var(--red-dim),var(--red));box-shadow:0 0 10px rgba({_RED_RGB},0.35);}}
/* ── Streamlit 네이티브 위젯 강제 테마 (Streamlit 라이트/다크 설정과의 충돌 방지) ── */
h1,h2,h3,h4,h5,h6{{color:var(--text-primary)!important;}}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li,[data-testid="stMarkdownContainer"] span{{color:inherit;}}
[data-testid="stWidgetLabel"] p,[data-testid="stWidgetLabel"] label{{color:var(--text-secondary)!important;font-size:12px!important;}}
[data-testid="stCaptionContainer"] p{{color:var(--text-muted)!important;}}
[data-testid="stRadio"] label p{{color:var(--text-primary)!important;font-size:13px!important;}}
div[data-baseweb="popover"] ul,ul[role="listbox"]{{background:var(--bg-card)!important;border:1px solid var(--border-hair)!important;border-radius:10px!important;}}
ul[role="listbox"] li,[role="option"]{{color:var(--text-primary)!important;background:var(--bg-card)!important;font-family:var(--font-body)!important;}}
[role="option"]:hover{{background:var(--bg-card-hover)!important;}}
li[aria-selected="true"][role="option"]{{background:var(--bg-card-hover)!important;color:var(--accent)!important;}}
[data-baseweb="select"] div,[data-baseweb="select"] span{{color:var(--text-primary)!important;}}
[data-baseweb="checkbox"]>div{{border-color:var(--border-strong)!important;}}
[data-testid="stTooltipContent"],div[data-baseweb="tooltip"]{{background:var(--bg-card)!important;color:var(--text-primary)!important;border:1px solid var(--border-hair)!important;}}
[data-testid="stNumberInput"] button{{background:var(--bg-surface)!important;color:var(--text-secondary)!important;border-color:var(--border-hair)!important;}}
[data-testid="stToast"]{{background:var(--bg-card)!important;color:var(--text-primary)!important;border:1px solid var(--border-hair)!important;}}
/* 🐛 FIX: 사이드바 폰트 강제(*)가 Material 아이콘 리가처를 깨서 "_arrow..." 원문 노출 → 아이콘 폰트 복원 */
span[data-testid="stIconMaterial"]{{font-family:"Material Symbols Rounded","Material Symbols Outlined","Material Symbols Sharp"!important;font-weight:400!important;letter-spacing:normal!important;}}
/* 🐛 FIX: 팝오버·툴팁 등 포털 요소가 Streamlit 네이티브 테마(다크)를 따라 라이트 테마에서 판독 불가
   → baseweb 포털 구조까지 직접 타겟팅해 앱 테마 강제 */
div[data-baseweb="popover"]>div>div,[data-testid="stPopoverBody"]{{background:var(--bg-card)!important;border:1px solid var(--border-hair)!important;border-radius:14px!important;}}
[data-testid="stPopoverBody"] *,div[data-baseweb="popover"] [data-testid="stMarkdownContainer"] *{{color:var(--text-primary);}}
[data-testid="stPopoverBody"] [data-testid="stWidgetLabel"] p{{color:var(--text-secondary)!important;}}
[data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] p{{color:var(--text-muted)!important;}}
[data-testid="stPopoverBody"] [data-testid="stRadio"] label p{{color:var(--text-primary)!important;}}
[data-baseweb="radio"]>div:first-child{{border-color:var(--border-strong)!important;background:var(--bg-surface)!important;}}
div[role="tooltip"]{{background:var(--bg-card)!important;border:1px solid var(--border-hair)!important;border-radius:10px!important;}}
div[role="tooltip"] *{{color:var(--text-primary)!important;background:transparent!important;}}
</style>"""
if IS_NEW_UI:
    st.markdown(_css_new, unsafe_allow_html=True)
    # ⌨️ 세션 이동 단축키 (1~5) — 구 UI의 편의 기능을 미니멀하게 이식
    import streamlit.components.v1 as components
    components.html("""<script>
    (function(){
      const P = window.parent.document;
      if (P.__fdsNewKeys) return; P.__fdsNewKeys = 1;
      P.addEventListener('keydown', function(e){
        if (e.target.closest('input, textarea, [contenteditable="true"], select')) return;
        const n = parseInt(e.key, 10);
        if (!(n >= 1 && n <= 5)) return;
        const pat = /^(📋|📊|🔍|🧪|🚀)/;
        const btns = Array.from(P.querySelectorAll('.stButton button')).filter(b => pat.test(b.innerText));
        if (btns[n-1]) btns[n-1].click();
      });
    })();
    </script>""", height=0, scrolling=False)

# ── ✨ v7 DESIGN: 공용 CSS — 페이지 히어로 + 푸터 (신·구 UI 공통 주입) ──
_css_shared = f"""<style>
.page-hero{{margin:2px 0 6px;animation:fdsFade .4s ease both;}}
.page-hero .hero-eyebrow{{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:10.5px;font-weight:700;letter-spacing:0.10em;color:var(--accent);background:rgba({T['accent_rgb']},0.09);border:1px solid rgba({T['accent_rgb']},0.24);border-radius:999px;padding:3px 11px;margin-bottom:10px;}}
.page-hero .hero-eyebrow::before{{content:'';width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 6px rgba({T['accent_rgb']},0.7);}}
.page-hero h1{{font-size:31px;font-weight:800;letter-spacing:-0.02em;margin:0;color:var(--text-primary);line-height:1.15;}}
.page-hero .hero-accent{{background:linear-gradient(92deg,var(--hero-c,var(--accent)) 20%,color-mix(in srgb,var(--hero-c,var(--accent)) 55%,var(--text-primary)));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:var(--hero-c,var(--accent));}}
.page-hero .hero-sub{{color:var(--text-muted);font-size:13px;margin:7px 0 0;letter-spacing:0.02em;}}
.fds-footer{{text-align:center;padding:18px 0 10px;margin-top:20px;position:relative;}}
.fds-footer::before{{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:min(520px,80%);height:1px;background:linear-gradient(90deg,transparent,rgba({T['accent_rgb']},0.40),transparent);}}
.fds-footer .f-line{{display:inline-flex;align-items:center;gap:10px;color:var(--text-muted);font-size:10.5px;letter-spacing:0.05em;}}
.fds-footer .f-chip{{font-family:var(--font-mono);font-weight:700;color:var(--accent);background:rgba({T['accent_rgb']},0.10);border:1px solid rgba({T['accent_rgb']},0.25);border-radius:6px;padding:1px 7px;}}
.fds-footer .f-dot{{width:3px;height:3px;border-radius:50%;background:var(--text-muted);opacity:0.6;}}
/* ── ✨ v7: 번호형 세션 진행 인디케이터 (신·구 UI 공용) ── */
.session-progress{{display:flex;gap:6px;justify-content:center;padding:10px 0;margin-bottom:6px;}}
.session-dot{{width:9px;height:9px;border-radius:99px;background:var(--border-strong,var(--border-glow));transition:all .35s cubic-bezier(.22,1,.36,1);display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:8.5px;font-weight:700;letter-spacing:0.06em;color:transparent;overflow:hidden;}}
.session-dot.active{{background:linear-gradient(90deg,var(--accent),var(--accent-dim));box-shadow:0 0 10px rgba({T['accent_rgb']},0.55);width:40px;color:{'#0b0f17' if _IS_DARK_BG else '#ffffff'};}}
.session-dot.done{{background:var(--green);opacity:0.55;}}
@media (prefers-reduced-motion: reduce){{.session-dot{{transition:none;}}}}
/* ── ✨ v7: 세션5 판정 히어로 배너 ── */
@keyframes vhPulse{{0%,100%{{box-shadow:0 0 14px rgba({_RED_RGB},0.30);}}50%{{box-shadow:0 0 26px rgba({_RED_RGB},0.55);}}}}
.verdict-hero{{display:flex;align-items:center;justify-content:space-between;gap:18px;border-radius:16px;padding:20px 26px;margin:10px 0 14px;border:1px solid;position:relative;overflow:hidden;}}
.verdict-hero::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;}}
.verdict-hero.anomaly{{border-color:rgba({_RED_RGB},0.45);background:linear-gradient(100deg,rgba({_RED_RGB},0.13),rgba({_RED_RGB},0.04) 55%,transparent);}}
.verdict-hero.anomaly::before{{background:linear-gradient(90deg,var(--red),transparent);}}
.verdict-hero.normal{{border-color:rgba({_GRN_RGB},0.40);background:linear-gradient(100deg,rgba({_GRN_RGB},0.11),rgba({_GRN_RGB},0.03) 55%,transparent);}}
.verdict-hero.normal::before{{background:linear-gradient(90deg,var(--green),transparent);}}
.verdict-hero .vh-icon{{width:46px;height:46px;min-width:46px;border-radius:13px;display:flex;align-items:center;justify-content:center;font-size:22px;}}
.verdict-hero.anomaly .vh-icon{{background:rgba({_RED_RGB},0.15);border:1px solid rgba({_RED_RGB},0.40);animation:vhPulse 2s ease-in-out infinite;}}
.verdict-hero.normal .vh-icon{{background:rgba({_GRN_RGB},0.12);border:1px solid rgba({_GRN_RGB},0.35);}}
.verdict-hero .vh-title{{font-size:21px;font-weight:800;letter-spacing:-0.01em;line-height:1.15;}}
.verdict-hero .vh-meta{{font-size:10.5px;color:var(--text-muted);font-family:var(--font-mono);margin-top:4px;letter-spacing:0.02em;}}
.verdict-hero .vh-score{{font-family:var(--font-mono);font-size:30px;font-weight:700;text-align:right;line-height:1;font-variant-numeric:tabular-nums;}}
@media (prefers-reduced-motion: reduce){{.verdict-hero.anomaly .vh-icon{{animation:none;}}}}
@media (max-width:760px){{.verdict-hero{{flex-direction:column;align-items:flex-start;}}.verdict-hero .vh-score{{text-align:left;}}}}
@media (prefers-reduced-motion: reduce){{.page-hero{{animation:none;}}}}
</style>"""
st.markdown(_css_shared, unsafe_allow_html=True)

# ── ✨ v9.2: 🗜 컴팩트 오버뷰 (신 UI 전용) — 세션 1개가 스크롤 없이 한 화면에 ──
#   설계 원칙(v9.1 zoom 방식 폐기):
#     · zoom은 리플로우가 깨지고 가로 스크롤을 유발 → 실제 높이/간격/배치 축소로 대체
#     · 차트 높이를 _ch()/_hc()로 절반 이하로, <br> 스페이서는 cbr()로 컴팩트 시 제거
#     · 2차 콘텐츠(가설·유형사전·상세표 등)는 csec()로 접이식 전환 → 기본 화면은 핵심만
CV = IS_NEW_UI and bool(st.session_state.get('compact_view', False))

# ✨ v9.3: 컴팩트 차트 높이 추가 축소 배율 — 좌우 2단 배치와 병행해 '무스크롤'을 달성.
#   좌우로 나란히 놓으면 한 행이 곧 한 차트 높이라, 여기에 배율까지 곱해 세로 점유를 더 줄인다.
_CV_H = 0.86
_CV_H_FLOOR = 148   # 너무 납작해 읽기 힘든 것 방지 하한선

def _ch(normal, compact):
    """명시 높이 차트용 — 컴팩트면 compact×배율(하한 적용), 아니면 normal(기존 동작 보존)."""
    return max(_CV_H_FLOOR, int(compact * _CV_H)) if CV else normal

def _hc(compact_h):
    """무명 높이(Plotly 기본 ~450px) 차트용 — 컴팩트일 때만 height를 주입.
    normal에서는 빈 dict라 기존 자동 높이를 그대로 유지(외형 변화 0)."""
    return {'height': max(_CV_H_FLOOR, int(compact_h * _CV_H))} if CV else {}

def cbr(n=1):
    """수직 스페이서 — 컴팩트에서는 출력하지 않아 세로 공간을 회수."""
    if not CV:
        st.markdown("<br>" * n, unsafe_allow_html=True)

import contextlib as _ctxlib
def csec(title, badge=None, expanded=False):
    """섹션 컨테이너 — normal은 기존 section_header + 인라인, 컴팩트는 접이식(collapsed)으로
    재배치해 2차 콘텐츠를 숨기되 접근 가능하게 유지한다(삭제가 아니라 재배치)."""
    if CV:
        return st.expander(f"{title}", expanded=expanded)
    section_header(title, badge)
    return _ctxlib.nullcontext()

def crow(specs, gap="small", valign="top"):
    """✨ v9.3: 컴팩트 오버뷰의 핵심 프리미티브 — '가로 공간을 쓰게' 한다.
      · 컴팩트: st.columns(specs)로 좌우 분할 → 두 콘텐츠가 한 행에 들어가 세로를 절반으로.
      · 일반  : 각 슬롯을 풀폭 st.container()로 반환 → 기존처럼 위→아래 순차 배치(외형 변화 0).
    사용법:  L, R = crow([1, 1.2]); with L: ...; with R: ...
    specs 는 정수(균등 분할) 또는 가중치 리스트."""
    if isinstance(specs, int):
        n, weights = specs, [1] * specs
    else:
        weights = list(specs); n = len(weights)
    if CV:
        try:
            return st.columns(weights, gap=gap, vertical_alignment=valign)
        except TypeError:      # 구버전 Streamlit 호환 (gap/valign 미지원)
            return st.columns(weights)
    return [st.container() for _ in range(n)]

def csec_row(items):
    """✨ v9.3: 접이식 2차 섹션들을 컴팩트에서 '가로로' 늘어놓기 위한 헬퍼.
    items = [(title, badge), ...]. 반환된 (컨텍스트, 슬롯) 순서대로 with 사용.
    일반 모드에서는 section_header + 풀폭이라 기존과 동일하게 세로로 쌓인다."""
    slots = crow(len(items)) if CV else [None] * len(items)
    out = []
    for (ttl, bdg), slot in zip(items, slots):
        if CV:
            out.append(slot.expander(ttl, expanded=False))
        else:
            section_header(ttl, bdg); out.append(_ctxlib.nullcontext())
    return out

if CV:
    st.markdown("""<style>
    /* 레이아웃 — v9.6/v9.8: 상단 패딩 최소화로 타이틀·탭을 더 위로 끌어올림(세로 공간 회수) */
    .main .block-container{padding:0.2rem 1.6rem 1rem!important;max-width:100%!important;}
    [data-testid="stVerticalBlock"]{gap:0.65rem!important;}
    [data-testid="stHorizontalBlock"]{gap:0.7rem!important;}
    [data-testid="stElementContainer"]{margin-bottom:0!important;}
    /* Plotly 래퍼 자체 여백 제거 (차트 위아래 큰 공백의 주범) */
    [data-testid="stPlotlyChart"]{margin:0!important;}
    [data-testid="stPlotlyChart"]>div{margin:0 auto!important;}
    /* 히어로 — 부제/아이브로 숨기고 한 줄로 */
    .page-hero{margin:0 0 1px;} .page-hero h1{font-size:18px;line-height:1.1;}
    .page-hero .hero-sub,.page-hero .hero-eyebrow{display:none;}
    /* 섹션 헤더 — 얇게 */
    .section-header{margin:0.45rem 0 0.4rem;} .section-header::before{height:12px;}
    .section-title{font-size:12.5px;}
    /* KPI 카드 — 값+단위 한 줄(kpi-delta-inline), 카드 높이 축소 */
    .kpi-card{padding:11px 14px;} .kpi-label{margin:0 0 4px;font-size:10px;}
    .kpi-value{font-size:15px;line-height:1.3;}
    .kpi-value .kpi-delta-inline{font-size:10.5px;color:var(--text-muted);font-weight:400;font-family:var(--font-mono);margin-left:5px;white-space:normal;}
    .kpi-delta{margin:2px 0 0;font-size:10.5px;white-space:nowrap;} .kpi-icon{font-size:13px;top:9px;right:11px;}
    /* 패널/배너/알림 — 압축 */
    .result-panel{padding:11px 14px;margin:0.35rem 0;}
    .verdict-hero{padding:9px 16px;margin:3px 0 5px;}
    .verdict-hero .vh-icon{width:34px;height:34px;min-width:34px;font-size:17px;}
    .verdict-hero .vh-title{font-size:15px;} .verdict-hero .vh-score{font-size:20px;}
    .verdict-hero .vh-meta{font-size:9.5px;margin-top:2px;}
    .alert-box{padding:7px 11px;font-size:12px;margin:3px 0;line-height:1.45;}
    .alert-box.alert-warn{display:none!important;}  /* v9.5: 발표/시연 — 경고 배너 숨김(에러·맥락 info는 유지) */
    .hypo-card,.fraud-type-card{padding:8px 11px;margin-bottom:4px;}
    .hypo-text{font-size:12px;margin-top:3px;} .hypo-code{font-size:10px;}
    /* 위젯 — 촘촘하게 */
    [data-testid="stExpander"] summary{padding:5px 12px!important;font-size:12.5px!important;}
    [data-testid="stExpander"] [data-testid="stExpanderDetails"]{padding-top:4px!important;}
    [data-testid="stTabs"] [data-baseweb="tab"]{padding:3px 12px!important;font-size:12px!important;}
    [data-testid="stTabs"] [data-baseweb="tab-list"]{margin-bottom:2px!important;}
    [data-testid="stMetric"]{padding:2px 0!important;}
    [data-testid="stCaptionContainer"]{margin:0!important;}
    div[data-testid="stMarkdownContainer"] p{margin-bottom:0.2rem;}
    .stButton>button{padding:5px 14px!important;}
    hr{margin:0.4rem 0!important;}
    .fds-footer{display:none;}
    .session-progress{padding:0;margin:-2px 0 2px;transform:scale(0.9);transform-origin:left center;}
    /* 컴팩트 안내 핀 */
    .compact-pin{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-mono);
      font-size:9.5px;color:var(--text-muted);background:var(--bg-surface);
      border:1px solid var(--border-hair);border-radius:999px;padding:2px 9px;margin:0 0 2px;}
    /* ✨ v13 — Phase 2·3에서 추가된 요소 압축 (RAG 편집기 · 음성 패널 · 행별 판정) */
    /* 확장 패널(expander) — 헤더/본문 패딩 축소. 세션5에 편집기·음성·이력이 늘어 누적 효과 큼 */
    [data-testid="stExpander"]{margin:0 0 0.35rem!important;}
    [data-testid="stExpander"] summary{padding:0.35rem 0.7rem!important;font-size:12px!important;}
    [data-testid="stExpander"] summary p{font-size:12px!important;margin:0!important;}
    [data-testid="stExpander"] [data-testid="stExpanderDetails"]{padding:0.5rem 0.7rem 0.6rem!important;}
    /* 탭 — 프롬프트/RAG 편집기의 파일별 탭 줄 높이 절감 */
    [data-testid="stTabs"] [data-baseweb="tab-list"]{gap:0.2rem!important;}
    [data-testid="stTabs"] [data-baseweb="tab"]{padding:0.25rem 0.6rem!important;height:auto!important;}
    [data-testid="stTabs"] [data-baseweb="tab"] p{font-size:11.5px!important;}
    /* 텍스트 영역 — 편집기 기본 높이를 컴팩트에서 낮춤(스크롤은 살아있음) */
    [data-testid="stTextArea"] textarea{font-size:12px!important;line-height:1.45!important;}
    /* 음성 입력 위젯 — 기본 높이가 커서 챗 패널을 밀어냄 */
    [data-testid="stAudioInput"]{margin:0.2rem 0!important;}
    [data-testid="stAudioInput"] > div{min-height:38px!important;}
    /* 채팅 — 메시지 버블/입력창 여백 축소 */
    [data-testid="stChatMessage"]{padding:0.4rem 0.6rem!important;margin-bottom:0.3rem!important;}
    [data-testid="stChatMessage"] p{margin:0.15rem 0!important;font-size:12.5px!important;}
    [data-testid="stChatInput"]{margin-top:0.3rem!important;}
    /* 코드/리포트 블록 — 배치 '행별 판정'이 길어 세로를 많이 먹는다 → 최대 높이 + 스크롤 */
    [data-testid="stExpanderDetails"] pre{max-height:260px!important;overflow:auto!important;
        font-size:11px!important;line-height:1.4!important;}
    /* 캡션/구분선 — 누적 여백 회수 */
    [data-testid="stCaptionContainer"] p{font-size:10.5px!important;margin:0.1rem 0!important;}
    hr{margin:0.4rem 0!important;}
    /* 버튼 — 저장/초기화/재색인 등 3열 버튼이 많아졌으므로 높이 축소 */
    [data-testid="stButton"] button{padding:0.28rem 0.6rem!important;min-height:30px!important;font-size:11.5px!important;}
    /* 체크박스·토글 — 직접입력 12개 플래그 열의 세로 압축 */
    [data-testid="stCheckbox"]{margin-bottom:-2px!important;}
    [data-testid="stCheckbox"] p{font-size:11.5px!important;}

    /* ✨ v14 (요청 7) — "한 화면에 한 세션" 목표: 세로 점유 추가 회수 */
    /* 페이지 최상단 여백/진행 인디케이터 압축 */
    .main .block-container{padding-top:0.1rem!important;}
    .session-progress{margin:0 0 0.35rem!important;} .session-dot{width:22px;height:22px;font-size:9.5px;}
    /* 입력 위젯 전반 — 라벨/본체 높이 축소 (세션5 직접입력이 가장 큰 수혜) */
    [data-testid="stWidgetLabel"] p{font-size:11px!important;margin-bottom:2px!important;}
    [data-testid="stNumberInput"] input,[data-testid="stTextInput"] input{
        padding:0.22rem 0.5rem!important;font-size:12px!important;}
    [data-baseweb="select"]>div{min-height:32px!important;font-size:12px!important;}
    [data-testid="stSlider"]{padding-top:0!important;padding-bottom:0.2rem!important;}
    [data-testid="stFileUploader"] section{padding:0.5rem!important;}
    [data-testid="stFileUploader"] section>div{font-size:11px!important;}
    /* 데이터프레임 — 기본 400px대 높이가 스크롤 주범. 상한 + 헤더/셀 압축 */
    [data-testid="stDataFrame"]{max-height:300px!important;}
    [data-testid="stDataFrame"] [role="columnheader"]{font-size:10.5px!important;}
    [data-testid="stDataFrame"] [role="gridcell"]{font-size:11px!important;}
    /* 커스텀 HTML 표(세션4 PASS/FAIL 등) 셀 패딩 축소 */
    table td{padding:5px 9px!important;font-size:11px!important;}
    table th{padding:5px 9px!important;font-size:9.5px!important;}
    /* 알림/배너 — 반복 등장하므로 누적 효과가 큼 */
    .alert-box{padding:7px 12px!important;font-size:11.5px!important;margin:4px 0!important;}
    /* 세션5 결과 패널 — 확률 막대/유형 정보 압축 */
    .result-panel{padding:11px 14px!important;}
    .prob-row{margin-bottom:3px!important;} .prob-label{font-size:10.5px!important;}
    /* 사이드바 — 챗봇·음성·진단 패널이 늘어 스크롤이 길어졌다 */
    [data-testid="stSidebar"] .block-container{padding-top:0.4rem!important;}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:0.4rem!important;}
    /* 스페이서 <br> 완전 무력화 — cbr()이 아닌 인라인 <br>까지 회수 */
    [data-testid="stMarkdownContainer"]>br{display:none!important;}
    /* 탭 패널 상단 여백 */
    [data-testid="stTabs"] [data-baseweb="tab-panel"]{padding-top:0.35rem!important;}

    /* ✨ v18 — 세션2 지표 pills가 2줄로 접히며 위 차트를 밀어 올리던 문제 */
    [data-testid="stPills"]{margin:0!important;}
    [data-testid="stPills"] [data-baseweb="button-group"]{gap:2px!important;flex-wrap:nowrap!important;}
    [data-testid="stPills"] button{padding:1px 7px!important;min-height:24px!important;
        height:24px!important;white-space:nowrap!important;}
    [data-testid="stPills"] button p,[data-testid="stPills"] button div{
        font-size:10.5px!important;line-height:1.2!important;margin:0!important;}
    /* multiselect 폴백 경로(구 Streamlit)도 동일하게 압축 */
    .s2-pills-scope + [data-testid="stMultiSelect"] [data-baseweb="tag"]{
        height:20px!important;font-size:10px!important;}
    </style>""", unsafe_allow_html=True)

# ── CSS 블록 3: OS 다크/라이트 자동 감지 안내 ────────────
# NOTE: Streamlit은 자체 테마 시스템이 있어 prefers-color-scheme 직접 적용은 제한적
# 대신 사이드바에 OS 테마 감지 버튼을 제공 (아래 사이드바 섹션에서 구현)

# ══════════════════════════════════════════════════════════
# 상수
# ══════════════════════════════════════════════════════════
# 🌐 아래 5개 딕셔너리는 언어별 데이터(i18n_data.py)에서 현재 언어(LANG) 기준으로 해석됩니다.
#    내부 키(a~m, 컬럼명 등)는 언어와 무관하므로 이 딕셔너리를 사용하는 이하 코드는 수정이 필요 없습니다.
FRAUD_LABELS=FRAUD_LABELS_I18N[LANG]
FRAUD_SHORT=FRAUD_SHORT_I18N[LANG]
FRAUD_TYPE_DETAILS=FRAUD_TYPE_DETAILS_I18N[LANG]
CAT_OPTIONS={'Customer_Gender':['male','female'],'Customer_credit_rating':['A','B','C','D','E','S'],'Customer_loan_type':['a','b','c','d','e'],'Account_account_type':['a','b','c','d'],'Channel':['ATM','internet','mobile','Others'],'Operating_System':['Android','Linux','Others','Windows','iOS','macOS'],'Error_Code':['a','c'],'Type_General_Automatic':['automatic','general'],'Access_Medium':['a','b','c','d','e','f','g']}
BINARY_FLAGS=['Customer_rooting_jailbreak_indicator','Customer_VPN_Indicator','Customer_flag_terminal_malicious_behavior_1','Customer_flag_terminal_malicious_behavior_2','Customer_flag_terminal_malicious_behavior_3','Unused_terminal_status','Unused_account_status','Recipient_account_suspend_status','Account_release_suspention','Transaction_Failure_Status','Another_Person_Account','Flag_deposit_more_than_tenMillion']
# 접근 매체 코드 매핑 (실데이터 정의 기반)
ACCESS_MEDIUM_MAP=ACCESS_MEDIUM_MAP_I18N[LANG]
FLAG_LABELS=FLAG_LABELS_I18N[LANG]
# 위험 플래그 도움말 (직접 입력 온보딩용 — ? 호버 시 표시)
FLAG_HELP=FLAG_HELP_I18N[LANG]
MODEL_DIR=Path("models")
DATA_DIR=Path("data")
IS_DARK_T = _IS_DARK_BG   # ✨ v7.2: CSS 블록의 _IS_DARK_BG와 판정 로직 단일화 (중복 계산 제거)
GRID_COLOR = 'rgba(255,255,255,0.05)' if IS_DARK_T else 'rgba(16,24,40,0.09)'
ROW_BORDER = 'rgba(255,255,255,0.05)' if IS_DARK_T else 'rgba(16,24,40,0.08)'   # ✨ v7: 커스텀 테이블 행 구분선 (라이트 테마 대응)
PLOTLY_LAYOUT=dict(paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(family='Inter, sans-serif',color=T['text_secondary'],size=12),colorway=T['plotly_colors'],transition=dict(duration=400,easing='cubic-in-out'),hoverlabel=dict(bgcolor=T['bg_card'],bordercolor=T['accent'],font=dict(family='JetBrains Mono, monospace',size=11,color=T['text_primary'])),modebar=dict(bgcolor='rgba(0,0,0,0)',color=T['text_muted'],activecolor=T['accent']))  # ✨ v7: 툴팁+모드바 테마 통일
_M_DEFAULT=dict(l=10,r=10,t=40,b=10)
_M_COMPACT=dict(l=0,r=0,t=10,b=30)

# ── 헬퍼 ────────────────────────────────────────────────
def _mtime(p: Path):
    """캐시 무효화용 — 파일이 바뀌면 캐시 자동 갱신"""
    try: return p.stat().st_mtime
    except OSError: return None

@st.cache_data(show_spinner=False)
def _load_eval_result_cached(mt):   # 🔴 FIX(v10): _mt → mt (Streamlit은 _접두 인자를 캐시 키에서 제외)
    p=MODEL_DIR/"eval_result.json"
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

def load_eval_result():
    return _load_eval_result_cached(_mtime(MODEL_DIR/"eval_result.json"))

@st.cache_data(show_spinner=t("common.csv_loading_spinner"))
def _load_csv_cached(path_str, mt):   # 🔴 FIX(v10): _mt → mt (밑줄 인자는 해시 제외 → 파일 교체 미반영)
    p=Path(path_str)
    if not p.exists(): return None
    df=pd.read_csv(p)
    # ⚡ 저카디널리티 문자열 → category (메모리·집계 최적화). Fraud_Type은
    #   필터 후 value_counts 0건 팬텀 행 부작용이 있어 제외.
    for c in df.select_dtypes(include='object').columns:
        if c == 'Fraud_Type':
            continue
        try:
            if df[c].nunique(dropna=False) <= 50:
                df[c]=df[c].astype('category')
        except TypeError:
            pass
    return df

def load_train_df():
    p=DATA_DIR/"train.csv"
    return _load_csv_cached(str(p), _mtime(p))

def load_test_df(path):
    p=Path(path)
    return _load_csv_cached(str(p), _mtime(p))

# ── ✨ v6.5: TTS · 알람 · DB ──────────────────────────────
def _tts_player(text, key):
    """🔊 TTS 플레이어 — 브라우저 음성 자동 검색 + 드롭다운 선택 + 재생/정지"""
    lang = st.session_state.get("tts_lang", "ko")
    clean = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${").replace("</", "<\\/")[:3000]  # 🛡 FIX(v9): </script> 주입 차단
    st.components.v1.html(f"""
    <div id="tts_{key}" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
      <select id="voice_{key}" style="flex:1;min-width:140px;max-width:260px;padding:4px 6px;
        border-radius:6px;border:1px solid #444;background:#1a1a2e;color:#ccc;font-size:11px"></select>
      <button onclick="ttsPlay_{key}()" style="padding:4px 12px;border-radius:6px;border:1px solid #6c5ce7;
        background:#6c5ce722;color:#a29bfe;cursor:pointer;font-size:12px;white-space:nowrap">🔊 읽기</button>
      <button onclick="speechSynthesis.cancel()" style="padding:4px 8px;border-radius:6px;border:1px solid #555;
        background:transparent;color:#888;cursor:pointer;font-size:11px">⏹</button>
    </div>
    <script>
    (function() {{
      var sel = document.getElementById("voice_{key}");
      var lang = "{lang}";
      function loadVoices() {{
        var voices = speechSynthesis.getVoices();
        sel.innerHTML = "";
        var filtered = voices.filter(function(v) {{ return v.lang.startsWith(lang); }});
        if (filtered.length === 0) filtered = voices;
        filtered.forEach(function(v, i) {{
          var o = document.createElement("option");
          o.value = i; o.textContent = v.name + " (" + v.lang + ")";
          sel.appendChild(o);
        }});
        sel._voices = filtered;
      }}
      loadVoices();
      if (speechSynthesis.onvoiceschanged !== undefined) speechSynthesis.onvoiceschanged = loadVoices;
      window.ttsPlay_{key} = function() {{
        speechSynthesis.cancel();
        var u = new SpeechSynthesisUtterance(`{clean}`);
        var voices = sel._voices || speechSynthesis.getVoices();
        if (voices.length > 0 && sel.value !== "") u.voice = voices[parseInt(sel.value)];
        u.lang = lang; u.rate = 1.0; u.pitch = 1.0;
        speechSynthesis.speak(u);
      }};
    }})();
    </script>
    """, height=38)

def _play_alarm():
    if not st.session_state.get("alarm_on", False): return
    st.components.v1.html('<script>try{var c=new(window.AudioContext||window.webkitAudioContext)(),o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.frequency.value=880;o.type="square";g.gain.value=0.3;o.start();setTimeout(function(){o.stop()},300);setTimeout(function(){var o2=c.createOscillator();o2.connect(g);o2.frequency.value=1100;o2.type="square";o2.start();setTimeout(function(){o2.stop()},300)},400)}catch(e){}</script>', height=0)

def _save_detection_to_db(row, fraud_type, risk_score, is_anomaly):
    import sqlite3, json
    try:
        con = sqlite3.connect("fds_results.db")
        con.execute("CREATE TABLE IF NOT EXISTS detections (transaction_id TEXT PRIMARY KEY, fraud_type TEXT, risk_score REAL, is_anomaly INTEGER, model TEXT, threshold REAL, detected_at TEXT DEFAULT (datetime('now','localtime')), raw_json TEXT)")
        txn_id = str(row.get('ID') or row.get('transaction_id') or row.get('_idx') or '').strip()
        # 🛡 FIX(v9): 수동 입력 등 ID 없는 행이 전부 txn_id='' 한 행으로 업서트-덮어쓰기되던 버그
        if not txn_id or txn_id.lower() in ('nan', 'none'):
            txn_id = f"MANUAL_{time.strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
        con.execute("INSERT INTO detections VALUES (?,?,?,?,?,?,datetime('now','localtime'),?) ON CONFLICT(transaction_id) DO UPDATE SET fraud_type=excluded.fraud_type, risk_score=excluded.risk_score, is_anomaly=excluded.is_anomaly, model=excluded.model, threshold=excluded.threshold, detected_at=datetime('now','localtime'), raw_json=excluded.raw_json",
                    (txn_id, fraud_type, round(risk_score,6), int(is_anomaly), st.session_state.get('selected_model',''), threshold, json.dumps({k:str(v) for k,v in row.items() if not str(k).startswith('_')}, ensure_ascii=False)[:4000]))
        con.commit(); con.close()
    except Exception as e: log.warning(f"DB 적재 실패: {e}")

def _save_batch_to_db(batch_res):
    import sqlite3, json
    try:
        con = sqlite3.connect("fds_results.db")
        con.execute("CREATE TABLE IF NOT EXISTS detections (transaction_id TEXT PRIMARY KEY, fraud_type TEXT, risk_score REAL, is_anomaly INTEGER, model TEXT, threshold REAL, detected_at TEXT DEFAULT (datetime('now','localtime')), raw_json TEXT)")
        _bts = time.strftime('%H%M%S')
        for r in batch_res.rows_out:
            # 🛡 FIX(v9): batch_analyzer.rows_out의 키는 'txn_id'인데 'transaction_id'로 조회해
            #   항상 idx(0,1,2…)로 폴백 → 배치마다 PRIMARY KEY 충돌로 이전 기록 덮어쓰기
            txn_id = str(r.get('txn_id') or r.get('transaction_id') or '').strip()
            if not txn_id or txn_id.startswith('ROW_') or txn_id.lower() in ('nan', 'none'):
                txn_id = f"BATCH_{_bts}_{r.get('idx', '')}"
            con.execute("INSERT INTO detections VALUES (?,?,?,?,?,?,datetime('now','localtime'),?) ON CONFLICT(transaction_id) DO UPDATE SET fraud_type=excluded.fraud_type, risk_score=excluded.risk_score, is_anomaly=excluded.is_anomaly, model=excluded.model, threshold=excluded.threshold, detected_at=datetime('now','localtime'), raw_json=excluded.raw_json",
                        (txn_id, r.get('fraud_type',''), round(r.get('risk_score',0),6), int(r.get('is_anomaly',False)),
                         st.session_state.get('selected_model',''), float(threshold),  # 🛡 FIX(v9): model=''/threshold=0 하드코딩 → 실값
                         json.dumps({k:str(v) for k,v in r.items()}, ensure_ascii=False)[:4000]))
        con.commit(); con.close()
    except Exception as e: log.warning(f"배치 DB 적재 실패: {e}")


# ── ✨ v5: 미병합 i18n 대비 한국어 폴백 ─────────────────────
# ── 빌드 버전 스탬프 — 사이드바 하단·🩺 진단에 표시 ("교체했는데 그대로" 사고 3초 판별) ──
DASH_VERSION = "v9.0"

_V5_KO = {
 "ds.section":"데이터셋","ds.select_label":"평가 데이터셋 선택","ds.folder_label":"데이터 폴더",
 "ds.none_found":"⚠ 폴더에서 데이터셋을 찾지 못했습니다 (CSV/Parquet)",
 "ds.no_label_warn":"선택한 데이터셋에 라벨(Fraud_Type)이 없어 평가할 수 없습니다 — 예측 전용",
 "ds.loaded_info":"데이터셋 로드: {name} — {n:,}행 · {note}",
 "s2.mode_label":"평가 모드","s2.mode_static":"학습 시점 리포트 (eval_result.json)",
 "s2.mode_dynamic":"실시간 재평가 (선택 데이터셋 × 모델)",
 "s2.model_multi_label":"비교할 모델 (최대 3개)","s2.run_eval_button":"⚡ 평가 실행",
 "s2.eval_spinner":"선택 데이터셋으로 {n}개 모델 평가 중...",
 "s2.eval_size_note":"평가 표본: {n:,}건 (성능을 위해 최대 {max:,}건 샘플링)",
 "s2.eval_fail":"평가 실패: {e}","s2.no_model_loaded":"선택한 모델을 하나도 로드하지 못했습니다 — 각 오류 메시지를 확인하세요",
 "s2.cost_fn_unit":"미탐 1건 비용(원)","s2.cost_fp_unit":"오탐 1건 비용(원)",
 "s2.cost_optimal":"최적 임계값 {th} (총비용 최소)","s2.metric_pick":"표시 지표","s2.model_chart_title":"모델 성능 비교","s2.micro_label":"전체 µ(사기)","s2.micro_note":"📌 주 지표 µF1 = 사기 클래스(a~l) 한정 micro F1 (건수 가중 통합) · 참고: 13클래스 전체 micro F1은 정확도와 동일해 99% 정상 데이터에선 변별력이 없습니다","nav.leak_muted":"🔕 is_fraud 누출 경고 숨김 상태 — 사이드바 '경고 배너' 토글로 다시 켤 수 있어요","link.two_way":"↔ 사이드바와 양방향 연동 중 — 어느 쪽에서 바꿔도 함께 변경됩니다","s2.evaluator_stale":"⚠ pipeline/evaluator.py가 구버전입니다 — 표본→모집단 보정 없이 계산됩니다. 새 evaluator.py를 pipeline/에 배치하고 완전 재시작하세요","nav.leak_warn_toggle":"🚨 라벨 누출 경고 배너","nav.leak_warn_help":"세션 2·5의 is_fraud 누출 경고 배너를 표시합니다. 담당자 확인이 끝났다면 꺼서 소음을 줄이세요 — 꺼도 🩺 호환성 진단에는 항상 기록됩니다.","s2.cost_weight_note":"오탐 비용 모집단 보정 ×{w} 적용 (층화 표본)","s2.cm_error_hint":"🟥 붉은 셀 = 오탐/미탐 (대각선 밖 예측 오류)",
 "s5.batch_button":"📦 일괄 분석 ({n}건)","s5.batch_min_warn":"일괄 분석은 2건 이상일 때 사용할 수 있습니다",
 "s5.batch_spinner":"배치 분석 중... ({i}/{n})","s5.batch_result_title":"배치 분석 결과",
 "s5.batch_kpi_total":"전체 거래","s5.batch_kpi_anomaly":"이상 거래","s5.batch_kpi_avg":"평균 위험","s5.batch_kpi_max":"최고 위험",
 "s5.batch_summary_label":"탐지 요약","s5.batch_report_title":"🧾 배치 AI 분석 보고서",
 "s5.batch_table_title":"건별 판정 결과","s5.batch_llm_fallback_note":"⚠ LLM 미연결 — 집계 기반 폴백 보고서입니다",
 "s5.batch_send_slack":"📨 Slack 발송","s5.batch_send_email":"📧 Email 발송","s5.batch_clear":"🗑 배치 결과 지우기",
 "s5.batch_accuracy_note":"정답 보유 {n}건 중 유형 일치 {hit}건 ({pct:.1f}%)","s5.batch_download_csv":"⬇️ 결과 CSV",
 "s2.ratio_toggle":"비율(%)로 보기 — 실제 유형별 예측 분포","s3.ratio_toggle":"비율(%)로 보기",
 "s2.zero_f1_warn":"⚠ F1=0 유형: {types} — 모델이 해당 유형을 전혀 정탐하지 못했습니다 (혼동행렬의 해당 행 참조)",
 "s2.sample_cap_label":"표본 상한","s2.low_support_warn":"⚠ 표본 10건 미만 유형: {types} — 해당 유형 지표는 통계적으로 불안정합니다",
 "s2.absent_class_note":"ℹ 이 데이터셋에 없는 유형: {types} (지표 0으로 표시)",
 "s2.adapt_note_prefix":"자동 피처 매칭 적용",
 "s2.skipped_models":"⚠ 데이터셋과 피처 계열이 달라 평가에서 제외된 모델:<br>{models}",
 "s5.tab3_src_label":"데이터 소스","s5.tab3_src_csv":"📄 원본 CSV (train.csv)","s5.tab3_src_pq":"📦 전처리 완료 (Parquet)",
 "s5.batch_reroll":"재분석",
 "s5.batch_tab_overview":"📊 전체 결과","s5.batch_tab_report":"🧾 분석 보고서",
 "nav.compact_toggle":"🗜 한눈에 보기 (컴팩트)",
 "nav.compact_hint":"현재 세션의 모든 정보를 한 화면에 압축 배치합니다 (신 UI 전용 · 단축키 V)",
 "sb.dual_toggle":"📮 이중 임계값 발송",
 "sb.dual_help":"위험도 구간에 따라 발송 채널·메시지 톤을 이원화합니다. 1차(의심) 이상~2차 미만: Slack만 · 담당자 검토 요청 / 2차(확정) 이상: Slack+Email 동시 · 확정 통보",
 "sb.th1_label":"1차 임계값 — 의심 (Slack 검토요청)",
 "sb.th2_label":"2차 임계값 — 확정 (Slack+Email)",
 "sb.dual_swap_warn":"⚠ 2차 임계값이 1차보다 낮습니다 — 발송 판정 시 2차={t2:.2f}로 보정 적용",
 "sb.dual_rule_note":"위험도 &lt;{t1:.2f}: 발송 없음 · {t1:.2f}~{t2:.2f}: 🟡 Slack 검토요청 · ≥{t2:.2f}: 🔴 Slack+Email 확정통보",
 "s5.dual_active_note":"📮 이중 임계값 모드 활성 — 구간 설정은 좌측 사이드바",
 "notif.tier_review_head":"🟡 [의심 단계 · 추가 검토 요청]\n위험도 {r:.2f} — 1차 임계값({t1:.2f})을 초과했으나 2차 임계값 미만입니다.\n확정 판정 전 단계이므로 담당자의 추가 검토를 요청드립니다. 원거래 내역과 아래 분석 내용을 대조해 오탐 여부를 확인해 주세요.",
 "notif.tier_confirm_head":"🔴 [확정 단계 · 즉시 대응 요망]\n위험도 {r:.2f} — 2차 임계값({t2:.2f}) 이상으로 이상거래로 판단됩니다.\nSlack·Email 동시 통보되었습니다. 계정 보호 조치 및 거래 차단 검토를 즉시 진행해 주세요.",
 "notif.subject_review":"[FDS 검토요청] {ft} 의심 거래 — 위험도 {r:.2f}",
 "notif.subject_confirm":"[FDS] {ft} 이상거래 확정 — 위험도 {r:.2f}",
 "s5.notify_tier_review":"🟡 의심(1차) — Slack 검토요청",
 "s5.notify_tier_confirm":"🔴 확정(2차) — Slack+Email 통보",
 "s5.notify_tier_none":"⚪ 1차 임계값 미만 — 자동 발송 생략",
 # ✨ v12: 챗봇 단축키·퀵프롬프트 — i18n_data.py 미수정으로 로컬 폴백만 제공(4개국어 미번역, 한국어 고정)
 "chat.hotkey_hint":"⌨ 아무 화면에서나 C 키를 누르면 챗봇으로 바로 이동해요",
 "chat.quick_title":"빠른 질문",
 "chat.quick1":"📋 현재 화면 분석해줘",
 "chat.quick2":"🚨 이상거래 판단 기준이 뭐야?",
 "chat.quick3":"🎚 임계값을 어떻게 정하면 좋을까?",
 "chat.quick4":"➡ 다음 세션으로 이동해줘",
 # ✨ v13: 세션5 — 분석/Slack/Email 프롬프트 편집기 (i18n_data.py 미수정, 로컬 폴백)
 "s5.prompt_editor_title":"🖊 AI 프롬프트 편집 (분석 · Slack · Email)",
 "s5.prompt_editor_help":"실제로 LLM에 보내지는 프롬프트를 직접 수정할 수 있어요. {중괄호} 자리표시자만 지키면 자유롭게 바꿔도 안전합니다 — 오타가 있어도 자동으로 기본 프롬프트로 되돌아가요.",
 "s5.prompt_tab_analysis":"📋 분석 리포트",
 "s5.prompt_tab_slack":"💬 Slack 요약",
 "s5.prompt_tab_email":"✉ Email 본문",
 "s5.prompt_save":"💾 저장",
 "s5.prompt_reset":"↩ 기본값으로",
 "s5.prompt_active":"✅ 커스텀 프롬프트 적용 중 — 위 탐지 실행부터 즉시 반영됩니다",
 "s5.prompt_vars_label":"사용 가능한 자리표시자",
 "s5.prompt_tab_batch":"📦 배치 종합보고서",
}
def tt(key, **kw):
    s = t(key, **kw)
    if s == key and key in _V5_KO:            # i18n 미병합 → 한국어 기본값
        try: return _V5_KO[key].format(**kw)
        except Exception: return _V5_KO[key]
    return s

def hint(key, **kw):
    """🔰 초보자 설명 — beginner_mode가 켜졌을 때만 지표/차트 아래 한 줄 해설(caption)을 렌더.
    꺼져 있으면 아무것도 그리지 않아 화면이 늘어지지 않는다(컴팩트 철학 유지).
    문구는 tt()를 거치므로 i18n_data(4개국어)에 있으면 현지화, 없으면 한국어 폴백."""
    if st.session_state.get('beginner_mode', False):
        st.caption(tt(key, **kw))

def _seg_nav(state_key, options, label_map, default=None):
    """✨ 트랙2: st.tabs 대체 — session_state로 구동되는 탭 네비게이션.
    위젯 key = state_key 라, 에이전트는 `st.session_state[state_key]='tabN'; st.rerun()`으로
    (위젯 생성 전 시점에) 탭을 옮길 수 있다. st.segmented_control(1.40+) 우선, 미지원 시 radio 폴백.
    반환: 현재 활성 옵션 키."""
    if state_key not in st.session_state or st.session_state[state_key] not in options:
        st.session_state[state_key] = default or options[0]
    _fmt = lambda k: label_map.get(k, k)
    _seg = getattr(st, "segmented_control", None)
    if _seg is not None:
        _seg(state_key, options=options, format_func=_fmt,
             label_visibility="collapsed", key=state_key)
    else:
        st.radio(state_key, options, format_func=_fmt, horizontal=True,
                 label_visibility="collapsed", key=state_key)
    return st.session_state[state_key]

# ── ✨ v5: 데이터셋 검색·로딩 (CSV/Parquet/X+y 분할셋) ──────
# 🔧 FIX(v8): cache_data(ttl=60) 위에 cache_resource(ttl=15)가 이중으로 감겨
#   바깥 60초 캐시가 이겨 "새 파일 15초 내 반영" 주석과 실동작이 어긋나던 버그 → 단일 캐시로 정리
@st.cache_data(ttl=15, show_spinner=False)
def _discover_ds(folder):
    """✨ v7.2: 사이드바에서 매 rerun마다 돌던 폴더 스캔 캐시 (ttl 15초 — 새 파일도 곧 반영)"""
    from pipeline.dataset_loader import discover_datasets
    return {k: v for k, v in discover_datasets(folder).items()}

@st.cache_data(show_spinner=t("common.csv_loading_spinner"))
def _load_selected_dataset_cached(ds_folder, ds_name, mtimes):   # 🔴 FIX(v10): 밑줄 제거
    from pipeline.dataset_loader import discover_datasets, load_dataset
    found = discover_datasets(ds_folder)
    if ds_name not in found:
        return None, ""
    info = found[ds_name]
    return load_dataset(info), info.note

@st.cache_resource(show_spinner=False)
def _get_feature_bridge():
    """✨ v6.3: 자동 fit — models/feature_bridge.pkl이 없지만 data/에 쌍이 있으면 자동 학습."""
    from pipeline.feature_bridge import FeatureBridge
    from pathlib import Path
    fb_path = Path("models/feature_bridge.pkl")
    if fb_path.exists():
        return FeatureBridge.load(fb_path)
    # 자동 fit 시도
    raw_path = Path("data/train.csv")
    xtr_path = Path("data/X_tr.parquet")
    if raw_path.exists() and xtr_path.exists():
        try:
            from pipeline.feature_bridge import fit_bridge_from_files
            log.info("FeatureBridge 자동 학습 시작 (최초 1회)...")
            br = fit_bridge_from_files(str(raw_path), str(xtr_path), save_to=str(fb_path))
            log.info(f"FeatureBridge 자동 학습 완료 — {br.summary()}")
            return br
        except Exception as e:
            log.warning(f"FeatureBridge 자동 학습 실패: {e}")
    return None


def load_selected_dataset(ds_folder, ds_name):
    """선택 데이터셋 로드 — X/y parquet 자동 결합, 정수 라벨은 'a'~'m'으로 디코딩.
    🐛 FIX(v5.2): 파일 mtime을 캐시 키에 포함 — 같은 이름으로 파일 교체 시 자동 리로드"""
    from pipeline.dataset_loader import discover_datasets
    found = discover_datasets(ds_folder)
    if ds_name not in found:
        return None, ""
    mtimes = tuple(p.stat().st_mtime for p in found[ds_name].paths if p.exists())
    return _load_selected_dataset_cached(ds_folder, ds_name, mtimes)

# ── ⚡ v8: 세션 3 표시용 디코딩 캐시 ─────────────────────
_S3_SEG_CANDS = ('Channel','Operating_System','Access_Medium','Customer_credit_rating','Customer_Gender','Account_account_type')

@st.cache_data(show_spinner=False)
def _decode_seg_cached(ds_folder, ds_name, mt, lep_mt):   # 🔴 FIX(v10): 밑줄 제거
    """⚡ v8: 96k행 × 6컬럼 inverse_transform이 토글/셀렉트 클릭 등 매 rerun마다
    재실행되던 병목 제거 — (데이터셋 mtime, 인코더 mtime) 키로 디코딩 결과 캐시.
    반환: (디코딩된 df | None, note). None이면 세그먼트 분석 요건 미충족."""
    df, note = _load_selected_dataset_cached(ds_folder, ds_name, mt)
    if df is None or 'Fraud_Type' not in df.columns:
        return None, note
    _s3cols = [c for c in _S3_SEG_CANDS if c in df.columns]
    if not _s3cols:
        return None, note
    try:
        _lep = Path("models/label_encoders.pkl")
        if _lep.exists() and any(pd.api.types.is_numeric_dtype(df[c]) for c in _s3cols):
            _les = _load_label_encoders(str(_lep), lep_mt)
            df = df.copy()
            for _c in _s3cols:
                if _c in _les and pd.api.types.is_numeric_dtype(df[_c]):
                    _cls = _les[_c].classes_
                    _idx = df[_c].fillna(0).astype(int).clip(0, len(_cls)-1)
                    df[_c] = _les[_c].inverse_transform(_idx)
    except Exception as _de:
        log.warning(f"세그먼트 표시용 디코딩 실패(코드값으로 표시): {_de}")
    return df, note

def load_decoded_segment_df(ds_folder, ds_name):
    if not ds_name:
        return None, ""
    from pipeline.dataset_loader import discover_datasets
    found = discover_datasets(ds_folder)
    if ds_name not in found:
        return None, ""
    mtimes = tuple(p.stat().st_mtime for p in found[ds_name].paths if p.exists())
    return _decode_seg_cached(ds_folder, ds_name, mtimes, _mtime(Path("models/label_encoders.pkl")))

def kpi_card(label,value,delta=None,icon="",accent=None,glow=False):
    ac = accent or T['accent']
    _cls = "kpi-card anomaly" if glow else "kpi-card"
    if CV:
        # ✨ v9.5: 컴팩트 — 값과 델타/단위를 한 줄로 (라벨 / "값 델타") → 3줄을 2줄로 압축
        d = f'<span class="kpi-delta-inline">{delta}</span>' if delta else ""
        st.markdown(f'<div class="{_cls}" style="--kpi-accent:{ac}"><span class="kpi-icon">{icon}</span><p class="kpi-label">{label}</p><p class="kpi-value">{value}{(" " + d) if d else ""}</p></div>', unsafe_allow_html=True)
    else:
        d=f'<p class="kpi-delta">{delta}</p>' if delta else ""
        st.markdown(f'<div class="{_cls}" style="--kpi-accent:{ac}"><span class="kpi-icon">{icon}</span><p class="kpi-label">{label}</p><p class="kpi-value">{value}</p>{d}</div>',unsafe_allow_html=True)

def section_header(title,badge=None):
    b=f'<span class="section-badge">{badge}</span>' if badge else ""
    st.markdown(f'<div class="section-header"><span class="section-title">{title}</span>{b}<div class="section-header-line"></div></div>',unsafe_allow_html=True)

def sb_section(title):
    """✨ v7 DESIGN: 사이드바 미니 섹션 헤더 — 액센트 틱 + 통일된 타이포 (인라인 <p> 복붙 5곳 통합)"""
    st.markdown(f'<div style="display:flex;align-items:center;gap:7px;margin:2px 0 6px"><span style="width:3px;height:11px;border-radius:2px;background:var(--accent)"></span><span style="color:{T["text_muted"]};font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase">{title}</span></div>', unsafe_allow_html=True)

def page_title(main, span="", sub=None, color=None, eyebrow=None):
    """✨ v7 DESIGN: 세션 히어로 타이틀 — 아이브로 배지 + 그라디언트 강조 텍스트"""
    c = color or T['accent']
    eb = f'<div class="hero-eyebrow">{eyebrow}</div>' if eyebrow else ""
    sp = f' <span class="hero-accent" style="--hero-c:{c}">{span}</span>' if span else ""
    sb = f'<p class="hero-sub">{sub}</p>' if sub else ""
    st.markdown(f'<div class="page-hero">{eb}<h1>{main}{sp}</h1>{sb}</div>', unsafe_allow_html=True)

def prob_bars(proba_dict,threshold):
    si=sorted(proba_dict.items(),key=lambda x:x[1],reverse=True)
    html=""
    for idx,(cls,prob) in enumerate(si):
        label=FRAUD_SHORT.get(cls,cls);pct=prob*100;is_top=(idx==0)
        fc="danger" if (cls!='m' and is_top) else ""
        html+=f'<div class="prob-bar-wrap"><div class="prob-bar-label"><span>{"⚑ " if is_top else ""}{label}</span><span>{pct:.2f}%</span></div><div class="prob-bar-bg"><div class="prob-bar-fill {fc}" style="width:{min(pct,100):.1f}%"></div></div></div>'
    st.markdown(html,unsafe_allow_html=True)

def risk_gauge(score):
    """✨ v7 DESIGN: 그라디언트 아크 + 25% 눈금 + 엔드포인트 마커 + 로드 애니메이션"""
    score = max(0.0, min(1.0, float(score)))
    if score>=0.8: color,dim,label=T['red'],T['red_dim'],"HIGH RISK"
    elif score>=0.5: color,dim,label=T['amber'],T['amber'],"ELEVATED"
    else: color,dim,label=T['green'],T['green'],"NORMAL"
    _gid = f"gg{int(score*10000)}"
    # 반원 아크: 중심(70,75), r=55 · 눈금 25% 간격
    _ticks = ""
    for p in (0.0, 0.25, 0.5, 0.75, 1.0):
        a = np.pi * (1 - p)
        x1,y1 = 70+49*np.cos(a), 75-49*np.sin(a)
        x2,y2 = 70+55*np.cos(a), 75-55*np.sin(a)
        _ticks += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{T["text_muted"]}" stroke-width="1.4" opacity="0.55"/>'
    # 현재 점수 위치 엔드포인트 마커
    _ea = np.pi * (1 - score)
    _ex,_ey = 70+55*np.cos(_ea), 75-55*np.sin(_ea)
    _dash = f"{score*173:.0f} 173"
    st.markdown(
        f'<div class="gauge-wrap"><svg viewBox="0 0 140 88" width="185" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="{_gid}" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{dim}" stop-opacity="0.55"/><stop offset="100%" stop-color="{color}"/></linearGradient></defs>'
        f'<path d="M15,75 A55,55,0,0,1,125,75" fill="none" stroke="{T["bg_surface"]}" stroke-width="10" stroke-linecap="round"/>'
        f'{_ticks}'
        # 🔧 FIX(v8.9): SMIL <animate>는 탐지 직후 rerun 연쇄에서 시작값(빈 아크)에 동결되는
        #   고질병 → CSS 키프레임으로 교체. 애니메이션이 실패해도 정적 stroke-dasharray가 최종값 보장.
        f'<style>@keyframes gf_{_gid}{{from{{stroke-dasharray:0 173}}to{{stroke-dasharray:{_dash}}}}}</style>'
        f'<path d="M15,75 A55,55,0,0,1,125,75" fill="none" stroke="url(#{_gid})" stroke-width="10" stroke-linecap="round" '
        f'stroke-dasharray="{_dash}" style="filter:drop-shadow(0 0 5px {color});animation:gf_{_gid} 0.9s cubic-bezier(0.22,1,0.36,1) 1"></path>'
        f'<circle cx="{_ex:.1f}" cy="{_ey:.1f}" r="4.5" fill="{color}" opacity="0.35"/>'
        f'<circle cx="{_ex:.1f}" cy="{_ey:.1f}" r="2.4" fill="{T["text_primary"]}"/>'
        f'<text x="70" y="62" text-anchor="middle" font-family="JetBrains Mono,monospace" font-size="22" font-weight="700" fill="{color}">{score:.3f}</text>'
        f'<text x="70" y="76" text-anchor="middle" font-family="JetBrains Mono,monospace" font-size="8.5" fill="{T["text_muted"]}">{score*100:.1f}%</text>'
        f'</svg><div class="gauge-label" style="color:{color}">{label}</div></div>',
        unsafe_allow_html=True)


def _resolve_seed(val):
    """시드 값이 -1이면 랜덤 시드 생성, 아니면 그대로 반환"""
    if int(val) < 0:
        s = random.randint(0, 9999)
        st.toast(t("common.random_seed_toast", s=s))
        return s
    return int(val)

# ── 개선: HTML 헬퍼 함수 (반복 패턴 통합) ────────────────
def alert_box(msg, level="info"):
    """레벨: info, warn, error, ok.
    ✨ v9.5: 컴팩트(발표/시연) 모드에선 수동적 info·warn 잡음을 숨기고
    error(치명 오류)·ok(사용자가 직접 유발한 액션 피드백)만 표시한다."""
    if CV and level in ("info", "warn"):
        return
    st.markdown(f'<div class="alert-box alert-{level}">{msg}</div>', unsafe_allow_html=True)

# ── 개선: 축 공통 스타일 헬퍼 (Plotly 레이아웃은 PLOTLY_LAYOUT 상수로 통일) ────
# NOTE(v9.1): get_plotly_layout()는 PLOTLY_LAYOUT 상수 도입 후 호출부가 사라진 데드코드였음 → 제거.
def styled_axis(fig, grid_color=None, **kwargs):
    """X/Y 축 공통 스타일 적용 헬퍼 (✨ v7: 기본값을 테마 반응형 GRID_COLOR로 — 라이트 테마 대응)"""
    grid_color = grid_color or GRID_COLOR
    fig.update_xaxes(gridcolor=grid_color, **kwargs)
    fig.update_yaxes(gridcolor=grid_color, **kwargs)
    return fig

# ── 개선: Pipeline 모듈 캐시 (lazy import 최적화) ────────
@st.cache_resource
def _load_label_encoders(path_str, mt):   # 🔴 FIX(v10): 밑줄 제거
    """✨ v7.2: label_encoders.pkl 캐시 — 세션 3에서 매 rerun마다 디스크 로드하던 것 제거 (mt는 mtime 무효화용)"""
    from pipeline.bundle_io import safe_load     # 🔴 FIX(v10): 팀 번들은 joblib 형식
    return safe_load(path_str)

@st.cache_resource
def _get_ml_classifier_cached(model_path, mt):
    """ML 분류기 인스턴스를 캐시하여 매 탐지마다 재로드 방지.
    🔴 FIX(v10): mt(mtime)를 캐시 키에 포함 — 같은 이름으로 모델 pkl을 교체했을 때
    '고쳤는데 화면은 그대로'가 되던 문제 해결. 재시작 불필요."""
    from pipeline.ml_classifier import MLClassifier
    return MLClassifier(model_path)

def _get_ml_classifier(model_path):
    return _get_ml_classifier_cached(str(model_path), _mtime(Path(model_path)))


# ══════════════════════════════════════════════════════════
# ✨ v10: 분류기 선택 단일 관문
#   기존엔 "row의 값이 전부 수치면 전처리 완료된 행"이라는 휴리스틱으로 판정했는데,
#   ① 문자 컬럼이 없는 원본 행이 '전처리 완료'로 오판되어 RowClassifier로 흘러가
#      학습 피처 순서와 어긋난 채 조용히 오예측하고,
#   ② 라벨/내부키가 섞이면 판정이 뒤집혔다.
#   → **컬럼 집합 대조**로 교체한다. 그리고 배포 번들이 선택된 경우엔
#     Preprocessor(원본·전처리완료 양쪽 모두 정확히 처리, 120k행 재현 검증됨)를 쓴다.
# ══════════════════════════════════════════════════════════
_RAW_ONLY_MARKERS = ("Transaction_Amount", "Location", "Transaction_Datetime",
                     "Time_difference", "Account_creation_datetime")

@st.cache_resource(show_spinner=False)
def _get_raw_classifier_cached(model_path, mt):
    """배포 번들용 RawRowClassifier(Preprocessor 내장) 캐시."""
    from pipeline.preprocessor import RawRowClassifier
    return RawRowClassifier.from_bundle(MODEL_DIR, model_path)

def _get_raw_classifier(model_path):
    return _get_raw_classifier_cached(str(model_path), _mtime(Path(model_path)))

def _is_bundle_model(model_path) -> bool:
    """선택된 모델이 배포 번들 본체인지 — feature_cols.json과 피처 수가 맞으면 번들."""
    try:
        if _BASE_MODEL_PATH is None:
            return False
        return Path(model_path).resolve() == Path(_BASE_MODEL_PATH).resolve()
    except Exception:
        return False

def _classify_row_shape(row: dict, feature_cols=None) -> str:
    """행의 컬럼 구성 판정 → 'raw' | 'engineered' | 'unknown'  (값 타입이 아니라 컬럼명 기준)"""
    keys = {str(k) for k in (row or {}) if not str(k).startswith('_') and k != 'Fraud_Type'}
    if not keys:
        return 'unknown'
    if any(m in keys for m in _RAW_ONLY_MARKERS):
        return 'raw'
    if feature_cols:
        cover = len(keys & set(feature_cols)) / max(len(feature_cols), 1)
        if cover >= 0.9:
            return 'engineered'
    return 'unknown'

def _resolve_classifier(model_path, sample_row: dict):
    """(분류기, 모드라벨, 전달할 row 정제 여부) 반환. 세션5 단건·배치가 공유한다."""
    # ① 배포 번들 → Preprocessor 경유 (원본/전처리완료 양쪽 정확)
    if _is_bundle_model(model_path):
        try:
            clf = _get_raw_classifier(model_path)
            shape = _classify_row_shape(sample_row, clf.feature_cols)
            return clf, t("clf.mode_bundle", n=len(clf.feature_cols), shape=shape), False
        except Exception as e:
            log.warning(f"RawRowClassifier 준비 실패 → MLClassifier 폴백: {e}")

    _mlclf = _get_ml_classifier(model_path)
    shape = _classify_row_shape(sample_row, getattr(_mlclf, 'feature_cols', None))

    # ② 전처리 완료 행 + 비번들 모델 → RowClassifier(위치/이름 정렬)
    if shape == 'engineered':
        try:
            from pipeline.model_loader import make_row_classifier
            _cols = [k for k in sample_row if not str(k).startswith('_') and k != 'Fraud_Type']
            return make_row_classifier(model_path, _cols), t("clf.mode_encoded"), True
        except Exception as e:
            log.warning(f"RowClassifier 준비 실패 → MLClassifier 폴백: {e}")

    # ③ 원본 행 + 🧩컴포지트 + 브리지 → 파생 모델 직접 탐지 (기존 v5.7 경로)
    if shape == 'raw' and Path("models/feature_bridge.pkl").exists():
        try:
            from pipeline.model_loader import discover_models as _dm
            from pipeline.feature_bridge import make_bridged_classifier
            _comps = {k: v for k, v in _dm("models/").items() if k.startswith("🧩")}
            if _comps:
                _ck = next(iter(_comps))
                return make_bridged_classifier(_comps[_ck]), t("clf.mode_bridge", ck=_ck), False
        except Exception as e:
            log.warning(f"브리지 경로 실패 → MLClassifier 폴백: {e}")

    return _mlclf, t("clf.mode_mlclf"), False


def fraud_type_popup(code):
    info=FRAUD_TYPE_DETAILS.get(code)
    if not info: return
    rc={'HIGH':T['red'],'MEDIUM':T['amber'],'LOW':T['green']}.get(info['risk'],T['text_secondary'])
    ind_html=' '.join(f'<span class="feature-tag danger">{x}</span>' for x in info['indicators'])
    # ✨ v17: 실측 근거(evidence) 노출 — 담당자와 AI가 같은 수치를 본다
    _ev = info.get('evidence', '')
    ev_html = ('<div style="margin-top:7px;padding-top:7px;border-top:1px solid %s">'
               '<span style="color:var(--text-muted);font-size:10px;letter-spacing:0.06em;'
               'text-transform:uppercase;margin-right:6px">%s</span>'
               '<span style="color:%s;font-size:11px;font-family:var(--font-mono);'
               'line-height:1.65">%s</span></div>'
               % (ROW_BORDER, t("common.measured_evidence"), T['accent'], _ev)) if _ev else ''
    st.markdown(f'<div class="fraud-type-card"><div style="display:flex;align-items:center;gap:10px;margin-bottom:6px"><span style="font-family:var(--font-mono);font-size:13px;font-weight:700;color:var(--accent)">{code.upper()}</span><span style="color:{rc};font-size:10px;font-weight:700;font-family:var(--font-mono)">{info["risk"]}</span></div><p style="font-size:14px;font-weight:600;color:var(--text-primary);margin:0 0 6px">{info["name"]}</p><p style="font-size:12.5px;color:var(--text-secondary);line-height:1.6;margin:0">{info["desc"]}</p><div style="margin-top:8px;padding-top:8px;border-top:1px solid {ROW_BORDER}"><span style="color:var(--text-muted);font-size:10px;letter-spacing:0.06em;text-transform:uppercase;margin-right:6px">{t("common.key_indicators")}</span>{ind_html}</div>{ev_html}</div>',unsafe_allow_html=True)

SESSION_LABELS=SESSION_LABELS_I18N[LANG]
SESSION_KEYS=["01","02","03","04","05"]

# ── 모델 레지스트리 (추가 모델 확장 가능) ─────────────────
# ✨ v10: 팀 배포 번들이 베이스 모델. 실제 파일명(`lgbm_13class(최종).pkl`)이 괄호·한글을
#   포함하고 팀마다 다를 수 있어, bundle_io.resolve_model_path()로 실물을 탐색해 등록한다.
#   기존 6개 항목은 그대로 유지 — 파일이 없으면 get_available_models가 자동으로 숨긴다.
try:
    from pipeline.bundle_io import resolve_model_path as _resolve_mp, is_non_model_pkl as _is_non_model
    _BASE_MODEL_PATH = _resolve_mp(MODEL_DIR)
except Exception:
    _BASE_MODEL_PATH, _is_non_model = None, (lambda p: False)
BASE_MODEL_NAME = "🎯 lgbm_13class (최종·58피처)"

MODEL_REGISTRY = {
    "LightGBM (기본)":    {"path": "models/lgbm_fds.pkl",    "type": "lightgbm",  "desc": MODEL_DESC_I18N["LightGBM (기본)"][LANG]},
    "RandomForest":       {"path": "models/rf_fds.pkl",      "type": "sklearn",   "desc": MODEL_DESC_I18N["RandomForest"][LANG]},
    "LogisticRegression": {"path": "models/lr_fds.pkl",      "type": "sklearn",   "desc": MODEL_DESC_I18N["LogisticRegression"][LANG]},
    "XGBoost":            {"path": "models/xgb_fds.pkl",     "type": "xgboost",   "desc": MODEL_DESC_I18N["XGBoost"][LANG]},
    "CatBoost":           {"path": "models/catboost_fds.pkl", "type": "catboost",  "desc": MODEL_DESC_I18N["CatBoost"][LANG]},
    "MLP (신경망)":        {"path": "models/mlp_fds.pkl",     "type": "sklearn",   "desc": MODEL_DESC_I18N["MLP (신경망)"][LANG]},
}

@st.cache_data(ttl=30)
def get_available_models(lang=LANG):   # 🔴 FIX(v10): _lang → lang (언어 변경 시 캐시 무효화가 실제로 동작)
    """models/ 디렉토리에서 실제 존재하는 모델 파일 탐색.
    ✨ v10: ① 팀 배포 번들을 맨 앞(베이스)으로 등록  ② 메타 pkl(label_encoders/le_target/
    feature_bridge)을 모델 목록에서 제외 — 기존엔 `🔍 Le Target`·`🔍 Label Encoders`가
    선택 가능한 '모델'로 노출돼 고르면 즉시 예측이 깨졌다."""
    available = {}
    if _BASE_MODEL_PATH is not None and Path(_BASE_MODEL_PATH).exists():
        available[BASE_MODEL_NAME] = {
            "path": str(_BASE_MODEL_PATH), "type": "lightgbm",
            "desc": t("model.base_bundle"),
        }
    for name, info in MODEL_REGISTRY.items():
        if Path(info["path"]).exists():
            available[name] = info
    # 등록되지 않은 .pkl 파일도 자동 발견 (메타/부속 pkl은 제외)
    _known = {str(Path(i["path"])) for i in MODEL_REGISTRY.values()}
    if _BASE_MODEL_PATH is not None:
        _known.add(str(Path(_BASE_MODEL_PATH)))
    for pkl in MODEL_DIR.glob("*.pkl"):
        if _is_non_model(pkl) or str(pkl) in _known:
            continue
        display = pkl.stem.replace("_", " ").title()
        available[f"🔍 {display}"] = {"path": str(pkl), "type": "auto", "desc": t("model.auto_discovered")}
    if not available:
        available["LightGBM (기본)"] = MODEL_REGISTRY["LightGBM (기본)"]
    return available


def default_model_name(avail: dict) -> str:
    """✨ v10: 기본 선택 모델 — 배포 번들이 있으면 그것, 없으면 첫 항목."""
    if BASE_MODEL_NAME in avail:
        return BASE_MODEL_NAME
    return next(iter(avail), "LightGBM (기본)")


# ── 키보드 단축키 ────────────────────────────────────────
import streamlit.components.v1 as components
_sb_accent = T['accent']
_sb_bg = T['bg_base']
_sb_rgb = T['accent_rgb']

# ══ ⌨ v8.3: 전역 단축키 확장 ══════════════════════════════
# 구조: 히든 버튼(st-key CSS로 화면 밖 고정) ← JS 키 리스너가 클릭 → 파이썬이 상태 전환.
#   U: 신/구 UI 전환 · T: 테마 순환 · S 또는 . : 설정(⋮) 열기 · ←/→: 세션 이동 · 1~5 · ?: 도움말
# 🔧 FIX(v8.3): 기존 1~5 단축키 JS가 구 UI 전용 블록(if not IS_NEW_UI)에 갇혀
#   신 UI에서 키보드가 전혀 안 먹던 문제 — 키 리스너를 분리해 양쪽 UI 공통 로드.
st.markdown("""<style>
.st-key-hk_ui,.st-key-hk_theme,.st-key-hk_prev,.st-key-hk_next,.st-key-hk_lang,.st-key-hk_compact,.st-key-hk_chat,.st-key-hk_help,.st-key-hk_guide,.st-key-hk_beginner,.st-key-hk_s5,.st-key-hk_home,.st-key-hk_chatclose{position:fixed!important;top:-10000px!important;left:-10000px!important;width:1px!important;height:1px!important;overflow:hidden!important;opacity:0!important}
/* ✨ v8.15: 장시간 분석(LLM 3단계) 중 직전 런의 '유령 잔상'(stale 프레임) 존재감 최소화
   — Streamlit 기본은 33% 투명 유지라 버튼/캡션이 이중으로 보였음. 완전 숨김(0)은
   레이아웃 점프가 생겨 12%로 타협: 시연 화면에선 사실상 안 보이는 수준 */
div[data-stale="true"],[data-stale="true"] *{opacity:0.12!important;transition:opacity .3s ease}
</style>""", unsafe_allow_html=True)
if st.button("⌨U", key="hk_ui"):
    _hk_new = "old" if st.session_state.get('ui_mode', 'new') == "new" else "new"
    st.session_state['ui_mode'] = _hk_new
    st.session_state['ui_mode_radio'] = _hk_new     # 설정 라디오 위젯 상태 동기화 (되돌림 방지)
    st.rerun()
if st.button("⌨T", key="hk_theme"):
    if IS_NEW_UI:
        _hk_o = list(NEW_THEME_ORDER); _hk_c = st.session_state.get('new_theme', _hk_o[0])
        _hk_n = _hk_o[(_hk_o.index(_hk_c) + 1) % len(_hk_o)] if _hk_c in _hk_o else _hk_o[0]
        st.session_state['new_theme'] = _hk_n; st.session_state['new_theme_radio'] = _hk_n
    else:
        _hk_o = list(THEMES.keys()); _hk_c = st.session_state.get('theme_name', _hk_o[0])
        _hk_n = _hk_o[(_hk_o.index(_hk_c) + 1) % len(_hk_o)] if _hk_c in _hk_o else _hk_o[0]
        st.session_state['theme_name'] = _hk_n; st.session_state['theme_selector'] = _hk_n
    st.rerun()
if st.button("⌨L", key="hk_lang"):
    _hk_o = list(LANG_OPTIONS); _hk_c = st.session_state.get('lang', _hk_o[0])
    _hk_n = _hk_o[(_hk_o.index(_hk_c) + 1) % len(_hk_o)] if _hk_c in _hk_o else _hk_o[0]
    st.session_state['lang'] = _hk_n
    st.session_state['lang_radio_top'] = _hk_n   # 설정 라디오 동기화
    st.rerun()
if st.button("⌨V", key="hk_compact"):
    # 🗜 컴팩트 오버뷰 토글 — 신 UI 전용 (구 UI에선 무시)
    # 🔧 FIX: 일반 세션 상태 compact_view만 뒤집는다(단일 진실). 토글은 value=compact_view로
    #   매 런 표시를 맞추고 key가 상태값 따라 바뀌므로, 여기서 위젯 상태를 손댈 필요가 없다.
    if st.session_state.get('ui_mode', 'new') == "new":
        st.session_state['compact_view'] = not st.session_state.get('compact_view', False)
    st.rerun()
if st.button("⌨◀", key="hk_prev"):
    st.session_state['session_idx'] = max(0, st.session_state.get('session_idx', 0) - 1); st.rerun()
if st.button("⌨▶", key="hk_next"):
    st.session_state['session_idx'] = min(len(SESSION_KEYS) - 1, st.session_state.get('session_idx', 0) + 1); st.rerun()
if st.button("⌨?", key="hk_help"):
    # ✨ v17: ? 단축키 → 전체 단축키 모음 모달. 기존엔 우측 하단 12px 토스트라 놓치기 쉬웠고,
    #   목록에 C(챗봇)·V(컴팩트)가 빠져 "전체 모음"이 아니었다.
    st.session_state['_kbd_open'] = True; st.rerun()
if st.button("⌨H", key="hk_guide"):
    # ✨ v17: H 단축키 → 사용 안내(온보딩) 재호출 (요청 2)
    st.session_state['_onboard_open'] = True; st.rerun()
if st.button("⌨C", key="hk_chat"):
    # ✨ v12: 챗봇 다이렉트 단축키 — 꺼져 있으면 켜고, 렌더 후 입력창에 자동 포커스(아래 _focus_chat_pending 처리부 참조)
    st.session_state['chat_open'] = True
    st.session_state['_focus_chat_pending'] = True
    st.rerun()
if st.button("⌨N", key="hk_beginner"):
    # ✨ v18: N 단축키 → 초보자 설명(beginner_mode) 토글. V(컴팩트)와 동일 패턴 — 단일 진실
    #   상태이므로 rerun 간에도 값이 유실되지 않는다.
    st.session_state['beginner_mode'] = not st.session_state.get('beginner_mode', False)
    st.rerun()
if st.button("⌨D", key="hk_s5"):
    # ✨ v18: D 단축키 → 5번째 세션(탐지) 분석으로 즉시 이동. 온보딩 모달의 '탐지로 이동'
    #   버튼(onb_detect)과 완전히 동일한 동작을 키보드로 바로 호출한다.
    st.session_state['session_idx'] = 4
    st.rerun()
if st.button("⌨⇱", key="hk_home"):
    # ✨ v18: Home 단축키 → 1번째 세션으로 즉시 이동 (D의 대칭 동작)
    st.session_state['session_idx'] = 0
    st.rerun()
if st.button("⌨Esc", key="hk_chatclose"):
    # ✨ v18: Esc 단축키 → 챗봇이 열려 있을 때만 JS가 호출 → 챗봇 닫기 (C의 대칭 동작)
    st.session_state['chat_open'] = False
    st.rerun()

_kbd_hint = t("kbd.hint").replace("'", "\\'")
# 🔧 FIX(v8.4): 리스너 사망 버그 — 테마/언어가 바뀌면 이 JS 문자열(색상·힌트 보간)이 달라져
#   iframe이 재마운트되고, 구 iframe이 등록한 리스너는 렐름과 함께 죽는데 __fk2 가드가
#   재등록을 막아 T 1회 후 전체 단축키가 먹통이 되던 문제.
#   → 가드 대신 "항상 제거 후 재등록" 패턴으로 교체 (재마운트 = 리스너 갱신).
_kbd_core_js = (f"""<!DOCTYPE html><html><head><style>body{{margin:0;padding:0;background:transparent;}}</style></head><body><script>
(function(){{var d=window.parent.document;
function hk(cls){{var b=d.querySelector('.st-key-'+cls+' button');if(b)b.click();}}
function toast(msg,ms){{var t=d.querySelector('#ft2');if(!t){{t=d.createElement('div');t.id='ft2';t.style.cssText='position:fixed;bottom:28px;right:28px;z-index:99999;background:rgba(13,22,38,0.95);border:1px solid rgba({_sb_rgb},0.40);border-radius:10px;padding:10px 18px;font-family:JetBrains Mono,monospace;font-size:12px;color:{_sb_accent};pointer-events:none;opacity:0;transition:opacity 0.4s;box-shadow:0 0 20px rgba({_sb_rgb},0.15)';d.body.appendChild(t);}}t.innerHTML=msg;t.style.opacity='1';clearTimeout(t.__h);t.__h=setTimeout(function(){{t.style.opacity='0'}},ms||3200);}}
function handler(e){{
  if(e.isComposing)return;                                   // 한글 IME 조합 중 무시
  var ae=d.activeElement||{{}};
  var tag=(ae.tagName||'').toUpperCase();
  if(['INPUT','TEXTAREA','SELECT'].indexOf(tag)>=0)return;
  if(ae.isContentEditable)return;
  // 🔧 FIX(v9.7): 단일문자 단축키(v=컴팩트 등)가 baseweb 셀렉트/멀티셀렉트/입력 포커스 중 새어나가
  //   type-ahead 키를 가로채 오작동(실시간 재평가에서 표본상한·모델선택 조작 중 컴팩트 해제)하던 문제.
  //   화살표 핸들러에만 있던 콤보박스 가드를 전 단축키에 확대 적용.
  if(ae.closest&&ae.closest('[data-baseweb="select"],[data-baseweb="input"],[data-baseweb="textarea"],[data-testid="stSelectbox"],[data-testid="stMultiSelect"],[data-testid="stNumberInput"],[data-testid="stTextInput"],[data-testid="stTextArea"],[data-testid="stSlider"],[role="combobox"],[role="listbox"],[role="slider"],[role="tab"],[contenteditable="true"]'))return;
  var k=(e.key||'').toLowerCase();
  if((e.ctrlKey||e.metaKey)&&k==='/'){{e.preventDefault();toast('{_kbd_hint}',9000);return;}}   // Ctrl+/ 도움말
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  if(['1','2','3','4','5'].indexOf(e.key)>=0){{e.preventDefault();var i=parseInt(e.key)-1;var bs=Array.from(d.querySelectorAll('button')).filter(function(b){{return/^(📋|📊|🔍|🧪|🚀)/.test(b.textContent.trim())}});if(bs.length>i)bs[i].click();return;}}
  if(k==='u'){{e.preventDefault();hk('hk_ui');return;}}
  if(k==='t'){{e.preventDefault();hk('hk_theme');return;}}
  if(k==='l'){{e.preventDefault();hk('hk_lang');return;}}
  if(k==='v'){{e.preventDefault();hk('hk_compact');return;}}
  if(k==='s'||k==='.'){{var p=Array.from(d.querySelectorAll('button')).find(function(b){{return b.textContent.trim()==='⋮'}});if(p){{e.preventDefault();p.click();}}return;}}
  if(k==='arrowleft'||k==='arrowright'){{
    var ae=d.activeElement;
    if(ae&&ae.closest&&ae.closest('[data-testid="stSlider"],[data-baseweb="select"],[role="slider"],[role="tab"],[data-testid="stSelectbox"]'))return;
    e.preventDefault();hk(k==='arrowleft'?'hk_prev':'hk_next');return;}}
  if(e.key==='?'||k==='/'){{e.preventDefault();hk('hk_help');return;}}       // ✨ v17: 토스트 → 전체 모음 모달
  if(k==='h'){{e.preventDefault();hk('hk_guide');return;}}                   // ✨ v17: 사용 안내
  if(k==='c'){{
    e.stopPropagation();                                      // Streamlit C키 캐시클리어 차단(기존 동작 유지)
    e.preventDefault();
    var ci=d.querySelector('[data-testid="stChatInputTextArea"]')||d.querySelector('[data-testid="stChatInput"] textarea');
    if(ci){{ci.scrollIntoView({{behavior:'smooth',block:'center'}});ci.focus();}}   // 이미 열려 있으면 바로 포커스(파이썬 왕복 없이)
    else{{hk('hk_chat');}}                                     // 꺼져 있으면 히든 버튼으로 켜기(→ rerun 후 자동 포커스)
    return;
  }}
  // ✨ v18: B — 사이드바 펼치기/접기. 파이썬 상태가 필요 없는 순수 클라이언트 동작이라
  //   히든 버튼 왕복 없이 Streamlit 네이티브 토글 버튼을 바로 클릭한다(_sb_fix_js와 동일 셀렉터).
  if(k==='b'){{
    e.preventDefault();
    var sc=d.querySelector('[data-testid="stSidebarCollapsedControl"] button')
         ||d.querySelector('[data-testid="stExpandSidebarButton"]')
         ||d.querySelector('[data-testid="stCollapseSidebarButton"]');
    if(sc)sc.click();
    return;
  }}
  if(k==='n'){{e.preventDefault();hk('hk_beginner');return;}}              // ✨ v18: 초보자 설명 토글
  if(k==='d'){{e.preventDefault();hk('hk_s5');return;}}                    // ✨ v18: 5번째 세션(탐지)으로 즉시 이동
  if(k==='home'){{e.preventDefault();hk('hk_home');return;}}               // ✨ v18: 1번째 세션으로 즉시 이동
  if(k==='escape'){{                                                       // ✨ v18: 챗봇 열려 있을 때만 Esc로 닫기
    var ci2=d.querySelector('[data-testid="stChatInputTextArea"]')||d.querySelector('[data-testid="stChatInput"] textarea');
    if(ci2){{e.preventDefault();hk('hk_chatclose');}}
    return;
  }}
}}
if(d.__fkH){{try{{d.removeEventListener('keydown',d.__fkH,true);}}catch(_e){{}}}}
d.__fkH=handler;
d.addEventListener('keydown',handler,true);
if(!d.__fkToast){{d.__fkToast=true;setTimeout(function(){{toast('{_kbd_hint}',4200)}},700);}}
}})();
</script></body></html>""")
components.html(_kbd_core_js, height=0, scrolling=False)   # ⌨ 양쪽 UI 공통 · 재마운트 안전

_sb_fix_js = (f"""<!DOCTYPE html><html><head><style>body{{margin:0;padding:0;background:transparent;}}</style></head><body><script>
(function(){{var d=window.parent.document;if(d.__fk)return;d.__fk=true;

// ── 사이드바 토글 버튼 교체 (DOM 직접 조작) ──
function fixSidebarBtns(){{
  // 닫기 버튼 (사이드바 내부)
  var sidebar=d.querySelector('[data-testid="stSidebar"]');
  if(sidebar){{
    var hdrBtns=sidebar.querySelectorAll('button');
    hdrBtns.forEach(function(btn){{
      var span=btn.querySelector('span[data-testid="stIconMaterial"]');
      if(span && !btn.dataset.fixed){{
        btn.dataset.fixed='1';
        btn.style.cssText='background:{_sb_accent};border:none;border-radius:8px;min-width:36px;min-height:36px;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 0 10px rgba({_sb_rgb},0.3);margin:4px;';
        btn.innerHTML='<span style="font-size:18px;font-weight:900;color:{_sb_bg};font-family:monospace;line-height:1">◀</span>';
      }}
    }});
  }}
  // 열기 버튼 (collapsed 상태)
  var ctrl=d.querySelector('[data-testid="stSidebarCollapsedControl"]');
  if(ctrl){{
    var btns=ctrl.querySelectorAll('button');
    btns.forEach(function(btn){{
      if(!btn.dataset.fixed){{
        btn.dataset.fixed='1';
        btn.style.cssText='background:{_sb_accent};border:none;border-radius:8px;min-width:36px;min-height:36px;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 0 10px rgba({_sb_rgb},0.3);margin:4px;';
        btn.innerHTML='<span style="font-size:18px;font-weight:900;color:{_sb_bg};font-family:monospace;line-height:1">▶</span>';
      }}
    }});
  }}
}}

// 초기 실행 + 주기적 체크 (Streamlit 리렌더 대응)
setTimeout(fixSidebarBtns,500);
setTimeout(fixSidebarBtns,2000);
var fixInterval=setInterval(fixSidebarBtns,3000);
setTimeout(function(){{clearInterval(fixInterval)}},15000);

// MutationObserver로 DOM 변경 감지 (debounced)
var _fixTimer=null;
var observer=new MutationObserver(function(){{
  if(_fixTimer)clearTimeout(_fixTimer);
  _fixTimer=setTimeout(fixSidebarBtns,200);
}});
observer.observe(d.body,{{childList:true,subtree:true}});
setTimeout(function(){{observer.disconnect()}},30000);
}})();
</script></body></html>""")
if not IS_NEW_UI:
    # 신 UI는 DOM 조작 JS 없이 CSS만으로 사이드바 버튼을 처리 (덜 난잡하게)
    components.html(_sb_fix_js, height=0, scrolling=False)

# ══════════════════════════════════════════════════════════
# 상단 네비게이션 바
# ══════════════════════════════════════════════════════════
nav_cols=st.columns([1.2]+[1]*5+[0.4])
with nav_cols[0]:
    st.markdown(f'<div style="display:flex;align-items:center;gap:10px;padding:4px 0"><div style="width:34px;height:34px;min-width:34px;border-radius:10px;background:linear-gradient(135deg,{T["accent"]},{T["accent_dim"]});display:flex;align-items:center;justify-content:center;font-size:17px;box-shadow:0 4px 12px rgba({T["accent_rgb"]},0.35)">🛡</div><div><div style="font-size:14px;font-weight:800;color:{T["accent"]};line-height:1.1;letter-spacing:-0.01em">{t("nav.brand_name")}</div><div style="font-size:8.5px;color:{T["text_muted"]};letter-spacing:0.06em;margin-top:1px">{t("nav.brand_sub")}</div></div></div>',unsafe_allow_html=True)
for i,label in enumerate(SESSION_LABELS):
    with nav_cols[i+1]:
        bt="primary" if st.session_state['session_idx']==i else "secondary"
        if st.button(label,key=f"nav_{i}",type=bt,width='stretch'):
            st.session_state['session_idx']=i
            st.rerun()
with nav_cols[-1]:
    # ✨ 우측 상단 ⋮ — 화면 설정 (UI 모드 · 테마 · 언어 전환)
    with st.popover("⋮", help=t("nav.settings_help"), width='stretch'):
        # ✨ v18: 사이드바에서 이주해온 데이터 경로 설정 (한 번 정하면 고정되는 값)
        with st.expander(t("cfg.paths_title"), expanded=False):
            st.caption(t("cfg.paths_help"))
            st.session_state['cfg_train_path'] = st.text_input(
                "train.csv", st.session_state.get('cfg_train_path', 'data/train.csv'),
                key="cfg_tp")
            st.session_state['cfg_test_path'] = st.text_input(
                "test.csv", st.session_state.get('cfg_test_path', 'data/test.csv'),
                key="cfg_sp")
            st.session_state['ds_folder'] = st.text_input(
                t("ds.folder_label"), st.session_state.get('ds_folder', 'data/'),
                key="cfg_dsf", help=t("cfg.folder_help"))
        st.markdown(f'<p style="font-size:13px;font-weight:800;color:{T["text_primary"]};margin:0 0 2px">{t("nav.settings_title")}</p><p style="font-size:11px;color:{T["text_muted"]};margin:0 0 10px">{t("nav.settings_desc")}</p>', unsafe_allow_html=True)
        _cur_lang = st.session_state.get('lang', 'ko')
        if "_pending_lang" in st.session_state:   # ✨ v15 에이전트 언어 변경
            st.session_state["lang_radio_top"] = st.session_state.pop("_pending_lang")
        _lang_sel = st.radio(t("sb.lang_label"), LANG_OPTIONS,
                             index=LANG_OPTIONS.index(_cur_lang) if _cur_lang in LANG_OPTIONS else 0,
                             horizontal=True, key="lang_radio_top",
                             format_func=lambda x: LANG_DISPLAY.get(x, x))
        if _lang_sel != _cur_lang:
            st.session_state['lang'] = _lang_sel
            st.rerun()
        st.markdown("<hr style='margin:8px 0'>", unsafe_allow_html=True)
        _ui_opts = ["new", "old"]
        _cur_ui = st.session_state.get('ui_mode', _ui_opts[0])
        _ui_sel = st.radio(t("nav.ui_mode_label"), _ui_opts,
                           index=_ui_opts.index(_cur_ui) if _cur_ui in _ui_opts else 0,
                           horizontal=True, key="ui_mode_radio",
                           format_func=lambda x: t("nav.ui_new") if x=="new" else t("nav.ui_old"))
        if _ui_sel != _cur_ui:
            st.session_state['ui_mode'] = _ui_sel
            st.rerun()
        # 🔰 초보자 설명 토글 — 신·구 UI 공통. compact 토글과 같은 key 패턴(cv_toggle 참조)으로
        #   rerun 간 값 유실을 막는다. 끄면 hint()가 아무것도 렌더하지 않아 화면이 그대로 유지됨.
        _prev_bm = bool(st.session_state.get('beginner_mode', False))
        _new_bm = st.toggle(t("nav.beginner_toggle"), value=_prev_bm,
                            key=f"beginner_toggle_{_prev_bm}", help=t("nav.beginner_hint"))
        if _new_bm != _prev_bm:
            st.session_state['beginner_mode'] = _new_bm
            st.rerun()
        if IS_NEW_UI:
            # ── ✨ v9.1: 🗜 컴팩트 오버뷰 — 한 세션의 정보를 한 화면에 압축 배치 ──
            # 🔧 FIX: compact_view는 '위젯 key가 아닌' 일반 세션 상태로 유지한다(= 단일 진실).
            #   토글/세션이동/단축키 히든버튼이 이 위젯보다 앞줄에서 st.rerun()으로 실행을 끊으면
            #   위젯이 그려지지 않고, 위젯 key로 삼은 상태는 Streamlit이 폐기해 컴팩트가 풀렸다.
            #   → compact_view를 일반 키로 두면 어떤 rerun에도 값이 보존된다.
            #   토글 key를 현재 상태값으로 조합(cv_toggle_{상태})해 상태가 바뀔 때마다 '새 위젯'이
            #   되게 하면 value=가 매번 다시 반영되어(캐시된 옛 값 무시 문제 제거) 표시도 항상 일치.
            #   사용자가 직접 토글을 눌렀을 때만 _new≠_prev가 되어 compact_view가 갱신된다.
            _prev_cv = bool(st.session_state.get('compact_view', False))
            _new_cv = st.toggle(tt("nav.compact_toggle"), value=_prev_cv,
                                key=f"cv_toggle_{_prev_cv}", help=tt("nav.compact_hint"))
            if _new_cv != _prev_cv:
                st.session_state['compact_view'] = _new_cv
                st.rerun()
            _nt_opts = list(NEW_THEME_ORDER)
            _cur_nt = st.session_state.get('new_theme', _nt_opts[0])
            _nt_sel = st.radio(t("nav.new_theme_label", n=len(_nt_opts)), _nt_opts,
                               index=_nt_opts.index(_cur_nt) if _cur_nt in _nt_opts else 0,
                               horizontal=False, key="new_theme_radio",
                               format_func=lambda x: f"{NEW_THEME_META_I18N[x]['display'][LANG]} · {NEW_THEME_META_I18N[x]['label'][LANG]}")
            if _nt_sel != _cur_nt:
                st.session_state['new_theme'] = _nt_sel
                st.rerun()
            st.caption(t("nav.new_theme_hint"))
        else:
            st.caption(t("nav.old_theme_hint"))

st.markdown(f'<div style="height:1px;background:linear-gradient(90deg,rgba({T["accent_rgb"]},0.3),transparent);margin:0 0 8px"></div>',unsafe_allow_html=True)

# ── 사이드바 (설정 + 테마) ───────────────────────────────
with st.sidebar:
    st.markdown(f'<div style="padding:0 0 14px;margin-bottom:14px"><div style="font-size:15px;font-weight:800;color:{T["accent"]};letter-spacing:-0.01em">{t("sb.title")}</div><div style="font-size:10px;color:{T["text_muted"]};margin-top:2px;letter-spacing:0.04em">{t("sb.subtitle")}</div><div style="height:1px;background:linear-gradient(90deg,rgba({T["accent_rgb"]},0.45),transparent);margin-top:13px"></div></div>',unsafe_allow_html=True)
    # ✨ v15: 에이전트가 임계값을 조작할 수 있도록 key 부여 + 챗 예약값 소비.
    #   Streamlit은 '위젯 생성 후' 그 key를 수정하면 예외를 던지므로, 반드시 생성 직전에 적용한다.
    if "_pending_threshold" in st.session_state:
        st.session_state["th_slider"] = float(st.session_state.pop("_pending_threshold"))
    if "th_slider" not in st.session_state:
        st.session_state["th_slider"] = 0.5
    threshold=st.slider(t("sb.threshold_label"),0.0,1.0,step=0.01,key="th_slider",help=t("sb.threshold_help"))
    # ⚖️ 임계값 변경 → 탐지 이력 기반 판정 재계산 미리보기
    _thist = st.session_state.get('det_history') or []
    if _thist:
        def _now_anom(r):
            return str(r.get('type','m'))!='m' or float(r.get('risk_score',0))>=threshold
        _n_anom = sum(1 for r in _thist if _now_anom(r))
        _n_flip = sum(1 for r in _thist if bool(r.get('is_anomaly')) != _now_anom(r))
        _flip_txt = t("sb.hist_flip", n=_n_flip) if _n_flip else t("sb.hist_no_change")
        st.markdown(f'<div style="color:{T["text_muted"]};font-size:10.5px;margin:-6px 0 4px;line-height:1.5">{t("sb.hist_recalc", n=len(_thist), anom=_n_anom, normal=len(_thist)-_n_anom, flip=_flip_txt)}</div>', unsafe_allow_html=True)
    # ── ✨ v9.1: 📮 이중 임계값 발송 — 위험도 구간별 채널·메시지 이원화 ──
    st.session_state['dual_threshold'] = st.toggle(tt("sb.dual_toggle"),
        value=bool(st.session_state.get('dual_threshold', False)),
        key="tg_dual_th", help=tt("sb.dual_help"))
    if st.session_state['dual_threshold']:
        _t1 = st.slider(tt("sb.th1_label"), 0.0, 1.0,
                        float(st.session_state.get('th_review', 0.6)), 0.01, key="sl_th_review")
        _t2 = st.slider(tt("sb.th2_label"), 0.0, 1.0,
                        float(st.session_state.get('th_confirm', 0.8)), 0.01, key="sl_th_confirm")
        st.session_state['th_review'] = float(_t1)
        st.session_state['th_confirm'] = float(_t2)
        if _t2 < _t1:
            st.markdown(f'<div style="color:{T["amber"]};font-size:10.5px;line-height:1.5">{tt("sb.dual_swap_warn", t2=max(_t1,_t2))}</div>', unsafe_allow_html=True)
        _t2e = max(_t1, _t2)
        st.markdown(f'<div style="color:{T["text_muted"]};font-size:10.5px;margin:2px 0 6px;line-height:1.6">{tt("sb.dual_rule_note", t1=_t1, t2=_t2e)}</div>', unsafe_allow_html=True)
    rag_k=st.slider(t("sb.rag_label"),1,5,3)

    # ── 🧠 전역 탐지 모델 (세션 04 합성 QA · 05 실시간 탐지 공용) ──
    cbr()
    sb_section(t("sb.model_section"))
    _gm = get_available_models()
    _gm_names = list(_gm.keys())
    # 🎛 최초 진입 시 1회: 설정된 기본 탐지 모델을 자동 선택 (이후 사용자 변경은 그대로 유지)
    if not st.session_state.get('_detect_model_default_applied'):
        # ✨ v10: 배포 번들이 있으면 그걸 기본으로 (조각 매칭 실패 시 default_model_name 폴백)
        _pref_gm = _pick_model_key(_gm, DEFAULT_DETECT_MODEL_MATCH) or default_model_name(_gm)
        if _pref_gm:
            st.session_state['selected_model'] = _pref_gm
        st.session_state['_detect_model_default_applied'] = True
    _gi = _gm_names.index(st.session_state['selected_model']) if st.session_state['selected_model'] in _gm_names else 0
    _gsel = st.selectbox(t("sb.model_select_label"), _gm_names, index=_gi, key="model_sel_global",
                         label_visibility="collapsed",
                         format_func=lambda x: model_display_name(x, LANG),
                         help=t("sb.model_select_help"))
    if _gsel != st.session_state['selected_model']:
        st.session_state['selected_model'] = _gsel
    _gmi = _gm.get(_gsel, {}); _gex = Path(_gmi.get("path","")).exists()
    # 🐛 FIX: f-string 표현식 내 백슬래시는 Python 3.12+ 전용 문법 → 3.11 이하 호환 위해 사전 조립
    if _gex:
        _gbadge = f'<span style="color:{T["green"]}">{t("sb.model_loadable")}</span>'
    else:
        _gbadge = f'<span style="color:{T["red"]}">{t("sb.model_missing")}</span>'
    st.markdown(f'<div style="color:{T["text_muted"]};font-size:10.5px;font-family:var(--font-mono);margin-top:-4px">{_gbadge} · {_gmi.get("path","-")}</div>', unsafe_allow_html=True)
    # ── 📂 평가 데이터셋 선택 (세션 2·3 공용) ──
    #   ✨ v18: 사이드바에서 '📁 데이터 경로'(train/test) 섹션과 '데이터 폴더' 입력을 제거하고
    #     ⋮ 설정 팝오버로 이주했다. 매일 만질 값이 아니라 한 번 정하면 고정되는 값이라,
    #     사이드바 상단의 귀한 세로 공간을 차지할 이유가 없다.
    #     세션상태에 남기므로 기존 참조(train_path/test_path/ds_folder)는 그대로 동작한다.
    cbr()
    sb_section(tt("ds.section"))
    train_path = st.session_state.setdefault('cfg_train_path', 'data/train.csv')
    test_path  = st.session_state.setdefault('cfg_test_path',  'data/test.csv')
    ds_folder  = st.session_state.setdefault('ds_folder',      'data/')
    _ds_found = _discover_ds(ds_folder)
    if _ds_found:
        _ds_names = list(_ds_found.keys())
        # 🎛 기본 선택: 설정값(DEFAULT_DATASET_MATCH) 우선 → 없으면 첫 '라벨 보유' 데이터셋으로 폴백
        _default_ds = _pick_key(_ds_names, DEFAULT_DATASET_MATCH) \
            or next((n for n in _ds_names if _ds_found[n].has_label), _ds_names[0])
        _cur_ds = st.session_state.get('selected_dataset', _default_ds)
        _di = _ds_names.index(_cur_ds) if _cur_ds in _ds_names else 0
        if "_pending_dataset" in st.session_state:   # ✨ v15 에이전트 데이터셋 변경(부분매칭)
            _pd = str(st.session_state.pop("_pending_dataset")).lower()
            _hit = next((n for n in _ds_names if _pd in n.lower()), None)
            if _hit:
                st.session_state["ds_sel_global"] = _hit
                _di = _ds_names.index(_hit)
        _ds_sel = st.selectbox(tt("ds.select_label"), _ds_names, index=_di, key="ds_sel_global",
                               format_func=lambda x: f"{'🏷️' if _ds_found[x].has_label else '❔'} {x}")
        st.session_state['selected_dataset'] = _ds_sel
        st.caption(_ds_found[_ds_sel].note)
    else:
        st.caption(tt("ds.none_found"))

    # 🔧 FIX(v8.10): 누출 경고 토글을 팝오버 → 사이드바로 이주 (팝오버 위젯 상태 quirk 제거).
    if 'show_leak_warn' not in st.session_state: st.session_state['show_leak_warn'] = False
    def _sync_leak_warn():
        st.session_state['show_leak_warn'] = bool(st.session_state.get('show_leak_warn_sb', True))
    st.toggle(tt("nav.leak_warn_toggle"), value=bool(st.session_state['show_leak_warn']),
              key="show_leak_warn_sb", help=tt("nav.leak_warn_help"), on_change=_sync_leak_warn)

    cbr()
    sb_section(t("sb.voice_section"))  # ✨ v7: i18n 적용
    _tts_voices = {"ko":"한국어","en":"English","ja":"日本語","zh":"中文"}
    st.selectbox(t("sb.tts_lang_label"), list(_tts_voices.keys()), index=0, key="tts_lang", format_func=lambda x: _tts_voices[x])
    st.toggle(t("sb.alarm_toggle"), value=True, key="alarm_on")

    cbr()
    eval_data=load_eval_result()
    if eval_data:
        try:
            _best_name = eval_data.get("best_model") or next(iter(eval_data["model_comparison"]))
            _bm = eval_data["model_comparison"][_best_name]
            # ✨ v8.12: 주 지표 = µF1(사기 한정) — 구 결과 파일엔 없으므로 macro 폴백
            best_f1 = _bm.get("micro_f1_fraud", _bm.get("macro_f1", 0.0))
            _f1_tag = "µF1" if "micro_f1_fraud" in _bm else "F1"
        except (KeyError, TypeError, StopIteration):
            _best_name, best_f1, _f1_tag = "LightGBM", 0.0, "F1"
        # ✨ v7: 커스텀 박스 → kpi_card 컴포넌트 재사용 (스파인·호버·광원 등 디자인 시스템 상속)
        kpi_card(t("sb.model_status_title"), f"{_f1_tag} {best_f1:.4f}", t("sb.model_status_features", name=_best_name), "🎯", T['accent'])

    # ── 테마/OS 감지 — 구 UI 전용 (신 UI는 우측 상단 ⋮에서 다크/라이트 전환) ──
    if not IS_NEW_UI:
        # ── 테마 선택기 ──────────────────────────────────────
        cbr()
        sb_section(t("sb.theme_section"))
        theme_names = list(THEMES.keys())
        current_idx = theme_names.index(st.session_state['theme_name']) if st.session_state['theme_name'] in theme_names else 0
        selected_theme = st.selectbox(
            t("sb.theme_select_label"),
            theme_names,
            index=current_idx,
            format_func=lambda x: f"{x}  —  {THEMES[x]['label']}",
            label_visibility="collapsed",
            key="theme_selector",
        )
        if selected_theme != st.session_state['theme_name']:
            st.session_state['theme_name'] = selected_theme
            st.rerun()

        # 테마 미리보기 스와치
        swatch_html = ""
        for tn, tv in THEMES.items():
            is_active = "2px solid " + tv['accent'] if tn == st.session_state['theme_name'] else "1px solid " + tv['text_muted']
            # 배경 밝기 감지 → 밝은 테마는 검정 텍스트
            bg_hex = tv["bg_card"].lstrip('#')
            bg_lum = (int(bg_hex[0:2],16)*299 + int(bg_hex[2:4],16)*587 + int(bg_hex[4:6],16)*114) / 1000
            txt_color = "#1a1a2e" if bg_lum > 140 else tv["text_secondary"]
            swatch_html += f'<div style="display:inline-flex;align-items:center;gap:6px;margin:3px 0;padding:5px 10px;border-radius:6px;background:{tv["bg_card"]};border:{is_active}"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{tv["accent"]}"></span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{tv["red"]}"></span><span style="font-size:10px;color:{txt_color}!important;font-family:JetBrains Mono">{tn.split(" ",1)[1] if " " in tn else tn}</span></div><br>'
        st.markdown(swatch_html, unsafe_allow_html=True)

        # ── OS 다크/라이트 모드 자동 감지 ─────────────────────
        import streamlit.components.v1 as _comp_theme
        _comp_theme.html(f"""<script>
        (function(){{
          var d=window.parent.document;
          if(d.__themeDetect)return;d.__themeDetect=true;
          // OS 다크모드 감지 → session_state에 반영
          try{{
            var isDark=window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches;
            // 부모 프레임 감지용 데이터 속성 설정
            d.body.dataset.osDarkMode=isDark?'true':'false';
          }}catch(e){{}}
        }})();
        </script>""", height=0)
        if st.button(t("sb.os_detect_button"), key="auto_theme_detect", width='stretch', help=t("sb.os_detect_help")):
            # 간단한 휴리스틱: 현재 테마가 라이트면 다크로, 다크면 라이트로
            current_bg = T['bg_base'].lstrip('#')
            current_lum = (int(current_bg[0:2],16)*299 + int(current_bg[2:4],16)*587 + int(current_bg[4:6],16)*114) / 1000
            if current_lum > 140:
                # 현재 라이트 → 다크 추천
                st.session_state['theme_name'] = "🌊 Cyber Teal"
            else:
                # 현재 다크 → 라이트 추천
                st.session_state['theme_name'] = "🏔️ Arctic Frost"
            st.rerun()

    # ✨ v15 (요청 3): 온보딩 안내 다시 보기
    _ob1, _ob2 = st.columns([1, 1])
    if _ob2.button(t("kbd.modal_title"), key="sb_kbd_open", width='stretch',
                   help=t("kbd.k_help")):
        st.session_state["_kbd_open"] = True; st.rerun()
    if _ob1.button(t("onb.reopen_short"), key="sb_onb_reopen", width='stretch',
                   help=t("onb.reopen_help")):
        st.session_state["_onboard_open"] = True
        st.rerun()

    # ── API 키 오버라이드 (대시보드 입력값 > .env) ───────
    cbr()
    with st.expander(t("sb.api_key_expander")):
        st.markdown(f'<p style="color:{T["text_muted"]};font-size:10px">{t("sb.api_key_hint")}</p>',unsafe_allow_html=True)
        st.session_state['ov_llama_url'] = st.text_input("llama.cpp URL", st.session_state.get('ov_llama_url','http://localhost:8080/v1/chat/completions'), key="sb_llama_url", placeholder="http://localhost:8080/v1/chat/completions")
        st.session_state['ov_model_name'] = st.text_input("모델 이름 (선택한 제공자 공통)", st.session_state.get('ov_model_name',''), key="sb_model_name", placeholder="예: claude-sonnet-4-6 · gpt-4o-mini · gemma-3-12b (비워두면 제공자 기본값)")
        st.session_state['ov_anthropic_key'] = st.text_input("Anthropic API Key", st.session_state.get('ov_anthropic_key',''), key="sb_anth_key", type="password")
        st.session_state['ov_openai_key'] = st.text_input("OpenAI API Key", st.session_state.get('ov_openai_key',''), key="sb_oai_key", type="password")
        st.session_state['ov_deepseek_key'] = st.text_input("DeepSeek API Key", st.session_state.get('ov_deepseek_key',''), key="sb_ds_key", type="password")
        st.session_state['ov_custom_key'] = st.text_input(t("common.custom_api_key_label"), st.session_state.get('ov_custom_key',''), key="sb_cu_key", type="password", help=t("sb.custom_key_help"))
        st.markdown(f'<p style="color:{T["text_muted"]};font-size:10px;margin-top:12px">{t("sb.notify_section")}</p>',unsafe_allow_html=True)
        st.session_state['ov_slack_webhook'] = st.text_input("Slack Webhook URL", st.session_state.get('ov_slack_webhook',''), key="sb_slack_wh", type="password")
        st.session_state['ov_smtp_user'] = st.text_input("SMTP User (Gmail)", st.session_state.get('ov_smtp_user',''), key="sb_smtp_u")
        st.session_state['ov_smtp_pass'] = st.text_input("SMTP Password", st.session_state.get('ov_smtp_pass',''), key="sb_smtp_p", type="password")


    # ✨ v18: 빌드 정보는 사이드바 최하단 — 정보성 캡션이 조작 위젯보다 위에 있을 이유가 없다
    cbr()
    st.caption(f"🏗️ dashboard build {DASH_VERSION}")
# ── 파이프라인 오버라이드 헬퍼 ────────────────────────────
def _build_llm_analyzer():
    """대시보드 설정값 우선, 없으면 .env fallback"""
    from pipeline.llm_analyzer import LLMAnalyzer
    provider = st.session_state.get('llm_p5', 'local')
    key_map = {
        'anthropic': st.session_state.get('ov_anthropic_key',''),
        'openai':    st.session_state.get('ov_openai_key',''),
        'deepseek':  st.session_state.get('ov_deepseek_key',''),
        'moonshot':  st.session_state.get('ov_moonshot_key',''),
        'custom':    st.session_state.get('ov_custom_key',''),
    }
    api_key = key_map.get(provider, '') or None
    llama_url = st.session_state.get('ov_llama_url','') or None
    # 🛡 FIX(v9): '로컬이면 마스킹 생략(pii_skip_local)' 상태에서 llama.cpp 실패 시
    #   Anthropic으로 자동 폴백되며 미마스킹 원문이 외부 전송되던 개인정보 유출 경로 차단.
    _no_cloud_fb = (provider == 'local' and st.session_state.get('pii_skip_local', True))
    return LLMAnalyzer(
        max_tokens=512,
        llama_cpp_url=llama_url,
        model=st.session_state.get('ov_model_name','') or None,
        provider=provider,
        api_key=api_key,
        custom_url=st.session_state.get('ov_custom_url','') or None,
        custom_model=st.session_state.get('ov_custom_model','') or None,
        cloud_fallback=not _no_cloud_fb,
        # 🖊 v13/v14: 프롬프트 편집기(세션5 환경설정) 오버라이드 — 값이 있는 슬롯만 적용됨.
        #   'batch'는 llm_analyzer.analyze()가 아니라 batch_analyzer.run_batch()가 이 dict를
        #   analyzer.prompt_overrides로 그대로 읽어 사용(단일 저장소 공유, 새 배선 불필요).
        prompt_overrides={
            'analysis': st.session_state.get('prompt_ov_analysis', ''),
            'slack':    st.session_state.get('prompt_ov_slack', ''),
            'email':    st.session_state.get('prompt_ov_email', ''),
            'batch':    st.session_state.get('prompt_ov_batch', ''),
        },
    )

def _build_notifier():
    """대시보드 설정값 우선, 없으면 .env fallback"""
    from pipeline.notifier import Notifier
    return Notifier(
        smtp_user=st.session_state.get('ov_smtp_user','') or None,
        smtp_pass=st.session_state.get('ov_smtp_pass','') or None,
        slack_webhook_url=st.session_state.get('ov_slack_webhook','') or None,
    )

def _effective_notify_email():
    """🔧 FIX(v8.2): 수신 주소 우선순위 — 대시보드 입력 > .env FDS_NOTIFY_EMAIL > SMTP_USER(발신자).
    기존 st.session_state.get('notify_email', os.getenv(...))는 위젯이 존재하는 한 키가 항상
    있어서(빈 문자열) env 폴백이 절대 실행되지 않던 죽은 코드였음 — or 체인으로 교정."""
    return ((st.session_state.get('notify_email') or '').strip()
            or os.getenv('FDS_NOTIFY_EMAIL', '').strip()
            or (st.session_state.get('ov_smtp_user') or '').strip()
            or os.getenv('SMTP_USER', '').strip())

def _agent_send_now(det, ch, thr):
    """✨ v19: 승인 게이트 OFF일 때 에이전트 요청을 즉시 발송한다.

    ⚠️ 이 경로는 **되돌릴 수 없다.** 기본값은 게이트 ON이며, 사용자가 명시적으로
      '⚡ 즉시 발송' 토글을 켰을 때만 여기로 들어온다.
      게이트를 껐더라도 다음 두 가지는 유지된다:
        ① PII 마스킹은 그대로 적용 (컴포저 내부에서 처리)
        ② 발송 결과와 대상을 채팅 답변·감사 로그(_send_audit)에 남긴다
      마스킹이 'off'인 상태에서 게이트까지 꺼져 있으면 경고를 함께 반환한다.
    """
    notes, results = [], []
    _nn = _build_notifier()
    _tier = _notify_tier(det.get('risk_score', 0))
    _to = _effective_notify_email()
    if ch in ('slack', 'both'):
        _ok = _nn.send_slack(_compose_slack_single(det, thr, tier=_tier))
        results.append(("Slack", _ok, _nn.last_error))
    if ch in ('email', 'both'):
        if not _to:
            results.append(("Email", False, t("s5.send_confirm_to_none")))
        else:
            _pb, _ph, _pa = _compose_email_single(det, thr, tier=_tier)
            _ok = _nn.send_email(_to, _tier_subject(_tier, det.get('fraud_type', '?'),
                                                    det.get('risk_score', 0)),
                                 _pb, html=_ph, attachments=_pa)
            results.append(("Email", _ok, _nn.last_error))
    for _nm, _ok, _err in results:
        notes.append(t("chat.act_sent_now_ok", ch=_nm) if _ok
                     else t("chat.act_sent_now_fail", ch=_nm, e=str(_err)[:90]))
    if st.session_state.get('pii_mask_level', 'standard') == 'off':
        notes.append(t("chat.act_sent_now_unmasked"))
    # 감사 로그 — 누가·언제·무엇을 게이트 없이 보냈는지 남긴다
    st.session_state.setdefault('_send_audit', []).append({
        "at": time.strftime("%H:%M:%S"), "ch": ch,
        "ft": det.get('fraud_type', '?'), "risk": float(det.get('risk_score', 0) or 0),
        "to": _to, "mask": st.session_state.get('pii_mask_level', 'standard'),
        "ok": all(r[1] for r in results) if results else False,
    })
    return notes


# ── ✨ v8: 리치 알림 컴포저 — Slack 텍스트 시각화 / Email KPI+HTML리포트 첨부 ──
def _rich_on():
    return st.session_state.get('rich_notify', True)

def _leak_alert(i18n_key):
    """🔧 v8.10: 누출 배너 단일 관문 — 스위치 OFF면 배너 대신 🔕 흔적 캡션."""
    if st.session_state.get('show_leak_warn', False):
        alert_box(t(i18n_key), "error")
    elif not CV:   # v9.6: 컴팩트(발표)에선 '숨김 상태' 흔적 캡션도 생략
        st.caption(tt("nav.leak_muted"))

def _notif_L():
    """notify_visuals에 전달할 현재 언어 라벨 묶음 (기존 i18n 키 최대 재사용)"""
    return {
        'risk': t('notif.risk'), 'thr': t('notif.thr'), 'prob': t('notif.prob_top'),
        'model': t('s5.h_model'), 'cnt': t('notif.cnt'),
        'total': t('s5.batch_kpi_total'), 'anomaly': t('s5.batch_kpi_anomaly'),
        'avg': t('s5.batch_kpi_avg'), 'max': t('s5.batch_kpi_max'),
        'risk_dist': t('notif.risk_dist'), 'type_dist': t('notif.type_dist'),
        'verdict': t('s5.h_verdict'), 'type': t('s5.th_pred_type'),
        'anom': t('s5.verdict_anomaly'), 'norm': t('s5.verdict_normal'),
        'attached': t('notif.attached'), 'auto_note': t('notif.auto_note'),
        'masked': t('notif.masked'), 'analysis': t('notif.analysis'),
        'verdicts': t('notif.verdicts'),
    }

# ── ✨ v9.1: 이중 임계값 발송 등급 ─────────────────────────
def _notify_tier(risk_score):
    """이중 임계값 모드의 발송 등급 결정.
    returns:
      'single'  — 이중 모드 OFF: 기존 단일 임계값 동작 그대로
      'confirm' — 위험도 ≥ 2차: Slack+Email 동시 · 확정 통보 (기존 확신성 메시지)
      'review'  — 1차 ≤ 위험도 < 2차: Slack만 · 담당자 추가 검토 요청
      'none'    — 위험도 < 1차: 자동 발송 생략
    ※ 2차 < 1차로 잘못 설정된 경우 2차=max(1차,2차)로 보정."""
    if not st.session_state.get('dual_threshold', False):
        return 'single'
    _t1 = float(st.session_state.get('th_review', 0.6))
    _t2 = max(float(st.session_state.get('th_confirm', 0.8)), _t1)
    _r = float(risk_score or 0)
    if _r >= _t2:
        return 'confirm'
    if _r >= _t1:
        return 'review'
    return 'none'

def _tier_head(tier, risk_score):
    """등급별 메시지 머리말 — review(의심·검토요청) / confirm(확정·즉시대응)."""
    _t1 = float(st.session_state.get('th_review', 0.6))
    _t2 = max(float(st.session_state.get('th_confirm', 0.8)), _t1)
    if tier == 'review':
        return tt("notif.tier_review_head", r=float(risk_score or 0), t1=_t1)
    if tier == 'confirm':
        return tt("notif.tier_confirm_head", r=float(risk_score or 0), t2=_t2)
    return ""

def _tier_subject(tier, fraud_type, risk_score):
    """등급별 이메일 제목 — single이면 기존 제목 유지."""
    _ft = str(fraud_type or '?').upper()
    if tier == 'review':
        return tt("notif.subject_review", ft=_ft, r=float(risk_score or 0))
    if tier == 'confirm':
        return tt("notif.subject_confirm", ft=_ft, r=float(risk_score or 0))
    return tt("notif.subject_single", ft=_ft)

def _compose_slack_single(det, threshold, tier="single"):
    txt = (det.get('llm') or {}).get('slack', '')
    _hd = _tier_head(tier, det.get('risk_score', 0))   # ✨ v9.1: 등급 머리말 (single이면 빈 문자열)
    if _hd:
        txt = _hd + "\n\n" + txt
    if not _rich_on():
        return txt
    try:
        from pipeline.notify_visuals import slack_visual_single
        L = _notif_L(); L['prob'] = t('notif.prob')
        _ft = str(det.get('fraud_type', '?'))
        head = slack_visual_single(L, _ft, FRAUD_SHORT.get(_ft, _ft),
                                   det.get('risk_score', 0), float(threshold),
                                   det.get('proba_dict'), str(det.get('model', '')))
        return head + "\n" + txt
    except Exception as e:
        log.warning(f"리치 Slack 구성 실패 → 기본 텍스트로 발송: {e}")
        return txt

def _compose_email_single(det, threshold, tier="single"):
    """→ (plain_body, html|None, attachments|None). 리치 OFF/실패 시 기존 동작 유지."""
    llm = det.get('llm') or {}
    raw = llm.get('email', '')
    _hd = _tier_head(tier, det.get('risk_score', 0))   # ✨ v9.1: 등급 머리말 (single이면 빈 문자열)
    if _hd:
        raw = _hd + "\n\n" + raw
    if not _rich_on():
        return raw, None, None
    try:
        from pipeline.notify_visuals import (email_html_single, wrap_email,
                                             report_html_single, html_to_text)
        L = _notif_L()
        _ft = str(det.get('fraud_type', '?'))
        kpi = email_html_single(L, _ft, FRAUD_SHORT.get(_ft, _ft), bool(det.get('is_anomaly')),
                                det.get('risk_score', 0), float(threshold),
                                det.get('proba_dict'), str(det.get('model', '')))
        html_doc = wrap_email(L, t('notif.report_title_single'), kpi, raw, attached_note=True)
        # ⚠ 첨부 리포트는 반드시 강제 마스킹 데이터만 사용 (이메일 = 유출 최다 매체)
        _clean = {k: v for k, v in (det.get('row') or {}).items() if not str(k).startswith('_')}
        try:
            _masked = _build_masker_forced().mask_row(_clean)
        except Exception:
            _masked = {}
        rep = report_html_single(L, t('notif.report_title_single'), _ft, FRAUD_SHORT.get(_ft, _ft),
                                 bool(det.get('is_anomaly')), det.get('risk_score', 0), float(threshold),
                                 det.get('proba_dict') or {}, str(det.get('model', '')),
                                 _masked, llm.get('analysis', ''))
        atts = [(f"fds_report_{_ft}_{time.strftime('%H%M%S')}.html", rep, "text/html")]
        return (html_to_text(raw) or raw), html_doc, atts
    except Exception as e:
        log.warning(f"리치 Email 구성 실패 → 기본 본문으로 발송: {e}")
        return raw, None, None

def _batch_type_counts(bres):
    tc = {}
    for r in getattr(bres, 'rows_out', []) or []:
        if r.get('is_anomaly'):
            k = str(r.get('fraud_type', '?'))
            tc[k] = tc.get(k, 0) + 1
    return tc

def _compose_slack_batch(bres):
    txt = getattr(bres, 'slack', '')
    if not _rich_on():
        return txt
    try:
        from pipeline.notify_visuals import slack_visual_batch
        risks = [r.get('risk_score', 0) for r in getattr(bres, 'rows_out', []) or []]
        head = slack_visual_batch(_notif_L(), bres.total, bres.anomaly_count,
                                  bres.avg_risk, bres.max_risk, risks, _batch_type_counts(bres))
        return head + "\n" + txt
    except Exception as e:
        log.warning(f"리치 Slack(배치) 구성 실패 → 기본 텍스트로 발송: {e}")
        return txt

def _compose_email_batch(bres):
    raw = getattr(bres, 'email', '')
    if not _rich_on():
        return raw, None, None
    try:
        from pipeline.notify_visuals import (email_html_batch, wrap_email,
                                             report_html_batch, html_to_text)
        L = _notif_L()
        tc = _batch_type_counts(bres)
        risks = [r.get('risk_score', 0) for r in getattr(bres, 'rows_out', []) or []]
        kpi = email_html_batch(L, bres.total, bres.anomaly_count, bres.avg_risk, bres.max_risk, tc)
        html_doc = wrap_email(L, t('notif.report_title_batch'), kpi, raw, attached_note=True)
        # rows_out은 판정 결과만 담고 있어(원거래 PII 없음) 리포트 표에 안전
        rep = report_html_batch(L, t('notif.report_title_batch'), bres.total, bres.anomaly_count,
                                bres.avg_risk, bres.max_risk, risks, tc,
                                getattr(bres, 'rows_out', []) or [], getattr(bres, 'analysis', ''))
        atts = [(f"fds_batch_report_{time.strftime('%H%M%S')}.html", rep, "text/html")]
        return (html_to_text(raw) or raw), html_doc, atts
    except Exception as e:
        log.warning(f"리치 Email(배치) 구성 실패 → 기본 본문으로 발송: {e}")
        return raw, None, None

@st.cache_resource(show_spinner=t("common.rag_index_spinner"))
def _get_rag_cached(top_k):
    """⚡ RAGSearcher 캐시 — KR-SBERT 임베딩 모델을 매 분석마다 재로딩하지 않도록.
    (기존: 분석할 때마다 'Loading weights 199/199' 재발생 → 수 초~수십 초 낭비)"""
    from pipeline.rag_searcher import RAGSearcher
    return RAGSearcher(top_k=top_k)

def _build_rag(top_k=3):
    return _get_rag_cached(top_k)

def _do_llm_analysis(det, row_data, fraud_type, risk_score, rag_k, threshold):
    """LLM 분석 실행 + 자동 발송 처리 — 별도 호출용"""
    try:
        clean_row = {k:v for k,v in row_data.items() if not k.startswith('_')}
        masker = _build_masker(); masked_row = masker.mask_row(clean_row)
        fraud_name = FRAUD_TYPE_DETAILS.get(fraud_type, {}).get('name', fraud_type)
        rag = _build_rag(rag_k); anlz = _build_llm_analyzer()
        rag_ctx = rag.search(f"사기유형 {fraud_type} {fraud_name} 이상거래 탐지 원인 분석", fraud_type)
        raw_r = anlz.analyze(masked_row, fraud_type, risk_score, rag_ctx, lang=LANG)
        if isinstance(raw_r, str):
            det['llm'] = {"analysis": raw_r, "slack": raw_r[:500], "email": raw_r}
        elif isinstance(raw_r, dict):
            det['llm'] = raw_r
        else:
            det['llm'] = {"analysis": str(raw_r), "slack": str(raw_r)[:500], "email": str(raw_r)}
        # ── 진단 정보는 det에 저장 (메인 렌더링에서 표시) ──
        # ※ 이 함수 내부에서 st.warning/st.info 등 Streamlit 위젯을 직접 생성하면
        #    st.rerun() 후 위젯 key 충돌(DuplicateWidgetID)이 발생하므로,
        #    데이터만 저장하고 표시는 메인 렌더 루프에 위임한다.
        det['_llm_diag'] = det['llm'].get('_diag', {})
        det.pop('llm_error', None)
        # 자동 발송
        # 🐛 FIX(v5): Notifier는 실패 시 예외가 아니라 False를 반환 →
        #   기존 '예외 없으면 True' 방식은 웹훅 미설정/발송 실패에도 "발송 완료" 뱃지 표시.
        #   반환값(ok)을 그대로 기록하고, 수신 이메일 미설정 시 발송 시도 자체를 건너뜀.
        if 'llm' in det:
            # ── ✨ v9.1: 이중 임계값 발송 이원화 ──
            #   single: 기존 동작 · review: Slack만(검토요청) · confirm: Slack+Email(확정통보) · none: 생략
            _tier = _notify_tier(det.get('risk_score', risk_score))
            det['notify_tier'] = _tier
            _slack_go = st.session_state.get('auto_slack', False) and _tier != 'none'
            _email_go = st.session_state.get('auto_email', False) and _tier in ('single', 'confirm')
            if _slack_go:
                try:
                    _nn = _build_notifier()
                    ok = _nn.send_slack(_compose_slack_single(det, threshold, tier=_tier))
                    det['auto_slack_sent'] = bool(ok)
                    if not ok: det['notify_error_slack'] = getattr(_nn, 'last_error', '')
                except Exception:
                    det['auto_slack_sent'] = False
            if _email_go:
                try:
                    _to = _effective_notify_email()   # 🔧 FIX(v8.2): 빈 입력칸 → .env 폴백 복원
                    if not _to:
                        log.warning("수신 이메일 미설정 — .env에 FDS_NOTIFY_EMAIL 또는 대시보드에서 설정 필요")
                        det['auto_email_sent'] = False
                    else:
                        _pb, _ph, _pa = _compose_email_single(det, threshold, tier=_tier)
                        _nn = _build_notifier()
                        ok = _nn.send_email(_to, _tier_subject(_tier, fraud_type, det.get('risk_score', risk_score)), _pb, html=_ph, attachments=_pa)
                        det['auto_email_sent'] = bool(ok)
                        if not ok: det['notify_error_email'] = getattr(_nn, 'last_error', '')
                except Exception:
                    det['auto_email_sent'] = False
    except Exception as e:
        det['llm_error'] = str(e)

def _llm_lang_suffix():
    """🌐 UI 언어가 한국어가 아니면 LLM에 해당 언어로 응답하도록 지시문을 추가합니다.
    (RAG 지식베이스·기본 분석 프롬프트는 한국어 코퍼스 기반이라 그대로 유지)
    ✨ v9.3: 지시문 문구를 i18n_data.llm_lang_directive로 일원화(단일 소스)."""
    return llm_lang_directive(LANG)

def _redo_llm_step(det, row_data, fraud_type, risk_score, rag_k, step):
    """단일 단계(analysis/slack/email)만 재분석. det['llm']을 직접 갱신."""
    try:
        clean_row = {k:v for k,v in row_data.items() if not k.startswith('_')}
        masker = _build_masker(); masked_row = masker.mask_row(clean_row)
        fraud_name = FRAUD_TYPE_DETAILS.get(fraud_type, {}).get('name', fraud_type)
        anlz = _build_llm_analyzer()
        llm_result = det.get('llm', {})
        existing_analysis = llm_result.get('analysis', '')

        if step == "analysis":
            rag = _build_rag(rag_k)
            rag_ctx = rag.search(f"사기유형 {fraud_type} {fraud_name} 이상거래 탐지 원인 분석", fraud_type)
            full = anlz.analyze(masked_row, fraud_type, risk_score, rag_ctx, lang=LANG)
            # 🐛 FIX: analyze()가 dict가 아닌 str을 반환할 수 있음 → .get() AttributeError 방지
            if isinstance(full, dict):
                llm_result['analysis'] = full.get('analysis', existing_analysis)
                llm_result['_diag'] = full.get('_diag', {})
            elif isinstance(full, str) and full.strip():
                llm_result['analysis'] = full
        elif step == "slack":
            p_slack = (f"아래 FDS 분석 결과를 Slack 알림 2줄로 요약해주세요. "
                       f"첫 줄: 위험 레벨 이모지 + 유형 + 거래 요약, "
                       f"둘째 줄: 위험점수 + 조치 필요:\n\n{existing_analysis[:400]}")
            p_slack += _llm_lang_suffix()
            result = anlz._call(p_slack, max_tokens=200, timeout=45)
            if result:
                llm_result['slack'] = result
        elif step == "email":
            _tx_id = masked_row.get('ID', masked_row.get('transaction_id', 'N/A'))
            _amount = masked_row.get('Transaction_Amount', 'N/A')
            _channel = masked_row.get('Channel', 'N/A')
            p_email = (
                f"아래 FDS 탐지 결과를 담당자에게 보낼 공식 이메일로 작성하세요.\n"
                f"마크다운 기호 절대 사용하지 마세요. 순수 텍스트만 출력하세요.\n"
                f"제목: [FDS 긴급] {fraud_type.upper()}형 이상거래 탐지 (거래ID: {_tx_id})\n\n"
                f"담당자 귀중,\nFDS 시스템에서 이상거래를 탐지하였습니다.\n\n"
                f"사기 유형: {fraud_type.upper()}형 / 위험 점수: {risk_score:.4f}\n"
                f"거래 ID: {_tx_id} / 금액: {_amount}원 / 채널: {_channel}\n\n"
                f"AI 분석 결과:\n{existing_analysis}\n\n"
                f"본 메일은 FDS 자동화 시스템에 의해 발송되었습니다.")
            p_email += _llm_lang_suffix()
            result = anlz._call(p_email, max_tokens=1536, timeout=180)
            if result:
                llm_result['email'] = result
        det['llm'] = llm_result
    except Exception as e:
        st.toast(t("common.redo_step_fail_toast", step=step, e=e))

class _DummyMasker:
    """pii_masker 미설치 시 사용하는 무동작 마스커"""
    level = "off"
    def mask_row(self, row): return dict(row)
    def mask_text(self, text): return text
    def get_log(self): return []

def _make_masker(level):
    try:
        from pipeline.pii_masker import PIIMasker
        return PIIMasker(level=level)
    except ImportError:
        return _DummyMasker()

def _build_masker():
    """PII 마스커 생성 — 로컬 스킵 / 미설치 시 더미 반환"""
    level = st.session_state.get('pii_mask_level', 'standard')
    skip_local = st.session_state.get('pii_skip_local', True)
    provider = st.session_state.get('llm_p5', 'local')
    if skip_local and provider == "local":
        level = "off"
    return _make_masker(level)

def _build_masker_forced():
    """강제 마스킹 (로컬 스킵 무시 — 마스킹 미리보기 용)"""
    return _make_masker(st.session_state.get('pii_mask_level', 'standard'))

# ══════════════════════════════════════════════════════════
# 🧾 v11: 화면 스냅샷 저장소 — "단일 진실 공급원(single source of truth)"
#   각 세션 렌더 블록이 '화면에 실제로 그리는 데 쓴' 변수 그대로 텍스트 요약을 만들어
#   여기 저장하고, _chat_context()는 그 저장된 텍스트를 그대로 읽기만 한다(재계산 안 함).
#   → _chat_context가 독자적으로 데이터를 다시 불러와 계산하다가 화면과 다른 값을 보여주거나,
#     세션 게이트를 깜빡해 엉뚱한 세션 정보가 섞여드는 부류의 버그(이번 세션2 사고)를
#     구조적으로 차단한다 — current_session과 다른 키는 애초에 조회하지 않으므로.
#   저장은 매 rerun 렌더 시점에 값을 "덮어쓰기"하므로 항상 이번 실행에서 그린 최신값이다.
# ══════════════════════════════════════════════════════════
def _snap_set(session_key: str, lines: list[str]):
    """세션 렌더 블록에서 호출 — 화면에 그린 값 그대로 텍스트 줄 목록을 저장."""
    st.session_state.setdefault('_screen_snap', {})[session_key] = list(lines or [])

def _snap_get(session_key: str):
    """_chat_context()에서 호출 — 저장된 스냅샷(없으면 None)을 읽기만 함."""
    return st.session_state.get('_screen_snap', {}).get(session_key) or None

def _format_eval_lines(_ev, _dyn_note: str = "") -> list[str]:
    """세션2 모델 평가 결과(eval_data/_ev)를 텍스트 줄 목록으로 포맷.
    렌더 블록(세션2 화면)과 _chat_context() 폴백이 이 함수 하나를 공유해
    '같은 데이터를 다르게 요약'하는 드리프트를 방지한다."""
    _lines: list[str] = []
    if not (isinstance(_ev, dict) and _ev.get("model_comparison")):
        return _lines
    _best = _ev.get("best_model") or ""
    _lines.append("모델 성능 리포트" + _dyn_note + (f" — 최고 모델: {_best}" if _best else ""))
    for _mn, _mv in _ev["model_comparison"].items():
        if not isinstance(_mv, dict):
            continue
        if _mv.get("error"):
            _lines.append(f"  · {_mn}: 평가 실패 ({str(_mv['error'])[:40]})")
            continue
        _bits = []
        if _mv.get("micro_f1_fraud") is not None:
            _bits.append(f"µF1(사기) {_mv['micro_f1_fraud']:.4f}")
        if _mv.get("macro_f1") is not None:
            _bits.append(f"F1(macro) {_mv['macro_f1']:.4f}")
        if _mv.get("macro_precision") is not None:
            _bits.append(f"정밀도 {_mv['macro_precision']:.4f}")
        if _mv.get("macro_recall") is not None:
            _bits.append(f"재현율 {_mv['macro_recall']:.4f}")
        if _mv.get("accuracy") is not None:
            _bits.append(f"정확도 {_mv['accuracy']:.4f}")
        _star = "🏆 " if _mn == _best else ""
        _lines.append(f"  · {_star}{_mn}: " + ", ".join(_bits))
    _rep = _ev.get("classification_report") or {}
    _cls_bits = []
    for _c in (_ev.get("class_order") or []):
        _r = _rep.get(_c)
        if isinstance(_r, dict):
            _short = FRAUD_SHORT.get(_c, _c)
            _cls_bits.append(f"{_short}(P{_r.get('precision',0):.2f}/R{_r.get('recall',0):.2f}/F1{_r.get('f1-score',0):.2f})")
    if _cls_bits:
        _lines.append("  클래스별(정밀도P/재현율R/F1): " + ", ".join(_cls_bits))
    _mac = _rep.get("macro avg")
    if isinstance(_mac, dict):
        _lines.append(f"  전체(macro avg): 정밀도 {_mac.get('precision',0):.4f}, "
                       f"재현율 {_mac.get('recall',0):.4f}, F1 {_mac.get('f1-score',0):.4f}")
    return _lines


def _chat_context(threshold):
    """🤖 AI 챗용 — 현재 대시보드 상태의 '마스킹된' 스냅샷 텍스트.
    _build_masker() 정책을 그대로 따르므로 외부 프로바이더 전송 전 PII가 보호된다."""
    _m = _build_masker()
    try:
        _sname = SESSION_LABELS[st.session_state.get('session_idx', 0)]
    except Exception:
        _sname = ""
    P = [f"현재 화면: 세션 {current_session}" + (f" ({_sname})" if _sname else ""),
         f"임계값(threshold): {threshold:.2f}"]

    # ── 세션1 (프로젝트 개요/데이터 분포) 스냅샷 ────────────────────────────
    #   🐛 FIX: 세션1은 화면 전체가 KPI 5개 + 유형별 분포 + 핵심가설인데 그동안
    #   컨텍스트에 아무 것도 안 담겨 있어, 봇이 세션2(정밀도/재현율) 수치를
    #   지어내 섞어 답하는 사고가 있었다(할루시네이션). 화면과 동일한 원천
    #   (load_selected_dataset→train.csv 폴백)에서 실제 KPI·분포를 그대로 넣는다.
    if current_session == "01":
        # ✨ v11: 화면 렌더 블록이 이번 rerun에 저장해둔 스냅샷을 그대로 사용(단일 진실 공급원).
        _s1_snap = _snap_get("01")
        if _s1_snap:
            P.extend(_s1_snap)
        else:
            # 폴백(스냅샷이 아직 없는 예외 상황에서만): 화면과 동일 원천에서 재계산
            try:
                _s1_ds = st.session_state.get('selected_dataset', '')
                _s1df, _s1note = load_selected_dataset(st.session_state.get('ds_folder', 'data/'), _s1_ds)
                if _s1df is None or 'Fraud_Type' not in _s1df.columns:
                    _s1df = load_train_df(); _s1_ds = ""
                if _s1df is not None and 'Fraud_Type' in _s1df.columns:
                    _n = len(_s1df)
                    _fraud_n = int((_s1df['Fraud_Type'] != 'm').sum())
                    _n_types = _s1df[_s1df['Fraud_Type'] != 'm']['Fraud_Type'].nunique()
                    _feat_n = len([c for c in _s1df.columns if c != 'Fraud_Type'])
                    _normal_pct = _s1df['Fraud_Type'].eq('m').mean() * 100
                    P.append(f"데이터 개요(세션1, 출처: {_s1_ds or 'train.csv'}): "
                             f"총 거래 {_n:,}건, 정상 비율 {_normal_pct:.1f}%, "
                             f"사기 {_fraud_n:,}건({_n_types}종), 전체 피처 {_feat_n}개, 분할 80/20")
                    _vc = _s1df['Fraud_Type'].value_counts()
                    _dist = ", ".join(f"{FRAUD_SHORT.get(k, k)} {v:,}건" for k, v in _vc.items())
                    P.append(f"  유형별 분포: {_dist}")
                    try:
                        _hyp = HYPOTHESES_I18N[LANG]
                        P.append("  핵심 가설: " + " / ".join(f"{code} {title}" for code, title, _ in _hyp))
                    except Exception:
                        pass
            except Exception:
                pass
    # ──────────────────────────────────────────────────────────────────────────

    # ── 모델 성능 스냅샷 (세션2 화면 = eval_result.json 리포트) ────────────────
    #   🐛 FIX(v10): 다른 세션(01/03/04/05) 블록은 전부 `if current_session == "0X":`로
    #   게이팅되어 있는데, 이 블록만 게이트가 빠져 있어 세션과 무관하게 매번 실행됨.
    #   → 세션1(개요)을 보고 있어도 컨텍스트에 세션2 지표(정확도·F1 등)가 섞여 들어가고,
    #   봇이 그 수치를 "지금 화면" 내용인 것처럼 답변에 인용하는 원인이었다(할루시네이션 아님,
    #   실제로 컨텍스트에 주입된 값이었음). 다른 세션 블록과 동일하게 current_session=="02"일
    #   때만 넣도록 게이트를 추가한다.
    #   🐛 FIX: 기존엔 세션 '번호'만 넣고 화면에 그려진 실제 지표(F1·정밀도·재현율·
    #   혼동행렬 등)는 넣지 않아, 봇이 세션은 알면서도 "수치는 화면에 표시되지 않았다"
    #   고 답하던 문제. 화면과 동일한 원천(load_eval_result)에서 지표를 텍스트로 요약해
    #   컨텍스트에 포함한다. (숫자 지표는 PII가 아니며 하단 mask_text 안전망은 그대로 통과)
    #   ✨ v9.9: 세션2 '평가 모드' 라디오(s2_mode)가 실시간 재평가(dynamic)면 그 결과를,
    #   학습 시점(static)이면 eval_result.json을 — 화면(2424~2427행)과 동일한 분기로 선택.
    #   그래야 사용자가 재평가를 실행해둔 상태에서 물어봐도 화면에 보이는 최신 수치로 답한다.
    if current_session == "02":
        # ✨ v11: 화면 렌더 블록(eval_data 확정 직후)이 저장한 스냅샷을 그대로 사용.
        _s2_snap = _snap_get("02")
        if _s2_snap:
            P.extend(_s2_snap)
        else:
            # 폴백(스냅샷이 아직 없는 예외 상황에서만): 화면과 동일 원천에서 재계산
            _dyn_note = ""
            try:
                if st.session_state.get('s2_mode') == "dynamic" and st.session_state.get('s2_dyn_eval'):
                    from pipeline.evaluator import recompute_at_threshold
                    _ev = recompute_at_threshold(st.session_state['s2_dyn_eval'], threshold)
                    _n = st.session_state['s2_dyn_eval'].get('eval_size')
                    _dyn_note = f" [실시간 재평가, 표본 {_n:,}건]" if _n else " [실시간 재평가]"
                else:
                    _ev = load_eval_result()
            except Exception:
                _ev = None
            P.extend(_format_eval_lines(_ev, _dyn_note))
    # ──────────────────────────────────────────────────────────────────────────

    # ── 세션3 (오탐·미탐 분석) 스냅샷 — 세그먼트/금액대/플래그 분석 화면 대응 ──
    #   화면과 동일 소스(load_decoded_segment_df→train.csv 폴백)로 재집계.
    #   현재 세션이 03일 때만 계산(무거운 crosstab을 다른 화면에서 매번 돌리지 않도록).
    if current_session == "03":
        # ✨ v11: 화면 렌더 블록(세그먼트/금액대/플래그 차트 계산 직후)이 저장한 스냅샷을 사용.
        _s3_snap = _snap_get("03")
        if _s3_snap:
            P.extend(_s3_snap)
        else:
            # 폴백(스냅샷이 아직 없는 예외 상황에서만): 화면과 동일 원천에서 재계산
            try:
                _s3df, _ = load_decoded_segment_df(st.session_state.get('ds_folder', 'data/'),
                                                    st.session_state.get('selected_dataset', ''))
                if _s3df is None:
                    _s3df = load_train_df()
                if _s3df is not None and 'Fraud_Type' in _s3df.columns:
                    _fraud_df = _s3df[_s3df['Fraud_Type'] != 'm']
                    _normal_df = _s3df[_s3df['Fraud_Type'] == 'm']
                    P.append(f"세그먼트·금액대·플래그 분석(세션3, 전체 {len(_s3df):,}행, "
                             f"사기 {len(_fraud_df):,}건/정상 {len(_normal_df):,}건)")
                    # 세그먼트: 화면에서 선택 가능한 첫 컬럼(또는 컴팩트뷰 선택값) 기준 상위 사기 구간
                    _seg_opts = [c for c in ('Channel', 'Operating_System', 'Access_Medium',
                                              'Customer_credit_rating', 'Customer_Gender',
                                              'Account_account_type') if c in _s3df.columns]
                    _seg_col = st.session_state.get('s3_seg_top') if st.session_state.get('s3_seg_top') in _seg_opts else (_seg_opts[0] if _seg_opts else None)
                    if _seg_col:
                        _seg_ct = _fraud_df[_seg_col].value_counts().head(3)
                        if len(_seg_ct):
                            P.append(f"  세그먼트({_seg_col}) 사기 최다: " +
                                     ", ".join(f"{k}({v}건)" for k, v in _seg_ct.items()))
                    # 금액대: 화면과 동일한 구간으로 사기 건수 집계
                    if 'Transaction_Amount' not in _s3df.columns and \
                       {'Transaction_Amount_abs', 'Transaction_is_withdrawal'}.issubset(_s3df.columns):
                        _s3df = _s3df.copy()
                        _s3df['Transaction_Amount'] = pd.to_numeric(_s3df['Transaction_Amount_abs'], errors='coerce') * \
                            (1 - 2 * pd.to_numeric(_s3df['Transaction_is_withdrawal'], errors='coerce').fillna(0))
                    if 'Transaction_Amount' in _s3df.columns:
                        _bins = ["-1천만 이하", "-1천만~0", "0~1천만", "1천만~1억", "1억 초과"]
                        _amt = pd.cut(pd.to_numeric(_s3df['Transaction_Amount'], errors='coerce'),
                                       bins=[-float('inf'), -10_000_000, 0, 10_000_000, 100_000_000, float('inf')],
                                       labels=_bins)
                        _amt_fraud_ct = _amt[_s3df['Fraud_Type'] != 'm'].value_counts()
                        _top_band = _amt_fraud_ct.idxmax() if len(_amt_fraud_ct) and _amt_fraud_ct.max() > 0 else None
                        if _top_band:
                            P.append(f"  금액대별 사기 최다 구간: {_top_band} ({int(_amt_fraud_ct.max())}건)")
                    # 플래그: 사기율-정상율 격차가 큰 상위 3개
                    _flag_gaps = []
                    for _flag in BINARY_FLAGS:
                        if _flag in _s3df.columns:
                            _fr = float(pd.to_numeric(_fraud_df[_flag], errors='coerce').mean() or 0) * 100
                            _nr = float(pd.to_numeric(_normal_df[_flag], errors='coerce').mean() or 0) * 100
                            _flag_gaps.append((FLAG_LABELS.get(_flag, _flag), _fr, _nr, _fr - _nr))
                    _flag_gaps.sort(key=lambda x: x[3], reverse=True)
                    if _flag_gaps:
                        P.append("  위험 플래그 상위(사기율 vs 정상율): " +
                                 ", ".join(f"{n}(사기{fr:.1f}%/정상{nr:.1f}%)" for n, fr, nr, _ in _flag_gaps[:3]))
            except Exception:
                pass

    # ── 세션4 (합성 데이터 QA) 스냅샷 — PASS/FAIL 체크·분포 비교 화면 대응 ──
    if current_session == "04":
        # ✨ v11: 화면 렌더 블록(PASS/FAIL 표 계산 직후)이 저장한 스냅샷을 사용.
        _s4_snap = _snap_get("04")
        if _s4_snap:
            P.extend(_s4_snap)
        else:
            # 폴백(스냅샷이 아직 없는 예외 상황에서만): 화면과 동일 원천에서 재계산
            _syn_df = st.session_state.get('syn_df')
            if _syn_df is not None:
                try:
                    P.append(f"합성 데이터 QA(세션4, 생성 {len(_syn_df):,}행)")
                    _CHECK_COLS = {'Transaction_Amount': ("거래금액", -382_480_000, 406_690_000),
                                    'Distance': ("접속거리", 0, 612),
                                    'Account_balance': ("계좌잔액", -45_756_563, 408_024_828)}
                    for _col, (_label, _mn, _mx) in _CHECK_COLS.items():
                        if _col in _syn_df.columns:
                            _ir = ((_syn_df[_col] >= _mn) & (_syn_df[_col] <= _mx)).mean()
                            _res = "PASS" if _ir > 0.95 else "FAIL"
                            P.append(f"  · {_label}: 기준범위 내 {_ir*100:.1f}% → {_res} "
                                     f"(합성 범위 {_syn_df[_col].min():,.0f}~{_syn_df[_col].max():,.0f})")
                    _df_ref = load_train_df()
                    if _df_ref is not None:
                        for _cc in ('Transaction_Amount', 'Distance', 'Account_balance'):
                            if _cc in _syn_df.columns and _cc in _df_ref.columns:
                                P.append(f"  · {_cc} 평균: 원본 {_df_ref[_cc].mean():,.0f} vs 합성 {_syn_df[_cc].mean():,.0f}")
                except Exception:
                    pass

    det = st.session_state.get('det')
    if isinstance(det, dict) and det and 'error' not in det:
        P.append(f"최근 단건 판정 → 예측유형 {det.get('fraud_type','-')}, "
                 f"위험점수 {det.get('risk_score','-')}, "
                 f"{'이상거래' if det.get('is_anomaly') else '정상'}, 모델 {det.get('model','-')}")
        _row = det.get('row')
        if isinstance(_row, dict):
            try:
                _mr = _m.mask_row({k: v for k, v in _row.items() if not str(k).startswith('_')})
                _sub = ", ".join(f"{k}={_mr.get(k)}" for k in
                                 ('Transaction_Amount', 'Channel', 'Operating_System', 'Distance')
                                 if k in _mr)
                if _sub:
                    P.append(f"  거래 요약(마스킹): {_sub}")
            except Exception:
                pass
        # ✨ v9.9: 화면에 표시되는 'AI 분석' 텍스트 자체도 봇이 참조할 수 있게(요약/재질문 대응)
        _llm = det.get('llm')
        if isinstance(_llm, dict) and _llm.get('analysis'):
            P.append(f"  AI 분석 결과(요약): {str(_llm['analysis'])[:300]}")
        if det.get('llm_error'):
            P.append(f"  ⚠ AI 분석 실패: {str(det['llm_error'])[:120]}")
        if det.get('notify_tier'):
            _sl = "발송✅" if det.get('auto_slack_sent') else ("미발송" if 'auto_slack_sent' in det else "-")
            _em = "발송✅" if det.get('auto_email_sent') else ("미발송" if 'auto_email_sent' in det else "-")
            P.append(f"  자동알림: 등급 {det['notify_tier']}, Slack {_sl}, Email {_em}")
    bres = st.session_state.get('batch_res')
    if bres is not None:
        P.append(f"최근 배치: {getattr(bres,'summary_line','')} "
                 f"(전체 {getattr(bres,'total',0)}건, 이상 {getattr(bres,'anomaly_count',0)}건, "
                 f"평균위험 {getattr(bres,'avg_risk',0)}, 최고위험 {getattr(bres,'max_risk',0)})")
        _banalysis = getattr(bres, 'analysis', '')
        if _banalysis:
            P.append(f"  배치 AI 분석 결과(요약): {str(_banalysis)[:300]}")
    _h = st.session_state.get('det_history') or []
    if _h:
        P.append(f"판정 이력: {len(_h)}건 누적")
    text = "\n".join(f"- {x}" for x in P)
    try:                       # 자유 텍스트 2차 마스킹(안전망)
        text = _m.mask_text(text)
    except Exception:
        pass
    return text

def _apply_chat_actions(actions):
    """ChatAgent가 반환한 검증된 액션을 실제 상태에 반영(화이트리스트만).
    plain state는 즉시, 위젯 key는 pending으로 예약(세션5 렌더 직전 적용).
    반환: 사용자에게 보여줄 동작 알림 문자열 리스트."""
    notes = []
    _pend_fields = {}
    _need_manual = False
    _S5_TABMAP = {"manual": "tab1", "test": "tab2", "train": "tab3",
                  "synthetic": "tab4", "folder": "tab5"}
    _FIELD_WK = {"amount": "amount_in", "distance": "dist_in", "balance": "bal_in",
                 "channel": "ch_in", "os": "os_in"}
    _FIELD_RANGE = {"amount": (-400_000_000, 400_000_000), "distance": (0, 620),
                    "balance": (-50_000_000, 410_000_000)}
    for act in actions or []:
        n, a = act.get("name"), act.get("arg")
        if n == "goto_session":
            st.session_state["session_idx"] = max(0, min(len(SESSION_KEYS) - 1, int(a) - 1))
            notes.append(t("chat.act_goto_session", n=a))
        elif n == "set_beginner_mode":
            st.session_state["beginner_mode"] = bool(a)
            notes.append(t("chat.act_beginner_on") if a else t("chat.act_beginner_off"))
        elif n == "goto_s5_tab" and a in _S5_TABMAP:
            st.session_state["session_idx"] = 4
            st.session_state["_pending_s5_tab"] = _S5_TABMAP[a]
            notes.append(t("chat.act_goto_s5tab", tab=a))
        elif n == "set_manual_field" and isinstance(a, dict):
            _f, _v = a.get("field"), a.get("value")
            _wk = _FIELD_WK.get(_f)
            _ok = False
            if _wk and _f in _FIELD_RANGE:
                try:
                    _iv = int(float(_v))
                    lo, hi = _FIELD_RANGE[_f]
                    _pend_fields[_wk] = max(lo, min(hi, _iv)); _ok = True
                except (ValueError, TypeError):
                    pass
            elif _f in ("channel", "os"):
                # 🐛 FIX(v12): 기존엔 완전일치만 허용해 LLM이 'Internet'/'windows'처럼
                #   대소문자를 다르게 쓰면 조용히 무시됐다 → 관용 매칭 후 정식 값으로 정규화.
                _opts = CAT_OPTIONS.get("Channel" if _f == "channel" else "Operating_System", [])
                _vn = str(_v).strip().lower()
                _hit = next((o for o in _opts if o.lower() == _vn), None)
                if _hit is not None:
                    _pend_fields[_wk] = _hit; _ok = True
            if _ok:
                _need_manual = True
                notes.append(t("chat.act_set_field", field=_f, value=_pend_fields[_wk]))
        elif n == "run_detection":
            st.session_state["_pending_run_manual"] = True
            _need_manual = True
            notes.append(t("chat.act_run_detection"))
        elif n == "goto_batch_subtab" and a in ("all", "analysis", "slack", "email"):
            st.session_state["session_idx"] = 4
            st.session_state["_pending_batch_subtab"] = a
            notes.append(t("chat.act_goto_batch_subtab", tab=a))
        elif n == "set_manual_flag" and isinstance(a, dict):
            _fn = (a.get("flag") or "").lower().strip()
            _bv = (a.get("value") or "").lower() in ("on", "true", "1", "yes", "켜기", "켜", "オン", "开")
            _fkeys = list(FLAG_LABELS.keys())[:12]        # 직접입력 화면에 렌더되는 12개만
            _match = next((k for k in _fkeys if _fn and _fn in k.lower()), None)
            if _match:
                _pend_fields[f"flag_{_match}"] = _bv
                _need_manual = True
                notes.append(t("chat.act_set_flag", flag=_match,
                               on=(t("chat.on") if _bv else t("chat.off"))))
        # ══════════════════════════════════════════════════════
        # ✨ v15: 신규 액션 8종 실행
        #   Streamlit은 위젯 생성 '후' 그 key를 수정하면 예외를 던지므로,
        #   위젯 기반 제어(임계값·언어·데이터셋·PII·평가모드)는 _pending 예약만 하고
        #   실제 적용은 각 위젯 생성 직전에 수행한다(위 소비 지점 참조).
        # ══════════════════════════════════════════════════════
        elif n == "set_threshold":
            try:
                _tv = max(0.0, min(1.0, float(a)))
            except (TypeError, ValueError):
                continue
            st.session_state["_pending_threshold"] = _tv
            notes.append(t("chat.act_set_threshold", v=f"{_tv:.2f}"))
        elif n == "select_model":
            _avail_m = get_available_models()
            _key = _pick_model_key(_avail_m, str(a))
            if _key:
                st.session_state["selected_model"] = _key      # plain state — 즉시 반영 가능
                notes.append(t("chat.act_select_model", m=_key))
        elif n == "select_dataset":
            st.session_state["_pending_dataset"] = str(a)
            notes.append(t("chat.act_select_dataset", d=str(a)))
        elif n == "set_eval_mode" and a in ("static", "dynamic"):
            st.session_state["_pending_s2_mode"] = a
            st.session_state["session_idx"] = 1                # 세션2로 이동해 결과를 보여준다
            notes.append(t("chat.act_set_eval_mode", m=a))
        elif n == "run_batch":
            if len(st.session_state.get("batch_rows") or []) >= 2:
                st.session_state["batch_go"] = True
                st.session_state["session_idx"] = 4
                notes.append(t("chat.act_run_batch", n=len(st.session_state["batch_rows"])))
            else:
                notes.append(t("chat.act_run_batch_none"))
        elif n == "set_pii_level" and a in ("off", "basic", "standard", "strict"):
            st.session_state["_pending_pii"] = a
            notes.append(t("chat.act_set_pii", lv=a))
        elif n == "set_compact_mode":
            st.session_state["compact_view"] = bool(a)          # plain state
            notes.append(t("chat.act_compact_on") if a else t("chat.act_compact_off"))
        elif n == "request_send":
            # ⚠️ 즉시 발송하지 않는다 — 확인 카드용 '요청'만 세션에 적재
            if not st.session_state.get('det') or 'error' in (st.session_state.get('det') or {}):
                notes.append(t("chat.act_send_no_result"))
            elif not st.session_state.get('agent_send_confirm', True):
                # ⚡ 승인 게이트 OFF — 빠른 업무 선호 사용자용. 즉시 발송(되돌릴 수 없음)
                notes.extend(_agent_send_now(st.session_state['det'], a, threshold))
            else:
                # 🚦 기본: 승인 게이트 ON — 요청만 적재하고 사람이 확인 카드에서 승인
                st.session_state['_send_request'] = {
                    "ch": a, "at": time.time(),
                    "ft": st.session_state['det'].get('fraud_type', '?'),
                    "risk": float(st.session_state['det'].get('risk_score', 0) or 0),
                }
                st.session_state['session_idx'] = 4      # 확인 카드가 보이는 세션5로 이동
                notes.append(t("chat.act_request_send", ch=a))
        elif n == "cancel_send":
            if st.session_state.pop('_send_request', None):
                notes.append(t("chat.act_cancel_send"))
            else:
                notes.append(t("chat.act_cancel_send_none"))
        elif n == "autofill_high_risk":
            # 세션5 '고위험 시나리오 자동입력' 버튼과 동일한 값 세트를 예약한다
            _pend_fields.update({
                'amount_in': -85_000_000, 'dist_in': 480, 'bal_in': 120_000_000,
                'ch_in': 'ATM', 'os_in': 'Others', 'am_in': 'a',
                'flag_Customer_rooting_jailbreak_indicator': True,
                'flag_Customer_VPN_Indicator': True,
                'flag_Customer_flag_terminal_malicious_behavior_1': True,
                'flag_Unused_terminal_status': True,
                'flag_Recipient_account_suspend_status': True,
            })
            _need_manual = True
            notes.append(t("chat.act_autofill"))
    if _pend_fields:
        st.session_state["_pending_manual"] = _pend_fields
    if _need_manual:                                  # 값입력/탐지는 직접입력 탭으로 자동 이동
        st.session_state["session_idx"] = 4
        st.session_state["_pending_s5_tab"] = "tab1"
    return notes

# ══════════════════════════════════════════════════════════
# ⌨ v17 — 전체 단축키 모음 모달 (? 또는 / 키)
#   기존엔 우측 하단 12px 토스트 한 줄이라 (a) 놓치기 쉽고 (b) C·V가 목록에 빠져 있었다.
#   실제 구현된 단축키를 전수 나열한다 (JS handler와 1:1 대응).
# ══════════════════════════════════════════════════════════
KEYMAP = [
    ("1 2 3 4 5", "kbd.k_session"),
    ("← →",       "kbd.k_move"),
    ("H",         "kbd.k_guide"),
    ("? /",       "kbd.k_help"),
    ("C",         "kbd.k_chat"),
    ("Esc",       "kbd.k_chatclose"),
    ("V",         "kbd.k_compact"),
    ("N",         "kbd.k_beginner"),
    ("D",         "kbd.k_detect"),
    ("Home",      "kbd.k_home"),
    ("B",         "kbd.k_sidebar"),
    ("U",         "kbd.k_ui"),
    ("T",         "kbd.k_theme"),
    ("L",         "kbd.k_lang"),
    ("S .",       "kbd.k_settings"),
    ("Ctrl+/",    "kbd.k_toast"),
]


def _render_keymap_body():
    st.caption(t("kbd.modal_help"))
    for keys, label_key in KEYMAP:
        chips = "".join(
            '<kbd style="display:inline-block;min-width:22px;text-align:center;'
            'padding:2px 7px;margin-right:4px;border-radius:5px;background:%s;'
            'border:1px solid %s;border-bottom-width:2px;font-family:var(--font-mono);'
            'font-size:11.5px;font-weight:700;color:%s">%s</kbd>'
            % (T.get("bg_elev", T["bg_card"]), ROW_BORDER, T["accent"], k)
            for k in keys.split())
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;padding:5px 0;'
            'border-bottom:1px solid %s"><div style="min-width:140px">%s</div>'
            '<div style="color:%s;font-size:12px">%s</div></div>'
            % (ROW_BORDER, chips, T["text_secondary"], t(label_key)),
            unsafe_allow_html=True)
    st.caption(t("kbd.modal_note"))


_D2 = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
_kbd_has_modal = False
if _D2 is not None:
    try:
        _kbd_dec = _D2(t("kbd.modal_title"), width="small")
    except TypeError:
        _kbd_dec = _D2(t("kbd.modal_title"))

    @_kbd_dec
    def _keymap_dialog():
        _render_keymap_body()
        if st.button(t("onb.close"), key="kbd_close", width='stretch'):
            st.rerun()
    _kbd_has_modal = True

if st.session_state.pop("_kbd_open", False):
    if _kbd_has_modal:
        try:
            _keymap_dialog()
        except Exception:
            with st.container(border=True):
                section_header(t("kbd.modal_title"), "KEYS")
                _render_keymap_body()
    else:
        with st.container(border=True):
            section_header(t("kbd.modal_title"), "KEYS")
            _render_keymap_body()

# ══════════════════════════════════════════════════════════
# 🎓 v15 (요청 3) — 첫 방문 온보딩 도우미
#   실무 초보자가 "이 화면에서 무엇을 할 수 있는지"를 세션별로 한 번에 파악하도록,
#   최초 진입 시 모달로 안내한다. 닫으면 다시 뜨지 않고(파일 마커 + 세션상태),
#   사이드바 '🎓 사용 안내' 버튼으로 언제든 다시 열 수 있다.
# ══════════════════════════════════════════════════════════
_ONBOARD_MARK = Path(".fds_onboarded")

def _onboard_seen() -> bool:
    if st.session_state.get("_onboard_done"):
        return True
    try:
        return _ONBOARD_MARK.exists()
    except Exception:
        return False

def _onboard_mark():
    st.session_state["_onboard_done"] = True
    try:
        _ONBOARD_MARK.write_text("1", encoding="utf-8")
    except Exception:
        pass          # 쓰기 권한이 없어도 세션 내에서는 다시 뜨지 않는다

_ONBOARD_STEPS = [
    ("01", "🗂", "purple"), ("02", "📊", "accent"), ("03", "🎯", "amber"),
    ("04", "🧪", "purple"), ("05", "🚨", "red"),
]

def _render_onboarding_body():
    st.markdown(f'<div style="font-size:13px;color:{T["text_secondary"]};line-height:1.6;'
                f'margin-bottom:10px">{t("onb.intro")}</div>', unsafe_allow_html=True)
    for _k, _ic, _cl in _ONBOARD_STEPS:
        _c = T.get(_cl, T["accent"])
        st.markdown(
            f'<div style="background:var(--bg-card);border:1px solid var(--border);'
            f'border-left:3px solid {_c};border-radius:9px;padding:9px 13px;margin-bottom:7px">'
            f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:3px">'
            f'<span style="font-size:15px">{_ic}</span>'
            f'<span style="font-family:var(--font-mono);font-size:10.5px;color:{_c};'
            f'font-weight:800;letter-spacing:0.06em">SESSION {_k}</span>'
            f'<span style="color:{T["text_primary"]};font-weight:800;font-size:13px">'
            f'{t(f"onb.s{_k}_title")}</span></div>'
            f'<div style="color:{T["text_secondary"]};font-size:11.5px;line-height:1.55">'
            f'{t(f"onb.s{_k}_body")}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div style="background:{T["accent"]}14;border:1px solid {T["accent"]}55;'
                f'border-radius:9px;padding:10px 13px;margin-top:4px">'
                f'<div style="color:{T["accent"]};font-weight:800;font-size:12px;margin-bottom:5px">'
                f'{t("onb.tips_title")}</div>'
                f'<div style="color:{T["text_secondary"]};font-size:11.5px;line-height:1.7">'
                f'{t("onb.tips_body")}</div></div>', unsafe_allow_html=True)

def _onboard_actions():
    _o1, _o2, _o3 = st.columns([1.2, 1, 1])
    if _o1.button(t("onb.start_beginner"), type="primary", key="onb_beginner", width='stretch'):
        st.session_state["beginner_mode"] = True
        st.session_state["session_idx"] = 0
        _onboard_mark(); st.rerun()
    if _o2.button(t("onb.goto_detect"), key="onb_detect", width='stretch'):
        st.session_state["session_idx"] = 4
        _onboard_mark(); st.rerun()
    if _o3.button(t("onb.close"), key="onb_close", width='stretch'):
        _onboard_mark(); st.rerun()

# st.dialog은 Streamlit 1.37+ (1.31~1.36은 experimental_dialog). 없으면 인라인 배너로 폴백.
_DLG = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
_onb_has_modal = False         # 모달 사용 가능 여부 (False면 인라인 폴백)
if _DLG is not None:
    try:                                    # width= 는 st.dialog(1.37+)만 지원
        _dec = _DLG(t("onb.title"), width="large")
    except TypeError:
        _dec = _DLG(t("onb.title"))

    @_dec
    def _onb_dialog_fn():
        _render_onboarding_body()
        _onboard_actions()
    _onb_has_modal = True

_onb_force = st.session_state.pop("_onboard_open", False)
if _onb_force or not _onboard_seen():
    # 🐛 모달 X로 닫으면 _onboard_mark()가 호출되지 않아 매 rerun마다 다시 뜬다.
    #   → 열자마자 '이번 세션에서는 본 것'으로 표시하고, 파일 마커는 버튼 클릭 시에만 남긴다.
    #   (사이드바 '🎓 사용 안내 다시 보기'로 언제든 재호출 가능)
    st.session_state["_onboard_done"] = True
    if _onb_has_modal:
        try:
            _onb_dialog_fn()
        except Exception as _oe:            # 다른 모달과 충돌 등 → 인라인 폴백
            log.warning(f"온보딩 모달 실패 → 인라인 표시: {_oe}")
            with st.container(border=True):
                section_header(t("onb.title"), "GUIDE")
                _render_onboarding_body(); _onboard_actions()
    else:
        with st.container(border=True):
            section_header(t("onb.title"), "GUIDE")
            _render_onboarding_body(); _onboard_actions()

current_session=SESSION_KEYS[st.session_state['session_idx']]

# ✨ v6 FINAL: 세션 진행 표시기
_si = st.session_state.get("session_idx", 0)
_dots = "".join(f'<div class="session-dot {"active" if i==_si else "done" if i<_si else ""}">{i+1:02d}</div>' for i in range(5))  # ✨ v7: 활성 필에 번호 표시
st.markdown(f'<div class="session-progress">{_dots}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 세션 01 — 프로젝트 개요
# ══════════════════════════════════════════════════════════
if current_session=="01":
    page_title(t("s1.title_main"), t("s1.title_span"), sub=t("s1.title_sub"), color=T["accent"], eyebrow=t("s1.eyebrow"))
    cbr()
    _s1_ds = st.session_state.get('selected_dataset', '')
    df, _s1_note = load_selected_dataset(st.session_state.get('ds_folder','data/'), _s1_ds)
    if df is None or 'Fraud_Type' not in df.columns:
        # 🔧 FIX(호환성): 선택 데이터셋이 라벨 미보유 등으로 사용 불가 → 폴백을 '눈에 보이게' 안내
        if _s1_ds:
            alert_box(t("compat.s1_fallback", name=_s1_ds), "warn")
        df = load_train_df(); _s1_note = t("s1.note_train_default"); _s1_ds = ""
    if df is not None:
        _s1_n = len(df); _s1_fraud = int((df['Fraud_Type']!='m').sum()); _s1_feat = len([c for c in df.columns if c!='Fraud_Type'])
        st.caption(f"📂 {_s1_ds or 'train.csv'} — {_s1_n:,}{t('common.rows')} · {_s1_note}")
        c1,c2,c3,c4,c5=st.columns(5)
        with c1: kpi_card(t("s1.kpi_total_label"),f"{_s1_n:,}",t("s1.kpi_total_unit"),"📊",T['accent'])
        with c2: kpi_card(t("s1.kpi_normal_label"),f"{df['Fraud_Type'].eq('m').mean()*100:.1f}%",t("s1.kpi_normal_unit"),"✅",T['green'])
        with c3: kpi_card(t("s1.kpi_fraud_label"),f"{_s1_fraud:,}{t('common.count')}",tt("s1.kpi_fraud_types", n=df[df['Fraud_Type']!='m']['Fraud_Type'].nunique()),"🚨",T['red'])
        with c4: kpi_card(t("s1.kpi_feat_label"),f"{_s1_feat}",t("s1.kpi_feat_unit"),"🔢",T['blue'])
        with c5: kpi_card(t("s1.kpi_period_label"),t("s1.kpi_period_val"),t("s1.kpi_period_unit"),"📅",T['purple'])
        # ✨ v11: 챗봇용 화면 스냅샷 — 위 KPI 카드에 쓴 변수 그대로 저장(재계산 없음)
        try:
            _s1_lines = [f"데이터 개요(세션1, 출처: {_s1_ds or 'train.csv'}): "
                         f"총 거래 {_s1_n:,}건, 정상 비율 {df['Fraud_Type'].eq('m').mean()*100:.1f}%, "
                         f"사기 {_s1_fraud:,}건({df[df['Fraud_Type']!='m']['Fraud_Type'].nunique()}종), "
                         f"전체 피처 {_s1_feat}개, 분할 80/20"]
            _s1_vc = df['Fraud_Type'].value_counts()
            _s1_lines.append("  유형별 분포: " + ", ".join(f"{FRAUD_SHORT.get(k, k)} {v:,}건" for k, v in _s1_vc.items()))
            try:
                _s1_hyp = HYPOTHESES_I18N[LANG]
                _s1_lines.append("  핵심 가설: " + " / ".join(f"{code} {title}" for code, title, _ in _s1_hyp))
            except Exception:
                pass
            _snap_set("01", _s1_lines)
        except Exception:
            pass
    cbr()
    if CV:
        # ══ ✨ v9.4: 세션1 컴팩트 재설계 — 접이식 전면 제거 · 무스크롤 한 화면 ══
        #   레이아웃:  [KPI] → [WHY 얇은 배너] → [분포: 막대(좌) + 도넛(우)] → [핵심가설 3열 그리드]
        #   컴팩트 전용 생략: 유형 사전 / 사기유형 확대분포(메인 막대와 중복) / 유형별 건수 상세표
        # ── (v9.4) 컴팩트 안내 핀 제거: 접이식 섹션이 사라져 문구도 불필요 · 세로 공간 회수 ──
        st.markdown(f'<div class="alert-box alert-info" style="margin:2px 0 6px">{t("s1.why_body")}</div>', unsafe_allow_html=True)
        if df is not None:
            section_header(t("s1.data_dist_title"), "DATA")
            hint("beginner.s1_dist")   # 🔰 초보자 설명(켤 때만)
            ft_all = df['Fraud_Type'].value_counts().reset_index(); ft_all.columns = ['유형', '건수']
            ft_all['레이블'] = ft_all['유형'].map(lambda x: FRAUD_SHORT.get(x, x))
            ft_all['색상'] = ft_all['유형'].apply(lambda x: T['green'] if x == 'm' else T['red'])
            fig_all = px.bar(ft_all, x='레이블', y='건수', color='색상', color_discrete_map="identity", title=t("s1.chart_all_title"), text='건수')
            fig_all.update_traces(marker_line_width=0, texttemplate='%{text:,}', textposition='outside', cliponaxis=False, textfont=dict(size=9.5, color=T['text_secondary'], family='JetBrains Mono, monospace'))
            fig_all.update_layout(**PLOTLY_LAYOUT, margin=dict(l=6, r=6, t=34, b=6), bargap=0.28, height=248, showlegend=False, title_font=dict(size=12, color=T['text_secondary']), yaxis=dict(gridcolor=GRID_COLOR), xaxis=dict(tickfont=dict(size=9.5), gridcolor=GRID_COLOR), dragmode='zoom')
            _dn_vals = [int((df['Fraud_Type'] == 'm').sum()), int((df['Fraud_Type'] != 'm').sum())]
            _dn = go.Figure(go.Pie(values=_dn_vals, labels=[t("s1.donut_normal"), t("s1.donut_fraud")], hole=0.62,
                marker=dict(colors=[T['green'], T['red']], line=dict(width=0)), pull=[0, 0.06], sort=False,
                textinfo='percent', textposition='inside', insidetextorientation='horizontal',
                textfont=dict(size=12, color=T['text_primary'], family='JetBrains Mono, monospace'),
                hovertemplate=t("s1.donut_hover", label='%{label}', value='%{value:,}', percent='%{percent}') + '<extra></extra>'))
            _dn.update_layout(**PLOTLY_LAYOUT, margin=dict(l=6, r=6, t=10, b=4), height=248, showlegend=True,
                uniformtext=dict(minsize=9, mode='hide'),
                legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5, font=dict(size=10)),
                annotations=[dict(text=f"<b>{_dn_vals[1]:,}</b><br><span style='font-size:10px;color:{T['text_muted']}'>{t('s1.donut_fraud')}</span>",
                                  x=0.5, y=0.5, font=dict(size=19, color=T['red']), showarrow=False)])
            _s1bar, _s1don = st.columns([1.7, 1], gap="medium", vertical_alignment="center")
            with _s1bar:
                st.plotly_chart(fig_all, width='stretch', config={'displayModeBar': False})
            with _s1don:
                st.plotly_chart(_dn, width='stretch', config={'displayModeBar': False})
        # 핵심 가설 — 하단 3열(2×3) 그리드 · 슬림 카드
        section_header(t("s1.hyp_title"), "HYPOTHESIS")
        hypotheses = HYPOTHESES_I18N[LANG]
        _hcols = st.columns(3, gap="small")
        for i, (code, title, desc) in enumerate(hypotheses):
            with _hcols[i % 3]:
                st.markdown(f'<div class="hypo-card" style="padding:8px 11px;margin-bottom:5px"><div style="display:flex;align-items:baseline;gap:7px;margin-bottom:3px"><span class="hypo-code" style="flex:none">{code}</span><span style="color:{T["text_primary"]};font-size:12px;font-weight:600;line-height:1.25">{title}</span></div><p class="hypo-text" style="font-size:11px;margin:0;line-height:1.45;color:{T["text_secondary"]}">{desc}</p></div>', unsafe_allow_html=True)
    else:
        with csec(t("s1.why_title"),"WHY"):
            st.markdown(f'<div class="alert-box alert-info">{t("s1.why_body")}</div>',unsafe_allow_html=True)
        with csec(t("s1.hyp_title"),"HYPOTHESIS"):
            hypotheses=HYPOTHESES_I18N[LANG]
            cols=st.columns(2)
            for i,(code,title,desc) in enumerate(hypotheses):
                with cols[i%2]:
                    st.markdown(f'<div class="hypo-card"><span class="hypo-code">{code}</span><p style="color:{T["text_primary"]};font-size:13.5px;font-weight:600;margin:5px 0 3px">{title}</p><p class="hypo-text">{desc}</p></div>',unsafe_allow_html=True)

        cbr()
        section_header(t("s1.fraud_dict_title"),"FRAUD TYPE REFERENCE")
        st.markdown(f'<div class="alert-box alert-info">{t("s1.fraud_dict_hint")}</div>',unsafe_allow_html=True)
        tc=st.columns(3)
        for i,(code,info) in enumerate(FRAUD_TYPE_DETAILS.items()):
            with tc[i%3]:
                with st.expander(f"🔖 {code.upper()} — {info['name']}",expanded=False):
                    fraud_type_popup(code)

        if df is not None:
            section_header(t("s1.data_dist_title"),"DATA")
            hint("beginner.s1_dist")   # 🔰 초보자 설명(켤 때만)
            ft_all=df['Fraud_Type'].value_counts().reset_index();ft_all.columns=['유형','건수']
            ft_all['레이블']=ft_all['유형'].map(lambda x:FRAUD_SHORT.get(x,x))
            ft_all['색상']=ft_all['유형'].apply(lambda x:T['green'] if x=='m' else T['red'])
            fig_all=px.bar(ft_all,x='레이블',y='건수',color='색상',color_discrete_map="identity",title=t("s1.chart_all_title"),text='건수')
            fig_all.update_traces(marker_line_width=0,texttemplate='%{text:,}',textposition='outside',cliponaxis=False,textfont=dict(size=10,color=T['text_secondary'],family='JetBrains Mono, monospace'))  # ✨ v7.1: 라벨 잘림 방지 + 모노 톤 통일
            fig_all.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,bargap=0.30,height=_ch(420,230),showlegend=False,title_font=dict(size=13,color=T['text_secondary']),yaxis=dict(gridcolor=GRID_COLOR),xaxis=dict(tickfont=dict(size=10),gridcolor=GRID_COLOR),dragmode='zoom')
            # ✨ v6 FINAL: 도넛 차트(정상 vs 사기 비율) + 전체 분포 막대 — 나란히
            _s1d, _s1b = st.columns([1, 2.5])
            with _s1d:
                _dn_vals = [int((df['Fraud_Type']=='m').sum()), int((df['Fraud_Type']!='m').sum())]
                # ✨ v7.1: 도넛 확대(240→420, 옆 막대와 수직 정렬) · 퍼센트 라벨 인사이드(상단 잘림 해소)
                #          · 사기 슬라이스 pull 강조 · 하단 범례 (팀 피드백: 여백 과다 + 라벨 클리핑)
                _dn = go.Figure(go.Pie(values=_dn_vals, labels=[t("s1.donut_normal"), t("s1.donut_fraud")], hole=0.62,
                    marker=dict(colors=[T['green'],T['red']], line=dict(width=0)),
                    pull=[0, 0.06], sort=False,
                    textinfo='percent', textposition='inside', insidetextorientation='horizontal',
                    textfont=dict(size=13, color=T['text_primary'], family='JetBrains Mono, monospace'),
                    hovertemplate=t("s1.donut_hover", label='%{label}', value='%{value:,}', percent='%{percent}')+'<extra></extra>'))
                _dn.update_layout(**PLOTLY_LAYOUT, margin=dict(l=10,r=10,t=16,b=6), height=_ch(420,230), showlegend=True,
                    uniformtext=dict(minsize=10, mode='hide'),
                    legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5, font=dict(size=11)),
                    annotations=[dict(text=f"<b>{_dn_vals[1]:,}</b><br><span style='font-size:10.5px;color:{T['text_muted']}'>{t('s1.donut_fraud')}</span>",
                                      x=0.5, y=0.5, font=dict(size=21, color=T['red']), showarrow=False)])
                st.plotly_chart(_dn, width='stretch', config={'displayModeBar': False})
            with _s1b:
                st.plotly_chart(fig_all,width='stretch',config={'displayModeBar':True,'scrollZoom':True,'displaylogo':False})

            with csec(t("s1.chart_zoom_title"),"FRAUD ONLY · ZOOM"):
                ft_fraud=df[df['Fraud_Type']!='m']['Fraud_Type'].value_counts().reset_index();ft_fraud.columns=['유형','건수']
                ft_fraud['레이블']=ft_fraud['유형'].map(lambda x:FRAUD_SHORT.get(x,x))
                ft_fraud['비율']=(ft_fraud['건수']/len(df)*100).round(3)
                fig_fraud=go.Figure()
                fig_fraud.add_trace(go.Bar(x=ft_fraud['레이블'],y=ft_fraud['건수'],marker_color=T['red'],marker_line_width=0,text=[f"{c}건<br>{p:.3f}%" for c,p in zip(ft_fraud['건수'],ft_fraud['비율'])],textposition='outside',cliponaxis=False,textfont=dict(size=10,color=T['red'],family='JetBrains Mono, monospace'),customdata=ft_fraud['비율']))
                avg_cnt=ft_fraud['건수'].mean()
                fig_fraud.add_hline(y=avg_cnt,line_dash="dot",line_color=T['amber'],annotation_text=t("s1.avg_annotation", n=f"{avg_cnt:.0f}"),annotation_font=dict(color=T['amber'],size=10),annotation_position="top right")
                fig_fraud.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,bargap=0.30,title=t("s1.chart_detail_title"),title_font=dict(size=13,color=T['text_secondary']),yaxis=dict(gridcolor=GRID_COLOR,title=t("s1.th_count")),xaxis=dict(tickfont=dict(size=11),gridcolor=GRID_COLOR),dragmode='zoom',height=_ch(380,210))
                st.plotly_chart(fig_fraud,width='stretch',config={'displayModeBar':True,'scrollZoom':True,'displaylogo':False})

            cbr()
            with csec(t("s1.table_title"),"TABLE"):
                fraud_cnt=df[df['Fraud_Type']!='m']['Fraud_Type'].value_counts();total=len(df)
                trows=""
                for ft_type,cnt in fraud_cnt.items():
                    pct=cnt/total*100;bw=int(cnt/fraud_cnt.max()*100);short=FRAUD_SHORT.get(ft_type,ft_type)
                    trows+=f'<tr style="border-bottom:1px solid {ROW_BORDER}"><td style="padding:8px 12px;font-family:JetBrains Mono;font-size:12px;color:{T["accent"]};font-weight:700">{ft_type.upper()}</td><td style="padding:8px 12px;font-size:12px;color:{T["text_secondary"]}">{short}</td><td style="padding:8px 12px;font-family:JetBrains Mono;font-size:12px;color:{T["red"]};font-weight:600">{cnt:,}</td><td style="padding:8px 12px;font-family:JetBrains Mono;font-size:11px;color:{T["text_muted"]}">{pct:.3f}%</td><td style="padding:8px 12px;width:160px"><div style="background:{T["bg_surface"]};border-radius:3px;height:6px;overflow:hidden"><div style="width:{bw}%;height:100%;border-radius:3px;background:linear-gradient(90deg,{T["red_dim"]},{T["red"]})"></div></div></td></tr>'
                st.markdown(f'<table style="width:100%;border-collapse:collapse;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;overflow:hidden"><thead><tr style="background:{T["bg_surface"]}"><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase">{t("s1.th_type")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase">{t("s1.th_desc")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase">{t("s1.th_count")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase">{t("s1.th_ratio")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase">{t("s1.th_rel_ratio")}</th></tr></thead><tbody>{trows}</tbody></table>',unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# 세션 02 — 모델 성능
# ══════════════════════════════════════════════════════════
elif current_session=="02":
    page_title(t("s2.title_main"), t("s2.title_span"), color=T["accent"], eyebrow=t("s2.eyebrow"))
    cbr()

    # ══ 🩺 v8: 호환성 진단(Schema Doctor) — 수동 검증하던 스키마 대조를 원클릭화 ══
    def _schema_doctor(ds_folder, ds_name, model_path):
        """→ [(level, msg)] level ∈ ok|warn|error|info. 데이터셋·모델·메타를 일괄 점검."""
        R = []
        from pipeline import dataset_loader as _dl
        from pipeline.dataset_loader import discover_datasets, load_dataset
        # ✨ v8.4: 실린 로더 버전 표시 — "파일은 바꿨는데 재시작을 안 한" 사고 즉시 진단
        _ver = getattr(_dl, "LOADER_VERSION", "v5 이하 (구버전! pipeline/dataset_loader.py 교체+재시작 필요)")
        import i18n_data as _i18n_mod
        _iver = getattr(_i18n_mod, "I18N_VERSION", "v8.4 이하 (구버전! i18n_data.py 교체+재시작 필요)")
        R.append(("info", f"ℹ dashboard: {DASH_VERSION} · dataset_loader: {_ver} · i18n: {_iver}"))
        found = discover_datasets(ds_folder)
        if not ds_name or ds_name not in found:
            R.append(("error", t("doc.ds_missing", name=ds_name or "—")))
            return R
        info = found[ds_name]
        R.append(("ok", t("doc.ds_ok", name=ds_name, kind=info.kind, note=info.note)))
        try:
            df = load_dataset(info)
        except Exception as e:
            R.append(("error", t("doc.load_fail", e=str(e)[:120])))
            return R
        # ── 라벨 디코딩 ──
        _has_label = 'Fraud_Type' in df.columns
        if not _has_label:
            R.append(("warn", t("doc.no_label")))
        else:
            _lab = df['Fraud_Type'].astype(str)
            _pct = _lab.isin(list("abcdefghijklm")).mean() * 100
            if _pct >= 99.0:
                R.append(("ok", t("doc.label_ok", pct=_pct, mratio=(_lab == 'm').mean() * 100)))
            else:
                R.append(("error", t("doc.label_bad")))
        # ── 라벨 누출 스캔 (이진 컬럼 × 라벨 일치율) ──
        _feat_cols = [c for c in df.columns if c != 'Fraud_Type']
        if _has_label:
            _fraud_mask = df['Fraud_Type'].astype(str) != 'm'
            _leaks = []
            for c in _feat_cols:
                try:
                    s = pd.to_numeric(df[c], errors='coerce')
                    if s.nunique(dropna=True) == 2:
                        if float(((s == s.max()) == _fraud_mask).mean()) >= 0.999:
                            _leaks.append(c)
                except Exception:
                    pass
            if _leaks:
                R.append(("error", t("doc.leak", cols=", ".join(_leaks[:5]))))
        else:
            _leaks = []
        # ── 상수 컬럼 / NaN ──
        _const = [c for c in _feat_cols if df[c].nunique(dropna=False) <= 1]
        if _const:
            R.append(("warn", t("doc.const", cols=", ".join(_const[:6]) + ("…" if len(_const) > 6 else ""))))
        _na = df[_feat_cols].isna().sum(); _na = _na[_na > 0]
        if len(_na):
            R.append(("warn", t("doc.nan", n=len(_na), cols=", ".join(f"{c}({v:,})" for c, v in _na.head(4).items()))))
        else:
            R.append(("ok", t("doc.nan_none")))
        # ── 모델 × 피처 대조 (evaluator의 20% 룰과 동일 기준) ──
        try:
            from pipeline.model_loader import load_model as _dm_load, get_expected_features
            _um = _dm_load(model_path)
            _exp = get_expected_features(_um)
            if _exp is None:
                R.append(("warn", t("doc.feat_noname")))
            else:
                _missing = [c for c in _exp if c not in df.columns]
                _extra = [c for c in _feat_cols if c not in _exp]
                if not _missing:
                    R.append(("ok", t("doc.feat_ok", n=len(_exp))))
                elif len(_missing) <= max(3, int(len(_exp) * 0.2)):
                    R.append(("warn", t("doc.feat_partial", miss=len(_missing), n=len(_exp), ex=", ".join(_missing[:3]))))
                else:
                    R.append(("error", t("doc.feat_bad", miss=len(_missing), n=len(_exp), ex=", ".join(_missing[:3]))))
                if _extra:
                    R.append(("info", t("doc.extra_note", n=len(_extra), cols=", ".join(_extra[:5]) + ("…" if len(_extra) > 5 else ""))))
                # ✨ v8.5: 누출 컬럼 × 모델 피처 교차검증 — "학습에서 뺐다"는 말을 기계적으로 확인
                if _leaks:
                    _leak_used = [c for c in _leaks if c in _exp]
                    if _leak_used:
                        R.append(("error", t("doc.leak_model_uses", cols=", ".join(_leak_used))))
                    else:
                        R.append(("ok", t("doc.leak_model_excluded", cols=", ".join(_leaks[:5]))))
        except Exception as e:
            R.append(("error", t("doc.model_fail", e=str(e)[:120])))
        # ── 메타 4종 + 브리지 ──
        _meta_miss = [f for f in ("label_encoders.pkl", "le_target.pkl", "feature_cols.json", "feature_defaults.json")
                      if not (MODEL_DIR / f).exists()]
        if _meta_miss:
            R.append(("warn", t("doc.meta_miss", files=", ".join(_meta_miss))))
        else:
            R.append(("ok", t("doc.meta_ok")))
        if (MODEL_DIR / "feature_bridge.pkl").exists():
            R.append(("info", t("doc.bridge_note")))
        return R

    # ✨ v9.5: 컴팩트 — [평가 모드 | 호환성 진단] 좌우 배치. 일반은 기존 순서(진단→평가모드) 유지.
    #   컬럼은 위치(index)로 배치되므로 코드에서 진단을 먼저 써도 컴팩트에선 오른쪽 칸에 들어간다.
    if CV:
        _ecL, _ecR = st.columns([1.25, 1], gap="medium", vertical_alignment="top")
        _ctx_radio, _ctx_doc = _ecL, _ecR
    else:
        _ctx_radio, _ctx_doc = _ctxlib.nullcontext(), _ctxlib.nullcontext()
    with _ctx_doc:
        with st.expander(t("doc.expander"), expanded=False):
            st.markdown(f'<div style="color:{T["text_muted"]};font-size:12px;margin-bottom:8px">{t("doc.desc")}</div>', unsafe_allow_html=True)
            _doc_ds = st.session_state.get('selected_dataset', '')
            _doc_models = get_available_models()
            _doc_mn = st.session_state.get('selected_model', '')
            _doc_mn = _doc_mn if _doc_mn in _doc_models else next(iter(_doc_models))
            _doc_mp = _doc_models[_doc_mn]["path"]
            dc1, dc2 = st.columns([1.1, 4], vertical_alignment="center")
            with dc1:
                if st.button(t("doc.run"), key="doc_run", type="primary", width='stretch'):
                    with st.spinner(t("doc.spinner")):
                        st.session_state['doc_result'] = _schema_doctor(
                            st.session_state.get('ds_folder', 'data/'), _doc_ds, _doc_mp)
                        st.session_state['doc_target'] = (_doc_ds or "—", _doc_mn)
            with dc2:
                st.markdown(f'<div style="font-family:var(--font-mono);font-size:12px;color:{T["text_secondary"]}">{t("doc.target", ds=_doc_ds or "—", model=model_display_name(_doc_mn, LANG))}</div>', unsafe_allow_html=True)
            if st.session_state.get('doc_result'):
                _dr = st.session_state['doc_result']
                _n_ok = sum(1 for l, _ in _dr if l == "ok"); _n_w = sum(1 for l, _ in _dr if l == "warn"); _n_e = sum(1 for l, _ in _dr if l == "error")
                st.caption(t("doc.summary", ok=_n_ok, warn=_n_w, err=_n_e) + f" — 📂 {st.session_state.get('doc_target',('—',''))[0]} × 🧠 {st.session_state.get('doc_target',('','—'))[1]}")
                for _lv, _msg in _dr:
                    alert_box(_msg, "info" if _lv == "info" else _lv)
    with _ctx_radio:
        # ── ✨ v5: 평가 모드 — 학습 시점 리포트 vs 선택 데이터셋×모델 실시간 재평가 ──
        # ✨ v15 (요청 4): 기본값을 '실시간 재평가(선택 데이터셋 × 모델)'로 변경.
        #   학습 시점 리포트(static)는 eval_result.json 스냅샷이라 현재 선택한 데이터셋·모델과
        #   무관한 수치를 보여준다 → 실제 운용 판단에 쓰이는 dynamic을 기본으로 노출한다.
        if "_pending_s2_mode" in st.session_state:   # ✨ v15 에이전트 평가모드 변경
            st.session_state["s2_mode"] = st.session_state.pop("_pending_s2_mode")
        if "s2_mode" not in st.session_state:
            st.session_state["s2_mode"] = "dynamic"
        _eval_mode = st.radio(tt("s2.mode_label"), ["static", "dynamic"], horizontal=True, key="s2_mode",
                              format_func=lambda x: tt("s2.mode_static") if x=="static" else tt("s2.mode_dynamic"))
    if _eval_mode == "dynamic":
        from pipeline.model_loader import discover_models, load_model
        from pipeline.evaluator import evaluate, passthrough_preprocess
        _mdl_found = discover_models("models/")
        # ✨ v5.3: 대시보드 톤에 맞춘 카드형 컨트롤 (선택 데이터셋 배지 + 모델·실행 정렬)
        _dsn = st.session_state.get('selected_dataset','')
        # v9.6: 컴팩트 = [데이터셋 배지 | 비교모델 | 표본상한 | 실행] 한 줄. 일반 = 배너 풀폭 + 컨트롤 행(기존).
        if CV:
            _cds, _dc1, _dc2, _dc3 = st.columns([1.5, 2.1, 0.9, 0.85], vertical_alignment="bottom")
            with _cds:
                # 🐛 FIX(v18): 배지에 라벨이 없어 '비교할 모델'·'표본 상한'(라벨 보유)과
                #   베이스라인이 어긋났다. vertical_alignment="bottom"만으로는 라벨 높이 차이를
                #   보정할 수 없다 → 같은 스타일의 라벨 줄을 명시적으로 붙여 높이를 맞춘다.
                st.markdown(
                    f'<div style="font-size:11px;color:var(--text-muted);margin:0 0 2px;'
                    f'line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                    f'{tt("ds.select_label")}</div>'
                    f'<div style="background:var(--bg-card);border:1px solid var(--border);'
                    f'border-radius:var(--radius);padding:0 11px;height:32px;box-sizing:border-box;'
                    f'display:flex;align-items:center;overflow:hidden">'
                    f'<span style="font-family:var(--font-mono);font-size:11.5px;color:var(--accent);'
                    f'font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                    f'📂 {_dsn or "—"}</span></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px;margin-bottom:6px"><span style="font-family:var(--font-mono);font-size:12px;color:var(--accent);font-weight:700">📂 {_dsn or "—"}</span> <span style="color:var(--text-muted);font-size:10.5px;float:right">{tt("ds.select_label")} → 좌측 사이드바</span></div>', unsafe_allow_html=True)
            _cols = st.columns([2.4, 0.9, 0.7], vertical_alignment="bottom")
            _dc1, _dc2, _dc3 = _cols[0], _cols[1], _cols[2]
        with _dc1:
            # 🎛 기본 비교 모델: 설정값(DEFAULT_COMPARE_MODEL_MATCH) 하나만 → 없으면 발견된 첫 모델 하나
            _mdl_keys = list(_mdl_found.keys())
            _pref_cmp = _pick_key(_mdl_keys, DEFAULT_COMPARE_MODEL_MATCH)
            _cmp_default = [_pref_cmp] if _pref_cmp else _mdl_keys[:1]
            _mdl_sel = st.multiselect(tt("s2.model_multi_label"), _mdl_keys,
                                      default=_cmp_default, max_selections=3, key="s2_models")
        with _dc2:
            # ✨ v5.8: 데이터셋 크기에 맞는 표본 상한 — 작으면 전체, 크면 층화 샘플
            _cap_opts = {1_000:"1천", 5_000:"5천", 20_000:"2만", 10**9:"전체"}
            # ✨ v8.8: 디폴트 '전체' — 사기 258건 전량 유지 표본에선 상한이 정상만 깎아 왜곡 여지
            _s2_cap = st.selectbox(tt("s2.sample_cap_label"), list(_cap_opts.keys()),
                                   index=3, key="s2_cap", format_func=lambda x: _cap_opts[x])
        with _dc3:
            _s2_go = st.button(tt("s2.run_eval_button"), type="primary", key="s2_run", width='stretch')
        if _s2_go:
            df_eval, _note = load_selected_dataset(st.session_state.get('ds_folder','data/'),
                                                   st.session_state.get('selected_dataset',''))
            if df_eval is None or 'Fraud_Type' not in df_eval.columns:
                alert_box(tt("ds.no_label_warn"), "warn")
            else:
                # 🔧 FIX(호환성): is_fraud = 라벨 누출 피처(검증됨) — 포함 평가 지표는 허위 만점이 됨. 평가는 진행하되 경고.
                if 'is_fraud' in df_eval.columns:
                    _leak_alert("compat.leak_s2")
                with st.spinner(tt("s2.eval_spinner", n=len(_mdl_sel))):
                    try:
                        # ✨ v6.2: evaluate가 모델별로 최적 프렙을 자동 선택
                        #   원본 데이터셋 → 48피처 모델은 MLClassifier, 81피처 모델은 브리지
                        #   인코딩 데이터셋 → passthrough + 피처 매칭
                        _feat = [c for c in df_eval.columns if c != 'Fraud_Type']
                        _is_encoded = all(pd.api.types.is_numeric_dtype(df_eval[c]) for c in _feat)
                        _brg_obj = None
                        if not _is_encoded:
                            _brg_obj = _get_feature_bridge()   # ✨ v6.3: 없으면 자동 fit 시도
                        _prep_fn = passthrough_preprocess(None, fillna=0) if _is_encoded else None
                        _prep_note = "🌉 모델별 자동 프렙 (브리지+MLClassifier)" if _brg_obj else ("passthrough" if _is_encoded else "MLClassifier 전처리")
                        models = {}
                        for _mn in _mdl_sel:
                            try: models[_mn] = load_model(_mdl_found[_mn])
                            except Exception as _me: alert_box(tt("s2.eval_fail", e=f"{_mn}: {_me}"), "error")
                        st.session_state['s2_prep_note'] = _prep_note
                        if not models:
                            alert_box(tt("s2.no_model_loaded"), "error")
                        else:
                            _MAX = int(st.session_state.get("s2_cap", 5000))
                            ev = evaluate(models, df_eval, preprocess_fn=_prep_fn,
                                          max_rows=_MAX, bridge=_brg_obj)
                            if not ev.get("best_model"):      # 전 모델 평가 실패
                                _errs = "; ".join(f"{k}: {v.get('error','?')[:80]}" for k, v in ev["model_comparison"].items())
                                alert_box(tt("s2.eval_fail", e=_errs), "error")
                            else:
                                # 🐛 FIX(v8.8): evaluator가 셔플 순서 그대로의 라벨을 반환 — head() 재구성은
                                #   표본 추출 시 risk와 어긋나므로 구버전 evaluator 폴백으로만 유지
                                if not ev.get("y_true_cache"):
                                    ev["y_true_cache"] = df_eval['Fraud_Type'].astype(str).head(ev["eval_size"]).tolist()
                                st.session_state['s2_dyn_eval'] = ev
                                st.session_state['s2_dyn_ytrue'] = ev["y_true_cache"]
                    except Exception as e:
                        alert_box(tt("s2.eval_fail", e=e), "error")
        if st.session_state.get('s2_dyn_eval') and not CV:   # v9.6: 컴팩트에선 평가 표본/저지지/부재 안내 캡션 숨김
            _ev = st.session_state['s2_dyn_eval']
            _cap_txt = f"{_ev['eval_size']:,}"
            st.caption(tt("s2.eval_sample_caption", n=_cap_txt) + (f" · {_ev['sampling_note']}" if _ev.get('sampling_note') else " · " + tt("s2.eval_full_use"))
                       + (f" · {st.session_state['s2_prep_note']}" if st.session_state.get('s2_prep_note') else ""))
            if _ev.get("low_support"):
                # 🔧 FIX(v8): 'if False else'로 사장돼 있던 표본 건수 표시 복원
                _yt_ls = st.session_state.get('s2_dyn_ytrue', [])
                st.caption(tt("s2.low_support_warn", types=", ".join(f"{c.upper()}({sum(1 for y in _yt_ls if y==c)}{t('notif.cnt')})" for c in _ev["low_support"])))
            if _ev.get("absent_classes"):
                st.caption(tt("s2.absent_class_note", types=", ".join(c.upper() for c in _ev["absent_classes"])))

    eval_data=load_eval_result()
    if _eval_mode == "dynamic" and st.session_state.get('s2_dyn_eval'):
        from pipeline.evaluator import recompute_at_threshold
        eval_data = recompute_at_threshold(st.session_state['s2_dyn_eval'], threshold)
    # 🛡 FIX(v9): 구버전/불완전 eval_result.json 필수 키 누락 → KeyError 페이지 크래시 방지
    if eval_data and (not isinstance(eval_data, dict) or 'model_comparison' not in eval_data or 'class_order' not in eval_data):
        alert_box(t("s2.no_eval_warn") + " (eval_result.json 스키마 불일치 — model_comparison/class_order 누락)", "warn")
        eval_data = None
    # ✨ v11: 챗봇용 화면 스냅샷 — 화면에 그릴 eval_data(위에서 확정) 그대로, 공유 포맷터(_format_eval_lines)로 저장
    try:
        _s2_dyn_note = ""
        if _eval_mode == "dynamic" and st.session_state.get('s2_dyn_eval'):
            _s2_n = st.session_state['s2_dyn_eval'].get('eval_size')
            _s2_dyn_note = f" [실시간 재평가, 표본 {_s2_n:,}건]" if _s2_n else " [실시간 재평가]"
        _snap_set("02", _format_eval_lines(eval_data, _s2_dyn_note))
    except Exception:
        pass
    if not eval_data:
        alert_box(t("s2.no_eval_warn"), "warn")
    else:
        section_header(t("s2.compare_title"),"BENCHMARK")
        comp=eval_data["model_comparison"];colors={"LogisticRegression":T['blue'],"RandomForest":T['purple'],"LightGBM":T['accent']};icons={"LogisticRegression":"📐","RandomForest":"🌲","LightGBM":"⚡"}
        cols=st.columns(max(len(comp),1))
        _adapt_notes=[]
        for i,(model,metrics) in enumerate(comp.items()):
            ib=model==eval_data.get("best_model")
            with cols[i%len(cols)]:
                if metrics.get("error"):
                    # ✨ v5.4: 평가 실패 모델은 F1 0.0으로 위장하지 않고 오류 카드로 표시
                    kpi_card(f"⚠ {model}","—",str(metrics["error"])[:60],"⚠",T['red'])
                else:
                    # ✨ v9.5: 주 지표 = µF1(사기 micro). 있으면 헤드라인, macro F1은 보조로 병기.
                    _mf = metrics.get('macro_f1', 0)
                    _p = metrics.get('macro_precision', _mf)
                    _r = metrics.get('macro_recall', _mf)
                    _acc = metrics.get('accuracy', 0)
                    _uf = metrics.get('micro_f1_fraud')
                    if _uf is not None:
                        _val = f"µF1 {_uf:.4f}"
                        _sub = (f"F1 {_mf:.3f} · P {_p:.3f} · R {_r:.3f} · Acc {_acc:.3f}")
                    else:
                        # 정적 eval_result.json에 모델별 µF1 부재 → macro F1 헤드라인(파생 불가, 실시간 재평가 시 µF1 표시)
                        _val = f"F1 {_mf:.4f}"
                        _sub = (f"P {_p:.4f} · R {_r:.4f} · Acc {_acc:.4f}")
                    kpi_card(f"{'🏆 ' if ib else ''}{model}", _val, _sub,
                             icons.get(model,"🤖"), colors.get(model,T['accent']))
                    if metrics.get("note"): _adapt_notes.append(f"{model}: {metrics['note']}")
        if _adapt_notes and not CV:
            st.caption("🔗 " + tt("s2.adapt_note_prefix") + " — " + " / ".join(_adapt_notes))
        if any('micro_f1_fraud' in m for m in comp.values()) and not CV:
            st.caption(tt("s2.micro_note"))
        hint("beginner.s2_metrics")   # 🔰 초보자 설명(켤 때만 표시)

        # ✨ v9.4/9.5: 컴팩트 2행×2열 — [모델비교|클래스리포트] / [혼동행렬|임계값비용]
        #   모델 비교 차트는 비교 모델 2개↑일 때만 존재 → 1개면 클래스 리포트를 풀폭으로(빈 칸 붕 뜸 방지)
        _ok_models = {k: v for k, v in comp.items() if not v.get("error")}
        _s2_has_mc = len(_ok_models) >= 2
        if CV and _s2_has_mc:
            _s2r1a, _s2r1b = st.columns([1, 1], gap="medium", vertical_alignment="top")
        else:
            _s2r1a, _s2r1b = _ctxlib.nullcontext(), _ctxlib.nullcontext()
        with _s2r1a:
            # ✨ v8.13: 모델 성능 비교 차트 — '비교할 모델(최대 3개)' 선택분을 지표별 그룹 막대로
            if _s2_has_mc:
                section_header(tt("s2.model_chart_title"), "MODEL COMPARISON")
                _mx = [("µF1", "micro_f1_fraud"), ("µP", "micro_precision_fraud"), ("µR", "micro_recall_fraud"),
                       ("Macro F1", "macro_f1"), ("Acc", "accuracy")]
                _mx = [(lb, k) for lb, k in _mx if any(k in v for v in _ok_models.values())]
                figm = go.Figure()
                for _mi, (_mn2, _mv2) in enumerate(_ok_models.items()):
                    figm.add_trace(go.Bar(name=_mn2, x=[lb for lb, _ in _mx],
                        y=[_mv2.get(k, 0) for _, k in _mx],
                        marker_color=colors.get(_mn2, [T['accent'], T['purple'], T['blue'], T['amber']][_mi % 4]),
                        marker_line_width=0,
                        text=[f"{_mv2.get(k, 0):.3f}" for _, k in _mx], textposition="outside",
                        textfont=dict(size=9, color=T['text_secondary'], family='JetBrains Mono, monospace'), cliponaxis=False,
                        hovertemplate=_mn2 + " · %{x} %{y:.4f}<extra></extra>"))
                figm.add_vline(x=0.5, line_dash="dot", line_color=T['text_muted'], opacity=0.35)  # 주 지표(µF1) 구분
                figm.update_layout(**PLOTLY_LAYOUT, margin=_M_DEFAULT, barmode='group', bargap=0.3, bargroupgap=0.08,
                                   height=_ch(320,230), yaxis=dict(range=[0, 1.12], gridcolor=GRID_COLOR),
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, font=dict(size=11)))
                figm.update_xaxes(tickfont=dict(size=11), gridcolor=GRID_COLOR)
                st.plotly_chart(figm, width='stretch')
        with _s2r1b:
            _metric_all = ["Precision", "Recall", "F1-score"]; _pick_opts = ["µF1"] + _metric_all
            _pick_fn = getattr(st, "pills", None); _picked = None
            def _s2_pills(_vis):
                if _pick_fn:
                    return _pick_fn(tt("s2.metric_pick"), _pick_opts, selection_mode="multi", default=_pick_opts, key="s2_metric_pick", label_visibility=_vis) or []
                return st.multiselect(tt("s2.metric_pick"), _pick_opts, default=_pick_opts, key="s2_metric_pick", label_visibility=_vis)
            if CV:   # v9.6: CLASS REPORT 헤더 + 지표 pills 한 줄로 (좌 헤더 / 우 pills)
                # 🐛 FIX(v18): pills 4개(µF1·Precision·Recall·F1-score)가 좁은 컬럼에서
                #   2줄로 접히며 위쪽 차트 영역을 밀어 올렸다.
                #   → ① 헤더:pills 비율을 1:1.6 → 0.75:2.25로 재배분해 한 줄에 들어가게 하고
                #     ② pills 자체를 컴팩트 CSS로 압축(아래 .s2-pills 스코프)
                _hcc, _pcc = st.columns([0.75, 2.25], vertical_alignment="center")
                with _hcc:
                    st.markdown(f'<div class="section-header" style="margin:0"><span class="section-title" style="font-size:11.5px">{t("s2.class_report_title")}</span></div>', unsafe_allow_html=True)
                with _pcc:
                    st.markdown('<div class="s2-pills-scope"></div>', unsafe_allow_html=True)
                    _picked = _s2_pills("collapsed")
            else:
                section_header(t("s2.class_report_title"),"CLASS REPORT")
                hint("beginner.s2_classreport")   # 🔰 초보자 설명(켤 때만)
            report=eval_data.get("classification_report",{});rows=[]
            for cls in eval_data["class_order"]:
                if cls in report:
                    r=report[cls];rows.append({"cls":cls,"유형":FRAUD_SHORT.get(cls,cls),"Precision":r.get("precision",0),"Recall":r.get("recall",0),"F1-score":r.get("f1-score",0),"support":int(r.get("support",0))})
            if rows:
                rdf=pd.DataFrame(rows)
                # 🐛 FIX(v7): macro avg를 렌더링 "이후" fig.data=[]로 재구성해 화면에 반영되지 않던 버그
                #    → 렌더링 전에 병합. 라벨도 i18n(s2.macro_label) 적용
                _mac=report.get("macro avg",{})
                if _mac:
                    rdf = pd.concat([rdf, pd.DataFrame([{"cls":"macro","유형":t("s2.macro_label"),"Precision":_mac.get("precision",0),"Recall":_mac.get("recall",0),"F1-score":_mac.get("f1-score",0),"support":int(_mac.get("support",0))}])], ignore_index=True)
                # ✨ v8.12: 주 지표 µ(사기 한정) 막대 — 혼동행렬에서 직접 집계해 정적/동적 모두 지원
                _cm_l = eval_data.get("confusion_matrix") or []
                _urow = None
                if _cm_l and len(_cm_l) == len(eval_data["class_order"]):
                    _cma = np.asarray(_cm_l, dtype=float); _ord = eval_data["class_order"]
                    _fi = [i for i, c in enumerate(_ord) if c != "m"]
                    _tp = float(sum(_cma[i, i] for i in _fi))
                    _fn = float(_cma[_fi, :].sum() - _tp); _fp = float(_cma[:, _fi].sum() - _tp)
                    _up = _tp / max(_tp + _fp, 1e-9); _ur = _tp / max(_tp + _fn, 1e-9)
                    _uf = 2 * _up * _ur / max(_up + _ur, 1e-9)
                    _urow = {"cls":"micro","유형":tt("s2.micro_label"),"Precision":round(_up,4),"Recall":round(_ur,4),"F1-score":round(_uf,4),"support":int(_tp+_fn)}
                else:
                    # 🔧 v8.13: 혼동행렬이 없는 결과(구 eval_result.json 등) — 베스트 모델의 µ 지표로 폴백
                    _bmm = eval_data.get("model_comparison", {}).get(eval_data.get("best_model",""), {})
                    if "micro_f1_fraud" in _bmm:
                        _urow = {"cls":"micro","유형":tt("s2.micro_label"),"Precision":_bmm.get("micro_precision_fraud",0),"Recall":_bmm.get("micro_recall_fraud",0),"F1-score":_bmm.get("micro_f1_fraud",0),"support":0}
                if _urow:
                    rdf = pd.concat([rdf, pd.DataFrame([_urow])], ignore_index=True)
                # 지표 pills — 컴팩트는 위 헤더 행에서 이미 렌더됨. 일반 모드만 여기서.
                if not CV:
                    _picked = _s2_pills("visible")
                _metric_sel = [m for m in _picked if m in _metric_all] or ["F1-score"]  # 전부 꺼도 주 지표는 유지
                if "µF1" not in _picked:                 # µ 요약 열(전체 µ(사기)) 표시 여부
                    rdf = rdf[rdf["cls"] != "micro"].reset_index(drop=True)
                st.markdown("""<style>div[data-testid='stPlotlyChart']{animation:s2fade .45s ease}
    @keyframes s2fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}</style>""", unsafe_allow_html=True)
                fig=go.Figure()
                _sup_hover = t("s2.hover_support", n="%{customdata}")
                # ✨ v5.4: 값이 0인 유형(예: A)이 '없어 보이던' 문제 — 값 라벨 + support 호버로 0을 명시
                for metric,color in [(m,c) for m,c in [("Precision",T['accent']),("Recall",T['red']),("F1-score",T['amber'])] if m in _metric_sel]:
                    fig.add_trace(go.Bar(name=metric,x=rdf["유형"],y=rdf[metric],marker_color=color,marker_line_width=0,
                        text=[f"{v:.2f}" for v in rdf[metric]],textposition="outside",textfont=dict(size=8.5,color=T['text_secondary'],family='JetBrains Mono, monospace'),cliponaxis=False,
                        customdata=rdf["support"],hovertemplate="%{x} · "+metric+" %{y:.4f}<br>"+_sup_hover+"<extra></extra>"))
                _n_sum = int((rdf["cls"]=="macro").sum() + (rdf["cls"]=="micro").sum())
                if _n_sum:  # ✨ v8.12: 요약(macro·µ) 영역을 세로 점선으로 구분
                    fig.add_vline(x=len(rdf)-_n_sum-0.5, line_dash="dot", line_color=T['text_muted'], opacity=0.5)
                fig.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,barmode='group',bargap=0.28,bargroupgap=0.08,legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1.0,font=dict(size=11)),**_hc(250))
                fig.update_xaxes(tickfont=dict(size=10),gridcolor=GRID_COLOR)
                fig.update_yaxes(range=[0,1.12],gridcolor=GRID_COLOR)
                st.plotly_chart(fig,width='stretch')
                _zero_f1=[r for r in rows if r["F1-score"]==0 and r["support"]>0]
                if _zero_f1 and not CV:   # ✨ v9.5: 컴팩트 오버뷰에선 세부 경고 숨김(공간 회수 · 한눈 우선)
                    _zl=", ".join(f"{z['cls'].upper()}({z['support']}건)" for z in _zero_f1)
                    alert_box(tt("s2.zero_f1_warn", types=_zl), "warn")
        _s2r2a, _s2r2b = crow([1, 1], gap="medium")
        with _s2r2a:
            section_header(t("s2.confusion_title"),"CONFUSION MATRIX")
            cm=eval_data.get("confusion_matrix")
            if cm:
                classes=[FRAUD_SHORT.get(c,c) for c in eval_data["class_order"]]
                # ✨ v5.4: 건수 ↔ 비율(행 기준 %, 실제 유형별 어디로 예측됐나) 토글
                _cm_pct = st.toggle(tt("s2.ratio_toggle"), key="cm_pct")
                _zc=np.array(cm,dtype=float)
                if _cm_pct:
                    _rs=_zc.sum(axis=1,keepdims=True); _rs[_rs==0]=1.0
                    _z=_zc/_rs*100.0
                else:
                    _z=_zc
                _fmt=(lambda v: f"{v:.1f}") if _cm_pct else (lambda v: f"{int(v)}")
                _unit="%" if _cm_pct else t("s2.count_axis")
                _eye=np.eye(len(_z),dtype=bool)
                _diag=np.where(_eye,_z,np.nan)                         # 정탐 (대각선)
                _err =np.where(~_eye & (_z>0),_z,np.nan)               # 오탐/미탐 (강조 대상)
                _zero=np.where(~_eye & (_z==0),0.0,np.nan)             # 무오류 배경
                fig_cm=go.Figure()
                _CM_GAP = 3  # ✨ v7: 셀 사이 갭 → 타일형 모던 그리드 룩
                _hv_head = t("s2.actual_axis")+" %{y} → "+t("s2.pred_axis")+" %{x}<br>"
                fig_cm.add_trace(go.Heatmap(z=_zero,x=classes,y=classes,colorscale=[[0,T['bg_surface']],[1,T['bg_surface']]],showscale=False,hoverinfo="skip",xgap=_CM_GAP,ygap=_CM_GAP))
                _diag_max = float(np.nanmax(_diag)) if np.any(np.isfinite(_diag)) else 1.0  # 🛡 FIX(v9): all-NaN → zmax=NaN 방지
                fig_cm.add_trace(go.Heatmap(z=_diag,x=classes,y=classes,zmin=0,zmax=_diag_max if _diag_max > 0 else 1,
                    colorscale=[[0,T['bg_card']],[0.5,T['accent_dim']],[1,T['accent']]],showscale=False,xgap=_CM_GAP,ygap=_CM_GAP,
                    text=np.vectorize(lambda m,v:_fmt(v) if m else "")(_eye,_z),texttemplate="%{text}",textfont=dict(size=10,family='JetBrains Mono, monospace'),
                    customdata=_zc,hovertemplate=_hv_head+"✅ "+t("s2.cm_hover_correct")+" %{z:.1f}"+_unit+" (%{customdata:.0f})<extra></extra>"))
                fig_cm.add_trace(go.Heatmap(z=_err,x=classes,y=classes,zmin=0,zmax=float(np.nanmax(_err)) if np.isfinite(np.nanmax(_err)) else 1,
                    colorscale=[[0,T['red_dim']],[1,T['red']]],showscale=False,xgap=_CM_GAP,ygap=_CM_GAP,
                    text=np.vectorize(lambda m,v:_fmt(v) if m else "")(~_eye & (_z>0),_z),texttemplate="%{text}",
                    textfont=dict(size=10,color=T['text_primary'],family='JetBrains Mono, monospace'),
                    customdata=_zc,hovertemplate=_hv_head+"🟥 "+t("s2.cm_hover_error")+" %{z:.1f}"+_unit+" (%{customdata:.0f})<extra></extra>"))
                fig_cm.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,
                    xaxis=dict(title=t("s2.pred_axis"),title_font=dict(size=12,color=T['accent']),tickfont=dict(size=10),side="bottom"),
                    yaxis=dict(title=t("s2.actual_axis"),title_font=dict(size=12,color=T['accent']),tickfont=dict(size=10),autorange="reversed"),**_hc(250))
                st.plotly_chart(fig_cm,width='stretch')
                st.caption(tt("s2.cm_error_hint"))
                hint("beginner.s2_cm")   # 🔰 초보자 설명(켤 때만 표시)
        with _s2r2b:
            section_header(t("s2.threshold_title"),f"THRESHOLD = {threshold:.2f}")
            # ── ✨ v5: 동적 모드 = 실측 FN/FP × 단가 / 정적 모드 = 기존 더미 공식(라벨 표기) ──
            _dyn = st.session_state.get('s2_dyn_eval')
            if st.session_state.get('s2_mode') == "dynamic" and _dyn and _dyn.get("best_model"):
                if CV:   # v9.6: [미탐 비용 | 오탐 비용 | 최적 임계값] 한 줄
                    cc1, cc2, cc3 = st.columns([1, 1, 1.5], vertical_alignment="bottom")
                else:
                    cc1, cc2 = st.columns(2); cc3 = None
                with cc1: _fn_c = st.number_input(tt("s2.cost_fn_unit"), 1_000, 100_000_000, 1_000_000, step=100_000, key="fn_c")
                with cc2: _fp_c = st.number_input(tt("s2.cost_fp_unit"), 100, 10_000_000, 30_000, step=10_000, key="fp_c")
                from pipeline.evaluator import threshold_cost_curve
                _pm = _dyn["per_model"][_dyn["best_model"]]
                _sw = _dyn.get("sampling", {})   # ✨ v8.7: 층화 표본 → 모집단 보정 (오탐 과소집계 방지)
                _cc_args = (np.asarray(_pm["risk"], dtype=float),
                            np.asarray(st.session_state.get('s2_dyn_ytrue', [])[:len(_pm["risk"])]))
                try:
                    _curve = threshold_cost_curve(*_cc_args, fn_cost=_fn_c, fp_cost=_fp_c,
                                                  fraud_weight=_sw.get("fraud_weight", 1.0),
                                                  normal_weight=_sw.get("normal_weight", 1.0))
                except TypeError:
                    # 🔧 FIX(v8.9): pipeline/evaluator.py 구버전(보정 인자 없음) — 크래시 대신 무보정 계산 + 안내
                    _curve = threshold_cost_curve(*_cc_args, fn_cost=_fn_c, fp_cost=_fp_c)
                    alert_box(tt("s2.evaluator_stale"), "warn")
                thresholds, dfn, dfp, dtot = _curve["thresholds"], _curve["fn"], _curve["fp"], _curve["total"]
                _opt_th = _curve.get("optimal_threshold")  # ✨ v7: 차트에 최적점 세로선 표시용
                _w_note = tt("s2.cost_weight_note", w=f"{_sw.get('normal_weight', 1.0):.1f}") if _sw.get("normal_weight", 1.0) > 1.01 else ""
                _opt_msg = tt("s2.cost_optimal", th=_curve["optimal_threshold"]) + (" · " + _w_note if _w_note else "")
                if cc3 is not None:
                    with cc3: st.caption(_opt_msg)
                else:
                    st.caption(_opt_msg)
                # ✨ 3-1: 임계값 → 비즈니스 언어 요약 (현재 임계값에서의 실측 건수 · 모집단 환산)
                if not CV:
                    try:
                        _thr_list = _curve["thresholds"]
                        _bi = min(range(len(_thr_list)), key=lambda k: abs(_thr_list[k] - threshold))
                        _n_missed = _curve["fn"][_bi] / max(_fn_c, 1)     # 놓친 사기(모집단 환산)
                        _n_fp     = _curve["fp"][_bi] / max(_fp_c, 1)     # 검토 대기열行(오탐)
                        _n_fraud  = _sw.get("n_fraud_total")              # 모집단 총 사기 건수
                        if _n_fraud is not None:
                            _n_caught = _n_fraud - _n_missed
                            st.info(t("s2.biz_readout", th=f"{threshold:.2f}",
                                      caught=f"{max(0, round(_n_caught)):,}",
                                      missed=f"{max(0, round(_n_missed)):,}",
                                      fp=f"{max(0, round(_n_fp)):,}",
                                      cost=f"{round(_curve['total'][_bi]):,}"))
                            hint("beginner.s2_cost")   # 🔰 초보자 설명(켤 때만)
                    except Exception:
                        pass
            else:
                thresholds=np.arange(0.05,1.0,0.02)
                dfn=[200*(1-_th)**2 for _th in thresholds];dfp=[80*_th**1.8 for _th in thresholds];dtot=[a+b for a,b in zip(dfn,dfp)]
                _opt_th = None
                st.caption(tt("s2.dummy_curve_note"))
            fig_th=go.Figure()
            # ✨ v7: 라인별 의미색 영역 채움 (FN=red / FP=accent) — 기존엔 둘 다 동일 accent 틴트
            fig_th.add_trace(go.Scatter(x=thresholds,y=dfn,name=t("s2.fn_cost"),line=dict(color=T['red'],width=2.2),fill='tozeroy',fillcolor=f'rgba({_RED_RGB},0.07)'))
            fig_th.add_trace(go.Scatter(x=thresholds,y=dfp,name=t("s2.fp_cost"),line=dict(color=T['accent'],width=2.2),fill='tozeroy',fillcolor=f'rgba({T["accent_rgb"]},0.07)'))
            fig_th.add_trace(go.Scatter(x=thresholds,y=dtot,name=t("s2.total_cost"),line=dict(color=T['amber'],width=2.6,dash="dot")))
            # 🐛 FIX(v7): 세로선 흰색 하드코딩 → 라이트 테마에서 비가시. 테마 반응형으로 교체
            fig_th.add_vline(x=threshold,line_color=T['text_muted'],line_dash="dash",annotation_text=t("s2.current_annotation", th=f"{threshold:.2f}"),annotation_font=dict(color=T['text_primary'],size=11))
            if _opt_th is not None:  # ✨ v7: 동적 모드 — 비용 최적 임계값을 차트에 직접 표시
                fig_th.add_vline(x=float(_opt_th),line_color=T['green'],line_dash="dash",opacity=0.9,
                                 annotation_text=t("s2.optimal_annotation", th=f"{float(_opt_th):.2f}"),
                                 annotation_position="bottom right",annotation_font=dict(color=T['green'],size=11))
            fig_th.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,legend=dict(orientation="h",y=1.08,font=dict(size=11)),xaxis_title=t("s2.threshold_axis"),yaxis_title=tt("s2.cost_axis"),**_hc(230))
            styled_axis(fig_th)
            st.plotly_chart(fig_th,width='stretch')


# ══════════════════════════════════════════════════════════
# 세션 03 — 오탐·미탐 세그먼트 분석
# ══════════════════════════════════════════════════════════
elif current_session=="03":
    _NORMAL_LBL=t("common.normal"); _FRAUD_LBL=t("common.fraud")
    page_title(t("s3.title_main"), t("s3.title_span"), color=T["red"], eyebrow=t("s3.eyebrow"))
    st.markdown(f'<div class="alert-box alert-info" style="margin:16px 0">{t("s3.info_note")}</div>',unsafe_allow_html=True)
    hint("beginner.s3_intro")   # 🔰 초보자 설명(켤 때만 표시)
    # ── ✨ v5: 선택 데이터셋 연동 — 세그먼트/금액대/플래그 그래프가 자동 변동 ──
    # ⚡ v8: 로드+표시용 디코딩을 캐시 경유로 일원화 (매 rerun 96k행 inverse_transform 제거)
    df, _s3note = load_decoded_segment_df(st.session_state.get('ds_folder','data/'),
                                          st.session_state.get('selected_dataset',''))
    if df is not None:
        _s3name = st.session_state.get('selected_dataset','')
        st.caption(tt("ds.loaded_info", name=_s3name, n=len(df), note=_s3note))
    if df is None:
        # 🔧 FIX(호환성): 데이터셋을 선택했는데 세그먼트 분석 요건(라벨+범주 컬럼)을 못 채워
        #   train.csv로 폴백하는 경우 — 조용히 넘어가지 않고 사유를 표시
        if st.session_state.get('selected_dataset',''):
            alert_box(t("compat.s3_fallback", name=st.session_state.get('selected_dataset','')), "warn")
        df = load_train_df()          # 폴백: 기존 동작 (train.csv)
    if df is None:
        alert_box(t("s3.no_train_warn"), "warn")
    else:
        # ✨ v11: 챗봇용 화면 스냅샷 — 이 화면이 쓰는 df 그대로 재사용(별도 로딩 없음)
        _s3_lines = [f"세그먼트·금액대·플래그 분석(세션3, 전체 {len(df):,}행, "
                     f"사기 {int((df['Fraud_Type']!='m').sum()):,}건/정상 {int((df['Fraud_Type']=='m').sum()):,}건)"]
        # ✨ v9.5: 컴팩트 컨트롤 행 — [세그먼트 기준 선택 | 비율 토글]을 한 줄로(세로 공간 회수).
        #   일반 모드는 기존대로(토글 → 세그먼트 섹션 안 선택기) 유지.
        _seg_opts=[c for c in ('Channel','Operating_System','Access_Medium','Customer_credit_rating','Customer_Gender','Account_account_type') if c in df.columns]
        if CV:
            _s3cA, _s3cB = st.columns([2, 1], gap="medium", vertical_alignment="bottom")
            with _s3cA:
                seg_col = st.selectbox(t("s3.seg_select_label"), _seg_opts, key="s3_seg_top")
            with _s3cB:
                _s3_pct = st.toggle(tt("s3.ratio_toggle"), key="s3_pct")
        else:
            _s3_pct = st.toggle(tt("s3.ratio_toggle"), key="s3_pct")
            seg_col = None
        # 컴팩트 = 세그먼트·금액대 좌우 페어링(플래그는 아래 풀폭)
        _s3c1, _s3c2 = crow([1, 1], gap="medium")
        with _s3c1:
            section_header(t("s3.seg_title"),"SEGMENT")
            if not CV:   # 일반 모드: 선택기를 세그먼트 섹션 안에 (기존 위치 보존)
                seg_col=st.selectbox(t("s3.seg_select_label"),_seg_opts)
            ct=pd.crosstab(df[seg_col],df['Fraud_Type'].apply(lambda x:_NORMAL_LBL if x=='m' else x))
            if _s3_pct:
                ctv=(ct.div(ct.sum(axis=1).replace(0,1),axis=0)*100).round(2)   # 행(세그먼트) 기준 %
                _txt=[[f"{v:.2f}%" for v in row] for row in ctv.values]
            else:
                ctv=ct; _txt=[[f"{int(v):,}" for v in row] for row in ctv.values]
            # ✨ v11: 챗봇용 스냅샷 — 위에서 그린 ct(크로스탭) 그대로 사기 최다 세그먼트 집계(재로딩 없음)
            try:
                _fraud_cols_ct = [c for c in ct.columns if c != _NORMAL_LBL]
                if _fraud_cols_ct:
                    _seg_fraud_top = ct[_fraud_cols_ct].sum(axis=1).sort_values(ascending=False).head(3)
                    _seg_fraud_top = _seg_fraud_top[_seg_fraud_top > 0]
                    if len(_seg_fraud_top):
                        _s3_lines.append(f"  세그먼트({seg_col}) 사기 최다: " +
                                         ", ".join(f"{k}({int(v)}건)" for k, v in _seg_fraud_top.items()))
            except Exception:
                pass
            # ✨ v7: 세션2 혼동행렬과 톤 통일 — 타일 갭 · bg_surface 기점(저값 셀 가시화) · 모노 폰트 · 컬러바 제거
            fig=px.imshow(ctv.values,x=ct.columns.tolist(),y=ct.index.tolist(),color_continuous_scale=[[0,T['bg_surface']],[0.5,T['red_dim']],[1,T['red']]],aspect="auto")
            fig.update_traces(text=_txt,texttemplate="%{text}",textfont=dict(size=10,family='JetBrains Mono, monospace'),xgap=3,ygap=3,
                              customdata=ct.values,hovertemplate="%{y} · %{x}<br>%{text} (%{customdata:,}건)<extra></extra>")
            fig.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,coloraxis_showscale=False,**_hc(200))
            st.plotly_chart(fig,width='stretch')

        with _s3c2:
            section_header(t("s3.amount_title"),"AMOUNT BAND")
            # 🔧 FIX(호환성): 새 전처리 스키마는 Transaction_Amount 대신 _abs + is_withdrawal 로 분해됨
            #   → 부호 있는 금액을 복원(출금이면 음수)해 금액대 분석 유지. 둘 다 없으면 스킵 안내.
            if 'Transaction_Amount' not in df.columns and {'Transaction_Amount_abs','Transaction_is_withdrawal'}.issubset(df.columns):
                df = df.copy()
                df['Transaction_Amount'] = pd.to_numeric(df['Transaction_Amount_abs'],errors='coerce') * (1 - 2*pd.to_numeric(df['Transaction_is_withdrawal'],errors='coerce').fillna(0))
                st.caption(t("compat.s3_amount_restored"))
            if 'Transaction_Amount' not in df.columns:
                alert_box(t("compat.s3_no_amount"), "warn")
            else:
              df2=df.copy()
              _amt_bins=[t("s3.amt_bin1"),t("s3.amt_bin2"),t("s3.amt_bin3"),t("s3.amt_bin4"),t("s3.amt_bin5")]
              df2['금액대']=pd.cut(pd.to_numeric(df2['Transaction_Amount'],errors='coerce'),bins=[-float('inf'),-10_000_000,0,10_000_000,100_000_000,float('inf')],labels=_amt_bins)
              df2['구분']=df2['Fraud_Type'].apply(lambda x:_NORMAL_LBL if x=='m' else _FRAUD_LBL)
              amt_ct=pd.crosstab(df2['금액대'],df2['구분'])
              # ✨ v11: 챗봇용 스냅샷 — 위에서 그린 amt_ct 그대로 사기 최다 금액대 집계(재로딩 없음)
              try:
                  if _FRAUD_LBL in amt_ct.columns and float(amt_ct[_FRAUD_LBL].max() or 0) > 0:
                      _top_band3 = amt_ct[_FRAUD_LBL].idxmax()
                      _s3_lines.append(f"  금액대별 사기 최다 구간: {_top_band3} ({int(amt_ct[_FRAUD_LBL].max())}건)")
              except Exception:
                  pass
              if _s3_pct:
                amt_v=(amt_ct.div(amt_ct.sum(axis=1).replace(0,1),axis=0)*100).round(2)   # 금액대 내 구성비 %
                _yt="%"
              else:
                amt_v=amt_ct; _yt=t("s2.count_axis")
              fig2=go.Figure()
              for col,color in [(_NORMAL_LBL,T['green']),(_FRAUD_LBL,T['red'])]:
                if col in amt_v.columns:
                    fig2.add_trace(go.Bar(name=col,x=amt_v.index.astype(str),y=amt_v[col],marker_color=color,marker_line_width=0,
                        customdata=amt_ct[col],hovertemplate="%{x} · "+col+"<br>%{y:,.2f}"+_yt+" (%{customdata:,}건)<extra></extra>"))
              fig2.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,barmode='group',bargap=0.28,bargroupgap=0.08,yaxis_title=_yt,
                               legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1.0),**_hc(190))
              styled_axis(fig2)
              st.plotly_chart(fig2,width='stretch')

        section_header(t("s3.flag_title"),"FLAG ANALYSIS")
        hint("beginner.s3_flags")   # 🔰 초보자 설명(켤 때만)
        fraud_df=df[df['Fraud_Type']!='m'];normal_df=df[df['Fraud_Type']=='m']
        flag_data=[]
        for flag in BINARY_FLAGS:
            # 🔧 FIX(호환성): 플래그가 bool/문자 '0'/'1'로 저장된 parquet 대응 — to_numeric 후 평균
            if flag in df.columns: flag_data.append({"플래그":FLAG_LABELS.get(flag,flag),"사기(%)":round(float(pd.to_numeric(fraud_df[flag],errors='coerce').mean() or 0)*100,1),"정상(%)":round(float(pd.to_numeric(normal_df[flag],errors='coerce').mean() or 0)*100,1)})
        # 🔧 FIX(호환성): 새 스키마에서 플래그 12종이 전부 개명/드랍되면 빈 DF sort_values → KeyError 크래시
        if not flag_data:
            alert_box(t("compat.s3_no_flags"), "warn")
        else:
          flag_df=pd.DataFrame(flag_data).sort_values("사기(%)",ascending=True)
          # ✨ v11: 챗봇용 스냅샷 — 위에서 그린 flag_df 그대로 위험 플래그 상위(격차 기준) 집계(재로딩 없음)
          try:
              _flag_gap3 = (flag_df["사기(%)"] - flag_df["정상(%)"]).sort_values(ascending=False)
              _top_flags3 = flag_df.loc[_flag_gap3.head(3).index]
              _s3_lines.append("  위험 플래그 상위(사기율 vs 정상율): " +
                                ", ".join(f"{r['플래그']}(사기{r['사기(%)']:.1f}%/정상{r['정상(%)']:.1f}%)"
                                          for _, r in _top_flags3.iterrows()))
          except Exception:
              pass
          fig3=go.Figure()
          fig3.add_trace(go.Bar(name=_NORMAL_LBL,y=flag_df["플래그"],x=flag_df["정상(%)"],orientation='h',marker_color=T['accent'],marker_line_width=0))
          fig3.add_trace(go.Bar(name=_FRAUD_LBL,y=flag_df["플래그"],x=flag_df["사기(%)"],orientation='h',marker_color=T['red'],marker_line_width=0))
          fig3.update_layout(**PLOTLY_LAYOUT,barmode='overlay',height=_ch(400,340),xaxis_title=t("s3.ratio_axis"))
          # ✨ v9.5: y축 라벨 잘림 해결 — 고정 l=8 제거 + automargin으로 라벨 길이만큼 좌측 자동 확보
          #   (긴 한글 플래그명 그대로 유지) · 컴팩트에서도 12개 막대가 눌리지 않게 높이 상향(340)
          fig3.update_layout(margin=dict(r=8,t=54,b=8),
                           legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1.0,
                                       bgcolor="rgba(0,0,0,0)",font=dict(size=11)))
          fig3.update_xaxes(gridcolor=GRID_COLOR,ticksuffix='%')
          fig3.update_yaxes(tickfont=dict(size=10 if CV else 10.5), automargin=True)  # ✨ 라벨 자동 여백(안 잘림)
          st.plotly_chart(fig3,width='stretch')
        # ✨ v11: 챗봇용 화면 스냅샷 저장 — 세그먼트/금액대/플래그 순서로 조립된 최종 라인을 저장
        try:
            _snap_set("03", _s3_lines)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
# 세션 04 — 합성데이터 QA
# ══════════════════════════════════════════════════════════
elif current_session=="04":
    page_title(t("s4.title_main"), t("s4.title_span"), color=T["purple"], eyebrow=t("s4.eyebrow"))
    cbr()

    # ── 모델 선택 (QA 검증 대상) ─────────────────────────
    section_header(t("s4.model_title"),"MODEL")
    hint("beginner.s4_intro")   # 🔰 초보자 설명(켤 때만)
    # 🌐 전역 모델 참조 (변경은 좌측 사이드바 — 세션 04·05 중복 셀렉터 제거)
    avail_models_04 = get_available_models()
    _cur04 = st.session_state['selected_model'] if st.session_state['selected_model'] in avail_models_04 else next(iter(avail_models_04))
    mi04 = avail_models_04[_cur04]
    me04 = Path(mi04["path"]).exists()
    sb04 = f'<span class="badge-safe">{t("sb.model_loadable")}</span>' if me04 else f'<span class="badge-danger">{t("sb.model_missing")}</span>'
    st.markdown(f'<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px"><span style="font-family:var(--font-mono);font-size:12px;color:var(--accent);font-weight:700">🧠 {model_display_name(_cur04, LANG)}</span> {sb04} <span style="color:var(--text-muted);font-size:11px;margin-left:8px">{mi04["desc"]}</span><span style="color:var(--text-muted);font-size:10.5px;float:right">{t("common.change_model_hint")}</span></div>', unsafe_allow_html=True)

    section_header(t("s4.gen_settings_title"),"GENERATE")
    c1,c2,c3,c4=st.columns([2,2,2,1], vertical_alignment="bottom")
    with c1: syn_n=st.number_input(t("s4.gen_count_label"),10,1000,100,step=10)
    with c2: syn_type=st.selectbox(t("s4.target_type_label"),["random"]+list("abcdefghijkl"))
    with c3: syn_seed=st.number_input(t("s4.seed_label"),-1,9999,-1,help=t("s4.seed_help"))
    with c4:
        gen_btn=st.button(t("s4.gen_button"),type="primary",width='stretch')
    if gen_btn:
        with st.spinner(t("s4.gen_spinner")):
            try:
                from pipeline.data_streamer import DataStreamer
                np.random.seed(_resolve_seed(syn_seed));streamer=DataStreamer(train_path=train_path)
                ft=None if syn_type=="random" else syn_type
                rows=streamer.from_synthetic(n=int(syn_n),fraud_type=ft)
                st.session_state['syn_df']=pd.DataFrame(rows)
                alert_box(t("s4.gen_success", n=len(rows)), "ok")
            except Exception as e:
                alert_box(t("s4.gen_fail", e=e), "error")
    if 'syn_df' in st.session_state:
        syn_df=st.session_state['syn_df'];df_ref=load_train_df()

        # ══════════════════════════════════════════════════════
        # ✨ v14 (요청 5): 합성 데이터의 '사기 유형'을 한눈에 — 강조 배너
        #   from_synthetic()은 각 행에 _target_type을 심는다('random'이면 전 유형 혼합 분포).
        # ══════════════════════════════════════════════════════
        _tt_series = (syn_df['_target_type'].astype(str)
                      if '_target_type' in syn_df.columns else pd.Series(dtype=str))
        _tt_counts = _tt_series.value_counts() if len(_tt_series) else pd.Series(dtype=int)
        _is_random = (len(_tt_counts) == 0) or ('random' in _tt_counts.index)
        def _ft_name(c):
            try:
                from pipeline.batch_analyzer import FRAUD_TYPE_NAMES as _FTN
                return _FTN.get(str(c).lower(), '-')
            except Exception:
                return '-'
        if _is_random:
            _chip = (f'<span style="display:inline-block;padding:4px 12px;border-radius:999px;'
                     f'background:{T["purple"]}22;border:1px solid {T["purple"]};'
                     f'color:{T["purple"]};font-weight:800;font-size:13px;font-family:var(--font-mono)">'
                     f'{t("s4.syn_type_random")}</span>')
            _detail = t("s4.syn_type_random_desc")
        else:
            _codes = [c for c in _tt_counts.index if c != 'random']
            _chips = []
            for _c in _codes:
                _chips.append(
                    f'<span style="display:inline-block;padding:4px 12px;margin-right:6px;'
                    f'border-radius:999px;background:{T["red"]}22;border:1px solid {T["red"]};'
                    f'color:{T["red"]};font-weight:800;font-size:14px;font-family:var(--font-mono)">'
                    f'{str(_c).upper()}형</span>'
                    f'<span style="color:{T["text_primary"]};font-weight:700;font-size:13px;'
                    f'margin-right:14px">{_ft_name(_c)} '
                    f'<span style="color:{T["text_muted"]};font-weight:400">({_tt_counts[_c]:,}행)</span></span>')
            _chip = "".join(_chips)
            _detail = t("s4.syn_type_fixed_desc", n=len(syn_df))
        st.markdown(
            f'<div style="background:var(--bg-card);border:1px solid var(--border);'
            f'border-left:3px solid {T["purple"] if _is_random else T["red"]};'
            f'border-radius:10px;padding:12px 16px;margin:6px 0 10px">'
            f'<div style="color:{T["text_muted"]};font-size:10px;letter-spacing:0.07em;'
            f'text-transform:uppercase;font-weight:700;margin-bottom:7px">'
            f'{t("s4.syn_type_label")}</div>{_chip}'
            f'<div style="color:{T["text_secondary"]};font-size:11.5px;margin-top:7px">{_detail}</div>'
            f'</div>', unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════
        # ✨ v14 (요청 6): 이 합성 데이터를 그대로 세션5로 보내 탐지·일괄분석
        #   세션5 합성탭이 읽는 'tab4_rows'에 그대로 주입하고 탭까지 예약한다.
        # ══════════════════════════════════════════════════════
        _sndL, _sndR = st.columns([1, 1] if CV else [1, 2.2])
        with _sndL:
            if st.button(t("s4.send_to_s5"), type="primary", width='stretch',
                         key="s4_send_s5", help=t("s4.send_to_s5_help")):
                _rows_out = syn_df.to_dict('records')
                for _r in _rows_out:
                    _r['_input_mode'] = 'synthetic'
                    _r.setdefault('_target_type',
                                  'random' if _is_random else str(_tt_counts.index[0]))
                st.session_state['tab4_rows'] = _rows_out
                st.session_state['batch_rows'] = _rows_out      # 일괄 분석도 바로 가능
                st.session_state['session_idx'] = 4
                st.session_state['_pending_s5_tab'] = 'tab4'
                st.session_state.pop('det', None)               # 이전 단건 결과 정리
                st.toast(t("s4.sent_to_s5", n=len(_rows_out)))
                st.rerun()
        with _sndR:
            st.caption(t("s4.send_to_s5_note", n=len(syn_df)))

        # ✨ v9.4: 컴팩트 — [PASS/FAIL 표 | 분포 차트] 좌우 · 미리보기는 아래 풀폭
        _s4a, _s4b = crow([1, 1], gap="medium")
        with _s4a:
            section_header(t("s4.pass_title"),"PASS/FAIL")
            CHECK_COLS={'Transaction_Amount':(t("s4.check_amount"),-382_480_000,406_690_000),'Distance':(t("s4.check_distance"),0,612),'Account_balance':(t("s4.check_balance"),-45_756_563,408_024_828)}
            check_results=[]
            for col,(label,mn,mx) in CHECK_COLS.items():
                if col in syn_df.columns:
                    ir=((syn_df[col]>=mn)&(syn_df[col]<=mx)).mean()
                    check_results.append({"항목":label,"컬럼":col,"기준 범위":f"{mn:,} ~ {mx:,}","합성 Min":f"{syn_df[col].min():,.0f}","합성 Max":f"{syn_df[col].max():,.0f}","범위 내":f"{ir*100:.1f}%","결과":"PASS" if ir>0.95 else "FAIL"})
            # ✨ v11: 챗봇용 화면 스냅샷 — 위 PASS/FAIL 표에 쓴 check_results 그대로 저장(재로딩 없음)
            try:
                _s4_lines = [f"합성 데이터 QA(세션4, 생성 {len(syn_df):,}행)"]
                for _r4 in check_results:
                    _s4_lines.append(f"  · {_r4['항목']}: 기준범위 내 {_r4['범위 내']} → {_r4['결과']} "
                                      f"(합성 범위 {_r4['합성 Min']}~{_r4['합성 Max']})")
                if df_ref is not None:
                    for _cc4 in ('Transaction_Amount', 'Distance', 'Account_balance'):
                        if _cc4 in syn_df.columns and _cc4 in df_ref.columns:
                            _s4_lines.append(f"  · {_cc4} 평균: 원본 {df_ref[_cc4].mean():,.0f} vs 합성 {syn_df[_cc4].mean():,.0f}")
                _snap_set("04", _s4_lines)
            except Exception:
                pass
            rh=""
            for r in check_results:
                badge=f'<span class="tag-pass">{t("s4.pass_badge")}</span>' if r["결과"]=="PASS" else f'<span class="tag-fail">{t("s4.fail_badge")}</span>'
                rh+=f'<tr style="border-bottom:1px solid {ROW_BORDER}"><td style="padding:10px 12px;color:{T["text_primary"]};font-weight:600">{r["항목"]}</td><td style="padding:10px 12px;font-family:JetBrains Mono;font-size:11px;color:{T["text_secondary"]}">{r["컬럼"]}</td><td style="padding:10px 12px;font-family:JetBrains Mono;font-size:11px;color:{T["text_secondary"]}">{r["기준 범위"]}</td><td style="padding:10px 12px;font-family:JetBrains Mono;font-size:11px;color:{T["text_secondary"]}">{r["합성 Min"]} ~ {r["합성 Max"]}</td><td style="padding:10px 12px;font-family:JetBrains Mono;font-size:11px;color:{T["accent"]}">{r["범위 내"]}</td><td style="padding:10px 12px">{badge}</td></tr>'
            st.markdown(f'<table style="width:100%;border-collapse:collapse;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;overflow:hidden"><thead><tr style="background:{T["bg_surface"]}"><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase;font-weight:700">{t("s4.th_item")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase;font-weight:700">{t("s4.th_column")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase;font-weight:700">{t("s4.th_range")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase;font-weight:700">{t("s4.th_syn_range")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase;font-weight:700">{t("s4.th_in_range")}</th><th style="padding:10px 12px;text-align:left;color:{T["text_muted"]};font-size:10px;letter-spacing:0.06em;text-transform:uppercase;font-weight:700">{t("s4.th_result")}</th></tr></thead><tbody>{rh}</tbody></table>',unsafe_allow_html=True)
        with _s4b:
            section_header(t("s4.dist_title"),"DISTRIBUTION")
            if df_ref is not None:
                cmp_col=st.selectbox(t("s4.cmp_col_label"),['Transaction_Amount','Distance','Account_balance'])
                fig=go.Figure()
                fig.add_trace(go.Histogram(x=df_ref[cmp_col].sample(min(1000,len(df_ref)),random_state=42),name=t("s4.legend_original"),opacity=0.65,marker_color=T['accent'],nbinsx=40,histnorm='probability'))
                fig.add_trace(go.Histogram(x=syn_df[cmp_col],name=t("s4.legend_synthetic"),opacity=0.65,marker_color=T['purple'],nbinsx=40,histnorm='probability'))
                # ✨ v7: 원본 vs 합성 평균선 — 분포 중심 이동을 한눈에
                fig.add_vline(x=float(df_ref[cmp_col].mean()),line_dash="dot",line_color=T['accent'],opacity=0.75)
                fig.add_vline(x=float(syn_df[cmp_col].mean()),line_dash="dot",line_color=T['purple'],opacity=0.75)
                fig.update_layout(**PLOTLY_LAYOUT,margin=_M_DEFAULT,barmode='overlay',bargap=0.04,legend=dict(orientation="h",y=1.06),**_hc(240))
                styled_axis(fig)
                st.plotly_chart(fig,width='stretch')
        section_header(t("s4.preview_title"),t("s4.preview_badge", n=len(syn_df)))
        dcols=['Transaction_Amount','Distance','Account_balance','Channel','Operating_System','Access_Medium']+BINARY_FLAGS[:4]
        dcols=[c for c in dcols if c in syn_df.columns]
        if CV:
            st.dataframe(syn_df[dcols].head(20), width='stretch', height=210, hide_index=True)
        else:
            st.dataframe(syn_df[dcols].head(20),width='stretch')
    elif CV:
        # ✨ v9.8 컴팩트: 생성 전 하단 여백을 '결과 슬롯 스켈레톤'으로 채워 무스크롤 레이아웃의 의도를 유지
        #   (일반 모드는 기존대로 빈 상태 — 외형 변화 0)
        _pa, _pb, _pc = crow([1, 1, 1], gap="medium")
        for _slot, _bdg, _ttl in zip((_pa, _pb, _pc),
                                     ("PASS/FAIL", "DISTRIBUTION", "PREVIEW"),
                                     (t("s4.pass_title"), t("s4.dist_title"), t("s4.preview_title"))):
            with _slot:
                st.markdown(
                    f'<div style="border:1px dashed var(--border);border-radius:12px;padding:20px 16px;'
                    f'text-align:center;background:var(--bg-surface)">'
                    f'<div style="font-family:var(--font-mono);font-size:10px;letter-spacing:0.08em;color:{T["text_muted"]}">{_bdg}</div>'
                    f'<div style="font-size:12.5px;margin-top:6px;color:{T["text_secondary"]}">{_ttl}</div>'
                    f'<div style="font-size:16px;margin-top:8px;color:{T["text_muted"]};opacity:0.55">⋯</div></div>',
                    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# 세션 05 — 실시간 탐지 시연
# ══════════════════════════════════════════════════════════
elif current_session=="05":
    page_title(t("s5.title_main"), t("s5.title_span"), color=T["red"], eyebrow=t("s5.eyebrow"))
    # 🔧 FIX(v8.1): 최근 알림 발송 실패 사유 고정 배너 — 토스트는 사라져서 원인 파악 불가했음
    if st.session_state.get('last_notify_error'):
        _ne1, _ne2 = st.columns([11, 1], vertical_alignment="center")
        with _ne1: alert_box(st.session_state['last_notify_error'], "error")
        with _ne2:
            if st.button("✕", key="clear_notify_err", help=t("common.close")):
                st.session_state.pop('last_notify_error', None); st.rerun()
    cbr()

    # ══ ⚙ 탐지 환경 설정 — 접이식 (IA 개선: 입력→탐지 흐름이 먼저 보이도록) ══
    with st.expander(t("s5.env_expander"), expanded=False):
        section_header(t("s5.llm_config_title"),"LLM CONFIG")
        lc1,lc2,lc3=st.columns([2,2,3])
        with lc1:
            llm_provider=st.selectbox(t("s5.llm_provider_label"),["local","anthropic","openai","deepseek","moonshot","custom","fallback"],key="llm_p5",format_func=lambda x:{"local":t("s5.llm_p_local"),"anthropic":t("s5.llm_p_anthropic"),"openai":t("s5.llm_p_openai"),"deepseek":t("s5.llm_p_deepseek"),"moonshot":t("s5.llm_p_moonshot"),"custom":t("s5.llm_p_custom"),"fallback":t("s5.llm_p_fallback")}.get(x,x),help=t("s5.llm_provider_help"))
        with lc2:
            llm_mode=st.selectbox(t("s5.api_mode_label"),["local","cloud"],key="llm_m5",
                                   format_func=lambda x: t("s5.api_mode_local") if x=="local" else t("s5.api_mode_cloud"))
        with lc3:
            if llm_mode=="cloud":
                st.markdown(f'<div class="alert-box alert-info" style="margin:0;padding:10px 14px;font-size:12px">{t("s5.cloud_note", p=llm_provider.upper())}</div>',unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="alert-box alert-warn" style="margin:0;padding:10px 14px;font-size:12px">{t("s5.local_note")}</div>',unsafe_allow_html=True)
        # ── 🌐 커스텀 엔드포인트 설정 (OpenAI 호환 API — OpenRouter 등) ──
        if llm_provider == "custom":
            cu1, cu2, cu3 = st.columns([3, 2.4, 2])
            with cu1:
                st.text_input(t("s5.custom_url_label"), key="ov_custom_url",
                              placeholder="https://openrouter.ai/api/v1/chat/completions",
                              help=t("s5.custom_url_help"))
            with cu2:
                st.text_input(t("s5.custom_model_label"), key="ov_custom_model",
                              placeholder="meta-llama/llama-3.3-70b-instruct",
                              help=t("s5.custom_model_help"))
            with cu3:
                st.text_input(t("s5.custom_key_label"), key="ov_custom_key", type="password",
                              help=t("s5.custom_key_help"))

        # ── LLM 연결 테스트 버튼 ──
        _tc1, _tc2 = st.columns([1, 5])
        with _tc1:
            if st.button(t("s5.conn_test_button"), key="llm_conn_test", type="secondary"):
                with st.spinner(t("s5.conn_test_spinner")):
                    try:
                        _test_anlz = _build_llm_analyzer()
                        _test_r = _test_anlz.test_connection()
                        if _test_r["ok"]:
                            st.success(_test_r["message"])
                        else:
                            st.error(_test_r["message"])
                            for _e in _test_r.get("errors", []):
                                st.markdown(f'<div style="color:{T["red"]};font-size:12px;font-family:var(--font-mono);padding:2px 0">• {_e}</div>', unsafe_allow_html=True)
                    except Exception as _te:
                        st.error(t("s5.conn_test_error", e=_te))
        with _tc2:
            st.markdown(f'<div style="color:{T["text_muted"]};font-size:11px;padding-top:8px">{t("s5.conn_test_desc")}</div>', unsafe_allow_html=True)
        cbr()

        # ── 🖊 v13/v14: AI 프롬프트 편집 — 분석/Slack/Email/배치종합 4종. 챗봇 시스템 프롬프트
        #   편집기와 동일한 패턴(저장=오버라이드, 초기화=삭제)이라 실무자에게 이미 익숙한 UX.
        #   기본값은 llm_analyzer.py·batch_analyzer.py의 DEFAULT_*_PROMPT_TEMPLATE(단일 진실
        #   공급원)를 그대로 가져와 보여준다 — 이 파일에 문구가 중복되지 않는다.
        try:
            from pipeline.llm_analyzer import (DEFAULT_ANALYSIS_PROMPT_TEMPLATE,
                                                DEFAULT_SLACK_PROMPT_TEMPLATE,
                                                DEFAULT_EMAIL_PROMPT_TEMPLATE,
                                                PROMPT_VARS_HELP)
        except ImportError:
            DEFAULT_ANALYSIS_PROMPT_TEMPLATE = DEFAULT_SLACK_PROMPT_TEMPLATE = DEFAULT_EMAIL_PROMPT_TEMPLATE = ""
            PROMPT_VARS_HELP = ""
        try:
            from pipeline.batch_analyzer import DEFAULT_BATCH_PROMPT_TEMPLATE, PROMPT_VARS_HELP_BATCH
        except ImportError:
            DEFAULT_BATCH_PROMPT_TEMPLATE = ""
            PROMPT_VARS_HELP_BATCH = ""
        # ✨ v13 컴팩트: 프롬프트/RAG 편집기를 좌우 2단으로 (세로 2칸 → 1칸)
        _ed_L, _ed_R = crow([1, 1])
        with _ed_L:
         with st.expander(tt("s5.prompt_editor_title"), expanded=False):
             st.caption(tt("s5.prompt_editor_help"))
             # ✨ v14: 슬롯마다 자리표시자 세트가 달라서(단건 vs 배치 집계값) 안내를 탭 안으로 이동
             _PROMPT_SLOTS = [
                 ("analysis", tt("s5.prompt_tab_analysis"), DEFAULT_ANALYSIS_PROMPT_TEMPLATE, PROMPT_VARS_HELP),
                 ("slack",    tt("s5.prompt_tab_slack"),    DEFAULT_SLACK_PROMPT_TEMPLATE,    PROMPT_VARS_HELP),
                 ("email",    tt("s5.prompt_tab_email"),    DEFAULT_EMAIL_PROMPT_TEMPLATE,    PROMPT_VARS_HELP),
                 ("batch",    tt("s5.prompt_tab_batch"),    DEFAULT_BATCH_PROMPT_TEMPLATE,    PROMPT_VARS_HELP_BATCH),
             ]
             _ptabs = st.tabs([_label for _, _label, _, _ in _PROMPT_SLOTS])
             for _ptab, (_slot, _label, _default_tpl, _vars_help) in zip(_ptabs, _PROMPT_SLOTS):
                 with _ptab:
                     if _vars_help:
                         st.caption(f"**{tt('s5.prompt_vars_label')}** — {_vars_help}")
                     _skey = f"prompt_ov_{_slot}"
                     _cur = st.session_state.get(_skey) or _default_tpl
                     _edited = st.text_area(_label, value=_cur, height=220,
                                             label_visibility="collapsed", key=f"prompt_ta_{_slot}")
                     _pc1, _pc2 = st.columns(2)
                     if _pc1.button(tt("s5.prompt_save"), key=f"prompt_save_{_slot}", width='stretch'):
                         st.session_state[_skey] = (_edited or "").strip()
                         st.rerun()
                     if _pc2.button(tt("s5.prompt_reset"), key=f"prompt_reset_{_slot}", width='stretch'):
                         st.session_state.pop(_skey, None)
                         st.rerun()
                     if st.session_state.get(_skey):
                         st.caption(tt("s5.prompt_active"))
         cbr()

        # ── 📚 v11: RAG 기본 문서 편집 (요청 3) ──────────────────
        #   프롬프트 편집기와 동일한 UX(저장=적용, 초기화=기본값 복원).
        #   rag_searcher는 docs/ 변경을 .docs_sig(mtime 해시)로 감지해 자동 재임베딩하므로,
        #   여기서는 파일만 쓰고 _get_rag_cached를 비워 새 인스턴스를 만들게 하면 끝이다.
        with _ed_R:
         with st.expander(tt("s5.rag_editor_title"), expanded=False):
             st.caption(tt("s5.rag_editor_help"))
             try:
                 from pipeline.rag_searcher import DOCS_DIR as _RAG_DOCS, RAGSearcher as _RS
                 _docs_dir = Path(_RAG_DOCS)
                 _docs_dir.mkdir(parents=True, exist_ok=True)
                 _md_files = sorted(_docs_dir.glob("*.md"))
                 st.caption(tt("s5.rag_docs_path", path=str(_docs_dir.resolve()), n=len(_md_files)))

                 if not _md_files:
                     if st.button(tt("s5.rag_create_samples"), key="rag_mk_samples", width='stretch'):
                         try:
                             # RAGSearcher.__init__은 Chroma 초기화까지 하므로, 문서 생성만
                             # 필요한 여기서는 인스턴스 없이 메서드만 호출한다.
                             object.__new__(_RS)._create_sample_docs()
                             _get_rag_cached.clear()
                             st.toast(tt("s5.rag_saved")); st.rerun()
                         except Exception as _re:
                             alert_box(tt("s5.rag_fail", e=_re), "error")
                 else:
                     _rtabs = st.tabs([f.name for f in _md_files])
                     for _rt, _f in zip(_rtabs, _md_files):
                         with _rt:
                             try:
                                 _cur = _f.read_text(encoding="utf-8")
                             except Exception as _re:
                                 _cur = ""
                                 alert_box(tt("s5.rag_read_fail", name=_f.name, e=_re), "error")
                             _ed = st.text_area(_f.name, value=_cur, height=260,
                                                label_visibility="collapsed",
                                                key=f"rag_ta_{_f.name}")
                             _rc1, _rc2, _rc3 = st.columns([1, 1, 1])
                             if _rc1.button(tt("s5.rag_save"), key=f"rag_save_{_f.name}", width='stretch'):
                                 try:
                                     _f.write_text(_ed, encoding="utf-8")
                                     _get_rag_cached.clear()      # 🔑 캐시된 RAGSearcher 폐기 → 재임베딩
                                     st.toast(tt("s5.rag_saved")); st.rerun()
                                 except Exception as _re:
                                     alert_box(tt("s5.rag_fail", e=_re), "error")
                             if _rc2.button(tt("s5.rag_reindex"), key=f"rag_reidx_{_f.name}", width='stretch'):
                                 try:
                                     # FDS_CHROMA_DIR 환경변수로 위치가 바뀔 수 있으므로
                                     # 경로를 하드코딩하지 않고 클래스 속성을 그대로 쓴다.
                                     _sig = Path(_RS._SIG_PATH)
                                     if _sig.exists():
                                         _sig.unlink()            # 서명 삭제 → 다음 init에서 강제 재구축
                                     _get_rag_cached.clear()
                                     st.toast(tt("s5.rag_reindexed")); st.rerun()
                                 except Exception as _re:
                                     alert_box(tt("s5.rag_fail", e=_re), "error")
                             if _rc3.button(tt("s5.rag_delete"), key=f"rag_del_{_f.name}", width='stretch'):
                                 if st.session_state.get(f"_rag_del_ok_{_f.name}"):
                                     try:
                                         _f.unlink(); _get_rag_cached.clear()
                                         st.session_state.pop(f"_rag_del_ok_{_f.name}", None)
                                         st.toast(tt("s5.rag_deleted", name=_f.name)); st.rerun()
                                     except Exception as _re:
                                         alert_box(tt("s5.rag_fail", e=_re), "error")
                                 else:
                                     st.session_state[f"_rag_del_ok_{_f.name}"] = True
                                     alert_box(tt("s5.rag_delete_confirm", name=_f.name), "warn")

                 st.divider()
                 _nc1, _nc2 = st.columns([3, 1])
                 _newname = _nc1.text_input(tt("s5.rag_new_label"), key="rag_new_name",
                                            placeholder="my_scenarios.md")
                 if _nc2.button(tt("s5.rag_new_btn"), key="rag_new_btn", width='stretch'):
                     _nm = (_newname or "").strip()
                     if not _nm:
                         alert_box(tt("s5.rag_new_empty"), "warn")
                     elif ("/" in _nm) or ("\\" in _nm) or _nm.startswith("."):
                         alert_box(tt("s5.rag_new_bad"), "error")   # 경로 탈출 방지
                     else:
                         if not _nm.endswith(".md"):
                             _nm += ".md"
                         _np = _docs_dir / _nm
                         if _np.exists():
                             alert_box(tt("s5.rag_new_dup", name=_nm), "warn")
                         else:
                             _np.write_text(f"# {_nm[:-3]}\n\n", encoding="utf-8")
                             _get_rag_cached.clear()
                             st.toast(tt("s5.rag_saved")); st.rerun()
             except Exception as _re:
                 alert_box(tt("s5.rag_fail", e=_re), "error")
        cbr()


        # ── 자동 발송 설정 (탐지 전 미리 설정) ─────────────────
        # ✨ v13 컴팩트: 2차 설정 섹션은 접이식으로 재배치 → 세로 점유 대폭 감소(삭제 아님)
        with csec(t("s5.auto_notify_title"), "AUTO NOTIFY"):
         an1, an2, an3 = st.columns(([1, 1, 1.2] if CV else [1.5, 1.5, 3]))
         with an1:
             st.session_state['auto_slack'] = st.toggle(t("s5.slack_toggle"), value=st.session_state.get('auto_slack', False), key="tg_slack_cfg")
             st.session_state['auto_email'] = st.toggle(t("s5.email_toggle"), value=st.session_state.get('auto_email', False), key="tg_email_cfg")
             st.session_state['rich_notify'] = st.toggle(t("notif.rich_toggle"), value=st.session_state.get('rich_notify', True), key="tg_rich_cfg", help=t("notif.rich_help"))
             if st.session_state.get('dual_threshold', False):
                 st.caption(tt("s5.dual_active_note"))   # ✨ v9.1
             # ── 🚦 v19: 챗봇 발송 승인 게이트 (기본 ON) ──
             #   기본은 '요청 → 사람 승인 → 발송'. 빠른 업무를 선호하면 끌 수 있지만,
             #   끄면 LLM의 판단만으로 되돌릴 수 없는 발송이 일어나므로 경고를 표시한다.
             st.session_state['agent_send_confirm'] = st.toggle(
                 tt("s5.agent_gate_toggle"),
                 value=bool(st.session_state.get('agent_send_confirm', True)),
                 key="tg_agent_gate", help=tt("s5.agent_gate_help"))
             if not st.session_state['agent_send_confirm']:
                 st.markdown(
                     f'<div style="color:{T["amber"]};font-size:10.5px;line-height:1.55;'
                     f'margin-top:2px">{tt("s5.agent_gate_off_warn")}</div>',
                     unsafe_allow_html=True)
                 if st.session_state.get('pii_mask_level', 'standard') == 'off':
                     st.markdown(
                         f'<div style="color:{T["red"]};font-size:10.5px;line-height:1.55;'
                         f'margin-top:2px;font-weight:700">{tt("s5.agent_gate_off_pii")}</div>',
                         unsafe_allow_html=True)
             # 감사 로그 — 게이트 없이 나간 발송 기록
             _aud = st.session_state.get('_send_audit') or []
             if _aud:
                 with st.expander(tt("s5.agent_audit_title", n=len(_aud)), expanded=False):
                     for _a in _aud[-8:][::-1]:
                         st.caption(f"{'✅' if _a['ok'] else '❌'} {_a['at']} · {_a['ch']} · "
                                    f"{str(_a['ft']).upper()}형 {_a['risk']:.4f} · "
                                    f"{_a['to'] or '-'} · mask={_a['mask']}")
         with an2:
             st.text_input(t("s5.recipient_label"), key="notify_email",
                           placeholder="fds-oncall@company.com",
                           help=t("s5.recipient_help"))
             # ✨ v8.2: 실제 발송될 주소를 투명하게 표시 — "비면 .env" 동작의 가시화
             if not (st.session_state.get('notify_email') or '').strip():
                 _eff = _effective_notify_email()
                 st.caption(t("notif.recipient_fallback", addr=_eff) if _eff else t("notif.recipient_none"))
         with an3:
             st.markdown(f'<div style="color:{T["text_muted"]};font-size:11px;padding-top:8px">{t("s5.auto_notify_desc")}</div>', unsafe_allow_html=True)
        cbr()

        # ── 개인정보 마스킹 설정 ─────────────────────────────
        with csec(t("s5.pii_title"), "PII MASKING"):
         mk1, mk2, mk3 = st.columns(([1.4, 1, 1.6] if CV else [2, 1.5, 2.5]))
         with mk1:
             try:
                 from pipeline.pii_masker import LEVEL_LABELS
                 _mask_options = list(LEVEL_LABELS.keys())
                 _mask_labels = list(LEVEL_LABELS.values())
             except ImportError:
                 _mask_options = ["off", "basic", "standard", "strict"]
                 _mask_labels = [t("s5.pii_off"), t("s5.pii_basic"), t("s5.pii_standard"), t("s5.pii_strict")]
             if "_pending_pii" in st.session_state:      # ✨ v15 에이전트 마스킹 강도 변경
                 st.session_state['pii_mask_level'] = st.session_state.pop("_pending_pii")
                 st.session_state.pop("pii_sel", None)
             _cur_mask = st.session_state.get('pii_mask_level', 'standard')
             _cur_idx = _mask_options.index(_cur_mask) if _cur_mask in _mask_options else 2
             st.session_state['pii_mask_level'] = st.selectbox(
                 t("s5.pii_level_label"),
                 _mask_options,
                 index=_cur_idx,
                 format_func=lambda x: dict(zip(_mask_options, _mask_labels)).get(x, x),
                 key="pii_sel",
             )
         with mk2:
             st.session_state['pii_skip_local'] = st.toggle(
                 t("s5.pii_skip_local_label"),
                 value=st.session_state.get('pii_skip_local', True),
                 key="pii_skip_local_tg",
                 help=t("s5.pii_skip_local_help"),
             )
         with mk3:
             _lvl = st.session_state.get('pii_mask_level', 'standard')
             _skip = st.session_state.get('pii_skip_local', True)
             _provider = st.session_state.get('llm_p5', 'local')
             _desc_map = {
                 "off": t("s5.pii_desc_off"),
                 "basic": t("s5.pii_desc_basic"),
                 "standard": t("s5.pii_desc_standard"),
                 "strict": t("s5.pii_desc_strict"),
             }
             _effective = t("s5.pii_effective_off") if (_skip and _provider == "local" and _lvl != "off") else _desc_map.get(_lvl,"")
             _box_type = "alert-ok" if (_skip and _provider == "local") else "alert-info"
             st.markdown(f'<div class="alert-box {_box_type}" style="margin:0;padding:10px 14px;font-size:12px">{_effective}</div>', unsafe_allow_html=True)
        cbr()

        # ── 연결 상태 테스트 ─────────────────────────────────
        section_header(t("s5.conn_status_title"),"CONNECTION TEST")
        tc1, tc2, tc3, tc4 = st.columns(4)
        with tc1:
            if st.button(t("s5.test_ml_button"), key="test_ml", width='stretch'):
                try:
                    _mpath = get_available_models().get(st.session_state.get('selected_model',default_model_name(get_available_models())), {}).get("path", str(_BASE_MODEL_PATH or "models/lgbm_fds.pkl"))
                    clf = _get_ml_classifier(_mpath)
                    alert_box(t("s5.test_ml_ok"), "ok")
                except Exception as e:
                    alert_box(t("s5.test_ml_fail", e=e), "error")
        with tc2:
            if st.button(t("s5.test_rag_button"), key="test_rag", width='stretch'):
                try:
                    rag = _build_rag(1)
                    ctx = rag.search(t("s5.test_rag_query"), "a")
                    alert_box(t("s5.test_rag_ok", n=(len(ctx) if isinstance(ctx,list) else 'OK')), "ok")
                except Exception as e:
                    alert_box(t("s5.test_rag_fail", e=e), "error")
        with tc3:
            if st.button(t("s5.test_llm_button"), key="test_llm", width='stretch'):
                # 🔴 FIX(v10): 기존엔 analyze()를 호출해 **LLM 3단계 풀 생성**(1536+200+1536 토큰,
                #   타임아웃 180+45+180초 = 최대 6분 45초)을 돌렸다. 연결 확인엔 과도하고
                #   화면이 몇 분간 멈춘다 → 위쪽 진단 패널과 동일한 test_connection()
                #   (32토큰 / 12초 ping)으로 통일.
                try:
                    _r = _build_llm_analyzer().test_connection()
                    if _r["ok"]:
                        st.markdown(f'<div class="alert-box alert-ok">{_r["message"]}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="alert-box alert-error">{_r["message"]}</div>', unsafe_allow_html=True)
                        for _e in _r.get("errors", []):
                            st.markdown(f'<div style="color:{T["red"]};font-size:12px;font-family:var(--font-mono);padding:2px 0">• {_e}</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.markdown(f'<div class="alert-box alert-error">{t("s5.test_llm_fail", e=e)}</div>', unsafe_allow_html=True)
        with tc4:
            if st.button(t("s5.test_notify_button"), key="test_notify", width='stretch'):
                try:
                    # 🔧 FIX(v8.1): 기존엔 객체 생성만 하고 무조건 성공 표시 — 실제 접속+로그인으로 교체
                    n = _build_notifier()
                    _stat = n.check_status()
                    if _stat["smtp_configured"]:
                        _ok, _detail = n.test_smtp()
                        alert_box(t("notif.smtp_ok", detail=_detail) if _ok else t("notif.smtp_fail", detail=_detail),
                                  "ok" if _ok else "error")
                    else:
                        alert_box(t("notif.smtp_fail", detail="SMTP_USER/PASS 미설정"), "warn")
                    alert_box(("✅ Slack webhook: " + _stat["slack_url_prefix"]) if _stat["slack_configured"]
                              else "⚠ SLACK_WEBHOOK_URL 미설정", "ok" if _stat["slack_configured"] else "warn")
                except Exception as e:
                    st.markdown(f'<div class="alert-box alert-error">{t("s5.test_notify_fail", e=e)}</div>', unsafe_allow_html=True)
        cbr()

        # ── 탐지 모델 (전역 — 변경은 좌측 사이드바) ─────────────
        section_header(t("s5.model_section_title"),"MODEL · GLOBAL")
        avail_models = get_available_models()
        selected_model = st.session_state['selected_model'] if st.session_state['selected_model'] in avail_models else next(iter(avail_models))
        minfo = avail_models[selected_model]
        model_exists = Path(minfo["path"]).exists()
        status_badge = f'<span class="badge-safe">{t("sb.model_loadable")}</span>' if model_exists else f'<span class="badge-danger">{t("sb.model_missing")}</span>'
        st.markdown(f'<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:12px 16px;margin-top:4px"><div style="display:flex;align-items:center;gap:10px;margin-bottom:4px"><span style="font-family:var(--font-mono);font-size:13px;font-weight:700;color:var(--accent)">🧠 {model_display_name(selected_model, LANG)}</span>{status_badge}<span style="color:var(--text-muted);font-size:10.5px;margin-left:auto">{t("common.change_model_hint")}</span></div><p style="color:var(--text-secondary);font-size:12px;margin:0">{minfo["desc"]}</p><p style="color:var(--text-muted);font-size:11px;margin:4px 0 0;font-family:var(--font-mono)">{minfo["path"]}</p></div>', unsafe_allow_html=True)
        cbr()

    # ✨ v9.3: 컴팩트 좌우 2단 — [왼쪽] 탐지 입력·설정 / [오른쪽] 탐지 결과·AI 분석
    #   일반 모드에선 crow가 풀폭 컨테이너를 돌려주어 기존처럼 세로로 순차 배치된다.
    _s5L, _s5R = crow([1.0, 1.15], gap="medium")
    # ✨ v14 (요청 4): 컴팩트 모드에서 단건 결과가 없으면 우측 패널이 "아직 결과 없음"으로
    #   비어 있는데 배치 결과는 좌측 아래로 계속 쌓여 스크롤을 유발했다.
    #   → 미리 우측에 컨테이너를 확보해두고, 배치 결과를 그 자리에 그린다(placeholder 패턴).
    _batch_slot = None
    if CV and st.session_state.get('batch_res') and not st.session_state.get('det'):
        with _s5R:
            _batch_slot = st.container()
    with _s5L:
        section_header(t("s5.input_mode_title"),"INPUT MODE")
        # AI 분석 포함 여부 토글
        _imc1, _imc2 = st.columns([1.5, 4])
        with _imc1:
            st.session_state['run_with_llm'] = st.toggle(t("s5.ai_include_toggle"), value=st.session_state.get('run_with_llm', True), key="tg_run_llm", help=t("s5.ai_include_help"))
        with _imc2:
            # 컴팩트(발표)에선 토글 옆 설명 문단을 생략해 한 행을 회수 — 설명은 토글 툴팁(?)에 유지됨
            if not CV:
                if st.session_state.get('run_with_llm', True):
                    _p = st.session_state.get('llm_p5','local')
                    st.markdown(f'<div style="color:{T["text_muted"]};font-size:11px;padding-top:8px">{t("s5.ai_include_on_desc", p=_p)}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div style="color:{T["text_muted"]};font-size:11px;padding-top:8px">{t("s5.ai_include_off_desc")}</div>', unsafe_allow_html=True)
        # ✨ v6.5: 기본 탭 = 📊 train.csv (가장 자주 쓰는 경로를 첫 번째로)
        if st.session_state.get("_pending_s5_tab"):          # 🤖 챗 예약 탭 적용(위젯 생성 직전)
            st.session_state["s5_active_tab"] = st.session_state.pop("_pending_s5_tab")
        _S5_ORDER = ["tab3","tab1","tab2","tab4","tab5"]   # 기존 st.tabs 표시 순서 유지
        _s5_active = _seg_nav("s5_active_tab", _S5_ORDER,
                              {k: t(f"s5.{k}") for k in _S5_ORDER}, default="tab3")
        row_to_predict=None

        if _s5_active=="tab1":
            if st.session_state.get("_pending_manual"):      # 🤖 챗 예약값 적용(위젯 생성 직전)
                for _wk, _wv in st.session_state.pop("_pending_manual").items():
                    st.session_state[_wk] = _wv
            # ✨ v18 (요청 6): '고위험 시나리오 자동입력'을 폼 위 → 폼 아래로 이동.
            #   컴팩트 모드에서 이 버튼이 2줄로 접혀 세로를 낭비했고, 입력을 다 채운 뒤
            #   누르는 경우가 없어(누르면 값을 덮어씀) 폼 앞에 있을 이유도 없었다.
            #   → 계좌잔액·접근매체 바로 아래에서 [탐지 실행]과 나란히 배치한다.
            # 기본값은 session_state에 1회만 시딩 — value=와 key= 동시 지정 경고 방지
            _MANUAL_DEFAULTS = {'amount_in':500_000,'dist_in':50,'bal_in':10_000_000,'ch_in':'ATM','os_in':'Windows','am_in':'a'}
            for _mk,_mv in _MANUAL_DEFAULTS.items():
                if _mk not in st.session_state: st.session_state[_mk]=_mv
            c1,c2,c3=st.columns(3)
            with c1:
                st.markdown(f'<p style="color:{T["text_muted"]};font-size:11px;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px">{t("s5.section_txn_info")}</p>',unsafe_allow_html=True)
                amount=st.number_input(t("s5.amount_label"),-400_000_000,400_000_000,step=100_000,key='amount_in',
                    help=t("s5.amount_help"))
                distance=st.slider(t("s5.distance_label"),0,620,key='dist_in',
                    help=t("s5.distance_help"))
                balance=st.number_input(t("s5.balance_label"),-50_000_000,410_000_000,step=100_000,key='bal_in',
                    help=t("s5.balance_help"))
            with c2:
                st.markdown(f'<p style="color:{T["text_muted"]};font-size:11px;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px">{t("s5.section_env_info")}</p>',unsafe_allow_html=True)
                channel=st.selectbox(t("s5.channel_label"),CAT_OPTIONS['Channel'],key='ch_in',
                    help=t("s5.channel_help"))
                os_=st.selectbox(t("s5.os_label"),CAT_OPTIONS['Operating_System'],key='os_in',
                    help=t("s5.os_help"))
                acc_med=st.selectbox(t("s5.access_medium_label"),CAT_OPTIONS['Access_Medium'],key='am_in',
                    format_func=lambda v: f"{v} — {ACCESS_MEDIUM_MAP.get(v,'-')}",
                    help=t("s5.access_medium_help"))
            with c3:
                st.markdown(f'<p style="color:{T["text_muted"]};font-size:11px;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px">{t("s5.section_risk_flags")}</p>',unsafe_allow_html=True)
                flag_vals={}
                for flag,label in list(FLAG_LABELS.items())[:12]:
                    if f"flag_{flag}" not in st.session_state: st.session_state[f"flag_{flag}"]=False
                    flag_vals[flag]=int(st.checkbox(label,key=f"flag_{flag}",help=FLAG_HELP.get(flag)))
            cbr()
            # ✨ v18: [⚡고위험 자동입력 | ▶탐지 실행] 나란히 — 컴팩트에서 세로 1줄 절약
            _acL, _acR = st.columns([1.15, 1] if CV else [1, 1.4])
            with _acL:
                if st.button(t("s5.autofill_button"), key="manual_autofill", width='stretch',
                             help=t("s5.autofill_help")):
                    st.session_state.update({'amount_in':-85_000_000,'dist_in':480,'bal_in':120_000_000,'ch_in':'ATM','os_in':'Others','am_in':'a','flag_Customer_rooting_jailbreak_indicator':True,'flag_Customer_VPN_Indicator':True,'flag_Customer_flag_terminal_malicious_behavior_1':True,'flag_Unused_terminal_status':True,'flag_Recipient_account_suspend_status':True})
                    st.rerun()
            with _acR:
                _run_manual_go = st.button(t("s5.detect_button"), type="primary",
                                           key="run_manual", width='stretch')
            if _run_manual_go or st.session_state.pop("_pending_run_manual", False):
                row_to_predict={'Transaction_Amount':amount,'Distance':distance,'Account_balance':balance,'Channel':channel,'Operating_System':os_,'Access_Medium':acc_med,'Customer_credit_rating':'B','Customer_loan_type':'a','Error_Code':'a','Type_General_Automatic':'general','Customer_Gender':'male',**flag_vals,'_input_mode':'manual'}

        if _s5_active=="tab2":
            cbr()
            if not CV: st.markdown(f'<div class="alert-box alert-info">{t("s5.t2_info")}</div>',unsafe_allow_html=True)
            # ✨ v9.8 컴팩트: 버튼 하단 정렬 + 과하게 넓던 숫자 입력 폭 축소(버튼에 배분). 일반 모드는 기존 비율 유지.
            _t2_spec = [1.5, 1.5, 3.0] if CV else [2, 2, 3]
            t2c1,t2c2,t2c3=st.columns(_t2_spec, vertical_alignment="bottom")
            with t2c1: t2_n=st.number_input(t("s5.sample_count_label"),1,50,1,step=1,key="t2_n")
            with t2c2: t2_seed=st.number_input(t("s5.seed_label"),-1,9999,-1,key="t2_seed",help=t("s5.seed_help"))
            with t2c3:
                t2_run=st.button(t("s5.random_extract_button"),key="run_test",width='stretch')
            if t2_run:
                df_test=load_test_df(test_path)
                if df_test is not None:
                    sampled=df_test.sample(min(int(t2_n),len(df_test)),random_state=_resolve_seed(t2_seed))
                    st.session_state['tab2_rows']=sampled.to_dict('records')
                    st.markdown(f'<div class="alert-box alert-ok">{t("s5.extract_success", n=len(sampled))}</div>',unsafe_allow_html=True)
                else: st.markdown(f'<div class="alert-box alert-error">{t("s5.testcsv_missing", p=test_path)}</div>',unsafe_allow_html=True)
            if 'tab2_rows' in st.session_state:
                rp=st.session_state['tab2_rows'];st.dataframe(pd.DataFrame(rp),width='stretch')
                if len(rp)>1:
                    si=st.selectbox(t("s5.row_select_label"),range(len(rp)),format_func=lambda i:t("s5.row_select_fmt", i=i+1, id=rp[i].get('ID',i)),key="t2_sel")
                    sr=rp[si]
                else: sr=rp[0]
                sr['_input_mode']='test_csv'
                # ✨ v5.3: 탐지 실행 | 일괄 분석 — 나란히 배치
                _bc1, _bc2 = st.columns(2)
                with _bc1:
                    if st.button(t("s5.run_detect_arrow"), key="run_test2", type="primary", width='stretch'): row_to_predict=sr
                with _bc2:
                    if len(rp) >= 2:
                        if st.button(tt("s5.batch_button", n=len(rp)), key="batch_test", width='stretch'):
                            st.session_state['batch_rows'] = rp
                            st.session_state['batch_go'] = True
                    else:
                        st.caption(tt("s5.batch_min_warn"))

        if _s5_active=="tab3":
            cbr()
            if not CV: st.markdown(f'<div class="alert-box alert-info">{t("s5.t3_info")}</div>',unsafe_allow_html=True)
            # ✨ v6.1: 데이터 소스 = CSV 또는 사이드바 선택 parquet (tr/va/추가분 자동 노출) + 유형 필터 — 한 줄
            _ds_f3 = _discover_ds(st.session_state.get('ds_folder', 'data/'))
            _pq_opts3 = ["csv"] + sorted(k for k, v in _ds_f3.items() if v.has_label and v.kind in ("parquet","parquet_xy"))
            _pq_disp3 = lambda x: tt("s5.tab3_src_csv") if x == "csv" else f"📦 {x}"
            # ── ✨ v8.6: 사이드바 '평가 데이터셋'과 소프트 연동 (기본 ON, 토글로 독립 전환) ──
            #   완전 통합 대신 연동인 이유: ① 역할이 다름(분석 대상 vs 추출처 — 교차 시나리오 유효)
            #   ② 선택지 집합이 다름(이 탭은 라벨 보유 parquet + 원본 CSV만) → 전역 선택이 미지원이면 로컬 유지
            if 't3_link' not in st.session_state: st.session_state['t3_link'] = True
            _t3_link = st.toggle(t("link.toggle"), key="t3_link", help=t("link.help"))
            # ✨ v8.10: 역방향 동기화 — 여기서 바꾸면 사이드바 '평가 데이터셋'도 함께 변경 (양방향)
            def _t3_reverse_sync():
                if not st.session_state.get('t3_link', True):
                    return
                _sel = st.session_state.get('t3_src')
                _g = "train.csv" if _sel == "csv" else _sel
                if _g and st.session_state.get('selected_dataset') != _g:
                    st.session_state['selected_dataset'] = _g
                    st.session_state['ds_sel_global'] = _g
            _t3_link_note = ""
            if _t3_link and len(_pq_opts3) > 1:
                _g_ds = st.session_state.get('selected_dataset', '')
                # 전역 선택 → 이 탭 옵션 매핑 (라벨 보유 csv는 '원본 CSV' 항목으로)
                _g_mapped = None
                if _g_ds in _pq_opts3:
                    _g_mapped = _g_ds
                elif _g_ds == "train.csv":
                    # '원본 CSV' 항목은 train.csv 전용 — 다른 라벨 csv를 여기 매핑하면 엉뚱한 데이터 추출
                    _g_mapped = "csv"
                if _g_mapped is not None:
                    if st.session_state.get("t3_src") != _g_mapped:
                        st.session_state["t3_src"] = _g_mapped     # 위젯 생성 전 주입 → 추종
                elif _g_ds:
                    _t3_link_note = t("link.unsupported", name=_g_ds)
            # ✨ v9.8 컴팩트: 좁은 좌측 컬럼에서 '데이터 소스' 셀렉트가 눌리지 않게 비율 재조정
            #   (주사위 칸을 줄여 셀렉트에 배분 · 숫자 입력 폭은 유지해 스테퍼 깨짐 방지). 일반 모드는 기존 비율.
            _t3_spec = [1.2, 1.2, 3.1, 2.1, 0.5] if CV else [1.2, 1.2, 2.8, 2, 0.8]
            t3c1,t3c2,t3c3,t3c4,t3c5=st.columns(_t3_spec, vertical_alignment="bottom")
            with t3c1: t3_n=st.number_input(t("s5.sample_count_label"),1,50,1,step=1,key="t3_n")
            with t3c2: t3_seed=st.number_input(t("s5.seed_label"),-1,9999,-1,key="t3_seed",help=t("s5.seed_help"))
            with t3c3:
                # 🔧 FIX(v8.10): disabled 제거 — 연동 중에도 자유 선택 + 사이드바로 역전파
                _t3_src = st.selectbox(tt("s5.tab3_src_label"), _pq_opts3, key="t3_src",
                                       format_func=_pq_disp3,
                                       on_change=_t3_reverse_sync) if len(_pq_opts3) > 1 else "csv"
                if _t3_link_note:
                    st.caption(_t3_link_note)
                # 🐛 FIX(v14): "↔ 사이드바와 양방향 연동 중..." 캡션 제거 — 좁은 컬럼(t3c3)에서
                #   줄바꿈되어 이 컬럼만 키가 커지고, vertical_alignment="bottom" 정렬 기준이
                #   틀어지면서 데이터 소스 셀렉트가 옆 칸(표본수/시드)보다 아래로 밀려 보이던 문제.
                #   연동 자체(_t3_link 토글)는 그대로 동작 — 안내 문구만 제거.
            with t3c4:
                _t3_opts=["all_both","all_fraud"]+list("abcdefghijkl")+["m"]
                _t3_disp={"all_both":t("s5.type_filter_all_both"),"all_fraud":t("s5.type_filter_all_fraud"),"m":t("s5.type_filter_normal")}
                t3_type=st.selectbox(t("s5.type_filter_label"),_t3_opts,format_func=lambda x:_t3_disp.get(x,x.upper()),key="t3_type")
            with t3c5:
                t3_run=st.button("🎲",key="run_train",width='stretch',help=t("s5.random_dice_help"))
            if t3_run:
                _t3_sel = st.session_state.get("t3_src", "csv")
                if _t3_sel != "csv" and _t3_sel in _ds_f3:
                    df_tr, _ = load_selected_dataset(st.session_state.get('ds_folder','data/'), _t3_sel)
                    # 🔧 FIX(호환성): 로더의 라벨 디코딩 실패로 정수 라벨이 남아온 경우 — 문자열로 통일해 'm' 비교 오작동 방지
                    if df_tr is not None and 'Fraud_Type' in df_tr.columns:
                        df_tr = df_tr.copy(); df_tr['Fraud_Type'] = df_tr['Fraud_Type'].astype(str)
                        if not df_tr['Fraud_Type'].isin(list("abcdefghijklm")).any():
                            alert_box(t("compat.t3_label_decode"), "warn")
                        # 🔧 FIX(호환성): is_fraud = 라벨과 100% 일치하는 누출 피처(검증됨) — 모델 입력 포함 시 성능 왜곡
                        if 'is_fraud' in df_tr.columns:
                            _leak_alert("compat.leak_t3")
                else:
                    df_tr = load_train_df()
                if df_tr is not None:
                    if t3_type=="all_both": pool=df_tr
                    elif t3_type=="all_fraud": pool=df_tr[df_tr['Fraud_Type']!='m']
                    elif t3_type=="m": pool=df_tr[df_tr['Fraud_Type']=='m']
                    else: pool=df_tr[df_tr['Fraud_Type']==t3_type]
                    if len(pool)==0: st.markdown(f'<div class="alert-box alert-warn">{t("s5.type_no_data", type=t3_type)}</div>',unsafe_allow_html=True)
                    else:
                        sampled=pool.sample(min(int(t3_n),len(pool)),random_state=_resolve_seed(t3_seed))
                        rl=[]
                        _src_mode = 'parquet_encoded' if st.session_state.get("t3_src","csv")!="csv" else 'train_csv'
                        for _,r in sampled.iterrows():
                            d=r.to_dict();d['_input_mode']=_src_mode;d['_true_label']=str(d.get('Fraud_Type','') if d.get('Fraud_Type') is not None else '');rl.append(d)  # 🔧 FIX(호환성): 정수 라벨 방어
                        st.session_state['tab3_rows']=rl
                        st.markdown(f'<div class="alert-box alert-ok">{t("s5.extract_success", n=len(rl))}</div>',unsafe_allow_html=True)
            if 'tab3_rows' in st.session_state:
                rl=st.session_state['tab3_rows']
                st.dataframe(pd.DataFrame([{k:v for k,v in r.items() if not k.startswith('_')} for r in rl]),width='stretch')
                if len(rl)>1:
                    si3=st.selectbox(t("s5.row_select_label"),range(len(rl)),format_func=lambda i:t("s5.row_select_true_fmt", i=i+1, type=str(rl[i].get('_true_label','?')).upper(), id=rl[i].get('ID',i)),key="t3_sel")
                    sr3=rl[si3]
                else: sr3=rl[0]
                tl=sr3.get('_true_label','')
                st.markdown(f'{t("s5.true_answer_label")} <span class="badge-danger">{FRAUD_SHORT.get(tl,tl or "—")}</span>',unsafe_allow_html=True)
                # ✨ v5.3: 탐지 실행 | 일괄 분석 — 나란히 배치
                _bc1, _bc2 = st.columns(2)
                with _bc1:
                    if st.button(t("s5.run_detect_arrow"), key="run_train2", type="primary", width='stretch'): row_to_predict=sr3
                with _bc2:
                    if len(rl) >= 2:
                        if st.button(tt("s5.batch_button", n=len(rl)), key="batch_train", width='stretch'):
                            st.session_state['batch_rows'] = rl
                            st.session_state['batch_go'] = True
                    else:
                        st.caption(tt("s5.batch_min_warn"))

        if _s5_active=="tab4":
            cbr()
            if not CV: st.markdown(f'<div class="alert-box alert-info">{t("s5.t4_info")}</div>',unsafe_allow_html=True)
            # ✨ v9.8 컴팩트: 과하게 넓던 숫자 입력을 줄이고 '목표 유형' 셀렉트에 배분. 일반 모드는 기존 비율.
            _t4_spec = [1.4, 1.4, 2.6, 0.9] if CV else [2, 2, 2, 1]
            t4c1,t4c2,t4c3,t4c4=st.columns(_t4_spec, vertical_alignment="bottom")
            with t4c1: t4_n=st.number_input(t("s4.gen_count_label"),1,100,1,step=1,key="t4_n")
            with t4c2: t4_seed=st.number_input(t("s5.seed_label"),-1,9999,-1,key="t4_seed",help=t("s5.seed_help"))
            with t4c3: syn_type4=st.selectbox(t("s5.target_type_label5"),["random"]+list("abcdefghijkl"),key="syn4_type")
            with t4c4:
                t4_run=st.button("🧪",key="run_syn",width='stretch',help=t("s5.synth_dice_help"))
            if t4_run:
                try:
                    from pipeline.data_streamer import DataStreamer
                    np.random.seed(_resolve_seed(t4_seed));ds=DataStreamer(train_path=train_path)
                    ft=None if syn_type4=="random" else syn_type4
                    rows_syn=ds.from_synthetic(n=int(t4_n),fraud_type=ft)
                    for r in rows_syn: r['_input_mode']='synthetic'
                    st.session_state['tab4_rows']=rows_syn
                    st.markdown(f'<div class="alert-box alert-ok">{t("s4.gen_success", n=len(rows_syn))}</div>',unsafe_allow_html=True)
                except Exception as e: st.markdown(f'<div class="alert-box alert-error">{t("s4.gen_fail", e=e)}</div>',unsafe_allow_html=True)
            if 'tab4_rows' in st.session_state:
                rs=st.session_state['tab4_rows']
                pcols=['Transaction_Amount','Distance','Account_balance','Channel','Operating_System']+BINARY_FLAGS[:3]
                # ✨ v14 (요청 5): 목표 사기유형을 미리보기 맨 앞 컬럼으로 노출 + 상단에 강조 표시
                _tgt = {str(r.get('_target_type','?')) for r in rs}
                _tgt_txt = ", ".join(sorted(x.upper() if x!='random' else 'RANDOM' for x in _tgt))
                st.markdown(
                    f'<div style="display:inline-block;padding:3px 11px;border-radius:999px;'
                    f'background:{T["red"] if "random" not in _tgt else T["purple"]}22;'
                    f'border:1px solid {T["red"] if "random" not in _tgt else T["purple"]};'
                    f'color:{T["red"] if "random" not in _tgt else T["purple"]};font-weight:800;'
                    f'font-size:12px;font-family:var(--font-mono);margin-bottom:5px">'
                    f'🎯 {t("s4.syn_type_label")}: {_tgt_txt}</div>', unsafe_allow_html=True)
                _pv = pd.DataFrame([{**{t("s4.th_target_type"): str(r.get('_target_type','?')).upper()},
                                     **{k:v for k,v in r.items() if not k.startswith('_') and k in pcols}}
                                    for r in rs])
                st.dataframe(_pv, width='stretch',
                             height=(min(240, 38 + 30*len(rs)) if CV else None))
                if len(rs)>1:
                    si4=st.selectbox(t("s5.row_select_label"),range(len(rs)),format_func=lambda i:t("s5.row_select_synth_fmt", i=i+1),key="t4_sel")
                    sr4=rs[si4]
                else: sr4=rs[0]
                # ✨ v5.3: 탐지 실행 | 일괄 분석 — 나란히 배치
                _bc1, _bc2 = st.columns(2)
                with _bc1:
                    if st.button(t("s5.run_detect_arrow"), key="run_syn2", type="primary", width='stretch'): row_to_predict=sr4
                with _bc2:
                    if len(rs) >= 2:
                        if st.button(tt("s5.batch_button", n=len(rs)), key="batch_syn", width='stretch'):
                            st.session_state['batch_rows'] = rs
                            st.session_state['batch_go'] = True
                    else:
                        st.caption(tt("s5.batch_min_warn"))

        if _s5_active=="tab5":
            cbr()
            if not CV: st.markdown(f'<div class="alert-box alert-info">{t("s5.t5_info")}</div>',unsafe_allow_html=True)
            folder_path=st.text_input(t("s5.folder_path_label"),"data/",key="folder_path_in")
            if st.button(t("s5.folder_scan_button"),key="run_folder"):
                _fp=Path(folder_path)
                csv_files=sorted(_fp.glob("*.csv")) if _fp.is_dir() else []
                if csv_files:
                    st.markdown(f'<div class="alert-box alert-ok">{t("s5.files_found", n=len(csv_files))}</div>',unsafe_allow_html=True)
                    for f in csv_files: st.markdown(f'<span class="feature-tag">{f.name}</span>',unsafe_allow_html=True)
                    df_first=load_test_df(str(csv_files[0]))
                    if df_first is not None:
                        row=df_first.iloc[0].to_dict();row['_input_mode']='folder';row_to_predict=row
                    else:
                        st.markdown(f'<div class="alert-box alert-error">{t("s5.csv_read_fail", name=csv_files[0].name)}</div>',unsafe_allow_html=True)
                else: st.markdown(f'<div class="alert-box alert-warn">{t("s5.no_csv_warn", path=folder_path)}</div>',unsafe_allow_html=True)

        # ── 탐지 실행 → ML 즉시 + 토글에 따라 LLM도 실행 ──
        if row_to_predict is not None:
            with st.spinner(t("s5.ml_classify_spinner")):
                try:
                    _mpath = avail_models.get(st.session_state['selected_model'], {}).get("path", str(_BASE_MODEL_PATH or "models/lgbm_fds.pkl"))
                    # ✨ v10: 값 타입 휴리스틱 → 컬럼 집합 대조 기반 단일 관문으로 교체
                    _b0 = {k: v for k, v in row_to_predict.items()
                           if not str(k).startswith('_') and k != 'Fraud_Type'}
                    clf, _clf_mode, _use_clean = _resolve_classifier(_mpath, _b0)
                    st.session_state['detect_clf_mode'] = _clf_mode
                    fraud_type,risk_score,proba_dict=clf.predict(_b0 if _use_clean else row_to_predict)
                    # NOTE: 현재 로직 — fraud_type!='m' 이면 risk_score 무관하게 이상거래 판정
                    # fraud_type=='m' 이어도 risk_score>=threshold 이면 이상거래로 판정 (높은 재현율 전략)
                    is_anomaly=fraud_type!='m' or risk_score>=threshold
                    st.session_state['det'] = {
                        'row': {k:v for k,v in row_to_predict.items()},
                        'fraud_type': fraud_type, 'risk_score': risk_score,
                        'proba_dict': proba_dict, 'is_anomaly': is_anomaly,
                        'model': st.session_state.get('selected_model','LightGBM (기본)'),
                    }
                    # 🕘 세션 내 탐지 이력 적재 (최근 50건) — 내부 키는 언어 무관(영문)으로 저장, 표시 시점에 번역
                    if is_anomaly: _play_alarm()
                    _save_detection_to_db(row_to_predict, fraud_type, risk_score, is_anomaly)
                    st.session_state.pop('batch_res', None)    # ✨ v6.2: 단건↔배치 상호 배타
                    st.session_state.pop('batch_via_bridge', None)
                    _hist = st.session_state.setdefault('det_history', [])
                    _hist.append({
                        'time': time.strftime('%H:%M:%S'),
                        'txn_id': str(row_to_predict.get('transaction_id', row_to_predict.get('ID','-')))[:24],
                        'is_anomaly': bool(is_anomaly),
                        'type': fraud_type, 'risk_score': round(float(risk_score),4),
                        'threshold': round(float(threshold), 2),
                        'input': str(row_to_predict.get('_input_mode','-')),
                        'model': str(st.session_state.get('selected_model','-')),
                    })
                    del _hist[:-50]
                except Exception as e:
                    st.session_state['det'] = {'error': str(e)}
            # 토글 ON + 이상거래 → LLM 분석도 자동 실행
            det = st.session_state.get('det', {})
            if st.session_state.get('run_with_llm', True) and det.get('is_anomaly') and 'error' not in det:
                with st.spinner(t("s5.llm_analyzing_spinner")):
                    _do_llm_analysis(det, det['row'], det['fraud_type'], det['risk_score'], rag_k, threshold)

        # ── 📦 배치 일괄 분석 실행 — v5 신설 ─────────────────
        if st.session_state.pop('batch_go', False):
            from pipeline.batch_analyzer import run_batch
            _brows = st.session_state.get('batch_rows', [])
            _pbar = st.progress(0.0, text=tt("s5.batch_spinner", i=0, n=len(_brows)))
            def _bcb(i, n): _pbar.progress(i/n, text=tt("s5.batch_spinner", i=i, n=n))
            _mpath = avail_models.get(st.session_state['selected_model'], {}).get("path", str(_BASE_MODEL_PATH or "models/lgbm_fds.pkl"))
            # 전처리 완료형(내부키 제외 전열 수치) 행이면 RowClassifier 어댑터 사용
            # 🔧 FIX(호환성): ① 라벨(Fraud_Type)이 섞이면 전열수치 판정이 항상 False → 인코딩 행이 원본용
            #   경로(브리지/MLClassifier)로 오진입하던 버그. 라벨 제외 + _input_mode 우선 판정으로 교정
            # ✨ v10: 단건과 동일한 단일 관문 사용 (판정 불일치 원천 제거)
            _b0 = {k: v for k, v in (_brows[0] or {}).items()
                   if not str(k).startswith('_') and k != 'Fraud_Type'}
            _bclf, _bclf_mode, _b_clean = _resolve_classifier(_mpath, _b0)
            st.session_state['batch_clf_mode'] = _bclf_mode
            st.caption(_bclf_mode)
            if _b_clean:   # RowClassifier는 내부키·라벨이 없는 정제 dict를 기대한다
                _brows = [{k: v for k, v in r.items()
                           if not str(k).startswith('_') and k != 'Fraud_Type'} for r in _brows]
            _banlz = _build_llm_analyzer() if st.session_state.get('run_with_llm', True) else None
            _brag  = _build_rag(rag_k) if _banlz else None
            try:
                st.session_state['batch_res'] = run_batch(
                    _brows, _bclf, threshold=threshold,
                    analyzer=_banlz, masker=_build_masker(), rag=_brag,
                    lang_suffix=_llm_lang_suffix(), lang=LANG, progress_cb=_bcb,
                )
                _save_batch_to_db(st.session_state['batch_res'])
                if st.session_state['batch_res'].anomaly_count > 0: _play_alarm()
                st.session_state.pop('det', None)              # ✨ v6.2: 배치↔단건 상호 배타
            except Exception as _be:
                alert_box(tt("s2.eval_fail", e=_be), "error")
            _pbar.empty(); st.rerun()

        _bres = st.session_state.get('batch_res')
        if _bres:
          # 컴팩트 + 단건결과 없음 → 우측 빈 공간에 렌더 (그 외에는 기존처럼 좌측 아래)
          with (_batch_slot if _batch_slot is not None else _ctxlib.nullcontext()):
            if _batch_slot is None:
                st.divider()
            section_header(tt("s5.batch_result_title"), "BATCH")
            b1,b2,b3,b4 = st.columns(4)
            with b1: kpi_card(tt("s5.batch_kpi_total"),   f"{_bres.total:,}", None, "📦", T['accent'])
            with b2: kpi_card(tt("s5.batch_kpi_anomaly"), f"{_bres.anomaly_count:,}", None, "🚨", T['red'], glow=_bres.anomaly_count>0)
            with b3: kpi_card(tt("s5.batch_kpi_avg"),     f"{_bres.avg_risk:.4f}", None, "📈", T['amber'])
            with b4: kpi_card(tt("s5.batch_kpi_max"),     f"{_bres.max_risk:.4f}", None, "🔥", T['purple'])
            alert_box(f"<b>{tt('s5.batch_summary_label')}</b> — {_bres.summary_line}", "info")
            if st.session_state.get('batch_via_bridge'):
                st.caption(t("s5.bridge_via_batch", info=st.session_state['batch_via_bridge']))
            if not _bres.llm_used:
                alert_box(tt("s5.batch_llm_fallback_note"), "warn")
            # 🐛 FIX(v14): _bres.errors(프롬프트 오버라이드 오류 등)가 지금까지 화면에 전혀
            #   노출되지 않고 조용히 버려지고 있었음 — 연결 테스트(_test_r["errors"])와 동일한
            #   스타일로 표시. 배치 프롬프트 편집기의 오타 안전복귀 여부도 이걸로 확인 가능.
            for _be in getattr(_bres, 'errors', []):
                st.markdown(f'<div style="color:{T["red"]};font-size:12px;font-family:var(--font-mono);padding:2px 0">• {_be}</div>', unsafe_allow_html=True)
            _blab = [r for r in _bres.rows_out if r.get('true_label')]
            if _blab:
                _bhit = sum(1 for r in _blab if r['fraud_type'] == r['true_label'])
                st.caption(tt("s5.batch_accuracy_note", n=len(_blab), hit=_bhit, pct=_bhit/len(_blab)*100))

            _PS = (f'max-height:{_ch(380,220)}px;overflow-y:auto;background:var(--bg-surface);'
                   'border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;'
                   'font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;line-height:1.6;'
                   'color:var(--text-secondary)')

            # ✨ v6.4: 탐지 실행과 동일한 2열 레이아웃 + 하단 탭 (스크린샷 기반)
            _bL, _bR = st.columns([3, 2])

            with _bL:
                st.markdown(f'<p style="color:{T["text_muted"]};font-size:10px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px">{t("s5.batch_panel_analysis")}</p>', unsafe_allow_html=True)
                st.markdown(f'<div style="{_PS}">{_html_esc.escape(_bres.analysis)}</div>', unsafe_allow_html=True)
                with st.expander(t("s5.batch_copy_analysis")):
                    st.code(_bres.analysis, language=None)
                _tts_player(_bres.analysis, "batch_tts")
                _bal1, _bal2 = st.columns(2)
                with _bal1:
                    st.markdown(f'<p style="color:{T["text_muted"]};font-size:10px;margin-bottom:2px">{t("s5.batch_notify_label")}</p>', unsafe_allow_html=True)
                    _bs1, _bs2 = st.columns(2)
                    with _bs1:
                        if st.button("Slack", key="batch_slack", width='stretch'):
                            _nn = _build_notifier()
                            ok = _nn.send_slack(_compose_slack_batch(_bres))
                            if ok: st.session_state.pop('last_notify_error', None)
                            elif getattr(_nn,'last_error',''): st.session_state['last_notify_error']=t("notif.slack_fail_reason", e=_nn.last_error)
                            st.toast(t("s5.slack_sent_toast") if ok else t("s5.slack_fail_toast"))
                    with _bs2:
                        if st.button(t("s5.email_btn_label"), key="batch_email", width='stretch'):  # 🐛 FIX(v7.2): 항상 False였던 dir() 가드 제거 → 정식 i18n 키 사용
                            _bto = _effective_notify_email()   # 🔧 FIX(v8.2): env 폴백 누락 보완
                            _pb,_ph,_pa = _compose_email_batch(_bres)
                            _nn = _build_notifier()
                            ok = bool(_bto) and _nn.send_email(_bto, tt("s5.batch_email_subject", n=_bres.anomaly_count), _pb, html=_ph, attachments=_pa)
                            if ok: st.session_state.pop('last_notify_error', None)
                            elif getattr(_nn,'last_error',''):
                                st.session_state['last_notify_error']=t("notif.send_fail_reason", e=_nn.last_error)
                            st.toast(t("s5.email_sent_toast") if ok else t("s5.email_fail_toast"))
                with _bal2:
                    st.markdown(f'<p style="color:{T["text_muted"]};font-size:10px;margin-bottom:2px">{t("s5.batch_regen_label")}</p>', unsafe_allow_html=True)
                    if st.button("🔄 " + tt("s5.batch_reroll"), key="batch_reroll", width='stretch'):
                        st.session_state['batch_go'] = True; st.rerun()

            with _bR:
                st.markdown(f'<p style="color:{T["text_muted"]};font-size:10px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px">{t("s5.batch_slack_label")}</p>', unsafe_allow_html=True)
                st.markdown(
                    f'<div style="max-height:200px;overflow-y:auto;background:var(--bg-surface);'
                    f'border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;'
                    f'font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;line-height:1.4;'
                    f'color:var(--text-secondary)">{_html_esc.escape(_bres.slack)}</div>', unsafe_allow_html=True)
                cbr()
                st.markdown(f'<p style="color:{T["text_muted"]};font-size:10px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px">{t("s5.batch_email_label")}</p>', unsafe_allow_html=True)
                st.markdown(
                    f'<div style="max-height:200px;overflow-y:auto;background:var(--bg-surface);'
                    f'border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;'
                    f'font-size:11px;line-height:1.4;color:var(--text-secondary);white-space:pre-wrap;'
                    f'font-family:var(--font-mono)">{_html_esc.escape(_bres.email)}</div>',  # 🛡 FIX(v9): XSS — 단건(L3107)과 동일 escape 정책
                    unsafe_allow_html=True)
                with st.expander(t("s5.batch_copy_email")):
                    st.code(_bres.email, language="html")

            # ── 하단 탭 (전체·분석·Slack·Email — 각각 다운로드/복사 가능) ──
            if st.session_state.get("_pending_batch_subtab"):     # 🤖 챗 예약 적용(위젯 생성 직전)
                st.session_state["s5_batch_subtab"] = st.session_state.pop("_pending_batch_subtab")
            _bt_active = _seg_nav("s5_batch_subtab", ["all","analysis","slack","email"],
                                  {"all": t("s5.batch_tab_all"), "analysis": t("s5.batch_tab_analysis"),
                                   "slack": "Slack", "email": "Email"}, default="all")
            if _bt_active=="all":
                st.dataframe(pd.DataFrame(_bres.rows_out).drop(columns=['idx'], errors='ignore'), width='stretch', hide_index=True)
            if _bt_active=="analysis":
                st.code(_bres.analysis, language=None)
            if _bt_active=="slack":
                st.code(_bres.slack, language=None)
            if _bt_active=="email":
                st.code(_bres.email, language="html")

            # ── 하단 액션 바 ──
            _ba1, _ba2, _ba3, _ba4, _ba5 = st.columns(5)
            with _ba1:
                if st.button(t("s5.batch_clear"), key="batch_clear"):
                    st.session_state.pop('batch_res', None); st.session_state.pop('batch_via_bridge', None); st.rerun()
            with _ba2:
                st.download_button(t("s5.batch_save_md"), _bres.analysis.encode('utf-8'),
                                   file_name="batch_report.md", mime="text/markdown", key="batch_rpt_dl")
            with _ba3:
                _bcsv = pd.DataFrame(_bres.rows_out).drop(columns=['idx'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
                st.download_button(t("s5.batch_download_csv"), _bcsv,
                                   file_name=f"batch_result_{_bres.total}rows.csv", mime="text/csv", key="batch_dl")
            with _ba4:
                st.download_button(t("s5.batch_save_pkg"), (_bres.analysis + "\n\n---SLACK---\n" + _bres.slack + "\n\n---EMAIL---\n" + _bres.email).encode('utf-8'),
                                   file_name="batch_full_package.txt", mime="text/plain", key="batch_pkg_dl")
            with _ba5:
                # ✨ 3-5: 자체완결 인터랙티브 HTML 리포트 — 이메일 경로와 동일한 다국어 L·유형집계 재사용
                try:
                    from pipeline.notify_visuals import report_html_batch
                    _rpt_risks = [r.get('risk_score', 0) for r in _bres.rows_out]
                    _rpt_html = report_html_batch(
                        _notif_L(), t("notif.report_title_batch"),
                        _bres.total, _bres.anomaly_count, _bres.avg_risk, _bres.max_risk,
                        _rpt_risks, _batch_type_counts(_bres), _bres.rows_out, _bres.analysis,
                    )
                    st.download_button(t("s5.batch_report_dl"), _rpt_html.encode('utf-8'),
                                       file_name=f"batch_report_{_bres.total}rows.html",
                                       mime="text/html", key="batch_html_rpt_dl")
                except Exception as _re:
                    st.caption(f"⚠ report: {_re}")

    # ── 저장된 탐지 결과 표시 ────────────────────────────
    det = st.session_state.get('det')
    with _s5R:
        if current_session == "05" and not det:
            # ✨ 빈 상태 안내 — 첫 사용자를 위한 다음 행동 가이드
            st.markdown(f'''<div style="border:1.5px dashed rgba({T['accent_rgb']},0.35);border-radius:14px;padding:26px 30px;margin:1.2rem 0;text-align:center;background:transparent">
                <div style="font-size:26px;margin-bottom:6px">🔍</div>
                <div style="color:{T['text_primary']};font-size:14.5px;font-weight:700;margin-bottom:4px">{t("s5.empty_title")}</div>
                <div style="color:{T['text_muted']};font-size:12.5px;line-height:1.7">{t("s5.empty_desc", accent=T['accent'])}</div>
            </div>''', unsafe_allow_html=True)
        if det and current_session == "05":
            if not CV: st.divider()
            section_header(t("s5.result_title"),"DETECTION RESULT")
            hint("beginner.s5_result")   # 🔰 초보자 설명(켤 때만)

            # ✨ v10: 어떤 전처리 경로로 예측했는지 투명하게 표시 (조용한 오예측 방지)
            if 'error' not in det and st.session_state.get('detect_clf_mode') and not CV:
                st.caption(st.session_state['detect_clf_mode'])
            # ══════════════════════════════════════════════════════
            # 📨 v18: 챗봇 발송 요청 확인 카드 (Human-in-the-loop)
            #   에이전트는 request_send()로 '요청'만 남긴다. 실제 전송은 여기서
            #   사람이 승인 버튼을 눌러야 일어난다. 발송 직전에 채널·수신자·제목·
            #   마스킹 수준을 눈으로 확인할 수 있게 미리보기를 함께 보여준다.
            # ══════════════════════════════════════════════════════
            _sreq = st.session_state.get('_send_request')
            if _sreq and 'error' not in det:
                _ch = _sreq.get('ch', 'slack')
                _want_slack = _ch in ('slack', 'both')
                _want_email = _ch in ('email', 'both')
                _to = _effective_notify_email()
                _mask_lv = st.session_state.get('pii_mask_level', 'standard')
                _tier_now = _notify_tier(det.get('risk_score', 0))
                st.markdown(
                    f'<div style="background:{T["amber"]}12;border:1px solid {T["amber"]}66;'
                    f'border-left:3px solid {T["amber"]};border-radius:10px;padding:11px 14px;'
                    f'margin:6px 0 8px">'
                    f'<div style="color:{T["amber"]};font-weight:800;font-size:12.5px;'
                    f'margin-bottom:6px">{t("s5.send_confirm_title")}</div>'
                    f'<div style="color:{T["text_secondary"]};font-size:11.5px;line-height:1.75;'
                    f'font-family:var(--font-mono)">'
                    f'{t("s5.send_confirm_ch")}: <b style="color:{T["text_primary"]}">'
                    f'{"Slack + Email" if _ch == "both" else _ch.upper()}</b><br>'
                    f'{t("s5.send_confirm_to")}: <b style="color:{T["text_primary"]}">'
                    f'{_to or t("s5.send_confirm_to_none")}</b><br>'
                    f'{t("s5.send_confirm_subj")}: '
                    f'{_tier_subject(_tier_now, det.get("fraud_type","?"), det.get("risk_score",0))}<br>'
                    f'{t("s5.send_confirm_mask")}: <b style="color:{T["accent"]}">{_mask_lv}</b>'
                    f'</div></div>', unsafe_allow_html=True)
                with st.expander(t("s5.send_confirm_preview"), expanded=False):
                    if _want_slack:
                        st.code(_compose_slack_single(det, threshold, tier=_tier_now)[:1400],
                                language="text")
                    if _want_email:
                        _pb, _ph, _pa = _compose_email_single(det, threshold, tier=_tier_now)
                        st.code(_pb[:1400], language="text")
                        st.caption(t("s5.send_confirm_att", n=len(_pa or [])))
                _kc1, _kc2 = st.columns([1, 1])
                if _kc1.button(t("s5.send_confirm_go"), type="primary",
                               key="sreq_go", width='stretch'):
                    _nn = _build_notifier()
                    _ok_all, _msgs = True, []
                    if _want_slack:
                        _ok = _nn.send_slack(_compose_slack_single(det, threshold, tier=_tier_now))
                        _ok_all &= _ok
                        _msgs.append(("Slack", _ok, _nn.last_error))
                    if _want_email:
                        if not _to:
                            _ok_all = False
                            _msgs.append(("Email", False, t("s5.send_confirm_to_none")))
                        else:
                            _pb, _ph, _pa = _compose_email_single(det, threshold, tier=_tier_now)
                            _ok = _nn.send_email(
                                _to, _tier_subject(_tier_now, det.get("fraud_type","?"),
                                                   det.get("risk_score",0)),
                                _pb, html=_ph, attachments=_pa)
                            _ok_all &= _ok
                            _msgs.append(("Email", _ok, _nn.last_error))
                    st.session_state.pop('_send_request', None)
                    for _nm, _ok, _err in _msgs:
                        alert_box(f"{'✅' if _ok else '❌'} {_nm} — "
                                  f"{t('s5.send_confirm_sent') if _ok else _err}",
                                  "ok" if _ok else "error")
                    if _ok_all:
                        st.toast(t("s5.send_confirm_sent"))
                if _kc2.button(t("s5.send_confirm_cancel"), key="sreq_no", width='stretch'):
                    st.session_state.pop('_send_request', None)
                    st.rerun()

            # ══════════════════════════════════════════════════════
            # 📋 v16: 규칙 체크리스트 — 모델 판정의 '근거'를 사람 말로 표시
            #   ⚠️ 사기/정상 판정은 하지 않는다. 정상 거래도 같은 특징을 흔히 갖기 때문
            #   (수취정지 49% · 미사용계좌 51% · 고액입금 42%) — 규칙만으로 판정하면 정밀도 0.3%.
            #   여기서는 "사기라고 할 때 어느 유형 특징에 맞는가"만 보여준다.
            # ══════════════════════════════════════════════════════
            if 'error' not in det:
                try:
                    from pipeline.rule_checker import RuleChecker
                    _rc = RuleChecker(LANG)
                    _rr = _rc.report(det['row'], det['fraud_type'])
                    if _rr.get("known") and _rr["n_total"]:
                        with (csec(t("s5.rule_title"), "RULES") if CV
                              else st.expander(t("s5.rule_title"), expanded=True)):
                            st.caption(t("s5.rule_disclaimer"))
                            _pct = _rr["n_hit"] / max(_rr["n_total"], 1)
                            _col = T['red'] if _pct >= 0.7 else (T['amber'] if _pct >= 0.4 else T['text_muted'])
                            _idx_txt = t("s5.rule_score", idx=f'{_rr["index"]:.2f}')
                            _hit_txt = f'{_rr["n_hit"]}/{_rr["n_total"]}'
                            st.markdown(
                                '<div style="display:flex;align-items:baseline;gap:9px;margin-bottom:6px">'
                                f'<span style="font-family:var(--font-mono);font-size:19px;font-weight:800;'
                                f'color:{_col}">{_hit_txt}</span>'
                                f'<span style="color:{T["text_secondary"]};font-size:12px">{_idx_txt}</span>'
                                f'<span style="color:{T["text_muted"]};font-size:11px">{_rr["title"]}</span>'
                                '</div>', unsafe_allow_html=True)
                            for _h in _rr["hits"]:
                                st.markdown(
                                    f'<div style="font-size:11.5px;line-height:1.6;margin:1px 0">'
                                    f'<span style="color:{T["red"]};font-weight:700">✅</span> '
                                    f'<span style="color:{T["text_primary"]}">{_h["label"]}</span> '
                                    f'<span style="color:{T["accent"]};font-family:var(--font-mono);'
                                    f'font-size:10.5px">→ {_h.get("evidence","")}</span></div>',
                                    unsafe_allow_html=True)
                            for _mi in _rr["misses"]:
                                st.markdown(
                                    f'<div style="font-size:11px;line-height:1.55;margin:1px 0;'
                                    f'color:{T["text_muted"]}">⬜ {_mi["label"]}</div>',
                                    unsafe_allow_html=True)
                            if _rr["unknowns"]:
                                st.caption("❔ " + ", ".join(u["label"] for u in _rr["unknowns"][:3]))
                            # 모델↔규칙 불일치 → 수동 검토 신호 (실측에서 모델 오분류를 잡아낸 경로)
                            if _rr.get("best_rule_type") and _rr.get("agreement") is False \
                                    and _rr.get("gap", 1.0) >= 1.3:
                                alert_box(t("s5.rule_mismatch",
                                            tp=str(_rr["best_rule_type"]).upper(),
                                            a=f"{_rr['best_rule_index']:.2f}",
                                            b=f"{_rr['index']:.2f}",
                                            g=f"{_rr['gap']:.1f}"), "warn")
                            _rank = ", ".join(f"{c.upper()} {v:.2f}" for c, v in _rr.get("ranking", [])[:4])
                            if _rank:
                                st.caption(t("s5.rule_ranking", r=_rank))
                except Exception as _rce:
                    log.debug(f"규칙 체크리스트 생략: {_rce}")

            if 'error' in det:
                alert_box(t("s5.model_error", e=det['error']), "error")
            else:
              try:
                row_data=det['row'];fraud_type=det['fraud_type'];risk_score=det['risk_score']
                proba_dict=det['proba_dict'];is_anomaly=det['is_anomaly']
                panel_cls="anomaly" if is_anomaly else "normal"
                verdict=t("s5.verdict_anomaly") if is_anomaly else t("s5.verdict_normal")
                true_lbl=row_data.get('_true_label','')
                true_html=f'<span class="badge-warn">{FRAUD_SHORT.get(true_lbl,true_lbl or "—")}</span>' if true_lbl else '—'

                # 자동발송 결과 뱃지 (토글은 상단 설정에서 이미 선택됨)
                _notify_badges = ""
                # ✨ v9.1: 이중 임계값 발송 등급 뱃지
                _tn = det.get('notify_tier')
                if _tn == 'review':   _notify_badges += f'<span class="badge-warn" style="margin-right:6px">{tt("s5.notify_tier_review")}</span>'
                elif _tn == 'confirm':_notify_badges += f'<span class="badge-danger" style="margin-right:6px">{tt("s5.notify_tier_confirm")}</span>'
                elif _tn == 'none':   _notify_badges += f'<span class="badge-safe" style="margin-right:6px">{tt("s5.notify_tier_none")}</span>'
                if det.get('auto_slack_sent') is True: _notify_badges += f'<span class="badge-safe" style="margin-right:6px">{t("s5.notify_slack_sent")}</span>'
                elif det.get('auto_slack_sent') is False: _notify_badges += f'<span class="badge-danger" style="margin-right:6px">{t("s5.notify_slack_fail")}</span>'
                if det.get('auto_email_sent') is True: _notify_badges += f'<span class="badge-safe" style="margin-right:6px">{t("s5.notify_email_sent")}</span>'
                elif det.get('auto_email_sent') is False: _notify_badges += f'<span class="badge-danger" style="margin-right:6px">{t("s5.notify_email_fail")}</span>'
                # 🔧 FIX(v8.1): 자동 발송 실패 사유를 화면에 노출 — 로그 접근 불가 환경 대응
                for _nk, _nkey in (("notify_error_slack", "notif.slack_fail_reason"), ("notify_error_email", "notif.send_fail_reason")):
                    if det.get(_nk):
                        _notify_badges += f'<div style="color:var(--red);font-size:11px;margin-top:4px">{t(_nkey, e=det[_nk])}</div>'
                if _notify_badges:
                    st.markdown(_notify_badges, unsafe_allow_html=True)

                # ✨ v7: 판정 히어로 배너 — 판정·위험점수·예측유형·모델 메타를 최상단 풀폭으로
                _vh_cls = "anomaly" if is_anomaly else "normal"
                _vh_c = T['red'] if is_anomaly else T['green']
                _vh_icon = "🚨" if is_anomaly else "🛡️"
                _vh_badge = ('<span class="badge-danger">' if is_anomaly else '<span class="badge-safe">') + FRAUD_SHORT.get(fraud_type, fraud_type) + '</span>'
                _vh_html = (
                    f'<div class="verdict-hero {_vh_cls}">'
                    f'<div style="display:flex;align-items:center;gap:14px">'
                    f'<div class="vh-icon">{_vh_icon}</div>'
                    f'<div><div class="vh-title" style="color:{_vh_c}">{verdict}</div>'
                    f'<div class="vh-meta">{t("s5.model_line", m=det.get("model","—"))} · {t("s5.threshold_line")} {threshold:.2f}</div></div>'
                    f'</div>'
                    f'<div><div class="vh-score" style="color:{_vh_c}">{risk_score:.3f}'
                    f'<span style="font-size:12px;color:{T["text_muted"]};font-weight:400"> / 1.0</span></div>'
                    f'<div style="text-align:right;margin-top:7px">{_vh_badge}</div></div>'
                    f'</div>')
                st.markdown(_vh_html, unsafe_allow_html=True)

                cg,cm_col=st.columns([1,2])
                with cg:
                    st.markdown(f'<div class="result-panel {panel_cls}">',unsafe_allow_html=True)
                    risk_gauge(risk_score)
                    # ✨ v7: 판정 텍스트는 상단 히어로 배너로 승격 → 여기선 임계값 정보만 (중복 제거)
                    st.markdown(f'<div style="text-align:center;margin-top:10px"><div style="color:{T["text_muted"]};font-size:12px">{t("s5.threshold_line")} <span style="font-family:JetBrains Mono;color:{T["text_secondary"]}">{threshold:.2f}</span></div></div></div>',unsafe_allow_html=True)
                with cm_col:
                    st.markdown('<div class="result-panel">',unsafe_allow_html=True)
                    bd='<span class="badge-danger">' if is_anomaly else '<span class="badge-safe">'
                    flags_html=''.join(f'<span class="feature-tag danger">{FLAG_LABELS.get(f,f)}</span>' for f in BINARY_FLAGS if str(row_data.get(f,'0')) in ['1','1.0','True']) or f'<span class="feature-tag safe">{t("common.none")}</span>'
                    st.markdown(f'<table style="width:100%;border-collapse:collapse"><tr><td style="padding:8px 0;color:{T["text_muted"]};font-size:11px;width:35%">{t("s5.th_pred_type")}</td><td style="padding:8px 0;font-weight:700;color:{T["text_primary"]}">{bd}{FRAUD_SHORT.get(fraud_type,fraud_type)}</span></td></tr><tr><td style="padding:8px 0;color:{T["text_muted"]};font-size:11px">{t("s5.th_true_answer")}</td><td style="padding:8px 0">{true_html}</td></tr><tr><td style="padding:8px 0;color:{T["text_muted"]};font-size:11px">{t("s5.th_input_mode")}</td><td style="padding:8px 0;font-family:JetBrains Mono;font-size:12px;color:{T["text_secondary"]}">{row_data.get("_input_mode","—")}</td></tr><tr><td style="padding:8px 0;color:{T["text_muted"]};font-size:11px">{t("s5.th_risk_features")}</td><td style="padding:8px 0">{flags_html}</td></tr></table></div>',unsafe_allow_html=True)

                if is_anomaly and fraud_type in FRAUD_TYPE_DETAILS:
                    cbr()
                    section_header(t("s5.fraud_info_title"),"FRAUD TYPE INFO")
                    fraud_type_popup(fraud_type)

                cbr()
                section_header(t("s5.prob_title"),"PROBABILITY")
                hint("beginner.s5_prob")   # 🔰 초보자 설명(켤 때만)
                cp,cc=st.columns([1,2])
                with cp: prob_bars(proba_dict,threshold)
                with cc:
                    pi=sorted(proba_dict.items(),key=lambda x:x[1],reverse=True)
                    labels=[FRAUD_SHORT.get(k,k) for k,v in pi];values=[v for k,v in pi]
                    cl=[T['red'] if k!='m' and i==0 else T['accent'] if k=='m' else T['text_muted'] for i,(k,v) in enumerate(pi)]
                    fp=go.Figure(go.Bar(x=labels,y=values,marker_color=cl,marker_line_width=0,
                        text=[f"{v*100:.1f}%" for v in values],textposition="outside",cliponaxis=False,
                        textfont=dict(size=8.5,color=T['text_secondary'],family='JetBrains Mono, monospace')))  # ✨ v7: 값 라벨
                    fp.update_layout(**PLOTLY_LAYOUT,margin=_M_COMPACT,height=_ch(210,150))
                    fp.update_xaxes(tickfont=dict(size=9),gridcolor=GRID_COLOR)
                    fp.update_yaxes(tickformat='.2%',gridcolor=GRID_COLOR)
                    st.plotly_chart(fp,width='stretch')

                # ── LLM 분석 결과 ────────────────────────────
                # 🐛 FIX: 기존엔 is_anomaly일 때만 이 섹션이 렌더링돼서, 정상 판정이 나오면
                #        'AI 분석 포함' 토글이 ON이어도 섹션 자체가 사라져 "비활성화"처럼 보였음.
                #        (자동 실행 조건도 is_anomaly 한정이라 정상 거래는 AI 분석이 안 돎)
                #        → 섹션은 항상 표시하고, 정상 판정 시엔 안내 + 수동 실행 버튼 제공.
                # ✨ v9.7: 컴팩트 = AI 원인 분석·조치 해석을 '왼쪽 하단 컨테이너'로 이동
                #   (탐지 버튼 아래 빈 공간 활용 → 오른쪽 결과 컬럼 스크롤 완화). 일반 = 현 위치(오른쪽) 유지.
                #   컬럼 컨테이너는 나중에 다시 채울 수 있어, 코드가 _s5R 안에 있어도 _s5L로 출력을 돌린다.
                _llm_ctx = _s5L if CV else _ctxlib.nullcontext()
                with _llm_ctx:
                    # ✨ 컴팩트에서도 '입력 방식 선택' 탭과 'AI 원인 분석·조치 해석'을
                    #   시각적으로 분리하기 위해 구분선을 항상 그린다(기존: 일반 모드 한정).
                    st.divider()
                    section_header(t("s5.llm_section_title"),"LLM ANALYSIS")
                    llm_result=det.get('llm');llm_error=det.get('llm_error')

                    if not is_anomaly and not llm_result and not llm_error:
                        alert_box(t("s5.llm_auto_skip_info"), "info")

                    # LLM 결과가 아직 없을 때 — 큰 분석 시작 버튼
                    if not llm_result and not llm_error:
                        ac1, ac2 = st.columns([2, 4])
                        with ac1:
                            if st.button(t("s5.llm_start_button"), key="run_llm_main", type="primary", width='stretch'):
                                _run_llm = True
                            else:
                                _run_llm = False
                        with ac2:
                            _prov = st.session_state.get('llm_p5','local')
                            st.markdown(f'<div style="color:{T["text_muted"]};font-size:12px;padding-top:8px">{t("s5.llm_provider_desc", p=_prov)}</div>', unsafe_allow_html=True)
                        if _run_llm:
                            _do_llm_analysis(det, row_data, fraud_type, risk_score, rag_k, threshold)
                            st.rerun()

                    if llm_error:
                        st.markdown(f'<div class="alert-box alert-warn">{t("s5.llm_fail", e=llm_error)}</div>',unsafe_allow_html=True)
                        if st.button(t("s5.retry_button"), key="retry_llm_err"):
                            det.pop('llm_error', None)
                            _do_llm_analysis(det, row_data, fraud_type, risk_score, rag_k, threshold)
                            st.rerun()

                    if llm_result:
                        # ── 진단 정보 표시 (메인 렌더링에서 안전하게) ──
                        _diag = det.get('_llm_diag', llm_result.get('_diag', {}))
                        if _diag.get('is_all_fallback') and not CV:
                            _err_lines = '\n'.join(f'  • {e}' for e in _diag.get('errors', []))
                            st.warning(
                                f"{t('s5.fallback_all_title')}\n\n"
                                f"{t('s5.fallback_provider', p=_diag.get('provider', '?'))}\n\n"
                                f"{t('s5.fallback_error_log')}\n{_err_lines or '  ' + t('s5.fallback_no_error')}"
                            )
                        elif _diag.get('fallback_fields') and not CV:
                            _fb = ', '.join(_diag['fallback_fields'])
                            _step_errs = _diag.get('step_errors', {})
                            _detail_parts = []
                            for _field in _diag['fallback_fields']:
                                _field_errs = _step_errs.get(_field, [])
                                if _field_errs:
                                    _detail_parts.append(f"**[{_field}]**\n" + '\n'.join(f'  • {e}' for e in _field_errs))
                                else:
                                    _detail_parts.append(t("s5.fallback_empty_no_error", field=_field))
                            st.warning(
                                f"{t('s5.fallback_partial_title', fb=_fb)}\n\n"
                                f"{t('s5.fallback_provider', p=_diag.get('provider', '?'))}\n\n"
                                + '\n\n'.join(_detail_parts)
                            )

                        ca,cb=st.columns(2)
                        with ca:
                            _analysis_text = llm_result.get("analysis",t("s5.no_analysis"))
                            st.markdown('<div class="alert-box alert-warn">',unsafe_allow_html=True)
                            st.markdown(f'**{t("s5.analysis_result_title")}**\n\n{_analysis_text}')
                            st.markdown('</div>',unsafe_allow_html=True)
                            with st.expander(t("s5.analysis_raw_expander"), expanded=False):
                                st.code(_analysis_text, language="markdown")
                            _tts_player(_analysis_text, "det_tts")
                        with cb:
                            _slack_text = llm_result.get("slack","")
                            st.markdown(f'**{t("s5.slack_title")}**')
                            st.code(_slack_text, language=None)

                            _email_text = llm_result.get("email","")
                            st.markdown(f'**{t("s5.email_title")}**')
                            # 전체 내용을 스크롤 가능한 영역으로 표시
                            st.markdown(
                                f'<div style="max-height:{_ch(400,200)}px;overflow-y:auto;background:var(--bg-surface);'
                                f'border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;'
                                f'font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);'
                                f'white-space:pre-wrap;line-height:1.6">{_html_esc.escape(_email_text)}</div>',  # 🐛 FIX(v5): XSS 방지
                                unsafe_allow_html=True
                            )
                            with st.expander(t("s5.email_raw_expander"), expanded=False):
                                st.code(_email_text, language=None)
                        # ── 액션 툴바: 발송/재생성 그룹으로 정렬 (기존 3×3 산개 개선) ──
                        st.markdown('<div style="height:1px;background:var(--border);margin:18px 0 12px"></div>', unsafe_allow_html=True)
                        tb_send, tb_redo = st.columns([2, 4], gap="large")
                        with tb_send:
                            st.markdown(f'<div style="color:{T["text_muted"]};font-size:10.5px;font-weight:700;letter-spacing:0.05em;margin-bottom:6px">{t("s5.send_toolbar_title")}</div>', unsafe_allow_html=True)
                            sb1, sb2 = st.columns(2)
                            with sb1:
                                if st.button(t("s5.send_slack_button"), key="manual_slack", width='stretch', help=t("s5.send_slack_help")):
                                    try:
                                        _mt=_notify_tier(det.get('risk_score', 0))   # ✨ v9.1: 수동 발송도 등급 톤 반영
                                        _nn=_build_notifier()
                                        ok=_nn.send_slack(_compose_slack_single(det, threshold, tier=_mt))
                                        if ok: st.session_state.pop('last_notify_error', None)
                                        elif getattr(_nn,'last_error',''):
                                            st.session_state['last_notify_error']=t("notif.slack_fail_reason", e=_nn.last_error)
                                        st.toast(t("s5.slack_sent_toast") if ok else t("s5.slack_fail_toast"))
                                    except Exception as e: st.toast(f"❌ {e}")
                            with sb2:
                                if st.button(t("s5.send_email_button"), key="manual_email", width='stretch', help=t("s5.send_email_help")):
                                    try:
                                        _mt=_notify_tier(det.get('risk_score', 0))   # ✨ v9.1
                                        _to=_effective_notify_email()   # 🔧 FIX(v8.2)
                                        _pb,_ph,_pa=_compose_email_single(det, threshold, tier=_mt)
                                        _nn=_build_notifier()
                                        ok=_nn.send_email(_to,_tier_subject(_mt, fraud_type, det.get('risk_score', 0)),_pb,html=_ph,attachments=_pa)
                                        if ok: st.session_state.pop('last_notify_error', None)
                                        elif getattr(_nn,'last_error',''):
                                            st.session_state['last_notify_error']=t("notif.send_fail_reason", e=_nn.last_error)
                                        st.toast(t("s5.email_sent_toast") if ok else t("s5.email_fail_toast"))
                                    except Exception as e: st.toast(f"❌ {e}")
                        with tb_redo:
                            st.markdown(f'<div style="color:{T["text_muted"]};font-size:10.5px;font-weight:700;letter-spacing:0.05em;margin-bottom:6px">{t("s5.redo_toolbar_title")}</div>', unsafe_allow_html=True)
                            rb0, rb1, rb2, rb3 = st.columns(4)
                            with rb0:
                                if st.button(t("s5.redo_all_button"), key="reroll_llm", type="primary", width='stretch', help=t("s5.redo_all_help")):
                                    with st.spinner(t("s5.redo_all_spinner")):
                                        _do_llm_analysis(det, row_data, fraud_type, risk_score, rag_k, threshold)
                                    st.rerun()
                            with rb1:
                                if st.button(t("s5.redo_analysis_button"), key="redo_analysis", width='stretch', help=t("s5.redo_analysis_help")):
                                    with st.spinner(t("s5.redo_analysis_spinner")):
                                        _redo_llm_step(det, row_data, fraud_type, risk_score, rag_k, "analysis")
                                    st.rerun()
                            with rb2:
                                if st.button("Slack", key="redo_slack", width='stretch', help=t("s5.redo_slack_help")):
                                    with st.spinner(t("s5.redo_slack_spinner")):
                                        _redo_llm_step(det, row_data, fraud_type, risk_score, rag_k, "slack")
                                    st.rerun()
                            with rb3:
                                if st.button("Email", key="redo_email", width='stretch', help=t("s5.redo_email_help")):
                                    with st.spinner(t("s5.redo_email_spinner")):
                                        _redo_llm_step(det, row_data, fraud_type, risk_score, rag_k, "email")
                                    st.rerun()

                # 결과 초기화 + 보고서 다운로드 + 데이터 보기
                rc1,rc_dl,rc2=st.columns([1,1.3,3.7])
                with rc1:
                    if st.button(t("s5.clear_result_button"),key="clear_det"):
                        st.session_state.pop('det',None);st.rerun()
                with rc_dl:
                    _llm_r = det.get('llm') or {}
                    if _llm_r.get('analysis'):
                        _rpt = (f"# FDS Detection Report\n\n"
                                f"- {t('s5.report_generated_at')}: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"- {t('s5.h_verdict')}: {t('s5.verdict_anomaly') if det.get('is_anomaly') else t('s5.verdict_normal')}\n"
                                f"- {t('s5.th_pred_type')}: {det.get('fraud_type','-')} ({FRAUD_LABELS.get(det.get('fraud_type',''),'-')})\n"
                                f"- {t('s5.h_risk_score')}: {det.get('risk_score',0):.4f}\n"
                                f"- {t('s5.h_model')}: {det.get('model','-')}\n\n"
                                f"## {t('s5.llm_section_title')}\n\n{_llm_r.get('analysis','')}\n\n"
                                f"## {t('s5.slack_title')}\n\n```\n{_llm_r.get('slack','')}\n```\n\n"
                                f"## {t('s5.email_title')}\n\n```\n{_llm_r.get('email','')}\n```\n")
                        st.download_button(t("s5.report_download_button"), _rpt.encode('utf-8'),
                                           file_name=f"fds_report_{det.get('fraud_type','x')}_{time.strftime('%H%M%S')}.md",
                                           mime="text/markdown", key="dl_report", width='stretch')
                with rc2:
                    _raw_data = {k:v for k,v in row_data.items() if not k.startswith('_')}
                    vc1, vc2 = st.columns(2)
                    with vc1:
                        with st.expander(t("s5.raw_data_expander")):
                            st.json(_raw_data)
                    with vc2:
                        with st.expander(t("s5.masked_preview_expander")):
                            _preview_masker = _build_masker_forced()
                            _masked_preview = _preview_masker.mask_row(_raw_data)
                            _log = _preview_masker.get_log()
                            if _log:
                                st.markdown(f'<div style="color:{T["amber"]};font-size:11px;margin-bottom:8px">{t("s5.masking_applied", fields=", ".join(_log))}</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div style="color:{T["text_muted"]};font-size:11px;margin-bottom:8px">{t("s5.masking_off_note")}</div>', unsafe_allow_html=True)
                            st.json(_masked_preview)
              except Exception as _render_err:
                alert_box(t("s5.render_error", e=_render_err), "error")
                with st.expander(t("s5.render_error_expander"), expanded=False):
                    st.code(traceback.format_exc(), language="python")

    # ── 🕘 탐지 이력 (이번 세션) — 반복 테스트 시 판정 비교용 ──
    if current_session == "05" and st.session_state.get('det_history'):
        with st.expander(t("s5.history_expander", n=len(st.session_state['det_history'])), expanded=False):
            _hraw = pd.DataFrame(st.session_state['det_history'][::-1])
            # ⚖️ 현재 임계값 기준 판정 재계산 미리보기 (유형≠m 이거나 점수≥임계값 → 이상)
            _cur_verdict_bool = _hraw.apply(lambda r: (str(r.get('type','m'))!='m' or float(r.get('risk_score',0))>=threshold), axis=1)
            _changed_bool = (_cur_verdict_bool != _hraw.get('is_anomaly', False))
            _n_flip2 = int(_changed_bool.sum())
            _n_anom2 = int(_cur_verdict_bool.sum())
            _V_ANOM,_V_NORM = t("hist.verdict_anomaly"), t("hist.verdict_normal")
            _hdf = pd.DataFrame({
                t("s5.h_time"): _hraw.get('time',''),
                t("s5.h_txn_id"): _hraw.get('txn_id',''),
                t("s5.h_verdict"): _hraw.get('is_anomaly',False).map({True:_V_ANOM, False:_V_NORM}),
                t("s5.h_current_verdict"): _cur_verdict_bool.map({True:_V_ANOM, False:_V_NORM}),
                t("s5.h_change"): _changed_bool.map({True:'⚠️', False:''}),
                t("s5.h_type"): _hraw.get('type',''),
                t("s5.h_risk_score"): _hraw.get('risk_score',0),
                t("s5.h_threshold"): _hraw.get('threshold',0),
                t("s5.h_input"): _hraw.get('input',''),
                t("s5.h_model"): _hraw.get('model',''),
            })
            _fc = T['amber'] if _n_flip2 else T['text_muted']
            st.markdown(f'<div style="font-size:12px;color:{T["text_secondary"]};margin-bottom:6px">{t("s5.history_recalc_note", th=f"{threshold:.2f}", anom=_n_anom2, normal=len(_hdf)-_n_anom2, flip=_n_flip2, accent=T["accent"], red=T["red"], green=T["green"], fc=_fc, muted=T["text_muted"])}</div>', unsafe_allow_html=True)
            st.dataframe(_hdf, width='stretch', height=min(320, 42+35*len(_hdf)), hide_index=True)
            hc1, hc2, _ = st.columns([1.2, 1.2, 4])
            with hc1:
                st.download_button(t("s5.history_csv_button"), _hdf.to_csv(index=False).encode('utf-8-sig'),
                                   file_name=f"fds_history_{time.strftime('%H%M%S')}.csv",
                                   mime="text/csv", key="dl_hist", width='stretch')
            with hc2:
                if st.button(t("s5.history_clear_button"), key="clear_hist", width='stretch'):
                    st.session_state.pop('det_history', None); st.rerun()

    # ── 🗃 v8: 영구 탐지 이력 뷰어 — _save_detection_to_db가 '쓰기만' 하던 sqlite를 드디어 조회 ──
    if current_session == "05":
        _dbp = Path("fds_results.db")
        _dbn, _dbanom = 0, 0
        if _dbp.exists():
            try:
                import sqlite3
                _con = sqlite3.connect(str(_dbp))
                _dbn, _dbanom = _con.execute("SELECT COUNT(*), COALESCE(SUM(is_anomaly),0) FROM detections").fetchone()
                _con.close()
            except Exception as _dbe0:
                log.warning(f"DB 카운트 실패: {_dbe0}")
        with st.expander(t("db.expander", n=_dbn), expanded=False):
            if _dbn == 0:
                st.caption(t("db.empty"))
            else:
                try:
                    import sqlite3
                    _con = sqlite3.connect(str(_dbp))
                    _dbdf = pd.read_sql_query(
                        "SELECT detected_at, transaction_id, fraud_type, risk_score, is_anomaly, model, threshold "
                        "FROM detections ORDER BY detected_at DESC LIMIT 500", _con)
                    _con.close()
                    st.caption(t("db.kpi", n=_dbn, anom=int(_dbanom), pct=_dbanom / max(_dbn, 1) * 100,
                                 last=str(_dbdf['detected_at'].iloc[0])))
                    _dbdf['is_anomaly'] = _dbdf['is_anomaly'].map({1: '🚨', 0: '✅'})
                    st.dataframe(_dbdf, width='stretch', height=min(320, 42 + 35 * len(_dbdf)), hide_index=True)
                    _dbc1, _dbc2, _ = st.columns([1.2, 1.2, 4])
                    with _dbc1:
                        st.download_button(t("db.csv"), _dbdf.to_csv(index=False).encode('utf-8-sig'),
                                           file_name=f"fds_db_history_{time.strftime('%H%M%S')}.csv",
                                           mime="text/csv", key="dl_dbhist", width='stretch')
                    with _dbc2:
                        if st.button(t("db.clear"), key="clear_dbhist", width='stretch'):
                            _con = sqlite3.connect(str(_dbp)); _con.execute("DELETE FROM detections"); _con.commit(); _con.close()
                            st.toast(t("db.cleared")); st.rerun()
                except Exception as _dbe:
                    alert_box(t("db.read_fail", e=_dbe), "error")


# ══════════════════════════════════════════════════════════
# ✨ v6 FINAL: Footer
# ══════════════════════════════════════════════════════════
cbr()
st.markdown(f'''<div class="fds-footer"><div class="f-line">
<span style="font-weight:700;color:var(--text-secondary)">FDS 이상거래탐지 QA 대시보드</span>
<span class="f-chip">v7</span><span class="f-dot"></span>
<span>Built with Streamlit</span><span class="f-dot"></span>
<span>{t("s1.kpi_period_val")}</span>
</div></div>''', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 🤖 AI 챗 (사이드바 도킹, 읽기 전용 v1)
#   스크립트 말미에서 렌더 → 사이드바 '하단'에 위치. 토글 끄면 아무것도 안 그림(컴팩트).
#   analyzer·masker·PII 락은 세션5 설정(_build_llm_analyzer/_build_masker)을 그대로 재사용.
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.divider()
    # 🐛 FIX(v12): compact_view/beginner_mode와 같은 원인의 버그 — 세션이동·단축키 히든버튼이
    #   이 위젯보다 앞줄에서 st.rerun()으로 실행을 끊으면 위젯이 안 그려지고, 위젯 key(chat_open)
    #   상태를 Streamlit이 폐기해 챗봇이 꺼졌다. compact_view와 동일하게 일반 상태 키로 분리하고
    #   토글 key를 상태값과 조합(chat_open_toggle_{상태})해 어떤 rerun에도 값이 보존되게 한다.
    _prev_chat_on = bool(st.session_state.get('chat_open', False))
    _chat_on = st.toggle(t("chat.toggle"), value=_prev_chat_on,
                         key=f"chat_open_toggle_{_prev_chat_on}", help=t("chat.help"))
    if _chat_on != _prev_chat_on:
        st.session_state['chat_open'] = _chat_on
        st.rerun()
    if _chat_on:
        _prov = st.session_state.get('llm_p5', 'local')
        _masked = not (st.session_state.get('pii_skip_local', True) and _prov == 'local')
        st.caption(t("chat.status", prov=_prov,
                     pii=(t("chat.pii_masked") if _masked else t("chat.pii_local"))))
        st.caption(tt("chat.hotkey_hint"))   # ⌨ v12: 챗봇 바로가기 단축키(C) 안내
        # ⚙️ 프롬프트 라이브 편집 (기본값 덮어쓰기 · 재시작 불필요)
        with st.expander(t("chat.sys_editor"), expanded=False):
            from pipeline.chat_agent import default_system as _def_sys
            _cur_sys = st.session_state.get("chat_system_override") or _def_sys(LANG)
            # 🐛 FIX(v12): key가 없어 리런(질문 전송·액션 적용)마다 편집 내용이 날아갔다.
            #   key를 주면 위젯 상태가 유지되므로, value=는 최초 시딩에만 사용한다.
            if "chat_sys_ta" not in st.session_state:
                st.session_state["chat_sys_ta"] = _cur_sys
            _edited_sys = st.text_area(t("chat.sys_editor"), height=160, key="chat_sys_ta",
                                       label_visibility="collapsed", help=t("chat.sys_editor_help"))
            _sc1, _sc2 = st.columns(2)
            if _sc1.button(t("chat.sys_save"), key="chat_sys_save", width='stretch'):
                st.session_state["chat_system_override"] = (_edited_sys or "").strip()
                st.rerun()
            if _sc2.button(t("chat.sys_reset"), key="chat_sys_reset", width='stretch'):
                st.session_state.pop("chat_system_override", None)
                st.session_state.pop("chat_sys_ta", None)     # 🐛 FIX(v12): 위젯 값도 기본값으로 복원
                st.rerun()
            if st.session_state.get("chat_system_override"):
                st.caption(t("chat.sys_active"))
        # ✨ v12: 채팅 전송 로직을 함수로 공유 — chat_input 제출과 아래 퀵프롬프트 버튼이 동일 코드 사용
        #   (chat_input엔 값을 미리 채워넣는 API가 없어, 퀵프롬프트는 입력창을 거치지 않고 바로 전송)
        def _run_chat_query(q: str):
            _hist_now = st.session_state.get("chat_history", [])
            try:
                from pipeline.chat_agent import ChatAgent
                _agent = ChatAgent(_build_llm_analyzer(), lang=LANG,
                                   system_override=st.session_state.get("chat_system_override"))
                with st.spinner(t("chat.thinking")):
                    _ans, _acts = _agent.answer(_hist_now, q, _chat_context(threshold))
                _notes = _apply_chat_actions(_acts)          # 화이트리스트 액션 실제 반영
                if _notes:
                    _ans = (_ans + "\n\n" + "\n".join("🔧 " + _nt for _nt in _notes)).strip()
            except Exception as _ce:
                _ans = f"⚠ {type(_ce).__name__}: {_ce}"
            st.session_state["chat_history"] = _hist_now + [
                {"role": "user", "content": q},
                {"role": "assistant", "content": _ans},
            ]

        _hist = st.session_state.get("chat_history", [])
        if not _hist:
            st.caption(t("chat.empty"))
        for _cm in _hist:
            with st.chat_message("user" if _cm.get("role") == "user" else "assistant"):
                st.markdown(_cm.get("content", ""))
        # ✨ v12: 퀵프롬프트 — 채팅창(입력창) 바로 위에 예시 질문 버튼. 누르면 바로 전송.
        st.caption(tt("chat.quick_title"))
        _qp_cols = st.columns(2)
        for _qi, _qp in enumerate([tt("chat.quick1"), tt("chat.quick2"), tt("chat.quick3"), tt("chat.quick4")]):
            with _qp_cols[_qi % 2]:
                if st.button(_qp, key=f"chat_quick_{_qi}", width='stretch'):
                    _run_chat_query(_qp)
                    st.rerun()
        # ══════════════════════════════════════════════════════
        # 🎤 v14: 음성 입력 — 녹음 + 오디오 파일 업로드 (요청 1·2)
        #   🐛 FIX(v14): 백엔드(faster-whisper / OPENAI_API_KEY)가 하나도 없어도
        #     녹음 위젯을 그대로 렌더해, 사용자가 3초 녹음한 뒤에야 실패했다.
        #     (스크린샷의 "An error has occurred, please try again."는 브라우저/위젯 단계 오류지만,
        #      애초에 인식할 수단이 없는 상태에서 녹음을 권하는 UI 자체가 문제였다)
        #     → 백엔드가 없으면 녹음기를 렌더하지 않고 설치 안내를 먼저 보여준다.
        #   ✨ v14: 마이크를 못 쓰는 환경(권한 거부·장치 없음·HTTPS 아님)을 위해
        #     오디오 파일 업로드 경로를 추가한다 — 마이크를 전혀 타지 않는다.
        # ══════════════════════════════════════════════════════
        with st.expander(tt("chat.voice_title"), expanded=bool(st.session_state.get("voice_open"))):
            try:
                from pipeline.speech_to_text import (
                    SpeechToText, LOCAL_MODELS, CLOUD_MODELS, AUDIO_EXTS,
                    DEFAULT_LOCAL_MODEL, DEFAULT_CLOUD_MODEL,
                )
                _stt_key = st.session_state.get("ov_openai_key") or None
                _avail = SpeechToText.availability(_stt_key)
                # 🔒 LLM이 로컬 모드(외부 전송 차단)면 클라우드 STT 금지
                _allow_cloud = not (st.session_state.get("llm_p5", "local") == "local"
                                    and st.session_state.get("pii_skip_local", True))
                _usable = _avail["local"] or (_avail["cloud"] and _allow_cloud)

                if not _usable:
                    # ── 백엔드 부재: 녹음기를 감추고 '무엇을 하면 되는지'만 보여준다 ──
                    alert_box(tt("chat.voice_no_backend"), "warn")
                    st.code("pip install faster-whisper", language="bash")
                    st.caption(tt("chat.voice_no_backend_alt"))
                    st.caption(tt("chat.voice_status",
                                  lo=("✅" if _avail["local"] else "❌") + " " + _avail["detail"]["local"],
                                  cl=("✅" if _avail["cloud"] else "❌") + " " + _avail["detail"]["cloud"]))
                    if not _allow_cloud:
                        st.caption(tt("chat.voice_locked"))
                else:
                    _vc1, _vc2 = st.columns([1, 1])
                    _be = _vc1.selectbox(
                        tt("chat.voice_backend"), ["auto", "local", "cloud"],
                        index=["auto", "local", "cloud"].index(st.session_state.get("stt_backend", "auto")),
                        key="stt_backend",
                        format_func=lambda b: {"auto": tt("chat.voice_auto"),
                                               "local": tt("chat.voice_local"),
                                               "cloud": tt("chat.voice_cloud")}[b],
                        help=tt("chat.voice_backend_help"))
                    if _be == "cloud" or (_be == "auto" and not _avail["local"]):
                        _vc2.selectbox(tt("chat.voice_model"), list(CLOUD_MODELS),
                                       index=list(CLOUD_MODELS).index(DEFAULT_CLOUD_MODEL),
                                       key="stt_cloud_model")
                    else:
                        _vc2.selectbox(tt("chat.voice_model"), list(LOCAL_MODELS),
                                       index=list(LOCAL_MODELS).index(DEFAULT_LOCAL_MODEL),
                                       key="stt_local_model",
                                       help=tt("chat.voice_local_model_help"))
                    st.caption(tt("chat.voice_status",
                                  lo=("✅" if _avail["local"] else "❌") + " " + _avail["detail"]["local"],
                                  cl=("✅" if _avail["cloud"] else "❌") + " " + _avail["detail"]["cloud"]))
                    if not _allow_cloud:
                        st.caption(tt("chat.voice_locked"))

                    def _stt_run(_raw: bytes, _fname: str, _src: str):
                        """녹음·업로드 공통 처리 — 같은 입력 재처리 방지 후 STT 실행."""
                        _sig = f"{_src}:{len(_raw)}:{hash(_raw[:8192])}"
                        if st.session_state.get("_stt_last_sig") == _sig:
                            return
                        _stt = SpeechToText(
                            backend=st.session_state.get("stt_backend", "auto"),
                            allow_cloud=_allow_cloud,
                            local_model=st.session_state.get("stt_local_model", DEFAULT_LOCAL_MODEL),
                            cloud_model=st.session_state.get("stt_cloud_model", DEFAULT_CLOUD_MODEL),
                            api_key=_stt_key, lang=LANG)
                        with st.spinner(tt("chat.voice_working")):
                            _ok, _txt, _note = _stt.transcribe(_raw, _fname)
                        st.session_state["_stt_last_sig"] = _sig
                        st.session_state["_stt_note"] = _note
                        if _ok:
                            st.session_state["_stt_text"] = _txt
                            if st.session_state.get("stt_autosend", True):
                                _run_chat_query(_txt)
                                st.session_state.pop("_stt_text", None)
                                st.rerun()
                        else:
                            st.session_state["_stt_err"] = _note

                    # ── ① 마이크 녹음 ──
                    _mic_ok = True
                    try:
                        _audio = st.audio_input(tt("chat.voice_record"), key="chat_audio")
                    except AttributeError:
                        _mic_ok, _audio = False, None
                        alert_box(tt("chat.voice_need_upgrade"), "warn")
                    if _mic_ok:
                        st.caption(tt("chat.voice_mic_hint"))
                    if _mic_ok and _audio is not None:
                        _rb = _audio.getvalue()
                        # ══════════════════════════════════════════════
                        # ✨ v15 (요청 2): 즉석 녹음 → 파일로 저장 → 파일 입력 경로
                        #   ① 다운로드: 내 PC에 .wav로 저장 (보관·재사용·공유)
                        #   ② 서버 저장: recordings/ 에 저장 → 아래 '저장된 녹음' 목록에서 재사용
                        #   브라우저 마이크가 불안정한 환경에서도, 한 번 성공한 녹음을
                        #   파일로 굳혀두면 이후엔 파일 경로로 안정적으로 인식할 수 있다.
                        # ══════════════════════════════════════════════
                        st.audio(_rb)
                        _rc1, _rc2, _rc3 = st.columns([1, 1, 1])
                        import datetime as _dt
                        _stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                        _rc1.download_button(tt("chat.voice_dl"), _rb,
                                             file_name=f"rec_{_stamp}.wav", mime="audio/wav",
                                             key="stt_dl", width='stretch')
                        if _rc2.button(tt("chat.voice_save"), key="stt_save", width='stretch'):
                            try:
                                _rdir = Path("recordings"); _rdir.mkdir(exist_ok=True)
                                _rp = _rdir / f"rec_{_stamp}.wav"
                                _rp.write_bytes(_rb)
                                st.toast(tt("chat.voice_saved", name=_rp.name))
                            except Exception as _se:
                                alert_box(tt("chat.voice_fail", e=_se), "error")
                        if _rc3.button(tt("chat.voice_transcribe"), key="stt_mic_go", width='stretch'):
                            _stt_run(_rb, f"rec_{_stamp}.wav", "mic")
                        if st.session_state.get("stt_autosend", True):
                            _stt_run(_rb, f"rec_{_stamp}.wav", "mic")   # 자동 전송 켜짐 → 즉시 인식

                    # ── ② ✨ v14: 오디오 파일 업로드 (마이크 불가 환경 대체 경로) ──
                    _up = st.file_uploader(tt("chat.voice_upload"), type=list(AUDIO_EXTS),
                                           key="chat_audio_file",
                                           help=tt("chat.voice_upload_help"))
                    if _up is not None:
                        _ub = _up.getvalue()
                        st.caption(tt("chat.voice_file_info", name=_up.name,
                                      kb=f"{len(_ub)/1024:,.0f}"))
                        _uc1, _uc2 = st.columns([1, 1])
                        if _uc1.button(tt("chat.voice_transcribe"), key="stt_file_go", width='stretch'):
                            _stt_run(_ub, _up.name, "file")
                        _uc2.audio(_ub)

                    # ── ③ ✨ v15: 서버에 저장해둔 녹음 재사용 ──
                    try:
                        _rdir = Path("recordings")
                        _saved = sorted(_rdir.glob("*.wav"), key=lambda q: q.stat().st_mtime,
                                        reverse=True)[:12] if _rdir.is_dir() else []
                    except Exception:
                        _saved = []
                    if _saved:
                        _sv1, _sv2 = st.columns([2.2, 1])
                        _pick = _sv1.selectbox(tt("chat.voice_saved_label"),
                                               [q.name for q in _saved], key="stt_saved_sel")
                        if _sv2.button(tt("chat.voice_transcribe"), key="stt_saved_go", width='stretch'):
                            _sp = _rdir / _pick
                            _stt_run(_sp.read_bytes(), _sp.name, f"saved:{_pick}")
                        st.caption(tt("chat.voice_saved_hint", n=len(_saved), dir=str(_rdir.resolve())))

                    st.checkbox(tt("chat.voice_autosend"), value=True, key="stt_autosend")

                    # ── 결과 / 오류 표시 ──
                    if st.session_state.get("_stt_err"):
                        alert_box(st.session_state.pop("_stt_err"), "error")
                    if st.session_state.get("_stt_text"):
                        st.caption(f"{st.session_state.get('_stt_note','')} — 📝 {st.session_state['_stt_text']}")
                        _sc1, _sc2 = st.columns([2, 1])
                        if _sc1.button(tt("chat.voice_send"), key="stt_send", width='stretch'):
                            _run_chat_query(st.session_state.pop("_stt_text"))
                            st.rerun()
                        if _sc2.button(tt("chat.voice_discard"), key="stt_discard", width='stretch'):
                            st.session_state.pop("_stt_text", None)
                            st.session_state.pop("_stt_last_sig", None)
                            st.rerun()

                # ── 🩺 진단 (요청 1: 원인 추적용) ──
                with st.expander(tt("chat.voice_diag"), expanded=False):
                    import streamlit as _stmod
                    st.caption(f"Streamlit {_stmod.__version__} · audio_input "
                               f"{'있음' if hasattr(st, 'audio_input') else '없음(1.42+ 필요)'}")
                    st.caption(tt("chat.voice_diag_secure"))
                    st.code(
                        f"local  : {_avail['local']}  ({_avail['detail']['local']})\n"
                        f"cloud  : {_avail['cloud']}  ({_avail['detail']['cloud']})\n"
                        f"llm_p5 : {st.session_state.get('llm_p5','local')}\n"
                        f"pii_skip_local : {st.session_state.get('pii_skip_local', True)}\n"
                        f"allow_cloud    : {_allow_cloud}",
                        language="text")
                    if st.session_state.get("_stt_trace"):
                        st.code(st.session_state["_stt_trace"][-1800:], language="text")
            except Exception as _ve:
                import traceback as _tb
                st.session_state["_stt_trace"] = _tb.format_exc()
                alert_box(tt("chat.voice_fail", e=_ve), "error")
                with st.expander(tt("chat.voice_diag"), expanded=True):
                    st.code(_tb.format_exc()[-1800:], language="text")

        _q = st.chat_input(t("chat.input_ph"), key="chat_in")
        if _q:
            _run_chat_query(_q)
            st.rerun()
        # ── 🩺 v14: 에이전트 자가진단 (요청 3) ──────────────────
        #   챗봇 액션이 "작동하지 않는" 것처럼 보이는 원인은 대개 액션 파이프라인이 아니라
        #   LLM 연결이다(provider=local + llama.cpp 미기동 → 응답 없음 → 액션 0건).
        #   이 패널은 **LLM을 거치지 않고** 파싱→검증→실행까지 직접 돌려
        #   "파이프라인 정상 / LLM 연결 문제"를 분리해준다.
        with st.expander(tt("chat.agent_diag"), expanded=False):
            try:
                from pipeline.chat_agent import ACTIONS, parse_actions
                _prov = st.session_state.get('llm_p5', 'local')
                st.caption(tt("chat.agent_diag_help"))
                st.code(f"provider : {_prov}\n"
                        f"actions  : {len(ACTIONS)}종 등록\n"
                        f"history  : {len(st.session_state.get('chat_history', []))}턴",
                        language="text")
                _dc1, _dc2 = st.columns([1, 1])
                if _dc1.button(tt("chat.agent_test_llm"), key="agent_test_llm", width='stretch'):
                    try:
                        _r = _build_llm_analyzer().test_connection()
                        alert_box(_r["message"], "ok" if _r["ok"] else "error")
                        for _e in _r.get("errors", [])[:2]:
                            st.caption(f"• {_e}")
                    except Exception as _te:
                        alert_box(f"{type(_te).__name__}: {_te}", "error")
                if _dc2.button(tt("chat.agent_test_actions"), key="agent_test_acts", width='stretch'):
                    # LLM이 보냈다고 가정한 마커를 직접 통과시켜 파싱·검증·실행을 전수 확인
                    _samples = [f"[[ACTION: {m['example']}]]" for m in ACTIONS.values()]
                    _rows, _bad = [], 0
                    for _sm in _samples:
                        _cl, _ac = parse_actions(_sm)
                        _rows.append(f"{'✅' if _ac else '❌'} {_sm[10:-2]:38s} → "
                                     f"{'검증통과' if _ac else '검증실패'}")
                        if not _ac:
                            _bad += 1
                    # 악성 입력 방어도 함께 확인
                    for _mal in ["exec_shell(rm -rf /)", "goto_session(99)", "goto_s5_tab(../../etc)"]:
                        _cl, _ac = parse_actions(f"[[ACTION: {_mal}]]")
                        _rows.append(f"{'✅' if not _ac else '⚠'} {_mal:38s} → "
                                     f"{'차단됨' if not _ac else '통과(위험)'}")
                        if _ac:
                            _bad += 1
                    st.code("\n".join(_rows), language="text")
                    if _bad == 0:
                        alert_box(tt("chat.agent_ok", n=len(ACTIONS)), "ok")
                    else:
                        alert_box(tt("chat.agent_ng", n=_bad), "error")
                # 실제로 상태를 바꿔보는 라이브 테스트 (한 번에 하나)
                _live = st.selectbox(tt("chat.agent_live"), list(ACTIONS.keys()), key="agent_live_sel",
                                     format_func=lambda k: f"{k} — {ACTIONS[k]['example']}")
                if st.button(tt("chat.agent_live_run"), key="agent_live_go", width='stretch'):
                    _cl, _ac = parse_actions(f"[[ACTION: {ACTIONS[_live]['example']}]]")
                    _nt = _apply_chat_actions(_ac)
                    if _nt:
                        alert_box(" / ".join(_nt), "ok")
                        st.rerun()
                    else:
                        alert_box(tt("chat.agent_live_none"), "warn")
            except Exception as _ae:
                alert_box(f"{type(_ae).__name__}: {_ae}", "error")

        if _hist and st.button(t("chat.clear"), key="chat_clear_btn"):
            st.session_state["chat_history"] = []
            st.rerun()
        # ⌨ v12: 단축키(C)로 챗봇을 새로 켠 직후라면, 렌더된 입력창에 자동 포커스
        if st.session_state.pop('_focus_chat_pending', False):
            components.html("""<script>(function(){
              var d=window.parent.document;
              function tryFocus(n){
                var el=d.querySelector('[data-testid="stChatInputTextArea"]')||d.querySelector('[data-testid="stChatInput"] textarea');
                if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.focus();}
                else if(n>0){setTimeout(function(){tryFocus(n-1)},150);}
              }
              tryFocus(15);
            })();</script>""", height=0)

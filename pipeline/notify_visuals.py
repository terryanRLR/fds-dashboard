"""
NotifyVisuals — 알림(이메일/Slack)용 경량 시각화 빌더 (신규)

배경
  실무자가 새벽 온콜 중 폰으로 알림을 받았을 때, 텍스트 벽 대신
  3초 안에 상황을 파악할 수 있는 시각 요소를 붙인다.

채널별 제약과 전략
  Slack (Incoming Webhook)
    - 이미지 첨부 불가(봇 토큰 필요) → 유니코드 블록 문자 스파크라인/막대
  Email (SMTP)
    - <script> 제거됨(Plotly 불가), 외부 이미지 차단 잦음
    → 표(table) + 인라인 스타일 + 배경색 막대만 사용 (100% 렌더 보장)
    - 상세 인터랙티브 차트는 자체완결 HTML "첨부파일"로 제공 (브라우저에서 열람)

⚠ 보안 원칙: 이 모듈에 들어오는 데이터는 반드시 "마스킹 후" 데이터여야 한다.
  (이메일/슬랙은 스크린샷 유출이 가장 쉬운 매체 — pii_masker 통과분만 전달할 것)

핵심 API
  slack_visual_single(L, ...) / slack_visual_batch(L, ...)  → str
  email_html_single(L, ...)  / email_html_batch(L, ...)     → KPI 블록 html
  wrap_email(L, title, kpi_html, body_html)                 → 완성 이메일 html
  report_html_single(L, ...) / report_html_batch(L, ...)    → 첨부용 자체완결 html
  html_to_text(html)                                        → 평문 폴백
"""

from __future__ import annotations

import re
import html as _esc
import json
import time

# ── 팔레트 (이메일은 라이트 배경 고정 — 다크모드 무관) ──────
_C = {
    "bg": "#f4f6f9", "card": "#ffffff", "line": "#e3e8ef",
    "text": "#1f2937", "muted": "#6b7280",
    "accent": "#0f766e", "red": "#dc2626", "amber": "#d97706", "green": "#059669",
    "bar_bg": "#eef1f5",
}

_SPARK = "▁▂▃▄▅▆▇█"


# ══════════════════════════════════════════════════════════
# 공용 유틸
# ══════════════════════════════════════════════════════════

def _clamp01(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def spark(values, n_bins: int = 12) -> str:
    """수치 리스트 → 스파크라인. 값이 많으면 균등 구간 히스토그램으로 압축."""
    vals = [_clamp01(v) for v in values if v is not None]
    if not vals:
        return ""
    if len(vals) > n_bins:                       # 히스토그램 압축 (위험도 분포용)
        counts = [0] * n_bins
        for v in vals:
            counts[min(int(v * n_bins), n_bins - 1)] += 1
        mx = max(counts) or 1
        return "".join(_SPARK[round(c / mx * (len(_SPARK) - 1))] for c in counts)
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    return "".join(_SPARK[round((v - lo) / rng * (len(_SPARK) - 1))] for v in vals)


def risk_bar(risk, width: int = 10) -> str:
    """위험도 0~1 → ▰▰▰▱▱ 텍스트 게이지"""
    r = _clamp01(risk)
    filled = round(r * width)
    return "▰" * filled + "▱" * (width - filled)


def _mini_bar(count: int, max_count: int, width: int = 6) -> str:
    if max_count <= 0:
        return ""
    n = max(1, round(count / max_count * width)) if count > 0 else 0
    return "■" * n


def html_to_text(html_str: str) -> str:
    """HTML → 평문 폴백 (multipart의 text/plain 파트용)"""
    s = re.sub(r"<\s*(br|/p|/div|/tr|/h[1-6])\s*/?>", "\n", html_str or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = _esc.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


# ── ✨ v3.2: 본문 정규화 — LLM이 평문/마크다운으로 답해도 이메일에서 줄바꿈 보존 ──
_HTML_TAG_RE = re.compile(r"<(p|br|div|table|ul|ol|li|h[1-6]|b|strong|em|i|span)\b", re.I)

def body_to_html(text: str) -> str:
    """평문/마크다운풍 본문 → 이메일 HTML.
    HTML은 \\n을 공백 취급하므로 평문 그대로 끼우면 '텍스트 벽'이 됨 →
    줄바꿈·빈 줄·**굵게**·- 목록·# 소제목을 이메일 안전 태그로 변환.
    이미 HTML 태그가 있으면 원문 그대로 통과."""
    t = (text or "").strip()
    if not t:
        return ""
    if _HTML_TAG_RE.search(t):
        return t                                   # 이미 HTML — 손대지 않음
    esc = _esc.escape(t)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)          # **굵게**
    out, in_list = [], False
    for ln in esc.split("\n"):
        s = ln.strip()
        m_li = re.match(r"^(?:[-•▪*]|\d+[.)])\s+(.*)$", s)
        if m_li:
            if not in_list:
                out.append("<ul style='margin:4px 0 10px;padding-left:20px'>"); in_list = True
            out.append(f"<li style='margin:2px 0'>{m_li.group(1)}</li>")
            continue
        if in_list:
            out.append("</ul>"); in_list = False
        m_h = re.match(r"^#{1,3}\s+(.*)$", s)
        if m_h:
            out.append(f"<div style='font-weight:700;font-size:13.5px;margin:12px 0 6px'>{m_h.group(1)}</div>")
        elif s == "":
            out.append("<div style='height:8px;font-size:0'>&nbsp;</div>")   # 빈 줄 = 문단 간격
        else:
            out.append(f"<div style='margin:0 0 2px'>{s}</div>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


# ══════════════════════════════════════════════════════════
# Slack — 텍스트 시각화 블록
# ══════════════════════════════════════════════════════════

def slack_visual_single(L: dict, type_code: str, type_label: str,
                        risk: float, threshold: float,
                        proba: dict | None = None, model: str = "") -> str:
    """단건 탐지용 헤더 블록. 기존 LLM slack 메시지 '앞'에 붙인다."""
    r = _clamp01(risk)
    icon = "🚨" if r >= threshold or (type_code and type_code != "m") else "✅"
    lines = [f"{icon} *{type_code.upper()} · {type_label}*  |  "
             f"{L.get('risk','위험')} {risk_bar(r)} *{r:.2f}*  ({L.get('thr','임계')} {threshold:.2f})"]
    if proba:
        top = sorted(((k, _clamp01(v)) for k, v in proba.items()),
                     key=lambda x: x[1], reverse=True)[:3]
        mx = top[0][1] or 1
        seg = " · ".join(f"{k} {'█' * max(1, round(v / mx * 6))} {v * 100:.0f}%" for k, v in top)
        lines.append(f"{L.get('prob','확률')}: {seg}")
    if model:
        lines.append(f"{L.get('model','모델')}: {model}")
    return "\n".join(lines)


def slack_visual_batch(L: dict, total: int, anomaly: int,
                       avg_risk: float, max_risk: float,
                       risks: list, type_counts: dict) -> str:
    lines = [f"📦 *{total}{L.get('cnt','건')}* → 🚨 *{anomaly}{L.get('cnt','건')}*  |  "
             f"{L.get('avg','평균')} {avg_risk:.2f} · {L.get('max','최고')} *{max_risk:.2f}*"]
    if risks:
        lines.append(f"{L.get('risk_dist','위험 분포')} {spark(risks)} (0→1)")
    if type_counts:
        mx = max(type_counts.values())
        items = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        lines.append(f"{L.get('type_dist','유형')}: " +
                     " · ".join(f"{k} {_mini_bar(v, mx)} {v}" for k, v in items))
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════
# Email — 본문 KPI 블록 (표 + 인라인 스타일, 스크립트/외부이미지 0)
# ══════════════════════════════════════════════════════════

def _kpi_cell(label: str, value: str, color: str) -> str:
    return (f'<td style="padding:10px 14px;background:{_C["card"]};border:1px solid {_C["line"]};'
            f'border-radius:8px;text-align:center;min-width:90px">'
            f'<div style="font-size:11px;color:{_C["muted"]};letter-spacing:.04em;margin-bottom:4px">{_esc.escape(label)}</div>'
            f'<div style="font-size:17px;font-weight:700;color:{color};font-family:Consolas,Menlo,monospace">{value}</div></td>')


def _hbar_row(label: str, pct: float, count_txt: str, color: str) -> str:
    """가로 막대 1줄 — 중첩 테이블 + 배경색 (이메일 클라이언트 전부 지원)"""
    w = max(2, min(100, round(pct)))
    return (f'<tr><td style="padding:3px 8px 3px 0;font-size:12px;color:{_C["text"]};'
            f'font-family:Consolas,Menlo,monospace;white-space:nowrap">{_esc.escape(label)}</td>'
            f'<td style="width:100%;padding:3px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="background:{color};width:{w}%;height:12px;border-radius:3px;font-size:0">&nbsp;</td>'
            f'<td style="background:{_C["bar_bg"]};height:12px;border-radius:3px;font-size:0">&nbsp;</td></tr></table></td>'
            f'<td style="padding:3px 0 3px 8px;font-size:12px;color:{_C["muted"]};'
            f'font-family:Consolas,Menlo,monospace;white-space:nowrap">{_esc.escape(count_txt)}</td></tr>')


def email_html_single(L: dict, type_code: str, type_label: str, is_anomaly: bool,
                      risk: float, threshold: float,
                      proba: dict | None = None, model: str = "") -> str:
    r = _clamp01(risk)
    rc = _C["red"] if r >= 0.5 else (_C["amber"] if r >= threshold else _C["green"])
    verdict = L.get("anom", "이상 거래") if is_anomaly else L.get("norm", "정상")
    vc = _C["red"] if is_anomaly else _C["green"]
    kpi = ('<table role="presentation" cellpadding="0" cellspacing="6"><tr>'
           + _kpi_cell(L.get("verdict", "판정"), _esc.escape(verdict), vc)
           + _kpi_cell(L.get("type", "예측 유형"), f"{type_code.upper()}", vc)
           + _kpi_cell(L.get("risk", "위험 점수"), f"{r:.3f}", rc)
           + _kpi_cell(L.get("thr", "임계값"), f"{threshold:.2f}", _C["muted"])
           + "</tr></table>")
    gauge = (f'<div style="margin:12px 2px 4px;font-size:12px;color:{_C["muted"]}">{_esc.escape(type_label)}'
             + (f' · {_esc.escape(model)}' if model else '') + "</div>"
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
             f'<td style="background:{rc};width:{max(2, round(r * 100))}%;height:14px;border-radius:4px;font-size:0">&nbsp;</td>'
             f'<td style="background:{_C["bar_bg"]};height:14px;border-radius:4px;font-size:0">&nbsp;</td></tr></table>')
    prob_rows = ""
    if proba:
        top = sorted(((k, _clamp01(v)) for k, v in proba.items()),
                     key=lambda x: x[1], reverse=True)[:5]
        prob_rows = (f'<div style="margin:14px 2px 6px;font-size:12px;font-weight:700;color:{_C["text"]}">'
                     f'{_esc.escape(L.get("prob", "클래스별 확률 (상위 5)"))}</div>'
                     '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
                     + "".join(_hbar_row(k, v * 100, f"{v * 100:.1f}%",
                                         _C["red"] if k != "m" else _C["green"]) for k, v in top)
                     + "</table>")
    return kpi + gauge + prob_rows


def email_html_batch(L: dict, total: int, anomaly: int, avg_risk: float, max_risk: float,
                     type_counts: dict) -> str:
    kpi = ('<table role="presentation" cellpadding="0" cellspacing="6"><tr>'
           + _kpi_cell(L.get("total", "전체 거래"), f"{total:,}", _C["accent"])
           + _kpi_cell(L.get("anomaly", "이상 거래"), f"{anomaly:,}", _C["red"] if anomaly else _C["green"])
           + _kpi_cell(L.get("avg", "평균 위험"), f"{avg_risk:.3f}", _C["amber"])
           + _kpi_cell(L.get("max", "최고 위험"), f"{max_risk:.3f}", _C["red"])
           + "</tr></table>")
    dist = ""
    if type_counts:
        mx = max(type_counts.values()) or 1
        items = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        dist = (f'<div style="margin:14px 2px 6px;font-size:12px;font-weight:700;color:{_C["text"]}">'
                f'{_esc.escape(L.get("type_dist", "이상거래 유형 분포"))}</div>'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
                + "".join(_hbar_row(k.upper(), c / mx * 100, f"{c}{L.get('cnt', '건')}", _C["red"])
                          for k, c in items)
                + "</table>")
    return kpi + dist


def wrap_email(L: dict, title: str, kpi_html: str, body_html: str,
               attached_note: bool = False) -> str:
    """KPI 블록 + 기존 LLM 본문을 하나의 이메일 문서로 감싼다.
    ✨ v3.2: 본문이 평문/마크다운이어도 줄바꿈이 보존되도록 자동 정규화."""
    body_html = body_to_html(body_html)
    note = ""
    if attached_note:
        note = (f'<div style="margin-top:14px;padding:10px 14px;background:#eef7f6;border:1px solid #cde7e4;'
                f'border-radius:8px;font-size:12px;color:{_C["accent"]}">📎 '
                f'{_esc.escape(L.get("attached", "상세 인터랙티브 리포트가 첨부되어 있습니다 — 브라우저에서 열어보세요."))}</div>')
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:{_C['bg']}">
<div style="max-width:640px;margin:0 auto;padding:20px 16px;font-family:'Segoe UI',AppleSDGothicNeo,'Malgun Gothic',sans-serif">
<div style="background:{_C['card']};border:1px solid {_C['line']};border-radius:12px;overflow:hidden">
<div style="background:#0b1f2a;padding:14px 20px">
  <span style="color:#7dd3cd;font-size:15px;font-weight:700">🛡️ {_esc.escape(title)}</span>
  <span style="color:#8296a0;font-size:11px;float:right;padding-top:3px;font-family:Consolas,monospace">{ts}</span>
</div>
<div style="padding:18px 20px 8px;background:{_C['bg']}">{kpi_html}</div>
<div style="padding:14px 20px;font-size:13px;line-height:1.65;color:{_C['text']}">{body_html}{note}</div>
<div style="padding:10px 20px;border-top:1px solid {_C['line']};font-size:11px;color:{_C['muted']}">
FDS QA Dashboard · {_esc.escape(L.get('auto_note', '본 메일은 이상거래 탐지 시스템에서 자동 발송되었습니다.'))}</div>
</div></div></body></html>"""


# ══════════════════════════════════════════════════════════
# 첨부용 자체완결 인터랙티브 리포트 (Plotly CDN)
# ══════════════════════════════════════════════════════════

def _report_shell(title: str, inner: str, charts_js: str) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{_esc.escape(title)}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
body{{margin:0;background:#0d1626;color:#e8f0fe;font-family:'Segoe UI',AppleSDGothicNeo,'Malgun Gothic',sans-serif}}
.wrap{{max-width:860px;margin:0 auto;padding:28px 20px}}
.card{{background:#111d30;border:1px solid #22304a;border-radius:12px;padding:18px 20px;margin-bottom:16px}}
h1{{font-size:19px;margin:0 0 4px}} .sub{{color:#8899b4;font-size:12px;font-family:Consolas,monospace}}
.kpis{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}
.kpi{{flex:1;min-width:120px;background:#0d1626;border:1px solid #22304a;border-radius:10px;padding:12px;text-align:center}}
.kpi .l{{font-size:11px;color:#8899b4}} .kpi .v{{font-size:20px;font-weight:700;font-family:Consolas,monospace;margin-top:4px}}
table{{width:100%;border-collapse:collapse;font-size:12px}} td,th{{padding:7px 10px;border-bottom:1px solid #22304a;text-align:left}}
th{{color:#8899b4;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em}}
</style></head><body><div class="wrap">
<h1>🛡️ {_esc.escape(title)}</h1><div class="sub">{ts} · FDS QA Dashboard</div>
{inner}
<script>{charts_js}</script>
</div></body></html>"""


_PLOTLY_DARK = ("{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',"
                "font:{color:'#8899b4',size:12},margin:{l:50,r:20,t:30,b:40}}")


def report_html_single(L: dict, title: str, type_code: str, type_label: str,
                       is_anomaly: bool, risk: float, threshold: float,
                       proba: dict, model: str, masked_row: dict,
                       analysis_text: str = "") -> str:
    r = _clamp01(risk)
    verdict = L.get("anom", "이상 거래") if is_anomaly else L.get("norm", "정상")
    vc = "#ff3b5c" if is_anomaly else "#10d98c"
    proba = {k: _clamp01(v) for k, v in (proba or {}).items()}
    keys = sorted(proba, key=proba.get, reverse=True)
    row_rows = "".join(f"<tr><td>{_esc.escape(str(k))}</td><td>{_esc.escape(str(v))}</td></tr>"
                       for k, v in list(masked_row.items())[:40])
    analysis_html = (f'<div class="card"><b>{_esc.escape(L.get("analysis", "AI 분석"))}</b>'
                     f'<div style="white-space:pre-wrap;font-size:13px;line-height:1.7;margin-top:8px">'
                     f'{_esc.escape(analysis_text)}</div></div>') if analysis_text else ""
    inner = f"""
<div class="kpis">
 <div class="kpi"><div class="l">{_esc.escape(L.get('verdict','판정'))}</div><div class="v" style="color:{vc}">{_esc.escape(verdict)}</div></div>
 <div class="kpi"><div class="l">{_esc.escape(L.get('type','예측 유형'))}</div><div class="v" style="color:{vc}">{type_code.upper()} · {_esc.escape(type_label)}</div></div>
 <div class="kpi"><div class="l">{_esc.escape(L.get('risk','위험 점수'))}</div><div class="v" style="color:#f59e0b">{r:.4f}</div></div>
 <div class="kpi"><div class="l">{_esc.escape(L.get('model','모델'))}</div><div class="v" style="font-size:13px">{_esc.escape(model or '-')}</div></div>
</div>
<div class="card"><div id="gauge" style="height:220px"></div></div>
<div class="card"><b>{_esc.escape(L.get('prob','클래스별 확률'))}</b><div id="proba" style="height:300px"></div></div>
{analysis_html}
<div class="card"><b>{_esc.escape(L.get('masked','거래 데이터 (마스킹 적용)'))}</b>
<table><tr><th>field</th><th>value</th></tr>{row_rows}</table></div>"""
    js = f"""
Plotly.newPlot('gauge',[{{type:'indicator',mode:'gauge+number',value:{r:.4f},
 gauge:{{axis:{{range:[0,1],tickcolor:'#8899b4'}},bar:{{color:'{('#ff3b5c' if r >= 0.5 else '#f59e0b' if r >= threshold else '#10d98c')}'}},
 bgcolor:'#0d1626',borderwidth:0,threshold:{{line:{{color:'#e8f0fe',width:2}},value:{threshold}}}}},
 number:{{font:{{color:'#e8f0fe'}}}}}}],{_PLOTLY_DARK},{{displayModeBar:false}});
Plotly.newPlot('proba',[{{type:'bar',orientation:'h',
 y:{json.dumps(keys[::-1])},x:{json.dumps([proba[k] for k in keys[::-1]])},
 marker:{{color:{json.dumps(['#10d98c' if k == 'm' else '#ff3b5c' for k in keys[::-1]])}}},
 text:{json.dumps([f"{proba[k] * 100:.1f}%" for k in keys[::-1]])},textposition:'auto'}}],
 {_PLOTLY_DARK},{{displayModeBar:false}});"""
    return _report_shell(title, inner, js)


def report_html_batch(L: dict, title: str, total: int, anomaly: int,
                      avg_risk: float, max_risk: float,
                      risks: list, type_counts: dict, rows_out: list,
                      analysis_text: str = "") -> str:
    risks = [_clamp01(v) for v in (risks or [])]
    tc_keys = sorted(type_counts, key=type_counts.get, reverse=True) if type_counts else []
    vrows = "".join(
        f"<tr><td>{i + 1}</td><td>{_esc.escape(str(r.get('fraud_type', '-')).upper())}</td>"
        f"<td>{_clamp01(r.get('risk_score', 0)):.4f}</td>"
        f"<td style='color:{('#ff3b5c' if r.get('is_anomaly') else '#10d98c')}'>{'🚨' if r.get('is_anomaly') else '✅'}</td>"
        f"<td>{_esc.escape(str(r.get('true_label', '') or '-').upper())}</td></tr>"
        for i, r in enumerate((rows_out or [])[:200]))
    analysis_html = (f'<div class="card"><b>{_esc.escape(L.get("analysis", "AI 분석"))}</b>'
                     f'<div style="white-space:pre-wrap;font-size:13px;line-height:1.7;margin-top:8px">'
                     f'{_esc.escape(analysis_text)}</div></div>') if analysis_text else ""
    inner = f"""
<div class="kpis">
 <div class="kpi"><div class="l">{_esc.escape(L.get('total','전체 거래'))}</div><div class="v" style="color:#00d2c8">{total:,}</div></div>
 <div class="kpi"><div class="l">{_esc.escape(L.get('anomaly','이상 거래'))}</div><div class="v" style="color:#ff3b5c">{anomaly:,}</div></div>
 <div class="kpi"><div class="l">{_esc.escape(L.get('avg','평균 위험'))}</div><div class="v" style="color:#f59e0b">{avg_risk:.4f}</div></div>
 <div class="kpi"><div class="l">{_esc.escape(L.get('max','최고 위험'))}</div><div class="v" style="color:#ff3b5c">{max_risk:.4f}</div></div>
</div>
<div class="card"><b>{_esc.escape(L.get('risk_dist','위험도 분포'))}</b><div id="hist" style="height:260px"></div></div>
<div class="card"><b>{_esc.escape(L.get('type_dist','이상거래 유형 분포'))}</b><div id="types" style="height:260px"></div></div>
{analysis_html}
<div class="card"><b>{_esc.escape(L.get('verdicts','건별 판정'))}</b>
<table><tr><th>#</th><th>type</th><th>risk</th><th>verdict</th><th>true</th></tr>{vrows}</table></div>"""
    js = f"""
Plotly.newPlot('hist',[{{type:'histogram',x:{json.dumps(risks)},nbinsx:20,marker:{{color:'#00d2c8'}}}}],
 {_PLOTLY_DARK},{{displayModeBar:false}});
Plotly.newPlot('types',[{{type:'bar',x:{json.dumps([k.upper() for k in tc_keys])},
 y:{json.dumps([type_counts[k] for k in tc_keys])},marker:{{color:'#ff3b5c'}},
 text:{json.dumps([str(type_counts[k]) for k in tc_keys])},textposition:'auto'}}],
 {_PLOTLY_DARK},{{displayModeBar:false}});"""
    return _report_shell(title, inner, js)

"""
FeatureBridge — 원본 행 → 파생(engineered) 피처 자동 변환기 (v5.7 신규)

배경
  팀의 81피처 모델(한방/2단계)은 파생 피처를 입력받지만, 세션 5의 5가지 입력은
  전부 '원본 행'이다. 전처리 코드가 없어도, 팀 환경에 이미 존재하는
  **train.csv(원본) + X_tr.parquet(변환 결과)** 쌍에서 변환 규칙을 역학습한다.
  (X_tr의 pandas 인덱스가 원본 행 번호를 보존하므로 정렬 가능 — 검증됨)

핵심 원리 — "추측하되, 검증 없이는 채택하지 않는다"
  각 피처마다 전략을 순서대로 시도하고, 홀드아웃에서 일치율 ≥ 98.5%일 때만 채택:
    S1 identity  : 원본에 같은 이름 존재, 값 일치 (81개 중 ~37개)
    S2 lookup    : 원본 컬럼 값 → 파생 값 매핑 학습 (범주 인코딩·빈도표·시군구 등)
    S3 derived   : 이름 패턴별 후보 공식(절대값·log·시각·비율·플래그합산 …) 중 검증 통과분
    S4 default   : 위 전부 실패 시 파생 컬럼 중앙값 (리포트에 명시 — 근사임을 투명하게)

  fit() 시작 시 정렬 자체를 검증한다(공통 수치 컬럼 일치율 ≥ 98%). 짝이 아닌
  (원본, 파생) 쌍이면 명확한 메시지로 거부 — 조용한 오변환 방지.

사용
  fit   : python -m pipeline.feature_bridge data/train.csv data/X_tr.parquet
          → models/feature_bridge.pkl 저장 + 피처별 채택 전략 리포트 출력
  추론  : bridge.transform(rows_df) → 파생 DataFrame
          make_bridged_classifier(모델 spec, bridge) → 세션5 호환 predict(row)
"""

from __future__ import annotations

import re
import pickle
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_MATCH_THRESHOLD = 0.985     # 홀드아웃 일치율 — 이 미만이면 채택하지 않음
_ALIGN_THRESHOLD = 0.98      # (원본, 파생) 정렬 검증 최소 일치율


# ══════════════════════════════════════════════════════════
# 이름 패턴별 파생 후보 공식 (여러 후보 → 검증 통과분만 채택)
# ══════════════════════════════════════════════════════════

def _dt(s):  return pd.to_datetime(s, errors="coerce")
def _num(s): return pd.to_numeric(s, errors="coerce")

def _candidates(feat: str, raw: pd.DataFrame) -> list:
    """feat 이름을 해석해 (설명, raw_df→Series 함수) 후보 목록 반환"""
    C, cols = [], set(raw.columns)
    amt = "Transaction_Amount"

    def has(*cs): return all(c in cols for c in cs)

    if feat.endswith("_abs"):
        base = feat[:-4]
        if base in cols:
            C.append((f"abs({base})", lambda r, b=base: _num(r[b]).abs()))
    if feat.endswith("_log"):
        base = feat[:-4]
        if base in cols:
            C += [(f"log1p(|{base}|)", lambda r, b=base: np.log1p(_num(r[b]).abs())),
                  (f"log1p(max({base},0))", lambda r, b=base: np.log1p(_num(r[b]).clip(lower=0)))]
    if feat == "Transaction_is_withdrawal" and has(amt):
        C += [("amount<0", lambda r: (_num(r[amt]) < 0).astype(float)),
              ("amount<=0", lambda r: (_num(r[amt]) <= 0).astype(float))]
    if feat == "tx_hour" and has("Transaction_Datetime"):
        C.append(("hour(tx_dt)", lambda r: _dt(r["Transaction_Datetime"]).dt.hour.astype(float)))
    if feat == "is_dawn" and has("Transaction_Datetime"):
        for hi in (6, 5, 7):
            C.append((f"hour<{hi}", lambda r, h=hi: (_dt(r["Transaction_Datetime"]).dt.hour < h).astype(float)))
    if feat == "Time_difference_seconds" and "Time_difference" in cols:
        C.append(("timedelta.seconds", lambda r: pd.to_timedelta(r["Time_difference"], errors="coerce").dt.total_seconds()))
    _date_pairs = [("account_age_days", "Account_creation_datetime"),
                   ("days_since_last_atm", "Last_atm_transaction_datetime"),
                   ("days_since_last_branch", "Last_bank_branch_transaction_datetime"),
                   ("days_since_resumed", "Transaction_resumed_date")]
    for key, srcc in _date_pairs:
        if feat == key and has("Transaction_Datetime", srcc):
            def _dd(r, s=srcc): return _dt(r["Transaction_Datetime"]) - _dt(r[s])
            C += [(f"(tx-{srcc}).days", lambda r, s=srcc: _dd(r, s).dt.days.astype(float)),
                  (f"(tx-{srcc})/86400s", lambda r, s=srcc: _dd(r, s).dt.total_seconds() / 86400.0),
                  (f"floor((tx-{srcc})/86400)", lambda r, s=srcc: np.floor(_dd(r, s).dt.total_seconds() / 86400.0)),
                  (f"(tx.date-{srcc}.date).days", lambda r, s=srcc: (_dt(r["Transaction_Datetime"]).dt.normalize() - _dt(r[s]).dt.normalize()).dt.days.astype(float)),
                  (f"|tx-{srcc}|.days", lambda r, s=srcc: _dd(r, s).dt.days.abs().astype(float))]
    _den = {"daily_limit": "Account_amount_daily_limit", "balance": "Account_balance",
            "month_max": "Account_one_month_max_amount"}
    m = re.match(r"amount_to_(\w+)_ratio", feat)
    if m and _den.get(m.group(1)) in cols and has(amt):
        den = _den[m.group(1)]
        for eps in (1.0, 1e-6, 1e-9):
            C.append((f"|amt|/({den}+{eps})", lambda r, d=den, e=eps: _num(r[amt]).abs() / (_num(r[d]).abs() + e)))
            C.append((f"amt/({den}+{eps})", lambda r, d=den, e=eps: _num(r[amt]) / (_num(r[d]).abs() + e)))
        def _rawdiv(a, b):
            with np.errstate(divide="ignore", invalid="ignore"):
                return pd.Series(np.asarray(a, dtype=float) / np.asarray(b, dtype=float), index=a.index)
        C += [(f"|amt|/{den}(순수)", lambda r, d=den: _rawdiv(_num(r[amt]).abs(), _num(r[d]))),
              (f"amt/{den}(순수)", lambda r, d=den: _rawdiv(_num(r[amt]), _num(r[d]))),
              (f"|amt|/max({den},1)", lambda r, d=den: _num(r[amt]).abs() / _num(r[d]).clip(lower=1)),
              (f"|amt|/max(|{den}|,1)", lambda r, d=den: _num(r[amt]).abs() / _num(r[d]).abs().clip(lower=1)),
              (f"amt/max({den},1)", lambda r, d=den: _num(r[amt]) / _num(r[d]).clip(lower=1))]
    if feat == "balance_depletion_ratio" and has(amt, "Account_balance"):
        bal = "Account_balance"
        for eps in (1.0, 1e-6, 1e-9):
            C += [(f"|amt|/(bal+{eps})", lambda r, e=eps: _num(r[amt]).abs() / (_num(r[bal]).abs() + e)),
                  (f"(bal-|amt|)/(bal+{eps})", lambda r, e=eps: (_num(r[bal]) - _num(r[amt]).abs()) / (_num(r[bal]).abs() + e))]
        C += [("|amt|/max(bal,1)", lambda r: _num(r[amt]).abs() / _num(r[bal]).clip(lower=1)),
              ("|amt|/max(|bal|,1)", lambda r: _num(r[amt]).abs() / _num(r[bal]).abs().clip(lower=1)),
              ("|amt|/(bal+|amt|+1)", lambda r: _num(r[amt]).abs() / (_num(r[bal]).abs() + _num(r[amt]).abs() + 1)),
              ("-amt/max(bal,1)", lambda r: -_num(r[amt]) / _num(r[bal]).clip(lower=1))]
    if feat == "recipient_history_low":
        for srcc in ("Number_of_transaction_with_the_account", "Transaction_history_with_the_account"):
            if srcc in cols:
                for k in (0, 1, 2, 3, 5):
                    C.append((f"{srcc}<={k}", lambda r, s=srcc, kk=k: (_num(r[s]) <= kk).astype(float)))
    if feat == "new_recipient_and_large_amount" and has(amt, "Number_of_transaction_with_the_account"):
        for th in (1e7, 5e7, 1e8):
            C.append((f"n_tx==0 & |amt|>={th:.0f}", lambda r, t=th: ((_num(r["Number_of_transaction_with_the_account"]) == 0) & (_num(r[amt]).abs() >= t)).astype(float)))
    if feat == "suspended_recipient_and_withdrawal" and has(amt, "Recipient_account_suspend_status"):
        C += [("suspend==1 & amt<0", lambda r: ((_num(r["Recipient_account_suspend_status"]) == 1) & (_num(r[amt]) < 0)).astype(float)),
              ("suspend==1 & amt<=0", lambda r: ((_num(r["Recipient_account_suspend_status"]) == 1) & (_num(r[amt]) <= 0)).astype(float))]
    if feat == "is_large_amount_abs" and has(amt):
        for th in (1e7, 5e7, 1e8):
            C.append((f"|amt|>={th:.0f}", lambda r, t=th: (_num(r[amt]).abs() >= t).astype(float)))
    if feat.endswith("_nonpositive_flag"):
        base = feat[:-len("_nonpositive_flag")]
        cand = [c for c in cols if base.lower() in c.lower()]
        for c in cand[:2]:
            C.append((f"{c}<=0", lambda r, cc=c: (_num(r[cc]) <= 0).astype(float)))
    if feat.endswith("_zero_flag"):
        base = feat[:-len("_zero_flag")]
        cand = [c for c in cols if all(t in c.lower() for t in base.split("_")[:2])]
        for c in cand[:2]:
            C.append((f"{c}==0", lambda r, cc=c: (_num(r[cc]) == 0).astype(float)))
    if feat == "threat_total_count":
        keys = ("terminal_malicious", "flag_change_of_authentication", "rooting", "VPN",
                "Unused_terminal", "roaming")
        gcols = [c for c in cols if any(k in c for k in keys)]
        if gcols:
            C.append((f"6그룹 {len(gcols)}플래그 합", lambda r, g=tuple(gcols): sum(_num(r[c]).fillna(0) for c in g)))
    _groups = {"auth_change_count": "flag_change_of_authentication",
               "terminal_malicious_count": "terminal_malicious_behavior"}
    if feat in _groups:
        gcols = [c for c in cols if _groups[feat] in c]
        if gcols:
            C.append((f"sum({len(gcols)}개 플래그)", lambda r, g=tuple(gcols): sum(_num(r[c]).fillna(0) for c in g)))
    if feat == "distance_log" and "Distance" in cols:
        C.append(("log1p(Distance)", lambda r: np.log1p(_num(r["Distance"]).clip(lower=0))))
    if feat == "connection_failure_flag" and "Transaction_num_connection_failure" in cols:
        C.append(("failures>0", lambda r: (_num(r["Transaction_num_connection_failure"]) > 0).astype(float)))
    if feat == "new_recipient_flag" and "Number_of_transaction_with_the_account" in cols:
        C.append(("n_tx_with_acct==0", lambda r: (_num(r["Number_of_transaction_with_the_account"]) == 0).astype(float)))
    return C


def _lookup_source(feat: str, cols) -> str | None:
    """파생 피처명 → 원본 소스 컬럼 추정 (가장 긴 접두 일치)"""
    best = None
    for c in cols:
        if feat.startswith(str(c)) and (best is None or len(str(c)) > len(best)):
            best = str(c)
    if best:
        return best
    if feat == "Location_sigungu" and "Location" in cols:
        return "Location"
    return None


_SRC_TF_REGISTRY = {
    "loc_token1": ("Location 2번째 토큰(시군구) 매핑", lambda s: s.astype(str).str.split().str[1]),
    "loc_token01": ("Location 시도+시군구 매핑", lambda s: s.astype(str).str.split().str[:2].str.join(" ")),
}

def _SRC_TRANSFORMS_FOR(feat: str, cols) -> dict:
    out = {}
    if feat == "Location_sigungu" and "Location" in cols:
        out["loc_token1"] = ("Location", _SRC_TF_REGISTRY["loc_token1"][0])
        out["loc_token01"] = ("Location", _SRC_TF_REGISTRY["loc_token01"][0])
    return out

def _apply_src_tf(tf_key: str, s: pd.Series) -> pd.Series:
    return _SRC_TF_REGISTRY[tf_key][1](s)


_FLAG_POOL_HINTS = {
    "device_network_risk_count": ("rooting", "vpn", "roaming", "terminal_malicious", "unused_terminal"),
    "threat_total_count": ("rooting", "vpn", "roaming", "terminal_malicious", "flag_change_of_auth",
                            "unused_terminal", "another_person", "suspend"),
    "cert_or_auth_risk": ("flag_change_of_auth", "rooting", "vpn"),
    "high_risk_device_flag": ("rooting", "terminal_malicious", "vpn", "unused_terminal"),
}

def _fit_subset(feat, Rf, tgt_f, Rv, tgt_v, R):
    """이진 플래그 풀에서 그리디로 합(count) 또는 OR(flag) 조합을 탐색해 검증 통과 시 채택"""
    hints = _FLAG_POOL_HINTS.get(feat)
    if hints is None and not (feat.endswith("_count") or feat.endswith("_risk") or feat.endswith("_flag")):
        return None
    pool = [c for c in R.columns
            if pd.api.types.is_numeric_dtype(R[c]) and set(pd.unique(_num(R[c]).dropna())) <= {0.0, 1.0}]
    if hints:
        pool = [c for c in pool if any(h in c.lower() for h in hints)] or pool
    if not pool:
        return None
    tf, tv = _num(tgt_f), _num(tgt_v)
    as_or = bool(set(tf.dropna().unique()) <= {0.0, 1.0}) and feat.endswith(("_flag", "_risk"))
    chosen, best = [], -1.0
    cur_f = pd.Series(0.0, index=Rf.index); cur_v = pd.Series(0.0, index=Rv.index)
    for _ in range(min(10, len(pool))):
        cand_best = None
        for c in pool:
            if c in chosen: continue
            nf = cur_f + _num(Rf[c]).fillna(0); nv = cur_v + _num(Rv[c]).fillna(0)
            pv = (nv > 0).astype(float) if as_or else nv
            r = _match_rate(pv, tv)
            if cand_best is None or r > cand_best[0]:
                cand_best = (r, c, nf, nv)
        if cand_best is None or cand_best[0] <= best + 1e-6:
            break
        best, _, cur_f, cur_v = cand_best[0], cand_best[1], cand_best[2], cand_best[3]
        chosen.append(cand_best[1])
        if best >= 0.9995:
            break
    if best >= _MATCH_THRESHOLD and chosen:
        kind = "subset_or" if as_or else "subset_sum"
        return {"kind": kind, "cols": chosen,
                "desc": f"{'OR' if as_or else '합'}({len(chosen)}개 플래그: {', '.join(chosen[:3])}{'…' if len(chosen)>3 else ''})"}
    return None


def _fit_threshold(feat, Rf, tgt_f, Rv, tgt_v, R):
    """이진 타깃 *_flag: 이름 유사 수치 소스의 최적 분할점 학습"""
    tv = _num(tgt_v)
    if not set(_num(tgt_f).dropna().unique()) <= {0.0, 1.0}:
        return None
    tokens = [t for t in re.split(r"[_]", feat.lower()) if len(t) > 3 and t not in ("flag",)]
    srcs = [c for c in R.columns if pd.api.types.is_numeric_dtype(R[c])
            and any(t in c.lower() for t in tokens)][:4]
    for s in srcs:
        vals = _num(Rf[s])
        # 타깃=1 최소값 근방을 후보 분할점으로
        pos_min = _num(Rf[s])[_num(tgt_f) == 1].min()
        cands = [v for v in (pos_min, np.floor(pos_min or 0), round(pos_min or 0, -1)) if pd.notna(v)]
        cands += list(np.nanquantile(vals, [0.5, 0.75, 0.9, 0.95, 0.99]))
        for th in cands:
            for op, fn in ((">=", lambda x, t: (x >= t)), (">", lambda x, t: (x > t))):
                if _match_rate(fn(_num(Rv[s]), th).astype(float), tv) >= _MATCH_THRESHOLD:
                    return {"kind": "threshold", "src": s, "th": float(th), "op": op,
                            "desc": f"{s}{op}{th:g}"}
    return None


def _match_rate(pred: pd.Series, target: pd.Series) -> float:
    p, t = _num(pred), _num(target)
    ok = np.isclose(p.fillna(np.inf), t.fillna(np.inf), rtol=1e-4, atol=1e-6)
    both_nan = p.isna() & t.isna()
    return float((ok | both_nan).mean())


# ══════════════════════════════════════════════════════════

class FeatureBridge:
    def __init__(self):
        self.feature_cols: list[str] = []
        self.strategies: dict[str, dict] = {}    # feat → {"kind","desc",...}
        self.report: dict[str, list] = {}
        self._fn_cache: dict = {}                # 파생 람다 캐시 (pickle 제외)

    def __getstate__(self):
        st = self.__dict__.copy(); st["_fn_cache"] = {}
        return st

    def __setstate__(self, st):
        self.__dict__.update(st); self._fn_cache = {}

    def _resolve_fn(self, feat: str, desc: str, rows: pd.DataFrame):
        """저장된 desc로 파생 공식을 재해석 (로드 후 최초 1회)"""
        fn = self._fn_cache.get(feat)
        if fn is None:
            for d, f in _candidates(feat, rows):
                if d == desc:
                    fn = f; self._fn_cache[feat] = f; break
        return fn

    # ── 학습 ────────────────────────────────────────────
    def fit(self, raw: pd.DataFrame, eng: pd.DataFrame) -> "FeatureBridge":
        eng = eng.drop(columns=[c for c in ("Fraud_Type",) if c in eng.columns])
        eng = eng[[c for c in eng.columns if not str(c).startswith("__index_level_")]]
        self.feature_cols = [str(c) for c in eng.columns]

        common = eng.index.intersection(raw.index)
        if len(common) < 200:
            raise ValueError(f"정렬 가능한 공통 인덱스가 {len(common)}행뿐 — 원본/파생 쌍이 맞는지 확인")
        R, E = raw.loc[common], eng.loc[common]

        # 정렬 자가검증: 양쪽에 있는 수치 identity 후보로 확인
        # 🐛 FIX(v5.9): 프로브는 '양쪽 모두 수치형'인 컬럼만 — 원본이 문자(성별 등)인 컬럼은
        #   인코딩 전후라 정당한 쌍에서도 불일치로 집계되어 오거부를 유발했음 (실데이터에서 발견)
        probes = [c for c in self.feature_cols
                  if c in R.columns
                  and pd.api.types.is_numeric_dtype(R[c])
                  and pd.api.types.is_numeric_dtype(E[c])][:10]
        rates = [_match_rate(R[c], E[c]) for c in probes]
        align = float(np.mean(rates)) if rates else 0.0
        if align < _ALIGN_THRESHOLD:
            raise ValueError(
                f"원본↔파생 정렬 검증 실패(일치율 {align:.1%}) — 이 train.csv와 X 파일은 같은 데이터의 쌍이 아닙니다. "
                f"모델 학습에 쓴 '원본 train.csv'와 그 변환 결과인 X_tr.parquet을 함께 두세요.")
        log.info(f"정렬 검증 통과: {len(common):,}행, 프로브 일치율 {align:.2%}")

        raw_full = raw                                  # 빈도표 후보용 전체 원본
        cut = int(len(common) * 0.8)
        Rf, Ef = R.iloc[:cut], E.iloc[:cut]        # 학습부(매핑 구축)
        Rv, Ev = R.iloc[cut:], E.iloc[cut:]        # 검증부(채택 판정)
        rep = {"identity": [], "lookup": [], "derived": [], "default": []}

        for feat in self.feature_cols:
            tgt_f, tgt_v = Ef[feat], Ev[feat]
            # S1 identity
            if feat in R.columns and _match_rate(Rv[feat], tgt_v) >= _MATCH_THRESHOLD:
                self.strategies[feat] = {"kind": "identity", "desc": "원본 동일"}
                rep["identity"].append(feat); continue
            # S2 lookup (같은 이름 문자 컬럼 or 접두 소스) — *_freq는 전용 전략(S2b)이 전담
            src = feat if feat in R.columns else _lookup_source(feat, R.columns)
            if src is not None and not feat.endswith("_freq"):
                key_f = Rf[src].astype(str)
                # ⚡ v5.9: 변환은 결정적(같은 원본값→같은 파생값)이므로 first로 충분 — IP 등 고카디널리티에서 수백 배 빠름
                lut = tgt_f.groupby(key_f).first().to_dict()
                fallback = float(_num(tgt_f).median())
                pred_v = Rv[src].astype(str).map(lut)
                if _match_rate(pred_v.fillna(fallback), tgt_v) >= _MATCH_THRESHOLD:
                    self.strategies[feat] = {"kind": "lookup", "src": src, "lut": lut,
                                             "fallback": fallback, "desc": f"{src} 값 매핑({len(lut)}종)"}
                    rep["lookup"].append(feat); continue
            # S2b 빈도표 (*_freq): 학습셋 count 매핑 + 미등장→0 (실데이터 tr/va 양쪽 100% 확정)
            if feat.endswith("_freq"):
                src_c = _lookup_source(feat, R.columns)
                if src_c:
                    vc = R[src_c].astype(str).value_counts()
                    pred_v = Rv[src_c].astype(str).map(vc).fillna(0)
                    if _match_rate(pred_v, tgt_v) >= _MATCH_THRESHOLD:
                        self.strategies[feat] = {"kind": "lookup", "src": src_c, "lut": vc.to_dict(),
                                                 "fallback": 0.0, "desc": f"{src_c} 학습셋 count(미등장→0)"}
                        rep["lookup"].append(feat); continue
                    hit = False
                    for norm, dsc in ((True, "freq(normalize)"), (False, "freq(count)")):
                        vc = raw_full[src_c].astype(str).value_counts(normalize=norm) if raw_full is not None else R[src_c].astype(str).value_counts(normalize=norm)
                        pred_v = Rv[src_c].astype(str).map(vc)
                        if _match_rate(pred_v.fillna(vc.min()), tgt_v) >= _MATCH_THRESHOLD:
                            self.strategies[feat] = {"kind": "lookup", "src": src_c, "lut": vc.to_dict(),
                                                     "fallback": float(vc.min()), "desc": f"{src_c} {dsc}"}
                            rep["lookup"].append(feat); hit = True; break
                    if hit: continue
            # S2c 소스 변환 매핑 (예: Location → 시군구 토큰 → 코드)
            for tf_key, (src_c, tf_desc) in _SRC_TRANSFORMS_FOR(feat, R.columns).items():
                key_ser = _apply_src_tf(tf_key, Rf[src_c])
                lut = tgt_f.groupby(key_ser).first().to_dict()
                fb = float(_num(tgt_f).median())
                pred_v = _apply_src_tf(tf_key, Rv[src_c]).map(lut)
                if _match_rate(pred_v.fillna(fb), tgt_v) >= _MATCH_THRESHOLD:
                    self.strategies[feat] = {"kind": "lookup_tf", "src": src_c, "tf": tf_key,
                                             "lut": lut, "fallback": fb, "desc": tf_desc}
                    rep["lookup"].append(feat); break
            if feat in self.strategies: continue
            # S3 derived 후보
            picked, best_r = None, _MATCH_THRESHOLD
            for desc, fn in _candidates(feat, R):
                try:
                    r = _match_rate(fn(Rv), tgt_v)
                except Exception:
                    continue
                if r >= best_r:                     # ✨ 최고 일치율 후보 채택 (동률 시 선순위)
                    if picked is None or r > best_r:
                        picked, best_r = (desc, fn), r
            if picked:
                # fn(람다)은 pickle 불가 → desc만 저장하고 transform 시 _candidates에서 재해석
                self.strategies[feat] = {"kind": "derived", "desc": picked[0]}
                self._fn_cache[feat] = picked[1]
                rep["derived"].append(feat); continue
            # S3b 부분집합 합/OR 탐색 (플래그 조합 카운트·복합 리스크)
            picked2 = _fit_subset(feat, Rf, tgt_f, Rv, tgt_v, R)
            if picked2:
                self.strategies[feat] = picked2
                rep["derived"].append(feat); continue
            # S3c 임계값 학습 (*_flag: 수치 소스의 최적 분할점 탐색)
            picked3 = _fit_threshold(feat, Rf, tgt_f, Rv, tgt_v, R)
            if picked3:
                self.strategies[feat] = picked3
                rep["derived"].append(feat); continue
            # S4 default
            self.strategies[feat] = {"kind": "default", "value": float(_num(E[feat]).median()),
                                     "desc": "중앙값(근사)"}
            rep["default"].append(feat)

        self.report = rep
        log.info(f"FeatureBridge 학습 완료 — identity {len(rep['identity'])} / lookup {len(rep['lookup'])} / "
                 f"derived {len(rep['derived'])} / default {len(rep['default'])} (총 {len(self.feature_cols)})")
        return self

    # ── 변환 ────────────────────────────────────────────
    def transform(self, rows: pd.DataFrame) -> pd.DataFrame:
        out = {}
        for feat in self.feature_cols:
            s = self.strategies[feat]
            if s["kind"] == "identity":
                out[feat] = _num(rows[feat]) if feat in rows.columns else np.nan
            elif s["kind"] == "lookup":
                if s["src"] in rows.columns:
                    out[feat] = rows[s["src"]].astype(str).map(s["lut"]).astype(float).fillna(s["fallback"])
                else:
                    out[feat] = s["fallback"]
            elif s["kind"] == "derived":
                fn = self._resolve_fn(feat, s["desc"], rows)
                try:
                    out[feat] = fn(rows) if fn is not None else np.nan
                except Exception:
                    out[feat] = np.nan
            elif s["kind"] == "lookup_tf":
                if s["src"] in rows.columns:
                    out[feat] = _apply_src_tf(s["tf"], rows[s["src"]]).map(s["lut"]).astype(float).fillna(s["fallback"])
                else:
                    out[feat] = s["fallback"]
            elif s["kind"] in ("subset_sum", "subset_or"):
                tot = sum(_num(rows[c]).fillna(0) for c in s["cols"] if c in rows.columns)
                if isinstance(tot, (int, float)):
                    out[feat] = float(tot > 0) if s["kind"] == "subset_or" else float(tot)
                else:
                    out[feat] = (tot > 0).astype(float) if s["kind"] == "subset_or" else tot
            elif s["kind"] == "batch_count":
                if s["src"] in rows.columns:
                    v = rows[s["src"]].astype(str)
                    out[feat] = v.map(v.value_counts()).astype(float)   # 배치 내 count (팀 분할별 fit_transform 재현)
                else:
                    out[feat] = 1.0
            elif s["kind"] == "threshold":
                x = _num(rows[s["src"]]) if s["src"] in rows.columns else pd.Series(np.nan, index=rows.index)
                out[feat] = ((x >= s["th"]) if s["op"] == ">=" else (x > s["th"])).astype(float)
            else:
                out[feat] = s["value"]
        return pd.DataFrame(out, index=rows.index)[self.feature_cols]

    def transform_row(self, row: dict) -> pd.DataFrame:
        return self.transform(pd.DataFrame([{k: v for k, v in row.items() if not str(k).startswith("_")}]))

    # ── 저장/로드 ────────────────────────────────────────
    def save(self, path: str | Path = "models/feature_bridge.pkl"):
        with open(path, "wb") as f:
            pickle.dump(self, f)
        log.info(f"저장: {path}")

    @staticmethod
    def load(path: str | Path = "models/feature_bridge.pkl") -> "FeatureBridge":
        with open(path, "rb") as f:
            return pickle.load(f)

    def summary(self) -> str:
        r = self.report
        lines = [f"FeatureBridge — 총 {len(self.feature_cols)}피처: "
                 f"원본동일 {len(r['identity'])} · 매핑 {len(r['lookup'])} · 공식복원 {len(r['derived'])} · 근사 {len(r['default'])}"]
        if r["default"]:
            lines.append(f"  ⚠ 근사(중앙값) 처리: {', '.join(r['default'][:8])}{'…' if len(r['default'])>8 else ''}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════
# 세션 5 호환 분류기 (원본 row → 브리지 → 파생 모델)
# ══════════════════════════════════════════════════════════

class BridgedClassifier:
    """MLClassifier.predict(row) 인터페이스 — 원본 행을 브리지로 변환해 파생 모델로 예측"""

    def __init__(self, model_spec, bridge: FeatureBridge):
        from pipeline.model_loader import load_model
        self.um = load_model(model_spec)
        self.bridge = bridge

    def predict(self, row: dict) -> tuple[str, float, dict]:
        X = self.bridge.transform_row(row).fillna(0)
        proba = np.asarray(self.um.predict_proba(X))[0]
        cls = [str(c) for c in self.um.classes_]
        pd_ = {c: float(p) for c, p in zip(cls, proba)}
        risk = float(1 - pd_.get("m", 0.0)) if "m" in pd_ else float(proba.max())
        if hasattr(self.um, "_predict_labels"):
            ft = str(self.um._predict_labels(X)[0])
        else:
            ft = cls[int(np.argmax(proba))]
        return ft, risk, pd_


def make_bridged_classifier(model_spec, bridge_path="models/feature_bridge.pkl") -> BridgedClassifier:
    return BridgedClassifier(model_spec, FeatureBridge.load(bridge_path))


def fit_bridge_from_files(train_csv="data/train.csv", x_parquet="data/X_tr.parquet",
                          save_to="models/feature_bridge.pkl") -> FeatureBridge:
    raw = pd.read_csv(train_csv)
    eng = pd.read_parquet(x_parquet)
    br = FeatureBridge().fit(raw, eng)
    if save_to:
        br.save(save_to)
    return br


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    a = sys.argv[1:] + ["data/train.csv", "data/X_tr.parquet"][len(sys.argv) - 1:]
    br = fit_bridge_from_files(a[0], a[1])
    print(br.summary())

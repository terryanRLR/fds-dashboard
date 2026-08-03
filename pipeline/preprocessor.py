"""
Preprocessor — 원본 거래 행 → 배포 번들 58피처 결정론적 변환기  ✨ v10 신규

배경
  팀에서 받은 배포 번들(lgbm_13class(최종).pkl)은 `X_tr.parquet`과 동일한
  **58개 파생/인코딩 완료 피처**를 입력으로 받는다. 전처리 *코드*는 받지 못했고
  산출물(X/y parquet)만 있었으므로, 이 모듈은 X_tr 96,140행 전수 대조로
  **역산·검증이 끝난 공식**을 결정론적으로 이식한다.

  기존 feature_bridge.py는 "추측하되 검증 없이는 채택하지 않는다"는 역학습기다.
  하지만 팀이 넘긴 X_tr은 셔플 + reset_index 상태여서 원본과 행 정렬이 불가능해
  fit() 자체가 (정당하게) 거부된다. 대신 공식이 전부 밝혀졌으므로
  **추측이 필요 없는 확정 변환**으로 대체한다 — 정확도 100%.

검증 근거 (X_tr 96,140행 전수, 일치율 100.0000%)
  Transaction_Amount_abs           = |Transaction_Amount|
  Transaction_is_withdrawal        = (Transaction_Amount < 0)
  Time_difference_seconds          = to_timedelta(Time_difference).total_seconds()
  Transaction_Hour                 = Transaction_Datetime.dt.hour
  Location_region                  = 시도명 → 정렬 인덱스 (강원도=0 … 충청북도=16)
  Amount_vs_daily_limit            = |amt| / Account_amount_daily_limit
  Amount_vs_monthly_max_ratio      = |amt| / Account_one_month_max_amount
  Amount_vs_remaining_balance      = |amt| / max(Account_balance + 1, 1)
      ↑ 위 세 비율은 모두 ±inf → NaN 으로 치환 (분모 0 → 0/0)
  unused_terminal_and_internet     = Unused_terminal_status & (Channel == internet)
  limit_check_then_transfer        = inquery_atm_limit & increase_atm_limit & (Channel == internet)
  large_deposit_and_remote_control = Flag_deposit_more_than_tenMillion
                                     & Customer_flag_terminal_malicious_behavior_2

⚠️ NaN 정책
  Amount_vs_monthly_max_ratio 는 실데이터에서 NaN이 다수 발생한다(X_va 2,195건).
  LightGBM은 NaN을 native 분기로 처리하므로 **절대 채우지 않는다.**
  (채우면 macro F1 0.6138 → 0.6070 으로 떨어짐 — 실측 확인)

핵심 API
  Preprocessor.from_bundle("models/")        → 번들 메타로 인스턴스 생성
  .transform(raw_df)                         → (n, 58) DataFrame
  .transform_row(row_dict)                   → (1, 58) DataFrame
  .learn_from_pair(raw_df, eng_df)           → 원본↔산출물로 매핑 자가검증·교정
  .report()                                  → 사람이 읽는 변환 요약
  RawRowClassifier(model, prep)               → MLClassifier.predict(row) 호환 어댑터
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

PREPROCESSOR_VERSION = "v10 (확정 공식 · X_tr 전수 검증)"

# ══════════════════════════════════════════════════════════
# 범주형 문자열 → 정수 코드
#   sklearn LabelEncoder는 unique 값을 sorted() 순으로 0..N-1에 배정한다.
#   ASCII에서 대문자 < 소문자이므로 'ATM' < 'Others' < 'internet' < 'mobile'.
#   9개 컬럼 전부 번들 label_encoders.pkl의 클래스 수와 일치함을 확인했고,
#   Channel('internet'→2) · Customer_Gender('male'→1) 은 원본↔X_va 대조로 실측 검증됨.
# ══════════════════════════════════════════════════════════
CAT_LEVELS = {
    "Customer_Gender":        ["female", "male"],
    "Customer_credit_rating": ["A", "B", "C", "D", "E", "S"],
    "Customer_loan_type":     ["a", "b", "c", "d", "e"],
    "Account_account_type":   ["a", "b", "c", "d"],
    "Channel":                ["ATM", "Others", "internet", "mobile"],
    "Operating_System":       ["Android", "Linux", "Others", "Windows", "iOS", "macOS"],
    "Error_Code":             ["a", "c"],
    "Type_General_Automatic": ["automatic", "general"],
    "Access_Medium":          ["a", "b", "c", "d", "e", "f", "g"],
}
CAT_MAPS_DEFAULT = {c: {v: i for i, v in enumerate(sorted(levels))}
                    for c, levels in CAT_LEVELS.items()}

# Channel 코드 중 'internet' — 복합 플래그 공식이 참조한다 (실측: 2)
_INTERNET_CODE = CAT_MAPS_DEFAULT["Channel"]["internet"]

# 17개 광역시도 → 정렬 인덱스. 강원도=0 · 경상북도=3 은 원본↔X_va 대조로 실측 검증됨.
SIDO_LEVELS = [
    "강원도", "경기도", "경상남도", "경상북도", "광주광역시", "대구광역시", "대전광역시",
    "부산광역시", "서울특별시", "세종특별자치시", "울산광역시", "인천광역시",
    "전라남도", "전라북도", "제주특별자치도", "충청남도", "충청북도",
]
REGION_MAP_DEFAULT = {v: i for i, v in enumerate(sorted(SIDO_LEVELS))}
# 개편 명칭 별칭 (2023 강원특별자치도, 2024 전북특별자치도 등) → 기존 코드로 흡수
REGION_ALIASES = {
    "강원특별자치도": "강원도",
    "전북특별자치도": "전라북도",
    "전라북도특별자치도": "전라북도",
    "제주도": "제주특별자치도",
    "세종시": "세종특별자치시",
}


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _inf2nan(s) -> pd.Series:
    """±inf → NaN. 팀 전처리가 0/0 결과를 NaN으로 남긴 것을 재현한다."""
    return pd.Series(s).replace([np.inf, -np.inf], np.nan)


def _flag(s) -> pd.Series:
    """1/'1'/True/1.0 → 1.0, 그 외 → 0.0"""
    return (_num(s).fillna(0) == 1).astype(float)


class Preprocessor:
    """원본 행 → 58피처. 결측 피처는 feature_defaults.json 값으로 채우되,
    **계산 결과로 나온 NaN은 보존한다**(LightGBM native 처리)."""

    def __init__(self, feature_cols: list[str], defaults: dict | None = None,
                 cat_maps: dict | None = None, region_map: dict | None = None):
        self.feature_cols = [str(c) for c in feature_cols]
        self.defaults = dict(defaults or {})
        self.cat_maps = {k: dict(v) for k, v in (cat_maps or CAT_MAPS_DEFAULT).items()}
        self.region_map = dict(region_map or REGION_MAP_DEFAULT)
        self.learned: dict[str, str] = {}   # learn_from_pair가 교정한 항목 기록
        self._notes: list[str] = []

    # ── 생성 ────────────────────────────────────────────
    @classmethod
    def from_bundle(cls, model_dir: str | Path = "models/") -> "Preprocessor":
        d = Path(model_dir)
        fc_path, fd_path = d / "feature_cols.json", d / "feature_defaults.json"
        if not fc_path.exists():
            raise FileNotFoundError(f"feature_cols.json 없음: {fc_path}")
        with open(fc_path, encoding="utf-8") as f:
            feature_cols = json.load(f)
        defaults = {}
        if fd_path.exists():
            with open(fd_path, encoding="utf-8") as f:
                defaults = json.load(f)
        else:
            log.warning(f"feature_defaults.json 없음({fd_path}) → 결측 피처는 0으로 대체")
        log.info(f"Preprocessor {PREPROCESSOR_VERSION} — {len(feature_cols)}피처 로드")
        return cls(feature_cols, defaults)

    # ── 파생 공식 ───────────────────────────────────────
    def _derive(self, raw: pd.DataFrame) -> dict:
        """원본 컬럼으로 계산 가능한 파생 피처를 dict[str, Series]로 반환.
        원본 컬럼이 없어 계산 불가한 항목은 아예 넣지 않는다(→ 기본값으로 처리)."""
        out: dict = {}
        has = lambda *cs: all(c in raw.columns for c in cs)
        idx = raw.index

        # ── 금액 계열 ──
        if has("Transaction_Amount"):
            amt = _num(raw["Transaction_Amount"])
            A = amt.abs()
            out["Transaction_Amount_abs"] = A
            out["Transaction_is_withdrawal"] = (amt < 0).astype(float)
        else:
            A = _num(raw["Transaction_Amount_abs"]) if "Transaction_Amount_abs" in raw.columns else None

        if A is not None:
            if has("Account_amount_daily_limit"):
                out["Amount_vs_daily_limit"] = _inf2nan(A / _num(raw["Account_amount_daily_limit"]))
            if has("Account_one_month_max_amount"):
                out["Amount_vs_monthly_max_ratio"] = _inf2nan(A / _num(raw["Account_one_month_max_amount"]))
            if has("Account_balance"):
                out["Amount_vs_remaining_balance"] = _inf2nan(
                    A / (_num(raw["Account_balance"]) + 1).clip(lower=1))

        # ── 시간 계열 ──
        if has("Transaction_Datetime"):
            out["Transaction_Hour"] = pd.to_datetime(
                raw["Transaction_Datetime"], errors="coerce").dt.hour.astype(float)
        if has("Time_difference"):
            out["Time_difference_seconds"] = pd.to_timedelta(
                raw["Time_difference"], errors="coerce").dt.total_seconds()

        # ── 위치 ──
        if has("Location"):
            out["Location_region"] = self._encode_region(raw["Location"])

        # ── 복합 플래그 (Channel은 코드 또는 원문 문자열 양쪽 허용) ──
        ch_is_internet = self._channel_is_internet(raw, idx)
        if has("Unused_terminal_status") and ch_is_internet is not None:
            out["unused_terminal_and_internet"] = (
                (_flag(raw["Unused_terminal_status"]) == 1) & ch_is_internet).astype(float)
        if has("Customer_inquery_atm_limit", "Customer_increase_atm_limit") and ch_is_internet is not None:
            out["limit_check_then_transfer"] = (
                (_flag(raw["Customer_inquery_atm_limit"]) == 1)
                & (_flag(raw["Customer_increase_atm_limit"]) == 1)
                & ch_is_internet).astype(float)
        if has("Flag_deposit_more_than_tenMillion", "Customer_flag_terminal_malicious_behavior_2"):
            out["large_deposit_and_remote_control"] = (
                (_flag(raw["Flag_deposit_more_than_tenMillion"]) == 1)
                & (_flag(raw["Customer_flag_terminal_malicious_behavior_2"]) == 1)).astype(float)
        return out

    def _channel_is_internet(self, raw: pd.DataFrame, idx) -> pd.Series | None:
        if "Channel" not in raw.columns:
            return None
        s = raw["Channel"]
        if pd.api.types.is_numeric_dtype(s):
            return _num(s) == _INTERNET_CODE
        txt = s.astype(str).str.strip()
        # 문자열이 코드 문자("2")로 들어온 경우도 흡수
        as_num = pd.to_numeric(txt, errors="coerce")
        return ((txt.str.lower() == "internet") | (as_num == _INTERNET_CODE)).fillna(False)

    def _encode_region(self, loc: pd.Series) -> pd.Series:
        """'강원도 고성군 죽왕면 38.35 128.50' → 첫 토큰(시도) → 코드."""
        sido = loc.astype(str).str.strip().str.split().str[0]
        sido = sido.replace(REGION_ALIASES)
        code = sido.map(self.region_map)
        n_miss = int(code.isna().sum())
        if n_miss:
            unknown = sorted(set(sido[code.isna()].dropna().unique()))[:4]
            log.warning(f"Location_region 미등록 시도 {n_miss}건 {unknown} → 기본값 대체")
        return code.astype(float)

    # ── 변환 ────────────────────────────────────────────
    def transform(self, raw: pd.DataFrame) -> pd.DataFrame:
        """원본 DataFrame → (n, len(feature_cols)) DataFrame.
        컬럼 순서는 feature_cols와 정확히 일치하며, 계산상 NaN은 그대로 보존된다."""
        raw = raw.copy()
        raw = raw[[c for c in raw.columns if not str(c).startswith(("_", "__index_level_"))]]
        derived = self._derive(raw)
        self._notes = []

        out: dict = {}
        n = len(raw)
        for col in self.feature_cols:
            if col in derived:                          # ① 파생 공식으로 계산됨
                out[col] = _num(derived[col])
            elif col in raw.columns:                    # ② 원본에 동일 이름 존재
                s = raw[col]
                if col in self.cat_maps and not pd.api.types.is_numeric_dtype(s):
                    mapped = s.astype(str).str.strip().map(self.cat_maps[col])
                    if mapped.isna().any():             # 미등록 범주 → 코드 문자 재시도 → 기본값
                        mapped = mapped.fillna(pd.to_numeric(s, errors="coerce"))
                    out[col] = _num(mapped)
                else:
                    out[col] = _num(s)
            else:                                       # ③ 없음 → 기본값
                out[col] = pd.Series([self._default_of(col)] * n, index=raw.index, dtype=float)
                self._notes.append(col)

        df = pd.DataFrame(out, index=raw.index)[self.feature_cols]
        # ✅ '컬럼 부재'로 채운 자리만 기본값 보정. 계산 결과 NaN은 손대지 않는다.
        for col in self._notes:
            df[col] = df[col].fillna(self._default_of(col))
        # 범주형은 정수 코드여야 하므로, 매핑 실패분만 기본값으로 메운다
        for col in self.cat_maps:
            if col in df.columns and df[col].isna().any():
                df[col] = df[col].fillna(self._default_of(col))
        if "Location_region" in df.columns and df["Location_region"].isna().any():
            df["Location_region"] = df["Location_region"].fillna(self._default_of("Location_region"))
        if self._notes:
            log.info(f"원본에 없어 기본값으로 채운 피처 {len(self._notes)}개: "
                     f"{self._notes[:6]}{'…' if len(self._notes) > 6 else ''}")
        return df

    def transform_row(self, row: dict) -> pd.DataFrame:
        clean = {k: v for k, v in row.items() if not str(k).startswith("_")}
        return self.transform(pd.DataFrame([clean]))

    def _default_of(self, col: str) -> float:
        try:
            return float(self.defaults.get(col, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    # ── 자가검증 · 자동 교정 ────────────────────────────
    def learn_from_pair(self, raw: pd.DataFrame, eng: pd.DataFrame,
                        join_keys=("Customer_Birthyear", "Account_balance",
                                   "Account_initial_balance")) -> dict:
        """원본 CSV와 산출물 X를 받아 매핑을 검증·교정한다.

        팀의 X는 셔플 + reset_index 상태라 인덱스 정렬이 불가능하므로,
        **고카디널리티 identity 컬럼 조인**으로 행 대응을 복구한다(검증된 기법).
        범주형/시도 매핑이 sorted() 가정과 다르면 실제 데이터 기준으로 덮어쓴다.

        반환: {피처명: '일치율 %'} 리포트
        """
        keys = [k for k in join_keys if k in raw.columns and k in eng.columns]
        if not keys:
            raise ValueError(f"조인 키를 찾을 수 없습니다 (후보: {join_keys})")
        r = raw.copy(); e = eng.copy()
        r["__rk"] = list(map(tuple, r[keys].to_numpy()))
        e["__rk"] = list(map(tuple, e[keys].to_numpy()))
        e_uniq = e.drop_duplicates("__rk", keep="first").set_index("__rk")
        common = [k for k in r["__rk"] if k in e_uniq.index]
        if len(common) < 2:
            raise ValueError(f"조인된 행이 {len(common)}건뿐 — 원본/산출물 쌍이 맞는지 확인하세요")
        R = r[r["__rk"].isin(e_uniq.index)].drop_duplicates("__rk", keep="first")
        E = e_uniq.loc[R["__rk"]]
        R = R.reset_index(drop=True); E = E.reset_index(drop=True)
        log.info(f"learn_from_pair: {len(R):,}행 정렬 성공 (조인 키 {keys})")

        # ① 범주형 · 시도 매핑을 실제 대응에서 재학습
        for col, cur in list(self.cat_maps.items()):
            if col in R.columns and col in E.columns and not pd.api.types.is_numeric_dtype(R[col]):
                obs = (pd.DataFrame({"k": R[col].astype(str).str.strip(),
                                     "v": _num(E[col])}).dropna()
                       .groupby("k")["v"].agg(lambda x: x.mode().iloc[0]).to_dict())
                obs = {k: int(v) for k, v in obs.items()}
                if obs and obs != {k: cur.get(k) for k in obs}:
                    self.cat_maps[col] = {**cur, **obs}
                    self.learned[col] = f"데이터에서 재학습 ({len(obs)}종)"
                    log.info(f"  ↻ {col} 매핑 교정: {obs}")
        if "Location" in R.columns and "Location_region" in E.columns:
            sido = R["Location"].astype(str).str.strip().str.split().str[0].replace(REGION_ALIASES)
            obs = (pd.DataFrame({"k": sido, "v": _num(E["Location_region"])}).dropna()
                   .groupby("k")["v"].agg(lambda x: x.mode().iloc[0]).to_dict())
            obs = {k: int(v) for k, v in obs.items()}
            diff = {k: v for k, v in obs.items() if self.region_map.get(k) != v}
            self.region_map.update(obs)
            if diff:
                self.learned["Location_region"] = f"{len(diff)}개 시도 코드 교정"
                log.warning(f"  ↻ 시도 코드 교정: {diff}")
            else:
                self.learned["Location_region"] = f"{len(obs)}개 시도 확인 (가정과 일치)"

        # ② 전체 재변환 후 피처별 일치율 산출
        got = self.transform(R)
        report = {}
        for col in self.feature_cols:
            if col not in E.columns:
                continue
            a, b = got[col].to_numpy(float), _num(E[col]).to_numpy(float)
            ok = np.isclose(a, b, rtol=1e-6, atol=1e-9) | (np.isnan(a) & np.isnan(b))
            report[col] = round(float(ok.mean()) * 100, 4)
        bad = {k: v for k, v in report.items() if v < 99.9}
        if bad:
            log.warning(f"일치율 99.9% 미만 피처 {len(bad)}개: "
                        + ", ".join(f"{k} {v}%" for k, v in sorted(bad.items(), key=lambda x: x[1])[:6]))
        else:
            log.info(f"✅ {len(report)}개 피처 전부 99.9% 이상 일치 — 변환 규칙 확정")
        self.last_report = report
        return report

    # ── 요약 ────────────────────────────────────────────
    def report(self) -> str:
        derived = [c for c in self.feature_cols
                   if c in ("Transaction_Amount_abs", "Transaction_is_withdrawal",
                            "Time_difference_seconds", "Transaction_Hour", "Location_region",
                            "Amount_vs_daily_limit", "Amount_vs_monthly_max_ratio",
                            "Amount_vs_remaining_balance", "unused_terminal_and_internet",
                            "limit_check_then_transfer", "large_deposit_and_remote_control")]
        lines = [f"Preprocessor {PREPROCESSOR_VERSION} — 총 {len(self.feature_cols)}피처: "
                 f"원본 통과 {len(self.feature_cols) - len(derived)} · 파생 공식 {len(derived)}"]
        lines.append(f"  범주형 인코딩 {len(self.cat_maps)}종 · 시도 코드 {len(self.region_map)}종")
        if self.learned:
            lines.append("  ↻ 데이터 재학습: " + " / ".join(f"{k}({v})" for k, v in self.learned.items()))
        if self._notes:
            lines.append(f"  ⚠ 마지막 변환에서 기본값으로 채운 피처 {len(self._notes)}개: "
                         f"{', '.join(self._notes[:8])}{'…' if len(self._notes) > 8 else ''}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════
# 세션 5 호환 어댑터 — MLClassifier.predict(row) 인터페이스
# ══════════════════════════════════════════════════════════

class RawRowClassifier:
    """원본 행(dict) → Preprocessor → 58피처 모델 예측.

    MLClassifier와 동일한 (fraud_type, risk_score, proba_dict)를 반환하므로
    세션 5의 5가지 입력 경로·배치 분석기에 그대로 꽂을 수 있다.
    """

    def __init__(self, model, prep: Preprocessor, classes=None, normal_label: str = "m"):
        self.model = model
        self.prep = prep
        self.normal_label = normal_label
        self.classes_ = [str(c) for c in (classes if classes is not None
                                          else getattr(model, "classes_", []))]
        self.feature_cols = prep.feature_cols

    @classmethod
    def from_bundle(cls, model_dir: str | Path = "models/", model_path=None) -> "RawRowClassifier":
        from pathlib import Path as _P
        try:
            from pipeline.bundle_io import safe_load, resolve_model_path, load_model_meta
        except ImportError:
            from bundle_io import safe_load, resolve_model_path, load_model_meta
        d = _P(model_dir)
        mp = resolve_model_path(d, model_path)
        if mp is None:
            raise FileNotFoundError(f"베이스 모델을 찾지 못했습니다: {d}")
        model = safe_load(mp)
        meta = load_model_meta(d)
        classes = meta.get("labels")
        if not classes:
            lt = d / "le_target.pkl"
            if lt.exists():
                classes = [str(c) for c in safe_load(lt).classes_]
        prep = Preprocessor.from_bundle(d)
        log.info(f"RawRowClassifier 준비 — 모델 {mp.name} · {len(prep.feature_cols)}피처 "
                 f"· {len(classes or [])}클래스")
        return cls(model, prep, classes, meta.get("normal_label", "m"))

    def predict(self, row: dict) -> tuple[str, float, dict]:
        X = self.prep.transform_row(row)
        proba = np.asarray(self.model.predict_proba(X))[0]
        cls = self.classes_ or [str(i) for i in range(len(proba))]
        proba_dict = {c: float(p) for c, p in zip(cls, proba)}
        m_prob = proba_dict.get(self.normal_label)
        risk = float(1 - m_prob) if m_prob is not None else float(proba.max())
        return str(cls[int(np.argmax(proba))]), risk, proba_dict

    def predict_batch(self, rows: list[dict]) -> list[tuple]:
        """⚡ 배치는 행별 루프 대신 한 번에 변환·추론 (수백 배 빠름)."""
        if not rows:
            return []
        clean = [{k: v for k, v in r.items() if not str(k).startswith("_")} for r in rows]
        X = self.prep.transform(pd.DataFrame(clean))
        P = np.asarray(self.model.predict_proba(X))
        cls = self.classes_ or [str(i) for i in range(P.shape[1])]
        mi = cls.index(self.normal_label) if self.normal_label in cls else None
        out = []
        for p in P:
            pd_ = {c: float(v) for c, v in zip(cls, p)}
            risk = float(1 - p[mi]) if mi is not None else float(p.max())
            out.append((str(cls[int(np.argmax(p))]), risk, pd_))
        return out

    def get_feature_info(self) -> dict:
        return {"feature_cols": self.feature_cols,
                "cat_cols": sorted(self.prep.cat_maps),
                "cat_options": {c: sorted(m, key=m.get) for c, m in self.prep.cat_maps.items()},
                "defaults": self.prep.defaults,
                "drop_cols": []}


def make_raw_classifier(model_dir="models/", model_path=None) -> RawRowClassifier:
    return RawRowClassifier.from_bundle(model_dir, model_path)


if __name__ == "__main__":   # 자가검증 CLI:  python -m pipeline.preprocessor <train.csv> <X.parquet>
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = sys.argv[1:]
    prep = Preprocessor.from_bundle("models/")
    if len(args) >= 2:
        rep = prep.learn_from_pair(pd.read_csv(args[0]), pd.read_parquet(args[1]))
        worst = sorted(rep.items(), key=lambda x: x[1])[:5]
        print(f"검증 피처 {len(rep)}개 · 최저 일치율: " + ", ".join(f"{k} {v}%" for k, v in worst))
    print(prep.report())

"""
Evaluator — 선택한 (모델 × 데이터셋) 조합으로 세션 2·3 지표를 실계산 (신규)

기존 세션 2는 models/eval_result.json(학습 시점 고정값)을,
임계값 기대비용 곡선은 하드코딩 더미 공식을 사용했음.
→ 이 모듈은 대시보드에서 고른 데이터셋과 모델로 동일 구조의 dict를
  즉석 생성하여, 기존 렌더링 코드를 최소 수정으로 재사용할 수 있게 한다.

핵심 API
  evaluate(models: dict[표시명, UnifiedModel], df, preprocess_fn)
      → eval_result.json 과 동일 스키마의 dict
  threshold_cost_curve(risk_scores, y_true, fn_cost, fp_cost)
      → 실측 기반 임계값-기대비용 곡선 (더미 공식 대체)
  segment_stats(df, seg_col) / amount_band_stats(df) / flag_on_ratio(df, flags)
      → 세션 3 그래프용 집계 (선택 데이터셋 반영)
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score, precision_score, recall_score

log = logging.getLogger(__name__)

CLASS_ORDER = list("abcdefghijklm")


def _auto_prep_for_model(um, raw_df, defaults, bridge, mlclf_path):
    """✨ v6.2: 모델별 최적 프렙 자동 선택 — train.csv 하나로 48/81피처 모델 동시 평가.
      1) 기대 피처 전부 존재 → passthrough
      2) 소량 누락(≤20%) → 피처 매칭 + 기본값 대체
      3) 대량 누락 + 브리지 → 브리지 변환 후 피처 매칭
      4) 대량 누락 + 브리지 없음 → MLClassifier 전처리 후 피처 매칭"""
    from pipeline.model_loader import get_expected_features
    exp = get_expected_features(um)
    if exp is None:
        # 피처명 없는 모델(ONNX 등): 문자열 컬럼이 있으면 MLClassifier 전처리 필수
        _has_str = any(not pd.api.types.is_numeric_dtype(raw_df[c]) for c in raw_df.columns)
        if not _has_str:
            return raw_df, ""
        # 브리지 또는 MLClassifier 경유
        if bridge is not None:
            try:
                X_b = bridge.transform(raw_df).fillna(0)
                return X_b, "🌉 브리지(피처명 없는 모델)"
            except Exception: pass
        try:
            from pipeline.ml_classifier import MLClassifier
            clf = MLClassifier(mlclf_path)
            X_c = make_batch_preprocess(clf)(raw_df)
            return X_c, "MLClassifier(피처명 없는 모델)"
        except Exception: pass
        return raw_df, ""
    cols = set(raw_df.columns)
    missing = [c for c in exp if c not in cols]
    # 🐛 FIX(v6.3): 원본 데이터(문자열 컬럼 보유)를 passthrough하면 모델이 크래시 →
    #   문자열이 있으면 passthrough 금지, 반드시 인코딩 경로(브리지 or MLClassifier)를 거쳐야 함
    _has_strings = any(not pd.api.types.is_numeric_dtype(raw_df[c]) for c in exp if c in cols)
    if not missing and not _has_strings:
        return raw_df[exp], "passthrough"
    if not _has_strings and len(missing) <= max(3, int(len(exp) * 0.2)):
        return _adapt_features(um, raw_df, defaults)
    # 브리지 변환 (81피처 파생 + 문자열 인코딩 동시 처리)
    if bridge is not None:
        try:
            X_b = bridge.transform(raw_df).fillna(0)
            X_m, note = _adapt_features(um, X_b, defaults)
            return X_m, f"🌉 브리지 · {note}" if note else "🌉 브리지"
        except Exception as e:
            log.warning(f"브리지 변환 실패({e})")
    # MLClassifier 전처리
    try:
        from pipeline.ml_classifier import MLClassifier
        clf = MLClassifier(mlclf_path)
        prep = make_batch_preprocess(clf)
        X_c = prep(raw_df)
        X_m, note = _adapt_features(um, X_c, defaults)
        return X_m, f"MLClassifier · {note}" if note else "MLClassifier"
    except Exception:
        pass
    raise ValueError(f"피처 {len(missing)}/{len(exp)}개 없음 — 브리지/전처리 실패")


def _load_feature_defaults() -> dict:
    """models/feature_defaults.json 탐색 — 누락 피처 대체값 (v5.4)"""
    import json
    from pathlib import Path
    for cand in (Path("models/feature_defaults.json"),
                 Path(__file__).resolve().parent.parent / "models" / "feature_defaults.json"):
        if cand.exists():
            try:
                with open(cand, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def _adapt_features(um, X_full: pd.DataFrame, defaults: dict) -> tuple[pd.DataFrame, str]:
    """✨ v5.4 자동 피처 매칭 — 팀 실사용 오류 대응
       · 'number of features (81) != training (48)' / 'feature names should match'
       → 모델이 기억하는 피처명으로 데이터셋 컬럼을 이름 기준 선택·재정렬.
         데이터셋에 없는 피처는 feature_defaults.json 값(없으면 0)으로 채움."""
    from pipeline.model_loader import get_expected_features
    names = get_expected_features(um)
    if names is None:
        n_exp = getattr(um, "_n_features", None)           # ONNX 등 이름 없는 형식
        if n_exp and n_exp != X_full.shape[1]:
            raise ValueError(
                f"모델은 {n_exp}피처를 기대하지만 데이터셋은 {X_full.shape[1]}피처입니다. "
                f"피처명이 없는 형식(ONNX 등)은 자동 매칭이 불가하니 학습 피처와 동일한 데이터셋을 선택하세요."
            )
        return X_full, ""

    missing = [n for n in names if n not in X_full.columns]
    if not missing:
        X = X_full[names]
        note = "" if list(X_full.columns) == names else f"피처 {len(names)}개 이름 매칭(재정렬)"
        return X, note

    if len(missing) > max(3, int(len(names) * 0.2)):       # 과도한 누락 = 다른 계열 데이터셋
        raise ValueError(
            f"모델 피처 {len(names)}개 중 {len(missing)}개가 데이터셋에 없습니다"
            f"(예: {missing[:4]}) — 데이터셋·모델 계열이 다릅니다."
        )
    X = X_full.copy()
    for n in missing:
        v = defaults.get(n, 0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        X[n] = v
    note = f"누락 피처 {len(missing)}개 기본값 대체({', '.join(missing[:3])}{'…' if len(missing)>3 else ''})"
    return X[names], note


# ══════════════════════════════════════════════════════════
# 세션 2 — 모델 비교 · 클래스 리포트 · 혼동 행렬
# ══════════════════════════════════════════════════════════

def evaluate(
    models: dict,                 # {표시명: UnifiedModel}
    df: pd.DataFrame,             # Fraud_Type 라벨 포함 데이터셋
    preprocess_fn=None,           # None이면 모델별 자동 프렙 (v6.2)
    max_rows: int = 5000,         # 대시보드 반응성 확보용 샘플 상한
    bridge=None,                  # FeatureBridge 인스턴스 (자동 프렙용)
    mlclf_path: str = "models/lgbm_fds.pkl",  # MLClassifier 폴백 경로
    seed: int = 42,
) -> dict:
    if "Fraud_Type" not in df.columns:
        raise ValueError("선택한 데이터셋에 Fraud_Type(라벨) 컬럼이 없습니다 — 라벨 포함 데이터셋을 선택하세요")

    sampling_note = ""
    # ✨ v6.1: 표본→모집단 보정 가중치 — 비용 분석에서 오탐(FP)이 표본 크기만큼 과소집계되는 것 방지
    _n_fraud_total  = int((df["Fraud_Type"].astype(str) != "m").sum())
    _n_normal_total = int(len(df) - _n_fraud_total)
    fraud_weight, normal_weight = 1.0, 1.0
    if max_rows and len(df) > max_rows:   # ✨ v6.2: None/0 = 전체 평가 허용
        # ✨ v5.8 층화 표본: 무작위 샘플은 0.8% 사기가 수십 건만 남아 macro-F1이 불안정.
        #   → 사기(비'm') 전량 보존 + 정상('m')만 잔여 예산으로 샘플링.
        fraud_df  = df[df["Fraud_Type"].astype(str) != "m"]
        normal_df = df[df["Fraud_Type"].astype(str) == "m"]
        if len(fraud_df) < max_rows:
            n_norm = max_rows - len(fraud_df)
            _n_norm_samp = min(n_norm, len(normal_df))
            df = pd.concat([fraud_df, normal_df.sample(_n_norm_samp, random_state=seed)])
            normal_weight = _n_normal_total / max(_n_norm_samp, 1)
            sampling_note = f"층화 표본 — 사기 {len(fraud_df):,}건 전량 + 정상 {_n_norm_samp:,}건"
        else:
            _ratio = len(df) / max_rows
            fraud_weight = normal_weight = _ratio
            df = df.sample(max_rows, random_state=seed)
            sampling_note = "무작위 표본(사기 건수가 상한 초과)"
        df = df.sample(frac=1, random_state=seed)      # 순서 셔플
    y_true = df["Fraud_Type"].astype(str).to_numpy()
    _raw_df = df.drop(columns=["Fraud_Type"], errors="ignore")
    if preprocess_fn is not None:
        X = preprocess_fn(df)
    else:
        X = _raw_df     # per-model 분기에서 처리

    # 🐛 FIX(v5.1): 샘플에 없는 클래스도 0행으로 유지 — 13×13 혼동행렬 고정 보장
    #   (기존: 표본에 존재하는 클래스만 → 11×11 등으로 축소되어 대시보드 축 라벨과 어긋남)
    class_order = list(CLASS_ORDER)

    result = {
        "model_comparison": {},
        "best_model": None,
        "class_order": class_order,
        "classification_report": {},
        "sampling": {"fraud_weight": round(fraud_weight, 4), "normal_weight": round(normal_weight, 4),
                     "n_fraud_total": _n_fraud_total, "n_normal_total": _n_normal_total},
        "confusion_matrix": [],
        "eval_size": int(len(df)),
        # 🐛 FIX(v6.1): 표본 셔플 후의 '진짜' 라벨 순서를 동봉 — 대시보드가 head()로 재구성하면
        #   risk 배열과 어긋나 비용곡선/임계값 재계산이 오염되던 문제의 근본 수정
        "y_true_cache": y_true.tolist(),
        "sampling_note": sampling_note,
        # ✨ v5.8 소표본 신뢰도: 표본 10건 미만 클래스는 지표 신뢰 불가 → UI 경고용
        "low_support": sorted(
            c for c in class_order
            if 0 < int((y_true == c).sum()) < 10
        ),
        "absent_classes": sorted(c for c in class_order if int((y_true == c).sum()) == 0),
        "per_model": {},          # 모델별 y_pred/risk 캐시 (임계값 곡선 재사용)
    }

    _defaults = _load_feature_defaults()
    best_f1, best_name = -1.0, None
    for name, um in models.items():
        try:
            # ✨ v6.2: 모델별 최적 프렙 자동 선택
            if preprocess_fn is None:
                X_m, _adapt_note = _auto_prep_for_model(um, _raw_df, _defaults, bridge, mlclf_path)
            else:
                X_m, _adapt_note = _adapt_features(um, X, _defaults)
            proba = um.predict_proba(X_m)
            cls = [str(c) for c in um.classes_]
            # 🐛 FIX(v5.5) 안전망: 예측 라벨이 숫자, 정답이 문자면 자동 매핑 (조용한 F1=0 방지)
            if all(c.lstrip("-").isdigit() for c in cls) and not str(y_true[0]).lstrip("-").isdigit():
                cls = [chr(ord("a") + int(c)) if 0 <= int(c) <= 25 else c for c in cls]
                _adapt_note = (_adapt_note + " · " if _adapt_note else "") + "정수 클래스→문자 디코딩"
            if hasattr(um, "_predict_labels"):       # ✨ v5.6: 2단계 임계값 판정 존중
                y_pred = np.asarray([str(v) for v in um._predict_labels(X_m)])
            else:
                y_pred = np.array([cls[i] for i in proba.argmax(axis=1)])
            m_idx = cls.index("m") if "m" in cls else None
            risk = 1.0 - proba[:, m_idx] if m_idx is not None else proba.max(axis=1)

            mf1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
            acc = accuracy_score(y_true, y_pred)
            # ✨ v6.2: 주 지표 = 사기 클래스(a~l) 한정 micro F1 — 건수 가중 통합.
            #   (13클래스 전체 micro F1은 정확도와 수학적으로 동일 → 99% 정상 데이터에선 무의미)
            _fraud_lbls = [c for c in class_order if c != "m"]
            uf1 = f1_score(y_true, y_pred, labels=_fraud_lbls, average="micro", zero_division=0)
            ufp = precision_score(y_true, y_pred, labels=_fraud_lbls, average="micro", zero_division=0)
            ufr = recall_score(y_true, y_pred, labels=_fraud_lbls, average="micro", zero_division=0)
            result["model_comparison"][name] = {
                "micro_f1_fraud": round(float(uf1), 4),
                "micro_precision_fraud": round(float(ufp), 4),
                "micro_recall_fraud": round(float(ufr), 4),
                "macro_f1": round(float(mf1), 4),
                "accuracy": round(float(acc), 4),
                **({"note": _adapt_note} if _adapt_note else {}),
            }
            result["per_model"][name] = {"y_pred": list(y_pred) if hasattr(y_pred,'tolist') else y_pred,
                                        "risk": list(risk) if hasattr(risk,'tolist') else risk}
            if uf1 > best_f1:                      # ✨ v6.2: 베스트 선정도 주 지표(µF1 사기) 기준
                best_f1, best_name = uf1, name
        except Exception as e:
            log.error(f"모델 '{name}' 평가 실패: {e}")
            result["model_comparison"][name] = {"micro_f1_fraud": 0.0, "macro_f1": 0.0, "accuracy": 0.0, "error": str(e)}

    result["best_model"] = best_name

    # 베스트 모델 기준 상세 리포트 + 혼동행렬 (기존 렌더 코드와 동일 스키마)
    if best_name:
        y_pred = result["per_model"][best_name]["y_pred"]
        result["classification_report"] = classification_report(
            y_true, y_pred, labels=class_order, output_dict=True, zero_division=0
        )
        result["confusion_matrix"] = confusion_matrix(
            y_true, y_pred, labels=class_order
        ).tolist()

    return result


# ══════════════════════════════════════════════════════════
# 세션 2 — 임계값 기대비용 곡선 (실측 — 하드코딩 공식 대체)
# ══════════════════════════════════════════════════════════

def threshold_cost_curve(
    risk_scores: np.ndarray,
    y_true: np.ndarray,             # 클래스 라벨 (m=정상)
    fn_cost: float = 1_000_000,     # 미탐 1건당 비용 (기본: 사기 피해액 가정)
    fp_cost: float = 30_000,        # 오탐 1건당 비용 (기본: 수동검토 인건비 가정)
    steps: int = 48,
    fraud_weight: float = 1.0,      # ✨ v6.1: 층화 표본 → 모집단 환산 가중치
    normal_weight: float = 1.0,
) -> dict:
    """
    risk_score >= threshold 를 '이상 판정'으로 보고,
    실제 라벨 대비 FN/FP 건수 × 단가로 기대비용을 계산한다.
    반환: {"thresholds": [...], "fn": [...], "fp": [...], "total": [...],
           "optimal_threshold": float}
    """
    risk = np.asarray(risk_scores, dtype=float)
    is_fraud = np.asarray(y_true).astype(str) != "m"

    thresholds = np.linspace(0.02, 0.98, steps)
    fn_c, fp_c, tot = [], [], []
    for th in thresholds:
        flagged = risk >= th
        fn = float((is_fraud & ~flagged).sum()) * fraud_weight    # 사기인데 놓침 (모집단 환산)
        fp = float((~is_fraud & flagged).sum()) * normal_weight   # 정상인데 잡음 (모집단 환산)
        fn_c.append(fn * fn_cost)
        fp_c.append(fp * fp_cost)
        tot.append(fn * fn_cost + fp * fp_cost)

    opt = float(thresholds[int(np.argmin(tot))])
    return {
        "thresholds": thresholds.tolist(),
        "fn": fn_c, "fp": fp_c, "total": tot,
        "optimal_threshold": round(opt, 2),
        "fn_unit_cost": fn_cost, "fp_unit_cost": fp_cost,
    }


# ══════════════════════════════════════════════════════════
# 세션 3 — 선택 데이터셋 기반 집계 (세그먼트/금액대/플래그)
# ══════════════════════════════════════════════════════════

def segment_stats(df: pd.DataFrame, seg_col: str, normal_label: str = "정상") -> pd.DataFrame:
    """세그먼트 × 사기유형 crosstab (기존 세션 3와 동일 — 데이터셋 인자화)"""
    return pd.crosstab(
        df[seg_col],
        df["Fraud_Type"].apply(lambda x: normal_label if x == "m" else x),
    )


def amount_band_stats(df: pd.DataFrame, labels: list[str],
                      normal_label="정상", fraud_label="사기") -> pd.DataFrame:
    d = df.copy()
    d["band"] = pd.cut(
        d["Transaction_Amount"],
        bins=[-float("inf"), -10_000_000, 0, 10_000_000, 100_000_000, float("inf")],
        labels=labels,
    )
    d["cls"] = d["Fraud_Type"].apply(lambda x: normal_label if x == "m" else fraud_label)
    return pd.crosstab(d["band"], d["cls"])


def flag_on_ratio(df: pd.DataFrame, flags: list[str]) -> pd.DataFrame:
    fraud_df = df[df["Fraud_Type"] != "m"]
    normal_df = df[df["Fraud_Type"] == "m"]
    def _pct(sub):
        # 🐛 FIX(v10): 기존 `float(mean or 0)`은 mean이 NaN일 때 NaN이 truthy라 그대로 통과했다
        m = pd.to_numeric(sub[flag], errors="coerce").mean()
        return round(0.0 if pd.isna(m) else float(m) * 100, 1)
    rows = []
    for flag in flags:
        if flag in df.columns:
            rows.append({"flag": flag, "fraud_pct": _pct(fraud_df), "normal_pct": _pct(normal_df)})
    return pd.DataFrame(rows)


# ── 전처리 완료 데이터셋용 passthrough (실 parquet X_tr/X_va 등) ──

def passthrough_preprocess(feature_cols: list[str] | None = None,
                           fillna: float | None = None):
    """X가 이미 인코딩·파생 완료된 경우(예: X_tr.parquet 82피처).
    라벨·인덱스 잔재만 떼고 그대로 모델에 전달한다.
    feature_cols를 주면 해당 컬럼 순서로 정렬(모델 학습 순서 보장).
    fillna: 실데이터 X에 NaN이 존재함(검증됨) — LightGBM/XGBoost는 native 처리하므로
            None(기본) 권장. LogReg/SVM/ONNX 등 NaN 비허용 모델 비교 시 0 등 지정."""
    def _fn(df: pd.DataFrame) -> pd.DataFrame:
        X = df.drop(columns=[c for c in ("Fraud_Type",) if c in df.columns])
        X = X[[c for c in X.columns if not str(c).startswith("__index_level_")]]
        if feature_cols:
            missing = [c for c in feature_cols if c not in X.columns]
            if missing:
                raise ValueError(f"모델 피처 {len(missing)}개가 데이터셋에 없음: {missing[:5]}...")
            X = X[feature_cols]
        if fillna is not None:
            X = X.fillna(fillna)
        return X
    return _fn


# ── MLClassifier._preprocess 를 DataFrame 배치용으로 감싸는 헬퍼 ──

def make_batch_preprocess(classifier, keep_nan: bool = True) -> callable:
    """기존 MLClassifier(단건 dict용)를 df 배치 전처리 함수로 변환.
    ⚡ v5.5: 행별 루프(5,000행 ≈ 수 분) → 컬럼 단위 벡터화(≈ 1초). 결과 동일.

    🔴 FIX(v10) keep_nan: '컬럼 자체가 없음'과 '값이 NaN'을 구분한다.
      실데이터 X_va에는 진짜 NaN이 존재하고(Amount_vs_monthly_max_ratio 2,195건 =
      분모 0으로 인한 0/0, Time_difference_seconds 30건), LightGBM/XGBoost는 이를
      native 분기로 처리한다. 기존 코드가 이걸 feature_defaults 값으로 일괄 대체해
      **macro F1 0.6138 → 0.6070 으로 조용히 떨어지고 있었다**(실측).
      keep_nan=True(기본): NaN 보존 → 학습 시점 성능을 그대로 재현.
      keep_nan=False     : NaN 비허용 모델(LogReg/SVM/ONNX 등) 비교용.
    """
    def _fn(df: pd.DataFrame) -> pd.DataFrame:
        fc = classifier.feature_cols
        if not fc:                                        # 메타데이터 없음 → 기존 경로
            parts = [classifier._preprocess(row) for row in df.to_dict("records")]
            return pd.concat(parts, ignore_index=True)
        out = {}
        try:
            from pipeline.ml_classifier import CAT_COLS
        except ImportError:
            from ml_classifier import CAT_COLS
        _passthrough = set(getattr(classifier, "passthrough_cats", ()) or ())
        for col in fc:
            dflt = classifier.defaults.get(col, 0)
            _absent = col not in df.columns          # 컬럼 자체가 없으면 기본값으로 채움
            s = df[col] if not _absent else pd.Series([None] * len(df), index=df.index)
            try:
                d_num = float(dflt)
            except (TypeError, ValueError):
                d_num = 0.0
            # ✨ v10: 수치형 인코더 번들은 인코딩 금지 → 원본 수치 통과 (ml_classifier와 동일 규칙)
            if col in CAT_COLS and col in classifier.label_encoders and col not in _passthrough:
                le = classifier.label_encoders[col]
                lut = {str(c): i for i, c in enumerate(le.classes_)}
                d_enc = lut.get(str(dflt), 0)
                out[col] = s.astype(str).str.strip().map(lut).fillna(d_enc).astype(int).to_numpy()
            else:
                v = pd.to_numeric(s, errors="coerce")
                if _absent or not keep_nan:
                    v = v.fillna(d_num)
                out[col] = v.to_numpy()
        return pd.DataFrame(out, index=df.index)[fc]
    return _fn


def recompute_at_threshold(eval_data: dict, threshold: float) -> dict:
    """✨ v6.0: 임계값에 따라 KPI·클래스 리포트·CM 재계산 (사이드바 슬라이더 연동).
    risk >= threshold → 이상(원래 유형), 아니면 → 정상('m')."""
    y_true = np.array(eval_data.get("y_true_cache", []))
    if len(y_true) == 0:
        return eval_data
    co = eval_data.get("class_order", CLASS_ORDER)
    from sklearn.metrics import (f1_score, accuracy_score, precision_score,
                                 recall_score, classification_report,
                                 confusion_matrix as _cm_fn)
    new_comp, best_f1, best_name = {}, -1.0, None
    new_report, new_cm = {}, []
    for name, pm in eval_data.get("per_model", {}).items():
        risk = np.array(pm["risk"], dtype=float)
        y_pred_orig = np.array(pm["y_pred"])
        y_pred = np.where(risk >= threshold, y_pred_orig, "m")
        n = min(len(y_true), len(y_pred))
        yt, yp = y_true[:n], y_pred[:n]
        mf1 = f1_score(yt, yp, labels=co, average="macro", zero_division=0)
        acc = accuracy_score(yt, yp)
        mp  = precision_score(yt, yp, labels=co, average="macro", zero_division=0)
        mr  = recall_score(yt, yp, labels=co, average="macro", zero_division=0)
        _fl = [c for c in co if c != "m"]              # ✨ v6.2: 주 지표(µF1 사기) 병행 산출
        uf1 = f1_score(yt, yp, labels=_fl, average="micro", zero_division=0)
        ufp = precision_score(yt, yp, labels=_fl, average="micro", zero_division=0)
        ufr = recall_score(yt, yp, labels=_fl, average="micro", zero_division=0)
        orig = eval_data.get("model_comparison", {}).get(name, {})
        new_comp[name] = {"micro_f1_fraud": round(float(uf1), 4),
                          "micro_precision_fraud": round(float(ufp), 4),
                          "micro_recall_fraud": round(float(ufr), 4),
                          "macro_f1": round(float(mf1), 4), "accuracy": round(float(acc), 4),
                          "macro_precision": round(float(mp), 4), "macro_recall": round(float(mr), 4),
                          **({"note": orig["note"]} if orig.get("note") else {}),
                          **({"error": orig["error"]} if orig.get("error") else {})}
        if uf1 > best_f1:
            best_f1, best_name = uf1, name
            new_report = classification_report(yt, yp, labels=co, output_dict=True, zero_division=0)
            new_cm = _cm_fn(yt, yp, labels=co).tolist()
    result = dict(eval_data)
    result["model_comparison"] = new_comp
    result["classification_report"] = new_report
    result["confusion_matrix"] = new_cm
    result["best_model"] = best_name
    result["threshold_applied"] = threshold
    return result

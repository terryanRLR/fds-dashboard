"""
bundle_io — 배포 번들(.pkl/.json) 안전 로드 공용 모듈  ✨ v10 신규

배경
  팀 배포 번들(lgbm_13class(최종).pkl · label_encoders.pkl · le_target.pkl)은
  전부 **joblib** 형식으로 저장돼 있어, 맨 `pickle.load()`는
  `UnpicklingError: invalid load key '\\x0a'` 로 즉사한다.
  기존 코드는 '모델 본체'에만 joblib 폴백이 있었고(ml_classifier v5.6),
  메타 파일(label_encoders/le_target)은 맨 pickle이라
  → 번들을 넣으면 MLClassifier가 통째로 '더미 모드'로 빠졌다(세션5 전체 랜덤 예측).

  이 모듈은 pickle → joblib 순으로 시도하는 단일 진입점을 제공해,
  프로젝트 전체의 `pickle.load()` 호출부를 한 곳으로 모은다.

핵심 API
  safe_load(path)              → 객체 (pickle → joblib 폴백)
  is_numeric_encoder(le)       → LabelEncoder가 '수치형 클래스'로 학습됐는지
  load_model_meta(dir)         → model_meta.json (없으면 {})
  resolve_model_path(dir, ...) → 베이스 모델 파일 경로 자동 탐색
"""

from __future__ import annotations

import json
import pickle
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# 베이스 모델 파일명 우선순위 — 앞쪽이 먼저 채택된다.
#   팀 번들 실제 파일명이 `lgbm_13class(최종).pkl`(괄호·한글 포함)이라
#   glob 패턴과 정확 이름을 함께 둔다.
BASE_MODEL_PREFERENCE = (
    "lgbm_13class(최종).pkl",
    "lgbm_13class_최종_.pkl",
    "lgbm_13class.pkl",
    "lgbm_fds.pkl",
)
BASE_MODEL_GLOBS = ("lgbm_13class*.pkl", "lgbm*.pkl", "*.pkl")

# 모델이 아닌 '메타/부속' pkl — 모델 목록에서 반드시 제외한다.
#   (기존 dashboard.get_available_models가 이걸 걸러내지 않아
#    `🔍 Le Target` · `🔍 Label Encoders`가 선택 가능한 '모델'로 노출됐다)
NON_MODEL_PKL_STEMS = {
    "label_encoders", "le_target", "feature_bridge",
    "scaler", "imputer", "preprocessor", "encoders",
}


def safe_load(path_or_file):
    """pickle → joblib 순으로 시도해 객체를 반환한다.

    path(str|Path) 또는 열린 바이너리 파일 객체를 모두 받는다.
    파일 객체를 받은 경우 pickle 실패 시 seek()으로 되감아 joblib을 시도한다.
    """
    # ── 파일 객체 ──
    if hasattr(path_or_file, "read"):
        f = path_or_file
        try:
            pos = f.tell()
        except (OSError, AttributeError):
            pos = None
        try:
            return pickle.load(f)
        except Exception as e:
            if pos is None:
                raise
            f.seek(pos)
            import joblib
            obj = joblib.load(f)
            log.debug(f"pickle 실패({type(e).__name__}) → joblib 로드 성공 (파일객체)")
            return obj

    # ── 경로 ──
    p = Path(path_or_file)
    try:
        with open(p, "rb") as f:
            return pickle.load(f)
    except (ModuleNotFoundError, AttributeError) as e:
        # 라이브러리 버전 불일치는 joblib으로도 해결되지 않는다 → 명확히 알린다
        raise TypeError(
            f"{p.name}: 역직렬화 실패({type(e).__name__}: {e}) — 학습 환경과 "
            f"scikit-learn/lightgbm 버전이 다를 가능성이 큽니다. "
            f"requirements.txt 기준으로 버전을 맞춘 뒤 다시 시도하세요."
        ) from e
    except Exception as e_pickle:
        try:
            import joblib
            obj = joblib.load(p)
            log.info(f"{p.name}: joblib 형식으로 로드 (pickle 실패: {type(e_pickle).__name__})")
            return obj
        except Exception as e_joblib:
            raise TypeError(
                f"{p.name}: pickle·joblib 모두 로드 실패 "
                f"(pickle={type(e_pickle).__name__}: {e_pickle} / "
                f"joblib={type(e_joblib).__name__}: {e_joblib})"
            ) from e_joblib


def is_numeric_encoder(le) -> bool:
    """LabelEncoder가 '이미 수치인 값'으로 학습됐는지 판정.

    팀 번들의 label_encoders.pkl은 classes_가 문자열이 아니라 정수다
    (예: Channel → array([0,1,2,3]), Customer_Gender → array([0,1])).
    이는 전처리 파이프라인이 문자열을 먼저 인코딩한 뒤 그 결과로 다시
    LabelEncoder를 fit했기 때문이며, **추론 시 이 인코더를 적용하면 안 된다.**

    특히 Customer_Birthyear(classes_=[1950..2004])나
    Account_amount_daily_limit(classes_=[1e6, 2e6, 1e7, 3e7])에 적용하면
    1980 → 30, 2000000 → 1 로 바뀌는데, 모델의 분기 임계값은
    1951~2004 / 1.5e6~3e7 이므로 값의 의미가 완전히 파괴된다.
    """
    cls = getattr(le, "classes_", None)
    if cls is None or len(cls) == 0:
        return False
    try:
        import numpy as np
        return bool(np.issubdtype(np.asarray(cls).dtype, np.number))
    except Exception:
        return all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in cls)


def load_model_meta(directory) -> dict:
    """model_meta.json 로드 (없으면 {}).

    팀 번들 스키마:
      n_features, n_classes, normal_index, normal_label,
      class_index_to_label {"0":"a" … "12":"m"},
      macro_f1_valid, n_estimators, leak_dropped, categorical_cols_encoded
    """
    p = Path(directory) / "model_meta.json"
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        log.warning(f"model_meta.json 로드 실패: {e}")
        return {}
    c2l = meta.get("class_index_to_label") or {}
    if c2l:
        # {"0":"a", …} → ['a','b',…,'m'] (인덱스 순서 보장)
        try:
            meta["labels"] = [c2l[str(i)] for i in range(len(c2l))]
        except KeyError:
            meta["labels"] = [c2l[k] for k in sorted(c2l, key=lambda x: int(x))]
    log.info(f"model_meta.json 로드: {meta.get('n_features')}피처 · "
             f"{meta.get('n_classes')}클래스 · macro_f1={meta.get('macro_f1_valid')}")
    return meta


def resolve_model_path(directory, requested=None) -> Path | None:
    """베이스 모델 파일 경로를 결정한다.

    requested가 실제로 존재하면 그대로 사용하고,
    없으면 BASE_MODEL_PREFERENCE → BASE_MODEL_GLOBS 순으로 탐색한다.
    메타/부속 pkl(label_encoders 등)은 절대 후보로 삼지 않는다.
    """
    d = Path(directory)
    if requested:
        rp = Path(requested)
        if rp.exists():
            return rp
        if (d / rp.name).exists():
            return d / rp.name
    if not d.is_dir():
        return None
    for name in BASE_MODEL_PREFERENCE:
        p = d / name
        if p.exists():
            return p
    for pattern in BASE_MODEL_GLOBS:
        cands = [p for p in sorted(d.glob(pattern)) if not is_non_model_pkl(p)]
        if cands:
            # 동일 패턴 내에서는 가장 큰 파일 = 모델 본체로 추정
            return max(cands, key=lambda p: p.stat().st_size)
    return None


def is_non_model_pkl(path) -> bool:
    """label_encoders.pkl 등 '모델이 아닌' pkl인지 판정 (모델 목록 필터용)."""
    return Path(path).stem.lower() in NON_MODEL_PKL_STEMS

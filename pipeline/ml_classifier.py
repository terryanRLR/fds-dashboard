"""
MLClassifier — LightGBM 다중분류 래퍼 (버그 수정판)
수정 내용:
  1. _preprocess(): 누락 피처를 feature_defaults.json 기본값으로 채움
  2. 범주형 컬럼 인코딩 시 빈 값 안전 처리
  3. predict() 반환 전 DataFrame shape 검증
"""

import os
import json
import pickle
import logging
import numpy as np
import pandas as pd
from pathlib import Path

log = logging.getLogger(__name__)

# 🔴 FIX(v10): 팀 배포 번들은 joblib 형식 — 맨 pickle.load는 UnpicklingError로 즉사한다.
#   safe_load(pickle→joblib) 단일 진입점으로 통일. (bundle_io 없으면 기존 동작 유지)
try:
    from pipeline.bundle_io import safe_load, is_numeric_encoder, load_model_meta, resolve_model_path
    _BUNDLE_IO_OK = True
except ImportError:  # pragma: no cover
    try:
        from bundle_io import safe_load, is_numeric_encoder, load_model_meta, resolve_model_path
        _BUNDLE_IO_OK = True
    except ImportError:
        _BUNDLE_IO_OK = False
        def safe_load(p):
            with open(p, "rb") as f:
                return pickle.load(f)
        def is_numeric_encoder(le): return False
        def load_model_meta(d): return {}
        def resolve_model_path(d, requested=None): return None

# ══════════════════════════════════════════════════════════
# 🐛 FIX: Path("models")는 "streamlit run을 실행한 위치(CWD)" 기준 상대경로.
#   프로젝트 루트가 아닌 곳에서 실행하거나, 메타데이터 파일이 pipeline/ 등
#   다른 폴더에 있으면 전부 "없음 → 더미 모드"로 빠짐.
#   → 후보 디렉토리를 순서대로 탐색해 실제 위치를 찾는다.
#   → FDS_MODEL_DIR 환경변수로 강제 지정도 가능.
# ══════════════════════════════════════════════════════════
_THIS_DIR = Path(__file__).resolve().parent          # .../pipeline
_PROJ_DIR = _THIS_DIR.parent                          # 프로젝트 루트 추정

_CANDIDATE_DIRS = [
    p for p in [
        Path(os.environ["FDS_MODEL_DIR"]) if os.environ.get("FDS_MODEL_DIR") else None,
        Path("models"),            # CWD/models (기존 동작)
        _PROJ_DIR / "models",      # 프로젝트루트/models
        _THIS_DIR / "models",      # pipeline/models
        _THIS_DIR,                 # pipeline/ (모듈 옆에 둔 경우)
        _PROJ_DIR,                 # 프로젝트 루트에 둔 경우
        Path("."),                 # CWD
    ] if p is not None
]

def _find_file(name: str) -> Path | None:
    """후보 디렉토리에서 파일을 탐색해 첫 번째 존재 경로 반환"""
    for d in _CANDIDATE_DIRS:
        p = d / name
        if p.exists():
            return p
    return None

MODEL_DIR   = Path("models")   # (하위 호환용 — 신규 코드는 _find_file 사용)
CLASS_ORDER = list("abcdefghijklm")

CAT_COLS = [
    'Customer_Gender', 'Customer_credit_rating', 'Customer_loan_type',
    'Account_account_type', 'Channel', 'Operating_System',
    'Error_Code', 'Type_General_Automatic', 'Access_Medium',
]

DROP_COLS = [
    'ID', 'Customer_personal_identifier', 'Customer_identification_number',
    'Customer_registration_datetime', 'Account_account_number',
    'Account_creation_datetime', 'Transaction_Datetime',
    'IP_Address', 'MAC_Address', 'Location', 'Recipient_Account_Number',
    'Last_atm_transaction_datetime', 'Last_bank_branch_transaction_datetime',
    'Transaction_resumed_date', 'Time_difference', 'Fraud_Type',
]


class MLClassifier:
    def __init__(self, model_path: str = "models/lgbm_fds.pkl"):
        self.model_path     = Path(model_path)
        self.model          = None
        self.label_encoders = {}
        self.le_target      = None
        self.feature_cols   = []
        self.defaults       = {}
        self.passthrough_cats = []   # ✨ v10: 인코딩을 건너뛸 범주형 컬럼 (수치형 인코더)
        self.meta           = {}     # ✨ v10: model_meta.json
        self._load_all()

    # ── 모델 및 메타데이터 로드 ─────────────────────────
    def _load_all(self):
        try:
            # ── 모델 본체: 전달받은 경로가 없으면 파일명으로 후보 탐색 ──
            mp = self.model_path
            if not mp.exists():
                found = _find_file(mp.name)
                # ✨ FIX(v10): 파일명이 다른 팀 번들(`lgbm_13class(최종).pkl` 등)도 찾아낸다
                if found is None:
                    for d in _CANDIDATE_DIRS:
                        found = resolve_model_path(d, None)
                        if found:
                            break
                if found:
                    log.info(f"모델 경로 보정: {mp} → {found.resolve()}")
                    mp = found
            # 🔴 FIX(v10): pickle→joblib 폴백을 safe_load로 통일
            self.model = safe_load(mp)
            self.model_path = mp

            # ── 메타데이터: 모델 파일과 같은 폴더 우선, 없으면 후보 탐색 ──
            def _meta(name):
                p = mp.parent / name
                return p if p.exists() else _find_file(name)

            le_path = _meta("label_encoders.pkl")
            lt_path = _meta("le_target.pkl")
            if le_path is None or lt_path is None:
                raise FileNotFoundError("label_encoders.pkl / le_target.pkl")
            # 🔴 FIX(v10): 이 두 파일이 joblib 형식이라 맨 pickle.load가 UnpicklingError를
            #   던지고, 그게 아래 `except Exception`으로 전파되어 **번들 전체가 더미 모드**로
            #   빠지던 것이 세션5 랜덤 예측의 근본 원인이었다.
            self.label_encoders = safe_load(le_path)
            self.le_target      = safe_load(lt_path)
            # ✨ FIX(v10): 인코더가 '이미 수치'로 학습된 번들이면 추론 시 적용하면 안 된다.
            #   (Customer_Birthyear 1980→30, Account_amount_daily_limit 2000000→1 파괴)
            self.passthrough_cats = sorted(
                c for c, le in (self.label_encoders or {}).items() if is_numeric_encoder(le)
            )
            if self.passthrough_cats:
                log.info(
                    f"수치형 인코더 {len(self.passthrough_cats)}개 감지 → 해당 컬럼은 "
                    f"인코딩 없이 원본 수치 통과 (배포 번들 계약과 동일)"
                )
            self.meta = load_model_meta(mp.parent)

            # 기본값 파일 먼저 로드 (feature_cols 복구에 필요)
            defaults_path = _meta("feature_defaults.json")
            if defaults_path:
                with open(defaults_path, encoding="utf-8") as f:
                    self.defaults = json.load(f)
                log.info(f"feature_defaults.json 로드: {defaults_path.resolve()}")
            else:
                log.warning(
                    "feature_defaults.json 없음 → 0으로 대체 | 탐색한 위치: "
                    + ", ".join(str((d / 'feature_defaults.json').resolve()) for d in _CANDIDATE_DIRS)
                )
                self.defaults = {}

            # feature_cols 로드 — 없으면 feature_defaults.json 키로 자동 복구
            feature_cols_path = _meta("feature_cols.json")
            if feature_cols_path:
                with open(feature_cols_path, encoding="utf-8") as f:
                    self.feature_cols = json.load(f)
            elif self.defaults:
                self.feature_cols = list(self.defaults.keys())
                # 자동 복구한 파일을 모델 폴더에 저장하여 다음 실행 시 바로 사용
                try:
                    save_path = mp.parent / "feature_cols.json"
                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(self.feature_cols, f, indent=2, ensure_ascii=False)
                    log.info(f"feature_cols.json 자동 생성 완료 — {len(self.feature_cols)}개 피처 → {save_path.resolve()}")
                except OSError as e:
                    log.warning(f"feature_cols.json 저장 실패: {e}")
            else:
                log.error("feature_cols.json도 feature_defaults.json도 없음 → 더미 모드")

            log.info(f"모델 로드 완료 — 피처 {len(self.feature_cols)}개 (모델: {mp.resolve()})")

        except FileNotFoundError as e:
            # 🛡 FIX(v9): 모델은 로드됐는데 메타(label_encoders/le_target)가 없으면
            #   model만 남은 '반쪽 초기화' → predict()에서 le_target.classes_ AttributeError 즉사
            self.model = None
            log.warning(
                f"모델/메타 파일 없음: {e} → 더미 모드 | CWD={Path.cwd()} | "
                f"탐색 후보: {[str(d.resolve()) for d in _CANDIDATE_DIRS]}"
            )
        except Exception as e:
            # 🐛 FIX(v5.3): 깨진 pickle('invalid load key' 등)·버전 불일치가
            #   UnpicklingError로 전파되어 대시보드 전체(s2.eval_fail 포함)를 죽이던 문제.
            #   어떤 로드 실패도 더미 모드로 격리하고 사유를 남긴다.
            self.model = None
            log.error(f"모델 로드 실패({type(e).__name__}: {e}) → 더미 모드 | 파일: {self.model_path}")

    # ── 핵심 예측 ────────────────────────────────────────
    def predict(self, row: dict) -> tuple[str, float, dict]:
        """
        Returns:
            fraud_type : 예측 클래스 (a~m)
            risk_score : 위험점수 = 1 - P(m)
            proba_dict : 클래스별 확률 딕셔너리
        """
        if self.model is None:
            return self._dummy_predict()

        X = self._preprocess(row)

        # shape 검증
        if X.empty or X.shape[1] == 0:
            log.error(f"전처리 결과 빈 DataFrame — row keys: {list(row.keys())[:10]}")
            return self._dummy_predict()

        try:
            proba = self.model.predict_proba(X)[0]
        except Exception as e:
            # 🐛 FIX(v5.6): 모델 기대 피처(예: 81개 파생셋)와 전처리 결과(48개)가 다른 조합 등
            #   예측 단계 실패 시 세션 5 전체가 죽지 않도록 더미로 격리 + 사유 로그.
            log.error(f"예측 실패({type(e).__name__}: {str(e)[:90]}) → 더미 폴백 | "
                      f"이 모델이 파생 피처(81개 등)용이면 세션 2 동적 평가에서 parquet 데이터셋과 사용하세요")
            return self._dummy_predict()
        classes    = self.le_target.classes_
        proba_dict = {cls: float(p) for cls, p in zip(classes, proba)}
        m_prob     = proba_dict.get('m', 0.0)
        risk_score = float(1 - m_prob)
        fraud_type = classes[int(np.argmax(proba))]

        return fraud_type, risk_score, proba_dict

    # ── 전처리 (핵심 수정) ───────────────────────────────
    def _preprocess(self, row: dict) -> pd.DataFrame:
        """
        row dict → 모델 입력 DataFrame
        - 누락 피처: feature_defaults.json 기본값으로 채움
        - _ 로 시작하는 내부 키 무시
        - 범주형: LabelEncoder 변환, 미등록 값은 최빈 클래스(인덱스 0)
        - 수치형: float 변환, 실패 시 기본값
        """
        data = {}

        for col in self.feature_cols:
            # 내부 키(_input_mode 등) 스킵
            raw = row.get(col)
            if raw is None:
                raw = self.defaults.get(col, 0)

            # 🔴 FIX(v10): 수치형 인코더(배포 번들)는 적용 금지 — 원본 수치를 그대로 통과.
            #   기존 코드는 `str(raw) in le.classes_`로 비교했는데 classes_가 np.int64
            #   배열이라 **항상 False** → 기본값도 False → data[col]=[0].
            #   결과: Channel/Gender/OS 등 9개 범주형이 입력과 무관하게 전부 0으로 고정됐다.
            if col in self.passthrough_cats:
                try:
                    data[col] = [float(raw)]
                except (ValueError, TypeError):
                    data[col] = [float(self.defaults.get(col, 0) or 0)]
            elif col in CAT_COLS and col in self.label_encoders:
                le      = self.label_encoders[col]
                val_str = str(raw).strip()
                _classes = [str(c) for c in le.classes_]      # dtype 무관 비교
                if val_str in _classes:
                    data[col] = [int(_classes.index(val_str))]
                else:
                    # 미등록 범주 → 기본값 → 그래도 없으면 최빈 클래스(0)
                    default_str = str(self.defaults.get(col, le.classes_[0]))
                    if default_str in _classes:
                        data[col] = [int(_classes.index(default_str))]
                    else:
                        data[col] = [0]
                    log.debug(f"미등록 범주 '{val_str}' → 기본값 사용 ({col})")
            else:
                # 수치형
                try:
                    data[col] = [float(raw)]
                except (ValueError, TypeError):
                    data[col] = [float(self.defaults.get(col, 0))]

        df = pd.DataFrame(data)[self.feature_cols]
        log.debug(f"전처리 완료: shape={df.shape}")
        return df

    # ── 배치 예측 ────────────────────────────────────────
    def predict_batch(self, rows: list[dict]) -> list[tuple]:
        return [self.predict(row) for row in rows]

    # ── 피처 정보 반환 (대시보드 UI용) ──────────────────
    def get_feature_info(self) -> dict:
        return {
            "feature_cols": self.feature_cols,
            "cat_cols":     CAT_COLS,
            "drop_cols":    DROP_COLS,
            "defaults":     self.defaults,
            "cat_options":  {
                col: self.label_encoders[col].classes_.tolist()
                for col in CAT_COLS if col in self.label_encoders
            },
        }

    # ── 더미 모드 ────────────────────────────────────────
    def _dummy_predict(self) -> tuple[str, float, dict]:
        import random
        if random.random() < 0.15:
            ft    = random.choice(list("abcdefghijkl"))
            score = round(random.uniform(0.6, 0.99), 4)   # score = 위험점수
        else:
            ft    = 'm'
            score = round(random.uniform(0.01, 0.3), 4)   # 정상 → 위험점수 낮음
        proba = {c: round(random.uniform(0, 0.05), 4) for c in CLASS_ORDER}
        # 🐛 FIX(v5): risk_score = 1 - P(m) 정의와 일치하도록 P(m)을 역산해서 채움.
        #   (기존: ft=='m'일 때 proba['m']=score(0.01~0.3) → risk=1-P(m)=0.7~0.99로
        #    정상 예측이 전부 고위험 판정되어 더미 모드에서 100% 이상거래 오탐)
        proba['m'] = round(1 - score, 4)
        if ft != 'm':
            proba[ft] = round(score, 4)
        return ft, score, proba

"""
ModelLoader — 다형식 모델 통합 어댑터 (신규)

지원 형식
  .pkl            : sklearn / LightGBM / XGBoost / CatBoost 등 pickle (기존 방식)
  .onnx           : onnxruntime — skl2onnx/onnxmltools로 내보낸 분류 모델
  .pmml           : sklearn-pmml-model(순수 파이썬, 트리·선형 계열) 우선,
                    실패 시 pypmml(JVM 필요) 폴백
  .sql            : m2cgen 등으로 내보낸 스코어링 SQL을 DuckDB로 실행
                    (규약: `data` 테이블을 대상으로 클래스별 확률 컬럼
                     proba_a ... proba_m 또는 score_* 를 SELECT 하는 쿼리)

통합 인터페이스 (UnifiedModel)
  .classes_             : 클래스 라벨 리스트 (a~m)
  .predict_proba(X_df)  : (n, n_classes) 확률 배열
  .backend              : 'pickle' | 'onnx' | 'pmml' | 'sql'

기존 MLClassifier 의 _preprocess 결과(DataFrame)를 그대로 받도록 설계.
"""

from __future__ import annotations

import re
import pickle
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
# 🔴 FIX(v10): 팀 배포 번들(joblib 형식) 대응 — 맨 pickle.load 금지
try:
    from pipeline.bundle_io import safe_load
except ImportError:  # pragma: no cover
    try:
        from bundle_io import safe_load
    except ImportError:
        def safe_load(p):
            import pickle as _pk
            with open(p, "rb") as f:
                return _pk.load(f)


CLASS_ORDER = list("abcdefghijklm")


class UnifiedModel:
    """모든 백엔드를 predict_proba 하나로 통일한 래퍼"""

    def __init__(self, backend: str, classes: list[str], impl):
        self.backend = backend
        self.classes_ = list(classes)
        self._impl = impl

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self._impl(X)

    def __repr__(self):
        return f"<UnifiedModel backend={self.backend} classes={len(self.classes_)}>"


# ══════════════════════════════════════════════════════════
# 진입점
# ══════════════════════════════════════════════════════════

def load_model(path: str | Path | dict) -> UnifiedModel:
    if isinstance(path, dict):                       # ✨ v5.6 컴포지트 spec
        return _load_composite(path)
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"모델 파일 없음: {path}")
    suffix = path.suffix.lower()
    if suffix in (".pkl", ".pickle", ".joblib"):
        return _load_pickle(path)
    if suffix == ".onnx":
        return _load_onnx(path)
    if suffix == ".pmml":
        return _load_pmml(path)
    if suffix == ".sql":
        return _load_sql(path)
    raise ValueError(f"지원하지 않는 모델 형식: {suffix} (pkl/onnx/pmml/sql)")


def _try_load_any(path: Path):
    """pickle → joblib 순으로 시도 (메타 스캔용) — v10: bundle_io.safe_load 위임"""
    try:
        return safe_load(path)
    except Exception:
        return None


def _scan_meta(path: Path) -> dict | None:
    """✨ v5.6: 팀 메타 pkl 감지 — {'feature_cols':…, 'labels':…, (normal_idx/threshold…)} dict"""
    if path.stat().st_size > 2_000_000:          # 메타는 소형 — 대형 모델 로드 방지
        return None
    obj = _try_load_any(path)
    if isinstance(obj, dict) and "labels" in obj:
        # ✨ v6.1: 팀별 메타 키명 변형 허용 (feature_cols / features / columns 등)
        fc = obj.get("feature_cols") or obj.get("features") or obj.get("feature_names") or obj.get("columns")
        if fc is not None:
            obj["feature_cols"] = fc     # 정규화
            return obj
    return None


def _match_part(paths: list[Path], patterns: tuple) -> Path | None:
    """🐛 FIX(v6.0): '2단계_1' 외에 '2단계(1)', '2단계-1', 'stage 1', '1단계' 등
    팀별 명명 관례를 정규식으로 허용 (실사용: '2단계(2)(미탐0 임계값...).pkl')"""
    for p in paths:
        stem = p.stem
        if any(re.search(pat, stem, flags=re.IGNORECASE) for pat in patterns):
            return p
    return None


def discover_models(folder: str | Path = "models/") -> dict:
    """models/ 폴더 검색 → {표시명: Path | 컴포지트 spec dict}
    ✨ v5.6: 메타 pkl(피처순서·라벨맵·임계값)을 감지해 2단계/메타결합 컴포지트를 자동 조립.
    부품(메타·1단계·2단계)은 단독 목록에서 숨겨 오사용을 방지한다."""
    folder = Path(folder)
    found: dict = {}
    if not folder.is_dir():
        return found

    pkls = [p for p in sorted(folder.glob("*.pkl"))
            if p.stem not in ("label_encoders", "le_target", "feature_bridge")]
    metas = [(p, m) for p in pkls if (m := _scan_meta(p))]
    hidden = {p for p, _ in metas}
    remaining = [p for p in pkls if p not in hidden]

    for mp, meta in metas:
        title = str(meta.get("model", mp.stem))
        thr = meta.get("threshold_zero_miss", meta.get("threshold_default"))
        if "TwoStage" in title or "2단계" in title or "2단계" in mp.stem:
            s1 = _match_part(remaining, (r"2\s*단계[\s_\-()]*1", r"stage[\s_\-]*1", r"(?:^|[_\s(])s1(?:$|[_\s)])", r"(?:^|[^0-9])1\s*단계"))
            s2 = _match_part(remaining, (r"2\s*단계[\s_\-()]*2", r"stage[\s_\-]*2", r"(?:^|[_\s(])s2(?:$|[_\s)])"))
            if s1 is not None and s2 is not None:
                name = f"🧩 2단계 파이프라인" + (f" · 미탐0(thr {thr})" if thr else "")
                found[name] = {"kind": "two_stage", "s1": s1, "s2": s2, "meta": meta}
                hidden.update({s1, s2})
                remaining = [p for p in remaining if p not in (s1, s2)]
            else:
                log.warning(f"{mp.name}: 2단계 메타지만 1/2단계 모델 파일을 찾지 못함(파일명에 '2단계_1'/'2단계_2' 권장)")
        else:
            comp = _match_part(remaining, ("13클래스", "한방", "single", "multiclass"))
            if comp is None and remaining:
                comp = max(remaining, key=lambda p: p.stat().st_size)   # 최대 크기 = 본체 추정
            if comp is not None:
                found[f"🧩 {title}"] = {"kind": "single_meta", "model": comp, "meta": meta}
                hidden.add(comp)
                remaining = [p for p in remaining if p != comp]
            else:
                log.warning(f"{mp.name}: 메타와 짝지을 모델 pkl 없음")

    for p in remaining:
        found[f"🥒 {p.name}"] = p
    for pattern, badge in (("*.onnx", "🔷"), ("*.pmml", "📄"), ("*.sql", "🗄️")):
        for p in sorted(folder.glob(pattern)):
            found[f"{badge} {p.name}"] = p
    return found


# ══════════════════════════════════════════════════════════
# 백엔드별 로더
# ══════════════════════════════════════════════════════════

# 번들 dict에서 실제 모델을 찾을 때 우선 확인하는 키 (팀 저장 관례 대응)
_BUNDLE_KEYS = ("model", "clf", "classifier", "estimator", "best_model",
                "pipeline", "booster", "lgbm", "lightgbm")


def _load_pickle(path: Path) -> UnifiedModel:
    """🐛 FIX(v5.3): 팀원 모델 실사용 오류 3종 대응
      · invalid load key ─ pickle이 아닌 파일(joblib/LightGBM 네이티브/ONNX 등)을
        .pkl 확장자로 저장한 경우 → 헤더 스니핑으로 실제 형식을 감지해 자동 로드
      · 'dict' has no predict_proba ─ {'model':…, 'encoder':…} 번들 저장 → 내부 모델 추출
      · 버전 불일치 ─ 명확한 안내 메시지 (invalid load key는 버전 문제가 아님)"""
    # ⚡ FIX(v9): read_bytes()는 수백MB 모델 전체를 메모리에 올림 → 16바이트만 읽기
    with open(path, "rb") as _hf:
        head = _hf.read(16)

    model, how = None, "pickle"
    if head[:1] in (b"\x80", b"(", b"c", b"}", b"]"):        # pickle 스트림 시그니처
        try:
            with open(path, "rb") as f:
                model = pickle.load(f)
        except (ModuleNotFoundError, AttributeError, ImportError) as e:
            raise TypeError(
                f"{path.name}: 역직렬화 실패({e}) — 학습 환경과 라이브러리 버전 불일치 가능성이 큽니다. "
                f"requirements.txt 기준으로 scikit-learn/lightgbm 버전을 맞춘 뒤 다시 시도하세요."
            ) from e
        except Exception:
            model = None                                       # joblib 등으로 폴백
    if model is None:
        # ① joblib (압축 저장 포함)
        try:
            import joblib
            model = joblib.load(path); how = "joblib"
        except Exception:
            model = None
    if model is None and (b"tree" in head or head[:1] in (b"\n", b"\r", b"t")):
        # ② LightGBM 네이티브 텍스트 모델 (booster.save_model 출력)
        try:
            import lightgbm as lgb
            try:
                model = lgb.Booster(model_file=str(path))
            except Exception:
                # 선두 공백/개행이 붙은 저장본 → 정리 후 재시도 (v5.3)
                txt = path.read_text(encoding="utf-8", errors="ignore").lstrip()
                if txt.startswith("tree"):
                    import tempfile, os as _os
                    fd, tmp = tempfile.mkstemp(suffix=".txt"); _os.close(fd)
                    Path(tmp).write_text(txt, encoding="utf-8")
                    try:
                        model = lgb.Booster(model_file=tmp)
                    finally:
                        _os.unlink(tmp)
                else:
                    raise
            how = "lgb_native"
        except Exception:
            model = None
    if model is None:
        # ③ ONNX/protobuf를 .pkl로 저장한 경우 (첫 바이트 0x08/0x0a 등)
        try:
            um = _load_onnx(path)
            log.warning(f"{path.name}: 내용이 ONNX로 감지되어 ONNX 로더로 열었습니다 — 확장자를 .onnx로 바꾸는 것을 권장")
            return um
        except Exception:
            pass
        raise TypeError(
            f"{path.name}: pickle 파일이 아닙니다 (첫 바이트 {head[:4]!r}). "
            f"joblib/LightGBM 네이티브/ONNX 로도 열리지 않았습니다. 저장 방식을 확인하세요 — "
            f"권장: pickle.dump(model) 또는 booster.save_model('x.txt'), skl2onnx('x.onnx')."
        )

    # ── dict 번들 → 내부 모델 추출 ──
    bundle_note = ""
    if isinstance(model, dict):
        inner = None
        for k in _BUNDLE_KEYS:
            v = model.get(k)
            if v is not None and (hasattr(v, "predict_proba") or type(v).__name__ == "Booster"):
                inner = v; bundle_note = f" (번들 dict의 '{k}' 키에서 추출)"; break
        if inner is None:
            inner = next((v for v in model.values()
                          if hasattr(v, "predict_proba") or type(v).__name__ == "Booster"), None)
            if inner is not None:
                bundle_note = " (번들 dict 값 탐색으로 추출)"
        if inner is None:
            raise TypeError(
                f"{path.name}: dict 번들 안에서 predict_proba 모델을 찾지 못했습니다 "
                f"(키: {list(model.keys())[:8]}). 모델 객체를 'model' 키로 저장해 주세요."
            )
        model = inner

    # ── LightGBM Booster(네이티브/번들) → predict_proba 래핑 ──
    if type(model).__name__ == "Booster":
        booster = model
        n_cls = booster.num_model_per_iteration() if hasattr(booster, "num_model_per_iteration") else 1
        classes = _guess_classes(n_cls, path)
        def _bpredict(X, _b=booster, _n=max(n_cls, 2)):
            p = np.asarray(_b.predict(X))
            if p.ndim == 1:                       # 이진 → 2열 확장
                p = np.column_stack([1 - p, p])
            return p
        um = UnifiedModel("lgb_native" if how == "lgb_native" else "pickle", classes, _bpredict)
        um._model_ref = booster
        log.info(f"{path.name}: LightGBM Booster 로드{bundle_note} — 클래스 {len(classes)}종")
        return um

    if not hasattr(model, "predict_proba"):
        raise TypeError(f"{path.name}: predict_proba 미지원 객체({type(model).__name__}){bundle_note}")
    classes = _decode_int_classes([str(c) for c in getattr(model, "classes_", CLASS_ORDER)], path)
    um = UnifiedModel("pickle" if how == "pickle" else how, classes,
                      lambda X: np.asarray(model.predict_proba(X)))
    um._model_ref = model      # RowClassifier 피처 순서 정렬용 (v5.2)
    if bundle_note or how != "pickle":
        log.info(f"{path.name}: 로드 완료{bundle_note} [형식: {how}]")
    return um


def _decode_int_classes(classes: list[str], path: Path) -> list[str]:
    """🐛 FIX(v5.5): y를 정수 인코딩(0~12)한 채 학습한 모델은 model.classes_가 숫자.
       세션 5(MLClassifier)는 le_target.pkl로 복원하지만 동적 평가는 숫자를 그대로 써서
       정답('a'~'m')과 전부 불일치 → F1이 조용히 0.0이 되던 문제.
       → le_target.pkl 우선, 없으면 알파벳 매핑(dataset_loader와 동일 규칙)으로 복원."""
    if not classes or not all(c.lstrip("-").isdigit() for c in classes):
        return classes                                   # 이미 문자 라벨
    idx = [int(c) for c in classes]
    for cand in (path.parent / "le_target.pkl", Path("models/le_target.pkl")):
        if cand.exists():
            try:
                le = safe_load(cand)     # 🔴 FIX(v10): joblib 번들 대응
                if max(idx) < len(le.classes_):
                    dec = [str(le.classes_[i]) for i in idx]
                    log.info(f"{path.name}: 정수 클래스 {idx[:3]}… → {dec[:3]}… (le_target.pkl 복원)")
                    return dec
            except Exception as e:
                log.warning(f"le_target 복원 실패({e}) → 알파벳 매핑")
            break
    if 0 <= min(idx) and max(idx) <= 25:
        dec = [chr(ord("a") + i) for i in idx]
        log.info(f"{path.name}: 정수 클래스 → 알파벳 매핑({idx[0]}→{dec[0]} … {idx[-1]}→{dec[-1]})")
        return dec
    return classes


def _guess_classes(n_cls: int, path: Path) -> list[str]:
    """네이티브 Booster는 클래스 라벨을 저장하지 않음 → le_target.pkl로 복원 시도"""
    for cand in (path.parent / "le_target.pkl", Path("models/le_target.pkl")):
        if cand.exists():
            try:
                le = safe_load(cand)     # 🔴 FIX(v10): joblib 번들 대응
                cls = [str(c) for c in le.classes_]
                if len(cls) == n_cls or n_cls <= 1:
                    return cls
            except Exception:
                pass
    return CLASS_ORDER[:n_cls] if 1 < n_cls <= len(CLASS_ORDER) else CLASS_ORDER


def _load_onnx(path: Path) -> UnifiedModel:
    import onnxruntime as ort

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    input_meta = sess.get_inputs()[0]
    input_name = input_meta.name
    outputs = [o.name for o in sess.get_outputs()]

    # skl2onnx 분류기는 보통 [label, probabilities(zipmap dict 또는 tensor)] 출력
    proba_out = next((o for o in outputs if "proba" in o.lower() or "score" in o.lower()),
                     outputs[-1])

    def _predict(X: pd.DataFrame) -> np.ndarray:
        arr = X.to_numpy(dtype=np.float32)
        raw = sess.run([proba_out], {input_name: arr})[0]
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            # ZipMap 출력: [{'a':0.1,...}, ...] → 클래스 순 정렬 배열
            keys = sorted(raw[0].keys(), key=lambda k: str(k))
            return np.array([[row[k] for k in keys] for row in raw], dtype=float)
        return np.asarray(raw, dtype=float)

    # 클래스 라벨 추출: 1건 더미 추론으로 ZipMap 키를 읽거나 CLASS_ORDER 폴백
    n_feat = input_meta.shape[-1] if isinstance(input_meta.shape[-1], int) else None
    _onnx_n_feat = n_feat            # 피처 적응용 보존 (v5.4)
    classes = CLASS_ORDER
    if n_feat:
        try:
            dummy = np.zeros((1, n_feat), dtype=np.float32)
            raw = sess.run([proba_out], {input_name: dummy})[0]
            if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                classes = sorted((str(k) for k in raw[0].keys()))
            elif hasattr(raw, "shape") and raw.shape[-1] != len(CLASS_ORDER):
                classes = [str(i) for i in range(raw.shape[-1])]
        except Exception as e:
            log.warning(f"ONNX 클래스 추론 실패 → 기본 a~m 사용: {e}")

    um = UnifiedModel("onnx", classes, _predict)
    um._n_features = _onnx_n_feat    # 이름 없는 형식 → 차원만 검증 가능 (v5.4)
    return um


def _load_pmml(path: Path) -> UnifiedModel:
    # 1순위: sklearn-pmml-model (순수 파이썬 — 트리·앙상블·선형 계열)
    try:
        from sklearn_pmml_model.auto_detect import auto_detect_estimator
        model = auto_detect_estimator(pmml=str(path))
        classes = [str(c) for c in model.classes_]
        return UnifiedModel("pmml", classes, lambda X: np.asarray(model.predict_proba(X)))
    except Exception as e:
        log.warning(f"sklearn-pmml-model 로드 실패({e}) → pypmml 시도")

    # 2순위: pypmml (JVM 필요 — 설치돼 있을 때만)
    from pypmml import Model as PMMLModel
    model = PMMLModel.fromFile(str(path))
    out_fields = [f.name for f in model.outputFields]
    proba_fields = [f for f in out_fields if f.lower().startswith(("probability", "proba"))]
    classes = [re.sub(r"^probability[_(]?", "", f).rstrip(")") for f in proba_fields] or CLASS_ORDER

    def _predict(X: pd.DataFrame) -> np.ndarray:
        res = model.predict(X)
        return res[proba_fields].to_numpy(dtype=float)

    return UnifiedModel("pmml", classes, _predict)


def _load_sql(path: Path) -> UnifiedModel:
    """
    스코어링 SQL 실행 (DuckDB 인메모리).
    규약:
      - 쿼리는 `data` 라는 테이블/뷰를 SELECT 대상으로 사용
      - 클래스별 확률 컬럼명: proba_<class>  (예: proba_a ... proba_m)
        또는 score_<class> — 합이 1이 아니면 행별로 정규화함
      - 행 순서는 입력 순서 유지 (ORDER BY 사용 금지 권장)
    """
    import duckdb

    sql_text = path.read_text(encoding="utf-8")
    col_re = re.compile(r"(?:proba|score)_([0-9A-Za-z]+)", re.IGNORECASE)
    classes = sorted(dict.fromkeys(m.group(1).lower() for m in col_re.finditer(sql_text)))
    if not classes:
        raise ValueError(f"{path.name}: proba_<class>/score_<class> 컬럼을 찾지 못함 — 스코어링 SQL 규약 확인")

    def _predict(X: pd.DataFrame) -> np.ndarray:
        con = duckdb.connect()
        try:
            con.register("data", X.reset_index(drop=True))
            out = con.execute(sql_text).df()
        finally:
            con.close()
        cols = []
        for c in classes:
            hit = next((oc for oc in out.columns if oc.lower() in (f"proba_{c}", f"score_{c}")), None)
            if hit is None:
                raise ValueError(f"SQL 결과에 proba_{c} 컬럼 없음")
            cols.append(hit)
        proba = out[cols].to_numpy(dtype=float)
        if len(proba) != len(X):
            raise ValueError(f"SQL 결과 행 수({len(proba)}) ≠ 입력 행 수({len(X)}) — ORDER BY/필터 제거 필요")
        # 합 1 정규화 (score_* 형태 대비)
        s = proba.sum(axis=1, keepdims=True)
        s[s == 0] = 1.0
        return proba / s

    return UnifiedModel("sql", classes, _predict)


# ══════════════════════════════════════════════════════════
# 세션 5 / batch_analyzer 호환 어댑터
# ══════════════════════════════════════════════════════════

class RowClassifier:
    """UnifiedModel(배치 proba)을 MLClassifier.predict(row dict) 인터페이스로 감싼다.
    전처리 완료(인코딩된) 피처를 그대로 받는 모델용 — 실 parquet 세트 배치 분석에 사용."""

    def __init__(self, um: UnifiedModel, feature_cols: list[str]):
        self.um = um
        self.feature_cols = list(feature_cols)
        # 🐛 FIX(v5.2): pkl 모델이 학습 시 피처 순서를 기억하면 그 순서를 우선한다.
        #   (row dict 키 순서가 학습 순서와 다르면 위치 기반 모델이 조용히 오예측하는 문제 방지)
        model = getattr(um, "_impl", None)
        inner = getattr(model, "__self__", None) if hasattr(model, "__self__") else None
        for attr in ("feature_names_in_", "feature_name_"):
            names = getattr(inner, attr, None) if inner is not None else None
            if names is None and hasattr(um, "_model_ref"):
                names = getattr(um._model_ref, attr, None)
            if names is not None:
                names = [str(n) for n in (names() if callable(names) else names)]
                missing = [n for n in names if n not in self.feature_cols]
                if not missing:
                    self.feature_cols = names
                else:
                    # 🔴 FIX(v10): 기존엔 경고 로그만 남기고 **row dict 키 순서 그대로** 위치
                    #   기반 예측을 계속했다. 값이 전부 엉뚱한 컬럼에 들어가는데 화면에는
                    #   정상 결과처럼 보이는 최악의 실패 모드였다 → 예외로 승격해
                    #   대시보드가 alert_box로 사용자에게 보여주도록 한다.
                    raise ValueError(
                        f"모델이 기대하는 피처 {len(names)}개 중 {len(missing)}개가 입력 행에 없습니다"
                        f"(예: {missing[:4]}). 입력 순서로 그냥 예측하면 값이 다른 컬럼에 들어가"
                        f" 조용히 오예측하므로 중단합니다 — 데이터셋·모델 계열을 맞추거나"
                        f" 배포 번들(Preprocessor) 경로를 사용하세요."
                    )
                break

    def predict(self, row: dict) -> tuple[str, float, dict]:
        # 🐛 FIX(v10): float(...) 직접 호출은 문자 범주값('ATM')에서 ValueError로 즉사했고,
        #   `or 0`은 누락 피처를 학습 기본값 대신 0으로 밀어넣었다 → NaN 보존 + 안전 변환.
        def _v(c):
            x = row.get(c, None)
            if x is None:
                return float("nan")
            try:
                return float(x)
            except (ValueError, TypeError):
                return float("nan")
        X = pd.DataFrame([[_v(c) for c in self.feature_cols]], columns=self.feature_cols)
        proba = self.um.predict_proba(X)[0]
        cls = [str(c) for c in self.um.classes_]
        proba_dict = {c: float(p) for c, p in zip(cls, proba)}
        m_prob = proba_dict.get("m", 0.0)
        risk = float(1 - m_prob) if "m" in proba_dict else float(proba.max())
        if hasattr(self.um, "_predict_labels"):      # ✨ v5.6: 2단계 임계값 판정 존중
            ft = str(self.um._predict_labels(X)[0])
        else:
            ft = cls[int(np.argmax(proba))]
        return ft, risk, proba_dict


def make_row_classifier(model_path, feature_cols) -> RowClassifier:
    return RowClassifier(load_model(model_path), feature_cols)


def _load_composite(spec: dict) -> UnifiedModel:
    """✨ v5.6: 메타 기반 컴포지트 조립
    - single_meta : 본체 모델 + 메타(피처순서 81·라벨 a~m·normal_idx)
    - two_stage   : 1단계(이진 risk) + 2단계(유형) + 임계값 — usage 규칙 그대로:
                    risk=s1.proba[:,1]; suspect=risk>=thr → s2 유형, 아니면 정상"""
    meta = spec["meta"]
    labels = [str(x) for x in meta["labels"]]
    nidx = int(meta.get("normal_idx", labels.index("m") if "m" in labels else len(labels) - 1))
    feat = [str(c) for c in meta.get("feature_cols") or []] or None

    if spec["kind"] == "single_meta":
        base = load_model(spec["model"])
        if len(base.classes_) != len(labels):
            raise ValueError(f"메타 라벨 {len(labels)}종 ≠ 모델 클래스 {len(base.classes_)}종 — 짝이 맞는지 확인")
        um = UnifiedModel(base.backend + "+meta", labels, base._impl)
        um._model_ref = getattr(base, "_model_ref", None)
        um._expected_features = feat
        return um

    s1 = load_model(spec["s1"]); s2 = load_model(spec["s2"])
    thr = float(meta.get("threshold_zero_miss", meta.get("threshold_default", 0.5)))
    # s2 클래스(v5.5 디코딩 후 'a'~'l' 등) → 라벨 인덱스 매핑
    s2_idx = []
    for c in s2.classes_:
        cs = str(c)
        s2_idx.append(labels.index(cs) if cs in labels
                      else int(float(cs)) if cs.lstrip("-").replace(".","").isdigit() else 0)

    def _proba(X):
        r = np.asarray(s1.predict_proba(X))[:, 1]
        p2 = np.asarray(s2.predict_proba(X))
        out = np.zeros((len(X), len(labels)))
        out[:, nidx] = 1.0 - r
        for j, ci in enumerate(s2_idx):
            out[:, ci] += r * p2[:, j]
        return out

    def _labels_fn(X):
        r = np.asarray(s1.predict_proba(X))[:, 1]
        p2 = np.asarray(s2.predict_proba(X))
        tl = np.array([labels[s2_idx[j]] for j in p2.argmax(axis=1)])
        return np.where(r >= thr, tl, labels[nidx])

    um = UnifiedModel("two_stage", labels, _proba)
    um._predict_labels = _labels_fn                  # 미탐0 임계값 의미 보존 (argmax 아님)
    um._expected_features = feat
    um._threshold = thr
    return um


def get_expected_features(um: UnifiedModel) -> list[str] | None:
    """모델이 학습 시 기억한 피처명 목록 (없으면 None) — 자동 피처 매칭용 (v5.4)"""
    exp = getattr(um, "_expected_features", None)    # ✨ v5.6: 메타 지정이 최우선
    if exp:
        return list(exp)
    ref = getattr(um, "_model_ref", None)
    if ref is None:
        return None
    for attr in ("feature_names_in_", "feature_name_"):
        names = getattr(ref, attr, None)
        if names is not None:
            names = names() if callable(names) else names
            return [str(n) for n in names]
    if hasattr(ref, "feature_name"):                       # 네이티브 Booster
        try:
            return [str(n) for n in ref.feature_name()]
        except Exception:
            pass
    return None

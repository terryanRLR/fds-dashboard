"""
DatasetLoader — 대시보드용 데이터셋 검색·로딩 모듈 (신규)

지원 형식
  1. 단일 CSV        : train.csv, test.csv, *.csv  (Fraud_Type 컬럼 포함/미포함)
  2. 단일 Parquet    : *.parquet (Fraud_Type 포함/미포함)
  3. 분할 Parquet 세트: X_tr.parquet + y_tr.parquet, X_va.parquet + y_va.parquet 등
                       (X_*/y_* 접두 페어를 자동 감지하여 결합)

핵심 API
  discover_datasets(folder)  → {표시명: DatasetInfo}
  load_dataset(info)         → pd.DataFrame (라벨이 있으면 'Fraud_Type' 컬럼으로 통일)
"""

from __future__ import annotations

import re
import pickle  # noqa: F401  (하위호환 - 외부에서 참조 가능)
import logging
from pathlib import Path
from dataclasses import dataclass, field

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


# 모듈 버전 — 🩺 진단 패널이 표시 (구버전 모듈이 메모리에 남는 문제 진단용)
LOADER_VERSION = "v6 (접두어 페어링)"

# 라벨 파일에서 Fraud_Type 으로 통일할 후보 컬럼명 (우선순위 순)
LABEL_COL_CANDIDATES = ["Fraud_Type", "fraud_type", "label", "Label", "target", "y", "Y"]

# X_tr / y_tr, X_train / y_train ... 에 더해 접두어 허용 (✨ v6: "구 X_tr", "old_X_va" 등)
#   pre  : 임의 접두어 (비어있거나, 마지막 글자가 공백·_·-·. 등 비영숫자여야 함 — "proxy_data" 오인 방지)
#   xy   : X|y (대소문자 무관)
#   split: 스플릿 이름 (tr, va, train, valid, test ...)
_SPLIT_RE = re.compile(r"^(?P<pre>.*?)(?P<xy>[xy])[_\-](?P<split>.+)$", re.IGNORECASE)

def _match_xy(stem: str):
    """파일명 → (접두어, x|y, split) | None. 접두어 경계가 애매하면(영숫자로 끝) 페어 후보에서 제외."""
    m = _SPLIT_RE.match(stem)
    if not m:
        return None
    pre = m.group("pre")
    if pre and pre[-1].isalnum():          # "proxy_data", "max_speed" 등 일반 이름 보호
        return None
    return pre, m.group("xy").lower(), m.group("split")


@dataclass
class DatasetInfo:
    """대시보드 셀렉터에 노출되는 데이터셋 1건의 메타데이터"""
    name: str                       # 표시명 (예: "train.csv", "parquet: tr (X+y)")
    kind: str                       # csv | parquet | parquet_xy
    paths: list[Path] = field(default_factory=list)   # 관련 파일 경로 (X, y 순)
    has_label: bool = False         # Fraud_Type(라벨) 보유 여부
    note: str = ""                  # UI 부가 설명


# ══════════════════════════════════════════════════════════
# 검색
# ══════════════════════════════════════════════════════════

def discover_datasets(folder: str | Path = "data/") -> dict[str, DatasetInfo]:
    """폴더를 스캔해 사용 가능한 데이터셋 목록을 반환한다."""
    folder = Path(folder)
    found: dict[str, DatasetInfo] = {}
    if not folder.is_dir():
        log.warning(f"데이터 폴더 없음: {folder}")
        return found

    # ✨ v6: (접두어, split) → {"x": Path, "y": Path, "disp": 표시명}
    parquet_pairs: dict[tuple, dict] = {}

    for p in sorted(folder.iterdir()):
        suffix = p.suffix.lower()

        if suffix == ".csv":
            has_label = _peek_has_label_csv(p)
            found[p.name] = DatasetInfo(
                name=p.name, kind="csv", paths=[p], has_label=has_label,
                note=("라벨 포함" if has_label else "라벨 없음 (예측 전용)") + f" · {_row_count_hint(p)}",
            )

        elif suffix in (".parquet", ".pq"):
            m = _match_xy(p.stem)
            if m:                                      # X_tr / 구 X_tr / old_y_va 등 분할 파일
                pre, xy, split = m
                key = (pre.casefold().strip(), split.casefold())
                slot = parquet_pairs.setdefault(key, {})
                slot[xy] = p
                slot.setdefault("disp", f"{pre}{split}".strip())   # 표시명은 원문 유지
            else:                                      # 단일 parquet
                has_label = _peek_has_label_parquet(p)
                found[p.name] = DatasetInfo(
                    name=p.name, kind="parquet", paths=[p], has_label=has_label,
                    note=("라벨 포함" if has_label else "라벨 없음 (예측 전용)") + f" · {_row_count_hint(p)}",
                )

    # X/y 페어 조립 — X만 있으면 예측 전용으로, y만 있으면 단일 데이터셋으로 노출
    for key, pair in sorted(parquet_pairs.items()):
        disp = pair.get("disp", key[1])
        if "x" in pair and "y" in pair:
            name = f"parquet:{disp} (X+y 결합)"
            found[name] = DatasetInfo(
                name=name, kind="parquet_xy",
                paths=[pair["x"], pair["y"]], has_label=True,
                note=f"{pair['x'].name} + {pair['y'].name} 자동 결합 · {_row_count_hint(pair['x'])}",
            )
        elif "x" in pair:
            name = f"parquet:{disp} (X만)"
            found[name] = DatasetInfo(
                name=name, kind="parquet", paths=[pair["x"]], has_label=False,
                note=f"{pair['x'].name} — y 파일 없음 (예측 전용)",
            )
        else:
            # 🔧 FIX(v6): 기존엔 y 단독 파일이 목록에서 통째로 사라졌음 → 단일 데이터셋으로 노출
            yp = pair["y"]
            log.warning(f"y 파일만 존재 — X 없음: {yp} (단일 데이터셋으로 노출)")
            found[yp.name] = DatasetInfo(
                name=yp.name, kind="parquet", paths=[yp],
                has_label=_peek_has_label_parquet(yp),
                note=f"⚠ 짝 X 파일 없음 · {_row_count_hint(yp)}",
            )

    return found


# ══════════════════════════════════════════════════════════
# 로딩
# ══════════════════════════════════════════════════════════

def load_dataset(info: DatasetInfo, n_limit: int | None = None,
                 label_decoder="auto") -> pd.DataFrame:
    """
    DatasetInfo → DataFrame.
    라벨이 있으면 컬럼명을 'Fraud_Type'으로 통일하고,
    정수 인코딩 라벨(0~12)이면 문자 클래스('a'~'m')로 디코딩한다.

    label_decoder:
      "auto"       : models/le_target.pkl 탐색 → 없으면 0..12 ⊆ 값일 때 알파벳 매핑
      LabelEncoder : inverse_transform 사용
      dict         : {정수: 클래스} 매핑
      None         : 디코딩 안 함 (원본 유지)
    """
    if info.kind == "csv":
        df = pd.read_csv(info.paths[0], nrows=n_limit)

    elif info.kind == "parquet":
        df = pd.read_parquet(info.paths[0])
        if n_limit:
            df = df.head(n_limit)

    elif info.kind == "parquet_xy":
        X = pd.read_parquet(info.paths[0])
        y = pd.read_parquet(info.paths[1])
        df = _join_xy(X, y)
        if n_limit:
            df = df.head(n_limit)

    else:
        raise ValueError(f"알 수 없는 데이터셋 종류: {info.kind}")

    df = _normalize_label_col(df)
    df = _drop_index_artifacts(df)
    df = _decode_labels(df, label_decoder)
    return df


def _drop_index_artifacts(df: pd.DataFrame) -> pd.DataFrame:
    """pyarrow 경로로 읽었을 때 남는 __index_level_N__ 잔재 컬럼 제거.
    (pd.read_parquet은 보통 인덱스로 흡수하지만, 엔진/버전에 따라 컬럼으로 남을 수 있음)"""
    junk = [c for c in df.columns if str(c).startswith("__index_level_")]
    if junk:
        log.info(f"인덱스 잔재 컬럼 제거: {junk}")
        df = df.drop(columns=junk)
    return df


def _decode_labels(df: pd.DataFrame, decoder) -> pd.DataFrame:
    """정수 인코딩 라벨(y=0~12)을 문자 클래스('a'~'m')로 디코딩.
    문자 라벨이면 그대로 둔다. 평가기/대시보드는 'm'(정상) 문자 기준으로 동작하므로 필수."""
    if decoder is None or "Fraud_Type" not in df.columns:
        return df
    col = df["Fraud_Type"]
    if not pd.api.types.is_integer_dtype(col) and not pd.api.types.is_float_dtype(col):
        return df                                   # 이미 문자 라벨

    vals = pd.unique(col.dropna())
    if decoder == "auto":
        decoder = _find_le_target()                 # models/le_target.pkl 우선
        if decoder is None:
            iv = [int(v) for v in vals]
            if iv and min(iv) >= 0 and max(iv) <= 25:
                decoder = {i: chr(ord("a") + i) for i in range(max(iv) + 1)}
                log.info(f"정수 라벨 감지({sorted(iv)[:5]}...) → 알파벳 매핑(0→a … {max(iv)}→{chr(ord('a')+max(iv))}) 적용. "
                         f"학습 시 사용한 le_target.pkl이 있다면 models/에 두면 그것을 우선 사용합니다.")
            else:
                log.warning(f"정수 라벨이지만 디코딩 규칙 불명(값 범위 {min(iv)}~{max(iv)}) → 원본 유지")
                return df

    # 🛡 FIX(v9): 라벨에 NaN이 섞인 float 컬럼은 astype(int)에서 ValueError 즉사
    #   → 유효 행만 디코딩, NaN 행은 원본 유지
    _valid = col.notna()
    if hasattr(decoder, "inverse_transform"):       # LabelEncoder
        df = df.copy()
        try:
            decoded = col.copy().astype(object)
            decoded[_valid] = [str(x) for x in decoder.inverse_transform(col[_valid].astype(int))]
            df["Fraud_Type"] = decoded
        except Exception as _de:
            log.warning(f"le_target 디코딩 실패({_de}) → 원본 라벨 유지")
    elif isinstance(decoder, dict):
        df = df.copy()
        decoded = col.copy().astype(object)
        decoded[_valid] = col[_valid].astype(int).map(decoder).fillna(col[_valid].astype(str))
        df["Fraud_Type"] = decoded
    return df


def _find_le_target():
    """models/le_target.pkl 후보 경로 탐색 (ml_classifier와 동일한 관례)"""
    for cand in (Path("models/le_target.pkl"),
                 Path(__file__).resolve().parent.parent / "models" / "le_target.pkl",
                 Path(__file__).resolve().parent / "models" / "le_target.pkl"):
        if cand.exists():
            try:
                le = safe_load(cand)        # 🔴 FIX(v10): joblib 번들 대응
                log.info(f"le_target.pkl 로드 → 라벨 디코딩에 사용: {cand}")
                return le
            except Exception as e:
                log.warning(f"le_target.pkl 로드 실패({cand}): {e}")
    return None


def _join_xy(X: pd.DataFrame, y: pd.DataFrame) -> pd.DataFrame:
    """X + y 결합. 인덱스가 다르면(0..n 리셋 등) 순서 기준으로 결합한다."""
    if len(X) != len(y):
        raise ValueError(f"X({len(X)}행)와 y({len(y)}행)의 행 수가 다릅니다 — 페어가 맞는지 확인하세요")

    y = y.copy()
    # y가 Series로 저장된 parquet(1열)일 수도, ID+label 2열일 수도 있음
    label_col = _pick_label_col(y)
    if label_col is None:
        # 컬럼명이 전부 무의미하면 첫 컬럼을 라벨로 간주 (단, X와 겹치지 않는 것)
        cands = [c for c in y.columns if c not in X.columns]
        if not cands:
            raise ValueError(f"y 파일에서 라벨 컬럼을 찾지 못함: {list(y.columns)}")
        label_col = cands[0]
        log.info(f"라벨 컬럼 추정: '{label_col}' (후보명 미일치 → 첫 비중복 컬럼 사용)")

    y = y.rename(columns={label_col: "Fraud_Type"})

    # 공통 ID 컬럼이 있으면 ID 기준 merge, 없으면 위치 기준 concat
    common_ids = [c for c in ("ID", "id") if c in X.columns and c in y.columns]
    if common_ids:
        key = common_ids[0]
        df = X.merge(y[[key, "Fraud_Type"]], on=key, how="left")
        n_miss = df["Fraud_Type"].isna().sum()
        if n_miss:
            log.warning(f"ID 결합 후 라벨 누락 {n_miss}건 — 위치 기준 결합을 검토하세요")
    else:
        X = X.reset_index(drop=True)
        y = y.reset_index(drop=True)
        df = pd.concat([X, y[["Fraud_Type"]]], axis=1)

    return df


def _pick_label_col(df: pd.DataFrame) -> str | None:
    for c in LABEL_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def _normalize_label_col(df: pd.DataFrame) -> pd.DataFrame:
    """라벨 후보 컬럼이 있으면 'Fraud_Type'으로 리네임"""
    if "Fraud_Type" in df.columns:
        return df
    c = _pick_label_col(df)
    if c:
        df = df.rename(columns={c: "Fraud_Type"})
    return df


# ── 가벼운 라벨 유무 체크 (전체 로드 없이) ────────────────

def _row_count_hint(p: Path) -> str:
    """✨ v5.8: 셀렉터에 표시할 행 수 — parquet 정확 / CSV는 20MB 이하 정확, 초과 시 크기 근사"""
    try:
        if p.suffix.lower() in (".parquet", ".pq"):
            import pyarrow.parquet as pq
            return f"{pq.read_metadata(p).num_rows:,}행"
        size = p.stat().st_size
        if size <= 20_000_000:
            with open(p, "rb") as f:
                n = sum(1 for _ in f) - 1
            return f"{max(n,0):,}행"
        return f"약 {size/1_000_000:.0f}MB"
    except Exception:
        return "?행"


def _peek_has_label_csv(p: Path) -> bool:
    try:
        cols = pd.read_csv(p, nrows=0).columns
        return any(c in cols for c in LABEL_COL_CANDIDATES)
    except Exception:
        return False


def _peek_has_label_parquet(p: Path) -> bool:
    try:
        import pyarrow.parquet as pq
        cols = pq.read_schema(p).names
        return any(c in cols for c in LABEL_COL_CANDIDATES)
    except Exception:
        return False

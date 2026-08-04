"""
verify_bundle — 배포 번들 × 데이터셋 호환 검증 하니스  ✨ v10 신규

목적
  "새 모델을 넣었는데 제대로 붙었나?"를 30초 안에 판정한다.
  전처리 경로 4가지를 모두 돌려 macro F1 / µF1(사기) / 정확도를 대조하고,
  model_meta.json에 기재된 기준값(macro_f1_valid)과 자동 비교한다.

경로
  ① passthrough        : X가 이미 58피처 → 그대로 모델에 전달 (기준선)
  ② Preprocessor       : pipeline.preprocessor — 원본/전처리완료 양쪽 결정론적 변환
  ③ MLClassifier       : evaluator.make_batch_preprocess (keep_nan=True)
  ④ MLClassifier(구동작): keep_nan=False — NaN을 기본값으로 채우던 이전 동작 (회귀 감시용)

사용
  python -m tools.verify_bundle
  python -m tools.verify_bundle --models models/ --x data/X_va.parquet --y data/y_va.parquet
  python -m tools.verify_bundle --raw data/train.csv --x data/X_tr.parquet   # 변환 규칙 자가검증까지
"""

from __future__ import annotations

import sys
import json  # noqa: F401  (하위 호환 - 외부 참조 가능)
import argparse
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("verify_bundle")

TOL = 0.005          # 기준값과의 허용 오차 (macro F1)


def _metrics(y_true, y_pred, classes) -> dict:
    from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score
    fraud = [c for c in classes if c != "m"]
    return {
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "micro_f1_fraud": f1_score(y_true, y_pred, labels=fraud, average="micro", zero_division=0),
        "precision_fraud": precision_score(y_true, y_pred, labels=fraud, average="micro", zero_division=0),
        "recall_fraud": recall_score(y_true, y_pred, labels=fraud, average="micro", zero_division=0),
        "accuracy": accuracy_score(y_true, y_pred),
    }


def run(models_dir="models/", x_path="data/X_va.parquet", y_path="data/y_va.parquet",
        raw_path=None) -> int:
    from pipeline.bundle_io import safe_load, resolve_model_path, load_model_meta
    from pipeline.preprocessor import Preprocessor
    from pipeline.ml_classifier import MLClassifier
    from pipeline.evaluator import make_batch_preprocess

    d = Path(models_dir)
    print("═" * 78)
    print(f" 배포 번들 검증 — {d.resolve()}")
    print("═" * 78)

    # ── 번들 인벤토리 ──
    mp = resolve_model_path(d)
    if mp is None:
        print(" ❌ 베이스 모델을 찾지 못했습니다.")
        return 2
    meta = load_model_meta(d)
    baseline = meta.get("macro_f1_valid")
    print(f" 모델            : {mp.name}  ({mp.stat().st_size/1e6:.1f} MB)")
    for fn in ("label_encoders.pkl", "le_target.pkl", "feature_cols.json",
               "feature_defaults.json", "model_meta.json"):
        print(f"   {'✅' if (d/fn).exists() else '⚠️ '} {fn}")
    if baseline:
        print(f" 기준 macro F1   : {baseline}  (model_meta.json)")

    model = safe_load(mp)
    le = safe_load(d / "le_target.pkl") if (d / "le_target.pkl").exists() else None
    classes = meta.get("labels") or ([str(c) for c in le.classes_] if le is not None else None)
    if classes is None:
        classes = [str(c) for c in getattr(model, "classes_", [])]

    X = pd.read_parquet(x_path) if str(x_path).endswith((".parquet", ".pq")) else pd.read_csv(x_path)
    y_raw = pd.read_parquet(y_path) if str(y_path).endswith((".parquet", ".pq")) else pd.read_csv(y_path)
    y_col = y_raw.columns[0]
    y = y_raw[y_col].to_numpy()
    if np.issubdtype(np.asarray(y).dtype, np.number):
        y_true = np.array([classes[int(v)] for v in y])
    else:
        y_true = np.asarray(y).astype(str)
    print(f" 데이터           : {Path(x_path).name}  {X.shape[0]:,}행 × {X.shape[1]}열")
    print(f"   라벨 분포      : 정상 {int((y_true=='m').sum()):,} / 사기 {int((y_true!='m').sum()):,}")
    print(f"   NaN 보유 행    : {int(X.isna().any(axis=1).sum()):,}")

    prep_obj = Preprocessor.from_bundle(d)
    fc = prep_obj.feature_cols
    n_missing = [c for c in fc if c not in X.columns]
    if n_missing:
        print(f" ⚠️  데이터에 없는 피처 {len(n_missing)}개: {n_missing[:5]}")

    # ── 경로별 평가 ──
    print("\n" + "─" * 78)
    print(f" {'경로':<26}{'macro F1':>10}{'µF1(사기)':>12}{'재현율':>9}{'정확도':>9}  판정")
    print("─" * 78)

    paths = []
    if not n_missing:
        paths.append(("① passthrough (기준선)", lambda: X[fc]))
    paths.append(("② Preprocessor", lambda: prep_obj.transform(X)))
    try:
        clf = MLClassifier(str(mp))
        if clf.model is not None:
            paths.append(("③ MLClassifier", lambda: make_batch_preprocess(clf, keep_nan=True)(X)))
            paths.append(("④ MLClassifier(구동작)", lambda: make_batch_preprocess(clf, keep_nan=False)(X)))
    except Exception as e:
        print(f" ⚠️  MLClassifier 준비 실패: {e}")

    results, failed = {}, 0
    for name, fn in paths:
        try:
            Xp = fn()
            proba = np.asarray(model.predict_proba(Xp))
            pred = np.array([classes[i] for i in proba.argmax(1)])
            m = _metrics(y_true, pred, classes)
            results[name] = m
            if baseline is None:
                verdict = "—"
            elif abs(m["macro_f1"] - baseline) <= TOL:
                verdict = "✅ 기준 일치"
            elif m["macro_f1"] < baseline - TOL:
                verdict = f"⚠️  {m['macro_f1'] - baseline:+.4f}"
                if not name.startswith("④"):
                    failed += 1
            else:
                verdict = f"↑ {m['macro_f1'] - baseline:+.4f}"
            print(f" {name:<26}{m['macro_f1']:>10.4f}{m['micro_f1_fraud']:>12.4f}"
                  f"{m['recall_fraud']:>9.4f}{m['accuracy']:>9.4f}  {verdict}")
        except Exception as e:
            print(f" {name:<26}{'—':>10}{'—':>12}{'—':>9}{'—':>9}  ❌ {type(e).__name__}: {str(e)[:34]}")
            failed += 1
    print("─" * 78)

    # ── Preprocessor 재현 검증 ──
    if not n_missing:
        got = prep_obj.transform(X)
        bad = [c for c in fc
               if not (np.isclose(got[c].to_numpy(float), pd.to_numeric(X[c], errors="coerce").to_numpy(float),
                                  rtol=1e-6, atol=1e-9)
                       | (got[c].isna().to_numpy() & X[c].isna().to_numpy())).all()]
        print(f"\n Preprocessor 재현 : {len(fc)-len(bad)}/{len(fc)}피처 일치"
              + (f"  ❌ 불일치: {bad[:5]}" if bad else "  🎉 전부 일치"))
        if bad:
            failed += 1

    # ── 원본 CSV로 변환 규칙 자가검증 ──
    if raw_path and Path(raw_path).exists():
        print("\n" + "─" * 78)
        print(f" 변환 규칙 자가검증 — {Path(raw_path).name} ↔ {Path(x_path).name}")
        try:
            rep = prep_obj.learn_from_pair(pd.read_csv(raw_path), X)
            worst = sorted(rep.items(), key=lambda kv: kv[1])[:5]
            n_ok = sum(1 for v in rep.values() if v >= 99.9)
            print(f"   {n_ok}/{len(rep)}피처 99.9%↑ 일치")
            for k, v in worst:
                print(f"     {'✅' if v >= 99.9 else '❌'} {k:<40} {v:>8.4f}%")
            if prep_obj.learned:
                print("   ↻ 자동 교정:", prep_obj.learned)
            if n_ok < len(rep):
                failed += 1
        except Exception as e:
            print(f"   ⚠️  자가검증 불가: {type(e).__name__}: {e}")

    print("\n" + "═" * 78)
    if failed == 0:
        print(" ✅ 전 경로 정상 — 번들이 파이프라인에 올바르게 붙었습니다.")
    else:
        print(f" ❌ {failed}건 문제 — 위 판정 열을 확인하세요.")
        if "④ MLClassifier(구동작)" in results and "③ MLClassifier" in results:
            d34 = results["③ MLClassifier"]["macro_f1"] - results["④ MLClassifier(구동작)"]["macro_f1"]
            if d34 > 0.001:
                print(f"    참고: ③−④ = {d34:+.4f} → NaN 보존(keep_nan=True)이 정상 동작 중입니다.")
    print("═" * 78)
    return 0 if failed == 0 else 1


def main():
    ap = argparse.ArgumentParser(description="배포 번들 × 데이터셋 호환 검증")
    ap.add_argument("--models", default="models/")
    ap.add_argument("--x", default="data/X_va.parquet")
    ap.add_argument("--y", default="data/y_va.parquet")
    ap.add_argument("--raw", default=None, help="원본 train.csv (변환 규칙 자가검증용)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.ERROR, format="  %(message)s")
    sys.exit(run(a.models, a.x, a.y, a.raw))


if __name__ == "__main__":
    main()

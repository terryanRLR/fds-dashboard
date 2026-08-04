"""
threshold_report — 임계값별 탐지·알림 실측 리포트  ✨ v16 신규

목적
  th_review / th_confirm 을 **감이 아니라 숫자로** 정한다.
  검증셋을 워처와 완전히 동일한 경로로 추론한 뒤, 임계값을 바꿔가며
  탐지·미탐·오탐과 **하루 예상 알림 건수**를 센다.

판정이 갈라지지 않게 하는 장치
  · 분류기   : pipeline.preprocessor.RawRowClassifier — 워처가 쓰는 그 객체
  · 위험점수 : predict_batch 와 동일한 정의 (1 - P(정상))
  · 등급판정 : DetectService.notify_tier 를 실제로 호출해 벡터 연산 결과를
               표본 대조한다. 불일치하면 리포트 상단에 경고가 뜬다.

사용법
  python -m tools.threshold_report
  python -m tools.threshold_report --daily 300
  python -m tools.threshold_report --x data/X_va.parquet --y data/y_va.parquet

출력
  터미널 표 + threshold_report.csv + threshold_report.txt
"""

from __future__ import annotations

import sys
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SINGLE_STEPS = [round(float(t), 2) for t in np.arange(0.05, 1.001, 0.05)]

DUAL_COMBOS = [
    (0.30, 0.70), (0.35, 0.75), (0.40, 0.80), (0.45, 0.80), (0.45, 0.85),
    (0.50, 0.80), (0.50, 0.85), (0.55, 0.85), (0.60, 0.85), (0.60, 0.90),
    (0.70, 0.90),
]


def _load_current_config() -> dict:
    try:
        from pipeline import watcher_config as wcfg
        return wcfg.load()
    except Exception:
        return {}


def _infer(models_dir: str, x_path: str, y_path: str):
    """워처와 동일한 경로로 추론."""
    from pipeline.preprocessor import RawRowClassifier

    clf = RawRowClassifier.from_bundle(models_dir)
    if getattr(clf, "model", None) is None:
        raise RuntimeError(
            "모델을 불러오지 못했습니다 — 먼저 python -m tools.verify_bundle 로 확인하세요")

    X = (pd.read_parquet(x_path) if str(x_path).endswith((".parquet", ".pq"))
         else pd.read_csv(x_path))
    y_raw = (pd.read_parquet(y_path) if str(y_path).endswith((".parquet", ".pq"))
             else pd.read_csv(y_path))

    classes = [str(c) for c in (clf.classes_ or [])]
    normal = str(getattr(clf, "normal_label", "m"))

    y = y_raw[y_raw.columns[0]].to_numpy()
    if np.issubdtype(np.asarray(y).dtype, np.number):
        if not classes:
            raise RuntimeError("정수 라벨인데 클래스 목록이 없습니다 (model_meta.json 확인)")
        y_true = np.array([classes[int(v)] for v in y])
    else:
        y_true = np.asarray(y).astype(str)

    if len(y_true) != len(X):
        raise RuntimeError(f"X({len(X)}행)와 y({len(y_true)}행)의 행 수가 다릅니다")

    Xp = clf.prep.transform(X)
    P = np.asarray(clf.model.predict_proba(Xp))
    mi = classes.index(normal) if normal in classes else None
    risk = (1.0 - P[:, mi]) if mi is not None else P.max(axis=1)
    pred_type = (np.array([classes[i] for i in P.argmax(1)]) if classes
                 else np.array([str(i) for i in P.argmax(1)]))

    name = "model"
    for attr in ("model_path", "path", "_model_path"):
        v = getattr(clf, attr, None)
        if v:
            name = Path(str(v)).name
            break
    return y_true, risk, pred_type, normal, name


def _verify_tier_logic(risk, pred_type, normal, th_r, th_c, n_sample=300) -> str:
    """벡터 계산이 DetectService.notify_tier 와 일치하는지 표본 대조."""
    try:
        from pipeline.detect_service import DetectService, DetectConfig
    except Exception as e:
        return f"[!] 등급 로직 대조 건너뜀 (detect_service 임포트 실패: {e})"

    svc = DetectService.__new__(DetectService)
    svc.cfg = DetectConfig(dual_threshold=True, th_review=th_r, th_confirm=th_c)

    rng = np.random.default_rng(0)
    idx = rng.choice(len(risk), size=min(n_sample, len(risk)), replace=False)
    bad = 0
    for i in idx:
        vec = ("confirm" if risk[i] >= max(th_r, th_c)
               else "review" if (risk[i] >= th_r or pred_type[i] != normal)
               else "none")
        if svc.notify_tier(str(pred_type[i]), float(risk[i])) != vec:
            bad += 1
    if bad:
        return f"[X] 등급 로직 불일치 {bad}/{len(idx)}건 — 이 리포트를 신뢰하지 마세요"
    return f"[OK] 등급 로직 대조 {len(idx)}건 전부 일치 (워처와 동일한 판정 규칙)"


def run(x_path="data/X_va.parquet", y_path="data/y_va.parquet",
        models_dir="models/", daily=300, save=True):

    y_true, risk, pred_type, normal, model_name = _infer(models_dir, x_path, y_path)

    n_total = len(y_true)
    is_fraud = (y_true != normal)
    n_fraud = int(is_fraud.sum())
    n_normal = n_total - n_fraud
    cur = _load_current_config()
    cur_r = float(cur.get("th_review", 0.45))
    cur_c = float(cur.get("th_confirm", 0.80))

    lines: list[str] = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("=" * 92)
    out(f" 임계값 실측 리포트 — {Path(x_path).name}")
    out(f" 모델 {model_name} · {n_total:,}행 · "
        f"사기 {n_fraud:,}건 ({n_fraud/n_total:.2%}) · 정상 {n_normal:,}건")
    out(f" 하루 유입량 가정 : {daily:,}건   (--daily 로 변경)")
    out(f" 현재 워처 설정   : review {cur_r} / confirm {cur_c}")
    out("=" * 92)
    out(" " + _verify_tier_logic(risk, pred_type, normal, cur_r, cur_c))

    # ── ① 단일 임계값 스윕 ────────────────────────────────────────────
    out("")
    out(" [1] 단일 임계값별 성능   (워처 규칙: 위험 >= 임계값  OR  예측 유형이 사기)")
    out("-" * 92)
    out(f" {'임계값':>6} {'알림':>7} {'적중TP':>7} {'미탐FN':>7} {'오탐FP':>7}"
        f" {'재현율':>8} {'정밀도':>8} {'F1':>7} {'하루알림':>9}")
    out("-" * 92)

    rows = []
    for th in SINGLE_STEPS:
        flagged = (risk >= th) | (pred_type != normal)
        tp = int((is_fraud & flagged).sum())
        fn = n_fraud - tp
        fp = int((~is_fraud & flagged).sum())
        n_alert = tp + fp
        recall = tp / n_fraud if n_fraud else 0.0
        prec = tp / n_alert if n_alert else 0.0
        f1 = 2 * prec * recall / (prec + recall) if (prec + recall) else 0.0
        per_day = n_alert / n_total * daily
        rows.append({"임계값": th, "알림건수": n_alert, "적중TP": tp, "미탐FN": fn,
                     "오탐FP": fp, "재현율": round(recall, 4), "정밀도": round(prec, 4),
                     "F1": round(f1, 4), "하루예상알림": round(per_day, 2)})
        mk = ""
        if abs(th - cur_r) < 0.026:
            mk = "  <- 현재 review"
        elif abs(th - cur_c) < 0.026:
            mk = "  <- 현재 confirm"
        out(f" {th:>6.2f} {n_alert:>7,} {tp:>7,} {fn:>7,} {fp:>7,}"
            f" {recall:>7.1%} {prec:>7.1%} {f1:>7.3f} {per_day:>8.1f}건{mk}")
    out("-" * 92)
    df = pd.DataFrame(rows)

    # ── ② 이중 임계값 조합 ────────────────────────────────────────────
    out("")
    out(" [2] 이중 임계값 조합   (1차 -> Slack만 · 2차 -> Slack+Email)")
    out("-" * 92)
    out(f" {'review':>7} {'confirm':>8} | {'Slack/일':>10} {'Email/일':>10} |"
        f" {'재현율':>8} {'미탐':>6} {'오탐/일':>9}")
    out("-" * 92)
    for th_r, th_c in sorted(set(DUAL_COMBOS) | {(round(cur_r, 2), round(cur_c, 2))}):
        t2 = max(th_r, th_c)
        # 🐛 FIX: confirm 은 순수 점수 기준이다. review 에만 '유형이 사기면 통과'
        #   안전망이 붙는다 (DetectService.notify_tier 와 동일).
        flag_r = (risk >= th_r) | (pred_type != normal)
        flag_c = (risk >= t2)
        tp_r = int((is_fraud & flag_r).sum())
        fp_r = int((~is_fraud & flag_r).sum())
        recall_r = tp_r / n_fraud if n_fraud else 0.0
        mk = "  <- 현재" if (abs(th_r - cur_r) < 0.005 and abs(th_c - cur_c) < 0.005) else ""
        out(f" {th_r:>7.2f} {th_c:>8.2f} |"
            f" {int(flag_r.sum())/n_total*daily:>9.1f}건"
            f" {int(flag_c.sum())/n_total*daily:>9.1f}건 |"
            f" {recall_r:>7.1%} {n_fraud-tp_r:>6,} {fp_r/n_total*daily:>8.1f}건{mk}")
    out("-" * 92)

    # ── ②-b 임계값이 실제로 움직이는 구간 ─────────────────────────────
    by_argmax = (pred_type != normal)
    n_argmax = int(by_argmax.sum())
    tp_argmax = int((is_fraud & by_argmax).sum())
    out("")
    out(" [2-b] 임계값은 무엇을 좌우하는가")
    out("-" * 92)
    out(f"   모델이 argmax로 '사기'라 부른 건    : {n_argmax:,}건 "
        f"(적중 {tp_argmax:,} · 오탐 {n_argmax-tp_argmax:,}) — 임계값과 무관하게 항상 알림")
    out(f"   임계값이 좌우하는 건 (유형은 정상)   : 아래 표")
    out("-" * 92)
    out(f"   {'임계값':>8} {'추가 알림':>10} {'추가 적중':>10} {'추가 오탐':>10}  누적 재현율")
    for th in (0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.70, 0.90):
        extra = (risk >= th) & ~by_argmax
        n_e = int(extra.sum())
        tp_e = int((is_fraud & extra).sum())
        rec = (tp_argmax + tp_e) / n_fraud if n_fraud else 0.0
        out(f"   {th:>8.2f} {n_e:>10,} {tp_e:>10,} {n_e-tp_e:>10,}  {rec:>10.1%}")
    out("-" * 92)

    # ── ②-c 놓친 사기의 정체 ──────────────────────────────────────────
    missed = is_fraud & ~by_argmax & (risk < 0.05)
    n_missed = int(missed.sum())
    out("")
    out(f" [2-c] 어떤 유형을 놓치고 있나  (임계값 0.05에서도 못 잡는 {n_missed}건)")
    out("-" * 92)
    if n_missed:
        vc = pd.Series(y_true[missed]).value_counts()
        tot = pd.Series(y_true[is_fraud]).value_counts()
        out(f"   {'유형':>6} {'놓친 수':>8} {'전체':>8} {'미탐률':>9}")
        for typ, cnt in vc.items():
            t_all = int(tot.get(typ, 0))
            out(f"   {typ:>6} {int(cnt):>8,} {t_all:>8,} {cnt/t_all if t_all else 0:>9.1%}")
        out("")
        out("   -> 이 유형들은 임계값을 아무리 낮춰도 잡히지 않습니다.")
        out("      모델이 '정상'이라고 확신하는 건이라, 재학습이나 규칙 보완이 필요합니다.")
    else:
        out("   임계값 0.05에서 모든 사기가 탐지됩니다.")
    out("-" * 92)

    # ── ③ 권장 ────────────────────────────────────────────────────────
    out("")
    out(" [3] 권장값")
    out("-" * 92)
    for lo, hi, label in ((2, 10, "하루 2~10건  (담당자 1명이 여유롭게 검토)"),
                          (10, 30, "하루 10~30건 (전담 검토 인력이 있을 때)")):
        band = df[(df["하루예상알림"] >= lo) & (df["하루예상알림"] <= hi)]
        if band.empty:
            out(f"   {label:<38} -> 해당 구간 없음")
            continue
        best = band.loc[band["재현율"].idxmax()]
        out(f"   {label:<38} -> review {best['임계값']:.2f}"
            f"  (사기 {int(best['적중TP'])}/{n_fraud}건 탐지 · 재현율 {best['재현율']:.1%}"
            f" · 하루 {best['하루예상알림']:.1f}건)")
    best_f1 = df.loc[df["F1"].idxmax()]
    out(f"   {'F1 최대 (통계적 균형점)':<38} -> {best_f1['임계값']:.2f}"
        f"  (F1 {best_f1['F1']:.3f} · 하루 {best_f1['하루예상알림']:.1f}건)")
    out("-" * 92)

    out("")
    out(" 해석 주의")
    out("   · 이 표는 검증셋(과거 데이터) 기준입니다. 실제 유입 데이터의 사기 비율이")
    out(f"     검증셋({n_fraud/n_total:.2%})과 다르면 하루 알림 건수도 그만큼 달라집니다.")
    out("   · confirm(2차)은 '틀리면 안 되는' 확정 통보이므로 정밀도가 높은 구간에서,")
    out("     review(1차)는 '놓치면 안 되는' 안전망이므로 재현율 위주로 고르세요.")
    out("   · 예측 유형이 사기면 점수가 낮아도 review로 올라갑니다. 그래서 임계값을")
    out("     아무리 올려도 알림이 0이 되지는 않습니다.")
    out("")
    out(" 적용 방법")
    out("   A. 대시보드 세션5 -> 워처 상태 -> 설정 -> 슬라이더 조정 -> 저장 (5초 내 반영)")
    out("   B. watcher_config.json 의 th_review / th_confirm 직접 수정 (재시작 불필요)")
    out("=" * 92)

    if save:
        try:
            df.to_csv("threshold_report.csv", index=False, encoding="utf-8-sig")
            Path("threshold_report.txt").write_text("\n".join(lines), encoding="utf-8")
            print("\n 저장: threshold_report.csv · threshold_report.txt")
        except Exception as e:
            print(f"\n [!] 파일 저장 실패: {e}")

    return df


def main():
    ap = argparse.ArgumentParser(description="임계값별 탐지·알림 실측 리포트")
    ap.add_argument("--x", default="data/X_va.parquet")
    ap.add_argument("--y", default="data/y_va.parquet")
    ap.add_argument("--models", default="models/")
    ap.add_argument("--daily", type=int, default=300, help="하루 평균 유입 건수 (기본 300)")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()
    try:
        run(a.x, a.y, a.models, a.daily, save=not a.no_save)
    except FileNotFoundError as e:
        print(f"파일을 찾지 못했습니다: {e}")
        print("경로를 지정하세요. 예: --x data/X_va.parquet --y data/y_va.parquet")
        sys.exit(1)
    except Exception as e:
        print(f"{type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""判别器：把鼠标记录切成 30 秒窗口，提取统计特征，训练分类器区分「真人 / 脚本」。

    python -X utf8 scripts/train_discriminator.py --human test/human1 \
        --generator clone=test/clone1 --generator old=test/stable1

输出：
  * 每个生成器 vs 真人的交叉验证 AUC（越接近 0.5 越难区分，说明越像人）
  * 哪些特征最能把我们区分出来（特征重要性）

为什么按窗口：一份文件只有一个标签，样本太少；切成 30 秒窗口后每份文件能出几十个样本，
分类器才有意义。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent

FEATURES = [
    "events_per_s", "move_per_s", "click_per_s",
    "step_px_med", "step_ms_med", "bend_med", "bend_p90",
    "press_ms_med", "press_ms_p90", "gap_med", "gap_p90",
    "x_std", "y_std", "move_burst_len",
]


def load(path: pathlib.Path) -> list[dict]:
    if path.is_dir():
        path = path / "mouse.jsonl"
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def window_features(rows: list[dict]) -> dict:
    if len(rows) < 10:
        return {}
    ts = [r["ts"] for r in rows]
    dur = max(ts) - min(ts)
    if dur < 3:
        return {}
    moves = [r for r in rows if r.get("ev") == "move"]
    downs = [r for r in rows if r.get("ev") == "ldown"]

    steps, step_t = [], []
    for a, b in zip(moves, moves[1:]):
        d = math.hypot(b["cx"] - a["cx"], b["cy"] - a["cy"])
        dt = b["ts"] - a["ts"]
        if d > 0 and 0 < dt < 0.2:
            steps.append(d)
            step_t.append(dt * 1000.0)

    # 弯曲度（每段 move burst）
    bursts, cur = [], []
    for r in moves:
        if cur and r["ts"] - cur[-1]["ts"] > 0.3:
            if len(cur) >= 5:
                bursts.append(cur)
            cur = []
        cur.append(r)
    if len(cur) >= 5:
        bursts.append(cur)
    devs = []
    for b in bursts:
        x0, y0 = b[0]["cx"], b[0]["cy"]
        x1, y1 = b[-1]["cx"], b[-1]["cy"]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 40:
            continue
        dx, dy = x1 - x0, y1 - y0
        devs.append(max(abs((p["cx"] - x0) * dy - (p["cy"] - y0) * dx) / L for p in b) / L)

    # 按下时长
    presses, down = [], None
    for r in rows:
        if r["ev"] == "ldown":
            down = r
        elif r["ev"] == "lup" and down is not None:
            dt = r["ts"] - down["ts"]
            if 0 < dt < 1.0:
                presses.append(dt * 1000.0)
            down = None

    gaps = [b - a for a, b in zip([r["ts"] for r in downs], [r["ts"] for r in downs][1:])]

    def med(v, default=0.0):
        return float(np.median(v)) if v else default

    def p90(v):
        return float(np.percentile(v, 90)) if v else 0.0

    xs = [r["cx"] for r in downs]
    ys = [r["cy"] for r in downs]
    return {
        "events_per_s": len(rows) / dur,
        "move_per_s": len(moves) / dur,
        "click_per_s": len(downs) / dur,
        "step_px_med": med(steps),
        "step_ms_med": med(step_t),
        "bend_med": med(devs),
        "bend_p90": p90(devs),
        "press_ms_med": med(presses),
        "press_ms_p90": p90(presses),
        "gap_med": med(gaps),
        "gap_p90": p90(gaps),
        "x_std": float(np.std(xs)) if len(xs) > 1 else 0.0,
        "y_std": float(np.std(ys)) if len(ys) > 1 else 0.0,
        "move_burst_len": med([len(b) for b in bursts]),
    }


def windows(rows: list[dict], size: float = 30.0, stride: float = 15.0) -> list[dict]:
    if not rows:
        return []
    t0, t1 = rows[0]["ts"], rows[-1]["ts"]
    out = []
    t = t0
    while t + size <= t1:
        win = [r for r in rows if t <= r["ts"] < t + size]
        f = window_features(win)
        if f:
            out.append(f)
        t += stride
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--human", required=True)
    ap.add_argument("--generator", action="append", default=[],
                    help="名字=目录，可重复")
    a = ap.parse_args()

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import cross_val_predict

    human = windows(load(ROOT / a.human))
    if not human:
        print("真人样本窗口不够")
        return 1
    print(f"真人窗口 {len(human)} 个（{a.human}）")

    gens = []
    for spec in a.generator:
        name, _, path = spec.partition("=")
        w = windows(load(ROOT / path))
        print(f"{name}: {len(w)} 个窗口（{path}）")
        gens.append((name, w))

    for name, w in gens:
        if not w:
            continue
        X = np.array([[f[k] for k in FEATURES] for f in human + w])
        y = np.array([0] * len(human) + [1] * len(w))
        clf = RandomForestClassifier(n_estimators=300, random_state=0)
        p = cross_val_predict(clf, X, y, cv=5, method="predict_proba")[:, 1]
        auc = roc_auc_score(y, p)
        print(f"\n{name} vs 真人：AUC = {auc:.3f}"
              f"（{'分得很开' if auc > 0.85 else '有点像了' if auc > 0.7 else '很难区分'}）")

        clf.fit(X, y)
        imp = sorted(zip(FEATURES, clf.feature_importances_), key=lambda t: -t[1])[:5]
        print("  最能区分的前 5 个特征：")
        for k, v in imp:
            print(f"    {k:<16}{v:.3f}")

        # 小样本下 AUC 容易虚高（这里一律 1.000），所以再给一个更直观的
        # 「整体偏差」：每个特征与真人的偏离，除以真人的 p10~p90 跨度，再平均。
        human_arr = {k: np.array([f[k] for f in human]) for k in FEATURES}
        devs = []
        worst = []
        for k in FEATURES:
            h = human_arr[k]
            span = np.percentile(h, 90) - np.percentile(h, 10)
            span = span if span > 1e-9 else max(1e-9, abs(np.median(h)) * 0.1 + 1e-9)
            g = np.median([f[k] for f in w])
            d = abs(g - np.median(h)) / span
            devs.append(d)
            worst.append((k, d))
        print(f"  整体偏差 {np.mean(devs):.2f}（越小越像；<0.5 算接近）")
        for k, d in sorted(worst, key=lambda t: -t[1])[:3]:
            print(f"    偏得最多：{k:<16}{d:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""训练一个"轨迹生成"小模型（行为克隆的神经版本），并生成样本供判别器评分。

    python -X utf8 scripts/train_move_model.py --train          # 训练 + 保存
    python -X utf8 scripts/train_move_model.py --gen test/neural1 --moves 70

思路（有意保持小）：输入是「目标距离」，输出是 16 个归一化路点（along, perp），
训练目标是 outputs = 模板里等间隔重采样的 16 个点。这样模型学的是"从 A 到 B 该走什么形状"，
而不是记住某一条具体轨迹；时间节奏单独用真人样本的分布采样。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import random

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / "data" / "move_templates.json"
MODEL = ROOT / "data" / "move_model.joblib"
N_POINTS = 16


def resample(pts: list[tuple[float, float]], n: int = N_POINTS) -> np.ndarray:
    """把模板按"沿程进度"重采样成固定 n 个点（沿 x 均匀取）。"""
    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)
    grid = np.linspace(0.0, 1.0, n)
    # xs 可能不是单调的（人会有回退），用单调包络做插值索引
    order = np.argsort(xs)
    x_sorted, y_sorted = xs[order], ys[order]
    xs_u, idx = np.unique(x_sorted, return_index=True)
    y_u = y_sorted[idx]
    ys_interp = np.interp(grid, xs_u, y_u)
    return np.stack([grid, ys_interp], axis=1)


def train() -> None:
    """训练：输入 log 距离，输出 16 个归一化路点（32 维）。

    先标准化（否则 relu 网络在这种量级上直接发散），再训一个小 MLP；
    同时用 Ridge 做基线，取训练集 R2 更好的那个存盘。
    """
    import joblib
    from sklearn.linear_model import Ridge
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    data = json.loads(LIB.read_text(encoding="utf-8"))
    X, Y = [], []
    for t in data["templates"]:
        X.append([math.log(max(1.0, t["len_px"]))])
        Y.append(resample(t["pts"]).reshape(-1))
    X = np.array(X, dtype=float)
    Y = np.array(Y, dtype=float)
    print(f"训练样本 {len(X)} 条，输入 1 维（log 距离），输出 {Y.shape[1]} 维")

    mlp = make_pipeline(StandardScaler(),
                        MLPRegressor(hidden_layer_sizes=(48, 48), activation="tanh",
                                     max_iter=6000, learning_rate_init=0.01,
                                     random_state=0))
    mlp.fit(X, Y)
    r2_mlp = mlp.score(X, Y)

    ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    ridge.fit(X, Y)
    r2_ridge = ridge.score(X, Y)
    print(f"MLP 训练集 R2 = {r2_mlp:.3f}；Ridge 基线 R2 = {r2_ridge:.3f}")

    best = mlp if r2_mlp >= r2_ridge else ridge
    if best is ridge:
        print("（MLP 不如 Ridge，存 Ridge —— 小样本下这是正常结果）")
    joblib.dump(best, MODEL)
    print(f"模型 -> {MODEL}（{'MLP' if best is mlp else 'Ridge'}）")


def gen(out: str, moves: int) -> int:
    import joblib

    if not MODEL.exists():
        print("还没有模型，先跑 --train")
        return 1
    model = joblib.load(MODEL)
    data = json.loads(LIB.read_text(encoding="utf-8"))
    presses = data.get("press_ms") or [65.0]

    d = ROOT / out
    d.mkdir(parents=True, exist_ok=True)
    path = d / "mouse.jsonl"
    rng = random.Random(3)
    seq = 0
    ts = 1_000.0
    rows = []

    def emit(ev: str, cx: int, cy: int, dt: float) -> None:
        nonlocal seq, ts
        seq += 1
        ts += dt
        rows.append({"seq": seq, "ts": round(ts, 6), "t": "00:00:00", "ev": ev,
                     "sx": cx, "sy": cy, "cx": cx, "cy": cy, "injected": 1})

    cur = (900, 500)
    for _ in range(moves):
        dist = math.exp(rng.uniform(math.log(60), math.log(900)))
        ang = rng.uniform(0, 2 * math.pi)
        tx = int(cur[0] + dist * math.cos(ang))
        ty = int(cur[1] + dist * math.sin(ang))
        tx = max(50, min(1850, tx))
        ty = max(80, min(900, ty))

        pts = model.predict([[math.log(max(1.0, math.hypot(tx - cur[0], ty - cur[1])))]]).reshape(-1, 2)
        real = np.hypot(tx - cur[0], ty - cur[1])
        ux, uy = (tx - cur[0]) / (real or 1.0), (ty - cur[1]) / (real or 1.0)
        for i, (along, perp) in enumerate(pts):
            px = int(cur[0] + ux * along * real - uy * perp * real)
            py = int(cur[1] + uy * along * real + ux * perp * real)
            emit("move", px, py, rng.uniform(0.006, 0.011))
        cur = (tx, ty)
        if rng.random() < 0.6:
            hold = rng.choice(presses) / 1000.0
            emit("ldown", tx, ty, rng.uniform(0.05, 0.2))
            emit("lup", tx, ty, hold)
        ts += rng.uniform(0.35, 1.2)

    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"生成 {len(rows)} 个事件 -> {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--gen", default="")
    ap.add_argument("--moves", type=int, default=70)
    a = ap.parse_args()
    if a.train:
        train()
    if a.gen:
        return gen(a.gen, a.moves)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

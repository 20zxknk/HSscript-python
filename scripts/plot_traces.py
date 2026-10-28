"""把四种轨迹画出来对比：真人 / LSTM 生成 / 模板重放 / 参数化(贝塞尔)。

    python -X utf8 scripts/plot_traces.py --out .captures/traces.png
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / "data" / "move_templates.json"
LSTM = ROOT / "data" / "lstm_move.pt"
N = 8


def load_templates():
    return json.loads(LIB.read_text(encoding="utf-8"))["templates"]


def to_xy(t_pts, length=1.0):
    return np.array([[p[0] * length, p[1] * length] for p in t_pts], dtype=float)


def lstm_paths(n=N, steps=60):
    """用序列输入的 LSTM 自回归生成轨迹（每步都看前 40 步历史）。"""
    import torch

    sys.path.insert(0, str(ROOT / "scripts"))
    from lstm_move import HIST, build, pick_device

    dev = pick_device()
    net = build().to(dev)
    net.load_state_dict(torch.load(LSTM, map_location=dev))
    net.eval()
    out = []
    for _ in range(n):
        along, perp = 0.0, 0.0
        pts = [(0.0, 0.0)]
        hist = []
        for _ in range(steps * 2):
            hist.append([along, perp, along, perp, 1 - along, -perp, along])
            h = hist[-HIST:]
            if len(h) < HIST:
                h = [[0.0] * 7] * (HIST - len(h)) + h
            x = torch.tensor([h], device=dev)
            with torch.no_grad():
                da, dp = net(x)[0, -1].tolist()
            # 闭环修正：纯自回归会累积漂移，把剩余量按剩余步数摊进去
            left = max(1.0, steps - len(pts))
            along = min(1.0, along + max(0.0, da) + 0.35 * (1.0 - along) / left)
            perp += dp + 0.35 * (-perp) / left
            pts.append((along, perp))
            if along >= 1.0:
                break
        out.append(np.array(pts))
    return out


def bezier_paths(n=N, seed=1):
    """参数化版本：贝塞尔 + 钟形速度（和 mouse.py 里 move_to 同算法）。"""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        dist = 1.0
        steps = 26
        bow = dist * rng.uniform(0.02, 0.08) * rng.choice((-1.0, 1.0))
        off1 = bow * rng.uniform(0.55, 1.0)
        off2 = bow * rng.uniform(0.55, 1.0)
        p0 = np.array([0.0, 0.0])
        p3 = np.array([dist, 0.0])
        nrm = np.array([0.0, 1.0])
        c1 = p0 + (p3 - p0) * 0.25 + nrm * off1
        c2 = p0 + (p3 - p0) * 0.75 + nrm * off2
        pts = [p0]
        for k in range(1, steps + 1):
            u = k / steps
            t = 0.5 - 0.5 * math.cos(math.pi * u)
            b = ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * c1 + 3 * (1 - t) * (t ** 2) * c2 + (t ** 3) * p3
            pts.append(b)
        out.append(np.array(pts))
    return out


def bend_of(arr):
    x0, y0 = arr[0]
    x1, y1 = arr[-1]
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    dx, dy = x1 - x0, y1 - y0
    return max(abs((p[0] - x0) * dy - (p[1] - y0) * dx) / L for p in arr) / L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".captures/traces.png")
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    tpls = load_templates()
    rng = random.Random(0)
    human = [to_xy(t["pts"]) for t in rng.sample(tpls, N)]
    clone = [to_xy(rng.choice(tpls)["pts"]) for _ in range(N)]
    neural = lstm_paths()
    param = bezier_paths()

    rows = [("真人（你录的）", human), ("LSTM 生成", neural),
            ("模板重放（克隆）", clone), ("参数化（贝塞尔）", param)]
    fig, axes = plt.subplots(len(rows), N, figsize=(2.2 * N, 1.9 * len(rows)))
    for r, (name, paths) in enumerate(rows):
        bends = [bend_of(p) for p in paths]
        for c in range(N):
            ax = axes[r][c]
            p = paths[c]
            ax.plot(p[:, 0], p[:, 1], lw=1.2)
            ax.plot([0], [0], "o", ms=3, color="tab:green")
            ax.plot([p[-1, 0]], [p[-1, 1]], "o", ms=3, color="tab:red")
            ax.set_xlim(-0.25, 1.25)
            ax.set_ylim(-0.7, 0.7)
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            if c == 0:
                ax.set_ylabel(name, fontsize=9)
        axes[r][0].text(-0.2, 0.55, f"弯曲度中位 {np.median(bends):.3f}",
                        fontsize=8, color="tab:blue")
    plt.suptitle("同一条 起点(绿)→终点(红) 的路径：真人 vs 三种生成器", fontsize=12)
    plt.tight_layout()
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=110)
    print(f"图 -> {out}")
    for name, paths in rows:
        print(f"  {name}: 弯曲度中位 {np.median([bend_of(p) for p in paths]):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

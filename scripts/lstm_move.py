"""LSTM 版轨迹生成（行为克隆的序列模型），用来和模板重放对比。

    python -X utf8 scripts/lstm_move.py --train            # 训练 + 保存 data/lstm_move.pt
    python -X utf8 scripts/lstm_move.py --gen test/lstm1 --moves 70

数据只有 102 条模板，所以先做**增强**（镜像 / 时间缩放 / 子段重采样），再训练。
模型是自回归的下一小步预测：
    输入  [Δalong, Δperp, along, perp, 剩余along, 剩余perp, 进度]
    输出  [Δalong, Δperp]
生成时从 (0,0) 出发、按"剩余量"逐步走，直到走完 1.0。
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
MODEL = ROOT / "data" / "lstm_move.pt"
N_STEPS = 60


# ---------------- 数据 ----------------
def resample(pts, n=N_STEPS):
    xs = np.array([p[0] for p in pts], dtype=np.float32)
    ys = np.array([p[1] for p in pts], dtype=np.float32)
    grid = np.linspace(0.0, 1.0, n)
    order = np.argsort(xs)
    xs_u, idx = np.unique(xs[order], return_index=True)
    y_u = ys[order][idx]
    return np.stack([grid, np.interp(grid, xs_u, y_u)], axis=1).astype(np.float32)


def augment(seq):
    """镜像 + 时间缩放（沿程重采样）+ 子段：把 102 条扩成几千条。"""
    out = []
    for flip in (1.0, -1.0):
        s = seq.copy()
        s[:, 1] *= flip
        out.append(s)
        # 子段：随机取 55%~100% 的路径，重新归一化到 0..1
        for _ in range(4):
            a = np.random.uniform(0.0, 0.35)
            b = np.random.uniform(max(a + 0.5, 0.6), 1.0)
            m = (s[:, 0] >= a) & (s[:, 0] <= b)
            if m.sum() < 12:
                continue
            sub = s[m].copy()
            sub[:, 0] = (sub[:, 0] - sub[0, 0]) / max(1e-6, sub[-1, 0] - sub[0, 0])
            sub = resample(sub.tolist(), N_STEPS)
            out.append(sub)
    return out


HIST = 40


def make_xy(seqs):
    """每个样本 = 前 HIST 步的轨迹（不足则左补零）+ 下一步的增量。"""
    X, Y = [], []
    for s in seqs:
        d = np.diff(s, axis=0)
        feat = np.zeros((len(s), 7), dtype=np.float32)
        for i in range(len(s)):
            feat[i] = [s[i, 0], s[i, 1], s[i, 0], s[i, 1], 1 - s[i, 0], -s[i, 1], s[i, 0]]
        for i in range(len(d)):
            hist = feat[max(0, i - HIST + 1):i + 1]
            if len(hist) < HIST:
                hist = np.vstack([np.zeros((HIST - len(hist), 7), dtype=np.float32), hist])
            X.append(hist)
            Y.append([d[i, 0], d[i, 1]])
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)


# ---------------- 模型 ----------------
def build():
    from torch import nn

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(input_size=7, hidden_size=64, num_layers=2,
                                batch_first=True, dropout=0.1)
            self.head = nn.Linear(64, 2)

        def forward(self, x):           # x: (B, L, 7)
            out, _ = self.lstm(x)
            return self.head(out)

    return Net()


def pick_device():
    import torch
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def train(epochs: int = 400) -> None:
    import torch

    dev = pick_device()
    print(f"设备: {dev}" + (f"（{torch.cuda.get_device_name(0)}）" if dev.type == "cuda" else ""))

    raw = json.loads(LIB.read_text(encoding="utf-8"))["templates"]
    seqs = []
    for t in raw:
        seqs.append(resample(t["pts"]))
    aug = []
    ids = list(range(len(seqs)))
    random.shuffle(ids)
    cut = max(1, len(ids) // 5)
    val_ids, train_ids = ids[:cut], ids[cut:]
    for i in train_ids:
        aug.extend(augment(seqs[i]))
    val_aug = []
    for i in val_ids:
        val_aug.extend(augment(seqs[i]))

    Xtr, Ytr = make_xy(aug)
    Xva, Yva = make_xy(val_aug)
    print(f"训练序列 {len(aug)} 条 / 样本 {len(Xtr)}；验证序列 {len(val_aug)} 条 / {len(Xva)}")

    Xtr = torch.tensor(Xtr).to(dev)     # (N, HIST, 7)
    Ytr = torch.tensor(Ytr).to(dev)
    Xva = torch.tensor(Xva).to(dev)
    Yva = torch.tensor(Yva).to(dev)

    net = build().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=3e-3)
    lossf = torch.nn.MSELoss()
    n = len(Xtr)
    for ep in range(epochs):
        perm = torch.randperm(n)
        for i in range(0, n, 512):
            idx = perm[i:i + 512]
            opt.zero_grad()
            pred = net(Xtr[idx])[:, -1]          # 只看最后一步的预测
            loss = lossf(pred, Ytr[idx])
            loss.backward()
            opt.step()
        if (ep + 1) % 100 == 0:
            with torch.no_grad():
                tr = lossf(net(Xtr[:4096])[:, -1], Ytr[:4096]).item()
                va = lossf(net(Xva)[:, -1], Yva).item()
            print(f"  epoch {ep+1:4d}  train {tr:.6f}  val {va:.6f}")
    torch.save(net.state_dict(), MODEL)
    print(f"模型 -> {MODEL}")


# ---------------- 生成 ----------------
def gen(out: str, moves: int) -> int:
    import torch

    dev = pick_device()
    net = build().to(dev)
    net.load_state_dict(torch.load(MODEL, map_location=dev))
    net.eval()
    data = json.loads(LIB.read_text(encoding="utf-8"))
    presses = data.get("press_ms") or [65.0]
    lengths = [len(t["pts"]) for t in data["templates"]]
    d = ROOT / out
    d.mkdir(parents=True, exist_ok=True)
    path = d / "mouse.jsonl"
    rng = random.Random(5)
    rows, seq, ts = [], 0, 1000.0

    def emit(ev, cx, cy, dt):
        nonlocal seq, ts
        seq += 1
        ts += dt
        rows.append({"seq": seq, "ts": round(ts, 6), "t": "00:00:00", "ev": ev,
                     "sx": cx, "sy": cy, "cx": cx, "cy": cy, "injected": 1})

    cur = (900, 500)
    for _ in range(moves):
        dist = math.exp(rng.uniform(math.log(60), math.log(900)))
        ang = rng.uniform(0, 2 * math.pi)
        tx, ty = cur[0] + dist * math.cos(ang), cur[1] + dist * math.sin(ang)
        tx = max(50, min(1850, tx))
        ty = max(80, min(900, ty))
        real = math.hypot(tx - cur[0], ty - cur[1]) or 1.0
        ux, uy = (tx - cur[0]) / real, (ty - cur[1]) / real

        along, perp = 0.0, 0.0
        n = rng.choice(lengths)
        hist = []
        for _ in range(n):
            hist.append([along, perp, along, perp, 1 - along, -perp, along])
            h = hist[-HIST:]
            if len(h) < HIST:
                h = [[0.0] * 7] * (HIST - len(h)) + h
            x = torch.tensor([h], device=dev)
            with torch.no_grad():
                d_along, d_perp = net(x)[0, -1].tolist()
            along = min(1.02, along + max(0.0, d_along))
            perp += d_perp
            px = int(cur[0] + ux * along * real - uy * perp * real)
            py = int(cur[1] + uy * along * real + ux * perp * real)
            emit("move", px, py, rng.uniform(0.006, 0.011))
            if along >= 1.0:
                break
        cur = (tx, ty)
        emit("move", tx, ty, 0.008)
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
    ap.add_argument("--epochs", type=int, default=400)
    ap.add_argument("--gen", default="")
    ap.add_argument("--moves", type=int, default=70)
    a = ap.parse_args()
    if a.train:
        train(a.epochs)
    if a.gen:
        return gen(a.gen, a.moves)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

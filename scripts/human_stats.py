"""对比「真人操作」和「脚本操作」的鼠标统计量，用来校准 Humanizer。

    python -X utf8 scripts/human_stats.py test/human1/mouse.jsonl test/stable1/mouse.jsonl
    python -X utf8 scripts/human_stats.py test/human1       # 只给一个目录也行

输出（并排对照）：
    事件数 / 时长 / 每秒事件数
    按下-抬起时长 中位与 p90
    移动步长 中位 / 每步耗时 中位
    路径弯曲度（每段移动偏离直线 / 段长）
    点击落点离散度（同一区域的点击标准差）
    动作间隔（相邻两次按下之间）中位与 p90
"""
from __future__ import annotations

import json
import math
import pathlib
import statistics
import sys


def load(path: pathlib.Path) -> list[dict]:
    if path.is_dir():
        path = path / "mouse.jsonl"
    rows = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def stats(rows: list[dict]) -> dict:
    if not rows:
        return {}
    ts = [r["ts"] for r in rows]
    dur = max(ts) - min(ts)

    # 按下-抬起
    presses = []
    down_at = None
    for r in rows:
        if r["ev"] == "ldown":
            down_at = r
        elif r["ev"] == "lup" and down_at is not None:
            dt = r["ts"] - down_at["ts"]
            if 0 < dt < 1.0:
                presses.append(dt * 1000.0)
            down_at = None

    # 移动步长/每步耗时
    moves = [r for r in rows if r["ev"] == "move"]
    steps, step_t = [], []
    for a, b in zip(moves, moves[1:]):
        d = math.hypot(b["cx"] - a["cx"], b["cy"] - a["cy"])
        dt = b["ts"] - a["ts"]
        if 0 < dt < 0.2 and d > 0:
            steps.append(d)
            step_t.append(dt * 1000.0)

    # 弯曲度：把连续 move 按 0.3s 间隔切段，算最大偏离/段长
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
        if L < 50:
            continue
        dx, dy = x1 - x0, y1 - y0
        dmax = max(abs((p["cx"] - x0) * dy - (p["cy"] - y0) * dx) / L for p in b)
        devs.append(dmax / L)

    # 动作间隔（相邻两次按下）
    downs = [r["ts"] for r in rows if r["ev"] == "ldown"]
    gaps = [b - a for a, b in zip(downs, downs[1:]) if 0.1 < b - a < 600]

    # 点击落点离散度
    xs = [r["cx"] for r in rows if r["ev"] == "ldown"]
    ys = [r["cy"] for r in rows if r["ev"] == "ldown"]

    def p90(v):
        return statistics.quantiles(v, n=10)[-1] if len(v) >= 10 else (max(v) if v else 0)

    return {
        "事件数": len(rows),
        "时长(s)": round(dur, 1),
        "每秒事件": round(len(rows) / dur, 1) if dur else 0,
        "按下时长 中位(ms)": round(statistics.median(presses), 1) if presses else 0,
        "按下时长 p90(ms)": round(p90(presses), 1) if presses else 0,
        "每步位移 中位(px)": round(statistics.median(steps), 1) if steps else 0,
        "每步耗时 中位(ms)": round(statistics.median(step_t), 1) if step_t else 0,
        "弯曲度 中位": round(statistics.median(devs), 3) if devs else 0,
        "动作间隔 中位(s)": round(statistics.median(gaps), 2) if gaps else 0,
        "动作间隔 p90(s)": round(p90(gaps), 2) if gaps else 0,
        "落点 x 标准差": round(statistics.pstdev(xs), 1) if len(xs) > 1 else 0,
        "落点 y 标准差": round(statistics.pstdev(ys), 1) if len(ys) > 1 else 0,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    files = [pathlib.Path(p) for p in sys.argv[1:]]
    results = [(f.name if f.is_dir() else f.stem, stats(load(f))) for f in files]
    keys = []
    for _, s in results:
        for k in s:
            if k not in keys:
                keys.append(k)
    head = "指标".ljust(18) + "".join(n.ljust(14) for n, _ in results)
    print(head)
    print("-" * len(head))
    for k in keys:
        line = str(k).ljust(18)
        for _, s in results:
            line += str(s.get(k, "-")).ljust(14)
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""从真人的 mouse.jsonl 里提取「移动片段」，归一化成可复用的模板库。

    python -X utf8 scripts/extract_moves.py test/human1/mouse.jsonl --out data/move_templates.json

做法：
  1. 连续 move 事件按「间隔 < 0.3s」切成片段；
  2. 丢掉总路程 < 40px 的片段（那只是手抖，不是一次有目标的移动）；
  3. 每条片段归一化：起点搬到原点、按终点方向旋转到 +x 轴、再缩放到长度 1；
  4. 保存：归一化轨迹点列、总时长、每步时间，以及原始长度/角度。

这样一条模板可以重放到任意起点→终点：旋转回去、缩放到目标距离即可。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent


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


def segments(rows: list[dict], gap: float = 0.3, min_len: float = 40.0) -> list[list[dict]]:
    moves = [r for r in rows if r.get("ev") == "move" and not r.get("injected")]
    out, cur = [], []
    for r in moves:
        if cur and r["ts"] - cur[-1]["ts"] > gap:
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)

    keep = []
    for seg in out:
        if len(seg) < 6:
            continue
        length = sum(math.hypot(seg[i]["cx"] - seg[i - 1]["cx"], seg[i]["cy"] - seg[i - 1]["cy"])
                     for i in range(1, len(seg)))
        if length < min_len:
            continue
        keep.append(seg)
    return keep


def press_durations(rows: list[dict]) -> list[float]:
    """真人按下到抬起（毫秒）：用来复现点击节奏（双峰：快点 / 深思）。"""
    out, down = [], None
    for r in rows:
        if r.get("ev") == "ldown" and not r.get("injected"):
            down = r
        elif r.get("ev") == "lup" and down is not None:
            dt = (r["ts"] - down["ts"]) * 1000.0
            if 0 < dt < 600:
                out.append(round(dt, 1))
            down = None
    return out


def normalize(seg: list[dict]) -> dict:
    x0, y0 = seg[0]["cx"], seg[0]["cy"]
    x1, y1 = seg[-1]["cx"], seg[-1]["cy"]
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 1.0:
        return {}
    ux, uy = (x1 - x0) / L, (y1 - y0) / L

    pts, times = [], []
    for i, r in enumerate(seg):
        dx, dy = r["cx"] - x0, r["cy"] - y0
        # 投影到「前进方向」与「法向」
        along = (dx * ux + dy * uy) / L
        perp = (-dx * uy + dy * ux) / L
        pts.append((round(along, 4), round(perp, 4)))
        if i:
            times.append(round(seg[i]["ts"] - seg[i - 1]["ts"], 4))

    # 一次"有目标的移动"不该跑出这么远：法向 > 1.2 或沿程 > 2 的是拼接错的片段
    max_perp = max(abs(p[1]) for p in pts)
    max_along = max(p[0] for p in pts)
    if max_perp > 1.2 or max_along > 2.0:
        return {}

    return {
        "n": len(pts),
        "len_px": round(L, 1),
        "dur": round(seg[-1]["ts"] - seg[0]["ts"], 3),
        "pts": pts,
        "steps": times,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", default="data/move_templates.json")
    ap.add_argument("--gap", type=float, default=0.3)
    ap.add_argument("--min-len", type=float, default=40.0)
    a = ap.parse_args()

    rows = load(ROOT / a.source)
    segs = segments(rows, a.gap, a.min_len)
    tpls = [t for t in (normalize(s) for s in segs) if t]
    dropped = len(segs) - len(tpls)
    if not tpls:
        print("没有提取到移动片段")
        return 1

    lens = [t["len_px"] for t in tpls]
    durs = [t["dur"] for t in tpls]
    ns = [t["n"] for t in tpls]
    perp = [max(abs(p[1]) for p in t["pts"]) for t in tpls]

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    presses = press_durations(rows)
    out.write_text(json.dumps({"templates": tpls, "press_ms": presses},
                              ensure_ascii=False), encoding="utf-8")

    print(f"片段 {len(tpls)} 条（丢弃 {dropped} 条异常的）-> {out}")
    print(f"  长度  中位 {statistics.median(lens):.0f}px  p90 {sorted(lens)[int(len(lens)*0.9)]:.0f}px")
    print(f"  时长  中位 {statistics.median(durs)*1000:.0f}ms")
    print(f"  采样点 中位 {statistics.median(ns):.0f}")
    print(f"  弯曲度 中位 {statistics.median(perp):.3f}（法向最大偏移 / 段长）")
    if presses:
        ps = sorted(presses)
        print(f"  按下时长 {len(ps)} 个：中位 {statistics.median(ps):.0f}ms "
              f"p90 {ps[int(len(ps)*0.9)]:.0f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""把 test/ 里的三份记录按时间对齐，打印"盒子说了什么 / 鼠标点了哪 / 游戏发生了什么"。

    python scripts/join3.py test                 # 全量，每步一块
    python scripts/join3.py test --from 01:43:00 --to 01:45:00
    python scripts/join3.py test --grep CAP_405  # 只看含这张牌的步骤

对齐规则（都是本机本地时间）：
    推荐 t  ──┬──> 鼠标事件 t ∈ [t, t+3.5s] 且 injected=1（脚本发的）
              └──> 叙述行 t ∈ [t, t+5.0s]
鼠标"点了哪"取这一小段里的按下点（ldown/rdown），"落在哪"取最后的抬起点（lup/rup）。
"""
from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

TS_LINE = re.compile(r"^`(\d\d:\d\d:\d\d\.\d+)`\s+(.*)$")


def load_recs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def load_story(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    out = []
    for line in io.open(path, encoding="utf-8"):
        m = TS_LINE.match(line.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def secs(t: str) -> float:
    """'HH:MM:SS.mmm' -> 秒（只用于同一天内比较）。"""
    try:
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return 0.0


def fmt_plan(p: dict) -> str:
    bits = [p.get("action") or "?"]
    if p.get("card_id"):
        bits.append(str(p["card_id"]))
    if p.get("card_name") and p.get("card_name") != p.get("card_id"):
        bits.append(f"「{p['card_name']}」")
    if p.get("hand_position"):
        bits.append(f"手{p['hand_position']}")
    if p.get("board_position"):
        bits.append(f"场{p['board_position']}")
    if p.get("target") and p.get("target") != "board":
        bits.append(f"目标={p['target']}:{p.get('target_position')}")
    return " ".join(bits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default="test")
    ap.add_argument("--from", dest="t0", default="")
    ap.add_argument("--to", dest="t1", default="")
    ap.add_argument("--grep", default="")
    ap.add_argument("--window-mouse", type=float, default=3.5)
    ap.add_argument("--window-story", type=float, default=5.0)
    args = ap.parse_args()

    d = Path(args.dir)
    recs = load_recs(d / "recommendations.jsonl")
    story = load_story(d / "powerlog_story.md")
    mouse: list[dict] = []
    mpath = d / "mouse.jsonl"
    if mpath.exists():
        for line in io.open(mpath, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    mouse.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    print(f"载入：推荐 {len(recs)} 条 / 鼠标 {len(mouse)} 条 / 叙述 {len(story)} 行\n")

    shown = 0
    for r in recs:
        t = r.get("t", "")
        if args.t0 and secs(t) < secs(args.t0):
            continue
        if args.t1 and secs(t) > secs(args.t1):
            continue
        plans = r.get("plans") or []
        head = f"[{t}] 盒子 n={r.get('n')}: " + ("；".join(fmt_plan(p) for p in plans) or "(空)")
        if args.grep and args.grep not in head:
            continue

        win_m = [m for m in mouse
                 if m.get("injected") == 1 and 0 <= secs(m.get("t", "00:00:00")) - secs(t) <= args.window_mouse]
        downs = [m for m in win_m if m.get("ev") in ("ldown", "rdown")]
        ups = [m for m in win_m if m.get("ev") in ("lup", "rup")]
        win_s = [(st, tx) for st, tx in story if 0 <= secs(st) - secs(t) <= args.window_story]

        print(head)
        if downs or ups:
            seq = " → ".join(f"{m['ev']}({m['sx']},{m['sy']}/客户区 {m['cx']},{m['cy']})"
                             for m in (downs + ups))
            print(f"    鼠标: {seq}")
            print(f"    （移动 {len(win_m)} 条，其中按下 {len(downs)} 次）")
        else:
            print("    鼠标: 该窗口内没有脚本点击")
        if win_s:
            for st, tx in win_s:
                print(f"    游戏: `{st}` {tx}")
        else:
            print("    游戏: 该窗口内没有叙述事件")
        print()
        shown += 1

    print(f"共展示 {shown} 步")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

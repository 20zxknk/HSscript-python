"""核对每条动作在 Power.log 里到底发生了什么（有没有真的 PLAY 块）。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path


def main() -> int:
    act_path = Path(sys.argv[1])
    log_path = Path(sys.argv[2])
    lines = io.open(log_path, encoding="utf-8", errors="replace").read().splitlines()
    recs = [json.loads(x) for x in io.open(act_path, encoding="utf-8").read().splitlines() if x.strip()]
    acts = [r for r in recs if r.get("plan")]
    ok_play = 0
    for a in acts:
        sb = a.get("seq_before", 0)
        sa = a.get("seq_after", 0)
        card = a["plan"].get("card_id") or ""
        win = lines[sb:sa]
        play_blocks = sum(1 for ln in win if "BlockType=PLAY" in ln)
        card_hits = sum(1 for ln in win if card and card in ln)
        tag = "真出牌" if play_blocks else ("日志前进但无PLAY块" if sa > sb else "无反应")
        if play_blocks:
            ok_play += 1
        print(f"{str(a['plan'].get('action')):6s} {card or '-':12s} 窗口{sb}..{sa} "
              f"PLAY块={play_blocks} 卡号出现={card_hits} -> {tag}")
    print(f"\n=== {len(acts)} 条动作，其中 {ok_play} 条在日志里真的出现了 PLAY 块 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

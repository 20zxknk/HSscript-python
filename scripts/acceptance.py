"""验收报表：把留档的对局逐局列出来（时间 / 对手 / 胜负 / 回合 / 出牌数 / 攻击数）。

数据源只有两样，都是游戏自己打印的：
    records/*.log        每局完整 Power.log 留档（含 CREATE_GAME 与 PLAYSTATE）
    logs/actions-*.jsonl 脚本每一步的动作日志（与 Power.log 的 seq 对账）

    python scripts/acceptance.py            # 最近 12 局
    python scripts/acceptance.py 30         # 最近 30 局
"""
from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ME = os.environ.get("HSPY_ME", "玩家")   # 本机账号名前缀；用前设 HSPY_ME=你的名字


def scan(path: str) -> dict:
    """只看**最后一个 CREATE_GAME 之后**的行。

    留档文件开头会带上上一局的 300 行上下文（`_tail[-300:]`），那里面也有
    上一局的 PLAYSTATE —— 不切掉就会把"上一局的对手/胜负"算到这一局头上。
    """
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = txt.splitlines()
    cut = 0
    for i, ln in enumerate(lines):
        if "CREATE_GAME" in ln:
            cut = i
    seg = lines[cut:]
    body = "\n".join(seg)

    start = ""
    for ln in seg:
        m = re.match(r"^D (\d\d:\d\d:\d\d)", ln)
        if m:
            start = m.group(1)
            break
    # 这一局里出现过的玩家（PLAYSTATE 行带名字）
    names = set(re.findall(r"Entity=([^\s\]]+#\d+) tag=PLAYSTATE", body))
    opp = sorted(n for n in names if not n.startswith(ME)) or ["(对手名未揭示)"]
    # 胜负：只看本机账号最后一条 PLAYSTATE
    mine = re.findall(ME + r"[^\n]*tag=PLAYSTATE value=(\w+)", body)
    last = mine[-1] if mine else ""
    result = {"WON": "胜", "WON_": "胜", "LOST": "负", "CONCEDED": "投降"}.get(last, "未结束")
    turns = [int(v) for v in re.findall(r"tag=TURN value=(\d+)", body) if v.isdigit()]
    return {
        "file": os.path.basename(path),
        "mtime": os.path.getmtime(path),
        "start": start,
        "opponent": ",".join(opp),
        "result": result,
        "max_turn": max(turns) if turns else 0,
        "plays": body.count("BlockType=PLAY"),
        "attacks": body.count("BlockType=ATTACK"),
        "powers": body.count("BlockType=POWER"),
    }


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    since = os.environ.get("ACCEPT_SINCE", "")      # 形如 00:11，只看这之后的对局
    files = sorted(glob.glob(str(ROOT / "records" / "*.log")), key=os.path.getmtime)
    rows = [scan(f) for f in files]
    if since:
        rows = [r for r in rows if r["start"] and r["start"] >= since]
    # **去重**：每次进程重启都会把历史段重写一遍留档，同一个"对局开始时间"就是同一局
    uniq: dict[str, dict] = {}
    for r in rows:
        if not r["start"]:
            continue
        key = r["start"]
        if key not in uniq or (r["plays"] + r["attacks"]) > (uniq[key]["plays"] + uniq[key]["attacks"]):
            uniq[key] = r
    def _k(r: dict) -> float:
        # 按留档文件时间排（跨零点也对）：只按"时:分:秒"排会把 00:17 排到 23:45 之前
        return r["mtime"]

    games = sorted(uniq.values(), key=_k)
    played = [r for r in games if r["plays"] or r["attacks"] or r["powers"]]
    print(f"去重后 {len(games)} 局（留档文件 {len(rows)} 份，重复来自重启重放）\n")
    head = f"{'时间':8s} {'对手':26s} {'结果':6s} {'回合':4s} {'PLAY':5s} {'ATTACK':6s}"
    print(head)
    print("-" * 60)
    for r in played[-limit:]:
        print(f"{r['start']:8s} {r['opponent']:26s} {r['result']:6s} "
              f"{r['max_turn']:<4d} {r['plays']:<5d} {r['attacks']:<6d}")

    done = [r for r in played if r["result"] in ("胜", "负", "投降")]
    win = sum(1 for r in done if r["result"] == "胜")
    print(f"\n含动作的对局 {len(played)} 局，其中已结束 {len(done)} 局：胜 {win} / 负 {len(done) - win}")
    print("注：'对手'取该局 PLAYSTATE 行里的玩家名（休闲对手揭示前显示 UNKNOWN HUMAN PLAYER）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

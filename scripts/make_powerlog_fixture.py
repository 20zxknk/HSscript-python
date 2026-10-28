"""从真实 Power.log 切一段脱敏样例做测试夹具（让离线测试真的离线）。

三个坑，写在这里免得再犯：

1. 段必须**从 `GameState.DebugPrintPower` 的 CREATE_GAME 开始**。
   从 PowerTaskList 的 CREATE_GAME 开始切，解析器会忽略掉那些实体行，得到 started=False。
2. 段里要**包含中间的 PowerTaskList 行**（TURN / STEP / CURRENT_PLAYER 这些全局标签
   往往只在 PowerTaskList 里有），否则回合数恒为 0。
3. 切出来的段必须真能让解析器看到随从和回合——判据不是写正则，而是直接喂一遍解析器。

所以：起点取 GameState 的 CREATE_GAME，终点取下一个 CREATE_GAME（任何一种），
原样保留中间所有行，最后用解析器验一遍。
"""
from __future__ import annotations

import glob
import io
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

MAX_LINES = 3000
FIX = ROOT / "tests" / "fixtures" / "powerlog-sample.log"


def sessions() -> list[pathlib.Path]:
    out = [pathlib.Path(f) for f in glob.glob(r"E:\Hearthstone\Logs\Hearthstone_*\Power.log")]
    out.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return out


def segments(lines: list[str]) -> list[list[str]]:
    starts = [i for i, l in enumerate(lines)
              if "GameState.DebugPrintPower" in l and re.search(r"-\s+CREATE_GAME", l)]
    out = []
    for begin in starts:
        end = len(lines)
        for i in range(begin + 1, len(lines)):
            # 只认 GameState 的下一局：PowerTaskList 会把同一局重放一遍，
            # 在那里截断会让每段只剩几百行（turn 永远是 0）。
            if ("GameState.DebugPrintPower" in lines[i]
                    and re.search(r"-\s+CREATE_GAME", lines[i])):
                end = i
                break
        out.append(lines[begin:min(end, begin + MAX_LINES)])
    return out


def parses(seg: list[str]) -> tuple[bool, int, str]:
    """喂一遍解析器，返回 (是否可用, 截到第几行, 说明)。

    段尾可能已经撞上下一局的 CREATE_GAME（状态被重置、turn 又归 0），
    所以在「第一次同时看到回合数与随从」的位置就截断，夹具才稳定。
    """
    from hspy.input.powerlog import PowerLog

    pl = PowerLog()
    pl._path = FIX
    cut = len(seg)
    for i, line in enumerate(seg):
        pl.seq += 1
        pl._feed(line)
        if i % 10 == 0:
            pl.state.refresh()
            if pl.state.turn > 0 and (pl.state.my_board or pl.state.rival_board):
                cut = min(len(seg), i + 100)
                break
    st = pl.state
    ok = st.started and st.turn > 0 and bool(st.my_board or st.rival_board)
    note = (f"started={st.started} turn={st.turn} "
            f"board={len(st.my_board)}/{len(st.rival_board)} 截到 {cut} 行")
    return ok, cut, note


def main() -> int:
    for src in sessions():
        lines = io.open(src, encoding="utf-8", errors="replace").read().splitlines()
        for seg in segments(lines):
            ok, cut, note = parses(seg)
            if not ok:
                continue
            seg = seg[:cut]
            body = "\n".join(seg) + "\n"
            body = re.sub(r"GameAccountId=\[hi=\d+ lo=\d+\]", "GameAccountId=[hi=0 lo=0]", body)
            body = re.sub(r"[\w\u4e00-\u9fff·]+#\d{4,}", "Player#0000", body)
            FIX.parent.mkdir(parents=True, exist_ok=True)
            io.open(FIX, "w", encoding="utf-8", newline="\n").write(body)
            print(f"写出 {FIX}（{len(seg)} 行，{FIX.stat().st_size // 1024} KB）"
                  f" 来源 {src.parent.name}；{note}")
            return 0
    print("没有找到同时有回合与随从的段")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

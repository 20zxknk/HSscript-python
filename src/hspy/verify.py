"""每一步都有输出 + 断言：让脚本的自述和 Power.log 能逐条对上。

规矩（本项目的硬要求）：
    1. 从"开始匹配"起，每一步都要打印一行 `[step] 名字 细节`；
    2. 每一步都要断言它的前置条件/结果；断言失败立刻抛 AssertionError，
       **绝不带着错状态继续点**（之前就是错着点、点空、还反复刷同一条推荐）；
    3. 同一步同时写进动作日志（JSONL），带 Power.log 的 seq/version，便于对账。

对账命令：`python -u scripts/join_actions.py logs/actions-*.jsonl <Power.log>`
"""
from __future__ import annotations

import json
import time
from typing import Any


class AssertFailed(AssertionError):
    """断言失败：脚本状态和日志不一致，必须停下来修，不许继续点。"""


class Stepper:
    def __init__(self, path=None) -> None:
        self.path = path
        self._fh = open(path, "a", encoding="utf-8") if path else None
        self.n = 0

    # ---------------- 输出 ----------------
    def step(self, name: str, **detail: Any) -> None:
        self.n += 1
        bits = " ".join(f"{k}={v}" for k, v in detail.items())
        print(f"[step {self.n:03d}] {name} {bits}".rstrip(), flush=True)
        if self._fh:
            rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "step_no": self.n, "step": name, **detail}
            self._fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()

    # ---------------- 断言 ----------------
    def require(self, cond: bool, name: str, **detail: Any) -> None:
        """断言；失败时把这一步的细节全打出来再抛。"""
        self.step(("ok:" if cond else "FAIL:") + name, **detail)
        if not cond:
            raise AssertFailed(f"{name} 断言失败: " + json.dumps(detail, ensure_ascii=False, default=str))

    # ---------------- 专门的前置断言 ----------------
    def require_hand_slot(self, st, slot: int, card_id: str) -> None:
        """点之前断言：这个槽位上确实是盒子里那张牌。

        槽位是**游戏声明的**（实体 `ZONE_POSITION` / `DebugPrintOptions`），
        不是 `my_hand` 列表的下标 —— 两者曾因增量维护漂移而不一致，
        拿列表下标去断言会每 6 步失败一次、整局卡死（2026-10-27 19:47 实证）。
        """
        hand = st.my_hand
        size = max(len(hand), (st.hand_size_hint() if hasattr(st, "hand_size_hint") else 0))
        if hasattr(st, "slot_cards"):
            ids = st.slot_cards(slot)
        else:                       # 离线假状态：只有列表
            ids = [hand[slot - 1].card_id] if 1 <= slot <= len(hand) else []
        ok = 1 <= slot <= size and (not card_id or card_id in ids)
        self.require(ok, "hand_slot",
                     slot=slot, size=size, want=card_id,
                     got="/".join(ids) or "<空>",
                     hand=[f"{e.zone_pos}:{e.card_id}" for e in hand])

    def require_board(self, index: int, size: int) -> None:
        """点之前断言：落点下标在 0..size 之间（size 表示追加到末尾）。"""
        self.require(0 <= index <= max(size, 0), "board_index", index=index, size=size)

    def close(self) -> None:
        if self._fh:
            self._fh.close()


def wait_until(fn, timeout: float = 3.0, interval: float = 0.1) -> bool:
    """等某个条件成立（只用于"等日志变化"的观察，不做动作重试）。"""
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(interval)
    return False

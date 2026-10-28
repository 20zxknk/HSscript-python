"""状态同步层 —— 按 DSH 的 event-sourced 模型重写。

DSH 的结构（session-persistence / event-sourced-sessions）：
    日志(append-only) -> 事件(seq 连续) -> 投影(状态) -> 消费者(读状态/等变化)

这里有两个日志源，但对上层只呈现**一个**同步接口：

    LoadingScreen.log ─┐
                       ├─> Sync.pump() -> Snapshot{version, mode, game}
    Power.log ─────────┘

规则（就是 DSH 那几条，换成两个源）：
1. **日志是唯一真相**：Snapshot 只能由两个日志 fold 出来，不手工改字段。
2. **version 单调**：任一源有新事件就 +1；消费者用 version 判断"有没有动"。
3. **动作-期望契约**：每个动作都带一个"做完应该看到什么"，
   看到才算成功；看不到 -> 判失步 -> 重放重建 -> 再试一次。
4. **失步只重放、不修补**：状态对不上就 rebuild()，绝不半修半补。
5. **停滞检测**：日志停写超过阈值 -> stale，交给上层决定退出还是重连。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .input.powerlog import PowerLog
from .input.screenlog import ScreenLog
from .input.state import GameState


class DesyncError(RuntimeError):
    """动作执行完，状态却没有到达期望值。"""


class StaleError(RuntimeError):
    """日志停止更新（游戏卡住/关闭）。"""


@dataclass(frozen=True)
class Snapshot:
    version: int
    mode: str | None
    game: GameState
    mode_changed_at: float = 0.0
    game_changed_at: float = 0.0

    # 常用便捷判断
    @property
    def in_match(self) -> bool:
        return self.mode == "GAMEPLAY"

    @property
    def my_turn(self) -> bool:
        return self.in_match and self.game.is_my_turn

    @property
    def finished(self) -> bool:
        return self.game.finished


class Sync:
    """两个日志源 -> 一个快照 + 一个动作-期望契约。"""

    def __init__(
        self,
        screen: ScreenLog | None = None,
        power: PowerLog | None = None,
        poll: float = 0.2,
        stale_after: float = 45.0,
    ):
        self.screen = screen or ScreenLog()
        self.power = power or PowerLog(poll=poll)
        self.poll = poll
        self.stale_after = stale_after
        self._version = 0
        self._mode: str | None = None
        self._mode_at = 0.0
        self._game: GameState = GameState()
        self._game_at = 0.0
        self._last_progress = time.time()

    # ---------------- 推进 ----------------
    def pump(self) -> Snapshot:
        """拉一次两个日志，返回最新快照（version 有变化就 ++）。"""
        mode = self.screen.poll_once()
        seq_before = self.power.seq
        self.power.pump()

        if mode != self._mode:
            self._mode = mode
            self._mode_at = time.time()
            self._version += 1
            self._last_progress = time.time()
        if self.power.seq != seq_before:
            self._game = self.power.state
            self._game_at = time.time()
            self._version += 1
            self._last_progress = time.time()
        return self.snapshot()

    def snapshot(self) -> Snapshot:
        return Snapshot(
            version=self._version,
            mode=self._mode,
            game=self._game,
            mode_changed_at=self._mode_at,
            game_changed_at=self._game_at,
        )

    # ---------------- 等待 ----------------
    def wait_until(
        self,
        pred: Callable[[Snapshot], bool],
        timeout: float = 30.0,
        interval: float | None = None,
    ) -> bool:
        """等状态满足条件。唯一等待入口，不允许上层再自己 sleep 猜。"""
        deadline = time.time() + timeout
        while True:
            snap = self.pump()
            if pred(snap):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(interval or self.poll)

    def wait_version(self, after: int, timeout: float = 30.0) -> bool:
        return self.wait_until(lambda s: s.version > after, timeout)

    # ---------------- 动作契约 ----------------
    def act(
        self,
        name: str,
        action: Callable[[], None],
        expect: Callable[[Snapshot], bool],
        timeout: float = 12.0,
        retries: int = 1,
    ) -> bool:
        """执行动作并验证期望；不满足则重放重建后再试。

        DSH 的哲学：动作是命令，状态是日志的投影；命令不"保证"结果，
        所以每个命令都要用状态回读来确认。
        """
        for attempt in range(1, retries + 2):
            before = self.pump()
            if expect(before):
                return True
            action()
            if self.wait_until(expect, timeout=timeout):
                print(f"[sync] {name}: OK (v{before.version}->v{self._version})")
                return True
            print(f"[sync] {name}: 未生效（第 {attempt} 次），重放重建")
            self.rebuild()
            time.sleep(0.4)
        raise DesyncError(f"{name} 执行后状态未到达期望")

    # ---------------- 重放 ----------------
    def rebuild(self) -> Snapshot:
        """从两个日志的开头重新投影（DSH 的 resume 语义）。"""
        self._game = self.power.rebuild()
        self._mode = None
        self._version += 1
        self._mode_at = self._game_at = time.time()
        self.screen = ScreenLog(self.screen.hs_dir)
        return self.pump()

    # ---------------- 健康 ----------------
    def stale(self) -> bool:
        return time.time() - self._last_progress > self.stale_after

    def check_health(self) -> None:
        if self.power.stale(self.stale_after) and not self.snapshot().in_match:
            raise StaleError("Power.log 长期没有新内容")

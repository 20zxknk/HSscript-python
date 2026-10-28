"""像人一样的节奏模型（状态机 + 时序分布），不是"随机乱点"。

为什么这么设计：真人其实很有规律——快慢是**成段**的，不是逐次随机跳。
所以这里先有一个状态机（专注 / 犹豫 / 走神 / 离座），状态决定所有时序参数；
具体数值都写成可调常量，便于用真人录制的数据去校准（scripts/human_stats.py）。

用法：
    from hspy.humanize import Humanizer
    h = Humanizer()
    time.sleep(h.think_delay(options=6, lethal=True))   # 出牌前"想"多久
    if h.should_look_at_card(): ...                     # 要不要看一张牌
    gap = h.inter_match_gap()                           # 局间休息
"""
from __future__ import annotations

import math
import random

# ---------------- 状态 ----------------
FOCUS = "focus"        # 专注：动作快、间隔短
HESITATE = "hesitate"  # 犹豫：出牌前长停顿
DRIFT = "drift"        # 走神：几十秒不动
AFK = "afk"            # 离座：烧绳级别

STATE_WEIGHTS = ((FOCUS, 60), (HESITATE, 25), (DRIFT, 12), (AFK, 3))

# 各状态下的"思考"基准（秒），真实值再乘对数正态噪声
STATE_THINK = {
    FOCUS: 0.55,
    HESITATE: 2.20,
    DRIFT: 4.50,
    AFK: 8.00,
}

# 状态最短停留（秒）：防止一秒内来回切，真人的状态是"成段"的
STATE_MIN_HOLD = {
    FOCUS: 8.0,
    HESITATE: 3.0,
    DRIFT: 12.0,
    AFK: 30.0,
}


class Humanizer:
    def __init__(self, rng: random.Random | None = None,
                 state_weights=STATE_WEIGHTS) -> None:
        self.rng = rng or random.Random()
        self.weights = list(state_weights)
        self.state = self._pick_state()
        self._state_since = 0.0
        self.elapsed = 0.0

    # ---------------- 状态机 ----------------
    def _pick_state(self) -> str:
        names = [n for n, _ in self.weights]
        ws = [w for _, w in self.weights]
        return self.rng.choices(names, weights=ws)[0]

    def tick(self, dt: float) -> str:
        """推进内部时钟，必要时切状态。dt 是距上次调用的秒数。"""
        self.elapsed += dt
        self._state_since += dt
        if self._state_since >= STATE_MIN_HOLD[self.state]:
            # 到最短停留后按概率切：专注状态下更可能保持
            if self.rng.random() < 0.35:
                self.state = self._pick_state()
                self._state_since = 0.0
        return self.state

    # ---------------- 时序 ----------------
    def think_delay(self, options: int = 0, lethal: bool = False,
                    dt: float = 0.0) -> float:
        """出牌前的思考时间（秒）。

        * 基准由当前状态决定；
        * 对数正态噪声（人类反应时间天然是右偏的，不能用均匀分布）；
        * 可选动作越多想得越久（Hick 定律）；
        * 有斩杀线时反而更快出手（人类看到赢面会立刻打）。
        """
        self.tick(dt)
        base = STATE_THINK[self.state]
        noise = math.exp(self.rng.gauss(0.0, 0.35))
        complexity = 1.0 + 0.12 * max(0, options)
        urgency = 0.45 if lethal else 1.0
        # 打久了会慢一点（疲劳），最多 +20%
        fatigue = 1.0 + min(0.20, 0.0009 * self.elapsed)
        return max(0.12, base * noise * complexity * urgency * fatigue)

    def press_duration(self) -> float:
        """按下到抬起（秒）：真人是右偏分布，中位 ~65ms。"""
        return min(0.20, max(0.035, self.rng.lognormvariate(-2.74, 0.30)))

    def double_click_gap(self) -> float:
        return self.rng.uniform(0.12, 0.25)

    def inter_match_gap(self) -> float:
        """一局结束到下一局开始（秒）：中位 ~45s，偶尔几分钟。"""
        gap = self.rng.lognormvariate(math.log(45.0), 0.55)
        if self.rng.random() < 0.06:                 # 6% 概率长休
            gap += self.rng.uniform(180.0, 600.0)
        return min(900.0, max(8.0, gap))

    # ---------------- 行为 ----------------
    def should_look_at_card(self, hand_size: int, lethal: bool) -> bool:
        """手牌多、又没有斩杀线时，偶尔点开一张牌看描述（真人高频动作）。"""
        if hand_size < 3 or lethal:
            return False
        return self.rng.random() < 0.08

    def look_duration(self) -> float:
        return self.rng.uniform(1.5, 3.5)

    def should_miss(self) -> bool:
        """偶发点偏（零失误本身就是异常信号）。"""
        return self.rng.random() < 0.02

    def miss_offset(self) -> tuple[int, int]:
        """点偏的偏移量：8~20px，方向随机。"""
        r = self.rng.uniform(8.0, 20.0)
        ang = self.rng.uniform(0.0, 2.0 * math.pi)
        return int(round(r * math.cos(ang))), int(round(r * math.sin(ang)))

    def correction_pause(self) -> float:
        """发现点偏之后的反应时间。"""
        return self.rng.uniform(0.3, 0.8)

    # ---------------- 观感 ----------------
    def describe(self) -> str:
        return f"state={self.state} elapsed={self.elapsed:.0f}s"

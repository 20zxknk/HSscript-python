"""干跑：用 dry_run 鼠标把整条动作链跑一遍，验证坐标与顺序（不动真实鼠标）。

    python -u scripts/dry_actions.py [宽 高]

窗口尺寸用假值（默认 1920x1080），只打印会点到哪里。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hspy import coords  # noqa: E402
from hspy.geometry import GameWindow  # noqa: E402
from hspy.output.actions import Actions, Target  # noqa: E402
from hspy.output.mouse import Mouse  # noqa: E402


class FakeWindow(GameWindow):
    def __init__(self, w: int, h: int):
        super().__init__()
        self.hwnd = 1
        self._w, self._h = w, h

    def alive(self) -> bool:
        return True

    def update(self):
        self.left, self.top = 0, 0
        self.right, self.bottom = self._w, self._h
        return 0, 0, self._w, self._h

    def bring_to_front(self) -> bool:
        return True


def show(label: str, rect) -> None:
    w, h = 1920, 1080
    x, y, rw, rh = rect.relative(w, h)
    print(f"  {label:<28} rect=({rect.left:+.4f},{rect.right:+.4f},{rect.top:+.4f},{rect.bottom:+.4f})"
          f" -> 客户区 x[{x},{x + rw}] y[{y},{y + rh}]  比例 y={((y + rh / 2) / h):.3f}")


def main() -> int:
    w = int(sys.argv[1]) if len(sys.argv) > 2 else 1920
    h = int(sys.argv[2]) if len(sys.argv) > 2 else 1080
    win = FakeWindow(w, h)
    m = Mouse(dry_run=True, humanize=True)
    ac = Actions(win, m)

    print(f"=== 假窗口 {w}x{h}，dry_run 鼠标 ===")
    print("--- 换牌：盒子 replace ZONE_POSITION=[2,4]，起手 4 张 ---")
    show("发现槽 0（换 2 号位）", coords.discover(4)[1])
    show("发现槽 1（换 4 号位）", coords.discover(4)[3])
    ac.mulligan([2, 4], 4)

    print("--- 出牌：手牌第 1 张（3 张手牌）打到空场 ---")
    show("手牌 0/3", coords.hand_card(0, 3))
    show("己方场面 0/0", coords.my_minion(0, 0))
    ac.play_card(hand_index=0, hand_size=3, board_index=0, board_size=0)

    print("--- 随从带战吼目标：上场后指向敌方 2 号随从 ---")
    show("敌方场面 1/2", coords.rival_minion(1, 2))
    ac.play_card(
        hand_index=1, hand_size=3, board_index=1, board_size=1,
        target=Target.minion(1, 2),
    )

    print("--- 攻击：己方 3 号位随从（共 3 个）打敌方英雄 ---")
    show("己方场面 2/3", coords.my_minion(2, 3))
    show("敌方英雄", coords.RIVAL_HERO)
    ac.attack(2, 3, Target.rival_hero())

    print("--- 英雄技能 / 结束回合 ---")
    show("英雄技能", coords.MY_POWER)
    ac.hero_power()
    show("结束回合", coords.END_TURN)
    ac.end_turn()

    print("--- 换牌确认序列（3 次确认 + 中心）---")
    show("确认", coords.CONFIRM)
    show("中心", coords.CENTER)

    print(f"=== 干跑结束，鼠标最后位置 prev={m.prev} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

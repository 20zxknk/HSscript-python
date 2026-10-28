"""Humanizer 的分布与状态机测试。

覆盖：
  * 状态机停在四种状态之一，且不会一秒内来回切
  * 思考时间是右偏分布（均值 > 中位），且都在合理区间
  * 复杂度越高越慢；有斩杀线更快
  * 按下时长中位 ≈ 65ms
  * 局间间隔中位 ≈ 45s，且有长尾
  * 看牌/点偏是低频事件
"""
from __future__ import annotations

import random
import statistics
import sys

sys.path.insert(0, "src")

from hspy.humanize import (  # noqa: E402
    AFK,
    DRIFT,
    FOCUS,
    HESITATE,
    Humanizer,
)


def test_state_machine_basic():
    rng = random.Random(1)
    h = Humanizer(rng)
    states = set()
    for _ in range(200):
        states.add(h.tick(0.5))
    assert states <= {FOCUS, HESITATE, DRIFT, AFK}, states
    # 1 秒内不应切状态（最短停留 3s 起）
    h2 = Humanizer(random.Random(2))
    s0 = h2.state
    h2.tick(0.2)
    assert h2.state == s0
    print(f"OK   状态机只在这四种里：{sorted(states)}；短时间不切换")


def test_think_delay_distribution():
    h = Humanizer(random.Random(3))
    vals = [h.think_delay(options=0) for _ in range(3000)]
    med = statistics.median(vals)
    mean = statistics.mean(vals)
    assert 0.3 <= med <= 3.0, med
    assert mean > med * 1.02, (mean, med)     # 右偏
    assert max(vals) < 60.0, max(vals)
    print(f"OK   思考时间右偏：中位 {med:.2f}s 均值 {mean:.2f}s 最大 {max(vals):.1f}s")


def test_complexity_and_lethal():
    h1 = Humanizer(random.Random(4))
    simple = [h1.think_delay(options=0) for _ in range(2000)]
    h2 = Humanizer(random.Random(4))
    complex_ = [h2.think_delay(options=8) for _ in range(2000)]
    assert statistics.median(complex_) > statistics.median(simple) * 1.3
    h3 = Humanizer(random.Random(4))
    lethal = [h3.think_delay(options=8, lethal=True) for _ in range(2000)]
    assert statistics.median(lethal) < statistics.median(complex_) * 0.7
    print(f"OK   复杂局面更慢（{statistics.median(complex_):.2f}s vs "
          f"{statistics.median(simple):.2f}s），斩杀线更快（{statistics.median(lethal):.2f}s）")


def test_press_duration():
    h = Humanizer(random.Random(5))
    vals = [h.press_duration() for _ in range(3000)]
    med = statistics.median(vals)
    assert 0.04 <= med <= 0.12, med
    assert 0.035 <= min(vals) and max(vals) <= 0.200
    print(f"OK   按下时长中位 {med*1000:.0f}ms（区间 {min(vals)*1000:.0f}~{max(vals)*1000:.0f}ms）")


def test_inter_match_gap():
    h = Humanizer(random.Random(6))
    vals = [h.inter_match_gap() for _ in range(3000)]
    med = statistics.median(vals)
    assert 20.0 <= med <= 90.0, med
    assert max(vals) > 200.0, max(vals)          # 有长尾（长休）
    print(f"OK   局间间隔中位 {med:.0f}s，最长 {max(vals):.0f}s（有长休）")


def test_look_and_miss_are_rare():
    h = Humanizer(random.Random(7))
    looks = sum(h.should_look_at_card(hand_size=6, lethal=False) for _ in range(5000))
    misses = sum(h.should_miss() for _ in range(5000))
    assert 150 <= looks <= 650, looks             # 约 8%
    assert 50 <= misses <= 160, misses            # 约 2%
    assert not h.should_look_at_card(hand_size=2, lethal=False)
    assert not h.should_look_at_card(hand_size=8, lethal=True)
    print(f"OK   看牌 {looks/5000:.1%}、点偏 {misses/5000:.1%}，斩杀线/手牌少时不看牌")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组人类节奏用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

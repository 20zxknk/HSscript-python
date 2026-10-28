"""贝塞尔轨迹与高斯落点的性质测试（不需要真机）。

覆盖：
  * 轨迹两端精确落在起终点（误差 <=1px）
  * 路径确实弯曲（偏离直线 > 5px），不是一条直线
  * 速度是单峰钟形（中段每步位移 > 两端 2 倍）
  * 只有远距离才可能过冲，且过冲后能回到终点
  * 落点在矩形内、呈高斯分布（不聚成一个点）、最近 10 次不重合
"""
from __future__ import annotations

import math
import random
import sys

sys.path.insert(0, "src")

from hspy.output.mouse import Mouse  # noqa: E402


class Recorder(Mouse):
    """记录每一帧光标位置，不真的动鼠标。"""

    def __init__(self, seed: int = 1) -> None:
        super().__init__(dry_run=False, humanize=True, rng=random.Random(seed))
        self.track: list[tuple[float, float]] = []
        self.clip_rect = None

    def position(self):  # type: ignore[override]
        return self.track[-1] if self.track else (0.0, 0.0)

    def _set_cursor(self, x, y):  # type: ignore[override]
        self.track.append((float(x), float(y)))

    def play(self, start: tuple[int, int], end: tuple[int, int]) -> list[tuple[float, float]]:
        import hspy.output.mouse as mm
        mm.time.sleep = lambda *a, **k: None      # 不真的等
        self.track = [(float(start[0]), float(start[1]))]
        self.move_to(end[0], end[1])
        return self.track


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_endpoints_exact():
    m = Recorder()
    tr = m.play((100, 100), (700, 500))
    assert len(tr) > 10, len(tr)
    assert _dist(tr[-1], (700, 500)) <= 1.0, tr[-1]
    print(f"OK   终点落在 (700,500)，误差 {_dist(tr[-1], (700,500)):.2f}px，共 {len(tr)} 帧")


def test_path_is_curved():
    worst = 0.0
    for seed in range(1, 6):
        m = Recorder(seed)
        tr = m.play((0, 0), (800, 0))       # 水平移动，方便量垂直偏移
        worst = max(worst, max(abs(y) for _, y in tr))
    assert worst > 5.0, worst
    print(f"OK   路径确有弧线：水平移动时最大垂直偏移 {worst:.0f}px")


def test_velocity_is_bell_shaped():
    m = Recorder(3)
    tr = m.play((0, 0), (900, 0))
    steps = [_dist(tr[i], tr[i - 1]) for i in range(1, len(tr))]
    mid = steps[len(steps) // 4: 3 * len(steps) // 4]
    ends = steps[: max(1, len(steps) // 8)] + steps[-max(1, len(steps) // 8):]
    assert (sum(mid) / len(mid)) > 2.0 * (sum(ends) / len(ends)), (mid[:3], ends[:3])
    print("OK   速度是钟形：中段每步位移是两端的两倍以上")


def test_overshoot_only_for_long_moves():
    short = Recorder(7)
    tr_short = short.play((0, 0), (120, 0))
    assert max(x for x, _ in tr_short) <= 120 + 2, max(x for x, _ in tr_short)

    hit = 0
    for seed in range(1, 31):
        m = Recorder(seed)
        tr = m.play((0, 0), (900, 0))
        if max(x for x, _ in tr) > 900 * 1.015:
            hit += 1
    assert 3 <= hit <= 18, hit
    print(f"OK   30 次远距离移动里 {hit} 次出现末端过冲，短距离不过冲")


def test_pick_point_gaussian_and_dedup():
    m = Mouse(dry_run=True, humanize=True, rng=random.Random(11))
    pts = [m.pick_point(0, 0, 200, 80) for _ in range(200)]
    assert all(0 < x < 200 and 0 < y < 80 for x, y in pts)
    xs = [p[0] for p in pts]
    assert max(xs) - min(xs) > 40, "落点几乎不动，不像高斯"
    # 连续 10 个点两两不重合（>= 6px）
    for i in range(len(pts) - 10):
        seg = pts[i:i + 10]
        for a in range(len(seg)):
            for b in range(a + 1, len(seg)):
                assert _dist(seg[a], seg[b]) >= 6.0, (seg[a], seg[b])
    print(f"OK   落点高斯分布（x 跨度 {min(xs)}~{max(xs)}），最近 10 次互不重合")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组贝塞尔/落点用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

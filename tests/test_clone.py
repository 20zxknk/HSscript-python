"""行为克隆（模板重放）的性质测试。

覆盖：
  * 模板库能加载，条数/按下样本非空
  * 重放的轨迹：起点不动、终点精确落在目标、路径有弧线（弯曲度与模板同量级）
  * 重放用的是模板里的每步耗时（不是固定 15.8ms）
  * 不同目标距离会挑不同长度的模板（缩放正确）
"""
from __future__ import annotations

import math
import random
import statistics
import sys

sys.path.insert(0, "src")

from hspy.clone import CloneMouse  # noqa: E402


class Recorder(CloneMouse):
    def __init__(self, seed: int = 1) -> None:
        super().__init__(rng=random.Random(seed), dry_run=False)
        self.track: list[tuple[float, float]] = []
        self.sleeps: list[float] = []
        self.clip_rect = None

    def position(self):  # type: ignore[override]
        return self.track[-1] if self.track else (0.0, 0.0)

    def _set_cursor(self, x, y):  # type: ignore[override]
        self.track.append((float(x), float(y)))

    def play(self, start, end):
        import hspy.clone as mod
        self.track = [(float(start[0]), float(start[1]))]
        self.sleeps = []
        orig_sleep = mod.time.sleep
        mod.time.sleep = lambda s: self.sleeps.append(s)
        try:
            self.move_to(end[0], end[1])
        finally:
            mod.time.sleep = orig_sleep
        return self.track


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_library_loaded():
    m = CloneMouse(rng=random.Random(1))
    assert len(m.templates) > 20, len(m.templates)
    assert len(m.press_ms) > 20, len(m.press_ms)
    med = statistics.median(m.press_ms)
    assert 50 <= med <= 200, med
    print(f"OK   模板 {len(m.templates)} 条、按下样本 {len(m.press_ms)} 个（中位 {med:.0f}ms）")


def test_replay_endpoint_and_shape():
    m = Recorder(2)
    tr = m.play((100, 100), (700, 400))
    assert len(tr) > 20, len(tr)
    assert dist(tr[0], (100, 100)) < 1.5, tr[0]
    assert dist(tr[-1], (700, 400)) < 1.5, tr[-1]

    x0, y0 = tr[0]
    x1, y1 = tr[-1]
    L = dist(tr[0], tr[-1])
    dx, dy = x1 - x0, y1 - y0
    bend = max(abs((p[0] - x0) * dy - (p[1] - y0) * dx) / L for p in tr) / L
    assert bend > 0.02, bend
    print(f"OK   重放：{len(tr)} 帧、终点误差 {dist(tr[-1], (700,400)):.2f}px、弯曲度 {bend:.3f}")


def test_timing_comes_from_template():
    m = Recorder(3)
    m.play((0, 0), (600, 300))
    assert m.sleeps, "没有用到模板的每步耗时"
    med = statistics.median(m.sleeps) * 1000
    assert 3 <= med <= 40, med          # 真人的每步耗时是 ms 量级、有变化
    assert len(set(round(s * 1000, 1) for s in m.sleeps)) > 3, "耗时都一样，说明没按模板重放"
    print(f"OK   每步耗时来自模板：中位 {med:.1f}ms，取值 {len(set(m.sleeps))} 种")


def test_distance_uses_matching_template():
    """远距离应该挑长模板、近距离挑短模板（否则缩放会失真）。"""
    m = Recorder(4)
    short = m._pick(80.0)
    long_ = m._pick(900.0)
    assert long_["len_px"] > short["len_px"], (short["len_px"], long_["len_px"])
    print(f"OK   80px 挑到 {short['len_px']:.0f}px 的模板，900px 挑到 {long_['len_px']:.0f}px")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组行为克隆用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""鼠标后端：默认参数化（贝塞尔 + 随机落点 + 随机间隔），克隆要显式要。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from hspy.clone import CloneMouse  # noqa: E402
from hspy.output.mouse import Mouse, make_mouse  # noqa: E402


def test_default_is_parametric():
    m = make_mouse(dry_run=False)
    assert isinstance(m, Mouse) and not isinstance(m, CloneMouse), type(m)
    print("OK   默认是参数化 Mouse（贝塞尔 + 随机落点）")


def test_clone_only_when_asked():
    m = make_mouse(dry_run=False, prefer_clone=True)
    assert isinstance(m, CloneMouse), type(m)
    assert m.templates, "模板没加载"
    print(f"OK   显式 prefer_clone=True 才返回 CloneMouse（{len(m.templates)} 条模板）")


def test_clone_falls_back_without_library():
    with tempfile.TemporaryDirectory() as d:
        missing = Path(d) / "nope.json"
        m = make_mouse(dry_run=False, library=missing, prefer_clone=True)
    assert isinstance(m, Mouse) and not isinstance(m, CloneMouse), type(m)
    print("OK   要克隆但模板库不存在时，退回参数化 Mouse")


def test_clone_press_uses_human_samples():
    m = make_mouse(dry_run=False, prefer_clone=True)
    assert isinstance(m, CloneMouse)
    vals = [m.press_ms[i] for i in range(min(20, len(m.press_ms)))]
    assert all(30 <= v <= 400 for v in vals), vals
    print(f"OK   克隆的按下时长来自真人样本（前 {len(vals)} 个：{min(vals):.0f}~{max(vals):.0f}ms）")


def test_random_landing_points_differ():
    """落点是随机的：同一个矩形连点 20 次，坐标不能全一样。"""
    m = make_mouse(dry_run=True)
    pts = {m.pick_point(100, 200, 300, 120) for _ in range(20)}
    assert len(pts) > 10, f"落点几乎没变化：{len(pts)} 个不同坐标"
    print(f"OK   同一矩形 20 次落点有 {len(pts)} 个不同坐标（随机落点生效）")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组后端选择用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

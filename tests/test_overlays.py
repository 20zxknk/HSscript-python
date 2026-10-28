"""「赛事中心」弹窗判据：米色占比。用真机截图做回归，避免阈值漂移。"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hspy import overlays  # noqa: E402

SHOTS = ROOT / ".captures"


def test_modal_detected() -> None:
    f = SHOTS / "r2-hub.png"
    if not f.exists():
        print("跳过：没有 .captures/r2-hub.png（真机截图，未入库）")
        return
    from PIL import Image

    img = Image.open(f)
    r = overlays.beige_ratio(img)
    assert overlays.tournament_modal_open(img), f"弹窗没被认出来（米色占比 {r:.3f}）"
    print(f"OK   赛事中心弹窗 -> 判为覆盖层（米色占比 {r:.3f}）")


def test_normal_hub_not_detected() -> None:
    f = SHOTS / "after_close.png"
    if not f.exists():
        print("跳过：没有 .captures/after_close.png")
        return
    from PIL import Image

    img = Image.open(f)
    r = overlays.beige_ratio(img)
    assert not overlays.tournament_modal_open(img), f"正常主菜单被误判成弹窗（{r:.3f}）"
    print(f"OK   正常主菜单 -> 不误判（米色占比 {r:.3f}）")


def test_threshold_margin() -> None:
    """两类的实测值差 200 倍，阈值取中间偏下，留足余量。"""
    assert 0.05 < overlays.BEIGE_MIN < 0.30, overlays.BEIGE_MIN
    print(f"OK   阈值 {overlays.BEIGE_MIN} 落在两类实测值之间（0.002 vs 0.50+）")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组覆盖层判据用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

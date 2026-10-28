"""Navigator 的两个契约：注入的 act 不许被覆盖；没注入时要能造出来。

审计实测的缺陷：`make_mouse` 写在 `if self.act is None:` 里面、却在 if 外面使用，
调用方一传 act 就抛 UnboundLocalError；而且传进来的 act 会被默认值覆盖。
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hspy import navigator as nav_mod  # noqa: E402
from hspy.geometry import GameWindow  # noqa: E402
from hspy.output.actions import Actions  # noqa: E402


@dataclass
class FakeAct:
    gw: object = None
    mouse: object = None
    calls: list = field(default_factory=list)

    def l_click(self, rect) -> None:  # noqa: D401 - 替身
        self.calls.append(rect)


@dataclass
class FakeSync:
    mode_value: str = "HUB"

    class _Snap:
        def __init__(self, mode: str) -> None:
            self.mode = mode

    def pump(self):
        return self._Snap(self.mode_value)


def test_injected_act_survives() -> None:
    act = FakeAct()
    with mock.patch.object(GameWindow, "update", lambda self: None):
        n = nav_mod.Navigator(hwnd=1, sync=FakeSync(), act=act)
    assert n.act is act, "传进来的 act 被覆盖了（默认值顶掉了调用方的注入）"
    print("OK   注入的 act 不会被覆盖")


def test_default_act_built_when_missing() -> None:
    with mock.patch.object(GameWindow, "update", lambda self: None):
        n = nav_mod.Navigator(hwnd=1, sync=FakeSync(), act=None)
    assert isinstance(n.act, Actions), type(n.act)
    print("OK   没注入时能造出默认动作层")


def test_mode_reads_from_sync() -> None:
    with mock.patch.object(GameWindow, "update", lambda self: None):
        n = nav_mod.Navigator(hwnd=1, sync=FakeSync("TOURNAMENT"), act=FakeAct())
    assert n.mode() == "TOURNAMENT"
    print("OK   mode() 读的是 sync.pump().mode")


def test_click_goes_through_act() -> None:
    act = FakeAct()
    with mock.patch.object(GameWindow, "update", lambda self: None):
        n = nav_mod.Navigator(hwnd=1, sync=FakeSync(), act=act)
    n.click("rect")
    assert act.calls == ["rect"]
    print("OK   click() 走的是注入的 act")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组 Navigator 契约用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""命令行小工具（不参与对局流程，run.py 才是入口）。

    python -m hspy.cli --selftest     # 只验坐标数学，不碰游戏、不点鼠标
    python -m hspy.cli --snapshot     # 打印一次当前对局状态（读 Power.log）
    python -m hspy.cli --window       # 打印炉石窗口尺寸/比例，必要时按 1.351 调整
    python -m hspy.cli --watch        # 只监听界面状态（LoadingScreen.log），不点击
"""
from __future__ import annotations

import argparse
import json
import sys

from . import coords, win
from .geometry import CONTENT_RATIO, GameRect


def selftest() -> int:
    """坐标数学自检：不依赖窗口、不碰游戏。"""
    w, h = 1920, 1080
    ok = True

    def check(name, rect: GameRect, expect_inside=True):
        nonlocal ok
        x, y, rw, rh = rect.relative(w, h)
        cx, cy = rect.click_point(w, h)
        inside = 0 <= cx < w and 0 <= cy < h
        if inside != expect_inside:
            ok = False
        print(f"{'OK ' if inside == expect_inside else 'FAIL'} {name:<16} "
              f"x={x:>5} y={y:>5} w={rw:>5} h={rh:>5}  click=({cx},{cy})")

    print(f"client={w}x{h}  usableW={int(h * CONTENT_RATIO)}  usableH={h}")
    for name, rect in (("end_turn", coords.END_TURN), ("confirm", coords.CONFIRM),
                       ("my_hero", coords.MY_HERO), ("rival_hero", coords.RIVAL_HERO),
                       ("my_power", coords.MY_POWER), ("center", coords.CENTER)):
        check(name, rect)

    assert len(coords.MY_HAND) == 10, "手牌表必须是 1..10 张共 10 组"
    for size, row in enumerate(coords.MY_HAND, start=1):
        assert len(row) == size, f"手牌 {size} 张应有 {size} 个位置，实际 {len(row)}"
    print(f"OK  MY_HAND 结构: 10 组 / 共 {sum(len(r) for r in coords.MY_HAND)} 个位置")

    for size in range(0, 8):
        for i in range(0, 7):
            coords.my_minion(i, size)      # 越界保护：不抛异常即可
            coords.rival_minion(i, size)
    print("OK  my_minion / rival_minion 越界保护")

    assert len(coords.DECK_POS) == 9
    assert len(coords.discover(3)) == 3 and len(coords.discover(4)) == 4
    print("OK  DECK_POS 9 位 / 发现面板 3、4 槽布局")
    print("\n坐标自检:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def snapshot(hs_dir: str | None, my_player: int = 0) -> int:
    from .input.powerlog import PowerLog

    log = PowerLog(hs_dir)
    if my_player:
        log.set_my_id(my_player)
    print(f"Hearthstone: {log.hs_dir}")
    print(f"Power.log  : {log.latest_log()}")
    st = log.poll_once()
    if st is None:
        print("还没读到日志")
        return 1
    print(json.dumps(st.snapshot(), ensure_ascii=False, indent=2))
    return 0


def window_info() -> int:
    hwnd = win.find_hwnd_for_process()
    left, top, w, h = win.client_rect(hwnd)
    ok = win.content_ratio_ok(hwnd)
    print(f"hwnd={hwnd} client={w}x{h} ratio={w / max(h, 1):.3f} "
          f"origin=({left},{top}) 需要调整={not ok}")
    if not ok:
        nw, nh, changed = win.ensure_content_ratio(hwnd)
        print(f"-> 已调整: {nw}x{nh} (changed={changed})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hspy", description="炉石三层脚本（输入/决策/输出）")
    ap.add_argument("--selftest", action="store_true", help="只跑坐标自检")
    ap.add_argument("--snapshot", action="store_true", help="打印一次对局状态")
    ap.add_argument("--window", action="store_true", help="打印/修正窗口比例")
    ap.add_argument("--watch", action="store_true", help="只监听界面状态并打印（只读）")
    ap.add_argument("--hs-dir", default=None, help="炉石安装目录")
    ap.add_argument("--my-player", type=int, default=0, help="强制指定自己是哪个 PlayerID（1/2）")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.window:
        return window_info()
    if args.watch:
        import time

        from .input.screenlog import ScreenLog

        sl = ScreenLog()
        print("监听界面状态 (Ctrl+C 退出)...")
        last = None
        try:
            while True:
                m = sl.poll_once()
                if m != last:
                    print(f"mode = {m}")
                    last = m
                time.sleep(0.2)
        except KeyboardInterrupt:
            return 0
    if args.snapshot:
        return snapshot(args.hs_dir, args.my_player)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

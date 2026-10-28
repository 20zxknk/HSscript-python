"""列出 HSAng（盒子）的所有窗口：位置、大小、扩展样式（是否点击穿透）。

用途：盒子的悬浮窗如果**没有** WS_EX_TRANSPARENT，它就会把点击吃掉，
表现为"鼠标动了、游戏毫无反应、Power.log 一条不出"。
    python scripts/window_dump.py [进程名]
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes

u = ctypes.WinDLL("user32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


def pids_of(name: str) -> set[int]:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, encoding="mbcs",
                         errors="replace").stdout
    pids: set[int] = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def dump(name: str) -> int:
    pids = pids_of(name)
    print(f"{name}: pids={sorted(pids)}")
    if not pids:
        return 1
    rows = []

    def cb(hwnd, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        rc = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rc))
        cls = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(hwnd, cls, 128)
        txt = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, txt, 256)
        ex = u.GetWindowLongW(hwnd, -20)
        st = u.GetWindowLongW(hwnd, -16)
        flags = []
        if ex & WS_EX_TRANSPARENT:
            flags.append("TRANSPARENT")
        if ex & WS_EX_LAYERED:
            flags.append("LAYERED")
        if ex & WS_EX_TOOLWINDOW:
            flags.append("TOOLWINDOW")
        if ex & WS_EX_NOACTIVATE:
            flags.append("NOACTIVATE")
        rows.append({
            "hwnd": hwnd, "class": cls.value, "title": txt.value,
            "rect": (rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top),
            "visible": bool(u.IsWindowVisible(hwnd)),
            "topmost": bool(st & 0x8), "ex": hex(ex), "flags": ",".join(flags),
            "area": max(0, rc.right - rc.left) * max(0, rc.bottom - rc.top),
        })
        return True

    u.EnumWindows(EnumProc(cb), 0)
    for r in sorted(rows, key=lambda r: -r["area"]):
        print(f"  hwnd={r['hwnd']:<10} area={r['area']:<9} rect={r['rect']} "
              f"visible={int(r['visible'])} topmost={int(r['topmost'])} "
              f"ex={r['ex']:<10} [{r['flags']}] {r['class']} {r['title']!r}")
    big = [r for r in rows if r["visible"] and r["area"] > 640 * 480 and "TRANSPARENT" not in r["flags"]]
    if big:
        print("\n[!] 有可见的大窗口**没有** WS_EX_TRANSPARENT：它会吃掉落在上面的点击。")
        for r in big:
            print(f"   hwnd={r['hwnd']} rect={r['rect']} {r['class']} {r['title']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(dump(sys.argv[1] if len(sys.argv) > 1 else "HSAng.exe"))

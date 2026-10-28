"""坐标几何层 —— 完全照抄作者 xjw580/hs-script 的 GameRect 约定。

作者约定（hs-script-app/.../bean/GameRect.kt）::

    realH    = 窗口内容区高度(px)
    usableH  = realH
    usableW  = realH * 1.351          # GameRationConst.GAME_WINDOW_CONTENT_WIDTH_HEIGHT_RATIO
    middleX  = realW // 2
    middleY  = realH // 2
    x = middleX + left  * usableW
    y = middleY + top   * usableH
    w = (right - left)  * usableW
    h = (bottom - top)  * usableH

注意三点，抄错任何一条全废：
1. left/right/top/bottom 是 [-0.5, 0.5] 的**相对值**，不是像素。
2. 横向按 `高度 * 1.351` 缩放，**不是**窗口实际宽度。
3. top/bottom 允许反向（top > bottom 时 h 为负），作者原样这么用。
"""
from __future__ import annotations

import ctypes
import random
from ctypes import wintypes
from dataclasses import dataclass

CONTENT_RATIO = 1.351  # GAME_WINDOW_CONTENT_WIDTH_HEIGHT_RATIO

user32 = ctypes.WinDLL("user32", use_last_error=True)

PW_CLIENTONLY = 0x00000001
SW_RESTORE = 9


@dataclass(frozen=True, slots=True)
class GameRect:
    """作者 GameRect 的等价物。"""

    left: float
    right: float
    top: float
    bottom: float

    def relative(self, real_w: int, real_h: int) -> tuple[int, int, int, int]:
        """-> (x, y, w, h)，x/y 相对窗口内容区左上角。作者原式，别改。

        横轴按 `realH * CONTENT_RATIO` 缩放，不是按客户区真实宽度：游戏按高度
        等比渲染、两侧留边。按真实宽度算会把整排拉宽（1905×982 时 6 张手牌的
        牌心从 700…1115 变成按宽度算的更大跨度）。

        具体的像素值随窗口尺寸变，别在文档里写死：算式是
            usable_w = real_h * CONTENT_RATIO
            x = real_w//2 + left * usable_w
        需要核对时直接跑一句 `python -X utf8 -c "..."` 算，别抄注释。
        """
        usable_h = real_h
        usable_w = int(real_h * CONTENT_RATIO)
        middle_x = real_w >> 1
        middle_y = real_h >> 1
        x = middle_x + self.left * usable_w
        y = middle_y + self.top * usable_h
        w = (self.right - self.left) * usable_w
        h = (self.bottom - self.top) * usable_h
        return int(x), int(y), int(w), int(h)

    def click_point(self, real_w: int, real_h: int, rng: random.Random | None = None) -> tuple[int, int]:
        """作者 getClickPos()：矩形内随机取一点，避免每次都点同一个像素。"""
        r = rng or random
        x, y, w, h = self.relative(real_w, real_h)
        x1, x2 = sorted((x, x + w))
        y1, y2 = sorted((y, y + h))
        # 内缩 1px，避免落在矩形边界上
        x1, x2 = x1 + 1, max(x1 + 1, x2 - 1)
        y1, y2 = y1 + 1, max(y1 + 1, y2 - 1)
        return r.randint(x1, x2), r.randint(y1, y2)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)


class GameWindow:
    """炉石窗口：客户区矩形 + 屏幕坐标换算。"""

    def __init__(self, title: str = "炉石传说", class_name: str = "UnityWndClass"):
        self.title = title
        self.class_name = class_name
        self.hwnd: int = 0
        self.left = self.top = self.right = self.bottom = 0

    # ---------- 窗口发现 ----------
    def find(self) -> int:
        hwnd = user32.FindWindowW(self.class_name, None)
        if not hwnd:
            hwnd = user32.FindWindowW(None, self.title)
        self.hwnd = hwnd or 0
        return self.hwnd

    def alive(self) -> bool:
        return bool(self.hwnd) and bool(user32.IsWindow(self.hwnd))

    # ---------- 尺寸 ----------
    def update(self) -> tuple[int, int, int, int]:
        """刷新客户区，返回 (left, top, width, height)。"""
        if not self.alive() and not self.find():
            raise RuntimeError("找不到炉石窗口（炉石没开？）")
        rc = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rc))
        w, h = rc.right - rc.left, rc.bottom - rc.top
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        self.left, self.top, self.right, self.bottom = origin.x, origin.y, origin.x + w, origin.y + h
        return self.left, self.top, w, h

    @property
    def size(self) -> tuple[int, int]:
        return self.right - self.left, self.bottom - self.top

    # ---------- 换算 ----------
    def to_screen(self, rect: GameRect) -> tuple[int, int]:
        """GameRect -> 屏幕绝对坐标（矩形内随机一点）。"""
        self.update()
        w, h = self.size
        x, y = rect.click_point(w, h)
        return self.left + x, self.top + y

    def to_screen_fixed(self, rect: GameRect) -> tuple[int, int]:
        """GameRect -> 屏幕绝对坐标（矩形中心）。"""
        self.update()
        w, h = self.size
        x, y, rw, rh = rect.relative(w, h)
        return self.left + x + rw // 2, self.top + y + rh // 2

    # ---------- 前台 ----------
    def bring_to_front(self) -> bool:
        if not self.alive():
            return False
        if user32.IsIconic(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_RESTORE)
        # 作者用 csystem.dll 的 topWindow；这里用 SetForegroundWindow + 附加输入线程做等价物
        fg = user32.GetForegroundWindow()
        if fg == self.hwnd:
            return True
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        tgt_tid = user32.GetWindowThreadProcessId(self.hwnd, None)
        attached = []
        for tid in (fg_tid, tgt_tid):
            if tid and user32.AttachThreadInput(cur_tid, tid, True):
                attached.append(tid)
        try:
            user32.ShowWindow(self.hwnd, SW_RESTORE)
            user32.BringWindowToTop(self.hwnd)
            user32.SetForegroundWindow(self.hwnd)
        finally:
            for tid in attached:
                user32.AttachThreadInput(cur_tid, tid, False)
        return user32.GetForegroundWindow() == self.hwnd

    # ---------- 比例坐标（0..1，相对客户区）----------
    def ratio_point(self, rx: float, ry: float) -> tuple[int, int]:
        """客户区比例 -> 窗口内像素坐标。不依赖分辨率，不写死像素。"""
        w, h = self.size
        return int(rx * w), int(ry * h)

    def ratio_box(self, x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
        w, h = self.size
        return int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)

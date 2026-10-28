"""Windows 窗口工具：枚举窗口、取客户区、截图、前台。

FindWindow 对炉石不稳（标题是中文、类名可能变），这里直接按进程枚举。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_hwnd_for_process(name: str = "Hearthstone.exe") -> int:
    """按进程名找主窗口（取面积最大的窗口，最小化的也认）。

    以前只认 IsWindowVisible：窗口被最小化/隐藏时直接报"没有可见窗口"，
    然后上层脚本就去"重新启动炉石"，白等两分钟。
    """
    import subprocess

    # 用 tasklist 拿 pid，避免再引一个依赖
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, encoding="mbcs", errors="replace",
    ).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(int(parts[1]))
    if not pids:
        raise RuntimeError(f"进程不存在: {name}")

    best: tuple[int, int, bool] = (0, 0, False)  # (area, hwnd, visible)
    found: list[int] = []

    def _cb(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        if user32.GetWindow(hwnd, GW_OWNER):
            return True  # 跳过 owned 弹窗（战网/输入法之类）
        # 最小化的窗口 GetClientRect 会返回 0x0，所以用 GetWindowRect 量面积
        rc = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        area = max(0, rc.right - rc.left) * max(0, rc.bottom - rc.top)
        vis = bool(user32.IsWindowVisible(hwnd)) and not user32.IsIconic(hwnd)
        found.append(hwnd)
        nonlocal best
        if best[1] == 0 or (vis and not best[2]) or (vis == best[2] and area > best[0]):
            best = (area, hwnd, vis)
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    if not best[1]:
        raise RuntimeError("找到进程但没有窗口")
    hwnd = best[1]
    if user32.IsIconic(hwnd) or not best[2]:
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.5)
    return hwnd


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """-> (left, top, width, height)，left/top 是客户区左上角的屏幕坐标。"""
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rc.right - rc.left, rc.bottom - rc.top


def to_screen(hwnd: int, cx: int, cy: int) -> tuple[int, int]:
    left, top, _, _ = client_rect(hwnd)
    return left + cx, top + cy


SPI_GETWORKAREA = 0x0030


def work_area() -> tuple[int, int, int, int]:
    """(left, top, width, height) 主显示器工作区（不含任务栏）。"""
    rc = wintypes.RECT()
    if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0):
        return 0, 0, 1920, 1080
    return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top


def set_client_size(hwnd: int, w: int, h: int, center: bool = True) -> tuple[int, int] | None:
    """把客户区精确调成 w×h（考虑边框），可选居中到工作区。返回新的客户区尺寸。"""
    style = user32.GetWindowLongW(hwnd, -16)    # GWL_STYLE
    exstyle = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    rc = wintypes.RECT(0, 0, w, h)
    user32.AdjustWindowRectEx(ctypes.byref(rc), style, False, exstyle)
    win_w, win_h = rc.right - rc.left, rc.bottom - rc.top
    if center:
        wl, wt, ww, wh = work_area()
        x = wl + max(0, (ww - win_w) // 2)
        y = wt + max(0, (wh - win_h) // 2)
    else:
        left, top, _, _ = client_rect(hwnd)
        x, y = left - rc.left, top - rc.top
    user32.MoveWindow(hwnd, x, y, win_w, win_h, True)
    time.sleep(0.35)
    _, _, cw, ch = client_rect(hwnd)
    return cw, ch


CONTENT_RATIO = 1.351     # 与 geometry.CONTENT_RATIO 同一个常数（作者 GAME_WINDOW_CONTENT_WIDTH_HEIGHT_RATIO）
MIN_CLIENT_H = 640        # 再小就没法可靠命中牌面/随从


def ensure_content_ratio(
    hwnd: int,
    ratio: float = CONTENT_RATIO,
    prefer_h: int = 967,
    min_h: int = MIN_CLIENT_H,
) -> tuple[int, int, bool]:
    """保证客户区宽高比 >= 1.351（作者的坐标表只在这个前提下成立）。

    为什么必须做（真机实证 2026-10-24 23:46）：
        当时客户区 389×372（比例 1.05），按 1.351 算出来的手牌/场面 x 全部偏，
        三次出牌点的位置都不在牌上，Power.log 里连一个 PLAY 块都没有，
        但脚本这边只看"日志前进了"就记成成功 —— 整局空点。
    游戏是按高度等比缩放、左右留边渲染（见 geometry.GameRect.relative 的实测），
    一旦窗口比 1.351 还窄，游戏只能裁切或改按宽度缩放，这套相对坐标就失效。

    返回 (w, h, 是否改过窗口)。已经合规时不动窗口（不打扰使用者）。
    """
    if not hwnd:
        return 0, 0, False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.4)
    _, _, w, h = client_rect(hwnd)
    if h >= min_h and w >= int(ratio * h * 0.985):
        return w, h, False

    _, _, ww, wh = work_area()
    target_h = min(prefer_h, max(min_h, wh - 120))
    target_w = int(round(target_h * ratio))
    if target_w > ww - 60:
        target_w = max(320, ww - 60)
        target_h = max(min_h, int(round(target_w / ratio)))
    got = set_client_size(hwnd, target_w, target_h, center=True)
    if not got:
        return w, h, False
    return got[0], got[1], True


def content_ratio_ok(hwnd: int, ratio: float = CONTENT_RATIO, min_h: int = MIN_CLIENT_H) -> bool:
    if not hwnd:
        return False
    _, _, w, h = client_rect(hwnd)
    return h >= min_h and w >= int(ratio * h * 0.985)


def fit_client(hwnd: int, height: int = 967, ratio: float = 1.351) -> tuple[int, int] | None:
    """把客户区调成作者坐标表的自洽比例（宽 = 高 × 1.351）。

    作者 `GameRect` 里 `usableW = realH * 1.351`，只有当窗口宽高比正好是这个数时
    x 方向才和表对齐（usableW == realW）。实测：玩家窗口 1865×967（比例 1.93）时
    手牌第 5 张会偏几十像素，点空；调成 1306×967 后就落在牌上。
    返回调整后的 (w, h)，失败返回 None。
    """
    if not hwnd:
        return None
    w = int(round(height * ratio))
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    rc = wintypes.RECT(0, 0, w, height)
    user32.AdjustWindowRectEx(ctypes.byref(rc), style, False, exstyle)
    win_w = rc.right - rc.left
    win_h = rc.bottom - rc.top
    left, top, _, _ = client_rect(hwnd)
    # 保持左上角不动，只改大小
    if not user32.MoveWindow(hwnd, left - 8, top - 31, win_w, win_h, True):
        return None
    time.sleep(0.3)
    _, _, cw, ch = client_rect(hwnd)
    return cw, ch


def capture(hwnd: int, path: str | Path) -> Path | None:
    """截客户区，存 PNG（走 GDI）。窗口最小化/客户区为空时返回 None，不抛。"""
    left, top, w, h = client_rect(hwnd)
    if w <= 0 or h <= 0:
        print(f"[win] 客户区为空（{w}x{h}），跳过截图", flush=True)
        return None
    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    old = gdi32.SelectObject(hdc_mem, hbmp)
    try:
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, left, top, 0x00CC0020)
        # BITMAPINFOHEADER + 像素
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = -h  # 负数 = 自上而下
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bi), 0)

        # 直接写 PNG：用最省事的办法——BMP 头 + 数据交给 Pillow（若有）
        try:
            from PIL import Image

            img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
            img = img.convert("RGB")
            out = Path(path)
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                img.save(out)
            except Exception as e:
                # 抓到的图是空的（窗口最小化/正在关闭）时 Pillow 会抛
                # "cannot write empty image"；截图是诊断用的，不能因为它把整轮跑挂掉。
                print(f"[win] 写截图失败（{w}x{h}）: {e}", flush=True)
                return None
            return out
        except ImportError:
            raise RuntimeError("截图需要 Pillow：pip install pillow")
    finally:
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)


SW_RESTORE = 9
HWND_TOP = 0
GW_OWNER = 4
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040


def foreground_hwnd() -> int:
    return user32.GetForegroundWindow()


def bring_to_front(hwnd: int, verify: bool = True) -> bool:
    """把窗口拉到前台，并**校验真的成功了**。

    只调 SetForegroundWindow 经常被 Windows 的前台锁挡掉（后台进程抢焦点），
    结果就是"以为点的是游戏、实际点了别的窗口"。必须用 AttachThreadInput，
    并且在调用方点击前再验一次 foreground_hwnd()。
    """
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    if foreground_hwnd() == hwnd:
        return True

    cur = ctypes.WinDLL("kernel32").GetCurrentThreadId()
    fg = foreground_hwnd()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
    attached = []
    for tid in (fg_tid, tgt_tid):
        if tid and tid != cur and user32.AttachThreadInput(cur, tid, True):
            attached.append(tid)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        for tid in attached:
            user32.AttachThreadInput(cur, tid, False)
    return (not verify) or foreground_hwnd() == hwnd


def is_foreground(hwnd: int) -> bool:
    return foreground_hwnd() == hwnd


HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
GA_ROOT = 2


def force_front(hwnd: int, topmost: bool = True) -> bool:
    """置顶 + 切前台，并校验。Chrome 这类普通窗口有时压在游戏上方。"""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if topmost:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    user32.SwitchToThisWindow(hwnd, True)
    bring_to_front(hwnd, verify=False)
    return foreground_hwnd() == hwnd


def drop_topmost(hwnd: int) -> None:
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


def hit_test(hwnd: int, sx: int, sy: int) -> bool:
    """屏幕坐标 (sx,sy) 上最上层的窗口是不是 hwnd 这一族。"""
    w = user32.WindowFromPoint(wintypes.POINT(sx, sy))
    if not w:
        return False
    root = user32.GetAncestor(w, GA_ROOT)
    return root == hwnd


SW_MINIMIZE = 6


def _root_under(sx: int, sy: int) -> int:
    w = user32.WindowFromPoint(wintypes.POINT(sx, sy))
    return user32.GetAncestor(w, GA_ROOT) if w else 0


def _proc_of(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


_BOX_PIDS: set[int] = set()


def _is_box_overlay(hwnd: int) -> bool:
    """盒子(HSAng)的悬浮窗：盖在游戏上但点击穿透，不能最小化它（推荐面板在它里面）。"""
    global _BOX_PIDS
    if not _BOX_PIDS:
        import subprocess

        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq HSAng.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="mbcs", errors="replace",
            ).stdout
            for line in out.splitlines():
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 2 and parts[1].isdigit():
                    _BOX_PIDS.add(int(parts[1]))
        except Exception as e:
            print(f"[win] 取盒子 pid 失败（按没有盒子遮挡处理）: {e}", flush=True)
    return _proc_of(hwnd) in _BOX_PIDS


def clear_obstruction(hwnd: int, cx: int, cy: int, max_rounds: int = 6) -> bool:
    """把挡在游戏前面的窗口最小化（只动真正挡路的那个）。

    返回 True 表示落点可用。盒子悬浮窗是点击穿透的，直接放行；
    **游戏自己的窗口（子窗口/弹窗）绝不能最小化** —— 曾经把它当"挡路窗口"
    最小化掉，之后所有点击都点到别处去了。
    """
    me_pid = _proc_of(hwnd)
    for _ in range(max_rounds):
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.5)
        sx, sy = to_screen(hwnd, cx, cy)
        top = _root_under(sx, sy)
        if top == hwnd:
            return True
        if top and (_is_box_overlay(top) or _proc_of(top) == me_pid):
            return True   # 盒子悬浮窗 / 游戏自己的窗口，别动它
        if not top:
            time.sleep(0.3)
            continue
        user32.ShowWindow(top, SW_MINIMIZE)
        time.sleep(0.35)
    sx, sy = to_screen(hwnd, cx, cy)
    top = _root_under(sx, sy)
    return top == hwnd or (top != 0 and (_is_box_overlay(top) or _proc_of(top) == me_pid))


def guard_point(hwnd: int, cx: int, cy: int, tries: int = 4, activate: bool = True) -> tuple[int, int]:
    """校验"客户区 (cx,cy) 这一点真的属于游戏窗口"，返回屏幕坐标。

    作者每次点击前都 topWindow，我们这里必须更严：炉石被别的窗口（盒子主界面、
    战网、浏览器）压住时，SendInput 点的是**上面那个窗口**，游戏收不到——
    表现就是"鼠标明明点了、游戏毫无反应、日志也不动"。

    **activate=False 用于"点-移-点"的第二次点击**：那时窗口必须保持原状，
    重新激活会触发 WM_ACTIVATE，炉石会把"正跟着鼠标走的那张牌"丢回手牌 ——
    整串动作变成两次空点（真机实证：单点导航/开始都能成，出牌/攻击全失败）。
    不激活时仍然校验前台与落点，不合格就抛异常，绝不盲点。
    """
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.5)
    if activate:
        for attempt in range(tries):
            if clear_obstruction(hwnd, cx, cy):
                break
            force_front(hwnd)
            time.sleep(0.4)
        force_front(hwnd)
    elif not is_foreground(hwnd):
        # 中间被别的窗口抢了前台：这时只能重新激活一次（宁可丢这一下，也别点到别处）
        force_front(hwnd)
        time.sleep(0.2)
    left, top, _, _ = client_rect(hwnd)
    sx, sy = left + cx, top + cy
    root = _root_under(sx, sy)
    ok_hit = root == hwnd or (root and _is_box_overlay(root))
    if not ok_hit:
        raise RuntimeError(f"落点 ({cx},{cy}) 被窗口 {root} 挡住，拒绝点击")
    return sx, sy


def click_client(hwnd: int, cx: int, cy: int, button: str = "left", mouse=None,
                 activate: bool = True) -> tuple[int, int]:
    """在客户区坐标 (cx, cy) 点一下，**点击前强制校验前台窗口与落点归属**。

    这是硬约束：落点不属于游戏就抛异常，绝不盲点——
    曾经因为 SetForegroundWindow 静默失败，一指点到了别的程序上。

    activate=False：不重新激活窗口（"点-移-点"里的第二次点击必须用它，
    否则重新激活会把已捡起的牌丢回手里，见 guard_point 的说明）。
    """
    sx, sy = guard_point(hwnd, cx, cy, activate=activate)
    if mouse is None:
        from .output.mouse import Mouse

        mouse = Mouse(dry_run=False, humanize=True)
    if button == "right":
        mouse.right_click((sx, sy))
    else:
        mouse.left_click((sx, sy))
    return sx, sy


def capture_window(hwnd: int, path: str | Path) -> Path | None:
    """PrintWindow 抓窗口自身内容，不受其他窗口遮挡影响。空图返回 None。"""
    from PIL import Image

    _, _, w, h = client_rect(hwnd)
    if w <= 0 or h <= 0:
        print(f"[win] 客户区为空（{w}x{h}），跳过截图", flush=True)
        return None
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    try:
        user32.PrintWindow(hwnd, mem, 3)  # PW_CLIENTONLY|PW_RENDERFULLCONTENT
        class BIH(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]
        bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            img.save(out)
        except Exception as e:
            print(f"[win] 写截图失败（{w}x{h}）: {e}", flush=True)
            return None
        return out
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)


def grab_client(hwnd: int):
    """抓客户区，返回 PIL.Image（不落盘）。

    overlays 的判据要「看一眼画面」，不能每次都写文件；这里复用 capture_window
    的 GDI 路径，只是不保存。
    """
    from PIL import Image

    _, _, w, h = client_rect(hwnd)
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    try:
        user32.PrintWindow(hwnd, mem, 3)  # PW_CLIENTONLY|PW_RENDERFULLCONTENT

        class BIH(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]
        bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
        return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)


def press_key(vk: int) -> None:
    """发一次按键（SendInput）。"""
    from .output.mouse import key_press

    key_press(vk)




def click_ratio(hwnd: int, rx: float, ry: float) -> None:
    """按客户区比例点击（0..1），不写死像素。"""
    _, _, w, h = client_rect(hwnd)
    click_client(hwnd, int(rx * w), int(ry * h))


"""输出层：真实鼠标（SendInput），语义照抄作者 MouseUtil。

为什么不用鼠标消息注入：炉石只认硬件级输入，PostMessage/SendMessage 会被吞。
SendInput 走 Windows 输入队列，和真人操作同一条路径——作者也是调
csystem.dll 的 simulateHumanMoveMouse/leftClick（同样是真实输入）。

本文件的三个原语与作者 MouseUtil 一一对应，别再自己加中间层：

    Mouse.human_move(start, end)   <-> MouseUtil.moveMouseByHuman(start, end, hwnd)
    Mouse.left_click(pt)           <-> MouseUtil.leftButtonClick(pos, hwnd)
    Mouse.right_click(pt)          <-> MouseUtil.rightButtonClick(pos, hwnd)

作者的两个细节必须抄：
1. **记住 prevPoint**：只有当目标点与上次点击点不同才移动鼠标；点完保存。
2. 移动完 `delayShort()`（250~450ms）才按下，太快游戏会当"没动过"。
"""
from __future__ import annotations

import ctypes
import math
import pathlib
import random
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000  # 没有它, 绝对坐标按主屏算, 多屏会偏
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

# ---- 作者 RandomUtil 的延迟档位（毫秒 -> 秒），一档都不许自己改 ----
TINY = (0.100, 0.200)          # getTinyRandom
SHORT = (0.250, 0.450)         # getShortRandom
SHORT_MEDIUM = (0.500, 0.800)  # getShortMediumRandom
MEDIUM = (1.000, 1.600)        # getMediumRandom
LONG = (2.000, 3.000)          # getLongRandom
HUGE = (3.000, 5.000)          # getHugeRandom

# ---- 以下数字是对作者 csystem.dll 的 simulateHumanMoveMouse 实测出来的 ----
# 用 SetCursorPos 逐步移动，每步之间 Sleep：
#   每步耗时 ≈ 15.7~15.9 ms（三组 pauseStep 都是这个值）
#   每步位移按 smoothstep 加减速：起点 7px → 中段 44px → 终点 2px
#   1350px 的移动：pauseStep=7 → 52 步，pauseStep=3 → 210 步，pauseStep=15 → 30 步
#   pauseStep=7 时平均每步 25.9px（≈ 26px）
STEP_SLEEP_MS = 15.8           # 作者 DLL 每步 Sleep 的实测中位数
STEP_PX_AT_DEFAULT = 26.0      # pauseStep=7 时的平均每步像素
PAUSE_STEP = 7                 # 作者 ConfigEnum.PAUSE_STEP 默认值


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTunion)]


def _send(*inputs: INPUT) -> None:
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise OSError(f"SendInput 失败 err={ctypes.get_last_error()}")


def _mouse_input(flags: int, dx: int = 0, dy: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(dx, dy, 0, flags, 0, None)))


def key_press(vk: int) -> None:
    """发一次真实按键（SendInput）。"""
    _send(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(vk, 0, 0, 0, None))))
    time.sleep(0.03)
    _send(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, None))))


def delay(range_: tuple[float, float]) -> float:
    """作者 SystemUtil.delay(min,max)：区间内均匀随机，返回实际等了多久。"""
    t = random.uniform(*range_)
    time.sleep(t)
    return t


class Mouse:
    """真实鼠标。dry_run=True 时只打印不点击。

    prev 就是作者的 MouseUtil.prevPoint：作者初始化成 (0,0)，第一次点击
    会从屏幕左上角"平移"过去，这里保持同样的初始值。
    """

    def __init__(self, dry_run: bool = True, humanize: bool = True, rng: random.Random | None = None):
        self.dry_run = dry_run
        self.humanize = humanize
        self.rng = rng or random.Random()
        self.prev: tuple[int, int] = (0, 0)
        # 作者的 PAUSE_STEP 与 limitMouseRange
        self.pause_step = PAUSE_STEP
        self.clip_rect: tuple[int, int, int, int] | None = None
        # 最近点过的位置（避免同像素连点）
        self.recent_points: list[tuple[int, int]] = []   # 作者 prevPoint
        self._vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self._vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        self._vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        self._vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    # ---------------- 基础 ----------------
    def position(self) -> tuple[int, int]:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _set_cursor(self, x: int, y: int) -> None:
        """作者 DLL 用的就是 SetCursorPos（实测导入表里有它），不是 SendInput。"""
        user32.SetCursorPos(int(x), int(y))

    def pick_point(self, x: int, y: int, w: int, h: int,
                   sigma: float = 0.12) -> tuple[int, int]:
        """矩形内取一个"像人"的落点：二维截断高斯 + 不与最近几次重合。

        `sigma` 是相对矩形尺寸的标准差（默认 12%），落点集中在中心偏下，
        但每次都不一样；同时和最近 10 次点击保持 >= 6px 的距离，避免"同像素连点"。
        """
        cx, cy = x + w / 2.0, y + h * 0.55          # 人手倾向点偏下一点
        sx, sy = max(1.0, w * sigma), max(1.0, h * sigma)
        for _ in range(24):
            px = int(round(self.rng.gauss(cx, sx)))
            py = int(round(self.rng.gauss(cy, sy)))
            px = max(x + 1, min(x + w - 2, px))
            py = max(y + 1, min(y + h - 2, py))
            if all((px - q[0]) ** 2 + (py - q[1]) ** 2 >= 36 for q in self.recent_points):
                break
        self.recent_points.append((px, py))
        del self.recent_points[:-10]
        return px, py

    def _clip(self, x: int, y: int) -> tuple[int, int]:
        """作者 limitMouseRange：光标只允许在游戏客户区内。"""
        r = self.clip_rect
        if r is None:
            return x, y
        left, top, right, bottom = r
        return max(left, min(right - 1, x)), max(top, min(bottom - 1, y))

    def _normalize(self, x: int, y: int) -> tuple[int, int]:
        # SendInput 绝对坐标是 0..65535 的虚拟屏幕归一化值
        nx = int((x - self._vx) * 65535 / max(1, self._vw - 1))
        ny = int((y - self._vy) * 65535 / max(1, self._vh - 1))
        return max(0, min(65535, nx)), max(0, min(65535, ny))

    def _bezier(self, p0, c1, c2, p3, t: float) -> tuple[float, float]:
        """三次贝塞尔：路径形状（弧线）由两个控制点决定。"""
        u = 1.0 - t
        x = (u ** 3) * p0[0] + 3 * (u ** 2) * t * c1[0] + 3 * u * (t ** 2) * c2[0] + (t ** 3) * p3[0]
        y = (u ** 3) * p0[1] + 3 * (u ** 2) * t * c1[1] + 3 * u * (t ** 2) * c2[1] + (t ** 3) * p3[1]
        return x, y

    def _walk(self, p0: tuple[float, float], p3: tuple[float, float],
              steps: int, bow: float, overshoot: float) -> None:
        """沿贝塞尔走一遍：余弦钟形速度 + 每步 ±1px 抖动。"""
        dx, dy = p3[0] - p0[0], p3[1] - p0[1]
        dist = (dx * dx + dy * dy) ** 0.5 or 1.0
        # 单位法向量：控制点沿它偏移，得到一条自然的弧线
        nx, ny = -dy / dist, dx / dist

        # 两个控制点：2%~8% 距离的侧向偏移，前后幅度不同（比对称弧更像人）
        off1 = bow * self.rng.uniform(0.55, 1.0)
        off2 = bow * self.rng.uniform(0.55, 1.0)
        c1 = (p0[0] + dx * 0.25 + nx * off1, p0[1] + dy * 0.25 + ny * off1)
        c2 = (p0[0] + dx * 0.75 + nx * off2, p0[1] + dy * 0.75 + ny * off2)

        end = (p0[0] + dx * overshoot, p0[1] + dy * overshoot)
        for k in range(1, steps + 1):
            u = k / steps
            # 余弦钟形：两端慢、中间快（人手速度剖面是单峰钟形）
            t = 0.5 - 0.5 * math.cos(math.pi * u)
            px, py = self._bezier(p0, c1, c2, end, t)
            if self.humanize and k < steps:
                px += self.rng.uniform(-1.0, 1.0)
                py += self.rng.uniform(-1.0, 1.0)
            self._set_cursor(px, py)
            time.sleep((STEP_SLEEP_MS + self.rng.uniform(-1.5, 1.5)) / 1000.0)

    def move_to(self, x: int, y: int, duration: float = 0.18) -> None:
        """作者式移动的加强版：贝塞尔路径 + 钟形速度 + 末端过冲修正。

        作者 DLL 实测是 smoothstep 直线（偏离直线只有 ~33px 的噪声量级）。
        这里换成真正的曲线：
          * 路径：三次贝塞尔，控制点沿法向偏移 2%~8% 距离；
          * 速度：余弦钟形（单峰），两端减速；
          * 末端：30% 概率冲过终点 2%~5%，再用 2~3 小步拉回来；
          * 每步之间 Sleep ≈ 15.8ms（和作者实测一致）。
        """
        x, y = self._clip(x, y)
        if self.dry_run:
            print(f"[dry] move {x},{y}")
            self.prev = (x, y)
            return
        sx, sy = self.position()
        dist = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
        if dist < 1.0:
            return

        step_px = STEP_PX_AT_DEFAULT * (PAUSE_STEP / max(1, self.pause_step))
        steps = max(6, min(400, int(dist / step_px) + 1))

        bow = 0.0
        if self.humanize and dist > 40:
            bow = dist * self.rng.uniform(0.02, 0.08) * self.rng.choice((-1.0, 1.0))

        # 末端过冲：人手常冲过头再修正（只有远距离才像人）
        overshoot = 1.0
        if self.humanize and dist > 200 and self.rng.random() < 0.3:
            overshoot = 1.0 + self.rng.uniform(0.02, 0.05)

        self._walk((sx, sy), (x, y), steps, bow, overshoot)

        if overshoot != 1.0:
            # 拉回来：2~3 个短步，每步 8~25% 的余量
            ox, oy = sx + (x - sx) * overshoot, sy + (y - sy) * overshoot
            back = 3
            for k in range(1, back + 1):
                t = k / back
                px = ox + (x - ox) * t
                py = oy + (y - oy) * t
                self._set_cursor(px, py)
                time.sleep(self.rng.uniform(0.012, 0.028))

        self._set_cursor(x, y)
        self.prev = (x, y)

    def left_down(self, hold: float | None = None) -> None:
        if self.dry_run:
            print("[dry] left down")
            return
        _send(_mouse_input(MOUSEEVENTF_LEFTDOWN))
        # 按下到抬起：真人中位 ~65ms、右偏（固定 20ms 太整齐）；
        # hold 由调用方给（行为克隆时用真人样本采样）
        if hold is None:
            hold = min(0.20, max(0.035, self.rng.lognormvariate(-2.74, 0.30)))
        time.sleep(hold)

    def left_up(self) -> None:
        if self.dry_run:
            print("[dry] left up")
            return
        _send(_mouse_input(MOUSEEVENTF_LEFTUP))
        time.sleep(0.02)

    def right_down(self) -> None:
        if self.dry_run:
            print("[dry] right down")
            return
        _send(_mouse_input(MOUSEEVENTF_RIGHTDOWN))
        time.sleep(min(0.20, max(0.035, self.rng.lognormvariate(-2.74, 0.30))))

    def right_up(self) -> None:
        if self.dry_run:
            print("[dry] right up")
            return
        _send(_mouse_input(MOUSEEVENTF_RIGHTUP))
        time.sleep(0.02)

    def _left_click_hw(self) -> None:
        self.left_down()
        self.left_up()

    def _right_click_hw(self) -> None:
        self.right_down()
        self.right_up()

    # ---------------- 作者 MouseUtil 三个原语 ----------------
    def human_move(self, start: tuple[int, int] | None, end: tuple[int, int]) -> None:
        """作者 MouseUtil.moveMouseByHuman(startPos, endPos)。

        有起点：先移到起点（prev->start），delayShort，再 start->end。
        没起点：直接从 prev 移到 end。
        """
        if start is not None:
            self._move_from_prev_to(start)
            delay(SHORT)
            if start != end:
                self.move_to(end[0], end[1])
                self.prev = end
        else:
            self._move_from_prev_to(end)

    def _move_from_prev_to(self, end: tuple[int, int]) -> None:
        if self.prev != end:
            self.move_to(end[0], end[1])
            self.prev = end

    def left_click(self, pt: tuple[int, int], settle: tuple[float, float] | None = None) -> None:
        """作者 MouseUtil.leftButtonClick(pos, hwnd)。

        settle 默认就是作者的 delayShort(250~450ms)；点手牌时要更短——
        鼠标停在手牌上 ~0.5s 会弹出"放大预览"，那一击会被预览吃掉（真机实测）。
        """
        if self.prev != pt:
            self.move_to(pt[0], pt[1])   # simulateHumanMoveMouse(prev -> pos)
            delay(settle or SHORT)       # 作者这里必等 delayShort
        self._left_click_hw()
        self.prev = pt

    def right_click(self, pt: tuple[int, int]) -> None:
        """作者 MouseUtil.rightButtonClick(pos, hwnd)。"""
        if self.prev != pt:
            self.move_to(pt[0], pt[1])
            delay(SHORT)
        self._right_click_hw()
        self.prev = pt

    def right_click_prev(self) -> None:
        """作者 GameUtil.cancelAction() = MouseUtil.rightButtonClick(prevPoint)。"""
        self.right_click(self.prev)

    def left_click_prev(self) -> None:
        """作者 MouseUtil.leftButtonClick(hwnd)（无参版，点 prevPoint）。"""
        self.left_click(self.prev)

    # ---------------- 兼容旧调用 ----------------
    def click(self, x: int, y: int, button: str = "left", settle: float = 0.06) -> None:
        pt = (x, y)
        if button == "right":
            self.right_click(pt)
        else:
            self.left_click(pt)

    def drag(self, x1: int, y1: int, x2: int, y2: int, hold: float = 0.12) -> None:
        """按住拖拽。作者从不这么做出牌/攻击（他用 lClickMoveLClick），
        这里只留给"拖拽类"界面（滑动卡组列表之类）。"""
        self.move_to(x1, y1)
        delay(TINY)
        self.left_down()
        delay(SHORT)
        self.move_to(x2, y2, duration=0.25)
        delay(SHORT)
        self.left_up()
        delay(TINY)

    def cancel(self) -> None:
        """作者 cancelAction()：右键取消当前选中。"""
        self.right_click_prev()


def make_mouse(dry_run: bool = False, humanize: bool = True,
               library: str | pathlib.Path | None = None,
               prefer_clone: bool = False) -> "Mouse":
    """造鼠标后端。

    默认是**参数化实现**：三次贝塞尔路径 + 余弦钟形速度 + 高斯随机落点，
    间隔由调用方（对战引擎）随机给。模板重放（`CloneMouse`）留作可选，
    需要时传 `prefer_clone=True` 或把 config 的 `mouse_backend` 设成 `clone`。
    """
    import pathlib as _p

    if prefer_clone:
        from ..clone import DEFAULT_LIBRARY, CloneMouse

        lib = _p.Path(library) if library else DEFAULT_LIBRARY
        if lib.exists():
            print(f"[mouse] 行为克隆：{lib}", flush=True)
            return CloneMouse(library=lib, dry_run=dry_run, humanize=humanize)
        print(f"[mouse] 没有模板库（{lib}），退回参数化鼠标", flush=True)
    print("[mouse] 参数化：贝塞尔路径 + 随机落点", flush=True)
    return Mouse(dry_run=dry_run, humanize=humanize)

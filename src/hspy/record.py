"""对局记录器：鼠标 LL 钩子 + 盒子推荐原文，统一到同一个时钟上。

三份产物（都写进同一个目录，靠 `ts` / `t` 对齐）：

    mouse.jsonl        鼠标事件（WH_MOUSE_LL 低层钩子）：移动/按下/抬起/滚轮，
                       带屏幕坐标 + 客户区坐标 + injected 标记（区分"我们发的"和"人手动"）
    recommendations.jsonl  每次向盒子要推荐收到的原文（plans + raw_rec + 原始 JSON 行）
    powerlog_story.md  Power.log 整局叙述（由 scripts/powerlog_story.py 生成）

时间基准：`ts` = `time.time()`（epoch 秒，6 位小数）；`t` = 本地 `HH:MM:SS.mmm`。
游戏侧 Power.log 行首也带 `D HH:MM:SS.fffffff`（同一台机器本地时间），三者可以直接对表。
"""
from __future__ import annotations

import ctypes
import json
import threading
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
LLMHF_INJECTED = 0x00000001
PM_REMOVE = 0x0001

_EVENT_NAME = {
    WM_MOUSEMOVE: "move",
    WM_LBUTTONDOWN: "ldown",
    WM_LBUTTONUP: "lup",
    WM_RBUTTONDOWN: "rdown",
    WM_RBUTTONUP: "rup",
    WM_MOUSEWHEEL: "wheel",
    WM_MOUSEHWHEEL: "hwheel",
}


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

# 显式声明签名：LPARAM 常是负的指针值，不声明 argtypes 会
# `OverflowError: int too long to convert`（真机踩过：回调里抛异常 -> 钩子链断掉）
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]


def _now_stamp() -> tuple[float, str]:
    ts = time.time()
    lt = time.localtime(ts)
    return ts, f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}.{int(ts % 1 * 1000):03d}"


class _JsonlWriter:
    """带缓冲的 JSONL 写入器（钩子回调里只排队，落盘在后台线程）。"""

    def __init__(self, path: Path, flush_every: int = 64, max_lines: int = 400_000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()
        self._buf: list[str] = []
        self._flush_every = flush_every
        self._lines = 0
        self._max = max_lines
        self.truncated = False

    def write(self, rec: dict) -> None:
        if self._lines >= self._max:
            self.truncated = True
            return
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._buf.append(line)
            self._lines += 1
            if len(self._buf) >= self._flush_every:
                self._flush_locked()

    def _flush_locked(self) -> None:
        if self._buf:
            self._fh.write("\n".join(self._buf) + "\n")
            self._buf.clear()

    def close(self) -> None:
        with self._lock:
            self._flush_locked()
        try:
            self._fh.close()
        except Exception as e:
            # 不静默：关不上说明最后几条可能没落盘，得让人知道
            print(f"[rec] 关闭 {self.path} 失败: {e}", flush=True)


class MouseHook:
    """WH_MOUSE_LL 低层鼠标钩子，记录所有鼠标事件（含脚本自己发的）。

    `injected=1` 表示该事件由 SendInput / mouse_event 产生（我们点的），
    `injected=0` 是物理鼠标（使用者自己动的）。钩子**只记录、不拦截**，
    永远 CallNextHookEx，绝不影响输入。
    """

    def __init__(self, path: str | Path, hwnd: int = 0, flush_every: int = 8):
        self.writer = _JsonlWriter(Path(path), flush_every=flush_every)
        self.hwnd = hwnd
        self._thread: threading.Thread | None = None
        self._hook = None
        self._proc = HOOKPROC(self._callback)     # 必须持有引用，否则回调被回收
        self._origin = (0, 0)
        self._origin_at = 0.0
        self._seq = 0
        self._lock = threading.Lock()
        self.error: str | None = None

    # ---------------- 钩子回调 ----------------
    def _refresh_origin(self) -> tuple[int, int]:
        now = time.time()
        if now - self._origin_at < 0.25:
            return self._origin
        self._origin_at = now
        if self.hwnd:
            try:
                from . import win

                left, top, _, _ = win.client_rect(self.hwnd)
                self._origin = (left, top)
            except Exception:
                self._origin = (0, 0)
        return self._origin

    def _callback(self, n_code, w_param, l_param):
        if n_code >= 0:
            try:
                msg = int(w_param)
                name = _EVENT_NAME.get(msg)
                if name:
                    ptr = ctypes.cast(ctypes.c_void_p(l_param),
                                      ctypes.POINTER(_MSLLHOOKSTRUCT))
                    info = ptr.contents
                    sx, sy = int(info.pt.x), int(info.pt.y)
                    ox, oy = self._refresh_origin()
                    ts, stamp = _now_stamp()
                    with self._lock:
                        self._seq += 1
                        seq = self._seq
                    self.writer.write({
                        "seq": seq, "ts": round(ts, 6), "t": stamp, "ev": name,
                        "sx": sx, "sy": sy, "cx": sx - ox, "cy": sy - oy,
                        "injected": 1 if (info.flags & LLMHF_INJECTED) else 0,
                        "data": int(info.mouseData) if name in ("wheel", "hwheel") else 0,
                    })
            except Exception:
                pass       # 钩子里绝不抛：抛了会卡住整条输入队列
        return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

    # ---------------- 生命周期 ----------------
    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, name="mouse-hook", daemon=True)
        self._thread.start()
        deadline = time.time() + 3.0
        while time.time() < deadline and self._hook is None and self.error is None:
            time.sleep(0.02)
        return self._hook is not None and self.error is None

    def _run(self) -> None:
        try:
            self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
            if not self._hook:
                self.error = f"SetWindowsHookExW 失败 err={ctypes.get_last_error()}"
                return
            msg = wintypes.MSG()
            while True:
                got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if got <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:
            self.error = f"钩子线程异常: {e}"
        finally:
            if self._hook:
                try:
                    user32.UnhookWindowsHookEx(self._hook)
                except Exception as e:
                    print(f"[rec] 卸载鼠标钩子失败: {e}", flush=True)
                self._hook = None

    def stop(self) -> None:
        try:
            if self._thread and self._thread.ident:
                user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)   # WM_QUIT
        except Exception as e:
            # 停不掉也不能静默：钩子还挂着会继续写文件
            print(f"[rec] 结束钩子线程失败（会等 2s 后放弃）: {e}", flush=True)
        if self._thread:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                print("[rec] 钩子线程 2s 内没退出（文件可能还在被写）", flush=True)
        self.writer.close()
        if self.error:
            print(f"[rec] 钩子异常记录: {self.error}", flush=True)


class RecommendationRecorder:
    """记录每次向盒子要推荐收到的原文（plans + raw_rec + 原始行）。"""

    def __init__(self, path: str | Path, max_lines: int = 20_000):
        self.writer = _JsonlWriter(Path(path), flush_every=1, max_lines=max_lines)
        self._seq = 0

    def rec(self, plans, raw: str, raw_rec: dict | None = None) -> None:
        ts, stamp = _now_stamp()
        self._seq += 1
        self.writer.write({
            "seq": self._seq, "ts": round(ts, 6), "t": stamp,
            "n": len(plans),
            "plans": [
                {
                    "action": p.action, "card_id": p.card_id, "card_name": p.card_name,
                    "hand_position": p.hand_position, "board_position": p.board_position,
                    "target": p.target, "target_position": p.target_position,
                    "target_card_id": p.target_card_id, "option_id": p.option_id,
                    "ai_win_rate": p.ai_win_rate,
                    "mulligan_positions": p.mulligan_positions,
                }
                for p in plans
            ],
            "raw_rec": raw_rec,
            "raw": raw,
        })

    def close(self) -> None:
        self.writer.close()

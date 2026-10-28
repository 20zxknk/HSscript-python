"""输入层：界面状态 —— 照抄作者的 ScreenLogListener。

作者不靠截图判界面，而是读游戏自己打的 `LoadingScreen.log`：

    D 09:16:33.6979585 LoadingScreen.OnSceneLoaded() - prevMode=STARTUP currMode=LOGIN
    D 09:16:51.3000526 LoadingScreen.OnScenePreUnload() - prevMode=LOGIN nextMode=HUB m_phase=INVALID

规则（ScreenLogListener.kt:25-58 / 100-109）：
- 行里有 `currMode=X`  -> 当前界面就是 X（立即生效）
- 行里有 `nextMode=Y ` -> 即将进入 Y（等真正 Loaded 或超时后生效）
- 行里有 `OnDestroy()` -> 游戏关闭，需要重启
"""
from __future__ import annotations

import re
import time
from pathlib import Path

RE_CURR = re.compile(r"currMode=(\w+)")
RE_NEXT = re.compile(r"nextMode=(\w+)")

# 作者 Mode.kt 的兜底：日志没打印"已进入"，5 秒后默认已经进入
NEXT_PROMOTE_SECONDS = 5.0


class ScreenLog:
    """增量 tail LoadingScreen.log，产出当前/下一个界面。"""

    def __init__(self, hs_dir: str | Path | None = None, poll: float = 0.2):
        if hs_dir:
            self.hs_dir = Path(hs_dir)
        else:
            try:
                self.hs_dir = self._guess_dir()
            except RuntimeError as e:
                # 离线测试 / CI 上没有炉石：没有界面日志，poll 会返回 None。
                print(f"[screenlog] {e}（离线模式）", flush=True)
                self.hs_dir = Path(".")
        self.poll = poll
        self.curr: str | None = None
        self.next: str | None = None
        self._next_at: float = 0.0
        self._path: Path | None = None
        self._fh = None
        self.closed = False
        # 只认这个时间点之后写的日志，避免读到上一次会话的残留
        self.min_mtime: float = 0.0

    # ---------------- 路径 ----------------
    @staticmethod
    def _guess_dir() -> Path:
        from .powerlog import PowerLog

        return PowerLog.guess_hearthstone_dir()

    def latest_log(self) -> Path | None:
        """只认最新会话目录里的 LoadingScreen.log（同 BUG 10）。"""
        logs = self.hs_dir / "Logs"
        if not logs.is_dir():
            return None
        dirs = [d for d in logs.iterdir() if d.is_dir()]
        if not dirs:
            return None
        newest = max(dirs, key=lambda d: d.stat().st_mtime)
        f = newest / "LoadingScreen.log"
        if not f.is_file() or f.stat().st_mtime < self.min_mtime:
            return None
        return f

    # ---------------- tail ----------------
    def _open(self, path: Path) -> None:
        self._path = path
        self._fh = open(path, "r", encoding="utf-8", errors="replace")
        self._fh.seek(0)  # 小文件全读，便于离线回放整局

    def _feed(self, line: str) -> None:
        if "OnDestroy()" in line:
            self.closed = True
            return
        m = RE_CURR.search(line)
        if m:
            self.curr = m.group(1)
            self.next = None
            self._next_at = 0.0
            return
        m = RE_NEXT.search(line)
        if m:
            self.next = m.group(1)
            self._next_at = time.time()

    def poll_once(self) -> str | None:
        f = self.latest_log()
        if f is None:
            return self.curr
        just_opened = False
        if self._path != f:
            if self._fh:
                self._fh.close()
            self.curr = self.next = None
            self._open(f)
            just_opened = True
        if self._fh:
            for line in self._fh.readlines():
                self._feed(line)
        if just_opened and self.next:
            # 刚打开一份已有日志：说明这次切换早就发生过（上一屏 -> next 已是当前屏），
            # 立即提升，避免新进程第一次读到上一屏的 currMode。
            self.curr, self.next = self.next, None
            self._next_at = 0.0
        elif self.next and self._next_at and time.time() - self._next_at > NEXT_PROMOTE_SECONDS:
            # 运行过程中：先认 currMode（OnSceneLoaded 那条），5 秒兜底（作者 Mode.kt 的定时器）
            self.curr, self.next = self.next, None
            self._next_at = 0.0
        return self.curr

    # ---------------- 查询 ----------------
    def wait_for(self, modes: str | tuple[str, ...], timeout: float = 60.0) -> str | None:
        want = (modes,) if isinstance(modes, str) else modes
        deadline = time.time() + timeout
        while time.time() < deadline:
            cur = self.poll_once()
            if cur in want:
                return cur
            time.sleep(self.poll)
        return None

    def history(self, path: str | Path) -> list[tuple[str, str]]:
        """离线回放一份日志，返回 [(时间, 事件)]，用于测试解析。"""
        out: list[tuple[str, str]] = []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                ts = line[:18].strip()
                m = RE_CURR.search(line)
                if m:
                    self._feed(line)
                    out.append((ts, f"curr={m.group(1)}"))
                    continue
                m = RE_NEXT.search(line)
                if m:
                    self._feed(line)
                    out.append((ts, f"next={m.group(1)}"))
        return out



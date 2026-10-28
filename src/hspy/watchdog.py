"""卡死取证：--debug 时把栈和心跳写到文件，事后能看它卡在哪一行。

    from hspy.watchdog import install, beat
    install(Path("test/015-112438"))
    beat("进对局")

产物（都在传入目录下）：

    watchdog-<ts>.stack   每 15 秒 dump 一次全线程栈（追加到同一个文件）
    watchdog-<ts>.beat    心跳，每 beat 一次一行，带时间与 tag
    watchdog-<ts>.exit    正常退出时写；没有这个文件说明进程是被杀或崩的

为什么不用 try/except：卡死不是异常，是某一行不返回。只有 faulthandler 能看出正在执行到哪。
真机上遇到过换牌阶段一直等、日志只剩「等起手张数」，靠这个才拿到行号。
"""
from __future__ import annotations

import atexit
import faulthandler
import os
import pathlib
import sys
import time

_FH = None
_STAMP = ""
_DIR = pathlib.Path(".")


def install(log_dir: pathlib.Path | str, every: int = 15) -> pathlib.Path:
    """装上看门狗，返回 stack 文件路径。"""
    global _FH, _STAMP, _DIR
    d = pathlib.Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)
    _DIR = d
    _STAMP = time.strftime("%Y%m%d_%H%M%S")
    stack = d / f"watchdog-{_STAMP}.stack"
    _FH = stack.open("a", encoding="utf-8", errors="replace")
    _FH.write(f"# watchdog 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} "
              f"pid={os.getpid()} argv={' '.join(sys.argv)}\n")
    _FH.flush()
    faulthandler.dump_traceback_later(every, repeat=True, file=_FH)
    atexit.register(_on_exit)
    return stack


def beat(tag: str = "") -> None:
    """心跳：卡死时看最后一次心跳就知道停在哪个阶段。"""
    if not _STAMP:
        return
    with (_DIR / f"watchdog-{_STAMP}.beat").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {tag}\n")


def _on_exit() -> None:
    try:
        faulthandler.cancel_dump_traceback_later()
    except Exception:
        pass
    if _FH is not None:
        try:
            (_DIR / f"watchdog-{_STAMP}.exit").write_text(
                f"正常退出 {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")
        except Exception:
            pass
        try:
            _FH.close()
        except Exception:
            pass

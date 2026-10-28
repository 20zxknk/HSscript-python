"""让 CloneMouse 在真实窗口上跑一段，录成 mouse.jsonl，供判别器评分。

    python -X utf8 scripts/clone_play.py --out test/clone1 --moves 40
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import win32gui  # noqa: E402

from hspy.clone import CloneMouse  # noqa: E402

ROOT_DIR = ROOT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="test/clone1")
    ap.add_argument("--moves", type=int, default=40)
    a = ap.parse_args()

    hwnd = win32gui.FindWindow("UnityWndClass", None)
    if not hwnd:
        print("找不到炉石窗口")
        return 1
    l, t, r, b = win32gui.GetClientRect(hwnd)
    W, H = r - l, b - t
    win_l, win_t = win32gui.ClientToScreen(hwnd, (0, 0))

    out = ROOT_DIR / a.out
    out.mkdir(parents=True, exist_ok=True)
    path = out / "mouse.jsonl"
    fh = path.open("w", encoding="utf-8")

    import ctypes
    import ctypes.wintypes as wt

    class POINT(ctypes.Structure):
        _fields_ = [("x", wt.LONG), ("y", wt.LONG)]

    user32 = ctypes.windll.user32

    def cursor():
        p = POINT()
        user32.GetCursorPos(ctypes.byref(p))
        return p.x - win_l, p.y - win_t

    seq = 0

    def log(ev: str) -> None:
        nonlocal seq
        seq += 1
        cx, cy = cursor()
        fh.write(json.dumps({"seq": seq, "ts": round(time.time(), 6),
                             "t": time.strftime("%H:%M:%S"), "ev": ev,
                             "sx": cx + win_l, "sy": cy + win_t, "cx": cx, "cy": cy,
                             "injected": 1}, ensure_ascii=False) + "\n")

    m = CloneMouse(dry_run=False)
    m.clip_rect = (win_l, win_t, win_l + W, win_t + H)
    rng = random.Random(9)

    # 采样线程：像真人录制的钩子一样，每 5ms 记一次光标
    import threading
    stop = threading.Event()

    last = [None]

    def sampler():
        # 只在光标真的动了才记一行，并用 8ms 采样（真人的钩子也是按系统事件来的）
        while not stop.is_set():
            cur = cursor()
            if last[0] != cur:
                last[0] = cur
                log("move")
            time.sleep(0.008)

    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    try:
        for i in range(a.moves):
            tx = rng.randint(int(W * 0.15), int(W * 0.85))
            ty = rng.randint(int(H * 0.25), int(H * 0.80))
            m.move_to(win_l + tx, win_t + ty)
            # 落点后点一下（产生按下-抬起事件，供判别器用）
            if rng.random() < 0.6:
                hold = m.rng.choice(m.press_ms) / 1000.0
                log("ldown")          # 先记按下（时间戳要在真正按下前）
                m.left_down(hold=hold)  # 内部 sleep hold
                m.left_up()
                log("lup")
            time.sleep(rng.uniform(0.35, 1.2))
    finally:
        stop.set()
        th.join(timeout=1.0)
        fh.close()
    print(f"生成 {seq} 个事件 -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

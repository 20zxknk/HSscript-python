"""把「手牌/场面」预测矩形画在当前截图上，肉眼核对坐标有没有偏。

用途：出牌点空时先看这张图 —— 框是不是落在牌上。
    python scripts/probe_rects.py            # 用日志里的手牌张数
    python scripts/probe_rects.py 6          # 强制按 6 张手牌布局
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw  # noqa: E402

from hspy import coords, win  # noqa: E402
from hspy.geometry import GameWindow  # noqa: E402
from hspy.input.powerlog import PowerLog  # noqa: E402


def draw_rect(d: ImageDraw.ImageDraw, rect, w: int, h: int, color, label: str = "") -> None:
    if rect is coords.INVALID:
        return
    x, y, rw, rh = rect.relative(w, h)
    x0, x1 = sorted((x, x + rw))
    y0, y1 = sorted((y, y + rh))
    d.rectangle((x0, y0, x1, y1), outline=color, width=2)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    d.line((cx - 8, cy, cx + 8, cy), fill=color, width=2)
    d.line((cx, cy - 8, cx, cy + 8), fill=color, width=2)
    if label:
        d.text((x0 + 2, max(0, y0 - 14)), label, fill=color)


def main() -> int:
    gw = GameWindow()
    gw.find()
    if not gw.hwnd:
        print("找不到炉石窗口")
        return 1
    gw.update()
    w, h = gw.size

    st = PowerLog().poll_once() or PowerLog().state
    hand_n = int(sys.argv[1]) if len(sys.argv) > 1 else max(st.hand_size_hint(), len(st.my_hand), 1)
    board_n = len(st.my_board)

    shot = win.capture(gw.hwnd, ".captures/probe_rects_src.png")
    im = Image.open(shot).convert("RGB")
    d = ImageDraw.Draw(im)

    for i in range(hand_n):
        r = coords.hand_card(i, hand_n)
        draw_rect(d, r, w, h, (255, 0, 0), f"H{i + 1}")
        # 也画整张牌的矩形（黄框），看"抬取点"和整张牌的相对位置
        full = coords.hand_card(i, hand_n)
        draw_rect(d, full, w, h, (255, 220, 0))
    for i in range(max(board_n, 1)):
        draw_rect(d, coords.my_minion(i, board_n), w, h, (0, 200, 255), f"B{i + 1}")
    draw_rect(d, coords.END_TURN, w, h, (0, 255, 0), "END")
    draw_rect(d, coords.MY_HERO, w, h, (255, 0, 255), "hero")

    out = ROOT / ".captures" / f"probe_rects_hand{hand_n}.png"
    im.save(out)
    print(f"client={w}x{h} hand={hand_n} board={board_n} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

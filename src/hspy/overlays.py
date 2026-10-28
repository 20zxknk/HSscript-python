"""识别挡在主菜单上的覆盖层（目前是「赛事中心」弹窗）。

为什么需要单独判断：屏幕模式（Screen.log）只报 `HUB`，覆盖层不会改变它，
于是导航会对着被盖住的「传统对战」一直点（真机实证：240 秒零进展，见 BUG 14）。

判据是**米色占比**：赛事中心那块牌桌面板在画面中央 25%~75% 的框里占一半以上，
正常主菜单几乎为 0（实测 0.50~0.52 vs 0.002）。这个差值大到不会误判，
也不需要 OCR 或模板文件。
"""
from __future__ import annotations

BEIGE_BOX = (0.25, 0.25, 0.75, 0.75)
BEIGE_MIN = 0.15          # 实测：弹窗 0.50+，正常主菜单 0.002

# 弹窗右上角「关闭」按钮（相对客户区）
CLOSE_AT = (0.72, 0.22)


def _is_beige(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return 195 <= r <= 250 and 180 <= g <= 235 and 140 <= b <= 205 and r > g > b


def beige_ratio(img, box: tuple[float, float, float, float] = BEIGE_BOX) -> float:
    """画面中央区域里「米色牌桌」像素占的比例。"""
    w, h = img.size
    crop = img.convert("RGB").crop(
        (int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))
    px = list(crop.getdata())
    if not px:
        return 0.0
    return sum(1 for p in px if _is_beige(p)) / len(px)


def tournament_modal_open(img) -> bool:
    """「赛事中心」弹窗是不是盖在主菜单上。"""
    return beige_ratio(img) >= BEIGE_MIN

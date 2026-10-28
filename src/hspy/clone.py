"""行为克隆的鼠标：轨迹从真人录制的模板库里挑，不再用参数化曲线。

原理：
  1. scripts/extract_moves.py 把真人每次移动归一化成「沿前进方向 / 法向」的
     单位长度曲线（起点在原点、终点在 (1,0)），连同每步耗时一起存库；
  2. 本模块对新目标（start→end）按 log 距离比例挑 1 条模板，
     旋转 + 缩放到目标距离，再按模板里的每步耗时重放；
  3. 点击的按下-抬起时长直接从真人样本里采样（双峰：快点 / 深思）。

和参数化实现（humanize.py + 贝塞尔）相比，这里连"碎步、来回微调、末端抖动"
都是真人自带的，不需要我们猜。
"""
from __future__ import annotations

import json
import math
import pathlib
import random
import time

from .output.mouse import Mouse

DEFAULT_LIBRARY = pathlib.Path(__file__).resolve().parents[2] / "data" / "move_templates.json"


class CloneMouse(Mouse):
    def __init__(self, library: str | pathlib.Path | None = None,
                 rng: random.Random | None = None, **kw) -> None:
        super().__init__(rng=rng, **kw)
        path = pathlib.Path(library) if library else DEFAULT_LIBRARY
        if not path.exists():
            raise RuntimeError(f"没有模板库：{path}（先跑 scripts/extract_moves.py）")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.templates = data["templates"]
        self.press_ms = data.get("press_ms") or [65.0]
        self.library_path = path

    # ---------------- 选模板 ----------------
    def _pick(self, dist: float) -> dict:
        """按「长度接近程度」加权挑一条：log 距离差越小权重越大。"""
        weights = []
        for t in self.templates:
            ratio = max(1e-3, t["len_px"] / max(1.0, dist))
            w = math.exp(-abs(math.log(ratio)) * 2.2)
            weights.append(w)
        return self.rng.choices(self.templates, weights=weights)[0]

    # ---------------- 重放 ----------------
    def move_to(self, x: int, y: int, duration: float | None = None) -> None:
        x, y = self._clip(x, y)
        if self.dry_run:
            print(f"[dry] clone move {x},{y}")
            self.prev = (x, y)
            return
        sx, sy = self.position()
        dx, dy = x - sx, y - sy
        dist = math.hypot(dx, dy)
        if dist < 2.0:
            return

        tpl = self._pick(dist)
        ux, uy = dx / dist, dy / dist          # 目标方向
        # 模板里 along 是 0..1，perp 是相对段长的偏移 -> 直接乘 dist 得到像素
        for i, (along, perp) in enumerate(tpl["pts"]):
            px = sx + ux * along * dist - uy * perp * dist
            py = sy + uy * along * dist + ux * perp * dist
            if i:
                px += self.rng.uniform(-0.6, 0.6)
                py += self.rng.uniform(-0.6, 0.6)
            self._set_cursor(px, py)
            if i < len(tpl["steps"]):
                time.sleep(tpl["steps"][i])
        self._set_cursor(x, y)
        self.prev = (x, y)

    # ---------------- 点击节奏 ----------------
    def left_down(self, hold: float | None = None) -> None:
        if self.dry_run:
            print("[dry] clone left down")
            return
        if hold is None:
            hold = self.rng.choice(self.press_ms) / 1000.0
        Mouse.left_down(self, hold=hold)

    def left_click(self, pt: tuple[int, int], settle=None) -> None:
        if self.prev != pt:
            self.move_to(pt[0], pt[1])
            time.sleep(self.rng.uniform(0.05, 0.15))
        self._left_click_hw()
        self.prev = pt

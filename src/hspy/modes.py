"""房间流程：启动游戏 → 练习模式 → 进对局（只打旅店老板）。

2026-10-23 在真机上逐步截图验证过的路径（炉石 客户端 1865x967）：

    战网已登录
      -> Battle.net.exe --exec="launch WTCG"        启动炉石
      -> 点击开始 (splash)
      -> 关任务弹窗
      -> 主界面 [其他模式]
      -> 选择模式 [冒险模式 -> 选择]
      -> [练习模式 -> 选择]  (载入中)
      -> 选套牌 [开始]
      -> 选对手 [第一个英雄] + [开始]
      -> "开始游戏" 对话框: Enter
      -> 对局开始(换牌) -> [确认]
      -> 对手回合

**绝不走「传统对战」**：全程只用 其他模式 -> 冒险 -> 练习，
坐标见 coords.OTHER_MODE / OTHER_ADVENTURE / OTHER_ADVENTURE_CHOOSE /
ADV_CHOOSE / ADV_START / ADV_FIRST_HERO。
"""
from __future__ import annotations

import subprocess
import time

from . import win

BATTLE_NET = None  # 由 config.detect_battle_net() 自动发现


def shell_execute(exe: str, args: str = "") -> int:
    """用 ShellExecuteW 启动（等价于 PowerShell 的 Start-Process）。

    实测：subprocess.Popen/CreateProcess 拉不起战网（会静默失败），
    ShellExecute 走的是 explorer 那条路，和手动双击一致。
    """
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.restype = wintypes.HINSTANCE
    res = shell32.ShellExecuteW(None, "open", exe, args, None, 1)
    # ShellExecute 返回值 > 32 表示成功
    return int(res) if res else 0


def close_game(timeout: float = 30.0) -> bool:
    """关掉炉石（纪律：一把跑完就关游戏，不许挂在那儿空等）。"""
    import time as _t

    def _running() -> bool:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Hearthstone.exe"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except Exception:
            return True
        return "Hearthstone.exe" in out

    if not _running():
        return True
    try:
        subprocess.run(["taskkill", "/IM", "Hearthstone.exe"],
                       capture_output=True, timeout=15, check=False)
    except Exception as e:
        print(f"[modes] taskkill 失败（炉石可能还开着）: {e}", flush=True)
    end = _t.time() + timeout
    while _t.time() < end:
        if not _running():
            return True
        _t.sleep(1.0)
    try:
        subprocess.run(["taskkill", "/F", "/IM", "Hearthstone.exe"],
                       capture_output=True, timeout=15, check=False)
    except Exception:
        return False
    return not _running()


def launch_game(battle_net: str | None = None, timeout: float = 180.0) -> int:
    """让战网拉起炉石（直接跑 Hearthstone.exe 会被服务层踢掉）。

    战网路径不写死：None 时由 config.detect_battle_net() 自动发现。
    战网的 launch 偶尔静默失败（Battle.net 在、但游戏没起来），
    所以每 15 秒重发一次 --exec，直到拿到有实际客户区尺寸的窗口。
    """
    if battle_net is None:
        from .config import detect_battle_net

        battle_net = str(detect_battle_net())
    try:
        hwnd = win.find_hwnd_for_process("Hearthstone.exe")
        _, _, w, h = win.client_rect(hwnd)
        if w > 200 and h > 200:
            return hwnd
    except RuntimeError:
        pass  # 没在跑，继续启动

    deadline = time.time() + timeout
    last_launch = 0.0
    while time.time() < deadline:
        if time.time() - last_launch > 15.0:
            shell_execute(battle_net, '--exec="launch WTCG"')
            last_launch = time.time()
        time.sleep(1.5)
        try:
            hwnd = win.find_hwnd_for_process("Hearthstone.exe")
            _, _, w, h = win.client_rect(hwnd)
            if w > 200 and h > 200:
                return hwnd
        except RuntimeError:
            continue
    raise RuntimeError("炉石没能启动（战网登录状态？）")


def _clusters(xs: list[int], gap: int = 6) -> list[list[int]]:
    groups: list[list[int]] = [[xs[0]]]
    for x in xs[1:]:
        if x - groups[-1][-1] <= gap:
            groups[-1].append(x)
        else:
            groups.append([x])
    return groups


def find_red_pill(img, box_ratio: tuple[float, float, float, float] = (0.43, 0.325, 0.57, 0.385)) -> tuple[int, int] | None:
    """红色药丸（认输按钮）中心。box_ratio 是相对截图的比例，不写死像素。"""
    _w, _h = img.size
    x0, y0, x1, y1 = (
        int(box_ratio[0] * _w), int(box_ratio[1] * _h),
        int(box_ratio[2] * _w), int(box_ratio[3] * _h),
    )
    crop = img.crop((x0, y0, x1, y1)).convert("RGB")
    w, h = crop.size
    px = crop.load()
    cols: dict[int, list[int]] = {}
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 85 and r > 1.7 * g and r > 1.7 * b:
                cols.setdefault(x, []).append(y)
    if not cols:
        return None
    groups = _clusters(sorted(cols))
    best = max(groups, key=len)
    if len(best) < 70:
        return None
    ys = [y for x in best for y in cols[x]]
    return x0 + (best[0] + best[-1]) // 2, y0 + (min(ys) + max(ys)) // 2


def find_confirm_button(img, box_ratio: tuple[float, float, float, float] = (0.33, 0.47, 0.70, 0.75)) -> tuple[int, int] | None:
    """确认框里左边那个奶黄色按钮（确定）。比例定位。"""
    _w, _h = img.size
    x0, y0, x1, y1 = (
        int(box_ratio[0] * _w), int(box_ratio[1] * _h),
        int(box_ratio[2] * _w), int(box_ratio[3] * _h),
    )
    crop = img.crop((x0, y0, x1, y1)).convert("RGB")
    w, h = crop.size
    px = crop.load()
    cols: dict[int, list[int]] = {}
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 185 and g > 165 and 110 < b < 225:
                cols.setdefault(x, []).append(y)
    if not cols:
        return None
    groups = [g for g in _clusters(sorted(cols), gap=8) if len(g) > 30]
    if not groups:
        return None
    left = groups[0]
    ys = [y for x in left for y in cols[x]]
    return x0 + (left[0] + left[-1]) // 2, y0 + (min(ys) + max(ys)) // 2









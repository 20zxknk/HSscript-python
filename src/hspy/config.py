"""运行期配置 —— 全部自动发现，零写死路径。

发现顺序：显式参数 > 环境变量 > 注册表（暴雪安装记录/协议处理器）> 运行中的进程。
找不到就抛错并提示设置环境变量，**不猜目录**。

脚本自己的偏好（模式/卡组位/桥路径）在仓库根的 `config.toml`（不进 git），
没写就用这里的 DEFAULT_SCRIPT，不把任何数字散落在代码里。
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

ENV_HS_DIR = "HSPY_HS_DIR"
ENV_BATTLE_NET = "HSPY_BATTLE_NET"

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.toml"


# ---------------------------------------------------------------- 脚本偏好
@dataclass
class ScriptConfig:
    """对应作者 script.ini 里的那几项：跑哪个模式、用几号位卡组。"""

    run_mode: str = "casual"          # casual / standard / wild（作者 RunModeEnum）
    deck_pos: int = 1                 # 卡组位（1 基，作者 CHOOSE_DECK_POS）
    deck_click_count: int = 3         # 作者 selectDeck: lClickDeckPos(3)
    match_timeout: float = 120.0      # 匹配超时（作者 MATCH_MAXIMUM_TIME，秒）
    bridge_script: str = ""           # 推荐桥脚本路径（空则用仓库同级的）
    bridge_cwd: str = ""
    seconds: float = 900.0            # 一局最多跑多久
    mouse_backend: str = "bezier"     # bezier（默认）/ clone（模板重放）
    # 拟人思考的缩放：快攻卡组要快（0.2~0.4），长考反而像脚本、还会烧绳；
    # 控制/组合技可以接近 1.0。
    think_scale: float = 1.0

    def bridge(self) -> tuple[str, str]:
        script = self.bridge_script
        cwd = self.bridge_cwd
        if not script:
            # 默认：作者仓库里的 recommendation_server.py（与 hs-py 同级）
            cand = REPO_ROOT.parent / "script-main" / "recommendation_server.py"
            script = str(cand)
            cwd = cwd or str(cand.parent)
        return script, cwd


def load_script_config(path: Path | None = None) -> ScriptConfig:
    """读 config.toml（可缺省），只认 [script] 段里的同名字段。"""
    cfg = ScriptConfig()
    p = Path(path) if path else CONFIG_PATH
    if not p.exists():
        return cfg
    try:
        import tomllib

        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # 配置写坏了不该拖死脚本，但要说清楚
        print(f"[config] 读取 {p} 失败，用默认值: {e}")
        return cfg
    sec = data.get("script") or {}
    for k, v in sec.items():
        if hasattr(cfg, k):
            setattr(cfg, k, type(getattr(cfg, k))(v))
    return cfg


# ---------------------------------------------------------------- 注册表
def _reg_value(root, path: str, name: str) -> str | None:
    try:
        import winreg

        with winreg.OpenKey(root, path) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return v
    except Exception:
        return None


def _hearthstone_from_registry() -> Path | None:
    """炉石的安装位置记录在「应用和功能」的卸载项里（InstallLocation）。"""
    import winreg

    uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Hearthstone"
    uninstall32 = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Hearthstone"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub in (uninstall32, uninstall):
            loc = _reg_value(root, sub, "InstallLocation")
            if loc and Path(loc, "Hearthstone.exe").exists():
                return Path(loc)
            icon = _reg_value(root, sub, "DisplayIcon")
            if icon:
                p = Path(icon.strip('"').split(",")[0])
                if p.name.lower() == "hearthstone.exe" and p.exists():
                    return p.parent
    return None


def _battle_net_from_config() -> Path | None:
    """战网自己的配置文件里记着安装目录。"""
    cfg = Path(os.environ.get("APPDATA", "")) / "Battle.net" / "Battle.net.config"
    if not cfg.exists():
        return None
    try:
        import json

        data = json.loads(cfg.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        return None
    path = None
    for k, v in data.items():
        if k.lower() == "path" and isinstance(v, str):
            path = v
            break
    if path:
        p = Path(path) / "Battle.net.exe"
        if p.exists():
            return p
    return None


def _battle_net_from_registry() -> Path | None:
    """battlenet:// 协议的打开命令里就是 exe 完整路径。"""
    import winreg

    for sub in (r"battlenet\shell\open\command", r"SOFTWARE\Classes\battlenet\shell\open\command"):
        cmd = _reg_value(winreg.HKEY_CLASSES_ROOT, sub, "") or _reg_value(
            winreg.HKEY_LOCAL_MACHINE, sub, ""
        )
        if not cmd:
            continue
        # 形如: "D:\Battle.net\Battle.net.exe" -- "%1"
        s = cmd.strip()
        if s.startswith('"'):
            end = s.find('"', 1)
            exe = s[1:end] if end > 0 else ""
        else:
            exe = s.split(" ")[0]
        if exe and Path(exe).exists():
            return Path(exe)
    return None


# ---------------------------------------------------------------- 进程
def _process_path(image_name: str) -> Path | None:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="mbcs", errors="replace",
        ).stdout
        pids = []
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.append(int(parts[1]))
        if not pids:
            return None
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        for pid in pids:
            h = k32.OpenProcess(0x1000, False, pid)
            if not h:
                continue
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    return Path(buf.value)
            finally:
                k32.CloseHandle(h)
    except Exception:
        return None
    return None


# ---------------------------------------------------------------- 对外
def detect_hearthstone_dir() -> Path:
    env = os.environ.get(ENV_HS_DIR)
    if env:
        return Path(env)
    p = _hearthstone_from_registry()
    if p:
        return p
    p = _process_path("Hearthstone.exe")
    if p:
        return p.parent
    raise RuntimeError(f"找不到炉石安装目录，请设置环境变量 {ENV_HS_DIR}")


def detect_battle_net() -> Path:
    env = os.environ.get(ENV_BATTLE_NET)
    if env:
        return Path(env)
    p = _battle_net_from_registry()
    if p:
        return p
    p = _battle_net_from_config()
    if p:
        return p
    p = _process_path("Battle.net.exe")
    if p:
        return p
    raise RuntimeError(f"找不到战网，请设置环境变量 {ENV_BATTLE_NET}")


def hearthstone_logs_dir() -> Path:
    return detect_hearthstone_dir() / "Logs"


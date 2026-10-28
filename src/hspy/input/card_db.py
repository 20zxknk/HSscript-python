"""卡牌元数据：日志里读不到"这是不是随从"时，以卡池为准。

为什么需要它（见 docs/reference/powerlog.md）：

* 日志里的 `tag=CARDTYPE` 会被裸 `tag=` 挂错实体，只能当后备；
* `cardType` 为空是常态（衍生/召唤物），旧代码用"有攻或血"猜 —— 附魔
  （如 `BE_207e`）同样带攻血，会被当成随从上场，场面人数和"点第 N 只"全错；
* 地标（`type=LOCATION`）占场面格子、但不是随从，**不能**算进可攻击目标。

数据来自 `data/card_meta.json.gz`（scripts/build_card_meta.py 生成，官方简中表 + 本地库），
缺文件时 `kind()` 返回 None，调用方退回日志里的 `cardType`，不会静默当成随从。
"""
from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path

# src/hspy/input/card_db.py -> 仓库根
META_PATH = Path(__file__).resolve().parents[3] / "data" / "card_meta.json.gz"

_cache: dict[str, dict] | None = None
_loaded_from: Path | None = None


def _load() -> dict[str, dict]:
    global _cache, _loaded_from
    if _cache is not None:
        return _cache
    path = META_PATH
    if not path.exists():
        _cache = {}
        return _cache
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                _cache = json.load(f)
        else:
            with open(path, encoding="utf-8") as f:
                _cache = json.load(f)
        _loaded_from = path
    except Exception as e:  # 坏文件不能把整局打挂：退回日志判定
        print(f"[card_db] 读 {path} 失败，随从判定退回日志 cardType: {e}", flush=True)
        _cache = {}
    return _cache


@lru_cache(maxsize=8192)
def kind(card_id: str) -> str | None:
    """卡牌类型（`MINION` / `SPELL` / `LOCATION` / `ENCHANTMENT` …），未知返回 None。"""
    if not card_id:
        return None
    meta = _load().get(card_id)
    if not meta:
        return None
    return (meta.get("type") or "").upper() or None


@lru_cache(maxsize=8192)
def is_minion(card_id: str) -> bool | None:
    """True/False = 卡池明确；None = 卡池里没有这张卡，交给调用方后备。"""
    k = kind(card_id)
    return None if k is None else k == "MINION"


def loaded() -> bool:
    """卡库到底有没有加载上（自检/日志用）。"""
    return bool(_load())


def source() -> Path | None:
    return _loaded_from

"""生成卡牌元数据表 `data/card_meta.json`：{cardId: {name, type, attack, health, cost, text}}。

两个来源，官方优先：
  1. 官方简体中文卡牌表 https://api.hearthstonejson.com/v1/latest/zhCN/cards.json（含衍生物）
  2. 作者本地库 D:\\desk\\hearthstone\\script-main\\hs_cards.db（离线兜底）

`type` 是这里最关键的一列：`MINION` 才是随从，`ENCHANTMENT` / `HERO` / `WEAPON` / `SPELL`
都上不了场面。之前靠 CARDTYPE tag 猜，会把附魔（BE_207e）当成随从上场。

    python -X utf8 scripts/build_card_meta.py [--offline]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import urllib.request
from pathlib import Path

DEFAULT_DB = Path(r"D:\desk\hearthstone\script-main\hs_cards.db")
OUT = Path("data/card_meta.json.gz")
URL = "https://api.hearthstonejson.com/v1/latest/zhCN/cards.json"
FIELDS = ("name", "type", "attack", "health", "cost", "text")


def from_official() -> dict[str, dict]:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        os.environ.setdefault("https_proxy", proxy)
        os.environ.setdefault("http_proxy", proxy)
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    out = {}
    for c in data:
        cid = c.get("id")
        if not cid:
            continue
        out[cid] = {k: c.get(k) for k in FIELDS if c.get(k) not in (None, "")}
    return out


def from_sqlite(db: Path) -> dict[str, dict]:
    if not db.exists():
        return {}
    con = sqlite3.connect(str(db))
    rows = con.execute("select cardId, name, type, attack, health, cost, text from cards").fetchall()
    con.close()
    out = {}
    for cid, name, ctype, atk, hp, cost, text in rows:
        item = {}
        for k, v in (("name", name), ("type", ctype), ("attack", atk),
                     ("health", hp), ("cost", cost), ("text", text)):
            if v not in (None, "", 0) or (k == "attack" and v == 0) or (k == "health" and v == 0):
                if v not in (None, ""):
                    item[k] = v
        if item:
            out[cid] = item
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()

    local = from_sqlite(Path(a.db))
    official: dict[str, dict] = {}
    if not a.offline:
        try:
            official = from_official()
            print(f"官方表：{len(official)} 张")
        except Exception as e:
            print(f"官方表下载失败（{type(e).__name__}: {e}），只用本地库")
    print(f"本地库：{len(local)} 张")

    merged = dict(local)
    for cid, item in official.items():
        merged.setdefault(cid, {}).update(item)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(merged, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    kinds: dict[str, int] = {}
    for item in merged.values():
        kinds[item.get("type", "?")] = kinds.get(item.get("type", "?"), 0) + 1
    print(f"写出 {out}：{len(merged)} 张，{out.stat().st_size // 1024} KB")
    print("类型分布：" + "，".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:6]))
    for probe in ("BE_207", "BE_207e", "BE_085t", "BE_013t5", "JAIL_399"):
        item = merged.get(probe, {})
        print(f"  {probe:<10} {item.get('name', '（无）')}　type={item.get('type', '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

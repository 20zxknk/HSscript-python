"""把需要的卡图下到 data/card_images/<cardId>.png。

来源：`https://art.hearthstonejson.com/v1/render/latest/zhCN/256x/<cardId>.png`（整张卡面）
（该站镜像的是暴雪官方卡牌美术，炉石官网 hs.blizzard.cn/cards 用的是同一套原画）

    python -X utf8 scripts/fetch_card_images.py --cards BE_726 TLC_451
    python -X utf8 scripts/fetch_card_images.py --json logs/boards-19-16-seg7.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import urllib.request
from pathlib import Path

OUT = Path("data/card_images")
URL = "https://art.hearthstonejson.com/v1/render/latest/zhCN/256x/{card}.png"


def fetch(card: str, out_dir: Path) -> str:
    dest = out_dir / f"{card}.png"
    if dest.exists() and dest.stat().st_size > 1024:
        return "已存在"
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        os.environ.setdefault("https_proxy", proxy)
        os.environ.setdefault("http_proxy", proxy)
    req = urllib.request.Request(URL.format(card=card), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:
        return f"失败 {type(e).__name__}: {e}"
    if len(data) < 1024:
        return "失败 图片太小"
    dest.write_bytes(data)
    return f"OK {len(data) // 1024} KB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", nargs="*", default=[])
    ap.add_argument("--json", action="append", default=[])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    cards = set(a.cards)
    for j in a.json:
        cards.update(json.loads(io.open(j, encoding="utf-8").read())["cards"])
    if not cards:
        print("没有要给卡图的卡")
        return 1

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for card in sorted(cards):
        res = fetch(card, out_dir)
        print(f"  {card:<14} {res}")
        ok += res.startswith(("OK", "已存在"))
        fail += res.startswith("失败")
    print(f"共 {len(cards)} 张：成功 {ok}，失败 {fail}，目录 {out_dir}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

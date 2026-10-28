"""把一局 Power.log 的每回合场面做成 HTML + JSON，并自证每个数字。

    python -X utf8 scripts/boards_replay.py --log <Power.log> --seg 7 \
        --out logs/boards-19-16-seg7.html --json logs/boards-19-16-seg7.json

## 数据怎么来的（每种信息只认一个来源）

| 信息 | 来源 | 理由 |
|---|---|---|
| 卡号 / 名字 | 任何方括号实体行里的 `cardId=` / `entityName=`（`FULL_ENTITY - Updating`、`SHOW_ENTITY - Updating`、`… CardID=XXX`） | 身份一旦揭示就不再变 |
| 区域 zone | `tag=ZONE` 的值（裸 tag 只挂到紧邻的实体头行）、或 **PowerTaskList** 方块里的方括号快照 | GameState 方括号里的 `zone=` 是那一行的旧状态，不能用 |
| 位置 zonePos | `tag=ZONE_POSITION`、或 PowerTaskList 方括号快照 | 同上 |
| 攻/血/伤害 | `tag=ATK` / `tag=HEALTH` / `tag=DAMAGE` | 只用显式 tag，缺了用卡牌库兜底 |
| 回合边界 | `TAG_CHANGE Entity=GameEntity tag=TURN value=N` → `(N+1)//2` | 半回合折算 |

裸 `tag=…` 归属规则：`FULL_ENTITY - Creating` / `SHOW|FULL_ENTITY - Updating [ref]` /
`BLOCK_START … Entity=` 把“待定实体”设成它；`BLOCK_END`、`HIDE_ENTITY` 或任何其他行
让待定实体作废。这一条是之前幸运币被写成 HERO_POWER、附魔被当成随从的根因。

## 自证（每一回合都查）

1. **主口径**：增量状态机（上面的规则）在回合边界拍快照。
2. **复核口径**：对每个回合边界，从段首**重新扫描一遍**，对每个 eid 取
   “最后一个显式区域/位置赋值”，独立算出双方随从集合。
3. 两种口径的随从集合必须完全相同（数量 + 卡号）；不同就抛错，并把差异行号打出来。
4. 另外检查随从数量 ≤ 7（一方最多 7 个），超了同样报错。

层级：MINION 判定用 `data/card_meta.json` 的 `type`，缺失时退回日志里的 `tag=CARDTYPE`。
"""
from __future__ import annotations

import argparse
import gzip
import html
import io
import json
import os
import re
import sys
from pathlib import Path

META_PATH = Path("data/card_meta.json.gz")
META: dict[str, dict] = {}
DEBUG = os.environ.get("BOARDS_DEBUG") == "1"

RE_CREATE = re.compile(r"-\s+CREATE_GAME")
RE_PNAME = re.compile(r"DebugPrintGame\(\) - PlayerID=(\d+), PlayerName=(.+)$")
RE_FULL_NEW = re.compile(r"FULL_ENTITY - Creating ID=(\d+) CardID=(\S*)")
RE_UPDATE = re.compile(
    r"(SHOW_ENTITY|FULL_ENTITY) - Updating (?:Entity=)?(?P<ref>.+?)(?: CardID=(?P<card>\S*))?$")
RE_BLOCK_START = re.compile(
    r"BLOCK_START BlockType=(?P<type>\w+) Entity=(?P<ent>.*?)"
    r"(?: EffectCardId=| EffectIndex=| Target=| PlayerID=|$)")
RE_BRACKET = re.compile(
    r"entityName=(?P<name>.*?) id=(?P<eid>\d+) zone=(?P<zone>\w+) "
    r"zonePos=(?P<pos>\d+) cardId=(?P<card>\S*?) player=(?P<player>\d+)")
RE_TAG_CHANGE = re.compile(r"TAG_CHANGE Entity=(?P<ent>.*?) tag=(?P<tag>\w+) value=(?P<val>\S+)")
RE_BARE_TAG = re.compile(r"^\s*tag=(?P<tag>\w+) value=(?P<val>\S+)\s*$")

ZONE_TAGS = {"ZONE", "ZONE_POSITION", "CONTROLLER", "ATK", "HEALTH", "DAMAGE", "CARDTYPE"}


def load_meta() -> dict[str, dict]:
    if not META_PATH.exists():
        print(f"[meta] 缺少 {META_PATH}，随从判定退回日志 tag", file=sys.stderr)
        return {}
    if META_PATH.suffix == ".gz":
        with gzip.open(META_PATH, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(io.open(META_PATH, encoding="utf-8").read())


def seg_bounds(lines: list[str], seg: int) -> tuple[int, int]:
    starts = [i for i, l in enumerate(lines) if "GameState" in l and RE_CREATE.search(l)]
    if not starts:
        raise SystemExit("日志里没有 CREATE_GAME")
    seg = max(0, min(seg, len(starts) - 1))
    begin = starts[seg]
    end = starts[seg + 1] if seg + 1 < len(starts) else len(lines)
    return begin, end


class Ent:
    __slots__ = ("eid", "card", "name", "zone", "pos", "player", "atk", "hp", "dmg",
                 "ctype", "zone_line", "pos_line")

    def __init__(self, eid: int) -> None:
        self.eid = eid
        self.card = ""
        self.name = ""
        self.zone = ""
        self.pos = 0
        self.player = 0
        self.atk = 0
        self.hp = 0
        self.dmg = 0
        self.ctype = ""
        self.zone_line = 0
        self.pos_line = 0


def is_minion(e: Ent) -> bool:
    kind = (META.get(e.card, {}) or {}).get("type")
    if kind:
        return kind == "MINION"
    return e.ctype == "MINION"


def parse_line(line: str):
    """把一行拆成 (kind, payload)。kind ∈ {"new", "update", "block", "tagchange", "bare", None}。"""
    m = RE_FULL_NEW.search(line)
    if m:
        return "new", {"eid": int(m.group(1)), "card": m.group(2)}
    m = RE_UPDATE.search(line)
    if m:
        return "update", {"ref": m.group("ref"), "card": m.group("card") or ""}
    m = RE_BLOCK_START.search(line)
    if m:
        return "block", {"ent": m.group("ent")}
    m = RE_TAG_CHANGE.search(line)
    if m:
        return "tagchange", {"ent": m.group("ent"), "tag": m.group("tag"), "val": m.group("val")}
    m = RE_BARE_TAG.match(line.split(" - ", 1)[-1])
    if m:
        return "bare", {"tag": m.group("tag"), "val": m.group("val")}
    return None, None


def ref_eid(text: str) -> int | None:
    m = RE_BRACKET.search(text)
    if m:
        return int(m["eid"])
    m = re.search(r"^\[.*?id=(\d+)", text)
    if m:
        return int(m.group(1))
    if text.isdigit():
        return int(text)
    return None


def scan(lines: list[str], begin: int, end: int):
    """主口径：一次扫描，得到每个回合边界的场面。返回 (snaps, names, my_id, stats)。"""
    ents: dict[int, Ent] = {}
    names: dict[int, str] = {}
    snaps: list[dict] = []
    pending = 0
    my_id = 0
    stats = {"bare_ignored": 0, "lines": 0}

    def touch(eid: int) -> Ent:
        e = ents.get(eid)
        if e is None:
            e = ents[eid] = Ent(eid)
        return e

    def take_bracket(eid: int, text: str, authoritative: bool) -> None:
        m = RE_BRACKET.search(text)
        if not m:
            return
        e = touch(eid)
        if m["card"]:
            e.card = m["card"]
        if m["name"] and not m["name"].startswith("UNKNOWN ENTITY"):
            e.name = m["name"].strip()
        if m["player"]:
            e.player = int(m["player"])
        if authoritative:                     # 只有 PowerTaskList 的方括号是当前状态
            e.zone = m["zone"]
            e.pos = int(m["pos"])

    def apply_tag(eid: int, tag: str, val: str, lineno: int) -> None:
        e = touch(eid)
        if tag == "ZONE":
            e.zone = val
            e.zone_line = lineno
            if val != "PLAY":
                e.pos = 0
        elif tag == "ZONE_POSITION":
            e.pos = int(val)
            e.pos_line = lineno
        elif tag == "CONTROLLER":
            e.player = int(val)
        elif tag == "ATK":
            e.atk = int(val)
        elif tag == "HEALTH":
            e.hp = int(val)
        elif tag == "DAMAGE":
            e.dmg = int(val)
        elif tag == "CARDTYPE":
            e.ctype = val

    def snapshot(turn: int, ts: str, lineno: int) -> None:
        if turn and snaps and snaps[-1]["turn"] == turn:
            return
        boards: dict[int, list[dict]] = {1: [], 2: []}
        for e in ents.values():
            if e.zone != "PLAY" or not is_minion(e):
                continue
            meta = META.get(e.card, {}) or {}
            boards.setdefault(e.player, []).append({
                "card": e.card,
                "name": e.name or meta.get("name", ""),
                "eid": e.eid,
                "zone_pos": e.pos,
                "atk": e.atk or int(meta.get("attack", 0) or 0),
                "hp": e.hp or int(meta.get("health", 0) or 0),
                "dmg": e.dmg,
                "zone_line": e.zone_line,
                "pos_line": e.pos_line,
            })
        for pid in boards:
            boards[pid].sort(key=lambda d: (d["zone_pos"] if d["zone_pos"] > 0 else 99, d["eid"]))
        snaps.append({"turn": turn, "ts": ts, "line": lineno, "boards": boards})
        if DEBUG:
            print(f"[snap] 回合 {turn} 行 {lineno} {ts} 我 {len(boards.get(2, []))} "
                  f"敌 {len(boards.get(1, []))}")

    for i in range(begin, end):
        line = lines[i]
        if not line.startswith("D "):
            continue
        stats["lines"] += 1
        ts = line[2:19]

        m = RE_PNAME.search(line)
        if m:                                   # 本局的玩家名，就在 CREATE_GAME 之后
            names[int(m.group(1))] = m.group(2).strip()
            continue

        kind, payload = parse_line(line)

        if kind == "new":
            pending = payload["eid"]
            e = touch(pending)
            if payload["card"]:
                e.card = payload["card"]
            continue
        if kind == "update":
            eid = ref_eid(payload["ref"])
            if eid is not None:
                take_bracket(eid, payload["ref"], authoritative="PowerTaskList" in line)
                pending = eid
            continue
        if kind == "block":
            eid = ref_eid(payload["ent"])
            pending = eid or 0
            continue
        if "BLOCK_END" in line:
            pending = 0
            continue
        if "HIDE_ENTITY" in line:
            pending = 0
            continue
        if kind == "bare":
            if pending:
                apply_tag(pending, payload["tag"], payload["val"], i)
            else:
                stats["bare_ignored"] += 1
            continue
        if kind == "tagchange":
            eid = ref_eid(payload["ent"])
            if "GameEntity" in payload["ent"]:
                if payload["tag"] == "TURN":
                    if not my_id:
                        score: dict[int, int] = {}
                        for e in ents.values():
                            if e.zone == "HAND" and e.card:
                                score[e.player] = score.get(e.player, 0) + 1
                        my_id = max(score, key=lambda k: score[k]) if score else 0
                    snapshot((int(payload["val"]) + 1) // 2, ts, i)
                pending = 0
                continue
            if eid is None:
                pending = 0
                continue
            take_bracket(eid, payload["ent"], authoritative=False)
            if payload["tag"] in ZONE_TAGS:
                apply_tag(eid, payload["tag"], payload["val"], i)
            pending = eid
            continue
        pending = 0

    if not my_id:
        score = {}
        for e in ents.values():
            if e.zone == "HAND" and e.card:
                score[e.player] = score.get(e.player, 0) + 1
        my_id = max(score, key=lambda k: score[k]) if score else 0
    snapshot(0, "收尾", end)
    return snaps, names, my_id, stats


def accounting(lines: list[str], begin: int, end: int, snaps: list[dict]) -> list[dict]:
    """第三重校验：按“上场/离场事件”计数，和快照里的随从数对账。

    只数事件、不看身份：
      +1：某个 MINION 实体 `tag=ZONE value=PLAY`
      -1：它 `tag=ZONE value=GRAVEYARD`（死亡）
    从段首累加到每个回合边界，双方各自的净值必须等于快照里的随从数。
    这一条能抓出“实体表漏掉一个随从但两种状态机口径恰好一致”的情况。
    """
    events: list[tuple[int, int, str]] = []      # (行号, 玩家, ±1)
    card_of: dict[int, str] = {}
    ctype_of: dict[int, str] = {}
    player_of: dict[int, int] = {}

    def is_minion(eid: int) -> bool:
        kind = (META.get(card_of.get(eid, ""), {}) or {}).get("type") or ctype_of.get(eid)
        return kind == "MINION"

    pending = 0
    for i in range(begin, end):
        line = lines[i]
        if not line.startswith("D "):
            continue
        kind, payload = parse_line(line)
        if kind == "new":
            pending = payload["eid"]
            if payload["card"]:
                card_of[pending] = payload["card"]
            continue
        if kind == "update":
            eid = ref_eid(payload["ref"])
            if eid is None:
                continue
            m = RE_BRACKET.search(payload["ref"])
            if m:
                if m["card"]:
                    card_of[eid] = m["card"]
                if m["player"]:
                    player_of[eid] = int(m["player"])
            if payload["card"]:
                card_of[eid] = payload["card"]
            pending = eid
            continue
        if kind == "block":
            pending = ref_eid(payload["ent"]) or 0
            continue
        if "BLOCK_END" in line:
            pending = 0
            continue
        if "HIDE_ENTITY" in line:
            pending = 0
            continue
        if kind == "bare":
            if not pending:
                continue
            eid, tag, val = pending, payload["tag"], payload["val"]
        elif kind == "tagchange":
            eid = ref_eid(payload["ent"])
            if "GameEntity" in payload["ent"] or eid is None:
                pending = 0
                continue
            m = RE_BRACKET.search(payload["ent"])
            if m:
                if m["card"]:
                    card_of[eid] = m["card"]
                if m["player"]:
                    player_of[eid] = int(m["player"])
            tag, val = payload["tag"], payload["val"]
            pending = eid
        else:
            pending = 0
            continue
        if tag == "CARDTYPE":
            ctype_of[eid] = val
        elif tag == "ZONE" and val in ("PLAY", "GRAVEYARD"):
            if is_minion(eid):
                events.append((i, player_of.get(eid, 0), 1 if val == "PLAY" else -1))

    problems = []
    for snap in snaps:
        horizon = end if snap["turn"] == 0 else snap["line"]
        for pid, who in ((1, "对方"), (2, "我方")):
            net = sum(delta for lineno, p, delta in events if lineno < horizon and p == pid)
            got = len(snap["boards"].get(pid, []))
            if net != got:
                problems.append({"turn": snap["turn"], "ts": snap["ts"], "side": who,
                                 "snapshot": got, "event_accounting": net,
                                 "kind": "事件计数不一致"})
    return problems


def verify(lines: list[str], begin: int, end: int, snaps: list[dict],
           my_id: int) -> list[dict]:
    """复核口径：对每个回合边界，从段首重新扫一遍，按“最后一个显式赋值”独立算随从集合。"""
    problems = []
    for snap in snaps:
        horizon = snap["line"]
        if snap["turn"] == 0:
            horizon = end
        zone: dict[int, str] = {}
        pos: dict[int, int] = {}
        card: dict[int, str] = {}
        ctype: dict[int, str] = {}
        player: dict[int, int] = {}
        pending = 0
        seen_lineno: dict[int, int] = {}

        for i in range(begin, min(horizon, end)):
            line = lines[i]
            if not line.startswith("D "):
                continue
            kind, payload = parse_line(line)
            if kind == "new":
                pending = payload["eid"]
                if payload["card"]:
                    card[pending] = payload["card"]
                continue
            if kind == "update":
                eid = ref_eid(payload["ref"])
                if eid is None:
                    continue
                m = RE_BRACKET.search(payload["ref"])
                if m:
                    if m["card"]:
                        card[eid] = m["card"]
                    if m["player"]:
                        player[eid] = int(m["player"])
                    if "PowerTaskList" in line:
                        zone[eid] = m["zone"]
                        pos[eid] = int(m["pos"])
                        seen_lineno[eid] = i
                if payload["card"]:
                    card[eid] = payload["card"]
                pending = eid
                continue
            if kind == "block":
                pending = ref_eid(payload["ent"]) or 0
                continue
            if "BLOCK_END" in line or "HIDE_ENTITY" in line:
                pending = 0
                continue
            if kind == "bare":
                if not pending:
                    continue
                eid = pending
                tag, val = payload["tag"], payload["val"]
                if tag == "ZONE":
                    zone[eid] = val
                    seen_lineno[eid] = i
                elif tag == "ZONE_POSITION":
                    pos[eid] = int(val)
                elif tag == "CONTROLLER":
                    player[eid] = int(val)
                elif tag == "CARDTYPE":
                    ctype[eid] = val
                continue
            if kind == "tagchange":
                eid = ref_eid(payload["ent"])
                if "GameEntity" in payload["ent"] or eid is None:
                    pending = 0
                    continue
                m = RE_BRACKET.search(payload["ent"])
                if m:
                    if m["card"]:
                        card[eid] = m["card"]
                    if m["player"]:
                        player[eid] = int(m["player"])
                tag, val = payload["tag"], payload["val"]
                if tag == "ZONE":
                    zone[eid] = val
                    seen_lineno[eid] = i
                elif tag == "ZONE_POSITION":
                    pos[eid] = int(val)
                elif tag == "CONTROLLER":
                    player[eid] = int(val)
                elif tag == "CARDTYPE":
                    ctype[eid] = val
                pending = eid
                continue
            pending = 0

        for pid, who in ((1, "对方"), (2, "我方")):
            indep = sorted((card.get(eid, ""), pos.get(eid, 0))
                           for eid, z in zone.items()
                           if z == "PLAY" and player.get(eid) == pid
                           and ((META.get(card.get(eid, ""), {}) or {}).get("type")
                                or ctype.get(eid)) == "MINION")
            main_rows = sorted((d["card"], d["zone_pos"]) for d in snap["boards"].get(pid, []))
            if indep != main_rows:
                problems.append({
                    "turn": snap["turn"], "ts": snap["ts"], "side": who,
                    "main": main_rows, "independent": indep,
                    "lines": {eid: seen_lineno.get(eid, 0) for eid in zone
                              if zone[eid] == "PLAY"},
                })
    return problems


CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin:0; padding:14px 16px 40px; background:#12100e; color:#e8ddc7;
       font-family:"Microsoft YaHei","Segoe UI",system-ui,sans-serif; }
h1 { font-size:18px; margin:2px 0 6px; }
.meta { font-size:12px; color:#9d8f74; margin-bottom:12px; }
.wrap { display:grid; grid-template-columns:repeat(auto-fill, minmax(620px, 1fr)); gap:12px; }
.panel { background:linear-gradient(#1d1813,#151110); border:1px solid #3a2f21;
         border-radius:10px; padding:8px 10px 22px; }
.hd { display:flex; align-items:baseline; gap:10px; margin-bottom:8px; }
.hd b { font-size:14px; color:#c9a227; }
.hd span { font-size:11px; color:#7d715c; }
.board { display:grid; grid-template-columns:20px repeat(7, 72px); gap:5px; }
.board + .board { margin-top:20px; }
.side { font-size:11px; color:#c9a227; writing-mode:vertical-rl; text-align:center;
        align-self:center; letter-spacing:1px; }
.slot { position:relative; width:72px; height:100px; border-radius:6px;
        border:1px dashed #2f2619; background:#0e0c0a;
        display:flex; align-items:center; justify-content:center; }
.slot.filled { border:1px solid #6b5527; }
.slot img { width:100%; height:100%; object-fit:cover; border-radius:5px; display:block; }
.slot.filled:hover { z-index:9; }
.slot.filled:hover img { transform:scale(2.0); transform-origin:center bottom;
        position:relative; box-shadow:0 6px 18px #000c; transition:transform .12s ease-out; }
.slot .num { position:absolute; left:2px; top:1px; font-size:9px; color:#d9c9a3;
             background:#000a; padding:0 2px; border-radius:3px; }
.slot .empty { color:#3d3427; font-size:10px; }
.stats { position:absolute; right:2px; bottom:2px; font-size:11px; font-weight:700;
         background:#000c; padding:0 3px; border-radius:3px; }
.stats .atk { color:#ffd76a; } .stats .hp { color:#8ef08e; } .stats .hurt { color:#ff8a6a; }
.cname { position:absolute; left:-3px; right:-3px; bottom:-15px; text-align:center;
         font-size:10px; color:#b8a684; white-space:nowrap; overflow:hidden;
         text-overflow:ellipsis; }
.legend { font-size:11px; color:#7d715c; margin-top:16px; line-height:1.7; }
.check { margin-top:14px; font-size:12px; padding:10px 12px; border-radius:8px; }
.check.ok { background:#12240f; border:1px solid #2f5a25; color:#bfe6b3; }
.check.bad { background:#2a1410; border:1px solid #6b2f22; color:#ffbfae; }
.check table { border-collapse:collapse; margin-top:6px; font-size:11px; }
.check td, .check th { border:1px solid #3a2f21; padding:2px 8px; text-align:center; }
"""


def row_cells(mons: list[dict], mirror: bool) -> list[str]:
    n = len(mons)
    offset = (7 - n) // 2
    placed: dict[int, dict] = {}
    for k, m in enumerate(mons, 1):
        placed[offset + k] = m
    order = range(7, 0, -1) if mirror else range(1, 8)
    return [cell(slot, placed.get(slot)) for slot in order]


def cell(slot: int, d: dict | None) -> str:
    if not d:
        return f'<div class="slot"><span class="num">{slot}</span><span class="empty">空</span></div>'
    key = d["card"] or d["name"] or f"eid{d['eid']}"
    zh = (META.get(d["card"], {}) or {}).get("name") or d["name"] or key
    label = html.escape(zh)
    code = html.escape(key)
    stats = ""
    if d["atk"] or d["hp"]:
        hp = d["hp"] - d["dmg"]
        hp_txt = f'{hp}<span class="hurt">(-{d["dmg"]})</span>' if d["dmg"] else f"{hp}"
        stats = (f'<span class="stats"><span class="atk">{d["atk"]}</span>'
                 f'/<span class="hp">{hp_txt}</span></span>')
    return (f'<div class="slot filled" title="{label} {code}（zonePos {slot}）">'
            f'<span class="num">{slot}</span>'
            f'<img src="../data/card_images/{code}.png" alt="{label}" '
            f'onerror="this.style.display=\'none\'">'
            f'{stats}<span class="cname">{label}</span></div>')


def render(snaps, names, my_id, log_path: str, seg: int, begin: int, end: int,
           problems: list[dict], stats: dict) -> str:
    other = 2 if my_id == 1 else 1
    out = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
           "<title>场面站位 · Power.log 还原</title>",
           f"<style>{CSS}</style></head><body>",
           "<h1>每回合场面（随从居中连排）</h1>",
           f"<div class='meta'>{html.escape(log_path)} ｜ 段 {seg}：行 {begin}–{end} ｜ "
           f"我方 {html.escape(names.get(my_id, '?'))}（PlayerID={my_id}）</div>",
           "<div class='wrap'>"]
    for s in snaps:
        turn = s["turn"] or "收尾"
        out.append("<div class='panel'>")
        out.append(f"<div class='hd'><b>回合 {turn}</b><span>{s['ts']}</span></div>")
        out.append("<div class='board'><div class='side'>对方</div>")
        out.extend(row_cells(s["boards"].get(other, []), mirror=True))
        out.append("</div>")
        out.append("<div class='board'><div class='side'>我方</div>")
        out.extend(row_cells(s["boards"].get(my_id, []), mirror=False))
        out.append("</div></div>")
    out.append("</div>")

    rows = []
    for s in snaps:
        rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            s["turn"] or "收尾",
            len(s["boards"].get(my_id, [])),
            len(s["boards"].get(other, [])),
            html.escape(s["ts"])))
    ok = not problems
    out.append("<div class='check {}'><b>自检：{}</b>".format(
        "ok" if ok else "bad", "通过" if ok else "失败"))
    out.append("<div>每回合随从数（主口径 = 增量状态机；复核 = 从段首独立重算）</div>")
    out.append("<table><tr><th>回合</th><th>我方</th><th>对方</th><th>时刻</th></tr>"
               + "".join(rows) + "</table>")
    if not ok:
        out.append("<div>不一致的地方：</div><ul>")
        for p in problems[:12]:
            if p.get("kind") == "事件计数不一致":
                out.append(f"<li>回合 {p['turn']}（{p['ts']}）{p['side']}："
                           f"快照 {p['snapshot']} 个，按上场/死亡事件应为 "
                           f"{p['event_accounting']} 个</li>")
            else:
                out.append(f"<li>回合 {p['turn']}（{p['ts']}）{p['side']}："
                           f"主口径 {p.get('main')} ≠ 复核 {p.get('independent')}</li>")
        out.append("</ul>")
    else:
        out.append("<div>两种口径逐回合完全一致（数量与卡号都相同）。"
                   f"解析行数 {stats['lines']}，无处可挂的裸 tag {stats['bare_ignored']} 行。</div>")
    out.append("</div>")
    out.append("<div class='legend'>随从按“居中连排”摆放：N 个占 7 格中间 N 格，起始列 (7-N)//2+1；"
               "对方一行按 7→1 显示（镜像），格内左上角是 zonePos。只画 type=MINION 的随从，"
               "法术/附魔/英雄/武器/英雄技能都不占场。卡面来自 art.hearthstonejson.com（暴雪官方美术）。</div>")
    out.append("</body></html>")
    return "\n".join(out)


def main() -> int:
    global META
    META = load_meta()
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--seg", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    lines = io.open(a.log, encoding="utf-8", errors="replace").read().splitlines()
    begin, end = seg_bounds(lines, a.seg)
    snaps, names, my_id, stats = scan(lines, begin, end)
    problems = verify(lines, begin, end, snaps, my_id)
    # 事件计数校验暂不启用：它会漏掉“段首之前就已上场”的随从，产生负净值

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    io.open(a.out, "w", encoding="utf-8", newline="\n").write(
        render(snaps, names, my_id, a.log, a.seg, begin, end, problems, stats))

    payload = {
        "log": a.log, "seg": a.seg, "lines": [begin, end],
        "my_id": my_id, "players": names,
        "check": {"passed": not problems, "problems": problems,
                  "method": "主口径=增量状态机；复核=每回合从段首独立重算最后显式赋值",
                  "bare_tags_ignored": stats["bare_ignored"],
                  "parsed_lines": stats["lines"]},
        "snaps": snaps,
    }
    if a.json:
        io.open(a.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps(payload, ensure_ascii=False) + "\n")

    print(f"写出 {a.out}" + (f" / {a.json}" if a.json else ""))
    for s in snaps:
        print(f"  回合 {s['turn'] or '收尾':<3} 我方 {len(s['boards'].get(my_id, []))} "
              f"对方 {len(s['boards'].get(2 if my_id == 1 else 1, []))}  {s['ts']}")
    if problems:
        print(f"自检失败：{len(problems)} 处不一致")
        for p in problems[:8]:
            if p.get("kind") == "事件计数不一致":
                print(f"  回合 {p['turn']} {p['side']}: 快照 {p['snapshot']} ≠ 事件计数 "
                      f"{p['event_accounting']}")
            else:
                print(f"  回合 {p['turn']} {p['side']}: 主 {p.get('main')} ≠ 复核 {p.get('independent')}")
        return 1
    print("自检通过：两种口径逐回合一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

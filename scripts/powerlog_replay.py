"""把一段 Power.log 还原成一局完整对局，并自己校验自己。

    python -X utf8 scripts/powerlog_replay.py <Power.log> --seg 3 --out logs/powerlog-timeline-seg3.md

读法（每条都有真机原文作证）

1. **叙事只认 `GameState.*` 行**。`PowerTaskList.*` 是同一批事件的完整重放，也拿它产生
   事件会让每条动作出现两次。它只用来补“eid 是张什么牌”。

2. 身份揭示：`SHOW_ENTITY - Updating Entity=[…] CardID=X`（真机 14854 `id=63 … CardID=BE_726`）。
   紧跟其后的裸 `tag=… value=…` 属于它（14861 `tag=ZONE value=HAND`）。

3. 方括号里的 `zone=` 是那一行的旧状态，不能用来更新当前区域；区域只认 `tag=ZONE value=…`。

4. **起手张数在 GameState 里没有 ZONE 行**：起手 4 张 + 幸运币只出现在
   `DebugPrintEntityChoices` 的候选里（14126 `ChoiceType=MULLIGAN CountMin=0 CountMax=5`，
   候选 = 4 张牌 + `GAME_005`）。所以“起手”读候选，不能靠“DECK→HAND”推。

5. **换牌语义：`DebugPrintEntitiesChosen` 列的是保留的牌**。
       对手 14771 `EntitiesCount=0` → 14783/14787/14791 把 37/14/15 全 ZONE=DECK（换掉 3 张）
                                 → 14780/14784/14788 把 11/82/13 发进手牌（发到 3 张）
       我方 14774 `EntitiesCount=1` → 保留 `id=45 CATA_210`
                                 → 14829/14853/14895 把 TIME_029/TIME_026/TLC_603 换掉
                                 → 14807/14833/14861 发到 BE_729/TLC_451/BE_726
   即：候选 5 = 保留 1 + 换掉 3 + 幸运币 1；发到 3 == 换掉 3。自洽。
   之前写成“全部保留又发 3 张”，是把 `EntitiesCount` 读成了“换掉数”，方向反了。

6. 回合：`TAG_CHANGE Entity=GameEntity tag=STEP value=MAIN_READY`（只认 GameState），
   一次 = 一个半回合。结算：`TAG_CHANGE Entity=<名字#编号> tag=PLAYSTATE value=WON/LOST/CONCEDED`。
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import pathlib
import re
from dataclasses import dataclass, field

RE_CREATE = re.compile(r"-\s+CREATE_GAME")
RE_PNAME = re.compile(r"DebugPrintGame\(\) - PlayerID=(\d+), PlayerName=(.+)$")
RE_FULL_NEW = re.compile(r"FULL_ENTITY - Creating ID=(\d+) CardID=(\S*)")
RE_UPDATE = re.compile(r"(SHOW_ENTITY|FULL_ENTITY) - Updating Entity=")
RE_BRACKET = re.compile(
    r"entityName=(?P<name>.*?) id=(?P<eid>\d+) zone=(?P<zone>\w+) "
    r"zonePos=(?P<pos>\d+) cardId=(?P<card>\S*?) player=(?P<player>\d+)\]")
RE_TRAILING_CARDID = re.compile(r"\] CardID=(\S+)")
RE_TAG_CHANGE = re.compile(r"TAG_CHANGE Entity=(?P<ent>.*?) tag=(?P<tag>\w+) value=(?P<val>\S+)")
RE_BARE_TAG = re.compile(r"DebugPrintPower\(\) - +tag=(?P<tag>\w+) value=(?P<val>\S+)\s*$")
RE_BLOCK = re.compile(r"BLOCK_START BlockType=(?P<type>\w+) Entity=")
RE_CHOICE = re.compile(
    r"DebugPrintEntityChoices\(\) - id=(\d+) Player=(.+?) .*?ChoiceType=(\w+) "
    r"CountMin=(\d+) CountMax=(\d+)")
RE_CHOSEN = re.compile(r"DebugPrintEntitiesChosen\(\) - id=(\d+) Player=(.+?) EntitiesCount=(\d+)")



META_GZ = pathlib.Path("data/card_meta.json.gz")
CARD_NAMES_PATH = pathlib.Path("data/card_names.json")


def load_card_names(path: pathlib.Path = CARD_NAMES_PATH) -> dict[str, str]:
    """卡号 -> 中文名。优先 card_names.json，没有就用 card_meta.json.gz 的 name 字段。"""
    if path.exists():
        return json.loads(io.open(path, encoding="utf-8").read())
    if META_GZ.exists():
        with gzip.open(META_GZ, "rt", encoding="utf-8") as f:
            meta = json.load(f)
        return {cid: item["name"] for cid, item in meta.items() if item.get("name")}
    print(f"[names] 没有卡名表（{path} / {META_GZ}），只显示卡号；"
          f"跑 python -X utf8 scripts/build_card_meta.py 生成")
    return {}


NAMES: dict[str, str] = {}



def is_coin(g, eid: int) -> bool:
    """幸运币：卡号 GAME_005，或日志里只给了名字“幸运币”。"""
    e = g.ents.get(eid)
    if e is None:
        return False
    return e.card == "GAME_005" or e.name == "幸运币"


@dataclass
class Ent:
    eid: int
    card: str = ""
    name: str = ""
    zone: str = ""
    player: int = 0
    dmg: int = 0

    def label(self) -> str:
        if self.card:
            zh = NAMES.get(self.card)
            if zh:
                return zh
            return "幸运币" if self.card == "GAME_005" else self.card
        if self.name:
            return self.name
        return f"未知牌(eid{self.eid})"


@dataclass
class Game:
    ents: dict[int, Ent] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)
    lines: list = field(default_factory=list)
    my_id: int = 0
    pending: int = 0
    armed: bool = False
    mulligan_open: bool = False
    submitted: set = field(default_factory=set)
    candidates: dict = field(default_factory=dict)
    countmax: dict = field(default_factory=dict)
    kept: dict = field(default_factory=dict)
    replaced: dict = field(default_factory=dict)
    dealt: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    half_turn: int = 0
    hand_ever: set = field(default_factory=set)
    _recent: set = field(default_factory=set)

    def touch(self, eid: int) -> Ent:
        return self.ents.setdefault(eid, Ent(eid))

    def apply_ref(self, text: str) -> Ent | None:
        m = RE_BRACKET.search(text)
        if not m:
            return None
        e = self.touch(int(m["eid"]))
        name = m["name"].strip()
        if name and not name.startswith("UNKNOWN ENTITY"):
            e.name = name
        if m["card"]:
            e.card = m["card"]
        e.player = int(m["player"])
        return e

    def side(self, pid: int) -> str:
        if not pid or not self.my_id:
            return ""
        return "我方" if pid == self.my_id else "对方"

    def add(self, ts: str, seq: int, text: str, pid: int = 0) -> None:
        key = (ts, text)
        if key in self._recent:
            return
        self._recent.add(key)
        self.lines.append((ts, seq, 0, text, pid))

    def zone(self, e: Ent, new: str, ts: str, seq: int) -> None:
        was = e.zone
        e.zone = new
        if new == "HAND":
            self.hand_ever.add(e.eid)
        if not self.armed:
            return
        who = self.side(e.player)
        cand = set(self.candidates.get(e.player, []))
        # 换牌候选就是手牌：它变成 DECK 即“换掉”，不看跟踪到的旧区域
        if (new == "DECK" and self.mulligan_open and e.player in self.submitted
                and e.eid in cand and e.eid not in self.replaced.get(e.player, [])):
            self.replaced.setdefault(e.player, []).append(e.eid)
            self.add(ts, seq, f"{who}换掉 {e.label()}", e.player)
            return
        if (new == "HAND" and self.mulligan_open and e.player in self.submitted
                and e.eid not in cand and e.eid not in self.dealt.get(e.player, [])):
            self.dealt.setdefault(e.player, []).append(e.eid)
            self.add(ts, seq, f"{who}换牌后发到 {e.label()}", e.player)
            return
        if new == was:
            return
        if new == "HAND" and was == "DECK" and not self.mulligan_open:
            self.add(ts, seq, f"{who}抽到 {e.label()}", e.player)
        elif new == "HAND" and was in ("", "SETASIDE"):
            self.add(ts, seq, f"{who}获得 {e.label()}（生成到手牌）", e.player)
        elif new == "GRAVEYARD" and was not in ("", "GRAVEYARD"):
            self.add(ts, seq, f"{who}{e.label()} 死亡", e.player)


def resolve_pid(g: Game, name: str) -> int:
    name = name.strip()
    for pid, nm in g.names.items():
        if nm == name:
            return pid
    unknown = [pid for pid, nm in g.names.items() if nm.startswith("UNKNOWN")]
    return unknown[0] if len(unknown) == 1 else 0


def parse(path: str, seg: int) -> tuple[Game, int, int]:
    raw = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
    starts = [i for i, l in enumerate(raw) if "GameState" in l and RE_CREATE.search(l)]
    if not starts:
        raise SystemExit("这份日志里没有 CREATE_GAME")
    begin = starts[max(0, min(seg, len(starts) - 1))]
    end = starts[seg + 1] if seg + 1 < len(starts) else len(raw)
    span = raw[begin:end]

    g = Game()
    for line in span:
        m = RE_PNAME.search(line)
        if m:
            g.names[int(m.group(1))] = m.group(2).strip()
            continue
        if "entityName=" in line:
            g.apply_ref(line)
        m = RE_FULL_NEW.search(line)
        if m and m.group(2):
            g.touch(int(m.group(1))).card = m.group(2)

    score: dict[int, int] = {}
    for e in g.ents.values():
        if e.card and e.player:
            score[e.player] = score.get(e.player, 0) + 1
    g.my_id = max(score, key=lambda k: score[k]) if score else 0
    for e in g.ents.values():
        e.zone = ""

    choice = None
    chosen = None

    def finalize_chosen():
        nonlocal chosen
        if chosen and chosen["ents"] and chosen["kind"] == "MULLIGAN":
            g.kept[chosen["pid"]] = list(chosen["ents"])
        chosen = None

    for seq, line in enumerate(span):
        if not line.startswith("D ") or "GameState." not in line:
            continue
        ts = line[2:19]
        if chosen is not None and "Entities[" not in line:
            finalize_chosen()

        m = RE_CHOSEN.search(line)
        if m:
            if (not g.mulligan_open and choice is not None
                    and choice["kind"] != "MULLIGAN" and choice["ents"]):
                cand = [g.ents[e].label() for e in choice["ents"]]
                g.add(ts, seq, f"[{choice['kind']} 面板] 候选 {len(cand)} 张，"
                               f"选 {m.group(3)} 张：{cand}", 0)
            finalize_chosen()
            pid = resolve_pid(g, m.group(2))
            chosen = {"pid": pid, "kind": "MULLIGAN" if g.mulligan_open else "OTHER",
                      "ents": []}
            if pid and g.mulligan_open:
                g.submitted.add(pid)
            choice = None
            continue
        m = RE_CHOICE.search(line)
        if m:
            pid = resolve_pid(g, m.group(2))
            kind = m.group(3)
            choice = {"pid": pid, "kind": kind, "n": int(m.group(5)), "ents": []}
            chosen = None
            if kind == "MULLIGAN":
                g.mulligan_open = True
                g.armed = True
                if pid:
                    g.countmax[pid] = int(m.group(5))
            continue
        if "Entities[" in line:
            e = g.apply_ref(line)
            if e is not None:
                if chosen is not None:
                    chosen["ents"].append(e.eid)
                    if not chosen["pid"]:
                        chosen["pid"] = e.player
                        if chosen["pid"] and chosen["kind"] == "MULLIGAN":
                            g.submitted.add(chosen["pid"])
                elif choice is not None:
                    choice["ents"].append(e.eid)
                    if not choice["pid"]:
                        choice["pid"] = e.player
                    if choice["kind"] == "MULLIGAN" and choice["pid"]:
                        g.candidates.setdefault(choice["pid"], []).append(e.eid)
                        if not e.zone:
                            e.zone = "HAND"      # 候选即起手手牌
                        g.hand_ever.add(e.eid)
            continue

        if RE_UPDATE.search(line):
            e = g.apply_ref(line)
            if e is not None:
                mc = RE_TRAILING_CARDID.search(line)
                if mc:
                    e.card = mc.group(1)
                g.pending = e.eid
            continue
        m = RE_FULL_NEW.search(line)
        if m:
            g.pending = int(m.group(1))
            if m.group(2):
                g.touch(g.pending).card = m.group(2)
            continue
        m = RE_BARE_TAG.search(line)
        if m and g.pending:
            e = g.ents.get(g.pending)
            if e is not None:
                tag, val = m.group("tag"), m.group("val")
                if tag == "ZONE":
                    g.zone(e, val, ts, seq)
                elif tag == "CONTROLLER":
                    e.player = int(val)
            continue

        m = RE_TAG_CHANGE.search(line)
        if m:
            ent, tag, val = m.group("ent"), m.group("tag"), m.group("val")
            if "GameEntity" in ent:
                if tag == "PROPOSED_DEFENDER" and val.isdigit():
                    d = g.ents.get(int(val))
                    if d is not None:
                        g.add(ts, seq, f"　→ 目标 {d.label()}", d.player)
                elif tag == "STEP" and val == "MAIN_READY":
                    g.half_turn += 1
                    g.lines.append((ts, seq, 1, g.half_turn, 0))
                    g.mulligan_open = False
                continue
            if "#" in ent and "[" not in ent:
                pid = resolve_pid(g, ent)
                if tag == "PLAYSTATE" and val in ("WON", "LOST", "CONCEDED"):
                    g.result[pid] = val
                    g.add(ts, seq, f"结算：{g.names.get(pid, ent)} → {val}", pid)
                continue
            e = g.apply_ref(ent)
            if e is None and ent.strip().isdigit():
                e = g.ents.get(int(ent.strip()))
            if e is None:
                continue
            g.pending = e.eid
            if tag == "ZONE":
                g.zone(e, val, ts, seq)
            elif tag == "DAMAGE":
                new = int(val or 0)
                if new > e.dmg:
                    g.add(ts, seq, f"{e.label()} 受到 {new - e.dmg} 点伤害（累计 {new}）",
                          e.player)
                e.dmg = new
            continue

        m = RE_BLOCK.search(line)
        if m:
            btype = m.group("type")
            e = g.apply_ref(line)
            if e is None:
                continue
            who = g.side(e.player)
            if btype == "PLAY":
                if e.label().endswith("bp"):
                    verb = "使用英雄技能"
                elif e.eid in g.hand_ever:
                    verb = "打出"
                else:
                    verb = "召唤/生成"
                g.add(ts, seq, f"{who}{verb} {e.label()}", e.player)
            elif btype == "ATTACK":
                g.add(ts, seq, f"{who}{e.label()} 发起攻击", e.player)
            continue

    finalize_chosen()
    return g, begin, end


def render(path: str, seg: int) -> str:
    g, begin, end = parse(path, seg)
    ordered = sorted(g.lines, key=lambda x: (x[0], x[1]))

    def labels(eids):
        return [g.ents[e].label() for e in eids if e in g.ents]

    out = ["# 一局对局的完整还原", "",
           f"- 日志：`{path}`", f"- 段 {seg}：行 {begin}–{end}", "", "## 双方"]
    for pid, name in sorted(g.names.items()):
        hero = next((e for e in g.ents.values()
                     if e.player == pid and (e.card or "").startswith("HERO_")), None)
        out.append(f"- {g.side(pid) or '?'}：{name}　英雄 {hero.label() if hero else '?'}")

    out += ["", "## 换牌"]
    for pid in sorted(g.candidates):
        cand = g.candidates[pid]
        kept = g.kept.get(pid, [])
        coin = [e for e in cand if is_coin(g, e)]
        opening = [e for e in cand if e not in coin]
        coin_txt = " + 幸运币" if coin else ""
        out.append(f"- {g.side(pid)}起手 {len(opening)} 张{coin_txt}：{labels(opening)}")
        out.append(f"- 保留 {len(kept)} 张：{labels(kept)}；"
                   f"换掉 {len(cand) - len(kept) - len(coin)} 张")

    out += ["", "## 过程"]
    for ts, _seq, kind, payload, pid in ordered:
        if kind == 1:
            out.append(f"\n**回合 {payload}**（{ts}）")
        else:
            out.append(f"- `{ts}`  {payload}")

    out += ["", "## 校验", "",
            "### 1. 换牌算术（候选 = 保留 + 换掉 + 幸运币；发到 == 换掉）"]
    all_ok = True
    for pid in sorted(g.candidates):
        cand = g.candidates[pid]
        kept = g.kept.get(pid, [])
        rep = g.replaced.get(pid, [])
        dealt = g.dealt.get(pid, [])
        coin = [e for e in cand if is_coin(g, e)]
        expect = len(cand) - len(kept) - len(coin)
        ok = (len(rep) == expect and len(dealt) == len(rep)
              and len(kept) + len(rep) + len(coin) == len(cand))
        all_ok = all_ok and ok
        cm = g.countmax.get(pid, 0)
        out.append(f"- {g.side(pid)}{g.names[pid]}：候选 {len(cand)}（面板 CountMax {cm}，"
                   f"{'一致' if cm == len(cand) else '不一致'}；含幸运币 {len(coin)}），"
                   f"保留 {len(kept)}，换掉 {len(rep)}（应为 {expect}），发到 {len(dealt)}"
                   f" → {'OK 自洽' if ok else 'XX 不自洽'}")
    out.append(f"- 结论：{'OK 全部自洽' if all_ok else 'XX 有不自洽'}")

    out += ["", "### 2. 手牌集合（换牌前 = 候选；换牌后 = 候选 - 换掉 + 发到）"]
    for pid in sorted(g.candidates):
        cand = g.candidates[pid]
        rep = set(g.replaced.get(pid, []))
        after = [e for e in cand if e not in rep] + g.dealt.get(pid, [])
        out.append(f"- {g.side(pid)}换牌前（{len(cand)}）：{labels(cand)}")
        out.append(f"- {g.side(pid)}换牌后（{len(after)}）：{labels(after)}")

    out += ["", "### 3. 来源核对（每张打出的牌前面必须有来源）"]
    sourced: set[str] = set()
    for pid in sorted(g.candidates):
        for e in g.candidates[pid]:
            sourced.add(g.ents[e].label())
    missing: list[str] = []
    summoned: set[str] = set()
    used = 0
    for ts, _seq, kind, txt, _pid in ordered:
        if kind:
            continue
        for token in re.findall(r"(?:换牌后发到|抽到|获得) (\S+?)(?:（| |$)", txt):
            sourced.add(token)
        if "打出 " in txt:
            card = txt.split("打出 ")[-1].strip()
            used += 1
            if card not in sourced:
                missing.append(f"{ts} {card}")
        elif "召唤/生成 " in txt:
            summoned.add(txt.split("召唤/生成 ")[-1].strip())
    out.append(f"- 出牌 {used} 次，缺来源 {len(missing)} 次")
    for m in missing:
        out.append(f"  - [!] {m}")
    if not missing:
        out.append("- OK 没有凭空出现的牌")
    if summoned:
        out.append(f"- 另有场上生成（不从手牌来）：{sorted(summoned)}")

    out += ["", "### 4. 结算"]
    for pid, state in sorted(g.result.items()):
        out.append(f"- {g.names.get(pid, pid)}：{state}")
    out.append(f"- 半回合数：{g.half_turn}")
    return "\n".join(out)


def main() -> int:
    global NAMES
    NAMES = load_card_names()
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--seg", type=int, default=0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    text = render(a.log, a.seg)
    if a.out:
        io.open(a.out, "w", encoding="utf-8", newline="\n").write(text + "\n")
        print(f"写出 {a.out}（{len(text.splitlines())} 行）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

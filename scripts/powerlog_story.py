"""把一局 Power.log 讲成人能读的过程（按回合计，逐事件带原始时间戳）。

    python scripts/powerlog_story.py <Power.log> [--offset 字节] [--out 文件.md]

`--offset` 用于只讲"从这一局开始"的部分：录制时记下开赛那一刻的文件大小，
生成时从该偏移往前找最近的 `CREATE_GAME`，所以不会把上一局的尾巴带进来。

只做"读日志 + 归纳"，不推断规则：
    BLOCK_START BlockType=PLAY   -> 谁打出什么（有目标就带目标）
    BLOCK_START BlockType=ATTACK -> 谁攻击谁（PROPOSED_DEFENDER 给目标）
    BLOCK_START BlockType=POWER  -> 谁触发/施放了什么
    tag=ZONE value=GRAVEYARD     -> 阵亡（[阵亡]）
    tag=DAMAGE（英雄上）          -> 英雄累计伤害
    tag=TURN / STEP / PLAYSTATE  -> 回合、换牌、出牌阶段、结算
    SHOW_ENTITY - Updating ...   -> 揭示/抽到
块是**带深度**的（PLAY 里套 TRIGGER 是常态），所以这里按行流走一遍，
只把 GameState 流当正文（PowerTaskList 会把每个块重打一遍）。
"""
from __future__ import annotations

import argparse
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TS = re.compile(r"^D (\d\d:\d\d:\d\d\.\d+)")
# 名字里可能带空格和方括号（"UNKNOWN ENTITY [cardType=INVALID]"），名字取非贪婪到 " id="
REF = re.compile(r"\[entityName=(.*?) id=(\d+) zone=(\S+) zonePos=(\d+) cardId=([^\s\]]*) player=(\d+)\]")
FULL = re.compile(r"FULL_ENTITY - (?:Creating|Updating) ID=(\d+) CardID=(\S*)")
SHOW = re.compile(r"SHOW_ENTITY - Updating Entity=(\[.*?) CardID=(\S+)")
BLOCK = re.compile(r"BLOCK_START BlockType=(\w+)")
TAG = re.compile(r"TAG_CHANGE Entity=(.+?) tag=(\w+) value=(\S*)")
TARGET_EID = re.compile(r"Target=(\d+)")
DEFENDER = re.compile(r"tag=PROPOSED_DEFENDER value=(\d+)")


@dataclass
class Ent:
    eid: int
    name: str = ""
    card_id: str = ""
    player: int = 0
    zone: str = ""


@dataclass
class Story:
    lines: list[str] = field(default_factory=list)
    ents: dict[int, Ent] = field(default_factory=dict)
    blocks: Counter = field(default_factory=Counter)
    events: int = 0

    def ent(self, eid: int) -> Ent:
        return self.ents.setdefault(eid, Ent(eid=eid))

    def learn(self, ref: str) -> int | None:
        m = REF.search(ref)
        if not m:
            return None
        name, eid, zone, _pos, cid, player = m.groups()
        e = self.ent(int(eid))
        if name:
            e.name = name
        if zone:
            e.zone = zone
        if player:
            e.player = int(player)
        if cid:
            e.card_id = cid
        return e.eid

    def label(self, eid: int | None) -> str:
        if eid is None:
            return "?"
        e = self.ent(eid)
        # 日志对隐藏实体只打 `UNKNOWN ENTITY [cardType=INVALID]`，名字没意义，用卡号代替
        name = "" if e.name.startswith("UNKNOWN") else e.name
        cid = f"({e.card_id})" if e.card_id else ""
        side = f"P{e.player} " if e.player else ""
        return f"{side}{name}{cid}".strip() or f"eid={eid}"

    def emit(self, stamp: str, text: str) -> None:
        self.events += 1
        self.lines.append(f"`{stamp}`  {text}")


def parse_players(raw: list[str]) -> tuple[dict[int, int], dict[int, int]]:
    eid2pid: dict[int, int] = {}
    pid2hero: dict[int, int] = {}
    cur_pid = 0
    for ln in raw:
        m = re.search(r"Player EntityID=(\d+) PlayerID=(\d+)", ln)
        if m:
            cur_pid = int(m.group(2))
            eid2pid[int(m.group(1))] = cur_pid
            continue
        m = re.search(r"tag=HERO_ENTITY value=(\d+)", ln)
        if m and cur_pid:
            pid2hero[cur_pid] = int(m.group(1))
    return eid2pid, pid2hero


def build(lines: list[str]) -> Story:
    st = Story()
    seen: set[tuple[str, str, str]] = set()
    pending_attack: tuple[str, str] | None = None
    last_turn: str = ""

    for raw in lines:
        m_ts = TS.match(raw)
        stamp = m_ts.group(1)[:12] if m_ts else "--:--:--.---"
        is_gs = "GameState.DebugPrintPower" in raw

        m_ref = REF.search(raw)
        if m_ref:
            st.learn(m_ref.group(0))
        m_full = FULL.search(raw)
        if m_full and m_full.group(2):
            st.ent(int(m_full.group(1))).card_id = m_full.group(2)

        m_block = BLOCK.search(raw)
        if m_block:
            btype = m_block.group(1)
            src_eid = st.learn(m_ref.group(0)) if m_ref else None
            if is_gs:
                st.blocks[btype] += 1
                if btype == "PLAY":
                    m_t = TARGET_EID.search(raw)
                    tgt = ""
                    if m_t and m_t.group(1) != "0":
                        tgt = f" → 目标 eid {m_t.group(1)}"
                    st.emit(stamp, f"打出 {st.label(src_eid)}{tgt}")
                elif btype == "ATTACK":
                    st.emit(stamp, f"攻击 {st.label(src_eid)}")
                    pending_attack = (stamp, st.label(src_eid))
                elif btype == "POWER":
                    st.emit(stamp, f"触发/施放 {st.label(src_eid)}")
            continue

        if "BLOCK_END" in raw:
            continue

        m_def = DEFENDER.search(raw)
        if m_def:
            if m_def.group(1) == "0":      # 攻击结束会把 PROPOSED_DEFENDER 清零，忽略
                continue
            dfd = st.label(int(m_def.group(1)))
            if pending_attack:
                st.emit(pending_attack[0], f"  → 目标 {dfd}")
                pending_attack = None
            else:
                st.emit(stamp, f"  → 目标 {dfd}")
            continue

        m_tag = TAG.search(raw)
        if m_tag:
            ent_s, tag, val = m_tag.groups()
            eid = st.learn(ent_s) if ent_s.startswith("[") else None
            key = (tag, val, stamp)
            if tag == "TURN":
                # 回合号只认 GameState 流、且必须**递增**：PowerTaskList 会重放历史，
                # 直接读会看到 2→1→2→1 这种回跳。
                if is_gs and val.isdigit() and int(val) > int(last_turn or 0):
                    last_turn = val
                    st.emit(stamp, f"—— 回合 {val} ——")
            elif tag == "STEP" and val == "BEGIN_MULLIGAN" and is_gs and key not in seen:
                seen.add(key)
                st.emit(stamp, "换牌阶段")
            elif tag == "STEP" and val == "MAIN_START" and is_gs and key not in seen:
                seen.add(key)
                st.emit(stamp, "进入出牌阶段")
            elif tag == "PLAYSTATE" and val in ("WON", "LOST", "CONCEDED", "TIED") and key not in seen:
                seen.add(key)
                st.emit(stamp, f"结算：{ent_s.strip()} → {val}")
            elif tag == "ZONE" and val == "GRAVEYARD" and eid and is_gs:
                st.emit(stamp, f"  [阵亡] 阵亡 {st.label(eid)}")
            elif tag == "DAMAGE" and eid and is_gs:
                if st.ent(eid).card_id.startswith("HERO_"):
                    st.emit(stamp, f"  英雄累计伤害 {val}（{st.label(eid)}）")
            continue

        m_show = SHOW.search(raw)
        if m_show and is_gs:
            eid = st.learn(m_show.group(1))
            st.emit(stamp, f"揭示/抽到 {m_show.group(2)}（{st.label(eid)}，区域 "
                           f"{st.ent(eid).zone if eid else '?'}）")
    return st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("powerlog")
    ap.add_argument("--offset", type=int, default=0, help="只讲这个字节偏移所在的那一局")
    ap.add_argument("--out", default="", help="输出 markdown（默认打印到 stdout）")
    args = ap.parse_args()

    path = Path(args.powerlog)
    text = io.open(path, encoding="utf-8", errors="replace").read()
    start = 0
    if args.offset > 0:
        head = text[: args.offset]
        k = head.rfind("CREATE_GAME")
        start = k if k >= 0 else 0
    lines = text[start:].splitlines()

    cg = [i for i, ln in enumerate(lines) if "CREATE_GAME" in ln]
    eid2pid, pid2hero = parse_players(lines[cg[0]: cg[0] + 400]) if cg else ({}, {})
    st = build(lines)

    out: list[str] = ["# Power.log 对局叙述", ""]
    out.append(f"- 来源：`{path}`")
    out.append(f"- 起始偏移：`{start}` 字节" +
               ("（从该偏移前最近的 CREATE_GAME 开始）" if start else "（整份文件）"))
    out.append(f"- 总行数：{len(lines)}，识别出 {st.events} 个事件")
    if eid2pid:
        pl = "；".join(f"PlayerID={pid}（玩家实体 {eid}，英雄实体 {pid2hero.get(pid, '?')}）"
                       for eid, pid in sorted(eid2pid.items()))
        out.append(f"- 玩家：{pl}")
    names = sorted({m for ln in lines for m in re.findall(r"Entity=([^\s\]]+#\d+) tag=", ln)})
    if names:
        out.append(f"- 日志里出现的玩家名：{', '.join(names)}")
    out.append(f"- 块统计：{dict(st.blocks)}")
    out.append("")
    out.append("> 时间戳为 Power.log 每行原始 `D HH:MM:SS.ffffff`（本机本地时间），"
               "可与 `mouse.jsonl`、`recommendations.jsonl` 的 `t` 直接对表。")
    out.append("")
    out.append("---")
    out.append("")
    out.extend(st.lines)

    md = "\n".join(out) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"写入 {args.out}（{st.events} 个事件，{len(lines)} 行）")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

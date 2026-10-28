"""输入层：对局状态模型。"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import card_db


def _dedupe_by_pos(cards: list) -> list:
    """同一 zone_pos 只留一个（eid 最大 = 最新）。"""
    best: dict[int, object] = {}
    for e in cards:
        cur = best.get(e.zone_pos)
        if cur is None or e.eid > cur.eid:
            best[e.zone_pos] = e
    return list(best.values())


def board_rank(cards: list, card_id: str = "", zone_pos: int = 0) -> int:
    """该随从在场面列表里的**密集下标**（作者 Area.indexOfCard 的语义）。

    作者的做法：卡牌进场面时按 pos-1 插进 `cards` 列表，离场就删，所以列表
    永远是 0..n-1 连续的，`indexOfCard()` 返回的就是它在列表里的下标。

    同名多张时必须用 zone_pos 消歧（否则永远点第一张 —— "点错随从"就是这个）：
        ① cardId + zone_pos 都对得上 -> 用它
        ② 只有一张同名 -> 用它
        ③ 多张同名但没有 zone_pos -> 用第一张
    """
    if card_id:
        cand = [i for i, e in enumerate(cards) if e.card_id == card_id]
        if cand:
            if len(cand) == 1:
                return cand[0]
            if zone_pos:
                for i in cand:
                    if cards[i].zone_pos == zone_pos:
                        return i
            return cand[0]
    if zone_pos:
        for i, e in enumerate(cards):
            if e.zone_pos == zone_pos:
                return i
        return max(0, min(zone_pos - 1, len(cards) - 1))
    return 0


def _is_real_card(e: "Entity") -> bool:
    """手牌/场面里只算真正的卡牌：排除英雄、英雄技能、游戏对象、附魔。"""
    if e.card_type in ("HERO", "HERO_POWER", "GAME", "ENCHANTMENT", "INVALID"):
        return False
    cid = e.card_id or ""
    # **不能按 `GAME_` 前缀排除**：`GAME_005` 就是幸运币，它是手牌里能打出的真卡；
    # 以前把它整类排除，手牌列表少一张、点击布局按 N-1 排，整排右移一格全点空
    # （真机实证 13:35 那局：实体 9 张、列表 8 张，槽 3 的币永远点不到）。
    # 日志没给类型时，卡池说了算：附魔/英雄技能即使 cardType 为空也不能当卡牌。
    if card_db.kind(cid) in ("ENCHANTMENT", "HERO", "HERO_POWER", "GAME", "INVALID", "PLAYER"):
        return False
    if cid.endswith("hp") or cid.endswith("hp1") or cid.endswith("dbp"):
        return False
    return True


def _is_board_card(e: "Entity") -> bool:
    """能不能算"场面上的东西"（随从/地标）。

    判据以卡池为准（docs/reference/powerlog.md）：`type` 是 `MINION` / `LOCATION`
    才占场面格子；法术、附魔、英雄都不上场。日志里的 `cardType` 只当后备 ——
    真机踩过：附魔 `BE_207e`（带攻血、cardType 常为空）被当成随从，场面人数多一只、
    "点第 N 只"整体错位；地标 `CATA_492` 占格子但不是随从，不能算进攻击目标。

    卡池里查不到的卡（新卡/未知衍生）仍按"不是英雄/技能/法术/武器/附魔"放进来，
    宁可按场面算，也不要整块场面丢空。
    """
    if not _is_real_card(e):
        return False
    k = card_db.kind(e.card_id)
    if k is not None:
        return k in ("MINION", "LOCATION")
    return e.card_type in ("", "MINION", "LOCATION")


def _is_minion_like(e: "Entity") -> bool:
    return e.zone == "PLAY" and _is_board_card(e)


@dataclass
class Entity:
    eid: int
    card_id: str = ""
    name: str = ""
    card_type: str = ""  # MINION / HERO / SPELL / WEAPON / ...
    controller: int = 0
    zone: str = ""  # HAND / PLAY / DECK / SECRET / GRAVEYARD
    zone_pos: int = 0
    cost: int = 0
    atk: int = 0
    health: int = 0
    damage: int = 0
    armor: int = 0
    taunt: bool = False
    divine_shield: bool = False
    frozen: bool = False
    stealth: bool = False
    exhausted: bool = False  # 本回合刚上场
    num_attacks: int = 0
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def is_minion(self) -> bool:
        """场面随从（可被攻击的目标）。

        判据以卡池为准（`type == "MINION"`）：地标、法术、附魔都不算随从。
        `card_type` 只当后备 —— 真机实证很多衍生/召唤物（如 BE_085t、CATA_725t）
        在日志里 `cardType` 是空的，但已经是随从；反过来附魔带攻血却**不是**随从。
        """
        if self.zone != "PLAY":
            return False
        k = card_db.kind(self.card_id)
        if k is not None:
            return k == "MINION"
        if self.card_type in ("HERO", "HERO_POWER", "WEAPON", "ENCHANTMENT", "INVALID",
                              "GAME", "SPELL", "LOCATION"):
            return False
        if self.card_type == "MINION":
            return True
        return not self.card_type and (self.atk > 0 or self.health > 0)

    @property
    def is_hero(self) -> bool:
        return self.card_type == "HERO"

    @property
    def hp(self) -> int:
        return max(0, self.health - self.damage)


@dataclass
class Player:
    pid: int
    name: str = ""
    hero: Entity | None = None
    hand: list[Entity] = field(default_factory=list)
    board: list[Entity] = field(default_factory=list)
    mana: int = 0
    mana_max: int = 0
    deck_count: int = 0


@dataclass
class GameState:
    started: bool = False
    finished: bool = False
    turn: int = 0            # 我方玩家的完整回合数（Entity=<我> tag=TURN）
    turn_global: int = 0     # GameEntity 的半回合计数（1,2,3,4…）
    my_id: int = 0
    current_player: int = 0
    players: dict[int, Player] = field(default_factory=dict)
    entities: dict[int, Entity] = field(default_factory=dict)
    # 发现/抉择面板（DebugPrintEntityChoices）：候选按游戏给的顺序排
    discover_open: bool = False
    discover_options: int = 0
    choice_open: bool = False
    choices: list = field(default_factory=list)   # [{"index","card_id","name","eid"}]
    choice_player: str = ""
    choice_type: str = ""
    choice_min: int = 0
    choice_max: int = 0
    mulligan_open: bool = False
    # DebugPrintOptions 里的手牌（pid -> {ZONE_POSITION: cardId}）。
    # 盒子读的是同一份东西，槽位以它为准，别自己数实体。
    hand_options: dict[int, dict[int, str]] = field(default_factory=dict)
    # 同一份选项里的 (槽位 -> 实体 id)：游戏对"这张牌在界面第几个"的权威声明
    hand_option_eids: dict[int, dict[int, int]] = field(default_factory=dict)
    hand_options_seq: int = 0     # 上一次「选项快照」的日志序号
    hand_mutation_seq: int = 0    # 手牌列表最后一次被事件改动的日志序号
    option_errors: dict[int, str] = field(default_factory=dict)  # eid -> 游戏给的不可用原因
    end_turn_option_seq: int = 0  # 上一次「option type=END_TURN」的日志序号（=真的轮到我动手）
    turn_seq: int = 0              # 本回合开始（CURRENT_PLAYER/TURN 变化）的日志序号
    hand_entities_seq: int = 0    # 上一次「手牌实体变化」的日志序号

    # ---------------- 查询 ----------------
    @property
    def me(self) -> Player | None:
        return self.players.get(self.my_id)

    @property
    def rival(self) -> Player | None:
        for pid, p in self.players.items():
            if pid != self.my_id:
                return p
        return None

    @property
    def my_hand(self) -> list[Entity]:
        """我的手牌，**按游戏的 ZONE_POSITION 排**（列表下标 = 槽位-1）。

        以前直接返回增量维护的 `p.hand`：插入/左移/选项快照回填会累积漂移，
        真机实证（2026-10-27 19:47:29）列表把 TIME_026 放在第 4 位（槽 4），
        但它的 `ZONE_POSITION` 是 4、盒子也报 4 —— 列表顺序却和 zonePos 对不上，
        `hand_slot` 断言拿列表下标去比，于是每 6 步失败一次、整局卡死。
        手牌槽位是**游戏声明的**（zonePos 1..N），不是我们维护列表的顺序。
        """
        p = self.me
        if not p:
            return []
        out = [e for e in p.hand if e.zone == "HAND"]
        # 同一槽位只留一个（eid 最大 = 最新）；zonePos=0 的幽灵放最后
        best: dict[int, Entity] = {}
        ghosts: list[Entity] = []
        for e in out:
            if e.zone_pos <= 0:
                ghosts.append(e)
                continue
            cur = best.get(e.zone_pos)
            if cur is None or e.eid > cur.eid:
                best[e.zone_pos] = e
        return [best[k] for k in sorted(best)] + ghosts

    @property
    def my_board(self) -> list[Entity]:
        p = self.me
        return p.board if p else []

    @property
    def rival_board(self) -> list[Entity]:
        p = self.rival
        return p.board if p else []

    @property
    def is_my_turn(self) -> bool:
        return self.my_id != 0 and self.current_player == self.my_id

    @property
    def my_action_window(self) -> bool:
        """是不是**真的**轮到我能操作了。

        只看 current_player 不够（真机实测：日志刚翻到我就去点，游戏界面还停在
        对手回合，出牌/结束回合全被吞）。游戏只在"轮到你操作"时才打选项块，
        其中 `option 0 type=END_TURN` 是最硬的信号 ⇒ 要求和 current_player 同时满足。

        `turn_seq` 是**回合起点**（GameEntity TURN 行，带"只许前进"守卫），
        不是 CURRENT_PLAYER 行 —— 后者会被 PowerTaskList 原样重放，拿它当时间戳
        会在选项块到达 30ms 后把窗口重新关上（真机 2026-10-28 09:12:24，整回合空过）。
        """
        if not self.is_my_turn:
            return False
        if self.end_turn_option_seq == 0:
            return True          # 从没读到选项块：退回旧判断
        return self.end_turn_option_seq >= self.turn_seq

    def my_hand_slots(self) -> dict[int, str]:
        """游戏自己列出的我的手牌槽位 {ZONE_POSITION: cardId}（DebugPrintOptions）。

        这份就是盒子读的东西，也是唯一权威的"手牌张数/槽位"来源；
        实体表会漏（真机踩过：4 张手牌只建出 3 个实体，点出来整体偏一格）。
        """
        return self.hand_options.get(self.my_id) or {}

    def hand_slot_entities(self) -> dict[int, Entity]:
        """槽位 -> 实体（只认实体自己的 `ZONE_POSITION`，不认方括号快照）。

        `DebugPrintOptions` 的 `mainEntity=[… zonePos=…]` 是**打那一行时的旧状态**
        （docs/reference/powerlog.md）：真机实证 19:47:28.493 先打
        `tag=ZONE_POSITION value=4`，6ms 后的选项括号里还写着 `zonePos=5`。
        所以槽位一律以实体身上最新的 tag 为准，选项括号只在实体没位置时兜底。
        """
        best: dict[int, Entity] = {}
        for e in self.entities.values():
            if e.controller != self.my_id or e.zone != "HAND" or not e.card_id:
                continue
            if e.zone_pos < 1:
                continue
            cur = best.get(e.zone_pos)
            if cur is None or e.eid > cur.eid:
                best[e.zone_pos] = e
        return best

    def slot_cards(self, slot: int) -> list[str]:
        """这个槽位上"游戏声明过的卡号"（实体 zonePos 与选项快照两个来源）。

        两者一致是最常见的；不一致时**两个都算数**（断言只问"盒子点名的牌在不在这个槽"），
        谁旧谁新交给点击结果和后续日志裁决 —— 不再用"我们列表的第几个"去否决盒子。
        """
        ids: list[str] = []
        ent = self.hand_slot_entities().get(slot)
        if ent is not None and ent.card_id:
            ids.append(ent.card_id)
        opt = self.my_hand_slots().get(slot)
        if opt and opt not in ids:
            ids.append(opt)
        return ids

    def slot_eid(self, slot: int) -> int:
        """这个槽位上的实体 id（实体 zonePos 优先，选项快照兜底）。"""
        ent = self.hand_slot_entities().get(slot)
        if ent is not None:
            return ent.eid
        return int((self.hand_option_eids.get(self.my_id) or {}).get(slot) or 0)

    def hand_size_hint(self) -> int:
        """点击布局用的手牌张数。

        取"游戏选项声明的最右槽位"与"实体表里 zone=HAND 的真实张数/最右槽位"的较大者。
        **不能**只数 click 列表里的牌：选项块只列当前可选的动作（真机实证：
        手牌 6 张、选项里只 2 张），按选项数排布局会把整排点击矩形排窄 → 点空。
        也**不能**把 cardId 为空的占位实体算进去（会多算一格、同样整排偏一格）。

        还要算上**回合开始摸的那张**：test5 实测——开局 4 张、摸 1 张后手牌 5 张，
        选项块只列出 4 张能打的（最右槽 4），而刚摸进来那张的 zonePos=6；
        只看选项会把布局当成 5 张排，槽 5 落在 1104（5 张布局），
        实际应该是 6 张布局的 1013 —— 点了 4 次全是空。

        **zonePos=0 的实体不算手牌**：test7 实测——手上真实 3 张
        （TIME_029@1、TIME_026@2、TIME_025@3），另有 2 个 `TIME_025t` 也是 zone=HAND
        但 zonePos=0（效果生成的分身，不在栏位上）。把它们算进去 → 手牌当 5 张排，
        槽 3 点在 5 张布局的位置，6 次全空。
        """
        # 选项快照只在自己比手牌变动**新**的时候才用来定张数：
        # 出牌后日志已经把每张牌的新位置打出来了（ZONE_POSITION），
        # 而旧快照还停在出牌前的槽位（test7：手牌 3 张、旧快照最右槽 4 -> 按 4 张排）。
        slots = self.my_hand_slots() if self.hand_options_seq >= self.hand_mutation_seq else {}
        hand_ents = [
            e for e in self.entities.values()
            if e.controller == self.my_id and e.zone == "HAND" and _is_real_card(e)
            and e.card_id and e.zone_pos >= 1      # zonePos=0 = 不在手牌栏位上（见下）
        ]
        known = len(hand_ents)
        max_pos = max((e.zone_pos for e in hand_ents), default=0)
        # **张数以实体为准**：实体的 zonePos 由日志逐条更新（出牌后每张牌都会打新的
        # ZONE_POSITION），而选项快照可能是"出牌前"的那一份（test7：快照最右槽 4，
        # 实际只剩 3 张）。只有实体表里一张手牌都没有时，才退回用快照的槽位数。
        if known or max_pos:
            return max(known, max_pos)
        return max(slots) if slots else 0

    def choice_index_of(self, card_id: str) -> int | None:
        """选择面板里这张卡是第几个（0 基，游戏给的顺序）；不在面板里返回 None。"""
        if not card_id:
            return None
        for c in self.choices:
            if c.get("card_id") == card_id:
                return int(c.get("index") or 0)
        return None

    def move_entity(self, e: "Entity") -> None:
        """按作者 `Area.add/removeByEntityId` 的语义，把实体挪到它 zone/zone_pos 说的位置。

        **先无条件从原区域摘掉**：牌死了/变形了（card_type 变 INVALID）也必须移除，
        否则场面上会留一只幽灵，让"点第 N 只"整体错位。
        """
        p = self.players.get(e.controller)
        if p is None:
            return
        for lst in (p.hand, p.board):
            for i, x in enumerate(lst):
                if x.eid == e.eid:
                    lst.pop(i)
                    break
        if not _is_real_card(e) or e.zone_pos <= 0:
            return          # 不是可点牌 / 还没落位（作者的"零区"）：不插入
        if e.zone == "HAND":
            target = p.hand
        elif e.zone == "PLAY" and _is_board_card(e):
            target = p.board
        else:
            return
        target.insert(max(0, min(e.zone_pos - 1, len(target))), e)

    # 注意：场面**不能**按 zone_pos 重排。实测（12 份留档）单只随从上场后
    # zone_pos 会一直停在它插入时的号（例如只剩一只时仍是 2 或 3），
    # 排序会让"点第 N 只"点错。作者的语义是：插入到 pos-1、离场即左移，
    # 列表顺序靠"事件顺序"维护，而不是靠重读位置。

    def resync_hand(self) -> None:
        """按"实体表里 zone=HAND 且 zonePos>=1"重建手牌列表。

        增量维护（插入/左移）会累积漂移：真机实证 —— 打出去一张牌之后，我们列表里
        它还挂着，于是盒子继续推这张牌、我们反复点同一个已经空掉的槽（点了零反应）。
        每来一份新的选项快照就整体重建一次，最差也是"和游戏当前声明一致"。
        """
        for pid, p in self.players.items():
            ents = [e for e in self.entities.values()
                    if e.zone == "HAND" and e.controller == pid and e.zone_pos >= 1]
            ents.sort(key=lambda e: e.zone_pos)
            if ents:
                p.hand = ents

    def apply_option_slots(self) -> None:
        """用 `DebugPrintOptions` 的 (槽位, 实体) 把可打出的牌**钉**回正确槽位。

        [!] 不能"用选项列表整体重建手牌"：选项块只列**当前可选**的动作，
        手上其它牌不出现（真机实证：手牌 6 张、选项里只有 2 张 → 重建后
        手牌变 2 张，点击布局按 2 张排，整排点空）。所以这里只做"钉位置"：
        选项点名的实体按它声明的槽位插入/补卡号，其余牌保持原相对顺序。
        """
        for pid, slots in self.hand_option_eids.items():
            p = self.players.get(pid)
            if p is None or not slots:
                continue
            # **过期的选项快照不许再用来摆牌**：真机实证 —— 打出一张牌之后，
            # 那份旧选项还在把这张牌塞回手牌列表，于是我们以为它还在手上、
            # 反复点同一个空槽（点了没反应、盒子又一直推同一张）。
            if self.hand_options_seq < self.hand_mutation_seq:
                continue
            items = sorted(slots.items())          # [(slot, eid)]
            opt_ids = self.hand_options.get(pid) or {}
            rebuilt: list[Entity] = []
            for slot, eid in items:
                ent = self.entities.get(eid)
                if ent is None:
                    continue
                # **钉位置不等于改区域**：一个实体如果已经被 ZONE=PLAY 移走了，
                # 选项快照不许把它拉回手牌。真机实证（test3 回合4）：CATA_210 打出后，
                # 02:29:05.94 那份选项里还带着它（type=POWER 的触发项），
                # 这里一句 `ent.zone = "HAND"` 就把它塞回槽 2，整排手牌编号全部错位，
                # 于是"盒子要第 4 槽的 TLC_603"被我们当成"第 1 槽"。
                if ent.zone not in ("HAND", ""):
                    continue
                cid = opt_ids.get(slot) or ""
                if cid and not ent.card_id:
                    ent.card_id = cid              # 游戏给的卡号，比我们拼的准
                # **位置只认日志的 ZONE_POSITION**（出牌后每张牌的新位置日志都会逐条打印：
                #   TAG_CHANGE [id=22 zone=HAND zonePos=4] tag=ZONE_POSITION value=3
                #   TAG_CHANGE [id=31 zone=HAND zonePos=3] tag=ZONE_POSITION value=2
                # ），选项快照只用来补"位置未知"的实体。
                # 以前无条件 `ent.zone_pos = slot`：test7 实测——打出 CATA_210 后日志已把
                # BE_207/TIME_029/TIME_026 改成 1/2/3，下一次 refresh() 又被旧快照按
                # 2/3/4 钉回去，槽位整体右移一格，连续 6 次点空。
                if ent.zone == "" or ent.zone_pos <= 0:
                    ent.zone = "HAND"
                    ent.zone_pos = slot
                rebuilt.append(ent)
            if not rebuilt:
                continue
            # 选项没点名、但实体表说还在手牌的牌：按 zone_pos 顺序补到后面。
            # 只补 zone 确实是 HAND 的（上面那条守卫已经把"已离手却被快照点名"的挡掉了）。
            seen = {e.eid for e in rebuilt}
            extra = [e for e in sorted(self.entities.values(), key=lambda x: (x.zone_pos, x.eid))
                     if e.eid not in seen and e.controller == pid and e.zone == "HAND"
                     and _is_real_card(e) and e.card_id and e.zone_pos >= 1]
            p.hand = rebuilt + extra

    def refresh(self) -> None:
        """只补齐玩家/英雄这类"谁的"信息；区域列表由 move_entity 增量同步。"""
        if self.hand_option_eids:
            self.apply_option_slots()
        # 不变量兜底：只清理"确实已经离场"的实体（坟墓/移出游戏/实体表里没了）。
        # 不能把 SETASIDE 当离场：换牌被替换的牌、换进来的新牌都会短暂待在 SETASIDE，
        # 摘掉就会"手牌少一张"（真机实测：换牌后手牌只剩 2 张，盒子却按 3 张报槽位）。
        dead = {"GRAVEYARD", "REMOVEDFROMGAME"}
        for p in self.players.values():
            p.hand = [e for e in p.hand
                      if e.eid in self.entities and e.zone not in dead]
            p.board = [e for e in p.board
                       if e.eid in self.entities and e.zone not in dead
                       and _is_board_card(e)]
        for p in self.players.values():
            if p.hero is None:
                for e in self.entities.values():
                    if e.controller == p.pid and e.card_type == "HERO":
                        p.hero = e
                        break
        # 兜底：从没收到 ZONE 的事件（例如日志截断）时，把有 zone 的实体补进去
        for e in sorted(self.entities.values(), key=lambda x: x.eid):
            if e.zone_pos <= 0 or not _is_real_card(e):
                continue
            p = self.players.get(e.controller)
            if p is None:
                continue
            lst = p.hand if e.zone == "HAND" else (
                p.board if _is_minion_like(e) else None
            )
            if lst is None or any(x.eid == e.eid for x in lst):
                continue
            # 槽位已经有人（同一 pos 两个 eid 是实体分裂/衍生物的典型症状）：
            # 以选项快照重建出来的列表为准，这里不硬塞，否则会出现两个"第 1 张"。
            if any(x.zone_pos == e.zone_pos for x in lst):
                continue
            self.move_entity(e)

    def snapshot(self) -> dict:
        """给决策层/日志用的精简快照（盒子桥不依赖它，但调试要看）。"""
        me, rv = self.me, self.rival
        return {
            "turn": self.turn,
            "my_turn": self.is_my_turn,
            "my_id": self.my_id,
            "current_player": self.current_player,
            "mine": {
                "id": self.my_id,
                "mana": f"{me.mana}/{me.mana_max}" if me else "",
                "hero_hp": me.hero.hp if me and me.hero else None,
                "hand": [
                    {"eid": e.eid, "card": e.card_id, "name": e.name, "cost": e.cost}
                    for e in (me.hand if me else [])
                ],
                "board": [
                    {"eid": e.eid, "card": e.card_id, "atk": e.atk, "hp": e.hp,
                     "taunt": e.taunt, "ds": e.divine_shield, "can_attack": self._can_attack(e)}
                    for e in (me.board if me else [])
                ],
            },
            "rival": {
                "hero_hp": rv.hero.hp if rv and rv.hero else None,
                "hand_count": len(rv.hand) if rv else 0,
                "board": [
                    {"eid": e.eid, "card": e.card_id, "atk": e.atk, "hp": e.hp,
                     "taunt": e.taunt, "ds": e.divine_shield}
                    for e in (rv.board if rv else [])
                ],
            },
        }

    @staticmethod
    def _can_attack(e: Entity) -> bool:
        return e.atk > 0 and not e.frozen and not e.exhausted and e.num_attacks < 1






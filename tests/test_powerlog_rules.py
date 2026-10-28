"""Power.log 读法规则（docs/reference/powerlog.md）在**实时解析器**里的回归。

每条用例都对应一次真机踩坑（括号里的时间/行号是真日志）：

1. 选项括号里的 `zonePos` 是旧状态 —— 按它改槽会把牌点空、每 6 步失败一次（19:47:28）；
2. PowerTaskList 里的 `tag=ZONE` 是随从上场的唯一证据 —— 跳过它对手场面永远少人；
3. 裸 `tag=` 只属于紧邻的实体头行，别的行插进来就作废；
4. `SHOW_ENTITY` 也是归属者 —— 不设 pending 会把 SETASIDE 写到刚上场的随从身上（13:45:03）；
5. 随从/地标/附魔按卡池判 —— 附魔带攻血但不是随从，地标占格子但不能被攻击；
6. 手牌顺序只认 `ZONE_POSITION` —— 列表增量维护会漂移（19:47 那局列表 4 位、实际槽 5）。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hspy.input.event_types import EV_ENTITY_FULL  # noqa: E402
from hspy.input.powerlog import PowerLog, classify_line  # noqa: E402
from hspy.input.state import Entity, GameState, Player  # noqa: E402

TS = "D 00:00:00.0000000 "


def make_log(my_id: int = 2) -> PowerLog:
    """不碰磁盘/注册表的解析器实例（只喂行）。"""
    pl = PowerLog.__new__(PowerLog)
    pl.hs_dir = pathlib.Path(".")
    pl.poll = 0
    pl.state = GameState(started=True)
    pl.state.my_id = my_id
    pl.state.players = {1: Player(pid=1), 2: Player(pid=2)}
    pl.bad_values = 0
    pl._fh = None
    pl._path = None
    pl._last_create_ts = ""
    pl._pending_entity = None
    pl._seen_players = []
    pl._my_id_override = my_id
    pl._name_to_eid = {}
    pl._name_to_pid = {}
    pl.seq = 0
    pl.seg_index = 0
    pl.seg_closed = False
    pl._my_id_locked = True
    pl._player_names = {}
    pl._pinned = None
    pl._record = None
    pl._record_seg = 0
    pl._tail = []
    pl._action_buf = []
    pl._replaying = True
    pl.records_dir = None
    return pl


def feed(pl: PowerLog, *lines: str) -> None:
    for ln in lines:
        pl.seq += 1
        pl._feed(TS + ln + "\n")
    pl.state.refresh()


def test_option_bracket_zone_pos_is_stale() -> None:
    """19:47:28.493 先改 ZONE_POSITION=4，6ms 后的选项括号还写 zonePos=5。"""
    pl = make_log()
    feed(pl,
         "GameState.DebugPrintPower() - FULL_ENTITY - Creating ID=61 CardID=TIME_026",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=61 tag=CONTROLLER value=2",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=61 tag=ZONE value=HAND",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=61 tag=ZONE_POSITION value=4",
         "GameState.DebugPrintOptions() - id=11",
         "GameState.DebugPrintOptions() -   option 3 type=POWER "
         "mainEntity=[entityName=续连熵能 id=61 zone=HAND zonePos=5 cardId=TIME_026 player=2] "
         "error=NONE errorParam=")
    st = pl.state
    assert st.my_hand_slots() == {4: "TIME_026"}, st.my_hand_slots()
    assert st.slot_cards(4) == ["TIME_026"], st.slot_cards(4)
    assert st.slot_cards(5) == [], st.slot_cards(5)
    assert st.hand_size_hint() == 4, st.hand_size_hint()
    print("OK   选项括号 zonePos=5 不覆盖实体的 ZONE_POSITION=4")


def test_option_of_played_card_not_a_hand_slot() -> None:
    """打出去的牌还在选项里（type=POWER），它的 zonePos 是场面位置，不是手牌槽。"""
    pl = make_log()
    feed(pl,
         "GameState.DebugPrintPower() - FULL_ENTITY - Creating ID=45 CardID=CATA_210",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=45 tag=CONTROLLER value=2",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=45 tag=ZONE value=PLAY",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=45 tag=ZONE_POSITION value=2",
         "GameState.DebugPrintOptions() - id=12",
         "GameState.DebugPrintOptions() -   option 5 type=POWER "
         "mainEntity=[entityName=暮光龙卵 id=45 zone=HAND zonePos=2 cardId=CATA_210 player=2] "
         "error=NONE errorParam=")
    assert pl.state.my_hand_slots() == {}, pl.state.my_hand_slots()
    print("OK   已上场的牌不会被选项括号拉回手牌槽")


def test_tasklist_zone_change_puts_rival_minion_on_board() -> None:
    """对手随从的 `tag=ZONE value=PLAY` 只在 PowerTaskList 里。"""
    pl = make_log()
    feed(pl,
         "GameState.DebugPrintPower() - FULL_ENTITY - Creating ID=12 CardID=",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=12 tag=CONTROLLER value=1",
         "PowerTaskList.DebugPrintPower() - BLOCK_START BlockType=PLAY "
         "Entity=[entityName=UNKNOWN ENTITY [cardType=INVALID] id=12 zone=HAND zonePos=5 "
         "cardId= player=1] EffectCardId=System.Collections.Generic.List`1[System.String] "
         "EffectIndex=0 Target=0 SubOption=-1",
         "PowerTaskList.DebugPrintPower() -     SHOW_ENTITY - Updating "
         "Entity=[entityName=小鬼马仔 id=12 zone=HAND zonePos=5 cardId=JAIL_399 player=1] "
         "CardID=JAIL_399",
         "PowerTaskList.DebugPrintPower() -     tag=ZONE value=PLAY",
         "PowerTaskList.DebugPrintPower() -     tag=ZONE_POSITION value=1")
    e = pl.state.entities[12]
    assert (e.card_id, e.zone, e.zone_pos) == ("JAIL_399", "PLAY", 1), (e.card_id, e.zone, e.zone_pos)
    assert [x.card_id for x in pl.state.rival_board] == ["JAIL_399"], \
        [x.card_id for x in pl.state.rival_board]
    print("OK   PowerTaskList 的 ZONE=PLAY 能落到对手场面")


def test_bare_tag_invalidated_by_other_line() -> None:
    """裸 tag 前面插进任何别的行，就不能再挂到上一个实体上。"""
    pl = make_log()
    feed(pl,
         "GameState.DebugPrintPower() - FULL_ENTITY - Creating ID=12 CardID=JAIL_399",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=12 tag=CONTROLLER value=1",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=12 tag=ZONE value=HAND",
         "GameState.DebugPrintPowerList() - Count=101",
         "PowerTaskList.DebugPrintPower() -             tag=ZONE value=PLAY")
    e = pl.state.entities[12]
    assert e.zone == "HAND", e.zone
    assert not pl.state.rival_board, [x.card_id for x in pl.state.rival_board]
    print("OK   无关行让裸 tag 作废（不会把牌写上场）")


def test_show_entity_owns_following_tags() -> None:
    """13:45:03：`SHOW_ENTITY … id=123` 后紧跟的 ZONE=SETASIDE 必须属于 123。"""
    pl = make_log()
    feed(pl,
         "GameState.DebugPrintPower() - FULL_ENTITY - Creating ID=84 CardID=TIME_029",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=84 tag=CONTROLLER value=2",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=84 tag=ZONE value=PLAY",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=84 tag=ZONE_POSITION value=1",
         "PowerTaskList.DebugPrintPower() - BLOCK_START BlockType=POWER "
         "Entity=[entityName=灾毁迅疾幼龙 id=84 zone=PLAY zonePos=1 cardId=TIME_029 player=2] "
         "EffectCardId=System.Collections.Generic.List`1[System.String] EffectIndex=0 "
         "Target=0 SubOption=-1",
         "PowerTaskList.DebugPrintPower() -     SHOW_ENTITY - Updating "
         "Entity=[entityName=时空撕裂 id=123 zone=DECK zonePos=0 cardId= player=2] "
         "CardID=TIME_025t",
         "PowerTaskList.DebugPrintPower() -         tag=ZONE value=SETASIDE")
    assert pl.state.entities[84].zone == "PLAY", pl.state.entities[84].zone
    e = pl.state.entities[123]
    assert (e.card_id, e.zone) == ("TIME_025t", "SETASIDE"), (e.card_id, e.zone)
    print("OK   SHOW_ENTITY 是裸 tag 的归属者（不会串到上一条实体）")


def test_tasklist_updating_without_entity_prefix() -> None:
    """PowerTaskList 的实体行没有 `Entity=` 前缀，旧正则一条都解析不到。"""
    kind, data = classify_line(
        TS + "PowerTaskList.DebugPrintPower() -     FULL_ENTITY - Updating "
        "[entityName=UNKNOWN ENTITY [cardType=INVALID] id=43 zone=DECK zonePos=0 "
        "cardId= player=2] CardID=")
    assert kind == EV_ENTITY_FULL, kind
    assert data["ref"]["eid"] == 43, data
    print("OK   `FULL_ENTITY - Updating [entityName=…]` 能解析出 eid")


def test_minion_judgement_uses_card_db() -> None:
    """附魔带攻血但不是随从；地标占格子但不能被攻击；随从按卡池认。"""
    def ent(eid: int, cid: str, **kw) -> Entity:
        return Entity(eid=eid, card_id=cid, zone="PLAY", zone_pos=eid, **kw)

    assert not ent(1, "BE_207e", atk=3, health=3).is_minion      # 附魔（威力增强）
    assert not ent(2, "CATA_492", health=2).is_minion            # 地标（暮光神坛）
    assert ent(3, "TIME_029", atk=6, health=6).is_minion         # 随从
    assert ent(4, "ZZZ_999", atk=2, health=2).is_minion          # 卡池没有：按攻血后备
    assert not ent(5, "ZZZ_999").is_minion                       # 没有攻血且类型未知：不算
    print("OK   随从判定以卡池为准（附魔/地标不算随从）")


def test_hand_list_follows_zone_pos() -> None:
    """手牌列表顺序 = ZONE_POSITION，不是增量插入的顺序。"""
    st = GameState(started=True, my_id=2)
    st.players = {2: Player(pid=2)}
    # 模拟漂移：先插入 B（槽 1），再插入 A（槽 2），最后 C（槽 3）
    for eid, cid, pos in ((2, "B", 1), (1, "A", 2), (3, "C", 3)):
        e = Entity(eid=eid, card_id=cid, controller=2, zone="HAND", zone_pos=pos,
                   card_type="SPELL")
        st.entities[eid] = e
        st.move_entity(e)
    assert [e.card_id for e in st.my_hand] == ["B", "A", "C"], \
        [e.card_id for e in st.my_hand]
    assert st.slot_cards(2) == ["A"] and st.slot_cards(3) == ["C"]
    # 盒子的槽位断言问的是"槽 2 是不是 A"，不是"列表第 2 个是不是 A"
    assert "A" in st.slot_cards(2)
    print("OK   手牌列表按 ZONE_POSITION 排（槽位断言不再看列表下标）")


def test_coin_is_a_real_hand_card() -> None:
    """GAME_005 是幸运币，能打出；不能因为 `GAME_` 前缀被排除。"""
    st = GameState(started=True, my_id=2)
    st.players = {2: Player(pid=2)}
    for eid, cid, pos in ((41, "TIME_026", 1), (42, "GAME_005", 2)):
        e = Entity(eid=eid, card_id=cid, controller=2, zone="HAND", zone_pos=pos,
                   card_type="SPELL", cost=0)
        st.entities[eid] = e
        st.move_entity(e)
    assert [e.card_id for e in st.my_hand] == ["TIME_026", "GAME_005"]
    assert st.hand_size_hint() == 2
    print("OK   幸运币算手牌（少了它整排点击会右移一格）")


def test_tasklist_current_player_replay_keeps_action_window() -> None:
    """真机 2026-10-28 09:12:24：我方选项先到，30ms 后 CURRENT_PLAYER 被原样重放。

    旧代码拿 CURRENT_PLAYER 行当"回合起点"，重放一来 `turn_seq` 就涨过选项块，
    `my_action_window` 变假 → 整回合「等待中」被烧绳。回合起点只认带"只许前进"
    守卫的 GameEntity TURN 行。
    """
    pl = make_log(my_id=2)
    pl._player_names = {1: "对手#1", 2: "我#2"}
    feed(pl,
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=我#2 tag=CURRENT_PLAYER value=1",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=GameEntity tag=TURN value=18",
         "GameState.DebugPrintOptions() - id=77",
         "GameState.DebugPrintOptions() -   option 0 type=END_TURN mainEntity= "
         "error=NONE errorParam=",
         # PowerTaskList 把同一段原样再打一遍
         "PowerTaskList.DebugPrintPower() -     TAG_CHANGE Entity=我#2 "
         "tag=CURRENT_PLAYER value=1",
         "PowerTaskList.DebugPrintPower() -     TAG_CHANGE Entity=GameEntity tag=TURN value=18",
         "GameState.DebugPrintPower() - TAG_CHANGE Entity=对手#1 tag=CURRENT_PLAYER value=0")
    st = pl.state
    assert st.current_player == 2, st.current_player
    assert st.is_my_turn, st.current_player
    assert st.my_action_window, (st.turn_seq, st.end_turn_option_seq)
    print("OK   CURRENT_PLAYER/TURN 被 tasklist 重放不会关掉操作窗口")


def test_target_choice_header_has_empty_tasklist() -> None:
    """`ChoiceType=TARGET` 的头部是 `TaskList= ChoiceType=…`（TaskList 为空）。

    旧正则写死 `TaskList=\\d+`，整条 header 匹配不上 → choice_open 永远假 →
    引擎把"选目标"面板当不存在，整回合等待到烧绳（真机 10:25:18 克苏恩的凝视）。
    """
    pl = make_log(my_id=2)
    feed(pl,
         "GameState.DebugPrintEntityChoices() - id=12 Player=我#2 TaskList= "
         "ChoiceType=TARGET CountMin=1 CountMax=1",
         "GameState.DebugPrintEntityChoices() -   Source=[entityName=克苏恩仪式 id=43 "
         "zone=SECRET zonePos=0 cardId=BE_726 player=2]",
         "GameState.DebugPrintEntityChoices() -   Entities[0]=[entityName=钢铁魔像 id=196 "
         "zone=PLAY zonePos=3 cardId=BE_561t player=1]",
         "GameState.DebugPrintEntityChoices() -   Entities[1]=[entityName=古神主谋尤格-萨隆 "
         "id=13 zone=PLAY zonePos=2 cardId=BE_009 player=1]")
    st = pl.state
    assert st.choice_open, st.choice_open
    assert st.choice_type == "TARGET", st.choice_type
    assert [c["card_id"] for c in st.choices] == ["BE_561t", "BE_009"], st.choices
    assert st.choice_index_of("BE_009") == 1, st.choice_index_of("BE_009")
    print("OK   TARGET 面板（TaskList 为空）也能被识别，候选按日志顺序")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组 Power.log 读法用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

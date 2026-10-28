"""引擎决策逻辑的离线回归测试（不需要真机）。

每一条都对应一个真实踩过的 bug，用假状态 + 假日志行复现：

  - 选择面板：SendChoices 里选中的卡必须等于盒子要的那张（选错不能算成功）
  - 出牌：同一张牌连点两次，第二次不能靠上一次的 PLAY 块判成功
  - 结束回合：必须真的交出去（turn 变化或不再是我方）
  - 目标：张数要听盒子的场面序号，不能只信我们列表长度
  - 目标：同名多张时按盒子给的位置取

跑法：python -X utf8 tests/test_engine_rules.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

sys.path.insert(0, "src")

from hspy.decision.box import Plan  # noqa: E402
from hspy.engine import Engine  # noqa: E402


# ---------------- 假状态 ----------------
@dataclass
class Ent:
    card_id: str = ""
    eid: int = 0
    zone_pos: int = 0
    card_type: str = "MINION"


@dataclass
class FakeState:
    my_hand: list = field(default_factory=list)
    my_board: list = field(default_factory=list)
    rival_board: list = field(default_factory=list)
    choices: list = field(default_factory=list)
    choice_open: bool = False
    is_my_turn: bool = True
    turn: int = 1
    my_id: int = 1


def plan(**kw) -> Plan:
    return Plan.from_json(kw)


# ---------------- 1) 选择面板：选错不算成功 ----------------
def test_choice_panel_still_open_means_failed():
    """v0.1 的判据：面板还开着、候选也没换 → 判失败。

    注意：v0.1 **没有**「SendChoices 里选中的卡必须等于盒子要的那张」这条核对
    （那是后续提交加的，回退时丢了）。这里只钉住现有行为，不假装它有。
    """
    p = plan(action="unknown", card_id="BE_013t4", raw_action="choice")
    before = FakeState(choice_open=True, choices=[{"card_id": "A"}])
    after = FakeState(choice_open=True, choices=[{"card_id": "A"}])
    ok, why = Engine._verify_effect(p, before, ["D … SendChoices() - id=4"], after)
    assert (ok, why) == (False, "选择面板还开着"), (ok, why)
    print("OK   选择面板：面板还开着、候选没换 → 判失败")


def test_choice_panel_closed_without_sendchoices():
    p = plan(action="unknown", card_id="X", raw_action="choice")
    ok, why = Engine._verify_effect(p, FakeState(choice_open=True), [], FakeState(choice_open=False))
    assert (ok, why) == (True, "选择面板已关闭"), (ok, why)
    print("OK   选择面板：面板关了也算生效（不依赖 SendChoices）")


def test_choice_next_candidates_counts_as_effect():
    p = plan(action="unknown", card_id="X", raw_action="choice")
    before = FakeState(choice_open=True, choices=[{"card_id": "A"}, {"card_id": "B"}])
    after = FakeState(choice_open=True, choices=[{"card_id": "C"}, {"card_id": "D"}])
    ok, why = Engine._verify_effect(p, before, [], after)
    assert (ok, why) == (True, "候选已换下一组"), (ok, why)
    print("OK   选择面板：候选换下一组也算生效（连发发现面板）")


# ---------------- 2) 出牌：块必须点名这张牌 ----------------
def test_play_block_must_name_the_card():
    p = plan(action="play", card_id="BE_207")
    ok, why = Engine._verify_effect(
        p, FakeState(), ["D … PowerTaskList.DebugPrintPower() - BLOCK_START BlockType=PLAY … cardId=BE_207"],
        FakeState())
    assert (ok, why) == (True, "PLAY块"), (ok, why)

    ok2, why2 = Engine._verify_effect(
        p, FakeState(), ["D … BLOCK_START BlockType=PLAY … cardId=BE_094"], FakeState())
    assert ok2 is False, f"别的牌的 PLAY 块被算到这张头上：{why2}"
    print("OK   出牌：PLAY 块必须点名这张牌，别的牌不算")


def test_play_second_click_not_fooled_by_old_block():
    """test4 回合1：同一张 BE_207 连点两次，第二次其实没成。"""
    p = plan(action="play", card_id="BE_207")
    hand_before = [Ent("BE_207", eid=11)]
    hand_after = [Ent("BE_207", eid=11)]      # 没离手
    ok, why = Engine._verify_effect(p, FakeState(my_hand=hand_before), [], FakeState(my_hand=hand_after))
    assert (ok, why) == (False, "牌还在手上"), (ok, why)
    print("OK   出牌：牌还在手上 → 判失败（不会被上一条的块骗）")


def test_play_same_name_eid_decrease_means_success():
    p = plan(action="play", card_id="BE_207")
    before = FakeState(my_hand=[Ent("BE_207", eid=11), Ent("BE_207", eid=12)])
    after = FakeState(my_hand=[Ent("BE_207", eid=12)])
    ok, why = Engine._verify_effect(p, before, [], after)
    assert (ok, why) == (True, "牌已离手"), (ok, why)
    print("OK   出牌：同名多张时按 eid 数，少一张就算打出")


# ---------------- 3) 结束回合 ----------------
def test_end_turn_requires_turn_change():
    p = plan(action="end")
    ok, why = Engine._verify_effect(p, FakeState(turn=5), [], FakeState(turn=5, is_my_turn=False))
    assert (ok, why) == (True, "回合已交出"), (ok, why)
    ok2, why2 = Engine._verify_effect(p, FakeState(turn=5), [], FakeState(turn=5, is_my_turn=True))
    assert (ok2, why2) == (False, "回合仍在我手上"), (ok2, why2)
    print("OK   结束回合：交出才算成功，还在手上判失败")


# ---------------- 4) 目标换算：张数听盒子的场面序号 ----------------
def test_target_size_follows_box_position():
    """test10 回合3：敌方真实 2 个，我们只解析到 1 个；盒子 position=2。"""
    p = plan(action="attack", card_id="CATA_210", target="enemy_board",
             target_position=2, target_card_id="Loot")
    st = FakeState(rival_board=[Ent("Loot", zone_pos=2)], my_board=[Ent("CATA_210", zone_pos=1)])
    tgt = Engine._target(p, st)
    assert tgt is not None
    idx, size = tgt.index, tgt.size
    assert (idx, size) == (1, 2), (idx, size)
    print(f"OK   目标：盒子场面位=2 → 下标 {idx}、张数 {size}（没被我们列表长度 1 带偏）")


def test_target_same_name_uses_box_slot():
    p = plan(action="play", card_id="CATA_210", target="my_board",
             target_position=2, target_card_id="BE_085t")
    st = FakeState(my_board=[Ent("BE_085t", zone_pos=1), Ent("BE_085t", zone_pos=2)],
                   my_hand=[Ent("CATA_210", zone_pos=1)])
    tgt = Engine._target(p, st)
    assert (tgt.index, tgt.size) == (1, 2), (tgt.index, tgt.size)
    print("OK   目标：同名两张时按盒子给的位置取第 2 个")


def test_target_hero_kinds():
    assert Engine._target(plan(action="attack", target="rival_hero"), FakeState()).kind == "rival_hero"
    assert Engine._target(plan(action="play", target="my_hero"), FakeState()).kind == "hero"
    print("OK   目标：rival_hero / my_hero 映射正确")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组引擎决策用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

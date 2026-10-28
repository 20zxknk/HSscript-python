"""B-06 的回归用例：盒子的 hand_position 与卡号冲突时，按游戏选项映射选槽。

真机证据（test/015-112438，11:32:36）：
  盒子说 play BE_207 在 hand_position=3；
  游戏的选项快照里槽 3 是 TIME_025（id=59, REQ_ENOUGH_MANA），
  BE_207（id=43）在 zonePos=4。
旧代码无条件信盒子的位置 -> 点槽 3 -> 游戏说这张牌打不出（REQ_ENOUGH_MANA）
-> 判失败 -> 重试 16 次，一次都没打出去。

修法：用「槽位 -> eid -> 实体卡号」核对；
  盒子的槽位与卡号一致 -> 用盒子的槽位；
  不一致但快照里另一槽正好是这张牌 -> 用那一槽（并记录 slot_from_card）；
  两边都对不上 -> 保留盒子槽位（快照可能更旧），照旧报 [!]。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

sys.path.insert(0, "src")

from hspy.decision.box import Plan  # noqa: E402
from hspy.engine import Engine  # noqa: E402


@dataclass
class Ent:
    card_id: str = ""
    eid: int = 0
    zone_pos: int = 0
    card_type: str = "MINION"
    zone: str = "HAND"


@dataclass
class FakeState:
    my_hand: list = field(default_factory=list)
    my_board: list = field(default_factory=list)
    rival_board: list = field(default_factory=list)
    choices: list = field(default_factory=list)
    choice_open: bool = False
    is_my_turn: bool = True
    turn: int = 1
    my_id: int = 2
    entities: dict = field(default_factory=dict)
    hand_option_eids: dict = field(default_factory=dict)
    option_errors: dict = field(default_factory=dict)

    def hand_size_hint(self) -> int:
        return len(self.my_hand)

    def my_hand_slots(self) -> dict:
        return {e.zone_pos: e.card_id for e in self.my_hand}


def build_state() -> FakeState:
    """槽 1..5：CATA_210 / TIME_026 / TIME_025 / BE_207 / CAP_405tb1（与真机一致）。"""
    ents = {
        "CATA_210": (100, 1), "TIME_026": (101, 2), "TIME_025": (59, 3),
        "BE_207": (43, 4), "CAP_405tb1": (139, 5),
    }
    st = FakeState(my_id=2)
    for cid, (eid, zp) in ents.items():
        e = Ent(card_id=cid, eid=eid, zone_pos=zp)
        st.entities[eid] = e
        st.my_hand.append(e)
        st.hand_option_eids.setdefault(2, {})[zp] = eid
    # 游戏说：槽 3 的 TIME_025 打不出（就是真机里那条 REQ_ENOUGH_MANA）
    st.option_errors[59] = "REQ_ENOUGH_MANA"
    return st


def resolve(st: FakeState, plan: Plan) -> int:
    """直接调 engine 里的真实现（不再复制一份逻辑，否则回归会漂移）。"""
    pos, _basis = Engine.resolve_play_slot(st, plan.hand_position or 0, plan.card_id or "")
    return pos


def test_conflict_uses_card_slot():
    st = build_state()
    plan = Plan.from_json({"action": "play", "card_id": "BE_207", "hand_position": 3})
    pos = resolve(st, plan)
    assert pos == 3, f"应当用槽 4（BE_207 的真实位置），实际 {pos + 1}"
    print("OK   盒子位置 3 与卡号冲突 -> 改用槽 4（BE_207 的真实位置）")


def test_consistent_position_kept():
    st = build_state()
    plan = Plan.from_json({"action": "play", "card_id": "BE_207", "hand_position": 4})
    pos = resolve(st, plan)
    assert pos == 3, pos
    print("OK   盒子位置与卡号一致 -> 照用槽 4")


def test_unknown_card_keeps_box_slot():
    st = build_state()
    plan = Plan.from_json({"action": "play", "card_id": "ZZZ_999", "hand_position": 2})
    pos = resolve(st, plan)
    assert pos == 1, pos
    print("OK   卡号在快照里找不到 -> 仍信盒子的槽位（快照可能更旧）")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组槽位裁决用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

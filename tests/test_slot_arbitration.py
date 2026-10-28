"""槽位裁决：改槽必须两个来源都点头（选项映射 + 手牌列表）。

真机实证（2026-10-27 20:0x，test/r4）：
  盒子说 TIME_026 在槽 2；选项映射说槽 2 是 BE_726；我们的手牌列表说槽 2 就是 TIME_026。
  旧规则只看选项映射 -> 改到槽 3 -> hand_slot 断言失败（槽 3 实际是 BE_726）-> 死循环。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hspy.decision.box import Plan  # noqa: E402
from hspy.engine import Engine  # noqa: E402


class Ent:
    def __init__(self, card_id: str, eid: int, zone_pos: int) -> None:
        self.card_id = card_id
        self.eid = eid
        self.zone_pos = zone_pos
        self.zone = "HAND"


class FakeState:
    """按官方快照造一份状态：list 是界面顺序，option_eids 是游戏选项映射。"""

    def __init__(self, hand: list[str], option_map: dict[int, str]) -> None:
        self.my_id = 1
        self.my_hand = []
        self.entities = {}
        self.hand_option_eids = {1: {}}
        for i, cid in enumerate(hand, start=1):
            eid = 100 + i
            e = Ent(cid, eid, i)
            self.my_hand.append(e)
            self.entities[eid] = e
            # 选项映射本来该等于界面顺序；要模拟“映射旧一拍”就单独覆盖
            self.hand_option_eids[1][i] = eid
        self._override = option_map

    def refresh(self) -> None:
        pass

    def hand_size_hint(self) -> int:
        return len(self.my_hand)

    def my_hand_slots(self) -> dict:
        return {e.zone_pos: e.card_id for e in self.my_hand}

    def slot_card(self, slot: int) -> str:
        return self._override.get(slot) or ""


def make_state_stale_map() -> FakeState:
    """手牌 [BE_086, TIME_026, BE_726]，但选项映射把槽 2 说成 BE_726。"""
    st = FakeState(["BE_086", "TIME_026", "BE_726"], {2: "BE_726", 3: "TIME_026"})
    original = st.hand_option_eids

    def fake_get(pid, default=None):
        # resolve_play_slot 里是 st.hand_option_eids.get(my_id).get(slot) -> eid -> card
        return original.get(pid, default)

    st.hand_option_eids = original
    # 直接把映射改坏：槽 2 的 eid 指向 BE_726 那个实体
    st.hand_option_eids[1][2] = 103
    return st


def plan(card: str, pos: int) -> Plan:
    return Plan.from_json({"action": "play", "card_id": card, "hand_position": pos})


def test_stale_option_map_keeps_box_slot() -> None:
    st = make_state_stale_map()
    pos, basis = Engine.resolve_play_slot(st, 2, "TIME_026")
    assert (pos, basis) == (1, "box"), (pos, basis)
    print("OK   选项映射旧一拍时不改槽（用盒子的槽 2）")


def test_both_sources_agree_switches() -> None:
    """两个来源都说 TIME_026 在槽 3 时，才允许改槽。"""
    st = FakeState(["BE_086", "BE_726", "TIME_026"], {})
    pos, basis = Engine.resolve_play_slot(st, 2, "TIME_026")
    assert (pos, basis) == (2, "card"), (pos, basis)
    print("OK   映射与列表都指向槽 3 时才改槽")


def test_no_option_map_trusts_box() -> None:
    st = FakeState(["BE_086", "TIME_026", "BE_726"], {})
    st.hand_option_eids = {1: {}}
    pos, basis = Engine.resolve_play_slot(st, 2, "TIME_026")
    assert (pos, basis) == (1, "box"), (pos, basis)
    print("OK   没有选项映射时不动盒子槽位")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组槽位裁决用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""干跑引擎：把真实的盒子推荐（recs_*.jsonl 里的 data）喂给 Engine._execute。

只验证「推荐 -> 动作 -> 点击坐标」这条链，不动真实鼠标、不连桥。

    python -u scripts/dry_engine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hspy.decision.box import Plan  # noqa: E402
from hspy.engine import Engine, EngineConfig  # noqa: E402
from hspy.input.state import Entity, GameState, Player  # noqa: E402
from hspy.output.actions import Actions  # noqa: E402
from hspy.output.mouse import Mouse  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dry_actions import FakeWindow  # noqa: E402


def make_state(hand=("CATA_210", "TLC_451", "DINO_COIN2"), board=("CS2_182",)):
    st = GameState(started=True, turn=3, my_id=1, current_player=1)
    me = Player(pid=1)
    rival = Player(pid=2)
    st.players = {1: me, 2: rival}
    eid = 100
    for i, cid in enumerate(hand):
        eid += 1
        e = Entity(eid=eid, card_id=cid, card_type="MINION", controller=1,
                   zone="HAND", zone_pos=i + 1, cost=3)
        st.entities[eid] = e
    for i, cid in enumerate(board):
        eid += 1
        e = Entity(eid=eid, card_id=cid, card_type="MINION", controller=1,
                   zone="PLAY", zone_pos=i + 1, atk=2, health=2)
        st.entities[eid] = e
    for i, cid in enumerate(("CS2_200", "CS2_201")):
        eid += 1
        e = Entity(eid=eid, card_id=cid, card_type="MINION", controller=2,
                   zone="PLAY", zone_pos=i + 1, atk=1, health=3)
        st.entities[eid] = e
    st.entities[1] = Entity(eid=1, card_id="HERO_01", card_type="HERO", controller=1, zone="PLAY")
    st.entities[2] = Entity(eid=2, card_id="HERO_02", card_type="HERO", controller=2, zone="PLAY")
    st.refresh()
    return st


CASES = [
    # (说明, 原始 data 元素, turnNum)
    ("随从上场（有小兵在场）", {"card": {"cardName": "暮光雏龙", "cardId": "CATA_210", "ZONE_POSITION": 1},
                              "actionName": "play_minion", "position": 2}, 2),
    ("法术无位置", {"card": {"cardName": "诅咒之墓", "cardId": "TLC_451", "ZONE_POSITION": 2},
                    "actionName": "play_special"}, 4),
    ("随从攻击敌方英雄", {"card": {"cardId": "CS2_182", "ZONE_POSITION": 1},
                          "actionName": "minion_attack",
                          "opp-target-hero": {"cardId": "HERO_02"}}, 5),
    ("随从攻击敌方随从", {"card": {"cardId": "CS2_182", "ZONE_POSITION": 1},
                          "actionName": "minion_attack",
                          "opp-target": {"cardId": "CS2_201", "ZONE_POSITION": 2}}, 6),
    ("指向法术打敌随从", {"card": {"cardId": "TLC_451", "ZONE_POSITION": 2},
                          "actionName": "play_spell",
                          "target": {"cardId": "CS2_200", "ZONE_POSITION": 1}}, 7),
    # 盒子只给 target（不带 opp-/my- 前缀）：目标是我方随从时绝不能打到对面
    ("buff 指向我方随从", {"card": {"cardId": "TLC_451", "ZONE_POSITION": 2},
                           "actionName": "play_spell",
                           "target": {"cardId": "CS2_182", "ZONE_POSITION": 1}}, 10),
    ("英雄技能", {"card": {"cardId": "HERO_01bp"}, "actionName": "hero_skill"}, 8),
    ("结束回合", {"actionName": "end_turn"}, 9),
]


def main() -> int:
    sys.path.insert(0, r"D:\desk\hearthstone\script-main")
    from recommendation_server import map_plans  # 复用桥自己的映射，别重写

    win = FakeWindow(1920, 1080)
    eng = Engine(EngineConfig(dry_run=True))
    eng.window = win
    eng.actions = Actions(win, Mouse(dry_run=True, humanize=True))
    st = make_state()

    for label, data, turn in CASES:
        rec = {"status": 2, "turnNum": turn, "optionId": turn * 3, "choiceId": -1, "data": [data]}
        plans = [Plan.from_json(p) for p in map_plans(rec)]
        print(f"\n=== {label} ===  action={plans[0].action} target={plans[0].target}:{plans[0].target_position}"
              f" hand={plans[0].hand_position} board={plans[0].board_position} card={plans[0].card_id}")
        eng._execute(plans[0], st)

    print("\n=== 全部执行完毕（dry_run，未动真实鼠标）===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

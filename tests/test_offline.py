"""离线自检（不碰游戏、不点鼠标）：输入层解析、结果核对、坐标数学。

    python tests/test_offline.py                       # 用最新的 Power.log
    python tests/test_offline.py <Power.log>           # 指定一份日志

覆盖三件最容易悄悄坏掉的事：
    1. Power.log -> GameState 还能不能正确还原（回合/我方玩家/手牌/场面）；
    2. mark()/since_mark() 能不能只拿到"这一步新增的日志"；
    3. 结果核对 _verify_effect 能不能把"真打出去"和"日志只是被对手推动"分开。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hspy.input.powerlog import PowerLog  # noqa: E402
from hspy.input.state import Entity, GameState, Player  # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'OK  ' if cond else 'FAIL'} {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def newest_power_log() -> Path | None:
    """测试要一份**历史**日志来重放，所以自己扫全部会话。

    运行时的 latest_log() 只认「本次会话」（见 BUG 10），语义不同。
    """
    hs = PowerLog().hs_dir
    logs = hs / "Logs"
    if not logs.is_dir():
        return None
    best = None
    for d in logs.iterdir():
        f = d / "Power.log"
        if f.is_file():
            m = f.stat().st_mtime
            if best is None or m > best[0]:
                best = (m, f)
    return best[1] if best else None


def check_parse(path: Path) -> GameState:
    log = PowerLog()
    log.pin_log(path)
    st = log.rebuild()
    check("解析: 开局标记", st.started, f"started={st.started}")
    check("解析: 认出了我方玩家", st.my_id in (1, 2), f"my_id={st.my_id}")
    check("解析: 回合数 > 0", st.turn > 0, f"turn={st.turn}")
    check("解析: 有实体", len(st.entities) > 20, f"entities={len(st.entities)}")
    check("解析: 段号已推进", log.seg_index >= 1, f"seg_index={log.seg_index}")
    names = [e.card_id for e in st.my_hand]
    check("解析: 能读出牌名（手牌或场面有卡号）",
          bool(names) or bool(st.my_board) or st.finished,
          f"hand={names[:6]} board={[e.card_id for e in st.my_board][:6]}")
    return st


def check_mark(path: Path) -> None:
    """mark() 之后只能拿到新行。"""
    log = PowerLog()
    log.pin_log(path)
    log.rebuild()
    before = len(log._action_buf)
    log.mark()
    check("mark: 清空缓冲", len(log.since_mark()) == 0, f"以前 {before} 行")
    # 手工喂两行，模拟点击之后游戏打印的日志
    log._feed("D 00:00:00.0000000 PowerTaskList.DebugPrintPower() - BlockType=PLAY\n")
    log._feed("D 00:00:00.0000001 PowerTaskList.DebugPrintPower() -     tag=X value=1\n")
    got = log.since_mark()
    check("mark: 只收新行", len(got) == 2, f"n={len(got)}")
    check("mark: 内容对得上", "BlockType=PLAY" in got[0])


def check_board_sync(path: Path) -> None:
    """中途必须能在场面上看到随从（回归：曾经因为随从 card_type 为空而永远空的）。

    真机实证（2026-10-25）：随从的类型只在 `FULL_ENTITY - Creating ... cardType=MINION`
    里出现，打出时只有 `tag=ZONE value=PLAY`；旧代码要求 card_type==MINION 才进
    场面列表 ⇒ 场面永远为空 ⇒ 盒子让我们攻击时我们场上没人。
    """
    from hspy.input.powerlog import PowerLog

    pl = PowerLog()
    pl._path = path            # 不走 latest_log，直接喂行
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    seen = False
    step = max(1, len(lines) // 400)
    for i, line in enumerate(lines):
        pl.seq += 1
        pl._feed(line)
        if i % step == 0:
            pl.state.refresh()
            if pl.state.my_board or pl.state.rival_board:
                seen = True
                break
    check("解析: 中途能看到场面随从（board 不为空）", seen,
          f"喂了 {i} 行, 我方场面={[e.card_id for e in pl.state.my_board]}")


def _state(hand=("A_1", "B_2"), board=("C_3",), turn=3, me=1, cur=1) -> GameState:
    st = GameState(started=True, turn=turn, my_id=me, current_player=cur)
    st.players = {1: Player(pid=1), 2: Player(pid=2)}
    eid = 100
    for i, cid in enumerate(hand):
        eid += 1
        st.entities[eid] = Entity(eid=eid, card_id=cid, card_type="MINION", controller=1,
                                  zone="HAND", zone_pos=i + 1, cost=1)
    for i, cid in enumerate(board):
        eid += 1
        st.entities[eid] = Entity(eid=eid, card_id=cid, card_type="MINION", controller=1,
                                  zone="PLAY", zone_pos=i + 1, atk=2, health=2)
    st.refresh()
    return st


def test_verify() -> None:
    from hspy.decision.box import Plan
    from hspy.engine import Engine

    st = _state()
    play = Plan(action="play", card_id="A_1", hand_position=1)
    ok, why = Engine._verify_effect(
        play, st, ["x BLOCK_START BlockType=PLAY Entity=[cardId=A_1 player=1] y\n"], st)
    check("核对: PLAY 块算成功", ok and why == "PLAY块", why)

    # 关键回归 1：块是**别的牌**的（test4 回合1 的重复认领）
    ok, why = Engine._verify_effect(
        play, st, ["BLOCK_START BlockType=PLAY Entity=[cardId=B_2 player=1]\n"], st)
    check("核对: 别的牌的 PLAY 块 -> 不算成功", not ok, why)

    # 关键回归：日志**前进了**却没有 PLAY 块（对手在动）——绝不能算成功
    ok, why = Engine._verify_effect(play, st, ["x TAG_CHANGE y\n"], st)
    check("核对: 只有无关日志 -> 未生效", not ok, why)

    # 牌离手（同名多张按 eid 数）
    after = _state(hand=("B_2",))
    ok, why = Engine._verify_effect(play, st, [], after)
    check("核对: 牌离手也算成功", ok and why == "牌已离手", why)

    atk = Plan(action="attack", card_id="C_3", board_position=1, target="enemy_hero")
    ok, _ = Engine._verify_effect(
        atk, st, ["BLOCK_START BlockType=ATTACK Entity=[cardId=C_3 player=1]\n"], st)
    check("核对: ATTACK 块", ok)
    ok, _ = Engine._verify_effect(
        atk, st, ["BLOCK_START BlockType=ATTACK Entity=[cardId=Z_9 player=1]\n"], st)
    check("核对: 别的随从的 ATTACK 块 -> 不算成功", not ok)

    end = Plan(action="end")
    ok, why = Engine._verify_effect(end, st, [], _state(turn=4, cur=2))
    check("核对: 回合已交出", ok and why == "回合已交出", why)
    ok, why = Engine._verify_effect(end, st, [], st)
    check("核对: 回合还在我手上 -> 未生效", not ok, why)

    # 防御性判断已全部拆除，engine 里不应再存在这些"替游戏做主"的入口
    for gone in ("_plan_stale", "ensure_geometry"):
        check(f"已拆: Engine.{gone} 不存在", not hasattr(Engine, gone))


def test_query_before_action() -> None:
    """动作前必须先查一次：每次调用都要真的向桥要，且换牌计划按场合过滤。"""
    from hspy.decision.box import Plan
    from hspy.engine import Engine, EngineConfig

    class FakeBridge:
        def __init__(self) -> None:
            self.calls = 0
            self.last_rec = {"optionId": 7, "turnNum": 3}
            self._last_raw = "{}"
            self.plans = [
                Plan(action="mulligan", mulligan_positions=[1]),
                Plan(action="play", card_id="X_1", hand_position=2),
            ]

        def scan(self):
            self.calls += 1
            return list(self.plans)

    eng = Engine(EngineConfig())
    eng.bridge = FakeBridge()

    batch = eng._query_before_action("单测")
    check("动作前查询: 剔掉换牌计划", len(batch) == 1 and batch[0].card_id == "X_1",
          str([p.action for p in batch]))
    batch2 = eng._query_before_action("单测-换牌", keep_mulligan=True)
    check("动作前查询: 换牌时保留换牌计划", len(batch2) == 2,
          str([p.action for p in batch2]))
    check("动作前查询: 每次调用都真的问了一次", eng.bridge.calls == 2,
          f"calls={eng.bridge.calls}")
    # Plan 的 target 默认必须是"无目标"：默认 "board" 会被 _target 当成敌方场面
    check("方案: 没写 target 就是无目标", Plan(action="play").target == "",
          f"target={Plan(action='play').target!r}")
    check("方案: 无目标解析成 None",
          Engine._target(Plan(action="play", card_id="X_1"), _state()) is None)


def test_coords() -> None:
    from hspy import coords
    from hspy.geometry import CONTENT_RATIO

    r = coords.hand_card(0, 4)
    x, y, w, h = r.relative(1306, 967)
    check("坐标: 4 张手牌落在自己身上", 0 < x < 1306 and 0 < y < 967, f"({x},{y})")
    check("坐标: 1.351 内容比", abs(CONTENT_RATIO - 1.351) < 1e-9, f"{CONTENT_RATIO}")
    # 1.351 比例下 usableW == realW，这是整套表自洽的前提
    check("坐标: 1306x967 时 usableW==realW",
          int(967 * CONTENT_RATIO) == 1306, f"{int(967 * CONTENT_RATIO)}")


def fixture_log() -> Path | None:
    """仓库里带的脱敏样例：没有真机日志时用它，保证离线可跑。"""
    f = Path(__file__).resolve().parent / "fixtures" / "powerlog-sample.log"
    return f if f.exists() else None


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    # 夹具优先：真机日志每次内容都不一样，断言会随机红（BUG 18 的连带问题）
    path = Path(arg) if arg else (fixture_log() or newest_power_log())
    if path is None or not path.exists():
        print("找不到 Power.log，也没有夹具 tests/fixtures/powerlog-sample.log")
        return 1
    print(f"用这份日志: {path}\n")
    check_parse(path)
    check_mark(path)
    check_board_sync(path)
    test_verify()
    test_query_before_action()
    test_coords()
    print()
    if FAILED:
        print(f"FAILED: {FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

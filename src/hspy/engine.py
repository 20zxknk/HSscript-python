"""引擎：轮询盒子推荐并执行，日志只负责同步回合/结束。

设计（按使用者的要求，也是作者真机的做法）：
1. **一直轮询盒子**（~0.5s 一次），拿到推荐就执行，**不自己判断该不该打**；
2. **不做手牌/cardId 校验**——盒子看到的就是局面，位置由它给；
3. 日志只回答两个问题：现在是不是我的回合、对局结束没有；
4. 执行完立刻再问盒子（它会重估），靠轮询自愈，不加闸门。

    while 对局未结束:
        if 不是我的回合: 等日志变化
        plans = 盒子.scan()
        if plans: 执行 plans[0]      # 单方案
        else: 短暂等待后继续问
"""
from __future__ import annotations

import pathlib
import random
import time
from dataclasses import dataclass

from . import win
from .actlog import ActionLog
from .decision.box import BoxBridge, BridgeError, Plan
from .geometry import GameWindow
from .humanize import Humanizer
from .input.state import GameState, board_rank
from .output.actions import Actions, Target
from .output.mouse import make_mouse
from .sync import Sync
from .verify import AssertFailed, Stepper


@dataclass
class EngineConfig:
    dry_run: bool = False
    bridge_script: str = ""
    bridge_cwd: str = ""
    bridge_timeout: float = 25.0
    poll: float = 0.5
    scan_interval: float = 0.5      # 两次问盒子之间的间隔（0.5s 一次轮询）
    probe_dir: str = ""              # 非空则每次点击前截图标出落点（排查用）
    # 拟人思考缩放（快攻 0.2~0.4）：快攻卡组长考反而像脚本，还容易烧绳。
    think_scale: float = 1.0


class Engine:
    def __init__(self, cfg: EngineConfig, sync: Sync | None = None,
                 act_log: "ActionLog | None" = None, recorder=None):
        self.cfg = cfg
        self.sync = sync or Sync(poll=cfg.poll)
        # 录制器（可选）：把每次向盒子要到的推荐原文按毫秒时间戳落盘
        self.recorder = recorder
        self.window = GameWindow()
        self.actions: Actions | None = None
        self.bridge = BoxBridge(
            cfg.bridge_script, cwd=cfg.bridge_cwd or None, timeout=cfg.bridge_timeout
        )
        self.stats = {"turns": 0, "plans": 0, "acts": 0, "empty": 0, "errors": 0,
                 "swallowed": 0, "stale": 0}
        # 本回合开始的墙钟时间（按 turn_seq 认）：拟人思考必须服从回合计时，
        # 否则"走神/离座"（人类模型里 8s、30s 的状态）会把一回合直接烧掉。
        self._turn_started = time.time()
        self._turn_key = -1
        # 动作日志：每步一条 JSONL，能和 Power.log 的 seq/version 逐条对账
        self.act_log = act_log
        self.stepper = Stepper(act_log.path if act_log is not None else None)

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        self.window.find()
        self.window.update()
        # 窗口比例**只报不改**：以前这里会自动把窗口调成 1.351，属于"替使用者
        # 做决定"的保护性代码（还会把用户摆好的窗口挪走）。比例不合规时坐标会偏，
        # 但那是"点击没生效"，由核对如实记成 swallowed —— 不掩盖、不擅自改环境。
        w, h = self.window.size
        if not win.content_ratio_ok(self.window.hwnd):
            print(f"[engine] [!] 窗口 {w}x{h}（比例 {w / max(h, 1):.3f}）窄于 1.351，"
                  f"手牌/场面坐标可能偏（不改窗口，请自行调整）", flush=True)
        self.human = Humanizer()
        self._last_think = time.time()   # 用于给状态机推进 dt（不传 dt 时它永远不切状态）
        self.actions = Actions(
            self.window,
            make_mouse(dry_run=self.cfg.dry_run,
                          prefer_clone=(getattr(self.cfg, "mouse_backend", "bezier") == "clone")),
            probe_dir=self.cfg.probe_dir or None,
        )
        self.bridge.start()
        print("[engine] 已就绪（窗口 + 桥 + 同步层）")

    def close(self) -> None:
        self.bridge.close()

    # ---------------- 换牌 ----------------
    def do_mulligan(self, hand_size: int = 0, wait: float = 30.0) -> None:
        """换牌：先拿盒子的换牌建议（开局就发），等 20 秒动画，再点牌+确认。"""
        assert self.actions is not None

        # 1) 先确认盒子有没有换牌建议（有就记下，真正的用不用要等动画结束后重查）
        plan = None
        deadline = time.time() + wait
        while time.time() < deadline and plan is None:
            batch = self._query_before_action("换牌前探测", keep_mulligan=True)
            for p in batch:
                a = (p.action or "").lower()
                if a in ("replace", "mulligan") or p.mulligan_positions:
                    plan = p
                    break
            if plan is None:
                time.sleep(0.5)

        # 2) 再等开局动画（作者 DeckStrategyActuator.changeCard 的 20000ms）
        print("[engine] 等开局动画 20s", flush=True)
        time.sleep(20.0)

        # 3) 点要换的牌 + 作者式确认（3 次确认 + 1 次中心）
        # 换牌面板的槽位由"起手张数"决定，起手张数要等日志建出实体；
        # 一上来就取会拿到上一局的残值（真机踩过：按 1 张的布局点 4 张的牌）。
        #
        # **读不到就一直等，不猜**：以前这里 12 秒读不到就 `hand_size = 4`
        # 硬点 —— 那等于用猜测替代证据，4 槽/3 槽布局点错会直接白丢牌。
        # 现在等到 wait 结束仍在等：只打日志、不点牌、不确认（把面板留在那儿，
        # 让主循环/下一次调用按真实数据再来）。
        deadline = time.time() + wait
        beat = 0.0
        rebuilt = False
        last_dump = 0.0
        while not hand_size:
            st = self.sync.pump().game
            # 手牌张数从日志实体同步：换牌阶段对手的手牌没有卡号，
            # 有卡号的 HAND 实体的最大槽号就是我的起手张数。
            known = [
                e.zone_pos
                for e in st.entities.values()
                if e.zone == "HAND" and e.card_id and e.zone_pos >= 1
            ]
            n = max([st.hand_size_hint(), len(st.my_hand), max(known or [0])])
            if n >= 3:
                hand_size = min(n, 4)   # 换牌面板最多 4 槽（后手 4 张）
                print(f"[engine] 起手 {hand_size} 张（换牌面板 {hand_size} 槽布局）", flush=True)
                break
            # 读不到就**从日志头重建一次**（日志里数据是全的；实时追尾可能错过了
            # CREATE_GAME/实体批次）。真机实证（test8）：实时读到 hand=0、turn=0，
            # 同一份留档从头回放却有 85 个实体、3 张手牌 —— 所以不是日志缺数据。
            if n == 0 and not rebuilt and time.time() < deadline - 2:
                rebuilt = True
                print("[engine] 起手张数读不到 -> 从日志头重建状态再读", flush=True)
                try:
                    self.sync.power.rebuild()
                except Exception as e:      # 重建失败要看得见，不能静默
                    print(f"[engine] 重建失败: {e}", flush=True)
                continue
            if time.time() >= deadline:
                print(f"[engine] 起手张数仍读不到（实体 zone=HAND 且有卡号的 {n} 个），"
                      f"这一轮不换牌、不点确认", flush=True)
                return
            if time.time() - beat > 2.0:
                beat = time.time()
                # 抓现场用：把判断起手张数依赖的每一项都打出来，
                # 否则只能看到 "n=0"（BUG 13 就是这么卡住的）
                pw = self.sync.power
                try:
                    fh_pos = pw._fh.tell() if pw._fh else -1
                except Exception:
                    fh_pos = -2
                hand_eids = [(e.eid, e.card_id, e.zone_pos)
                             for e in st.entities.values()
                             if e.zone == "HAND" and e.card_id]
                print(f"[engine] 等起手张数… n={n} hand={len(st.my_hand)} "
                      f"hint={st.hand_size_hint()} | seq={pw.seq} seg={pw.seg_index} "
                      f"实体={len(st.entities)} 带卡号HAND={len(hand_eids)} "
                      f"my_id={st.my_id} fh={fh_pos} known={sorted(known)[-4:]}",
                      flush=True)
                if hand_eids and time.time() - last_dump > 6.0:
                    last_dump = time.time()
                    print(f"[engine]   带卡号的 HAND 实体样例: {hand_eids[:6]}", flush=True)
            time.sleep(0.3)
        # 4) **点之前再查一次**：动画期间盒子可能已经改主意，绝不能拿 20 秒前的
        #    方案去点牌。这一批里没有换牌建议，就"全部保留"（不去点任何牌）。
        fresh = self._query_before_action("换牌前", keep_mulligan=True)
        plan = None
        for p in fresh:
            a = (p.action or "").lower()
            if a in ("replace", "mulligan") or p.mulligan_positions:
                plan = p
                break
        if plan is not None:
            pos = plan.mulligan_positions or []
            print(f"[engine] 按盒子换牌: 替换 {pos}（起手 {hand_size} 张）", flush=True)
            self.actions.mulligan(pos, hand_size)
        else:
            print("[engine] 换牌前这次没给换牌建议 -> 全部保留", flush=True)
        # 换牌只点一次确认：不做重试（点了没变就让主循环去问盒子要新方案）
        self.actions.confirm_mulligan()

    # ---------------- 动作前强制查询 ----------------
    def _query_before_action(self, why: str, keep_mulligan: bool = False,
                             st: GameState | None = None) -> list[Plan]:
        """**每一个动作执行前都必须走这里**：现向盒子要一次推荐。

        返回这一批方案（已剔除换牌缓存）；空列表表示"这次没得做"。
        之所以收敛成一个入口：以前换牌是"拿到方案 → 睡 20 秒动画 → 用 20 秒前的
        方案去点"，主循环也有"先查、再断言、再点"的窗口。现在规定：**点击这一下
        之前必须刚查过**，日志里会打 `动作前重查(...) optionId=...`，可事后核对。
        """
        t0 = time.time()
        try:
            plans = self.bridge.scan()
        except BridgeError as e:
            self.stats["errors"] += 1
            print(f"[engine] 桥接失败（{why}）: {e}", flush=True)
            return []
        if self.recorder is not None:
            # 原文照录：plans（解析后）+ raw_rec（盒子给的原始结构）+ 桥那一行 JSON
            self.recorder.rec(plans, getattr(self.bridge, "_last_raw", ""),
                              getattr(self.bridge, "last_rec", None))
        # 换牌计划在桥里是「不过期」的缓存，打牌阶段必须剔掉，否则会反复确认起手
        if not keep_mulligan:
            plans = [p for p in plans
                     if (p.action or "").lower() not in ("mulligan", "replace")]
        rec = getattr(self.bridge, "last_rec", None) or {}
        p0 = plans[0] if plans else None
        # **过期判定**：盒子给的 turnNum 要和我方回合数（Power.log：
        # GameEntity.TURN 的半回合数 -> (v+1)//2）比。盒子比我们旧 -> 这条是上一回合
        # 产生的结论，绝不能用在当前回合。
        # 真机实证（test4）：02:47:01 时 GameEntity.TURN=3 -> 我方第 2 回合，
        # 盒子给的却是 turnNum=1 的 end_turn（它 02:46:53 就产出了），
        # 我们照点就是"用回合 1 的结论结束回合 2"。
        if not keep_mulligan and st is not None and p0 is not None:
            tn = rec.get("turnNum")
            if isinstance(tn, (int, float)) and st.turn and tn < st.turn:
                self.stats["stale"] = self.stats.get("stale", 0) + 1
                print(f"[engine] 推荐已过期：盒子 turnNum={tn} < 我方回合={st.turn}"
                      f"（GameEntity.TURN={st.turn_global}）→ 不执行，继续要新推荐",
                      flush=True)
                self.stepper.step("stale_rec", box_turn=tn, my_turn=st.turn,
                                  game_turn=st.turn_global,
                                  option_id=rec.get("optionId"),
                                  action=p0.action, card=p0.card_id)
                return []
        print(f"[engine] 动作前重查({why}) "
              f"耗时{(time.time() - t0) * 1000:.0f}ms "
              f"optionId={rec.get('optionId')} turnNum={rec.get('turnNum')} n={len(plans)}"
              + (f" → {p0.action} {p0.card_id or ''} "
                 f"手{p0.hand_position} 场{p0.board_position} "
                 f"目标={p0.target}:{p0.target_position}/{p0.target_card_id}" if p0 else " → 无方案"),
              flush=True)
        if not plans:
            self.stats["empty"] += 1
        return plans

    # ---------------- 主循环 ----------------
    def play_match(self, timeout: float = 900.0) -> str:
        assert self.actions is not None
        deadline = time.time() + timeout
        last_turn = -1
        last_seq = self.sync.power.seq
        last_ver = 0
        last_progress = time.time()
        last_stall_log = 0.0

        while time.time() < deadline:
            snap = self.sync.pump()
            st = snap.game

            # 局面不动**不中止**：只每 30 秒打一行，然后继续轮询。
            # （原来 45 秒不动就断言失败 -> 整轮中止并投降。真机实证：对手长考、
            #  或日志恰好没新行时，这一下就把还能打的对局判死了 —— 典型"保护比故障更贵"。）
            if self.sync.power.seq != last_seq or snap.version != last_ver:
                last_seq = self.sync.power.seq
                last_ver = snap.version
                last_progress = time.time()
            elif (st.started and not st.finished
                  and time.time() - last_progress > 30
                  and time.time() - last_stall_log > 30):
                last_stall_log = time.time()
                print(f"[engine] 局面 {time.time() - last_progress:.0f}s 未动，继续轮询 "
                      f"turn={st.turn} cur={st.current_player} me={st.my_id} "
                      f"hand={len(st.my_hand)} board={len(st.my_board)}", flush=True)

            if not st.started:
                time.sleep(self.cfg.poll)
                continue
            if st.finished:
                print("[engine] 对局结束")
                return "finished"

            # **选择面板开着就算"能操作"**：真机实证（test12）——打出 `BE_726 克苏恩仪式`
            # 后弹出一个 GENERAL 选择面板（克苏恩的愤怒/领域/凝视/仆从），
            # 这时 `my_action_window=False`（不是我的回合窗口），
            # 旧代码就整局在"等待中"空转 60 秒，而游戏在等我们选牌。
            if not st.my_action_window and not st.choice_open:
                if st.turn != last_turn:
                    last_turn = st.turn
                    print(f"[engine] 对手回合 turn={st.turn}（GameTURN={st.turn_global}）", flush=True)
                if time.time() - getattr(self, "_beat", 0) > 10:
                    self._beat = time.time()
                    print(f"[engine] 等待中 mode={snap.mode} turn={st.turn} "
                          f"cur={st.current_player} me={st.my_id} "
                          f"hand={len(st.my_hand)} board={len(st.my_board)}", flush=True)
                time.sleep(self.cfg.poll)
                continue

            if st.turn != last_turn:
                last_turn = st.turn
                self.stats["turns"] += 1
                print(f"[engine] 我的回合 turn={st.turn}（GameTURN={st.turn_global}）", flush=True)

            # ---- 动作前**强制现查一次**：这一下要用的方案必须是刚刚问出来的 ----
            batch = self._query_before_action("主循环", st=st)
            if not batch:
                time.sleep(self.cfg.scan_interval)
                continue

            plan = batch[0]        # 只取 A 方案，B/C 一律丢掉（它们基于旧局面）
            # **面板开着时优先用盒子"点名"的那条**：盒子的 A 方案有时还是上一拍的
            # `end`/`play`（面板刚弹出它还没重算），照它点会盲点第 1 个候选。
            # 真机实证（2026-10-28 10:16 那局）：面板已开、A 还是 end，
            # 我们点了 1 号候选（克苏恩的愤怒）；同一批里其实有 `choice` 方案
            # 点名 BE_013t4。有名字的优先，没名字才退回 A。
            if st.choice_open:
                alt = next((p for p in batch if self._is_choice_plan(p)), None)
                if alt is not None and alt is not plan:
                    if plan.target_card_id != alt.target_card_id:
                        print(f"[engine]   面板开着：A 方案是 {plan.action}，"
                              f"改用盒子点名的 {alt.target_card_id or alt.card_id}", flush=True)
                    plan = alt
            self.stats["plans"] += 1
            # **不做"重复推荐就跳过/就结束回合"的判断**：一条推荐值不值得再点，
            # 由游戏裁决 —— 牌不在手会被下面的断言拦住，点了没生效会被核对判成
            # swallowed 然后重来。所以这里不再有 dup 计数器、不再有"推进回合"的分支：
            # 那两个东西的真机后果是把本该重试的攻击/出牌直接换成"结束回合"。

            # 断言：动作前必须真的能操作。两种合法情形：
            #   1) 我的回合窗口已开；2) 选择面板开着（哪怕不在我的回合窗口）。
            # 真机实证（test12）：选择面板弹出时 `my_action_window=False`，
            # 拿"必须是我的回合"去断言会直接把这条正确动作拦掉。
            if st.choice_open:
                self.stepper.require(len(st.choices) > 0, "choice_open", n=len(st.choices),
                                     turn=st.turn, current_player=st.current_player,
                                     my_id=st.my_id)
            else:
                self.stepper.require(st.my_action_window, "my_turn",
                                     turn=st.turn, current_player=st.current_player, my_id=st.my_id,
                                     options_seq=st.hand_options_seq, turn_seq=st.turn_seq)
            ac = self.actions
            if ac is not None:
                ac.clicks.clear()
            seq_before = self.sync.power.seq
            ver_before = snap.version
            resolved: dict = {}
            # 从这一刻起记录新增的原始日志行，用来核对这一步到底有没有真的打出东西
            self.sync.power.mark()

            # ① 这一步的输入：盒子给的 A 方案 + 当前局面指纹（和 Power.log 对账用）
            self.stepper.step("plan_A", action=plan.action, card=plan.card_id or plan.card_name,
                              box_hand=plan.hand_position, box_board=plan.board_position,
                              box_target=f"{plan.target}:{plan.target_position}",
                              turn=st.turn, mine=st.is_my_turn,
                              seq=seq_before, ver=ver_before,
                              hand=[e.card_id for e in st.my_hand],
                              board=[e.card_id for e in st.my_board])
            # 盒子这一批推过来的原始 JSON 全量落盘（A/B/C 都在里面），
            # 便于事后对照"盒子同期推荐什么 / 我们打了什么 / 日志实际发生什么"。
            self.stepper.step("box_rec_raw", n=len(batch),
                              raw=getattr(self.bridge, "_last_raw", ""))
            try:
                self._execute(plan, st, resolved)
            except AssertFailed as e:
                # 前置断言失败：**这一下不点**，但既不投降也不退出。
                # 按时间线证据（盒子 options 比牌的 REVEALED 早 3~5s），
                # "推荐里有、手上还没有"是**必然出现**的正常中间态 —— 等它进手，
                # 再问一次盒子（疯狂轮询自愈，不加锁）。
                self.stats["errors"] += 1
                print(f"[engine] 断言拦截（未点击，等牌进手/等新方案）: {e}", flush=True)
                self.stepper.step("wait_card_in_hand", card=plan.card_id,
                                  box_hand=plan.hand_position,
                                  hand=[e.card_id for e in st.my_hand])
                time.sleep(0.9)
                continue
            except RuntimeError as e:
                print("[engine] 窗口异常:", e)
                return "window-lost"
            # 除"断言失败"外**一律不再吞**：以前这里用 `except Exception` 兜住所有异常，
            # 结果坐标越界这种真 bug（ValueError: 无效坐标）被记成"动作失败/被吞"，
            # 查了一晚上才找到。现在让程序栈直接冒出来，宁可这一轮炸掉。
            self.stats["acts"] += 1

            # ② 实际点了哪些像素
            clicks = ac.clicks if ac is not None else []
            self.stepper.step("clicked", n=len(clicks), clicks=clicks, resolved=resolved)

            # ③ 结果核对：只看**游戏侧证据**。
            # 旧判据是"Power.log 行号/版本号变了没有"，真机实证会误判：23:46 那三次
            # 出牌全记成 effect=true，可日志里一个 PLAY 块都没有 —— 前进的是对手的动作，
            # 脚本却以为打出去了。现在按动作类型找对应的块，找不到就重试。
            act = (plan.action or "").lower()
            need_effect = act in ("play", "attack", "hero_power", "trade") or "choice" in act
            ok, why = self._await_effect(plan, st, 3.0 if need_effect else 5.0)
            seq_after = self.sync.power.seq
            ver_after = self.sync.pump().version
            if self.act_log is not None:
                self.act_log.write({
                    "turn": st.turn, "my_turn": st.is_my_turn,
                    "seq_before": seq_before, "seq_after": seq_after,
                    "ver_before": ver_before, "ver_after": ver_after,
                    "plans_in_batch": len(batch),
                    "plan": {"action": plan.action, "card_id": plan.card_id,
                             "hand_position": plan.hand_position,
                             "board_position": plan.board_position,
                             "target": plan.target, "target_position": plan.target_position},
                    "resolved": resolved, "clicks": clicks, "effect": ok, "evidence": why,
                })
            if ok:
                self.stepper.step("ok:action_effect", action=plan.action, card=plan.card_id,
                                  evidence=why, before=seq_before, after=seq_after, clicks=clicks)
            else:
                # 被吞/没生效：记一笔，接着轮询重试（这是自愈机制，不是错误）。
                # 这里刻意**不做任何补偿**：不挪手牌偏移量、不重设窗口尺寸。
                # 补偿只会把"真 bug（坐标越界、牌数算错）"伪装成"点空"，让人查不出原因。
                self.stats["swallowed"] += 1
                self.stepper.step("swallowed", action=plan.action, card=plan.card_id,
                                  evidence=why, before=seq_before, after=seq_after, clicks=clicks)
            # 一步一动：执行完立刻回到循环顶部，重新向桥要一份全新方案（不重试、不复用）
            time.sleep(self.cfg.scan_interval)

        return "timeout"

    # ---------------- 结果核对 ----------------
    def _await_effect(self, plan: Plan, st_before: GameState, timeout: float) -> tuple[bool, str]:
        """在 timeout 内不断折叠日志，直到出现该动作的游戏侧证据。"""
        end = time.time() + timeout
        ok, why = False, "超时且无证据"
        while True:
            self.sync.pump()          # 继续把新行折叠进状态（也是重试的输入）
            ok, why = self._verify_effect(
                plan, st_before, self.sync.power.since_mark(), self.sync.power.state
            )
            if ok or time.time() >= end:
                return ok, why
            time.sleep(0.12)

    @staticmethod
    def _verify_effect(plan: Plan, st_before: GameState, lines: list[str],
                       st_after: GameState) -> tuple[bool, str]:
        """用游戏侧证据判断这一步成没成。

        证据优先级：日志里的 Block 类型 > 状态前后差异 > 兜底（判失败）。
        Block 类型是炉石自己打印的，不依赖我们对 UI 的假设。
        """
        a = (plan.action or "").lower()
        cid = plan.card_id or ""
        joined = "".join(lines)

        # 先按动作类型判，别用"日志里有任何块"当证据：
        # 真机踩过 —— 结束回合时上一手的 PLAY 块刚好还在刷，被判成"PLAY块"成功。
        if a.startswith("end") or a == "pass":
            if (not st_after.is_my_turn) or st_after.turn != st_before.turn:
                return True, "回合已交出"
            return False, "回合仍在我手上"

        if st_before.choice_open or "choice" in a or a in ("pick", "select"):
            if not st_after.choice_open:
                return True, "选择面板已关闭"
            # 选完一张立刻弹下一张（连发发现面板）时，面板还开着但候选已经换了 ——
            # 这也算这一步生效了，否则会把它当成失败反复点同一张。
            if [c.get("card_id") for c in st_before.choices] != \
                    [c.get("card_id") for c in st_after.choices]:
                return True, "候选已换下一组"
            return False, "选择面板还开着"

        if a == "attack":
            for ln in lines:
                if "BlockType=ATTACK" in ln and (not cid or f"cardId={cid}" in ln):
                    return True, "ATTACK块"
            return False, "无 ATTACK 块"

        if a in ("hero_power", "hero_skill"):
            ok = "BlockType=POWER" in joined or "BlockType=HERO_POWER" in joined
            return (True, "POWER块") if ok else (False, "无 POWER 块")

        if a == "play":
            # 光看"有 PLAY 块"会**把上一条动作的块算到这一条头上**：
            # 真机实证（test4 回合1）——同一张 BE_207 连点两次，第二次的点击其实没成，
            # 但 3 秒窗口里还留着前一次的 PLAY 块，于是被判成"两次都成功"，
            # 游戏日志里只有一张。所以块必须**点名是这张牌**才算。
            hit = False
            for ln in lines:
                if "BlockType=PLAY" not in ln:
                    continue
                if not cid or f"cardId={cid}" in ln:
                    hit = True
                    break
            if hit:
                return True, "PLAY块"
            # 同名多张按 eid 数：至少得有一张真的离开了手牌
            before = [e.eid for e in st_before.my_hand if e.card_id == cid]
            after = [e.eid for e in st_after.my_hand if e.card_id == cid]
            if cid and before and len(after) < len(before):
                return True, "牌已离手"
            return False, "牌还在手上"

        return (True, "有 PLAY 块") if "BlockType=PLAY" in joined else (False, "无游戏侧证据")

    # ---------------- 执行 ----------------
    def _execute(self, plan: Plan, st: GameState, resolved: dict | None = None) -> None:
        # 出牌前的"思考"：由状态机决定（专注/犹豫/走神/离座），
        # 复杂度越高想得越久，有斩杀线反而更快（Hick 定律 + 人类紧迫感）。
        #
        # **但必须服从回合计时**（真机 2026-10-28 14:31：连续 4 个选择面板 +
        # 每步 3~7s 的"思考"，一回合直接烧完）。规则：
        #   * 选择面板：不等（面板本身就是等待，点了就要快）；
        #   * 本回合已经过了 35s：思考上限 1.2s；
        #   * 过了 50s：上限 0.3s。
        options = len(getattr(st, "options", []) or [])
        lethal = bool(getattr(plan, "lethal", False))
        now = time.time()
        if st.is_my_turn and self._turn_key != st.turn_seq:
            self._turn_key = st.turn_seq
            self._turn_started = now
        age = now - self._turn_started if st.is_my_turn else 0.0
        dt = now - self._last_think          # 距上一个动作过了多久 -> 状态机推进
        self._last_think = now
        if st.choice_open:
            wait = random.uniform(0.10, 0.25)
        else:
            wait = self.human.think_delay(options=options, lethal=lethal, dt=dt)
            wait *= max(0.0, float(getattr(self.cfg, "think_scale", 1.0)))
            # 我方回合硬上限：快攻卡组 3 秒以上的停顿就是在告诉对面"这是脚本"，
            # 也真的会把回合烧掉。控制/组合技把 think_scale 调回 1.0 即可。
            wait = min(wait, 1.5)
            if age > 50:
                wait = min(wait, 0.3)
            elif age > 35:
                wait = min(wait, 1.0)
        time.sleep(wait)
        """盒子说什么就点什么；resolved 只用于动作日志（这一步解析成了哪个槽/下标）。"""
        resolved = resolved if resolved is not None else {}
        a = (plan.action or "").lower()
        ac = self.actions

        if st.choice_open:
            self._do_choice(plan, st)
            return

        if a == "play":
            self._do_play(plan, st, resolved)
        elif a == "attack":
            mv = st.my_board
            tgt = self._target(plan, st) or Target.rival_hero()
            bp = plan.board_position
            if bp:
                idx = board_rank(mv, plan.card_id, bp)
                # 断言：这个槽位上必须真的是盒子里点名的攻击者。
                # 我们场面列表里压根没有这张牌时（衍生随从/顺序不同），退化成
                # "按盒子槽位点 + 只查边界"，和手牌同一个策略（决策层就是盒子）。
                known = any(e.card_id == plan.card_id for e in mv) if plan.card_id else True
                if not known and plan.card_id:
                    print(f"[engine]   场面列表里没有 {plan.card_id}，按盒子槽位 {bp} 点", flush=True)
                    self.stepper.step("trust_box_slot", card=plan.card_id, box_slot=bp,
                                      board=[e.card_id for e in mv])
                    idx = max(0, min(bp - 1, max(len(mv) - 1, 0)))
                    self.stepper.require(0 <= idx < max(len(mv), 1), "attacker_bound",
                                         slot=idx + 1, size=len(mv), card=plan.card_id)
                else:
                    got = mv[idx].card_id if 0 <= idx < len(mv) else "<越界>"
                    self.stepper.require(got == (plan.card_id or got), "attacker_slot",
                                         slot=idx + 1, size=len(mv), want=plan.card_id, got=got,
                                         board=[e.card_id for e in mv])
                print(f"[engine]   我方场面[{len(mv)}] 攻击者={plan.card_id or bp} -> 槽 {idx + 1}，"
                      f"目标={tgt.kind} 第 {tgt.index + 1}/{tgt.size}", flush=True)
                ac.attack(idx, max(len(mv), 1), tgt)
            else:
                ac.attack(0, 0, tgt, hero=True)   # 英雄攻击
        elif a == "hero_power":
            ac.hero_power()
        elif a == "trade":
            found = self._hand_index_by_card(plan, st)
            pos = found if found >= 0 else (plan.hand_position or 1) - 1
            ac.trade(pos, max(len(st.my_hand), pos + 1))
        elif "choice" in a or "choose" in a or "discover" in a or a in ("pick", "select"):
            pos = plan.target_position or plan.hand_position or 1
            n = len(st.choices) or max(3, pos)
            if n == 2:
                ac.choose_one(min(max(0, pos - 1), 1))
            else:
                ac.choose_discover(max(0, pos - 1), n)
        elif a == "unknown":
            if plan.hand_position:
                self._do_play(plan, st)
            elif plan.board_position:
                pos = plan.board_position
                ac.attack(
                    pos - 1,
                    max(len(st.my_board), pos),
                    self._target(plan, st) or Target.rival_hero(),
                )
            elif plan.target_position:
                pos = plan.target_position
                n = len(st.choices) or max(3, pos)
                if n == 2:
                    ac.choose_one(min(max(0, pos - 1), 1))
                else:
                    ac.choose_discover(max(0, pos - 1), n)
            else:
                ac.end_turn()
        elif a.startswith("end") or a == "pass":
            ac.end_turn()
        elif a in ("mulligan", "replace"):
            ac.confirm_mulligan()
        else:
            print(f"[engine] 未识别动作 {plan.action!r}，当作出牌处理")
            self._do_play(plan, st)

    @staticmethod
    def _is_choice_plan(p: Plan) -> bool:
        """这条方案是不是"在面板里选一张"（盒子用 raw_action=choice / 点名 target）。"""
        raw = str(getattr(p, "raw_action", "") or "").lower()
        act = (p.action or "").lower()
        return raw == "choice" or act in ("choice", "choose", "discover", "pick", "select") \
            or "choice" in act

    def _do_choice(self, plan: Plan, st: GameState) -> None:
        """发现/抉择面板：按游戏日志给出的候选顺序点。

        日志里 Entities[i] 的 i 就是面板上第几个；盒子点名的那张优先，
        没点名就用它给的位置。

        **TARGET 不是卡牌面板**：`ChoiceType=TARGET` 是"在场上点一个随从"
        （真机 10:25:18 克苏恩的凝视：三个敌人亮绿框，等我们点）。候选的
        `Entities[i]` 只是可选目标清单，点的是**场面矩形**，不是发现面板坐标。
        以前一律按发现面板点，点在空处 → 面板不关 → 整回合被烧绳。
        """
        ctype = (st.choice_type or "").upper()
        cid = plan.card_id or plan.target_card_id or ""

        if ctype == "TARGET":
            tgt = self._target(plan, st)
            if tgt is None:
                rv = st.rival_board
                tgt = Target.minion(0, max(len(rv), 1))
            print(f"[engine]   目标选择面板[{len(st.choices)}] 候选 "
                  f"{[c['card_id'] for c in st.choices]}；盒子要 {cid or '-'} "
                  f"-> {tgt.kind} 第 {tgt.index + 1}/{tgt.size}", flush=True)
            self.actions.l_click(self.actions.target_rect(tgt))
            self._wait_choice_changed(st)
            return

        n = len(st.choices) or 3
        idx = st.choice_index_of(cid)
        if idx is None:
            idx = max(0, (plan.target_position or 1) - 1)
            print(f"[engine]   选择面板[{n}] 候选 {[c['card_id'] for c in st.choices]}；"
                  f"盒子没点名 -> 按位置点第 {idx + 1} 个", flush=True)
        else:
            print(f"[engine]   选择面板[{n}] 候选 {[c['card_id'] for c in st.choices]}；"
                  f"盒子要 {cid} -> 第 {idx + 1} 个", flush=True)
        # 2 张候选用的是"左右两张、中间空"的专用布局，和 3/4 张的发现面板不同。
        # 用 3 槽布局去点 2 张面板，中间那一下正好落在两张牌的空隙里（真机实证：
        # 选择面板点了 4 次都还开着）。
        if n == 2:
            self.actions.choose_one(min(idx, 1))
        elif (st.choice_type or "").upper() == "GENERAL" and n >= 4:
            # 「进行选择」类面板（克苏恩仪式）：4 张大牌，坐标和发现面板不同
            self.actions.choose_general(idx, n)
        else:
            self.actions.choose_discover(idx, n)

        # 点完**轮询到面板变化**（关闭或换下一组），最多 1.2s：
        # 固定等 0.8s 会让链式面板每块都多花时间；立刻判定又会把正常关闭记成"没关"。
        changed, snap = self._wait_choice_changed(st)
        if not changed:
            try:
                import time as _t

                out = pathlib.Path(".captures") / f"choice-fail-{_t.strftime('%H%M%S')}.png"
                out.parent.mkdir(exist_ok=True)
                from .win import capture

                capture(self.window.hwnd, out)
                print(f"[engine]   选择面板没关：截图 {out}；候选 {[c['card_id'] for c in st.choices]}；"
                      f"点了第 {idx + 1} 个（rect 中心约 {self.actions.last_rect}）", flush=True)
            except Exception as e:
                print(f"[engine]   选择面板没关，截图失败: {e}", flush=True)

    def _wait_choice_changed(self, st: GameState, timeout: float = 1.2) -> tuple[bool, object]:
        """点完后面板是否真的变了：关闭，或候选换成下一组。返回 (changed, snap)。"""
        want = [c.get("card_id") for c in st.choices]
        deadline = time.time() + timeout
        snap = self.sync.pump()
        while True:
            got = [c.get("card_id") for c in snap.game.choices]
            changed = (not snap.game.choice_open) or got != want
            if changed or time.time() >= deadline:
                return changed, snap
            time.sleep(0.12)
            snap = self.sync.pump()

    @staticmethod
    def resolve_play_slot(st, box_pos: int, cid: str) -> tuple[int, str]:
        """决定「这张牌在手牌的第几槽（0 基）」。返回 (pos, 依据)。

        依据取值：`card`（用游戏选项映射核到卡号所在的槽）、`box`（信盒子的槽位）、
        `list`（按我们的手牌列表找）。规则见 bugs/已修-06-…/README.md。
        """
        slots = st.my_hand_slots()

        def slot_card(slot: int) -> str:
            eid = (st.hand_option_eids.get(st.my_id) or {}).get(slot)
            ent = st.entities.get(eid) if eid else None
            return (ent.card_id if ent is not None else "") or ""

        opt_hit = sorted(s for s, c in (slots or {}).items() if cid and c == cid)
        if box_pos and 1 <= box_pos <= max(len(st.my_hand), st.hand_size_hint(), 1):
            box_card = slot_card(box_pos)
            # 选项映射可能比界面旧一拍（真机实证 20:0x：映射说槽 2 是 BE_726，
            # 而我们的手牌列表说槽 2 就是 TIME_026，改槽后 hand_slot 断言立刻失败）。
            # 所以「改槽」必须两个来源都点头：选项映射和手牌列表都指向同一槽才算。
            if cid and box_card and box_card != cid and opt_hit:
                alt = next((s for s in opt_hit
                            if slot_card(s) == cid and (slots or {}).get(s) == cid), None)
                if alt:
                    return alt - 1, "card"
            return box_pos - 1, "box"
        if opt_hit:
            return opt_hit[0] - 1, "list"
        return max(0, int(box_pos or 1) - 1), "list"

    def _do_play(self, plan: Plan, st: GameState, resolved: dict | None = None) -> None:
        """出牌：作者 execPower（手牌->场面）+ 需要时 execPointTo（指向目标）。

        槽位 = 作者 `handArea.indexOfCard` 的语义：在**同步好的密集手牌列表**里
        找这张卡的列表下标（列表就是界面顺序），找不到才退回盒子给的 ZONE_POSITION。
        """
        ac = self.actions
        slots = st.my_hand_slots()          # 游戏选项快照，用于日志对照
        box_pos = plan.hand_position or 0
        cid = plan.card_id or ""

        pos, basis = self.resolve_play_slot(st, box_pos, cid)
        trusted_box = basis == "box"
        opt_hit = sorted(s for s, c in (slots or {}).items() if cid and c == cid)
        if basis == "card":
            print(f"[engine]   [?] 盒子槽 {box_pos} 与卡号 {cid} 冲突，改用卡号所在槽 {pos + 1}",
                  flush=True)
            self.stepper.step("slot_from_card", card=cid, box_slot=box_pos, used_slot=pos + 1)
        elif basis == "box" and opt_hit and (slots or {}).get(box_pos) not in (None, cid):
            print(f"[engine]   [!] 盒子槽 {box_pos} 我们快照里是 {(slots or {}).get(box_pos)}，"
                  f"以盒子为准（快照比游戏旧）", flush=True)
            self.stepper.step("slot_from_box", card=cid, box_slot=box_pos,
                              our_snapshot=(slots or {}).get(box_pos))
        # 布局张数用"已知卡号 + 游戏声明的最右槽位"，**不能**用 len(列表)：
        # 列表里可能挂着没卡号的占位实体，会把手牌算多一张，整排矩形偏一格、点空。
        hand_size = max(st.hand_size_hint(), pos + 1)
        # 断言：槽位必须存在。用盒子槽位时**不再用我们的列表校验牌名** ——
        # 我们的列表本来就可能是旧的那一份，拿它去否决盒子只会把正确动作拦住。
        if trusted_box:
            self.stepper.require(1 <= pos + 1 <= max(len(st.my_hand),
                                                     st.hand_size_hint(), pos + 1),
                                 "hand_slot_bound", slot=pos + 1,
                                 size=len(st.my_hand), card=cid)
        else:
            self.stepper.require_hand_slot(st, pos + 1, cid)
        self.stepper.require(hand_size >= pos + 1, "hand_size", hand_size=hand_size, slot=pos + 1)
        # 费用/可用性：游戏自己在选项里写了不可用原因（REQ_ENOUGH_MANA 等）。
        # 有原因就别点 —— 点下去游戏只会静默忽略（零日志），还会被当成"被吞"重试。
        #
        # **必须用游戏自己的 (槽位 -> eid) 映射去查**：真机实证（test13）——
        # 那一手真实 6 张（选项快照：1=BE_726, 2=CATA_210, 3=BE_726, 4=CAP_405,
        # 5=DINO_COIN2, 6=BE_729），而我们的 my_hand 只认得出 3 张（位置 4/5/6）。
        # 盒子要槽 3 = BE_726（游戏 error=NONE，合法），我们却按"列表第 3 个"抓到
        # BE_729（eid=19, REQ_ENOUGH_MANA）—— 拿错的实体去判可用性，
        # 结果一张合法的牌被拦了 3 分半钟、点了 230 轮空。
        slot_eid = st.slot_eid(pos + 1) if hasattr(st, "slot_eid") else 0
        ent = st.entities.get(slot_eid) if slot_eid else None
        if ent is None:
            ent = next((e for e in st.my_hand if e.zone_pos == pos + 1), None)
        if ent is None and 0 <= pos < len(st.my_hand):
            ent = st.my_hand[pos]
        if ent is not None:
            err = st.option_errors.get(ent.eid) or ""
            self.stepper.require(err in ("", "NONE"), "card_usable",
                                 card=cid, eid=ent.eid, error=err, slot=pos + 1,
                                 src=("option_map" if slot_eid else "roster"))
        # 技能文档实证：牌刚进手时 UI 槽位还在落定，立刻点会被吞（"第一击被吞 15s"）。
        # 同步成功后再等 600~1000ms 才点。
        time.sleep(random.uniform(0.6, 1.0))
        if resolved is not None:
            resolved.update({"hand_slot": pos + 1, "hand_size": hand_size})
        tgt = self._target(plan, st)
        bp = plan.board_position

        lst = " ".join(f"{i + 1}:{e.card_id}" for i, e in enumerate(st.my_hand)) or "-"
        print(f"[engine]   手牌[{hand_size}] {lst} | 盒子槽={box_pos} cardId={cid} "
              f"-> 用槽 {pos + 1}/{hand_size}"
              + (f" | 目标={tgt.kind}:{tgt.index + 1}/{tgt.size}" if tgt else ""), flush=True)

        if tgt is not None and not bp:
            ac.play_targeted(pos, hand_size, ac.target_rect(tgt))
            return

        board_size = len(st.my_board)
        board_index = (bp - 1) if bp else board_size
        board_index = max(0, min(board_index, board_size))
        # 断言：落点下标必须在 0..size（size = 追加到末尾）
        self.stepper.require_board(board_index, board_size)
        if resolved is not None:
            resolved.update({"board_index": board_index, "board_size": board_size})
        print(f"[engine]   场面[{board_size}] 盒子上场位={bp} -> 落点槽 {board_index + 1}", flush=True)
        ac.play_card(
            hand_index=pos,
            hand_size=hand_size,
            board_index=board_index,
            board_size=board_size,
            target=tgt,
        )

    @staticmethod
    def _hand_index_by_card(plan: Plan, st: GameState) -> int:
        """按 cardId 找手牌下标（0 基）；找不到返回 -1。

        只作为「盒子槽位对不上」时的修正手段：手牌有重复卡时以盒子槽位为准。
        """
        if not plan.card_id:
            return -1
        for i, e in enumerate(st.my_hand):
            if e.card_id == plan.card_id:
                return i
        return -1

    @staticmethod
    def _target(plan: Plan, st: GameState) -> Target | None:
        """目标 -> (密集下标, 张数)，与作者 indexOfCard / cardSize 完全一致。

        盒子有时只给 `target`（不带 opp-target/my-target），**没写是哪一边**。
        这时不能默认敌方（真机踩过：buff 加给了对面），要先拿 cardId 去
        我方场面 / 敌方场面 / 我方手牌里查，查不到才按位置猜。
        """
        t = (plan.target or "").lower()
        pos = plan.target_position or 0
        cid = plan.target_card_id or ""
        if t in ("hero", "rival_hero", "enemy_hero"):
            return Target.rival_hero()
        if t == "my_hero":
            return Target.hero()
        mv, rv, mh = st.my_board, st.rival_board, st.my_hand

        def _slot(board: list, card_id: str, box_pos: int) -> tuple[int, int]:
            """(密集下标, 张数)。

            **张数不能只信我们自己的场面列表**：真机实证（test10 回合3）盒子给
            `opp-target position=2`，我们的 rival_board 只解析到 1 个随从，
            于是按"1 个随从"排布局、点在唯一那一格，连点 8 次没有 ATTACK 块。
            盒子给的位置就是游戏里的场面序号，和我们的列表谁大信谁。
            """
            idx = None
            # **盒子给了场面序号就以它为准**：它来自游戏里的 zonePos，是"第几个随从"；
            # 我们的列表可能少解析了随从（test10：敌方 2 个只解析到 1 个），
            # 这时候按 cardId 找到的下标是"我们列表里的第几个"，不是真实位置。
            if box_pos:
                idx = box_pos - 1
                if card_id:
                    real = next((i for i, e in enumerate(board) if e.card_id == card_id), None)
                    if real is not None and real != idx:
                        print(f"[engine]   [!] 目标 {card_id}: 盒子场面位={box_pos} "
                              f"我们列表下标={real + 1}，听盒子的", flush=True)
            if idx is None and card_id:
                for i, e in enumerate(board):
                    if e.card_id == card_id:
                        idx = i
                        break
            if idx is None:
                idx = 0
            size = max(len(board), box_pos or 0, idx + 1, 1)
            return idx, size

        if t == "my_board":
            idx, size = _slot(mv, cid, pos)
            return Target.ally_minion(idx, size)
        if t in ("board", "enemy_board", "enemy", ""):
            if t in ("enemy_board", "enemy"):
                idx, size = _slot(rv, cid, pos)
                print(f"[engine]   敌方目标 {cid or '-'} 盒子上场位={pos} "
                      f"我方列表={len(rv)} -> 第 {idx + 1}/{size} 格", flush=True)
                return Target.minion(idx, size)
            # 没写边：按 cardId 查三处
            mine = [i for i, e in enumerate(mv) if cid and e.card_id == cid]
            if mine:
                return Target.ally_minion(mine[0], max(len(mv), 1))
            theirs = [i for i, e in enumerate(rv) if cid and e.card_id == cid]
            if theirs:
                idx, size = _slot(rv, cid, pos)
                return Target.minion(idx, size)
            hand = [i for i, e in enumerate(mh) if cid and e.card_id == cid]
            if hand:
                return Target.ally_hand(hand[0], max(len(mh), 1))
            if t == "" and not pos:
                return None
            print(f"[engine]   [!] 目标 {cid or pos} 三处都没找到，按敌方场面处理", flush=True)
            idx, size = _slot(rv, cid, pos)
            return Target.minion(idx, size)
        return None














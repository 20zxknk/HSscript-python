"""hspy —— 炉石自动打牌的三层脚本（唯一入口）。

    python run.py                # 直接开打（真实鼠标）
    python run.py --games 1      # 只打一局
    python run.py --seconds 600  # 最多跑 10 分钟
    python run.py --probe        # 每次点击前截图标出落点（排查坐标用）
    python run.py --mode wild --deck 2

三层（互不越界）：
    输入层  input/     Power.log -> GameState（回合/手牌/场面/选项/选择面板）
    决策层  decision/  盒子 HSAng 的推荐（frida 桥，stdin 发 SCAN，stdout 收 plans）
    输出层  output/    真实鼠标 SendInput + 作者 GameRect 坐标表

跑之前会自动把这些前提准备好：
    * 推荐桥在进对局前就挂上（推荐在开局/换牌那一刻就产生）
    * 单实例（两个进程会互相抢桥）
    * 窗口比例只**检查并提示**，不自动改（改环境属于保护性代码，已拆掉）
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from hspy import modes, win  # noqa: E402
from hspy.actlog import ActionLog  # noqa: E402
from hspy.config import load_script_config  # noqa: E402
from hspy.engine import Engine, EngineConfig  # noqa: E402
from hspy.navigator import Navigator  # noqa: E402


def arg(name: str, default: str | None = None) -> str | None:
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def enter_match(nav: Navigator) -> bool:
    """进一局「新的、还没结束」的对局。

    关键流程（真机踩过的坑都在这）：
      * 已经在对战/卡组页（TOURNAMENT）时**不要先回主界面** —— 那里正是
        点「开始」的地方；回主界面要连点两个不同的"返回"（相对坐标不同），
        会在"卡组页 <-> 模式页"之间来回摆，一直点不出结果。
      * 只有真的在结算界面（GAMEPLAY）或未知界面时才回主界面。
      * 进对局前先解钉日志并重建，否则上一局的残局状态会被当成本局。
    """
    try:
        nav.sync.power.pin_log(None)
        nav.sync.rebuild()
    except Exception as e:
        print("[run] 解钉日志失败:", e, flush=True)

    m = nav.mode()
    print(f"[run] 进对局前界面: mode={m}", flush=True)
    if m in (None, "GAMEPLAY", "STARTUP", "LOGIN", "GAME_MODE", "ADVENTURE"):
        # 结算界面：先点「点击继续」退出，再回主界面
        if m == "GAMEPLAY":
            win.click_ratio(nav.hwnd, 0.50, 0.93)
            time.sleep(1.5)
        nav.to_hub()
    elif m == "TOURNAMENT":
        print("[run] 已在对战/卡组页，直接开始匹配（不回主界面）", flush=True)

    for attempt in range(1, 4):
        seg_before = nav.sync.power.seg_index
        print(f"=== 进对战（第 {attempt} 次, 模式={nav.cfg.run_mode} 卡组位={nav.cfg.deck_pos}, "
              f"当前段 {seg_before}）===", flush=True)
        if not nav.go_tournament():
            # go_tournament 只认 screen 日志翻到 GAMEPLAY；真机见过"最后一秒匹配上"：
            # 它 240s 超时返回 False，但 Power.log 里新对局其实已经开始
            # （2026-10-28 22:52:54 退出，22:53 画面已在第 1 回合）。
            # 先看日志再判失败，接管这局，别把它当"没进去"。
            snap = nav.sync.pump()
            if snap.game.started and not snap.game.finished:
                print("[run] go_tournament 超时，但日志里新对局已开始 -> 直接接管", flush=True)
                return True
            print("[run] 进入对战失败", flush=True)
            continue
        # 必须看到「新的 CREATE_GAME（段号+1）」，否则会把上一局的残留状态当成新对局
        # 只看事实：新的 CREATE_GAME 段 + 已开局 + 没结束。
        # 不能要求 mulligan_open —— 进得晚一点（换牌已结束）它永远为假，
        # 于是每局白等 60 秒再点「继续」（BUG 11）。
        # 判据用「日志在读进新行」而不是段号：全新会话里这一局就是第 1 段，
        # seg_index 不会 > seg_before（真机实证 test/c2：三次都判成没等到新对局）。
        seq_before = nav.sync.power.seq
        ok = nav.sync.wait_until(
            lambda s: nav.sync.power.seq > seq_before
            and s.game.started
            and not s.game.finished,
            timeout=60,
        )
        snap = nav.sync.pump()
        if ok:
            print(f"[run] 新对局已开始（段 {seg_before}->{nav.sync.power.seg_index}，换牌中）",
                  flush=True)
            return True
        print(f"[run] 没等到新对局（killed={snap.game.finished}），点继续退出后重试", flush=True)
        win.click_ratio(nav.hwnd, 0.50, 0.93)
        time.sleep(3.0)
        nav.sync.rebuild()
    return False


def acquire_lock() -> bool:
    """单实例锁：两个 run 同时跑会互相抢推荐桥（真机踩过：桥握手超时整轮报废）。"""
    lock = Path("logs") / ".run.lock"
    lock.parent.mkdir(exist_ok=True)
    if lock.exists():
        try:
            old = int(lock.read_text(encoding="utf-8").strip() or 0)
        except Exception:
            old = 0
        if old:
            import subprocess

            try:
                out = subprocess.run(["tasklist", "/FI", f"PID eq {old}"],
                                     capture_output=True, text=True, timeout=10).stdout
                if str(old) in out:
                    print(f"[run] 已有实例在跑（pid={old}），直接退出", flush=True)
                    return False
            except Exception as e:
                # 查不到旧进程就别当成"没在跑"——如实说一句，再继续（锁内容随后覆盖）
                print(f"[run] 检查旧实例失败（按无旧实例继续）: {e}", flush=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        (Path("logs") / ".run.lock").unlink()
    except FileNotFoundError:
        pass          # 本来就没有锁文件，正常
    except Exception as e:
        print(f"[run] 删锁失败（不影响本进程，但下次启动会看到旧 pid）: {e}", flush=True)


def write_record_readme(d: Path, power_log: str, offset: int) -> None:
    """写一份"怎么对照这三份东西"的说明，免得回头自己都要想半天。"""
    md = f"""# 本目录：一局的三份对照记录

| 文件 | 内容 | 时间字段 |
|---|---|---|
| `powerlog_story.md` | 这一局 Power.log 的逐事件叙述（回合 / 出牌 / 攻击 / 阵亡 / 结算） | 每行前 `` `HH:MM:SS.ffffff` `` |
| `recommendations.jsonl` | 每次向盒子要推荐收到的原文（`plans` + `raw_rec` + 桥返回的整行 JSON） | `t`（毫秒）+ `ts` |
| `mouse.jsonl` | 鼠标低层钩子记录（移动/按下/抬起/滚轮） | `t`（毫秒）+ `ts` |

## 怎么对照

1. 时间基准是同一台机器的本地时间：Power.log 行首 `D HH:MM:SS.fffffff`、
   另两份的 `t`（`HH:MM:SS.mmm`）可以直接对。
2. `mouse.jsonl` 每条有：
   - `sx/sy` 屏幕坐标，`cx/cy` 客户区坐标（客户区原点按窗口位置动态刷新）；
   - `injected=1` 表示这一下是脚本用 SendInput 发的，`0` 是物理鼠标（你自己动的）。
3. `recommendations.jsonl` 每条有 `n`（方案数）、`plans`（已解析字段）、
   `raw_rec`（盒子原始结构，含 `data/actionName/card/position`）、`raw`（桥那一行 JSON）。
4. 建议的读法：先按 `recommendations.jsonl` 找到某一步推荐 → 用它附近的 `t`
   去 `mouse.jsonl` 找那两下点击（`injected=1`）→ 再去 `powerlog_story.md` 找
   同一秒的游戏事件，就能看出"盒子说了什么 / 我们点了哪 / 游戏实际发生了什么"。

- Power.log 来源：`{power_log}`
- 叙述起点偏移：`{offset}` 字节（从该偏移往回找最近的 `CREATE_GAME`）
"""
    (d / "README.md").write_text(md, encoding="utf-8")


def main() -> int:
    # 控制台可能是 GBK：日志里出现编码不了的字符时不要抛 UnicodeEncodeError，
    # 否则一行日志就能把整局打断（真机踩过：打印 "[!]" 直接崩在中盘）。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    cfg = load_script_config()
    if "--mode" in sys.argv:
        cfg.run_mode = arg("--mode", cfg.run_mode) or cfg.run_mode
    if "--deck" in sys.argv:
        cfg.deck_pos = int(arg("--deck", str(cfg.deck_pos)) or cfg.deck_pos)
    seconds = float(arg("--seconds", str(cfg.seconds)) or cfg.seconds)
    # --seconds 是**单局**上限（runbook 一直这么写）；--minutes 才是整轮预算。
    # 以前把 seconds 当整轮预算用：`--seconds 900 --games 5` 跑到第 2 局途中就
    # 报 timeout 退出，看起来像"脚本打不完"，其实是预算到点了。
    minutes = float(arg("--minutes", "0") or 0)
    max_games = int(arg("--games", "0") or 0)
    probe = ".captures/probe" if "--probe" in sys.argv else ""
    bridge, bridge_cwd = cfg.bridge()

    if not acquire_lock():
        return 3

    print(f"=== 配置：模式={cfg.run_mode} 卡组位={cfg.deck_pos}(点{cfg.deck_click_count}次) "
          f"匹配超时={cfg.match_timeout:.0f}s 单局上限={seconds:.0f}s "
          f"整轮预算={f'{minutes:.0f}min' if minutes > 0 else '不限'} "
          f"局数上限={max_games or '不限'} ===", flush=True)
    print(f"=== 推荐桥：{bridge}", flush=True)

    already_running = True
    try:
        nav = Navigator(cfg=cfg)
    except RuntimeError as e:
        already_running = False
        print(f"=== 游戏没在跑（{e}），先启动 ===", flush=True)
        modes.launch_game(timeout=120)
        time.sleep(3)
        nav = Navigator(cfg=cfg)
    nav.cfg = cfg
    # 只有"确实没在跑"才启动并等新日志；已经在跑就立刻接上，
    # 否则会卡在 await_new_log 上等于挂机（真机踩过：游戏里正打着，脚本在等新日志）。
    if not already_running and "--no-launch" not in sys.argv:
        before = nav.sync.screen.latest_log()
        print("=== 启动炉石 ===", flush=True)
        try:
            modes.launch_game(timeout=120)
        except Exception as e:
            print("启动失败:", e)
            release_lock()
            return 1
        nav.await_new_log(before, timeout=120)

    # 坐标前提：客户区宽高比 >= 1.351 时坐标表才自洽。
    # 这里**只报不改** —— 自动调窗口属于"替使用者改环境"的保护性代码，已拆掉；
    # 比例不对就打印一行，坐标会偏、点击会被核对记成 swallowed，如实暴露不掩盖。
    _, _, cw, ch = win.client_rect(nav.hwnd)
    if not win.content_ratio_ok(nav.hwnd):
        print(f"[run] [!] 客户区 {cw}x{ch} 比例={cw / max(ch, 1):.3f} < 1.351，"
              f"手牌/场面坐标可能偏（不会自动改窗口）", flush=True)
    else:
        print(f"[run] 客户区 {cw}x{ch} 比例={cw / max(ch, 1):.3f}", flush=True)

    # ---- 录制（--record [目录]，默认 test/）：鼠标钩子 + 推荐原文 + 赛后 Power.log 叙述 ----
    record_dir: Path | None = None
    if "--record" in sys.argv or any(a.startswith("--record=") for a in sys.argv):
        v = ""
        for a in sys.argv:
            if a.startswith("--record="):
                v = a.split("=", 1)[1]
        if not v and "--record" in sys.argv:
            v = arg("--record", "") or ""
        record_dir = Path(v or "test")
        record_dir.mkdir(parents=True, exist_ok=True)
        print(f"[rec] 录制目录: {record_dir.resolve()}", flush=True)

    # ---- --debug：装看门狗。卡死不是异常，只有 faulthandler 能看出卡在哪一行 ----
    if "--debug" in sys.argv:
        from hspy import watchdog

        wd_dir = record_dir or Path("logs")
        stack = watchdog.install(wd_dir)
        print(f"[run] 看门狗已装：{stack}（每 15 秒 dump 一次栈）", flush=True)
        watchdog.beat("启动")

    hook = None
    rec = None
    story_offset = 0
    if record_dir is not None:
        from hspy.record import MouseHook, RecommendationRecorder

        hook = MouseHook(record_dir / "mouse.jsonl", hwnd=nav.hwnd)
        started = hook.start()
        print(f"[rec] 鼠标 LL 钩子: {'已挂上' if started else '挂载失败 ' + str(hook.error)}",
              flush=True)
        rec = RecommendationRecorder(record_dir / "recommendations.jsonl")

    act_path = Path("logs") / f"actions-{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    act_log = ActionLog(act_path)
    print(f"[run] 动作日志: {act_path}", flush=True)
    eng = Engine(
        EngineConfig(bridge_script=bridge, bridge_cwd=bridge_cwd, probe_dir=probe,
                     think_scale=cfg.think_scale),
        sync=nav.sync,
        act_log=act_log,
        recorder=rec,
    )
    eng.bridge.start()
    print("[run] 桥已提前挂载", flush=True)

    attach = "--attach" in sys.argv
    if attach:
        # 已经在对局里（或在排队）：不要重新走导航，直接接管当前这一局
        print("[run] attach：不重新进对局，直接接管当前对局", flush=True)
        nav.sync.pump()          # 先 pump 一次，才能拿到当前 Power.log 的路径
    elif not enter_match(nav):
        eng.close()
        release_lock()
        return 1
    # 钉死这一局的 Power.log，引擎运行期间不再换文件
    nav.sync.power.pin_log(nav.sync.power._path)
    print("[run] 日志已钉死:", nav.sync.power._path, flush=True)
    # **钉完立刻从日志头重建一次状态**：真机实证（test8）——引擎是开赛前就打开文件追尾的，
    # 本局的 CREATE_GAME / 实体批次可能落在它"打开"与"真正开打"之间，实时追尾会漏掉，
    # 结果 my_id=0、hand=0、turn=0，换牌界面读不到手牌，整局空转。
    # 日志里数据是全的（同一份留档从头回放有 85 个实体、3 张手牌），所以直接重放一遍。
    try:
        nav.sync.power.rebuild()
        st0 = nav.sync.power.state
        print(f"[run] 钉死后重建: 实体={len(st0.entities)} my_id={st0.my_id} "
              f"turn={st0.turn} hand={len(st0.my_hand)}", flush=True)
    except Exception as e:
        print(f"[run] 钉死后重建失败（继续用当前状态）: {e}", flush=True)
    if record_dir is not None and nav.sync.power._path:
        # 记下开赛时 Power.log 的字节大小：赛后就从这里往回找 CREATE_GAME，
        # 只讲这一局，不会把上一局的尾巴带进叙述
        try:
            story_offset = Path(nav.sync.power._path).stat().st_size
            print(f"[rec] Power.log 叙述起点偏移: {story_offset}", flush=True)
        except OSError:
            story_offset = 0
    eng.start()
    result = "crashed"
    games = 0
    # 整轮预算：只有显式给了 --minutes 才封顶；否则由 --games 决定跑几局。
    end_by = time.time() + minutes * 60 if minutes > 0 else float("inf")
    try:
        while time.time() < end_by and (max_games == 0 or games < max_games):
            if games > 0:
                # 上一局正常结束（不是投降）：直接再进一局
                nav.sync.power.pin_log(None)
                if not enter_match(nav):
                    break
                nav.sync.power.pin_log(nav.sync.power._path)
                print(f"[run] 第 {games + 1} 局，日志已钉死:", nav.sync.power._path, flush=True)
            games += 1
            # attach 时可能还在排队：先等"对局真的开始"（不是等换牌）
            nav.sync.wait_until(lambda s: s.game.started, timeout=180 if attach else 30)
            if nav.sync.pump().game.mulligan_open:
                time.sleep(0.8)
                try:
                    eng.do_mulligan()
                    print("[run] 换牌完成", flush=True)
                except Exception as e:
                    print("[run] 换牌失败:", e, flush=True)
            else:
                # 接手的是已经开打的残局（attach）：绝不能在这里点换牌确认，
                # 那会把"确认起手"的点击落到场上（真机踩过：白丢一张牌 + 烧绳）
                print("[run] 不在换牌阶段（接手残局），跳过换牌", flush=True)
            time.sleep(1.5)
            budget = max(60.0, seconds)
            if end_by != float("inf"):
                budget = min(budget, max(60.0, end_by - time.time()))
            result = eng.play_match(timeout=budget)
            print(f"=== 第 {games} 局结果 ===", result, eng.stats, flush=True)
            win.capture(eng.window.hwnd, f".captures/run_game{games}.png")
            if result not in ("finished",):
                break          # 异常/超时就停，别硬撑（也不投降）
    except Exception:
        # 不再只打一行 `str(e)`：那样只有一句话，栈就丢了（坐标越界那类 bug 会看起来
        # 像"动作失败"）。这里打完整栈，然后照旧收尾（投降/关游戏），绝不静默继续。
        import traceback

        traceback.print_exc()
        result = "crashed"
    finally:
        # **不自动认输**：这一条以前是"跑完不关游戏，改成投降退出"——听着像纪律，
        # 实际后果是"脚本自己崩了（比如 NameError）-> 判成未打完 -> 替你把这局投了"。
        # 认输是对局里的破坏性动作，只能由使用者决定（或明确传 --concede）。
        if result not in ("finished",) and nav.mode() == "GAMEPLAY":
            print("[run] 对局还没结束，脚本退出，**不自动认输**（要认输请加 --concede）",
                  flush=True)
            if "--concede" in sys.argv:
                print("[run] --concede 指定：认输", flush=True)
                try:
                    nav.concede()
                except Exception as e:
                    print("[run] 认输失败:", e, flush=True)
        if "--close-game" in sys.argv:
            print("[run] 关闭炉石", flush=True)
            try:
                modes.close_game()
            except Exception as e:
                print("[run] 关闭失败:", e, flush=True)
        eng.close()
        act_log.close()
        # ---- 收尾：停钩子、生成 Power.log 叙述、写对照说明 ----
        if hook is not None:
            hook.stop()
            print(f"[rec] 鼠标事件已落盘: {record_dir / 'mouse.jsonl'}", flush=True)
        if rec is not None:
            rec.close()
        if record_dir is not None:
            import subprocess as _sp

            story_path = record_dir / "powerlog_story.md"
            power_log = str(nav.sync.power._path or "")
            if power_log:
                try:
                    _sp.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "powerlog_story.py"),
                             power_log, "--offset", str(story_offset), "--out", str(story_path)],
                            check=False, timeout=180)
                except Exception as e:
                    print("[rec] 生成叙述失败:", e, flush=True)
            write_record_readme(record_dir, power_log, story_offset)
            print(f"[rec] 三份产物在 {record_dir.resolve()}", flush=True)
        release_lock()

    print(f"=== 收工：{games} 局，统计 {eng.stats} ===", flush=True)
    return 0 if result == "finished" else 2


if __name__ == "__main__":
    raise SystemExit(main())

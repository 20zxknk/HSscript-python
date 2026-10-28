"""导航：界面状态机，全部走 Sync 的动作-期望契约。

跟作者 ModeStrategy 的分工一致，但等待方式换成"读状态直到满足期望"：
每个动作都带一个 expect，看不到期望状态就重放重建再试——
不 sleep 猜、不盲点。

作者的设计理念（真机踩过）：**疯狂轮询自愈，不要加锁**。
所以这里没有"先别动"的闸门，只有"再看一眼状态"。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import coords, win
from .config import ScriptConfig, load_script_config
from .geometry import GameWindow
from .output.actions import Actions
from .output.mouse import LONG, SHORT, TINY, VK_ESCAPE, delay, key_press
from .sync import Sync

HUB = "HUB"
GAME_MODE = "GAME_MODE"
ADVENTURE = "ADVENTURE"
TOURNAMENT = "TOURNAMENT"
GAMEPLAY = "GAMEPLAY"
LOGIN = "LOGIN"
STARTUP = "STARTUP"
JOURNAL = "JOURNAL"


def default_actions(gw: GameWindow) -> Actions:
    """没注入时造一个默认动作层。

    独立成函数是为了能测：原来 `make_mouse` 写在 if 里面、却在 if 外面用，
    调用方一传 act 就 UnboundLocalError，而且传进来的 act 会被无条件覆盖。
    """
    from .output.mouse import make_mouse

    return Actions(gw, make_mouse(dry_run=False))


@dataclass
class Navigator:
    hwnd: int = 0
    gw: GameWindow = field(default_factory=GameWindow)
    sync: Sync | None = None
    act: Actions | None = None
    cfg: ScriptConfig = field(default_factory=load_script_config)

    def __post_init__(self):
        if not self.hwnd:
            self.hwnd = win.find_hwnd_for_process("Hearthstone.exe")
        self.gw.hwnd = self.hwnd
        self.gw.update()
        if self.sync is None:
            self.sync = Sync()
        if self.act is None:
            self.act = default_actions(self.gw)

    # ---------------- 基础 ----------------
    def mode(self) -> str | None:
        return self.sync.pump().mode

    def click(self, rect) -> None:
        """点一个作者坐标表里的矩形（走同一套 lClick：右键取消 -> 移动 -> 点击）。"""
        self.act.l_click(rect)

    def click_ratio(self, rx: float, ry: float) -> None:
        win.click_ratio(self.hwnd, rx, ry)

    def _fresh(self) -> None:
        """只认近 6 小时内写的日志。

        更精确的"新会话"判定交给 await_new_log()：启动游戏后等日志文件换新，
        而不是用一个时间窗去猜（闲置久了会被自己误伤）。
        """
        self.sync.screen.min_mtime = time.time() - 6 * 3600

    def await_new_log(self, previous: Path | None, timeout: float = 120.0) -> bool:
        """等 LoadingScreen.log 换成一个新文件（= 新启动的会话）。"""
        import time as _t

        deadline = _t.time() + timeout
        while _t.time() < deadline:
            cur = self.sync.screen.latest_log()
            if cur and previous and cur != previous:
                print(f"[nav] 新日志会话: {cur.parent.name}")
                return True
            if cur and previous is None:
                return True
            _t.sleep(0.5)
        return False

    # ---------------- 登录页（照 LoginModeStrategy）----------------
    def login_tick(self, stay: int) -> int:
        """登录页每 2 秒一次：前 7 次点右侧中间，之后点「确定」（卡牌调整弹窗）。

        作者原逻辑（LoginModeStrategy.afterEnter）：
            stayTime++; if (stayTime > 7) CARD_ADJUSTMENT_CONFIRM_RECT.lClick()
                        else GameUtil.lClickRightCenter()
        返回新的 stayTime。
        """
        stay += 1
        if stay > 7:
            print(f"[nav] 登录页停留 {stay} 次，点确定")
            self.click(coords.CARD_ADJUSTMENT_CONFIRM)
        else:
            print(f"[nav] 登录页第 {stay} 次：点右侧中间")
            self.click(coords.RIGHT_CENTER)
        return stay

    # ---------------- 回主界面 ----------------
    def to_hub(self, timeout: float = 120.0) -> bool:
        self._fresh()
        deadline = time.time() + timeout
        stay = 0
        back_tries = 0
        ticks = 0
        while time.time() < deadline:
            m = self.sync.pump().mode
            ticks += 1
            if ticks % 8 == 1:
                print(f"[nav] to_hub: mode={m} 第{ticks}次 (剩 {deadline - time.time():.0f}s)", flush=True)
            if m == HUB:
                return True
            if m in (STARTUP, LOGIN):
                stay = self.login_tick(stay)
                time.sleep(2.0)
                continue
            elif m in (ADVENTURE, GAME_MODE, TOURNAMENT):
                # 卡组页按一次「返回」只是退到上一级（还是 TOURNAMENT），要退两级才回主界面。
                # **不能按 ESC**：对局外 ESC 打开的是"游戏菜单(选项/退出)"弹窗，而且再按
                # 也不会关掉它 —— 真机实证：连续按 ESC 把菜单弹出来卡了 40 多轮。
                # 弹窗都是"点外面就关"，所以隔几轮点一次中间空白处把它点掉。
                if back_tries and back_tries % 5 == 0:
                    print("[nav] 可能压着弹窗/菜单，点中间空白处", flush=True)
                    self.click_ratio(0.50, 0.62)
                    time.sleep(0.5)
                self.click(coords.MODE_BACK)
                back_tries += 1
                time.sleep(0.6)
            elif m == GAMEPLAY:
                # **不自动认输**：认输是对局里的破坏性动作，只能由使用者决定。
                # 分两种情况：
                #   * 对局已结束 / 还没开局 -> 只是"结算界面挡路"，点「点击继续」离开即可；
                #   * 正在对局中 -> 拒绝离开，打印一句，让使用者自己决定（或传 --concede）。
                st = self.sync.pump().game
                if st.finished or not st.started:
                    print("[nav] 对局已结束，点「点击继续」离开结算界面", flush=True)
                    self.click_ratio(0.50, 0.93)
                    time.sleep(1.5)
                else:
                    print("[nav] 当前正在对局中：不自动认输（要认输请在命令行加 --concede）",
                          flush=True)
                    return False
            time.sleep(0.8)
        return False

    # ---------------- 练习 ----------------
    def go_practice(self, timeout: float = 240.0) -> bool:
        self._fresh()
        deadline = time.time() + timeout
        stay = 0
        while time.time() < deadline:
            m = self.sync.pump().mode
            if m == GAMEPLAY:
                print("[nav] 已进入对局")
                return True
            if m in (STARTUP, LOGIN):
                stay = self.login_tick(stay)
                time.sleep(2.0)
                continue
            elif m == HUB:
                self.click(coords.OTHER_MODE)
            elif m == GAME_MODE:
                self.click(coords.OTHER_ADVENTURE)
                self.click(coords.OTHER_ADVENTURE_CHOOSE)
            elif m == ADVENTURE:
                # 作者 AdventureModeStrategy.afterEnter 的固定点击序列
                self.click(coords.ADV_PRACTICE)
                self.click(coords.ADV_CHOOSE)
                self.click(coords.PREV_DECK_PAGE)
                self.click(coords.ADV_START)
                self.click(coords.ADV_FIRST_HERO)
                self.click(coords.ADV_START)
            else:
                self.click(coords.MODE_BACK)
            time.sleep(1.0)
        print("[nav] 超时")
        return False

    # ---------------- 传统对战（照作者 TournamentModeStrategy）----------------
    # 作者 afterEnter 的固定序列，一步都不能省、也不能"看情况跳过"：
    #   delayShort -> CHANGE_MODE_RECT.lClick()          # 切换模式按钮
    #   delayShort -> CASUAL_MODE_RECT.lClick()          # 休闲盾牌
    #   delayShort -> PREV_DECK_PAGE.lClick()            # 翻回第一页
    #   delayTiny  -> lClickDeckPos(3)                   # 一号位卡组，点 3 次
    #   delayShort -> START_RECT.lClick()                # 开始匹配
    # 匹配超时（作者 MATCH_MAXIMUM_TIME）：CANCEL -> delayLong -> ERROR -> reconnect -> 重来。
    MODE_RECTS = {
        "casual": coords.CASUAL_MODE,
        "standard": coords.STANDARD_MODE,
        "wild": coords.WILD_MODE,
    }
    MODE_TITLE_BOX = (0.34, 0.015, 0.56, 0.075)

    def _mode_refs(self) -> dict:
        from PIL import Image

        base = Path(__file__).resolve().parents[2] / "references" / "modes"
        refs = {}
        for name in ("casual", "wild", "standard"):
            f = base / f"{name}.png"
            if f.exists():
                refs[name] = Image.open(f).convert("RGB")
        return refs

    def read_mode(self) -> str | None:
        """读顶部标题，返回 casual / wild / standard（模板最近者）。

        狂野和休闲的底色都是暗红，颜色分不出来，只能比标题文字。
        """
        from PIL import Image, ImageChops

        refs = self._mode_refs()
        if not refs:
            return None
        shot = win.capture(self.hwnd, ".captures/mode_title.png")
        im = Image.open(shot).convert("RGB")
        w, h = im.size
        x0, y0, x1, y1 = self.MODE_TITLE_BOX
        cur = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
        best, best_d = None, 1e9
        for name, ref in refs.items():
            d = ImageChops.difference(cur, ref)
            px = list(d.getdata())
            score = sum(sum(p) for p in px) / (len(px) * 3)
            if score < best_d:
                best, best_d = name, score
        if best_d > 6.0:
            return None
        return best

    def select_deck(self, pos: int | None = None, count: int | None = None) -> None:
        """作者 selectDeck：先翻回第一页，再点卡组位 count 次。"""
        pos = pos or self.cfg.deck_pos
        count = count or self.cfg.deck_click_count
        print(f"[nav] 选择套牌：第 {pos} 号位，点 {count} 次")
        self.click(coords.PREV_DECK_PAGE)
        delay(TINY)
        rect = coords.deck_pos(pos)
        if rect is coords.INVALID:
            raise RuntimeError(f"卡组位 {pos} 越界（作者只有 1~9 号位）")
        for _ in range(count):
            self.click(rect)
            delay(TINY)

    def enter_tournament(self) -> None:
        """作者 TournamentModeStrategy.afterEnter。"""
        mode = self.cfg.run_mode.lower()
        if mode not in self.MODE_RECTS:
            raise RuntimeError(f"不支持的模式: {mode}（casual/standard/wild）")
        delay(SHORT)
        print("[nav] 点击切换模式按钮")
        self.click(coords.CHANGE_MODE)
        delay(SHORT)
        print(f"[nav] 切换至 {mode} 模式")
        self.click(self.MODE_RECTS[mode])
        delay(SHORT)
        # 校验：切完读一次标题，明确不是目标模式就再点一次（读不到不猜）
        mood = self.read_mode()
        print(f"[nav] 模式校验 -> {mood}")
        if mood is not None and mood != mode:
            print(f"[nav] 标题还是 {mood}，再点一次 {mode}")
            self.click(self.MODE_RECTS[mode])
            delay(SHORT)
            print(f"[nav] 模式校验(重试) -> {self.read_mode()}")
        self.select_deck()
        delay(SHORT)
        print("[nav] 开始匹配")
        self.click(coords.TOURNAMENT_START)

    def match_failed(self) -> None:
        """作者 generateTimer 的兜底：取消匹配 -> 错误弹窗 -> 重连。"""
        print("[nav] 匹配失败，取消后重连再匹配")
        self.click(coords.MODE_CANCEL)
        delay(LONG)
        self.click(coords.TOURNAMENT_ERROR)
        delay(SHORT)
        self.click(coords.RECONNECT)
        delay(SHORT)

    def close_overlay(self) -> bool:
        """关掉挡在主菜单上的「赛事中心」弹窗；关掉了返回 True。"""
        from .overlays import CLOSE_AT, tournament_modal_open

        img = win.grab_client(self.hwnd)
        if img is None or not tournament_modal_open(img):
            return False
        print("[nav] 主菜单被「赛事中心」弹窗盖住 -> 点关闭", flush=True)
        win.click_ratio(self.hwnd, CLOSE_AT[0], CLOSE_AT[1])
        time.sleep(0.8)
        return True

    def go_tournament(self, timeout: float = 240.0) -> bool:
        """进入对战模式并匹配：走作者那套动作序列，匹配不上就重来。"""
        self._fresh()
        # **新对局以 Power.log 的新段为准**：真机见过 screen 日志一直报 TOURNAMENT、
        # 实际游戏早就开了（2026-10-28 22:51:37 已 BEGIN_MULLIGAN，
        # LoadingScreen 22:51:40 也写了 GAMEPLAY，但导航 4 分钟没认出来，
        # 最后超时退出、白丢一局）。Power.log 是游戏自己写的，不会被界面缓存骗。
        seg0 = self.sync.power.seg_index
        deadline = time.time() + timeout
        stay = 0
        seq_done = False
        matched_at = 0.0
        last_poke = 0.0
        last_m = None
        stuck = 0
        ticks = 0
        while time.time() < deadline:
            m = self.sync.pump().mode
            ticks += 1
            g = self.sync.power.state
            if g.started and not g.finished and self.sync.power.seg_index > seg0:
                print("[nav] 已进入对局（Power.log 新段）", flush=True)
                return True
            if ticks % 8 == 1:
                print(f"[nav] go_tournament: mode={m} 第{ticks}次 seq_done={seq_done} "
                      f"(剩 {deadline - time.time():.0f}s)", flush=True)
            # 同一界面反复没变化 = 上面压着覆盖层（任务/商店/日志），退一层。
            # 已经在匹配中就不要再点返回了——那会把排队取消掉。
            # **不按 ESC**：对局外按 ESC 会把游戏菜单弹出来（真机实证，卡 40 多轮），
            # 所以这里只点「返回」/返回箭头，其它界面只打日志。
            if m == last_m and not seq_done:
                stuck += 1
                if stuck >= 4:
                    if m in (ADVENTURE, GAME_MODE, TOURNAMENT):
                        print(f"[nav] {m} 卡住 {stuck} 次，点返回")
                        self.click(coords.MODE_BACK)
                    elif m == JOURNAL:
                        print("[nav] 任务页，点返回箭头")
                        self.click_ratio(0.198, 0.858)
                    else:
                        print(f"[nav] {m} 卡住 {stuck} 次（这个界面没有可点的返回，继续等）")
                    stuck = 0
                    time.sleep(1.2)
            else:
                last_m = m
                stuck = 0

            if m == GAMEPLAY:
                print("[nav] 已进入对局")
                return True
            if m in (STARTUP, LOGIN):
                stay = self.login_tick(stay)
                time.sleep(2.0)
                continue
            if m == HUB:
                # 覆盖层（赛事中心）会盖住「传统对战」，但 screen 仍报 HUB：
                # 先看一眼是不是它，是就点关闭，再照常点对战（BUG 14）
                if self.close_overlay():
                    continue
                self.click(coords.TOURNAMENT_MODE)
            elif m == TOURNAMENT:
                if not seq_done:
                    self.enter_tournament()
                    seq_done = True
                    matched_at = time.time()
                    last_poke = matched_at
                else:
                    now = time.time()
                    # 「开始游戏时发生了错误」弹窗会一直挡着匹配：作者 generateTimer
                    # 也是点 ERROR_RECT（确定）。没弹窗时这一下落在卡组行之间的空隙。
                    if now - last_poke > 8.0:
                        print("[nav] 匹配中：点一次「确定」（可能弹了开赛错误）")
                        self.click(coords.TOURNAMENT_ERROR)
                        last_poke = now
                    if matched_at and now - matched_at > self.cfg.match_timeout:
                        self.match_failed()
                        seq_done = False
                        matched_at = 0.0
            elif m in (ADVENTURE, GAME_MODE):
                self.click(coords.MODE_BACK)
            time.sleep(1.0)
        print("[nav] 超时")
        return False

    # 旧名保留：只跑休闲（用户一直玩休闲）
    def go_casual(self, timeout: float = 240.0) -> bool:
        self.cfg.run_mode = "casual"
        return self.go_tournament(timeout=timeout)

    # ---------------- 认输 ----------------
    def concede(self, timeout: float = 30.0) -> bool:
        """ESC -> 点红色「认输」（作者就是一次点击，不重试）。

        对局已经结束（结算界面）时没有「认输」，直接点「点击继续」退出去，
        否则会一直按 ESC 空转（真机踩过：to_hub 里死循环）。
        """
        from PIL import Image

        from .modes import find_red_pill

        snap = self.sync.pump()
        if snap.mode != GAMEPLAY:
            raise RuntimeError("当前不是对局，拒绝认输")
        if snap.game.finished:
            print("[nav] 对局已结束，点「点击继续」退出结算界面")
            self.click_ratio(0.50, 0.93)
            time.sleep(2.0)
            return self.sync.wait_until(lambda s: s.mode != GAMEPLAY, timeout=20)

        win.force_front(self.hwnd)
        key_press(VK_ESCAPE)
        time.sleep(1.0)
        shot = win.capture(self.hwnd, ".captures/nav_menu.png")
        pt = find_red_pill(Image.open(shot))
        print(f"[nav] 认输按钮 {pt}")
        if not pt:
            return False
        self._click_pt(*pt)
        ok = self.sync.wait_until(lambda s: s.mode != GAMEPLAY, timeout=timeout)
        print("[nav] 认输生效" if ok else "[nav] 认输未生效")
        return ok

    def _click_pt(self, cx: int, cy: int) -> None:
        win.click_client(self.hwnd, cx, cy)

















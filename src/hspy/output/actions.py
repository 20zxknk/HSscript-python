"""输出层语义动作 —— 把"出牌/攻击/技能/结束回合"翻译成作者那套坐标 + 真实鼠标。

坐标来源全部是 coords.py（抄自 GameUtil.kt），动作语义照抄这几个作者函数，
一个都不许自己发明：

    GameRect.lClick(isCancel)                -> Actions.l_click
    GameRect.lClickMoveLClick(endRect, ...)  -> Actions.l_click_move_l_click
    GameRect.move(endRect)                   -> Actions.move_to
    GameUtil.cancelAction()                  -> Actions.cancel_action
    CommonCardAction.execPower(index)        -> Actions.play_card
    CommonCardAction.execPointTo(card)       -> Actions.point_to
    CommonCardAction.execAttack(card)        -> Actions.attack
    GameUtil.chooseDiscoverCard(i, size)     -> Actions.choose_discover
    GameUtil.lClickTurnOver()                -> Actions.end_turn
    DeckStrategyActuator.changeCard() finally-> Actions.confirm_mulligan
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import coords, win
from ..geometry import GameRect, GameWindow
from .mouse import SHORT, TINY, Mouse, delay

# 目标类型
TARGET_HERO = "hero"
TARGET_BOARD = "board"
TARGET_RIVAL_HERO = "rival_hero"
TARGET_ALLY_BOARD = "ally_board"
TARGET_ALLY_HAND = "ally_hand"


@dataclass(frozen=True)
class Target:
    kind: str  # hero / rival_hero / board(敌方场面) / ally_board(我方场面)
    index: int = 0
    size: int = 0

    @classmethod
    def hero(cls) -> "Target":
        return cls(TARGET_HERO)

    @classmethod
    def rival_hero(cls) -> "Target":
        return cls(TARGET_RIVAL_HERO)

    @classmethod
    def minion(cls, index: int, size: int) -> "Target":
        return cls(TARGET_BOARD, index, size)

    @classmethod
    def ally_minion(cls, index: int, size: int) -> "Target":
        return cls(TARGET_ALLY_BOARD, index, size)

    @classmethod
    def ally_hand(cls, index: int, size: int) -> "Target":
        return cls(TARGET_ALLY_HAND, index, size)


class Actions:
    def __init__(self, window: GameWindow, mouse: Mouse, probe_dir: str | None = None):
        self.w = window
        self.m = mouse
        # 作者 CommonCardAction.lastRect：上一次真正操作过的矩形。
        # 指向（pointTo）时优先从它出发，作者就是这么接的。
        self.last_rect: GameRect | None = None
        # 干跑/排查用：每次点击前截一张图上画个准星，看清到底点了哪
        self.probe_dir = Path(probe_dir) if probe_dir else None
        self._probe_n = 0
        # 动作日志用：本步实际点过的点（客户区/屏幕坐标），由引擎每步清空
        self.clicks: list[dict] = []

    # ---------------- 底层 ----------------
    def _client(self, rect: GameRect) -> tuple[int, int]:
        """作者 GameRect.getClickPos()：矩形内随机一点，**客户区**坐标。

        手牌用**矩形中心**而不是随机点：手牌矩形比牌略窄，随机点容易落到
        两张牌之间的缝里（真机实测：明明槽位对，点下去牌没被拿起来）。
        """
        if rect is coords.INVALID:
            raise ValueError("无效坐标（手牌/场面数量越界）")
        self.w.update()
        w, h = self.w.size
        x, y, rw, rh = rect.relative(w, h)
        # 落点：矩形内截断高斯 + 最近点去重（σ=6%，仍在牌/随从内侧，
        # 不会像"全矩形均匀随机"那样落到两张牌之间的缝里 —— 真机踩过）
        cx, cy = self.m.pick_point(x, y, rw, rh, sigma=0.06)
        return max(0, min(cx, w - 1)), max(0, min(cy, h - 1))

    def _guard(self, pt: tuple[int, int]) -> tuple[int, int]:
        """确认这个客户区落点真的属于游戏窗口，返回屏幕坐标（不属于就抛异常）。"""
        if self.m.dry_run:      # 干跑不碰真实鼠标，也就不需要校验落点归属
            return pt
        return win.guard_point(self.w.hwnd, pt[0], pt[1])

    def _click(self, pt: tuple[int, int], tag: str = "click", activate: bool = True) -> None:
        """真实点击（带落点校验）；干跑只打印。

        每次点击都把「客户区坐标 + 屏幕坐标」记到 self.clicks，
        这样脚本日志里就能写出到底点了屏幕哪个像素，和截图逐点对上。

        activate=False 是给"点-移-点"的第二次点击用的：**不能**再激活窗口，
        否则炉石收到 WM_ACTIVATE 会把已捡起的牌丢回手牌（真机实证）。
        """
        self._probe(tag, pt)
        if self.m.dry_run:
            self.m.left_click(pt)
            self.clicks.append({"tag": tag, "client": [pt[0], pt[1]], "screen": None})
            return
        sx, sy = win.click_client(self.w.hwnd, pt[0], pt[1], mouse=self.m, activate=activate)
        self.clicks.append({"tag": tag, "client": [pt[0], pt[1]], "screen": [sx, sy]})

    def _ensure_front(self) -> None:
        if not self.w.bring_to_front():
            win.force_front(self.w.hwnd)

    def _probe(self, tag: str, pt: tuple[int, int]) -> None:
        """把落点画在截图上（排查"到底点了哪一号位"）。只留前 12 张，别塞满硬盘。"""
        if not self.probe_dir or self._probe_n >= 24:
            return
        from PIL import Image, ImageDraw

        self._probe_n += 1
        path = self.probe_dir / f"{self._probe_n:02d}_{tag}.png"
        shot = win.capture(self.w.hwnd, path)
        im = Image.open(shot).convert("RGB")
        d = ImageDraw.Draw(im)
        cx, cy = pt
        d.line((cx - 26, cy, cx + 26, cy), fill=(255, 0, 0), width=3)
        d.line((cx, cy - 26, cx, cy + 26), fill=(255, 0, 0), width=3)
        d.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), outline=(0, 255, 0), width=3)
        im.save(path)
        print(f"[probe] {path.name} 点 ({cx},{cy})", flush=True)

    def cancel_action(self) -> None:
        """作者 GameUtil.cancelAction() = 右键点 prevPoint + delayTiny。"""
        self.m.right_click_prev()
        delay(TINY)

    def l_click(self, rect: GameRect, cancel: bool = True) -> None:
        """作者 GameRect.lClick(isCancel=True)。"""
        self._ensure_front()
        if cancel:
            self.cancel_action()
        self._click(self._client(rect), "lclick")

    def l_click_move_l_click(
        self,
        start: GameRect,
        end: GameRect,
        cancel: bool = True,
        start_settle: tuple[float, float] | None = None,
    ) -> None:
        """作者 GameRect.lClickMoveLClick(endRect)：点起点 -> 移动 -> 点终点。

        注意这不是拖拽（不按住左键），作者的出牌/攻击全是这么点的：
        第一次点击把牌/随从"拿起来"，移动过去，第二次点击落下。

        **两次点击之间绝不能重新激活窗口**：激活会触发 WM_ACTIVATE，
        炉石把正跟着鼠标的牌丢回手牌，第二次点击就落在空场面上 ——
        脚本看到的是"两次点击都发出去了、游戏一点反应没有"。
        真机实证：单点导航/开始都能成，所有"点-移-点"的出牌/攻击 0 次生效。
        """
        self._ensure_front()
        if cancel:
            self.cancel_action()
        sp = self._client(start)
        ep = self._client(end)
        left, top, _, _ = self.w.update()
        spp = (left + sp[0], top + sp[1])
        epp = (left + ep[0], top + ep[1])
        self._probe("mlc_start", sp)
        self._click(sp, "mlc_start", activate=True)
        # 捡牌落定：太短游戏还没把牌挂到鼠标上，太长会弹"放大预览"吃掉这一击
        delay((0.120, 0.180))
        self.m.human_move(spp, epp)
        delay((0.100, 0.160))
        self._probe("mlc_end", ep)
        self._click(ep, "mlc_end", activate=False)

    def move_to(self, rect: GameRect) -> None:
        """作者 GameRect.move(endRect)：从 last_rect 移到 rect（不点击）。"""
        start = self.last_rect if self.last_rect and self.last_rect is not coords.INVALID else None
        self._ensure_front()
        start_pt = self._guard(self._client(start)) if start is not None else None
        self.m.human_move(start_pt, self._guard(self._client(rect)))

    # ---------------- 对局动作 ----------------
    def end_turn(self) -> None:
        """作者 lClickTurnOver() = END_TURN_RECT.lClick()。"""
        self.l_click(coords.END_TURN)

    def confirm(self) -> None:
        self.l_click(coords.CONFIRM, cancel=False)

    def confirm_mulligan(self) -> None:
        """作者 DeckStrategyActuator.changeCard 的 finally：
        连点 3 次确认（间隔 delayShort）+ 点一次屏幕中心，收尾防点击被吞。"""
        self._ensure_front()
        for _ in range(3):
            self.l_click(coords.CONFIRM, cancel=False)
            delay(SHORT)
        self.l_click(coords.CENTER, cancel=False)

    def mulligan(self, replace_positions: list[int], hand_size: int) -> None:
        """按盒子的建议换牌，点击位置照作者 changeCard()：chooseDiscoverCard(i, handSize)。

        换牌面板的牌位就是"发现"那套 3/4 张布局，不是手牌位。
        """
        size = max(1, hand_size)
        for pos in replace_positions:
            self.choose_discover(max(0, pos - 1), size)   # 作者：delayShortMedium 由面板自己等
            delay((0.500, 0.800))                          # SystemUtil.delayShortMedium()
        self.confirm_mulligan()

    def choose_discover(self, index: int, options: int) -> None:
        """作者 GameUtil.chooseDiscoverCard(index, size)：>=4 张用四槽，否则三槽，越界夹住。"""
        rects = coords.discover(options)
        i = max(0, min(index, len(rects) - 1))
        self.l_click(rects[i])
        self.last_rect = rects[i]

    def choose_general(self, index: int, options: int) -> None:
        """「进行选择」类大牌面板（4 张）：用实测坐标表点，不走发现面板的表。"""
        rects = coords.CHOICE_GENERAL_4 if options >= 4 else coords.DISCOVER_3
        i = max(0, min(index, len(rects) - 1))
        self.l_click(rects[i])
        self.last_rect = rects[i]

    def choose_one(self, index: int) -> None:
        self.l_click(coords.CHOOSE_ONE[max(0, min(index, 1))])

    def keep_timeline(self) -> None:
        self.l_click(coords.TIMELINE[1])

    def rewind_timeline(self) -> None:
        self.l_click(coords.TIMELINE[0])

    def hero_power(self) -> None:
        """作者 execLClick（HERO_POWER 卡）：powerRect.lClick()。"""
        self.l_click(coords.MY_POWER)

    def trade(self, hand_index: int, hand_size: int) -> None:
        """可交易：把手牌拖/点到牌库（GameUtil.DECK_RECT）。"""
        self.l_click_move_l_click(coords.hand_card(hand_index, hand_size), coords.DECK)

    # ---------------- 出牌 / 指向 / 攻击 ----------------
    # 手牌上停太久会弹"放大预览"，点击会被吃掉 —— 点手牌统一用短停留
    HAND_SETTLE = (0.060, 0.100)

    def play_card(
        self,
        hand_index: int,
        hand_size: int,
        board_index: int = 0,
        board_size: int = 0,
        target: Target | None = None,
    ) -> None:
        """作者 CommonCardAction.execPower(index) + （有目标时）execPointTo。

        1. 手牌 -> 己方场面：lClickMoveLClick（点牌、移动、点落点）
        2. 盒子还给了目标：再 pointTo（把鼠标移到目标上点一下，不右键取消）
        """
        start = coords.hand_card(hand_index, hand_size)   # 作者原矩形，不改
        end = coords.my_minion(board_index, board_size)   # 作者场面矩形，不改
        self.l_click_move_l_click(start, end, start_settle=self.HAND_SETTLE)
        self.last_rect = end
        if target is not None:
            self.point_to(self.target_rect(target))

    def play_targeted(self, hand_index: int, hand_size: int, rect: GameRect) -> None:
        """指向法术：手牌直接落到目标矩形（作者 execPower(card) 的 endRect=目标）。"""
        self.l_click_move_l_click(
            coords.hand_card(hand_index, hand_size), rect, start_settle=self.HAND_SETTLE
        )
        self.last_rect = rect

    def point_to(self, rect: GameRect) -> None:
        """作者 CommonCardAction.execPointTo(card)：
        从 lastRect 移到目标矩形，然后在目标上点一下（isCancel=false）。"""
        if rect is coords.INVALID:
            return
        self.move_to(rect)
        self.l_click(rect, cancel=False)
        self.last_rect = rect

    def attack(
        self,
        attacker_index: int,
        attacker_size: int,
        target: Target,
        hero: bool = False,
    ) -> None:
        """作者 CommonCardAction.execAttack / execAttackHero：
        起点（英雄或场面位）lClickMoveLClick 到目标矩形。"""
        start = coords.MY_HERO if hero else coords.my_minion(attacker_index, attacker_size)
        end = self.target_rect(target)
        self.l_click_move_l_click(start, end)
        self.last_rect = end

    def target_rect(self, target: Target) -> GameRect:
        if target.kind == TARGET_HERO:
            return coords.MY_HERO
        if target.kind == TARGET_RIVAL_HERO:
            return coords.RIVAL_HERO
        if target.kind == TARGET_ALLY_BOARD:
            return coords.my_minion(target.index, target.size)
        if target.kind == TARGET_ALLY_HAND:
            return coords.hand_card(target.index, target.size)
        return coords.rival_minion(target.index, target.size)

    def ally_minion_rect(self, index: int, size: int) -> GameRect:
        return coords.my_minion(index, size)

    # ---------------- 房间/模式 ----------------
    def select_deck(self, pos: int) -> None:
        """选卡组：pos 从 1 开始（作者 DECK_POS_RECTS）。"""
        self.l_click(coords.PREV_DECK_PAGE)
        self.l_click(coords.deck_pos(pos))

    def start_match(self) -> None:
        self.l_click(coords.TOURNAMENT_START)

    def enter_practice(self) -> None:
        """练习模式：作者 AdventureModeStrategy.afterEnter 的点击序列。"""
        self.l_click(coords.ADV_PRACTICE)
        self.l_click(coords.ADV_CHOOSE)
        self.l_click(coords.PREV_DECK_PAGE)
        self.l_click(coords.ADV_START)
        self.l_click(coords.ADV_FIRST_HERO)
        self.l_click(coords.ADV_START)

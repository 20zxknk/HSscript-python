"""输入层：读炉石 Power.log，实时还原对局状态。

日志位置（作者的 GameLogInitializer 同款）：
    <炉石安装目录>/Logs/Hearthstone_<日期>/Power.log
每开一局游戏会新建一个 Hearthstone_<时间> 目录。

只做作者那套里真正用得到的子集：
    CREATE_GAME / FULL_ENTITY / SHOW_ENTITY / TAG_CHANGE
想补 BLOCK_START 里的"发现/抉择/换牌"再往外扩，见 TODO。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .event_types import (
    EV_BLOCK_END,
    EV_BLOCK_START,
    EV_CHOICE_DONE,
    EV_CHOICE_ENTITY,
    EV_CHOICE_HEADER,
    EV_ENTITY_FULL,
    EV_ENTITY_SHOW,
    EV_GAME_CREATE,
    EV_GLOBAL_TAG,
    EV_MULLIGAN,
    EV_OPTION,
    EV_OPTIONS_HEADER,
    EV_PLAYER,
    EV_PLAYER_NAME,
    EV_TAG,
    EV_TAG_BLOCK,
)
from .state import Entity, GameState, Player

# ---- 解析用正则 ----
RE_TS = re.compile(r"^[A-Z] (\d{2}:\d{2}:\d{2}\.\d+)\s")
RE_CREATE = re.compile(r"-\s+CREATE_GAME")
RE_FULL = re.compile(r"-\s+FULL_ENTITY - Creating ID=(\d+)(?: CardID=(\S+))?")
RE_SHOW = re.compile(r"-\s+SHOW_ENTITY - Updating Entity=(?:\[.*?id=(\d+).*?\]|(\d+))(?: CardID=(\S+))?")
RE_TAG = re.compile(r"-\s+tag=(\w+) value=(\S+)")
RE_TAGCHANGE = re.compile(r"-\s+TAG_CHANGE Entity=(\[[^\]]*\]|\S+) tag=(\w+) value=(\S+)")
RE_GAMEPLAYER = re.compile(r"-\s+PlayerID=(\d+),\s*PlayerName=(.+?)\s*$")
RE_PLAYER = re.compile(r"-\s+Player EntityID=(\d+)\s+PlayerID=(\d+)")
RE_IDENT = re.compile(r"- (?:Player|GameEntity) EntityID=(\d+)")
RE_CHOICE = re.compile(r"- (?:BLOCK_START|FULL_ENTITY).*?BlockType=TRIGGER.*?(?:DISCOVER|CHOOSE)")
RE_MULLIGAN = re.compile(r"-.*(?:mulligan|MULLIGAN)")

# CARDTYPE 枚举（炉石日志里的数字）
CARDTYPE = {4: "MINION", 5: "SPELL", 6: "WEAPON", 7: "HERO", 10: "HERO_POWER"}
ZONES = {"HAND", "PLAY", "DECK", "GRAVEYARD", "SECRET", "SETASIDE", "REMOVEDFROMGAME"}

# 需要换算成 bool 的 tag
BOOL_TAGS = {
    "TAUNT": "taunt",
    "DIVINE_SHIELD": "divine_shield",
    "FROZEN": "frozen",
    "STEALTH": "stealth",
    "EXHAUSTED": "exhausted",
}


class PowerLog:
    """增量 tail Power.log，变化时回调 on_state(state)。"""

    def __init__(self, hearthstone_dir: str | Path | None = None, poll: float = 0.25):
        if hearthstone_dir:
            self.hs_dir = Path(hearthstone_dir)
        else:
            try:
                self.hs_dir = self.guess_hearthstone_dir()
            except RuntimeError as e:
                # 离线测试 / CI 上没有炉石：先空着，等 pin_log() 指定日志。
                print(f"[powerlog] {e}（离线模式，等待 pin_log）", flush=True)
                self.hs_dir = Path(".")
        self.poll = poll
        self.state = GameState()
        # tag 数值解析失败的计数：必须在 __init__ 里就存在，
        # 否则不经 rebuild() 直接喂行的用法会在 _bad_value 里 AttributeError
        self.bad_values = 0
        self._fh = None
        self._path: Path | None = None
        self._last_create_ts: str = ""
        self._pending_entity: Entity | None = None
        self._seen_players: list[int] = []
        self._my_id_override: int = 0
        self._name_to_eid: dict[str, int] = {}   # 玩家名 -> 玩家实体 id
        self._name_to_pid: dict[str, int] = {}   # 玩家名 -> PlayerID
        self.seq: int = 0              # 段内事件序号（DSH 的 seq）
        self.seg_index: int = 0        # 第几段（每次 CREATE_GAME +1）
        self.seg_closed: bool = False  # 该段是否已 STATE=COMPLETE
        self._my_id_locked: bool = False
        self._player_names: dict[int, str] = {}
        self._pinned: Path | None = None
        self._record: list[str] | None = None      # 当前这一局的原生日志（录像）
        self._record_seg: int = 0
        self._tail: list[str] = []                   # 最近 300 行（含开局前的玩家信息）
        # 动作对账缓冲：引擎在每次点击前 mark()，点完读 since_mark()，
        # 只在**这一段新增日志**里找 PLAY/ATTACK 块 —— 比"整份日志前进了没有"准确得多
        # （实证：23:46 那三次出牌日志都前进了，其实是对手在动，一个 PLAY 块都没有）。
        self._action_buf: list[str] = []
        self._replaying = False     # rebuild() 重放整份日志时不要落录像
        self.records_dir: Path | None = Path(__file__).resolve().parents[3] / "records"

    # ---------------- 路径 ----------------
    @staticmethod
    def guess_hearthstone_dir() -> Path:
        """从正在运行的炉石进程推断安装目录。"""
        from ..config import detect_hearthstone_dir

        try:
            return detect_hearthstone_dir()
        except Exception as e:
            print(f"[powerlog] 配置/注册表推断炉石目录失败，改从进程枚举: {e}", flush=True)
        try:
            import ctypes
            from ctypes import wintypes

            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            arr = (wintypes.DWORD * 4096)()
            needed = wintypes.DWORD()
            psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed))
            count = needed.value // ctypes.sizeof(wintypes.DWORD)
            for pid in arr[:count]:
                h = kernel32.OpenProcess(0x1000, False, pid)
                if not h:
                    continue
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                        continue
                    if buf.value.lower().endswith("hearthstone.exe"):
                        return Path(buf.value).parent
                finally:
                    kernel32.CloseHandle(h)
        except Exception as e:
            print(f"[powerlog] 进程枚举找不到炉石（改用常见路径）: {e}", flush=True)
        for p in (r"C:\Program Files (x86)\Hearthstone", r"D:\Hearthstone", r"E:\Hearthstone"):
            if Path(p, "Hearthstone.exe").exists():
                return Path(p)
        raise RuntimeError("找不到 Hearthstone 目录，请传 --hs-dir")

    def pin_log(self, path: Path | str | None) -> None:
        """把日志钉死在这一份上：一局之内绝不再换文件，避免状态在多个会话间跳。"""
        self._pinned = Path(path) if path else None

    def latest_log(self) -> Path | None:
        """只认**最新会话**的 Power.log：那个会话目录里没有就返回 None。

        以前在全部会话里挑 mtime 最新的，客户端这次没写 Power.log 时会拿上一次
        会话的旧文件继续跑，mode 永远停在 GAMEPLAY（BUG 10）。
        """
        if getattr(self, "_pinned", None) and self._pinned.exists():
            return self._pinned
        logs = self.hs_dir / "Logs"
        if not logs.is_dir():
            return None
        dirs = [d for d in logs.iterdir() if d.is_dir()]
        if not dirs:
            return None
        newest = max(dirs, key=lambda d: d.stat().st_mtime)
        f = newest / "Power.log"
        return f if f.is_file() else None

    # ---------------- tail ----------------
    # 单局 Power.log 一般几 MB；超过这个值只追尾部，避免开新局时全量重读
    FULL_READ_LIMIT = 64 * 1024 * 1024

    def _open(self, path: Path) -> None:
        self._path = path
        self._fh = open(path, "r", encoding="utf-8", errors="replace")
        size = self._fh.seek(0, os.SEEK_END)
        if size <= self.FULL_READ_LIMIT:
            # 常规情况：从头读，才能拿到 CREATE_GAME 和整局实体
            self._fh.seek(0)
        else:
            self._fh.seek(size - 4096 * 256)

    def poll_once(self) -> GameState | None:
        """兼容旧接口：拉一次日志，有变化返回状态。"""
        seq = self.pump()
        return self.state if seq else None

    # ---------------- 事件流 ----------------
    def pump(self) -> int:
        """读出上次之后的新行并折叠进状态，返回当前段内事件序号。

        与 DSH 一致：**日志是唯一真相**，状态只是 fold 的结果；
        序号（seq）单调递增，消费者用「序号变化」判断状态是否真的推进了。
        """
        f = self.latest_log()
        if f is None:
            return self.seq
        if self._path != f:
            if self._fh:
                self._fh.close()
            self.state = GameState()
            self.seg_index += 1
            self.seg_closed = False
            self._open(f)
        if not self._fh:
            return self.seq
        lines = self._fh.readlines()
        if lines:
            for line in lines:
                self.seq += 1
                self._feed(line)
            self.state.refresh()
        return self.seq

    def wait_change(self, after_seq: int, timeout: float = 10.0) -> bool:
        """等到 seq > after_seq（即状态真的前进了一步），超时返回 False。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.pump() > after_seq:
                return True
            time.sleep(self.poll)
        return False

    def rebuild(self) -> GameState:
        """从段首（文件头）重放整份日志，得到确定性的状态。

        DSH 的 resume 就是这个语义：不修补半截状态，而是从日志重新投影。
        """
        self.state = GameState()
        self.seq = 0
        self.bad_values = 0        # 解析不了的 tag 数值条数（不静默）
        self.seg_index = 0
        self.seg_closed = False
        self._pending_entity = None
        self._seen_players = []
        self._name_to_eid = {}
        self._name_to_pid = {}
        if self._fh:
            self._fh.close()
        # 有 pinned 的日志就重放那一份；没有才用最新会话。
        # 之前这里无条件取 latest_log()，“重放这份日志”实际读的是别的文件，
        # 离线夹具/回放全被它带偏（BUG 18）。
        f = self._path if self._path else self.latest_log()
        if f is None:
            return self.state
        self._path = f
        self._fh = open(f, "r", encoding="utf-8", errors="replace")
        self._fh.seek(0)
        self._replaying = True
        try:
            for line in self._fh:
                self.seq += 1
                self._feed(line)
        finally:
            self._replaying = False
        self.state.refresh()
        return self.state

    def stale(self, max_idle: float = 30.0) -> bool:
        """日志停写超过 max_idle 秒（游戏卡住/窗口没了）。"""
        f = self.latest_log()
        if f is None:
            return True
        return time.time() - f.stat().st_mtime > max_idle


    def watch(self, on_state, idle_timeout: float = 120.0) -> None:
        """阻塞轮询；状态变化时调用 on_state(state)。"""
        last = time.time()
        while True:
            st = self.poll_once()
            if st is not None and st.started:
                on_state(st)
                last = time.time()
            if time.time() - last > idle_timeout:
                return
            time.sleep(self.poll)

    # ---------------- 动作对账 ----------------
    def mark(self) -> None:
        """开始记录"从此刻起新增的原始日志行"（供动作结果核对）。"""
        self._action_buf = []

    def since_mark(self) -> list[str]:
        """返回 mark() 之后新增的原始日志行（不含 mark 之前的历史）。"""
        return self._action_buf

    # ---------------- 解析 ----------------
    def _feed(self, raw: str) -> None:
        """投影：一行日志 -> 一个事件 -> 折叠进状态。

        与 DSH 的 event-sourced 一致：日志是唯一真相，state 只是 fold 的结果；
        分类逻辑抽到纯函数 `classify_line()`，事件流和投影共用同一份判定。
        """
        self._action_buf.append(raw)
        if len(self._action_buf) > 6000:
            del self._action_buf[:1000]
        kind, data = classify_line(raw)
        self._record_line(raw, kind)
        if kind is None:
            # **任何认不出的行都让裸 tag 的归属作废**（docs/reference/powerlog.md）。
            # 以前这里直接 return、pending 留着，下一批裸 tag 会写到很久以前的实体上。
            self._pending_entity = None
            return
        self._dispatch(kind, data)
        # **裸 `tag=X value=Y` 只属于紧挨着它的那个 FULL_ENTITY/SHOW_ENTITY/BLOCK_START**：
        # 中间只要插进任何别的行，就作废 pending，否则这些 tag 会写到一个**早已过期的
        # 实体**上。真机实证（test5）：03:11:34 建的幸运币 eid=69 之后pending 一直停在它，
        # 到 03:12:35 对手实体块里的 `tag=ZONE value=PLAY` / `tag=CONTROLLER value=1`
        # 全写到了这张币上 —— 币被当成已上场，手牌张数和落点全错。
        if kind not in (EV_TAG_BLOCK, EV_ENTITY_FULL, EV_ENTITY_SHOW, EV_BLOCK_START):
            self._pending_entity = None

    # ---------------- 录像（盒子 NeteaseHSRecord 的同款思路）----------------
    def _record_line(self, raw: str, kind: str | None) -> None:
        """把当前这一局的原生日志整段存下来。

        盒子能做到"回放"，靠的不是读游戏内存，而是**把 Power.log 整段留档再 fold**
        （heart_overlay_x64.dll 的 CreateFileW/ReadFile + NeteaseHSRecord 录像模块）。
        我们状态本来就是日志的 fold 结果，所以留档 = 随时能重建任意时刻的局面。
        """
        if kind == EV_GAME_CREATE:
            self._record = list(self._tail[-300:])
            self._record_seg = self.seg_index + 1
        self._tail.append(raw)
        if len(self._tail) > 300:
            del self._tail[:-300]
        if self._record is None:
            return
        self._record.append(raw)
        if len(self._record) > 400000:      # 防爆内存
            self._record = None

    def _adopt_ref_zone(self, ref: dict) -> None:
        """把方括号里声明的 zone / zonePos 落到实体上（只许"前进"）。

        允许的方向：
            DECK / SETASIDE / ""  -> HAND      （起手发牌、抽牌）
            HAND                  -> PLAY       （打出）
            HAND                  -> GRAVEYARD  （弃掉/阵亡）
        绝不接受的：PLAY -> HAND（出牌时旧括号把刚上场的牌写回手牌，
        这就是当初关掉 zone_hint 要防的回归）；HAND -> DECK（抽牌时括号是旧的）。
        """
        eid = ref.get("eid")
        if not eid:
            return
        ent = self.state.entities.get(eid)
        if ent is None:
            # 换牌/发现这些括号行**先于** FULL_ENTITY 出现（真机实证 test14：
            # 13:26:56.0 就有 `Entities[0]=[… id=42 zone=HAND …]`，
            # 而 42 这个实体要到后面才被创建）。先按括号建出来，
            # 否则 _adopt_ref_zone 一进来就 return，手牌永远是 DECK。
            ent = Entity(eid=int(eid))
            self.state.entities[int(eid)] = ent
        if ref.get("controller"):
            try:
                ent.controller = int(ref["controller"])
            except (TypeError, ValueError):
                pass
        zref = (ref.get("zone") or "").upper()
        if not zref:
            return
        ok = (
            (zref == "HAND" and ent.zone in ("", "DECK", "SETASIDE"))
            or (zref in ("PLAY", "GRAVEYARD") and ent.zone == "HAND")
        )
        if not ok:
            return
        before = (ent.zone, ent.zone_pos)
        if ref.get("card_id"):
            ent.card_id = ref["card_id"]
        ent.zone = zref
        if ref.get("zone_pos") is not None:
            ent.zone_pos = int(ref["zone_pos"])
        if before != (ent.zone, ent.zone_pos):
            print(f"[powerlog] 按括号落位: eid={eid} {before[0] or '?'}{before[1]}"
                  f" -> {ent.zone}{ent.zone_pos}", flush=True)
        self.state.hand_mutation_seq = self.seq
        self.state.move_entity(ent)

    def _bad_value(self, tag: str, value: str) -> None:
        """tag 的 value 不是整数：前 3 条打出来，留档时汇总，绝不静默。"""
        self.bad_values += 1
        if self.bad_values <= 3:
            print(f"[powerlog] tag={tag} 的 value 不是整数：{value!r}"
                  f"（累计 {self.bad_values}）", flush=True)

    def _flush_record(self) -> None:
        if getattr(self, "_replaying", False):
            # 重放历史整份日志时不要落盘：否则每读一遍过去 20 多局就写 20 多份录像
            self._record = None
            return
        if not self._record or not self.records_dir:
            return
        try:
            self.records_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            p = self.records_dir / f"{stamp}_seg{self._record_seg}.log"
            p.write_text("".join(self._record), encoding="utf-8", errors="replace")
            print(f"[powerlog] 本局日志留档: {p}", flush=True)
            if self.bad_values:
                print(f"[powerlog] 本局有 {self.bad_values} 条 tag 数值解析失败（见上）",
                      flush=True)
        except Exception as e:
            print("[powerlog] 录像写盘失败:", e)
        finally:
            self._record = None

    def _infer_my_id_from_names(self, pid: int, name: str) -> None:
        """本地玩家的名字在日志里是可见的，对手显示为 UNKNOWN HUMAN PLAYER。

        只有一方有真名时，那一方就是我（休闲/排名的情形）。
        两边都有名字（打旅店老板）则留给手牌可见性判断。
        """
        # 名字永远要记（判 CURRENT_PLAYER 全靠它），不能因为"已锁定"就早退
        self._player_names[pid] = name
        if self._my_id_override:
            return
        known = [
            p for p, n in self._player_names.items()
            if n and "UNKNOWN" not in n.upper()
        ]
        # 一方真名可见、另一方 UNKNOWN -> 真名那方是我（比手牌推断强，直接覆盖）
        if len(known) == 1 and len(self._player_names) >= 2:
            self.state.my_id = known[0]
            self._my_id_locked = True

    def _infer_my_id(self) -> None:
        """用「换牌期只有我的手牌可见」来确定本地玩家。

        对手手牌在开局没有 card_id（未揭示），所以 ZONE=HAND 且带 card_id 的实体
        只可能属于我。等到两个控制者都出现（对手亮牌）就放弃推断，保持原值。
        """
        if self._my_id_override or self._my_id_locked:
            return
        ctrls = {
            e.controller
            for e in self.state.entities.values()
            if e.zone == "HAND" and e.card_id and e.controller
        }
        if len(ctrls) == 1:
            pid = next(iter(ctrls))
            self.state.my_id = pid
            self._my_id_locked = True

    def _dispatch(self, kind: str, data: dict) -> None:
        if kind == EV_GLOBAL_TAG:
            tag, value = data["tag"], data["value"]
            if tag == "TURN":
                # **这是 GameEntity 的半回合计数**（1,2,3,4…），不等于"我们第几个回合"。
                # 真机实证：`TAG_CHANGE Entity=GameEntity tag=TURN value=3` 与
                # `Entity=玩家#0000 tag=TURN value=2` 同时出现 —— 后者才是我们的回合数，
                # 也就是盒子 turnNum 要对比的那个数（= (GameEntity.TURN+1)//2）。
                #
                # 只接受**往前走**的值：PowerTaskList 会把旧的 TURN 再放一遍
                # （test8：新一局 TURN=1 只有 tasklist 打了，而旧的 value=2 也会重放），
                # 用"大于当前值才生效"既不会把新局卡在 0，也不会被重放拽回去。
                try:
                    v = int(value)
                except ValueError:
                    self._bad_value(tag, value)
                    return
                if v > self.state.turn_global:
                    self.state.turn_global = v
                    # 我方回合数 = (半回合数+1)//2。实测与 `Entity=<我> tag=TURN`
                    # 逐条相等（G=1→1、3→2、5→3、8→4、10→5）。
                    self.state.turn = (v + 1) // 2
                    # **回合起点只认这一行**：它带"只许前进"守卫，tasklist 重放旧值会被滤掉。
                    # 选项块必须晚于它才算"真的轮到我操作"（my_action_window）。
                    self.state.turn_seq = self.seq
            elif tag == "STEP":
                # 换牌阶段以 GameEntity 的 STEP 为准：BEGIN_MULLIGAN 进来，
                # 任何别的 STEP（MAIN_READY/MAIN_START…）就是换牌结束。
                # 之前只在 BEGIN_MULLIGAN 时置 True、从不置回 False，
                # 导致换牌确认后还要再空点 8 下（正好点在起手牌上）。
                self.state.mulligan_open = value == "BEGIN_MULLIGAN"
            elif tag == "STATE" and value == "COMPLETE":
                self.state.finished = True
                self.seg_closed = True
                self._flush_record()
            return

        if kind == EV_OPTIONS_HEADER:
            # 一组新的选项 = 游戏重算了一遍"现在能做什么"，旧的手牌快照作废
            self.state.hand_options = {}
            self.state.hand_option_eids = {}
            self.state.option_errors = {}
            self.state.hand_options_seq = self.seq
            # 新快照 = 游戏重新算了一遍手牌：整体重建，消掉增量维护累积的漂移
            self.state.resync_hand()
            return

        if kind == EV_OPTION:
            ref = data.get("ref") or {}
            self.state.hand_options_seq = self.seq
            # 游戏**只在轮到谁操作时**才打选项块；`option 0 type=END_TURN` 就是
            # "现在轮到你动手"的权威信号（比 CURRENT_PLAYER 可靠：真机实测过
            # CURRENT_PLAYER 已翻到我们、界面还停在对手回合，那一整轮点击全被吞）。
            if (data.get("type") or "").upper() == "END_TURN":
                self.state.end_turn_option_seq = self.seq
            # 记下游戏对每个选项的"错误原因"（REQ_ENOUGH_MANA = 打不起）。
            # 盒子有时会推一张费用不够的牌，点下去游戏只会静默忽略（零日志），
            # 所以出牌前必须查这个，别白点。
            if ref.get("eid") and data.get("error"):
                self.state.option_errors[int(ref["eid"])] = data["error"]
            if ref.get("zone") == "HAND" and ref.get("controller") and ref.get("eid"):
                eid = int(ref["eid"])
                # **槽位只认实体身上的 ZONE_POSITION，不认选项括号里的 zonePos**：
                # 选项行是"打这一行时"的快照，括号里的 zonePos 可能比 tag 旧几毫秒。
                # 真机实证（2026-10-27 19:47:28）：先打
                #   TAG_CHANGE [id=61 …] tag=ZONE_POSITION value=4
                # 6ms 后的选项仍是 `mainEntity=[… id=61 zone=HAND zonePos=5 …]`，
                # 旧代码按 5 记进映射 → 改槽到 5 → 实际槽 4 是别的牌 →
                # `hand_slot` 每 6 步失败一次，整局卡死在同一步。
                ent = self.state.entities.get(eid)
                # 括号里的 zone 是旧状态：实体已经打到场上/进墓地时，它的 zonePos
                # 是**场面位置**，绝不能再当手牌槽位（否则手牌槽 1 会被写成刚打出的牌）。
                if ent is not None and ent.zone and ent.zone != "HAND":
                    return
                zp = ent.zone_pos if (ent is not None and ent.zone_pos >= 1) else 0
                if zp < 1:
                    zp = int(ref.get("zone_pos") or 0)
                if zp >= 1:
                    cid = ref.get("card_id") or (ent.card_id if ent is not None else "")
                    self.state.hand_options.setdefault(ref["controller"], {})[zp] = cid or ""
                    self.state.hand_option_eids.setdefault(ref["controller"], {})[zp] = eid
            return

        if kind == EV_GAME_CREATE:
            # DebugPrintGame 的名字（PlayerID=/PlayerName=）是**在 CREATE_GAME 之前**
            # 打的：清状态时要把它们带上，并立刻重新判一次"我是谁"，
            # 否则回放/新一局开头 my_id 会一直是 0。
            names = dict(self._player_names)
            self.state = GameState(started=True)
            self._pending_entity = None
            self.seg_index += 1
            self.seg_closed = False
            # 每局重新判定本地玩家（PlayerID 在不同局可能互换）
            self._my_id_locked = False
            self._player_names = names
            self._name_to_eid = {}
            self._name_to_pid = {}
            for pid, name in names.items():
                self._infer_my_id_from_names(pid, name)
            return

        if kind == EV_CHOICE_HEADER:
            st = self.state
            st.choice_open = True
            st.choice_player = data["player"]
            st.choice_type = data["type"]
            st.choice_min = data["min"]
            st.choice_max = data["max"]
            st.choices = []
            return

        if kind == EV_CHOICE_ENTITY:
            ref = data.get("ref") or {}
            self.state.choices.append(
                {
                    "index": data["index"],
                    "eid": ref.get("eid", 0),
                    "card_id": ref.get("card_id", ""),
                    "name": ref.get("name", ""),
                }
            )
            # **括号里的区域要落到实体上**：真机实证（test14 换牌）——
            # 起手牌在 GameState 里只有这种方括号行
            #     Entities[0]=[entityName=污亵 id=42 zone=HAND zonePos=1 cardId=BE_086 player=2]
            # （还有 m_chosenEntities[N]=… 与选项的 mainEntity=…），
            # 没有单独的 `tag=ZONE value=HAND`（那一句只在 PowerTaskList 段，被整行跳过）。
            # 不把括号区域用起来，我方手牌永远是 DECK：换牌阶段 hand_size_hint()=0，
            # 整轮换牌被跳过（bugs/07-mulligan-hand-unreadable）。
            self._adopt_ref_zone(ref)
            return

        if kind == EV_CHOICE_DONE:
            # 这一行若带着 ref（`DebugPrintEntitiesChosen … Entities[N]=[…]`），
            # 先把括号里的 zone/zonePos 落到实体上，再关面板。
            if data.get("ref"):
                self._adopt_ref_zone(data["ref"])
            self.state.choice_open = False
            self.state.choices = []
            return

        if kind == EV_PLAYER_NAME:
            pid, name = data["pid"], data["name"]
            self._infer_my_id_from_names(pid, name)
            p = self.state.players.setdefault(pid, Player(pid=pid))
            p.name = name
            self._name_to_pid[name] = pid
            for eid_, e in self.state.entities.items():
                if e.controller == pid and e.card_type != "MINION":
                    self._name_to_eid[name] = eid_
                    break
            return

        if kind == EV_PLAYER:
            eid, pid = data["eid"], data["pid"]
            if pid not in self._seen_players:
                self._seen_players.append(pid)
            if not self._my_id_override and self.state.my_id == 0:
                self.state.my_id = pid
            self.state.players.setdefault(pid, Player(pid=pid))
            e = self.state.entities.setdefault(eid, Entity(eid=eid))
            e.controller = pid
            return

        if kind == EV_ENTITY_FULL:
            ref = data.get("ref") or {}
            eid = ref.get("eid") or data.get("eid") or 0
            e = self.state.entities.setdefault(eid, Entity(eid=eid))
            self._merge_ref(e, ref)
            if data.get("card_id"):
                e.card_id = data["card_id"]
            self._pending_entity = e
            # 实体被（重新）创建 = 作者 Area.add 的时机：按当前 zone/zonePos 重新落位，
            # 顺带把列表里"同一个 eid 的旧对象"摘掉（否则占位实体会一直挂着手牌，
            # 把手牌张数顶多一格，整手点击矩形全体错位）。
            self.state.hand_mutation_seq = self.seq
            self.state.move_entity(e)
            if e.zone == "HAND":
                self.state.hand_entities_seq = self.seq
            return

        if kind == EV_ENTITY_SHOW:
            ref = data.get("ref") or {}
            eid = ref.get("eid") or data.get("eid") or 0
            e = self.state.entities.setdefault(eid, Entity(eid=eid))
            self._merge_ref(e, ref)
            if data.get("card_id"):
                e.card_id = data["card_id"]
            # **SHOW_ENTITY 也是裸 tag 的归属者**（docs/reference/powerlog.md）：
            # 任务/衍生牌登场是 `SHOW_ENTITY - Updating [ref] CardID=X` 后面跟一串
            # `tag=CONTROLLER/ZONE…`。以前这里不设 pending，这些 tag 会挂到**上一条**
            # 方块/实体上（真机实证 13:45:03：`tag=ZONE value=SETASIDE` 写到刚上场的
            # TIME_029 身上，把场上的龙又塞回 SETASIDE，场面少一只、攻击目标少一个）。
            self._pending_entity = e

            # 抽到的牌是先 `SHOW_ENTITY ... zone=DECK CardID=XXX` 揭晓、之后才补
            # `tag=ZONE value=HAND`。盒子的推荐在这两者之间就发了 —— 真机实测：
            # 盒子说"4 号位打 BE_207"，我们手牌只有 3 张（id=46 还挂在 DECK 上），
            # 于是断言把它拦下、白等一整回合。
            # **不能要求 cardType 已知**：日志里这一行常常还是 `cardType=INVALID`
            # （实证：id=44 SHOW_ENTITY CardID=BE_729，type 仍是 INVALID，
            #  下一小时才打 `zone=HAND zonePos=5 cardId=BE_729`）。
            if e.controller == self.state.my_id and e.zone == "DECK" and e.card_id:
                e.zone = "HAND"
            if e.zone == "HAND":
                self.state.hand_entities_seq = self.seq
                self.state.hand_mutation_seq = self.seq
            self.state.move_entity(e)
            return

        if kind == EV_MULLIGAN:
            # 这里**不能清实体表**：日志顺序是 CREATE_GAME -> （建实体）-> BEGIN_MULLIGAN，
            # 清在这里会把这一局刚建好的实体全抹掉，随后对手同 id 的实体就顶上来，
            # 我们手里的牌被写成对手的 zone（test5：幸运币 eid=69 变成 zone=PLAY）。
            self.state.mulligan_open = True
            self._infer_my_id()
            return

        if kind == EV_BLOCK_START:
            # `BLOCK_START … Entity=[ref]` 是裸 `tag=` 的归属者（docs/reference/powerlog.md）。
            # 以前不认这一行：方块里紧跟的 `tag=ZONE value=PLAY`（对手随从唯一的上场证据）
            # 没有归属者，整段被丢 —— 对手场面永远少人，攻击落点全错。
            ref = data.get("ref") or {}
            eid = ref.get("eid") or 0
            if not eid:
                name = (ref.get("name") or "").strip()
                if not name or name == "GameEntity":
                    return              # 方块挂在 GameEntity/玩家上：没有实体可归属
                eid = self._resolve_entity(name)
            if not eid:
                return
            e = self.state.entities.setdefault(eid, Entity(eid=eid))
            before = (e.zone, e.zone_pos)
            # PowerTaskList 的方括号是执行时的当前状态；GameState 的只当"首次见到"用，
            # 否则出牌块里的旧括号会把刚上场的牌写回手牌（见 EV_TAG 的注释）。
            self._merge_ref(e, ref, zone_hint=bool(data.get("tasklist")))
            self._pending_entity = e
            if (e.zone, e.zone_pos) != before:
                self.state.move_entity(e)
            return

        if kind == EV_BLOCK_END:
            self._pending_entity = None
            return

        if kind == EV_TAG:
            ref = data.get("ref") or {}
            tag, value = data["tag"], data["value"]

            # CURRENT_PLAYER 的 Entity 是「对局内玩家名」（如 玩家#0000），
            # 这个名字和 DebugPrintGame 登记的对手名（UNKNOWN HUMAN PLAYER）不同源，
            # 所以不查 pid，只判「是不是我的名字」。
            if tag == "CURRENT_PLAYER" and ref.get("name"):
                # **这里只更新"现在谁在动"，绝不动 turn_seq**：PowerTaskList 会把
                # 同一行原样重放（真机 2026-10-28 09:12:24：我方选项块 id=77 先到，
                # 30ms 后 CURRENT_PLAYER=1 又被重放一次；turn_seq 一涨，
                # `my_action_window` 立刻变假 → 整回合"等待中"，被烧绳）。
                # 回合起点改用带"只许前进"守卫的 GameEntity TURN 行（见 EV_GLOBAL_TAG）。
                if value != "1":
                    return
                me_name = self._player_names.get(self.state.my_id, "")
                if me_name and ref["name"] == me_name:
                    self.state.current_player = self.state.my_id
                elif self.state.my_id:
                    others = [p for p in self.state.players if p != self.state.my_id]
                    if others:
                        self.state.current_player = others[0]
                return

            eid = ref.get("eid") or self._resolve_entity(ref.get("name", "") or "")
            if not eid:
                # 玩家名（如 玩家#0000）上的 tag
                name = (ref.get("name") or "").strip()
                pid = self._name_to_pid.get(name)
                if pid and tag == "CURRENT_PLAYER":
                    self.state.current_player = pid if value == "1" else self.state.current_player
                return
            e = self.state.entities.setdefault(eid, Entity(eid=eid))
            # 方括号里是**块开始那一刻**的实体快照，不是"当前状态"：
            # 真机实证（Power.log 原文）——
            #   TAG_CHANGE Entity=[id=52 zone=HAND zonePos=5 cardId=TIME_029] tag=ZONE value=PLAY
            #   TAG_CHANGE Entity=[id=52 zone=HAND zonePos=5 ...]          tag=ZONE_POSITION value=2
            #   TAG_CHANGE Entity=[id=52 zone=HAND zonePos=5 ...]          tag=1196 value=1
            # 打出之后每一行都还带着 zone=HAND 的旧括号。若把括号无条件并进来，
            # 紧接着的下一行就会把刚设好的 zone=PLAY **写回 HAND** —— 表现就是
            # "牌打出去了、手牌里还挂着它，场面永远是空的"，于是盒子让打牌我们点空、
            # 盒子让攻击我们场上没人。所以 tag 行里的括号只当"首次见到这个实体时的
            # 初始值"用（zone/位置未知才填），已有状态一律以 TAG_CHANGE 本身为准。
            self._merge_ref(e, ref, zone_hint=False)
            self._apply_tag(eid, tag, value)
            # **括号里的 zone 只允许"前进"：HAND -> PLAY/GRAVEYARD**。
            # 真机实证（test11）：对手打出的随从，GameState 里只有带**旧括号**
            # （zone=HAND）的 tag 行（1196/JUST_PLAYED/NUM_TURNS_IN_PLAY…），
            # 而 `tag=ZONE value=PLAY` 只出现在 PowerTaskList 段（我们整行跳过）——
            # 结果对手的随从永远停在"手上"，rival_board 永远是空，
            # 盒子让攻击它时按"场上 1 个"排布局，点在两个随从中间的空隙上，连点 8 次。
            # 反向（PLAY -> HAND）**绝不接受**：那是出牌时旧括号把刚上场的牌写回手牌，
            # 正是当初关掉 zone_hint 要防的事。DECK 也不接受（抽牌时括号是旧的 zone=DECK）。
            zref = (ref.get("zone") or "").upper()
            if zref in ("PLAY", "GRAVEYARD") and e.zone == "HAND":
                print(f"[powerlog] 按括号前进: eid={eid} HAND -> {zref}"
                      f"（tag={tag} value={value}）", flush=True)
                e.zone = zref
                if ref.get("zone_pos") is not None:
                    e.zone_pos = int(ref["zone_pos"])
                self.state.hand_mutation_seq = self.seq
                self.state.move_entity(e)
            # 我自己的手牌变了（进/出/换位）就记一下序号：手牌张数要用"较新的那份"。
            # 只算自己的手牌，对手手牌上的 tag 更新很频繁，会把选项快照永远压成"旧的"。
            if tag in ("ZONE", "ZONE_POSITION", "CONTROLLER") or (
                ref.get("zone") == "HAND"
                and (not self.state.my_id or ref.get("controller") == self.state.my_id)
            ):
                self.state.hand_entities_seq = self.seq
            # 区域同步：ZONE / ZONE_POSITION 一变就把这张牌挪到新位置（作者 Area.add 语义）
            if tag in ("ZONE", "ZONE_POSITION", "CONTROLLER"):
                self.state.hand_mutation_seq = self.seq
            self.state.move_entity(self.state.entities.get(eid, e))
            return

        if kind == EV_TAG_BLOCK:
            if self._pending_entity is not None:
                e = self._pending_entity
                self._apply_tag(e.eid, data["tag"], data["value"])
                # FULL_ENTITY/SHOW_ENTITY 块里的 tag=ZONE/ZONE_POSITION 也是状态变更：
                # 必须触发重新落位，否则 zonePos 变成 0 的占位实体永远留在手牌列表里
                # （手牌张数被顶多一格 → 整手点击矩形错位）。
                if data["tag"] in ("ZONE", "ZONE_POSITION", "CONTROLLER"):
                    self.state.hand_mutation_seq = self.seq
                    self.state.move_entity(e)
            return

    @staticmethod
    def _merge_ref(e: Entity, ref: dict, zone_hint: bool = True) -> None:
        """把实体描述（方括号里的内容）合并进实体。

        zone_hint=False：只补"还不知道"的区域/位置，不覆盖已知状态。
        用于 TAG_CHANGE 行里的括号 —— 那是块开始时的快照，会落后于同一块里的
        ZONE/ZONE_POSITION 变更（见调用处注释）。
        """
        if not ref:
            return
        if ref.get("card_id"):
            e.card_id = ref["card_id"]
        if ref.get("zone") and (zone_hint or not e.zone):
            e.zone = ref["zone"]
        if ref.get("zone_pos") is not None and (zone_hint or e.zone_pos <= 0):
            e.zone_pos = ref["zone_pos"]
        if ref.get("controller"):
            e.controller = ref["controller"]
        ct = (ref.get("card_type") or "").upper()
        if ct in ("MINION", "HERO", "SPELL", "WEAPON", "HERO_POWER", "LOCATION",
                  "ENCHANTMENT", "BATTLEGROUND_SPELL", "BATTLEGROUND_MINION"):
            e.card_type = ct


    def _apply_tag(self, eid: int, tag: str, value: str) -> None:
        st = self.state

        # 全局 tag
        if tag == "TURN":
            # 玩家自己那条 `Entity=<名字> tag=TURN` **一律忽略**：
            # `st.turn` 只由 GameEntity 的半回合数算（turn_global -> (v+1)//2）。
            # 以前谁后写谁生效，玩家的那条会把 GameEntity 的值盖掉，回合数就随机错。
            return
        if tag == "CURRENT_PLAYER":
            # value=1 表示"该实体属于当前行动方"
            e = st.entities.get(eid)
            if value == "1":
                if e is not None and e.controller:
                    st.current_player = e.controller
                else:
                    st.current_player = eid
            return
        if tag == "STATE" and value == "COMPLETE":
            st.finished = True
            return

        e = st.entities.setdefault(eid, Entity(eid=eid))
        e.tags[tag] = value

        if tag == "ZONE":
            e.zone = value
        elif tag == "CONTROLLER":
            try:
                e.controller = int(value)
            except ValueError:
                self._bad_value(tag, value)
        elif tag == "CARDTYPE":
            # 日志里打的是**字符串**（MINION / SPELL / ENCHANTMENT / LOCATION …），
            # 少数老版本是数字。以前只认数字枚举，`ENCHANTMENT` 一律记成
            # "value 不是整数"（一局 19 条），附魔的类型永远空着，只能靠攻血猜。
            v = value.strip().upper()
            if v in ("MINION", "HERO", "SPELL", "WEAPON", "HERO_POWER", "GAME",
                     "ENCHANTMENT", "LOCATION", "PLAYER", "BATTLEGROUND_SPELL",
                     "BATTLEGROUND_MINION"):
                e.card_type = v
            elif v == "INVALID":
                pass                       # 未知就是未知，别写成"不是卡牌"
            else:
                try:
                    e.card_type = CARDTYPE.get(int(v), e.card_type)
                except ValueError:
                    self._bad_value(tag, value)
        elif tag == "ZONE_POSITION":
            try:
                e.zone_pos = int(value)
            except ValueError:
                self._bad_value(tag, value)
        elif tag in ("ATK", "HEALTH", "DAMAGE", "COST", "ARMOR", "NUM_ATTACKS_THIS_TURN"):
            try:
                v = int(value)
            except ValueError:
                self._bad_value(tag, value)
                return
            setattr(
                e,
                {
                    "ATK": "atk",
                    "HEALTH": "health",
                    "DAMAGE": "damage",
                    "COST": "cost",
                    "ARMOR": "armor",
                    "NUM_ATTACKS_THIS_TURN": "num_attacks",
                }[tag],
                v,
            )
        elif tag in BOOL_TAGS:
            setattr(e, BOOL_TAGS[tag], value == "1")

    # ---------------- 我的编号 ----------------
    def _resolve_entity(self, token: str) -> int:
        token = token.strip()
        if token.startswith("["):
            m = re.search(r"id=(\d+)", token)
            return int(m.group(1)) if m else 0
        if token == "GameEntity":
            return 1
        if token.isdigit():
            return int(token)
        return self._name_to_eid.get(token, 0)

    def set_my_id(self, pid: int) -> None:
        self._my_id_override = pid
        self.state.my_id = pid

    def reset_my_id(self) -> None:
        self._my_id_override = 0


def parse_entity_ref(token: str) -> dict:
    """解析 Power.log 里的实体引用。

    两种形式：
        Entity=123
        Entity=[entityName=UNKNOWN ENTITY [cardType=INVALID] id=59 zone=DECK
                zonePos=0 cardId= player=2]
    方括号里就是该实体的完整状态（zone / 位置 / 卡号 / 控制者 / 类型），
    很多卡从牌库进手牌只更新这里，没有单独的 ZONE tag —— 这是之前状态读错的主因。
    """
    token = (token or "").strip()
    d: dict = {}
    if token.startswith("[") and "id=" in token:
        m = re.search(r"entityName=(.*?) (?:\[cardType=|id=)", token)
        if m:
            d["name"] = m.group(1).strip()
        m = re.search(r"id=(\d+)", token)
        if m:
            d["eid"] = int(m.group(1))
        m = re.search(r"zone=(\w+)", token)
        if m:
            d["zone"] = m.group(1)
        m = re.search(r"zonePos=(\d+)", token)
        if m:
            d["zone_pos"] = int(m.group(1))
        m = re.search(r"cardId=([^\s\]]*)", token)
        if m:
            d["card_id"] = m.group(1)
        m = re.search(r"player=(\d+)", token)
        if m:
            d["controller"] = int(m.group(1))
        m = re.search(r"\[cardType=(\w+)\]", token)
        if m:
            d["card_type"] = m.group(1)
        return d
    if token.isdigit():
        d["eid"] = int(token)
    elif token:
        d["name"] = token
    return d


def classify_line(line: str) -> tuple[str | None, dict]:
    """纯函数：一行 Power.log -> (事件类型, 数据)。不碰任何状态。

    规则见 docs/reference/powerlog.md：

    * `PowerTaskList` 是方块执行时的**全量快照**，`GameState` 是**增量广播**：
      两者都要读。对手随从的 `tag=ZONE value=PLAY` 往往只在 PowerTaskList 里，
      以前整段跳过 ⇒ 对手场面永远少人、攻击落点全错。
    * 裸 `tag=X value=Y` 只属于紧邻的 `FULL_ENTITY` / `SHOW_ENTITY` / `BLOCK_START`。
    * `GameState` 方括号里的 `zone=` 是旧状态，具体值以 tag 为准（调用方处理）。
    """
    line = line.rstrip("\n")
    if not line:
        return None, {}
    tasklist = "PowerTaskList.DebugPrint" in line
    source = "tasklist" if tasklist else "game"

    if "BEGIN_MULLIGAN" in line:
        return EV_MULLIGAN, {}

    # 开局与玩家信息只在 GameState 里有（PowerTaskList 的 CREATE_GAME 是重放）
    if not tasklist:
        if RE_CREATE.search(line):
            return EV_GAME_CREATE, {}
        m = RE_GAMEPLAYER.search(line)
        if m:
            return EV_PLAYER_NAME, {"pid": int(m.group(1)), "name": m.group(2)}
        m = RE_PLAYER.search(line)
        if m:
            return EV_PLAYER, {"eid": int(m.group(1)), "pid": int(m.group(2))}

    # GameEntity 的全局标签（STEP / TURN / STATE）——换牌阶段的开关靠它，两种来源都有
    m = re.search(r"TAG_CHANGE Entity=GameEntity tag=(STEP|TURN|STATE) value=(\S+)", line)
    if m:
        return EV_GLOBAL_TAG, {"tag": m.group(1), "value": m.group(2), "source": source}

    # 其它 TAG_CHANGE：Entity 可能是数字、名字或方括号描述。
    # **PowerTaskList 里的也要认**：对手随从上场/死亡、手牌换位常常只有这里打全。
    m = re.search(r"TAG_CHANGE Entity=(.+?) tag=(\w+) value=(\S+)", line)
    if m:
        return EV_TAG, {
            "ref": parse_entity_ref(m.group(1)),
            "tag": m.group(2),
            "value": m.group(3),
            "source": source,
        }

    # DebugPrintEntityChoices：发现/抉择面板，候选按 Entities[i] 的顺序排，
    # 这就是"点第几个"的唯一权威来源（盒子给的也是它）。
    if "DebugPrintEntityChoices" in line:
        m = re.search(
            # **`TaskList=` 可能是空的**（ChoiceType=TARGET 就是这样：
            # `TaskList= ChoiceType=TARGET CountMin=1 CountMax=1`）。旧正则写死
            # `TaskList=\d+`，整条 header 匹配不上 → choice_open 永远假 →
            # 引擎把"选目标"面板当不存在，整回合等待、被烧绳（真机 10:25:18，
            # 克苏恩的凝视 要求选一个敌方随从，空等了 69 秒）。
            r"DebugPrintEntityChoices\(\) - id=(\d+) Player=(\S+) TaskList=\S* "
            r"ChoiceType=(\w+) CountMin=(\d+) CountMax=(\d+)",
            line,
        )
        if m:
            return EV_CHOICE_HEADER, {
                "id": int(m.group(1)),
                "player": m.group(2),
                "type": m.group(3),
                "min": int(m.group(4)),
                "max": int(m.group(5)),
            }
        m = re.search(r"Entities\[(\d+)\]=(\[.*?\]|\S*)\s*$", line)
        if m:
            return EV_CHOICE_ENTITY, {"index": int(m.group(1)), "ref": parse_entity_ref(m.group(2))}
        return None, {}

    if "DebugPrintEntitiesChosen" in line:
        # **"已选中的实体" 既是"选择结束"，也带着实体的完整方括号状态**：
        # 真机实证（test14 换牌）——
        #   GameState.DebugPrintEntitiesChosen() -   Entities[0]=[entityName=污亵 id=42
        #       zone=HAND zonePos=1 cardId=BE_086 player=2]
        # 起手牌**只有这一种行**能告诉我们"它在手牌第几格"（没有单独的 tag=ZONE value=HAND）。
        # 旧规则把整块当 EV_CHOICE_DONE 直接 return，括号里的 zone=HAND 一起丢掉 ——
        # 换牌阶段 hand_size_hint() 恒为 0，整轮换牌被跳过（bugs/07）。
        m = re.search(r"(?:m_chosenEntities|Entities)\[(\d+)\]=(\[.*?\]|\S*)\s*$", line)
        if m:
            return EV_CHOICE_DONE, {"ref": parse_entity_ref(m.group(2))}
        return EV_CHOICE_DONE, {}

    # FULL_ENTITY：Creating ID=84 CardID=... / Updating [ref] CardID=...
    # **两种 Updating 形式都要认**（docs/reference/powerlog.md）：
    #   GameState:    FULL_ENTITY - Updating Entity=43 CardID=…
    #   PowerTaskList: FULL_ENTITY - Updating [entityName=… id=43 …] CardID=…
    # 后者没有 `Entity=` 前缀，旧正则一条都解析不到，方块里的状态全丢。
    m = re.search(r"FULL_ENTITY - Creating ID=(\d+) CardID=(\S*)", line)
    if m:
        return EV_ENTITY_FULL, {"eid": int(m.group(1)), "card_id": m.group(2),
                                "source": source}
    m = re.search(r"(FULL_ENTITY|SHOW_ENTITY) - Updating (.+)$", line)
    if m:
        ev = EV_ENTITY_SHOW if m.group(1) == "SHOW_ENTITY" else EV_ENTITY_FULL
        rest = m.group(2).strip()
        card = ""
        cm = re.search(r"\s+CardID=(\S*)\s*$", rest)
        if cm:
            card = cm.group(1)
            rest = rest[:cm.start()].strip()
        if rest.startswith("Entity="):
            rest = rest[len("Entity="):].strip()
        return ev, {"ref": parse_entity_ref(rest), "card_id": card, "source": source}

    # BLOCK_START：裸 tag 的归属者（`Entity=` 后面可能是方括号、名字或数字）
    m = re.search(
        r"BLOCK_START BlockType=(\w+) Entity=(.+?)"
        r"(?: EffectCardId=| EffectIndex=| Target=| PlayerID=|$)", line)
    if m:
        return EV_BLOCK_START, {"ref": parse_entity_ref(m.group(2)),
                                "type": m.group(1), "source": source}

    if "BLOCK_END" in line or "HIDE_ENTITY" in line:
        return EV_BLOCK_END, {}

    # DebugPrintOptions：游戏自己把"当前能做的事"列了一遍，手牌也在里面
    # （含 ZONE_POSITION），盒子读的就是它 —— 手牌槽位以它为准。
    if "DebugPrintOptions" in line:
        m = re.search(r"DebugPrintOptions\(\) - id=(\d+)", line)
        if m:
            return EV_OPTIONS_HEADER, {"id": int(m.group(1))}
        m = re.search(r"option (\d+) type=(\w+) mainEntity=(\[.*?\]|\S*) error=(\S+)", line)
        if m:
            return EV_OPTION, {
                "index": int(m.group(1)),
                "type": m.group(2),
                "ref": parse_entity_ref(m.group(3)),
                "error": m.group(4),
            }
        return None, {}

    m = RE_TAG.search(line)
    if m:
        return EV_TAG_BLOCK, {"tag": m.group(1), "value": m.group(2)}

    return None, {}








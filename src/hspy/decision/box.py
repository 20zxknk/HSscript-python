"""决策层：完全依赖盒子（HSAng 推荐）——通过作者那套 frida 内存桥拿推荐。

协议和作者插件里的一模一样（见 su-discard-warlock-box-v4-strategy 的
ensureBridgeRunning/callBridge）：

    python -u recommendation_server.py     # 子进程
    向 stdin 写 "SCAN\n"
    从 stdout 读一行 JSON：{"plans":[...], "raw_rec": {...}|null, "timestamp":"..."}

每个 plan 的字段（作者插件消费的就是这些）：
    plan              "A" / "B" ...
    action            play_minion / hero_skill / minion_attack / end_turn / replace ...
    raw_action        choice / mulligan / ...
    hand_position     手牌位（0 基）
    board_position    上场位置
    target            board / hero / ...
    target_position   对方随从位（按 ZONE_POSITION）
    target_card_id / card_name / card_id / option_id / ai_win_rate
    mulligan_positions

决策层**不做任何自己的判断**，盒子给什么就执行什么——这是本项目的硬约束。
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Plan:
    action: str = ""
    plan: str = "A"
    raw_action: str = ""
    hand_position: int | None = None
    board_position: int | None = None
    # 默认必须是"没有目标"：以前默认 "board"，而 _target() 把 "board" 当**敌方场面**，
    # 于是任何没写 target 的方案（盒子少给一个字段、或单测里直接构造）都会变成
    # "指向敌方场面"。盒子正常会显式给 null，这里只是把地雷拆掉。
    target: str = ""
    target_position: int | None = None
    target_card_id: str = ""
    card_name: str = ""
    card_id: str = ""
    option_id: int | None = None
    ai_win_rate: float | None = None
    mulligan_positions: list[int] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, d: dict) -> "Plan":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        known.pop("extra", None)
        return cls(**known, extra={k: v for k, v in d.items() if k not in known})


class BridgeError(RuntimeError):
    pass


class BoxBridge:
    """盒子推荐桥。一次只允许一个实例（脚本自己用 lock 文件兜底）。"""

    def __init__(
        self,
        script: str | Path = "recommendation_server.py",
        python: str = "python",
        cwd: str | Path | None = None,
        timeout: float = 15.0,
        echo_stderr: bool = True,
    ):
        self.script = Path(script)
        self.python = python
        self.cwd = Path(cwd) if cwd else self.script.parent
        self.timeout = timeout
        self.echo_stderr = echo_stderr
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._last_raw: str = ""

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        if not self.script.exists():
            raise BridgeError(f"找不到推荐桥脚本: {self.script}")
        self._proc = subprocess.Popen(
            [self.python, "-u", self.script.name],
            cwd=str(self.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True, name="bridge-out")
        self._reader.start()
        threading.Thread(target=self._read_stderr, daemon=True, name="bridge-err").start()
        # 作者也是读两行做 init/ready 握手
        self._handshake()

    def _handshake(self) -> None:
        """读到 `{"status":"ready"}` 为止。

        桥启动会打**两行**：`{"status":"loading"}` 和 `{"status":"ready"}`。
        以前这里只读一行，于是队列里永远多一行，**之后每次 SCAN 读到的都是上一次的应答**
        —— 真机实证（test9）：03:36:18.267 的查询拿到 03:36:12.498 构建的 payload，
        而盒子在 03:36:12.806 已经给了新的 `play TIME_025`，我们直到 03:36:40.511 才读到。
        表现就是"拿过期推荐当当前推荐"，还以为是盒子/桥缓存的问题。
        """
        deadline = time.time() + self.timeout
        seen = 0
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise BridgeError(f"推荐桥启动握手超时（{self.timeout}s 没等到 ready）")
            line = self._readline(timeout=left)
            if line is None:
                raise BridgeError(f"推荐桥启动握手超时（{self.timeout}s 没等到 ready）")
            txt = line.strip()
            if not txt:
                continue
            try:
                obj = json.loads(txt)
            except json.JSONDecodeError:
                seen += 1
                print(f"[bridge] 握手期非 JSON 行（第 {seen} 行）: {txt[:80]}", flush=True)
                continue
            status = (obj.get("status") or "").lower()
            if status == "ready":
                return
            seen += 1
            print(f"[bridge] 握手期状态行: status={status or '?'}", flush=True)

    def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _read_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        for line in self._proc.stderr:
            if self.echo_stderr:
                print(f"[bridge] {line.rstrip()}", file=sys.stderr)
            if "无法获取桥接单实例锁" in line:
                self._lines.put(None)

    def _readline(self, timeout: float) -> str | None:
        try:
            return self._lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def __enter__(self) -> "BoxBridge":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------------- 查询 ----------------
    def scan(self) -> list[Plan]:
        if not self._proc or self._proc.poll() is not None:
            self.start()
        assert self._proc and self._proc.stdin
        try:
            self._proc.stdin.write("SCAN\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise BridgeError(f"桥接写入失败: {e}") from e

        # **必须读到带 "plans" 的那一行**：桥的输出里还可能混着 status/ready 之类的行，
        # 读错一行就会永远错位一轮（每次拿到的都是上一次的应答）。
        payload = None
        for _ in range(4):
            line = self._readline(self.timeout)
            if line is None:
                raise BridgeError(f"桥接响应超时({self.timeout}s)")
            txt = line.strip()
            if not txt:
                continue
            try:
                obj = json.loads(txt)
            except json.JSONDecodeError as e:
                self._last_raw = txt
                raise BridgeError(f"桥接返回非 JSON: {txt[:200]}") from e
            if "plans" in obj:
                payload = obj
                self._last_raw = txt
                break
            print(f"[bridge] 跳过非应答行: {txt[:80]}", flush=True)
        if payload is None:
            raise BridgeError("桥没有返回 SCAN 应答（连续 4 行都不是 plans 结构）")
        # 盒子每条推荐都属于某个"状态"（turnNum/optionId）；记下来，
        # 供引擎判断"这条推荐是不是当前状态的"，避免执行过期推荐。
        self.last_rec = payload.get("raw_rec") or {}
        return [Plan.from_json(p) for p in payload.get("plans") or []]

    @property
    def last_turn_num(self) -> int | None:
        rec = getattr(self, "last_rec", None) or {}
        v = rec.get("turnNum")
        return int(v) if isinstance(v, (int, float)) else None

    @property
    def last_option_id(self) -> int | None:
        rec = getattr(self, "last_rec", None) or {}
        v = rec.get("optionId")
        return int(v) if isinstance(v, (int, float)) else None

    @property
    def last_raw(self) -> str:
        return self._last_raw


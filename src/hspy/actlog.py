"""可对账的动作日志：每一步都记下"脚本怎么想 / 点了哪个像素 / 日志有没有反应"。

为什么要它（实测教训）：
    之前只有 stdout 的中文行，出了问题无法回答三个基本问题——
    ① 这一步是盒子的哪条方案（A/B/C 里的哪条）、参数是什么；
    ② 我们到底点了屏幕哪个像素（客户区坐标 + 屏幕坐标）；
    ③ 点完之后 Power.log 有没有对应的变化（没有 = 点了没生效）。
    于是只能靠猜。这个模块把三件事写进同一行 JSONL，并且带上 Power.log 的
    `seq`（事件序号）与 `version`（全局版本号），可以直接和日志逐条对账。

格式（每行一个 JSON）：
    {
      "t": "2026-10-24T21:04:20.123",   # 本地时间
      "turn": 3, "my_turn": true,
      "seq_before": 123, "ver_before": 45,
      "plan": {"action": "play", "card_id": "BE_207", "hand_position": 4,
               "board_position": 1, "target": null, "target_position": null},
      "plans_in_batch": 1,              # 这一批盒子给了几个方案（我们只做第 1 个）
      "resolved": {"hand_slot": 4, "hand_size": 5, "board_index": 0,
                   "board_size": 0, "target": null},
      "clicks": [{"tag": "hand", "client": [900, 800], "screen": [912, 838]}],
      "seq_after": 126, "ver_after": 46,
      "effect": true,                   # 日志是否发生了新事件
      "note": ""
    }

用法：
    from hspy.actlog import ActionLog
    log = ActionLog(Path("logs/actions-20261024.jsonl"))
    log.write(...)
对账脚本：scripts/join_actions.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class ActionLog:
    def __init__(self, path: Path | None = None, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled and path is not None
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
            self._fh = self.path.open("a", encoding="utf-8")      # type: ignore[union-attr]

    def write(self, record: dict) -> None:
        if not self.enabled:
            return
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")  # type: ignore[union-attr]
        self._fh.flush()                                             # type: ignore[union-attr]

    def close(self) -> None:
        if self.enabled:
            try:
                self._fh.close()   # type: ignore[union-attr]
            except Exception as e:
                print(f"[actlog] 关闭动作日志失败: {e}", flush=True)

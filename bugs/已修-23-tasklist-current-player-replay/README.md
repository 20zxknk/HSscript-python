---
id: B-23
state: 已修
module: input.powerlog
stage: 我方回合
symptom_key: CURRENT_PLAYER 被 tasklist 重放，turn_seq 涨过选项块，整回合等待
patterns: ["等待中 cur=我", "局面 60s 未动"]
root_cause: 回合起点用 CURRENT_PLAYER 行，没防 PowerTaskList 原样重放
related: [B-20]
reopened_count: 0
fp: b559029bdab3
fixed_at: 2026-10-28T10:15:00
---

# 23 `CURRENT_PLAYER` 被重放一次，整回合的"能操作"窗口又关上了

**状态：已修**

## 名称

`tasklist-current-player-replay`：把 `CURRENT_PLAYER` 行当"回合起点"（`turn_seq`），
而 `PowerTaskList` 会把同一行**原样再打一遍**。选项块到达 30ms 后重放一来，
`turn_seq` 涨过 `end_turn_option_seq`，`my_action_window` 变假 → 引擎整回合"等待中"，
直到烧绳把回合交出去。

## 现象

线上 2026-10-28 09:12（旧代码 r8 之后的第 1 局）第 9 回合：

```
[engine] 等待中 mode=GAMEPLAY turn=9 cur=2 me=2 hand=2 board=0
[engine] 局面 30s 未动，继续轮询 turn=9 cur=2 me=2 hand=2 board=0
[engine] 局面 60s 未动，继续轮询 turn=9 cur=2 me=2 hand=2 board=0
[engine] 对手回合 turn=10（GameTURN=19）        ← 我们一整回合没出手
```

`cur=2 me=2`（轮到我）却一直"等待中"，日志里没有任何点击。

## 触发条件

1. 我方回合开始，游戏打 `CURRENT_PLAYER=1` → `TURN=18` → `DebugPrintOptions id=77`；
2. 30ms 后 `PowerTaskList` 把同一段原样重放：`CURRENT_PLAYER=1`、`TURN=18`；
3. 旧代码在 `EV_TAG` 的 `CURRENT_PLAYER` 分支里无条件 `turn_seq = self.seq`；
4. 重放行的 seq 大于选项块 → `my_action_window` 假 → 整回合空转。

## 触发场景

2026-10-28 09:12:24，`records/20261028_091354_seg1.log`：

```
09:12:24.0435  GameState    [POS] CURRENT_PLAYER=1 … TURN=18
09:12:24.0501  GameState    DebugPrintOptions() - id=77      ← 选项到了
09:12:24.0842  PowerTaskList CURRENT_PLAYER=1 … TURN=18      ← 重放，把窗口关上
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/powerlog-0912-options-then-replay.log`：上面这几行的原文（09:12:23.9–24.2）；
- `logs/run-stall-0912.log`：引擎侧同一时刻的「等待中 / 局面 60s 未动」连续输出。

## 根因

```python
if tag == "CURRENT_PLAYER" and ref.get("name"):
    self.state.turn_seq = self.seq      # ← 每次出现都算"回合开始"
```

这条判据的初衷是"选项块必须晚于回合开始"，但 `CURRENT_PLAYER` 不是单调的
（重放、双方各一条 value=0/1），拿它当时间戳必然被后面的重放推翻。

## 修复

- 回合起点改成 `GameEntity TURN` 行：它本来就有"只接受前进值"的守卫
  （`v > turn_global`），重放同值会被滤掉；
- `CURRENT_PLAYER` 分支只更新 `current_player`，**不再动 `turn_seq`**；
- 新增回归用例（选项 → 重放 CURRENT_PLAYER/TURN → 断言窗口仍开）。

## 验证

```
tests/test_powerlog_rules.py
  OK   CURRENT_PLAYER/TURN 被 tasklist 重放不会关掉操作窗口
```

真机日志回放（同一份 seg1，09:12:24）：改后 `turn_seq=20891`（TURN 行），
选项 `end_turn_option_seq=21072`，重放后窗口保持 true。

线上：修复后连跑 4 局（live5b/c/final），未再出现「`cur=我` 却等待中」；
其中 2 局正常打完（1 胜 1 负），另 2 局是客户端冻结/批次预算到点（与本条无关）。

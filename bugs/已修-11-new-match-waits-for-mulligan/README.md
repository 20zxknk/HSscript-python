---
id: B-11
state: 已修
module: run.enter_match
stage: 进对局
symptom_key: 进对局判据要求换牌面板还开着，进晚了白等 60 秒再点继续
patterns: ["进对战（第 2 次", "进对战（第 3 次"]
root_cause: 判据含 mulligan_open
related: []
reopened_count: 0
fp: 3bbcbffc33ec
fixed_at: 2026-10-27T01:40:00

---

# 11 进对局的判据要求「换牌面板还开着」，进晚了就白等 60 秒再点「继续」搅局

**状态：已修**

## 现象

日志停在最后一行：

```
[nav] 已进入对局
```

之后一分钟没有任何输出，游戏里已经是我方回合（`你的回合` 横幅、4/4 费、手牌 6 张），
脚本什么都没做；60 秒后打一行 `没等到新对局…点继续退出后重试`，去点屏幕底部，
把对局搅成"点继续"循环。

## 触发条件

`run.py` 的 `enter_match()` 等新对局的判据里有 `s.game.mulligan_open`。
只要进得晚一点（换牌阶段已经过去、已经在打第一回合），它**永远为假**，
即使新对局段确实开始了，也判成"没等到新对局"。

## 触发场景

2026-10-27 01:34:20 `test/008-013209`：导航打出 `已进入对局` 后卡住；
01:34:43 的屏幕（截图已删除）显示已经是我方回合、
没有任何换牌面板。同批 007 也是 14 步后停在同一处。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/run-008-stuck-after-enter.log`（53 行，最后一行是 `[nav] 已进入对局`）
- `logs/SOURCES.txt`

## 根因

判据把「新对局」和「正在换牌」绑成一件事。实际上：
**新对局 = 新的 CREATE_GAME 段 + 已开局 + 未结束**；换牌只是可选的一步。

## 修复

```python
ok = nav.sync.wait_until(
    lambda s: nav.sync.power.seg_index > seg_before
    and s.game.started
    and not s.game.finished,
    timeout=60,
)
```

换牌要不要做，由主循环里 `if nav.sync.pump().game.mulligan_open:` 判断（已经有
「不在换牌阶段（接手残局），跳过换牌」的分支）。

## 验证

修完后进对局：`[run] 新对局已开始（段 N->N+1，换牌中）` 或直接进入主循环，
不再出现「已进入对局」后静默 60 秒。

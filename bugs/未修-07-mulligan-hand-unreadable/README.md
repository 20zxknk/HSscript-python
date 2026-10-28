---
id: B-07
state: 未修
module: engine.do_mulligan
stage: 换牌
symptom_key: 换牌阶段读不到起手张数，整轮换牌被跳过
patterns: ["等起手张数"]
root_cause: 依赖带卡号的 HAND 实体，实时追尾错过批次
related: []
reopened_count: 1

fp: e0e5c152ad5b


---

# 07 换牌阶段读不到起手张数，整轮换牌被跳过（还打了“换牌完成”）

**状态：未修**

> 原 B-07 标的「实机验证」被 2026-10-27 稳定版那一局推翻（15 次读不到起手张数），verify 与 fixed_at 一并作废。

## 名称

`mulligan-hand-unreadable`

## 现象

1. 换牌阶段引擎连续打 `等起手张数… n=0 hand=0 hint=0`（15 次，约 30 秒），
   然后 `起手张数仍读不到（实体 zone=HAND 且有卡号的 0 个），这一轮不换牌、不点确认`；
2. 紧接着仍打印 `[run] 换牌完成`（**假的**，什么都没做）；
3. 盒子在 `13:25:45` 就给过换牌建议：`replace [BE_086@槽1, CATA_725@槽2]`，
   之后每 0.5 秒重发同一份（约 40 次），我们一条都没执行；
4. 游戏侧：`MULLIGAN_STATE` 走到 `DONE`，我方手牌**没有任何 `ZONE value=DECK`**
   —— 四张全保留，盒子让换的两张没换。

## 触发条件

换牌阶段（`MULLIGAN` 期间）解析器读不到我方 `zone=HAND` 的实体。
本次具体情形：

- `[run] 钉死后重建: 实体=71 my_id=2 turn=0 hand=0`（重建后 `my_hand` 就是 0）；
- 而同一时刻 Power.log 里已经有 `zone=HAND player=2` 的实体：
  `污亵 BE_086`（eid 42）、`暗誓信徒 CATA_725`（eid 50）、`暮光龙卵 CATA_210`（eid 58）；
- 于是 `hand_size_hint()` 返回 0，`do_mulligan` 按“读不到就不猜”的规则直接 `return`
  —— 不点牌、不点确认，盒子建议整条丢弃。

## 触发场景

test14（casual，`2026-10-25 13:25:13` 那局）：

```
13:25:45.5  盒子: replace [BE_086@槽1, CATA_725@槽2]（choiceId=2）
13:26:37 ~ 13:26:56  盒子每 0.5 秒重发同一份，共约 40 次
13:26:2x    [run] 钉死后重建: 实体=71 my_id=2 turn=0 hand=0
13:26:3x    [engine] 等起手张数… n=0 hand=0 hint=0   ×15
13:26:56.1  游戏: 玩家#0000 MULLIGAN_STATE → DONE
13:27:0x    [engine] 起手张数仍读不到…这一轮不换牌、不点确认
            [run] 换牌完成            ← 与事实不符
13:27:06    我方手牌第一次出现 ZONE 变化：CATA_210 → PLAY（正常出牌）
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/mouse.jsonl.gz`（121896 字节）
- `logs/powerlog_story.md`（4446 字节）
- `logs/recommendations.jsonl`（75266 字节）
- `logs/SOURCES.txt`：以上文件各自的原始路径

文件名保持原样，未改；`SOURCES.txt` 里写了每个文件的出处。

## 根因（已查明）

两条叠加：

1. **起手牌只有 `DebugPrintEntitiesChosen` 一种行**：
   ```
   GameState.DebugPrintEntitiesChosen() -   Entities[0]=[entityName=污亵 id=42
       zone=HAND zonePos=1 cardId=BE_086 player=2]
   ```
   没有单独的 `tag=ZONE value=HAND`（那句只在 PowerTaskList 段，被整行跳过）。
2. `classify_line()` 把 `DebugPrintEntitiesChosen` 整块判成 `EV_CHOICE_DONE`
   （清空候选、`choice_open=False`）后**直接 return**，括号里的 `zone=HAND zonePos=1`
   被丢掉；于是实体永远停在 `DECK`，`hand_size_hint()` 恒为 0。

顺带确认：这一块既不是"选择结束"独占，也不是纯实体行 —— 它同时携带
"选择结束"和"被选中实体的完整状态"。

## 旧修复（已作废）

1. `DebugPrintEntitiesChosen` 的 `Entities[N]=[…]` / `m_chosenEntities[N]=[…]` 行
   在关闭面板之前，先把括号里的 `zone / zonePos / cardId / controller` 落到实体上
   （新helper `_adopt_ref_zone`，只许前进：`DECK/SETASIDE/"" -> HAND`、
   `HAND -> PLAY/GRAVEYARD`；拒绝 `PLAY -> HAND` 与 `HAND -> DECK`）。
2. 实体还不存在时按括号先建出来（这些行先于 `FULL_ENTITY` 出现）。
3. 面板仍然会被关闭（`choice_open=False`、清空 `choices`），不影响选择面板流程。

## 旧验证（已作废）

> 这一节的结论「修后能读到 4 张」只在那一种日志形态下成立。
> 2026-10-27 稳定版那一局（`evidence/stable-v01-r1`）连打 15 次
> `等起手张数… n=0 hand=0 hint=0`，把它推翻了。保留原文只为记录当时怎么误判的。


回放同一份 Power.log 到 13:26:58：

```
修前：hand_size_hint=0  len(my_hand)=0   实体 42/50/58 全是 zone=DECK
修后：hand_size_hint=4  len(my_hand)=4
      my_hand = [BE_086@1, CATA_725@2, CATA_210@3, BE_086@4]
      choice_open = False            ← 面板照常关闭
```

`tests/test_offline.py` 全绿。真机待验：换牌阶段应打出
`起手 4 张（换牌面板 4 槽布局）` 并按盒子替换槽 1、2。

## 证据（原始日志）

本目录 `logs/` 下的原始文件（可直接 grep）：

```
logs/mouse.jsonl.gz    ← test14\mouse.jsonl.gz
logs/recommendations.jsonl    ← test14\recommendations.jsonl
logs/powerlog_story.md    ← test14\powerlog_story.md
```

核对方式：在 `logs/` 里按 README 上的时间戳/卡号直接搜；三份文件（鼠标 / 盒子应答 / 游戏侧叙述）互相对照。

## 复发记录 #1（2026-10-27 13:48）

- 症状：稳定版跑的一局里 15 次「等起手张数… n=0」——所谓「实机验证」是假的
- 原始日志：`logs/reopen1-stable-v01-r1-err.log`, `logs/reopen1-stable-v01-r1-mouse.jsonl.gz`, `logs/reopen1-stable-v01-r1-recommendations.jsonl`, `logs/reopen1-stable-v01-r1-run.log`
- 来源：`evidence\stable-v01-r1`

状态已改回「未修」：这条修复在真机上没有生效，先别当已修看。

## 复发确认的根因（2026-10-27 13:44，证据 evidence/stable-v01-r1）

稳定版（v0.1）那一局里，换牌阶段连打 15 行：

```
[engine] 等起手张数… n=0 hand=0 hint=0
```

这说明「实机验证」是假的：test15 那次能读到起手张数，只是**那一种日志形态**能读到；
换成今天这种（后手、换牌实体落定晚）就完全读不到。

同时暴露出一个判定缺陷：`do_mulligan` 的判据取
`max(hand_size_hint, len(my_hand), 带卡号 HAND 实体的最大槽号)`，
而这三样在换牌早期都还是 0；真正能读出张数要等 `DebugPrintEntitiesChosen`
把起手张数打印出来（今天这局是 6 秒后才出现）。

**根因（待定位到具体一行）**：等待窗口里只看「实体」，没看「EntitiesChosen 里的
mulligan 张数」这条更早、更直接的信源。

## 合并说明

原 `未修-13-mulligan-hand-zero-again` 与本条是**同一缺陷**（module/stage/症状一致），
已合并到本条，日志一并放在 `logs/reopen1-…`。

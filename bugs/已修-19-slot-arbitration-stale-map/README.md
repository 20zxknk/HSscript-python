---
id: B-19
state: 已修
module: engine.play_match
stage: 出牌
symptom_key: 选项映射旧一拍时改到错槽，hand_slot 断言失败并每 6 步重试一次
patterns: ["slot_from_card", "FAIL:hand_slot"]
root_cause: 改槽只看选项映射，没有和手牌列表交叉验证
related: [B-06]
reopened_count: 0
fixed_at: 2026-10-27T19:35:00
fp: b77d61db3210
---

# 19 选项映射旧一拍就改错槽：hand_slot 断言失败，每 6 步重试一次

**状态：已修**

## 现象

第一局第 2 回合，出 TIME_026 时进入死循环：

```
[step 064] slot_from_card card=TIME_026 box_slot=2 used_slot=3
[step 065] FAIL:hand_slot slot=3 size=3 want=TIME_026 got=BE_726 hand=['BE_086','TIME_026','BE_726']
[step 070] slot_from_card card=TIME_026 box_slot=2 used_slot=3
[step 071] FAIL:hand_slot …
```

每 6 步重复一次，直到人工停掉这一局。

## 触发条件

1. 手牌是 `[BE_086, TIME_026, BE_726]`，盒子说 TIME_026 在**槽 2**（正确）；
2. `hand_option_eids`（游戏选项映射）比界面**旧一拍**，把槽 2 说成 BE_726、槽 3 说成 TIME_026；
3. BUG 06 加的裁决规则只看选项映射 → 认为盒子说错了 → 改到槽 3；
4. 槽 3 实际是 BE_726 → `hand_slot` 断言失败 → 下一轮重复同一条路。

## 触发场景

2026-10-27 19:20 起的两局验证（`test/r4`，参数化鼠标改完后的第一局）。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/run-r4-slot-from-card-loop.log`：从 `test/r4/stdout.log` 里摘出的
  `slot_from_card` / `FAIL:hand_slot` / `[?]` 行（原文件在 `test/r4/`，不入库）

## 根因

改槽的判据只依赖一个来源（选项映射），而它有滞后性。

## 修复

改槽必须**两个来源都点头**：选项映射与手牌列表都指向同一槽。

```python
alt = next((s for s in opt_hit
            if slot_card(s) == cid and (slots or {}).get(s) == cid), None)
```

不一致时保持盒子槽位——盒子读的是游戏内存里的 live zonePos，比我们这份快照新。

## 验证

```
tests/test_slot_arbitration.py
  OK   选项映射旧一拍时不改槽（用盒子的槽 2）
  OK   映射与列表都指向槽 3 时才改槽
  OK   没有选项映射时不动盒子槽位
```

真机待验：同一手牌下应看到直接点槽 2 成功，不再出现 `slot_from_card` + `FAIL:hand_slot`。

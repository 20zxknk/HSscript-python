---
id: B-20
state: 已修
module: input.powerlog
stage: 出牌
symptom_key: 选项括号 zonePos 旧一拍，hand_slot 每 6 步失败一次、整局卡死
patterns: ["FAIL:hand_slot", "slot_from_card"]
root_cause: 手牌槽位信了 DebugPrintOptions 括号里的 zonePos，而它是打这一行时的旧状态
related: [B-06, B-19]
reopened_count: 0
fp: cd382ff6123a
fixed_at: 2026-10-28T00:50:00
---

# 20 选项括号的 zonePos 旧一拍：`hand_slot` 每 6 步失败一次，整局卡死

**状态：已修**

## 名称

`option-zone-pos-stale`：`DebugPrintOptions` 的 `mainEntity=[… zonePos=…]` 是**打这一行时**
的快照；实体自己的 `tag=ZONE_POSITION` 可能已经先走了一步。按括号里的槽位改槽 →
点到别的牌 → `hand_slot` 断言失败 → 盒子继续推同一条 → 死循环。

## 现象

r8（3 局）里 `hand_slot` 失败 64 次 / `slot_from_card` 64 次；每 6 步一轮，同一手牌反复重试：

```
[step 054] plan_A action=play card=TIME_026 box_hand=4 ... hand=["BE_729","TLC_451","GAME_005","TIME_026","TLC_451"]
[step 055] box_rec_raw ... "ZONE_POSITION": 4 ...
[step 056] slot_from_card card=TIME_026 box_slot=4 used_slot=5
[step 057] FAIL:hand_slot slot=5 size=5 want=TIME_026 got=TLC_451
[step 058] wait_card_in_hand card=TIME_026 box_hand=4
```

盒子给的是**对的**（槽 4），是我们自己把槽改到了 5。

## 触发条件

1. 打出一张牌后，游戏先打 `TAG_CHANGE … tag=ZONE_POSITION value=4`（把 TIME_026 挪到槽 4）；
2. 6ms 后同一回合的选项块里，`mainEntity` 的括号**还是旧状态** `zonePos=5`；
3. `EV_OPTION` 把括号的 `zonePos` 记进 `hand_option_eids`（槽 5 → eid 61）；
4. `resolve_play_slot` 看到"盒子槽 4 的卡号 ≠ 盒子点名"，从选项映射里找到槽 5，
   改槽并记 `slot_from_card`；
5. `require_hand_slot` 拿 `my_hand` **列表下标**去比：列表第 5 个是 TLC_451 → 失败。

BUG 19 的"改槽要两个来源都点头"没能拦住：那两个来源（`hand_option_eids` 与
`hand_options`）**都来自同一份选项块**，一起旧、一起错，不是独立证据。

## 触发场景

2026-10-27 19:47:28，`records/20261027_195511_seg4.log`（r8 第 3 局）。
关键两行只差 6ms：

```
19:47:28.4939875 GameState.DebugPrintPower() - TAG_CHANGE Entity=[… id=61 zone=HAND zonePos=5 cardId=TIME_026 player=2] tag=ZONE_POSITION value=4
19:47:28.5000128 GameState.DebugPrintOptions() - option 3 type=POWER mainEntity=[entityName=续连熵能 id=61 zone=HAND zonePos=5 cardId=TIME_026 player=2] error=NONE
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/powerlog-1947-zone-position.log`：19:47:17–19:47:30 的 TIME_026 / id=61 / 选项行原文；
- `logs/actions-r8-step57.log`：动作日志 step 050–058（同一轮失败的全套输入/输出）；
- `logs/slot-map-before.log`：用**改前**代码回放到 19:47:29.816 的槽位映射
  （选项说槽 5 是 TIME_026、槽 2 还是已打出的 CATA_210）；
- `logs/slot-map-after.log`：同一时刻**改后**的映射（槽 4 = TIME_026、槽 5 = TLC_451，
  与盒子、与实体 zonePos 一致）。

## 根因

`input/powerlog.py` 的 `EV_OPTION` 分支用 `ref.get("zone_pos")`（方括号）当手牌槽位：

```python
zp = int(ref.get("zone_pos") or 0)
self.state.hand_option_eids.setdefault(pid, {})[zp] = eid
```

而 `docs/reference/powerlog.md` 的规则是：**方括号里的 zone/zonePos 是旧状态，
具体值只认 `tag=ZONE/ZONE_POSITION`**。这条规则当时只用在了 TAG_CHANGE 上，
漏了选项块。

## 修复

1. **槽位只认实体身上的 tag**：`EV_OPTION` 先取 `entities[eid].zone_pos`，
   只有实体还没有位置时才退回括号；实体已经不在手牌（`zone != HAND`）就直接跳过
   —— 已打出的牌括号里的 `zonePos` 是**场面位置**；
2. `GameState.my_hand` 改成按 `zone_pos` 排序（不再用增量插入顺序）；
3. 新增 `hand_slot_entities()` / `slot_cards()` / `slot_eid()`：
   "槽位上游戏声明过哪些卡号"，实体与选项两个来源都算数，但**谁也不否定谁**；
4. `verify.require_hand_slot` 改成问 `slot_cards(slot)`，不再看列表下标；
5. `engine._do_play` 查可用性/实体也用 `slot_eid()`。

## 验证

```
tests/test_powerlog_rules.py
  OK   选项括号 zonePos=5 不覆盖实体的 ZONE_POSITION=4
  OK   已上场的牌不会被选项括号拉回手牌槽
  OK   手牌列表按 ZONE_POSITION 排（槽位断言不再看列表下标）
  OK   幸运币算手牌（少了它整排点击会右移一格）
```

真机日志回放（同一份 `seg4`，19:47:29.816）：

```
改前：hand_options={1:BE_729,2:CATA_210,3:TLC_451,4:GAME_005,5:TIME_026,6:TLC_451}
      my_hand 列表 = [BE_729, TLC_451, GAME_005, TIME_026, TLC_451]
改后：hand_options={1:BE_729,2:TLC_451,3:GAME_005,4:TIME_026,5:TLC_451}
      my_hand = [(1,BE_729),(2,TLC_451),(3,GAME_005),(4,TIME_026),(5,TLC_451)]
      slot 4 / slot 5 = ["TIME_026"] / ["TLC_451"]
```

再用**改前卡死的那一步**走一遍引擎的槽位裁决（同一份日志、同一时刻）：

```
resolve_play_slot(hand_position=4, TIME_026) -> 槽 4，依据 box
[step 001] ok:hand_slot slot=4 size=5 want=TIME_026 got=TIME_026
           hand=['1:BE_729','2:TLC_451','3:GAME_005','4:TIME_026','5:TLC_451']
```

改前这一步会走 `slot_from_card` 改到槽 5、随即 `FAIL:hand_slot`；现在不改槽，断言直接过。

**真机待验**：同一手牌下应看到直接用盒子的槽 4、不再出现 `slot_from_card` + `FAIL:hand_slot`。

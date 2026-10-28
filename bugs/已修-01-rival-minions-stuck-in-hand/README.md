---
id: B-01
state: 已修
module: input.powerlog
stage: 对手出牌
symptom_key: 对手随从永远停在 HAND，rival_board 恒空
patterns: []
root_cause: TAG_CHANGE 的括号 zone 被丢弃
related: []
reopened_count: 0
fp: a08e292ec7fd
fixed_at: 2026-10-25T02:00:00

---

# 01 对手随从永远进不了 `rival_board`（停在“手上”）

**状态：已修**

## 名称

`rival-minions-stuck-in-hand`：对手打出的随从实体始终留在 `zone=HAND`，
`rival_board` 恒为空，导致“攻击敌方随从”的落点按**错误张数**计算。

## 现象

- 我方 `CATA_210` 攻击敌方 `战利品贮藏者`，连续 **8 次**点同一对坐标
  `(822,539) → (949,370)`，全部 `无 ATTACK 块`；Power.log 同期 `BlockType=ATTACK` 数量 **0**。
- 动作日志写的是 `我方列表=0 -> 第 1/1 格`：我们以为敌方场上只有 1 个随从。

## 触发条件

1. 对手打出一张随从（例：`id=17 战利品贮藏者`）；
2. GameState 段落里，这张随从**只有带旧括号 `zone=HAND`** 的 tag 行
   （`tag=1196` / `JUST_PLAYED` / `NUM_TURNS_IN_PLAY` 等），
   真正的 `tag=ZONE value=PLAY` 只出现在 `PowerTaskList` 段；
3. 我们的解析器：`PowerTaskList` 的非 TURN 行整行跳过（`classify_line` 返回 None），
   且 TAG_CHANGE 行括号里的 zone 被 `_merge_ref(..., zone_hint=False)` 丢弃。

→ 实体永远停在 `HAND`，`rival_board` 为空。
→ 盒子的 `opp-target.position` 只有序号，推不出总数；落点按“1 个随从”的中心算。

## 触发场景

test11（casual，`2026-10-25 12:59:56` 那局）：

```
13:02:04.1  GameState : BLOCK_START … id=17 zone=HAND zonePos=3（打出时的旧括号）
13:02:05.6  TaskList  : [战利品贮藏者 id=17 zone=PLAY zonePos=1]        ← 我们跳过
13:03:04.7  盒子      : minion_attack CATA_210 → opp-target 战利品贮藏者 position=1
13:03:09 ~ 13:03:46  我们连点 8 次 (822,539)→(949,370)，全部失败（42 秒）
```

两个敌方随从的实际槽心：`(887,370)` 与 `(1015,370)`；我们点的 `(949,370)` 是两者正中。

## 日志文件

**无**：本条引用的那一局原始日志已随历史清理丢失，无法附带原件。

## 根因

`src/hspy/input/powerlog.py` 的 TAG_CHANGE 处理：

```python
self._merge_ref(e, ref, zone_hint=False)   # 括号里的 zone 不生效
```

`zone_hint=False` 是为了防止“出牌时旧括号把刚上场的牌写回 HAND”。
但它同时把**唯一能把对手随从从 HAND 推进 PLAY 的信息**丢掉了。

## 修复

同一个 `_dispatch` 里，在 `_apply_tag` 之后增加“括号只许前进”：

```python
zref = (ref.get("zone") or "").upper()
if zref in ("PLAY", "GRAVEYARD") and e.zone == "HAND":
    e.zone = zref
    e.zone_pos = int(ref["zone_pos"])
    self.state.move_entity(e)
```

- 只接受 `HAND → PLAY / GRAVEYARD`；
- **不接受** `PLAY → HAND`（那正是当初的回归）；
- **不接受** `→ DECK`（抽牌时括号里的 zone 是旧的 `DECK`）。

## 验证

回放同一份 Power.log 到 `13:03:05`：

```
修前：敌方场面 []                                目标 → 第 1/1 格，落点 (949,370)
修后：敌方场面 [(1,CORE_EX1_096), (2,CORE_EX1_096)]  目标 → 第 1/2 格，落点 (887,370)
```

`tests/test_offline.py` 全绿。

## 证据（原始日志）

**原始日志已丢失**：该局目录在历史清理中被删，本条只剩下面的离线回放结果，无法用原始日志复核。状态因此只记「已修」，不记「实机验证」。

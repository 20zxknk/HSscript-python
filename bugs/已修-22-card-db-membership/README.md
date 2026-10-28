---
id: B-22
state: 已修
module: input.state
stage: 出牌
symptom_key: 幸运币被当非卡牌、附魔/地标被当随从，手牌张数与攻击目标偏移
patterns: ["hand_size_hint 比列表多一张", "攻击目标数多一只"]
root_cause: 成员判定靠前缀/攻血猜，没查卡池类型
related: [B-03, B-16]
reopened_count: 0
fp: cbe25c653178
fixed_at: 2026-10-28T00:50:00
---

# 22 手牌/场面的"成员判定"：幸运币被排除、附魔和地标被算成随从

**状态：已修**

## 名称

`card-db-membership`：手牌里哪些算卡、场上哪些算随从，旧代码靠卡号前缀和攻血猜：

- `cardId.startswith("GAME_")` 一律不算卡 → **幸运币 `GAME_005` 被排除**；
- `card_type` 为空时"有攻或血就算随从" → **附魔 `BE_207e`（带攻血）被算成随从**；
- `_is_board_card` 放行 `LOCATION` / `BATTLEGROUND_SPELL` → **地标 `CATA_492` 算进攻击目标数**。

真机后果：点击布局按 9 张排、列表只有 8 张（整排右移一格）；攻击目标数多一只
（"点第 N 只"点空）。

## 现象

2026-10-27 13:35:41（`13_32_40` 的 Power.log 第 5966 行附近）：

```
DebugPrintOptions 槽位：1 BE_094, 2 CATA_725, 3 GAME_005(幸运币), 4 BE_729, 5 BE_729,
                        6 CATA_725, 7 CORE_SCH_713, 8 BE_726   （另有 TLC_451 在 zonePos=9）
实体表 zone=HAND 且有卡号：9 个
旧 my_hand 列表：8 个（GAME_005 被排除）
```

`hand_size_hint()` 用的是实体表（9），所以布局按 9 张排；`my_hand` 列表只有 8 张，
槽位与列表下标从此错开。这不是"手牌少一张"的显示问题——点击矩形真的会偏。

## 触发条件

1. **后手**起手带幸运币，或任何 `GAME_005` 在手上；
2. 场上/手牌里出现**类型为空**的附魔（`BE_207e` 之类）；
3. 打出地标（`CATA_492` 暮光神坛），它进 `PLAY` 且 `card_type=LOCATION`。

## 触发场景

同上那局（r8 第 3 局的前一局），13:35:41 我方回合开始时。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/hand-vs-entities.txt`：槽位声明 / 实体表 / 旧列表的差（含卡池里的三个类型）。

## 根因

```python
# 旧 _is_real_card
if cid.startswith("GAME_"):
    return False        # 把幸运币也排掉了

# 旧 is_minion：类型为空时按攻血猜
return not self.card_type and (self.atk > 0 or self.health > 0)   # 附魔也有攻血

# 旧 _is_board_card
return e.card_type in ("", "MINION", "LOCATION", "BATTLEGROUND_SPELL", …)
```

## 修复

新增 `input/card_db.py`（读 `data/card_meta.json.gz`，36522 张，来自
`scripts/build_card_meta.py`），判定顺序改成"卡池优先，日志 `cardType` 后备"：

| 判定 | 规则 |
|---|---|
| 算不算卡牌 `_is_real_card` | 卡池类型 `ENCHANTMENT/HERO/HERO_POWER/GAME/INVALID/PLAYER` 排除；**不再按 `GAME_` 前缀排除** |
| 算不算随从 `is_minion` | 卡池 `type == MINION`；查不到再退回日志 `cardType` / 攻血 |
| 占不占场面格 `_is_board_card` | 卡池 `MINION` / `LOCATION`；法术、附魔、英雄不上场 |

卡池文件缺失时 `kind()` 返回 None，全部退回旧后备逻辑，不会把整局打挂。

## 验证

```
tests/test_powerlog_rules.py
  OK   随从判定以卡池为准（附魔/地标不算随从）
  OK   幸运币算手牌（少了它整排点击会右移一格）
```

另外 `tests/test_offline.py` 的"中途能看到场面随从"仍通过（没有因为收紧判定把场面清空）。

**真机待验**：后手开局时手牌布局应与游戏里一致（不右移一格）；攻击目标数不含地标/附魔。

---
id: B-16
state: 未修
module: engine._do_attack
stage: 我方回合
symptom_key: 攻击点了没反应：seq 冻结不变，连续 10 次以上
patterns: ["无 ATTACK 块"]
root_cause: 待定位（点击落点/攻击者槽位/目标矩形三者之一）
related: [B-06]
reopened_count: 0

fp: b7b1506bc984
---

# 16 攻击点了没反应：日志 seq 冻住，同一步连续重试 10 次以上

**状态：未修**

> 这条是从未修过的条目，fixed_at 是建账时误带的。

## 现象

稳定版那局（evidence/stable-v01-r1）从 step 212 起，连续 10 次攻击全部无效果，
而且 `before == after`（日志一行都没新增）：

```
[step 212] swallowed action=attack card=CATA_210 evidence=无 ATTACK 块 before=16366 after=16513
[step 218] swallowed action=attack card=CATA_210 evidence=无 ATTACK 块 before=16513 after=16513
[step 224] … 同样 before=16513 after=16513
… 一直到 step 272
```

`seq` 完全不动 = 点击根本没被游戏接收（不是“点了但没生效”）。

## 触发条件

待定位。这条局里攻击目标多次是对方英雄/随从，我们的 `attacker_slot` 断言都通过了
（`ok:attacker_slot`），所以不是“选错攻击者”这一层——更像是**落点不在可攻击区域**，
或者点击落在随从之间。

## 触发场景

2026-10-27 13:44 本目录 `logs/`（v0.1 稳定版跑的一局）。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/run.log`（80 KB，含 10 次 `无 ATTACK 块`）
- `logs/mouse.jsonl.gz`（257 KB）
- `logs/recommendations.jsonl`（96 KB，能看到盒子每次都要攻击同一条线）
- `logs/SOURCES.txt`

## 根因

未知。候选：

1. 攻击落点用的是「场面矩形中心」，但这个面板的随从站位更靠上；
2. 目标矩形（对方英雄）被血条/护甲遮挡；
3. 攻击前缺一次「点一下自己随从确认选中」的动作（作者是拖拽式）。

## 修复（未开始）

先用同一份日志 + 截图定位一次真实点击落点，再决定。不要先加重试上限。

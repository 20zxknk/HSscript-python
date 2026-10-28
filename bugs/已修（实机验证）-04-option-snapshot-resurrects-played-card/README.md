---
id: B-04
state: 已修（实机验证）
module: input.state
stage: 选项快照
symptom_key: 选项快照把已打出的牌塞回手牌并把位置钉回旧值
patterns: []
root_cause: 快照既能改区域又能改位置
related: []
reopened_count: 0
verify: {build: "51254d0", logs: "bugs/已修（实机验证）-04-option-snapshot-resurrects-played-card"}
fp: a2f27efa8bc4
fixed_at: 2026-10-25T13:00:00

---

# 04 选项快照把已打出的牌塞回手牌、并把位置钉回旧值

**状态：已修（实机验证）**

## 名称

`option-snapshot-resurrects-played-card`

## 现象

打出一张牌后，我们的手牌列表里它还在；整排手牌编号整体右移一格，
盒子点名的槽位随之错位（要第 4 槽，点成第 1 槽）。

## 触发条件

`apply_option_slots()` 无条件执行 `ent.zone = "HAND"; ent.zone_pos = slot`；
而 `DebugPrintOptions` 打印时机早于出牌结算，里面带着**出牌前的旧括号**。

## 触发场景

test3 回合4（`02:29:05`–`02:29:09`）：`CATA_210` 已 `ZONE=PLAY`，
选项块里仍有它（`type=POWER` 的触发项），下一次 `refresh()` 把它塞回槽 2。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/mouse.jsonl.gz`（210616 字节）
- `logs/powerlog_story.md`（7713 字节）
- `logs/recommendations.jsonl`（33760 字节）
- `logs/SOURCES.txt`：以上文件各自的原始路径

文件名保持原样，未改；`SOURCES.txt` 里写了每个文件的出处。

## 根因

快照既可以改区域、又可以改位置，而日志已经把真实位置逐条打印出来了
（`TAG_CHANGE … tag=ZONE_POSITION value=N`）。

## 修复

- 只有 `zone in ("HAND","")` 的实体允许被快照“钉位置”，**钉位置不改区域**；
- 位置只认日志的 `ZONE_POSITION`，快照只补 `card_id` 与位置未知（`zone_pos<=0`）的实体。

## 验证

同一断点：`refresh 后` 仍为 `[(1,BE_207),(2,TIME_029),(3,TIME_026)]`，
`CATA_210` 留在场面。

## 证据（原始日志）

本目录 `logs/` 下的原始文件（可直接 grep）：

```
logs/mouse.jsonl.gz    ← test3\mouse.jsonl.gz
logs/recommendations.jsonl    ← test3\recommendations.jsonl
logs/powerlog_story.md    ← test3\powerlog_story.md
```

核对方式：在 `logs/` 里按 README 上的时间戳/卡号直接搜；三份文件（鼠标 / 盒子应答 / 游戏侧叙述）互相对照。

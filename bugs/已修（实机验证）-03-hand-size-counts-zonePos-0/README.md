---
id: B-03
state: 已修（实机验证）
module: input.state
stage: 手牌统计
symptom_key: 手牌张数把 zonePos=0 的分身算成手牌，布局排宽
patterns: []
root_cause: 没过滤 zonePos>=1
related: []
reopened_count: 0
verify: {build: "51254d0", logs: "bugs/已修（实机验证）-03-hand-size-counts-zonePos-0"}
fp: 31b5f79653e1
fixed_at: 2026-10-25T13:00:00

---

# 03 手牌张数把 `zonePos=0` 的分身算成手牌，布局排宽

**状态：已修（实机验证）**

## 名称

`hand-size-counts-zonePos-0`

## 现象

同一个 `play TIME_025`（槽 3）连点 6 次，全部 `牌还在手上`；
日志里 `手牌[5]` 而实际只有 3 张。

## 触发条件

`GameState.hand_size_hint()` 把“`zone=HAND` 且 `cardId` 非空”的实体全部计数，
其中包含 `zonePos=0` 的**效果分身**（`TIME_025t`）——它们不在手牌栏位上。

## 触发场景

test7 回合5（`03:24:14`）：手牌 3 张 + 2 个 `TIME_025t`（pos=0）。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/mouse.jsonl.gz`（266106 字节）
- `logs/powerlog_story.md`（3026 字节）
- `logs/recommendations.jsonl`（66946 字节）
- `logs/SOURCES.txt`：以上文件各自的原始路径

文件名保持原样，未改；`SOURCES.txt` 里写了每个文件的出处。

## 根因

```python
known = sum(1 for e in ... if e.zone == "HAND" and e.card_id)   # 把 pos=0 也算进去
```

## 修复

只数 `zone_pos >= 1`，且张数以实体为准（`max(known, max_pos)`），
选项快照只在实体表为空时兜底。

## 验证

同一断点 `hand_size_hint 5 -> 3`，`my_hand = [TIME_029@1, TIME_026@2, TIME_025@3]`。

## 证据（原始日志）

本目录 `logs/` 下的原始文件（可直接 grep）：

```
logs/mouse.jsonl.gz    ← test7\mouse.jsonl.gz
logs/recommendations.jsonl    ← test7\recommendations.jsonl
logs/powerlog_story.md    ← test7\powerlog_story.md
```

核对方式：在 `logs/` 里按 README 上的时间戳/卡号直接搜；三份文件（鼠标 / 盒子应答 / 游戏侧叙述）互相对照。

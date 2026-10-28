---
id: B-21
state: 已修
module: input.powerlog
stage: 场面同步
symptom_key: PowerTaskList 与 SHOW_ENTITY 的裸 tag 没归属，场面少人/多幽灵
patterns: ["rival_board 少人", "场面人数与日志不符"]
root_cause: 实时解析器整段跳过 PowerTaskList，且只把 FULL_ENTITY 当裸 tag 归属者
related: [B-01, B-16]
reopened_count: 0
fp: 77121ec2bb38
fixed_at: 2026-10-28T00:50:00
---

# 21 裸 `tag=` 的归属缺了 SHOW_ENTITY / BLOCK_START，PowerTaskList 又被整段跳过

**状态：已修**

## 名称

`powerlog-tasklist-ownership`：`docs/reference/powerlog.md` 写明"PowerTaskList 是方块执行时的
全量快照"，但实时解析器只从里面取 TURN/STEP/STATE/CURRENT_PLAYER，其余整段丢弃；
裸 `tag=` 又只认 `FULL_ENTITY` 一个归属者，`SHOW_ENTITY` / `BLOCK_START` 后面的 tag 会挂到
**上一条实体**上。两个问题叠在一起，场面人数会少、会多幽灵、会把随从写回 SETASIDE。

## 现象

1. 对手随从打出来了，`rival_board` 仍是空/少一只 —— 攻击目标按错误张数排落点
   （BUG 01 的"括号只许前进"只是绕过，见下）；
2. 真机 13:45:03（`Hearthstone_2026_10_27_13_32_40`）更直接：场上一只 `TIME_029`（id=84）
   被一句 `tag=ZONE value=SETASIDE` 塞回 SETASIDE，场面凭空少一只；
3. 同一份日志按回合对账（与独立还原脚本 `scripts/boards_replay.py` 逐行号比），
   改前多个回合点双方随从集合不一致、手牌顺序 4~6 个回合点不一致。

## 触发条件

1. **PowerTaskList 的实体行没有 `Entity=` 前缀**：
   `FULL_ENTITY - Updating [entityName=… id=43 …] CardID=…`。旧 `classify_line` 遇到
   `PowerTaskList.DebugPrint` 直接走"只认全局 tag"的分支，这条一条都解析不到；
2. 对手随从的 `tag=ZONE value=PLAY` 往往**只在 PowerTaskList** 里打；
3. 任务/衍生牌登场是 `SHOW_ENTITY - Updating [id=123 …] CardID=TIME_025t` 后面跟一串
   `tag=CONTROLLER/ZONE…`。旧 `EV_ENTITY_SHOW` 不设 `_pending_entity`，
   于是 `tag=ZONE value=SETASIDE` 挂到了**上一条** `BLOCK_START Entity=[id=84 …]` 上；
4. `BLOCK_START` 本身也没被当成归属者（旧代码里根本没有这个事件）。

## 触发场景

2026-10-27 13:45:03，第 16322 行起：

```
PowerTaskList … BLOCK_START BlockType=POWER Entity=[entityName=灾毁迅疾幼龙 id=84 zone=PLAY zonePos=1 …]
PowerTaskList … SHOW_ENTITY - Updating Entity=[entityName=时空撕裂 id=123 zone=DECK zonePos=0 …] CardID=TIME_025t
PowerTaskList …         tag=CONTROLLER value=2
…
PowerTaskList …         tag=ZONE value=SETASIDE      ← 属于 123，被写到 84 上
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/powerlog-1345-setaside.log`：上面这段原文（含前后 28 行）；
- `logs/compare-before-after.log`：改前/改后用同一行号对齐的逐回合对账结果。

## 根因

```python
# 旧：PowerTaskList 除了几个全局 tag 以外整段丢掉
if "PowerTaskList.DebugPrint" in line:
    m = re.search(r"TAG_CHANGE Entity=.+? tag=(TURN|STATE|STEP|CURRENT_PLAYER) …", line)
    if not m:
        return None, {}
```

```python
# 旧：SHOW_ENTITY 不接管后续裸 tag
if kind == EV_ENTITY_SHOW:
    …
    self.state.move_entity(e)
    return          # _pending_entity 还停在上一条 BLOCK_START 的实体上
```

## 修复

1. `classify_line` 去掉"tasklist 整段跳过"，按同一套规则解析两种来源：
   `FULL_ENTITY - Creating/Updating`（含无 `Entity=` 前缀）、`TAG_CHANGE`、
   `BLOCK_START`、裸 `tag=` 全部认；`source=tasklist` 的方括号当**当前状态**用，
   GameState 的方括号仍只当"首次见到"（防旧括号把上场的牌写回手牌）；
2. 新增 `EV_BLOCK_START` / `EV_BLOCK_END`：`BLOCK_START … Entity=[ref]` 设 `_pending_entity`，
   `BLOCK_END` / `HIDE_ENTITY` 清掉；
3. `EV_ENTITY_SHOW` 也设 `_pending_entity`；
4. **任何认不出的行都让 pending 作废**（以前 `kind is None` 直接 return，pending 一直留着）。

## 验证

```
tests/test_powerlog_rules.py
  OK   PowerTaskList 的 ZONE=PLAY 能落到对手场面
  OK   SHOW_ENTITY 是裸 tag 的归属者（不会串到上一条实体）
  OK   `FULL_ENTITY - Updating [entityName=…]` 能解析出 eid
  OK   无关行让裸 tag 作废（不会把牌写上场）
```

真机日志逐回合对账（`logs/compare-before-after.log`）：

```
19_16 seg3：随从集合 1 处不一致 → 0；手牌顺序 4 个回合点不一致 → 0
19_16 seg4：随从集合 0 → 0；手牌顺序 6 → 0
13_32 seg0：随从集合 2 → 1；手牌顺序 5 → 0
```

剩下的 1 处是"衍生牌的名字什么时候揭示"：两边数的是**同一只随从**，
独立脚本那边还是 `未知牌(eid)`、我们这边已经认出 `CORE_WON_141`（卡号来自 SHOW_ENTITY）。
不是人数错误。

**真机待验**：攻击敌方随从的落点应按真实张数排；`rival_board` 不应再少人。

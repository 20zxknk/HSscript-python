---
id: B-06
state: 已修
module: engine.card_usable
stage: 出牌前校验
symptom_key: 用残缺手牌名单查能否打出，抓到别的实体，合法牌被拦
patterns: ["FAIL:card_usable", "error=REQ_"]
root_cause: 按 card_id 查实体而不是用槽位->eid 映射
related: []
reopened_count: 1
fp: cda52462e9d8
fixed_at: 2026-10-25T20:00:00

---

# 06 用残缺的手牌名单查"这张牌能不能打"，抓到别的实体，合法的牌被拦 3 分半钟

**状态：已修**

## 名称

`card-usable-wrong-entity`

## 现象

同一张 `play_special BE_726 手3` 被连续拦下约 230 次（01:22:13 → 13:23:19，约 70 秒 ×
每轮 1.1s），引擎一直打：

```
[engine] 断言拦截（未点击，等牌进手/等新方案）: card_usable 断言失败:
         {"card": "BE_726", "eid": 19, "error": "REQ_ENOUGH_MANA"}
```

而游戏自己的选项里，槽 3 那张 `BE_726` 的 error 是 `NONE`（能打）。

## 触发条件

1. 手牌里有些牌我们的实体名单里认不出来（test13 这一手真实 6 张，`my_hand` 只有 3 张：
   位置 4/5/6 的 CAP_405 / DINO_COIN2 / BE_729）；
2. 盒子点的是**我们名单外**的那张（槽 3 = BE_726）；
3. `_do_play` 判可用性时按"我们名单里 zone_pos==3 的实体"去找 —— 找不到就退化成
   "列表第 3 个"，抓到的是 `BE_729`（eid=19，`REQ_ENOUGH_MANA`），于是断言失败。

## 触发场景

test13（casual，`2026-10-25 13:21:06` 那局），第 1 回合（`my_id=1`、`turn=1`）：

```
13:22:13.4  盒子: play_special BE_726 手3（turnNum=2）
13:22:13~   我们每轮都打 FAIL:card_usable card=BE_726 eid=19 error=REQ_ENOUGH_MANA
            到 13:23:19 共约 230 轮，一次都没点
同一时刻（回放 Power.log 到 13:22:14）：
  游戏选项快照 slot->cardId = {1:BE_726, 2:CATA_210, 3:BE_726, 4:CAP_405, 5:DINO_COIN2, 6:BE_729}
  游戏选项 slot->eid       = {1:10, 2:15, 3:25, 5:68, 4:13, 6:19}
  option_errors            = {25:'NONE', 19:'REQ_ENOUGH_MANA', 13:'REQ_ENOUGH_MANA', ...}
  我们的 my_hand           = [(CAP_405,pos4,eid13), (DINO_COIN2,pos5,eid68), (BE_729,pos6,eid19)]
```

槽 3 在游戏里是 `eid=25`（BE_726，`NONE`）；我们却抓到 `eid=19`（BE_729，`REQ_ENOUGH_MANA`）。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/mouse.jsonl.gz`（99899 字节）
- `logs/recommendations.jsonl`（79555 字节）
- `logs/SOURCES.txt`：以上文件各自的原始路径

文件名保持原样，未改；`SOURCES.txt` 里写了每个文件的出处。

## 根因

`src/hspy/engine.py::_do_play` 判可用性：

```python
ent = next((e for e in st.my_hand if e.zone_pos == pos + 1), None)
if ent is None and 0 <= pos < len(st.my_hand):
    ent = st.my_hand[pos]        # ← 名单残缺时抓错人
err = st.option_errors.get(ent.eid) or ""
```

游戏已经给了 **槽位 → eid** 的权威映射（`hand_option_eids`）和每个 eid 的 error
（`option_errors`），我们没用它，反而拿自己残缺的名单去查。

## 修复

优先用游戏的映射：

```python
slot_eid = (st.hand_option_eids.get(st.my_id) or {}).get(pos + 1)
ent = st.entities.get(slot_eid) if slot_eid else None
if ent is None:                       # 游戏没给这个槽位，才退回我们的名单
    ent = next((e for e in st.my_hand if e.zone_pos == pos + 1), None)
if ent is None and 0 <= pos < len(st.my_hand):
    ent = st.my_hand[pos]
```

## 验证

回放同一时刻：

```
修后：槽3 -> eid 25  card=BE_726  error='NONE'          → 断言通过，可以点
旧逻辑：列表第 3 个 = BE_729  eid=19  error='REQ_ENOUGH_MANA' → 被拦
```

`tests/test_offline.py` 全绿。真机待验：同样的局面下应看到这个动作真的点出去。

## 证据（原始日志）

本目录 `logs/` 下的原始文件（可直接 grep）：

```
logs/mouse.jsonl.gz    ← test13\mouse.jsonl.gz
logs/recommendations.jsonl    ← test13\recommendations.jsonl
```

核对方式：在 `logs/` 里按 README 上的时间戳/卡号直接搜；三份文件（鼠标 / 盒子应答 / 游戏侧叙述）互相对照。

## 复发记录 #1（2026-10-27 12:44）

- 症状：16 次 FAIL:card_usable / REQ_ENOUGH_MANA，同一个 BE_207 反复重试
- 原始日志：`logs/reopen1-015-112438-mouse.jsonl.gz`, `logs/reopen1-015-112438-powerlog_story.md`, `logs/reopen1-015-112438-README.md`, `logs/reopen1-015-112438-recommendations.jsonl`, `logs/reopen1-015-112438-run.log`
- 来源：`test\015-112438`

状态已改回「未修」：这条修复在真机上没有生效，先别当已修看。

## 复发确认的根因（2026-10-27 13:00，证据 test/015-112438）

真机日志（`logs/reopen1-015-112438-run.log`）：

```
[step 196] FAIL:card_usable card=BE_207 eid=59 error=REQ_ENOUGH_MANA slot=3 src=option_map
（后面 16 次同样的失败，每次都点槽 3）
```

对照同一时刻游戏的选项块（Power.log 11:32:36, id=43）：

```
option 2 type=POWER mainEntity=[… id=43 zone=HAND zonePos=4 cardId=BE_207 player=2]
option 3 type=POWER mainEntity=[… id=59 zone=HAND zonePos=3 cardId=TIME_025 player=2]
```

而盒子这一轮给的是：

```json
{"action": "play", "hand_position": 3, "card_id": "BE_207"}
```

**盒子的 `hand_position` 与 `card_id` 自相矛盾**（BE_207 在槽 4，槽 3 是 TIME_025），
而旧代码的规则是「槽位只认盒子的 hand_position」，于是：

1. 点槽 3 = TIME_025；
2. 游戏在选项里标着 `REQ_ENOUGH_MANA`（这张牌这一回合打不出）；
3. 我们判 `card_usable` 失败，但**没有换槽**，下一轮还是盒子同一份推荐 → 再点 → 再失败，
   16 次、每次 8 步。

所以根因不是“盒子给了非法推荐”，而是**我们无条件相信盒子的槽位，不用卡号核对**。

## 修复

`engine._do_play` 的槽位解析改成用「游戏选项映射」三方核对：

```python
def slot_card(slot):                     # 槽位 -> eid -> 实体卡号（游戏自己给的）
    eid = hand_option_eids[my_id].get(slot)
    ent = entities.get(eid)
    return ent.card_id if ent else ""

box_card = slot_card(box_pos)            # 盒子指的那个槽，实际是什么牌
if cid and box_card and box_card != cid and opt_hit:
    alt = first(s for s in opt_hit if slot_card(s) == cid)   # 快照里这张牌真正在的槽
    if alt: pos = alt - 1
```

规则变成：

| 情况 | 用哪个槽 |
|---|---|
| 盒子槽位的实体卡号 == 盒子点名卡号 | 盒子的槽位（快照可能更旧，仍以它为准） |
| 不一致，但快照里另一槽正好是这张牌 | 那一槽，并记录 `slot_from_card` |
| 卡号在快照里完全找不到 | 仍用盒子的槽位（快照更旧的情况） |

## 验证（离线）

```
tests/test_slot_conflict.py
  OK   盒子位置 3 与卡号冲突 -> 改用槽 4（BE_207 的真实位置）
  OK   盒子位置与卡号一致 -> 照用槽 4
  OK   卡号在快照里找不到 -> 仍信盒子的槽位（快照可能更旧）
```

真机验证待补：同一场景下应看到 `[?] 盒子槽 3 实际是 TIME_025，按卡号 BE_207 改用槽 4`，
并且不再出现 `REQ_ENOUGH_MANA` 的连续失败。

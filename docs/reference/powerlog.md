# Power.log 怎么读

这一页只讲一件事：**从 Power.log 还原一局对局时，每一种信息该认哪一行**。
每条规则都是真机日志验证过的，括号里是踩过的坑。

## 日志里有三种区块

```
PowerTaskList.DebugDump() - ID=1 ParentID=0 PreviousID=0 TaskCount=68
PowerTaskList.DebugDump() - Block Start=(null)
PowerTaskList.DebugPrintPower() - FULL_ENTITY - Updating [entityName=栉龙 id=43 zone=HAND zonePos=4 cardId=TLC_603 player=2]
PowerTaskList.DebugDump() - Block End=(null)

GameState.DebugPrintPower() - TAG_CHANGE Entity=[…] tag=ZONE value=GRAVEYARD
GameState.DebugPrintOptions() - id=1
GameState.DebugPrintEntityChoices() - id=2 Player=… ChoiceType=MULLIGAN CountMin=0 CountMax=5
GameState.SendChoices() -   m_chosenEntities[0]=[…]
```

`PowerTaskList` 是方块执行时的**全量快照**，`GameState` 是**增量广播**。

## 每条信息的唯一来源

| 信息 | 认这一行 | 不能用的 |
|---|---|---|
| 卡号 / 名字 | 任何方括号实体的 `cardId=` / `entityName=` | — |
| 区域 / 位置 | `tag=ZONE` / `tag=ZONE_POSITION` 的值，或 PowerTaskList 方括号快照 | `GameState` 方括号里的 `zone=`（是旧状态） |
| 手牌槽位 | 实体自己的 `tag=ZONE_POSITION`（`DebugPrintOptions` 只用来拿 eid） | 选项行 `mainEntity=[… zonePos=…]` 里的 `zonePos`（旧一拍） |
| 随从判定 | 卡牌库 `type == "MINION"`（`data/card_meta.json.gz`） | 日志里的 `tag=CARDTYPE`（会被裸 tag 挂错，只作后备） |
| 回合 | `TAG_CHANGE Entity=GameEntity tag=TURN value=N` → 回合 = `(N+1)//2` | 玩家的 `tag=TURN`（是完整回合数，会互相覆盖） |
| 回合起点（"能不能动手"的时间戳） | `GameEntity TURN` 行（只接受前进值） | `CURRENT_PLAYER` 行（PowerTaskList 会原样重放，重放一来自动把窗口关上） |
| 换牌保留数 | `DebugPrintEntitiesChosen … EntitiesCount=N` → **N 是保留数** | 当成“换掉数”（会得出“全部保留还发 3 张”的矛盾） |
| 起手张数 | `DebugPrintEntityChoices … CountMax=N`，含幸运币，所以起手 = N − 1（有币时） | 靠 `DECK→HAND` 推（GameState 里没有起手牌的这行） |

**选项行是最会骗人的一处**（真机 2026-10-27 19:47:28）：先打

```
19:47:28.493  TAG_CHANGE Entity=[… id=61 zone=HAND zonePos=5 cardId=TIME_026 …] tag=ZONE_POSITION value=4
19:47:28.500  DebugPrintOptions() - option 3 … mainEntity=[… id=61 zone=HAND zonePos=5 …]
```

6ms 后的选项括号还写着 `zonePos=5`。按它改槽 → 点到槽 5 的 `TLC_451` →
`hand_slot` 断言每 6 步失败一次，整局卡死。**槽位只认实体身上的 tag**；
括号里的 `zonePos` 只在实体还没位置时兜底。已经离开手牌的实体（`zone != HAND`）
哪怕还被选项点名，它的 `zonePos` 也是**场面位置**，不能写进手牌槽位表。

## 裸 `tag=` 的归属

```
FULL_ENTITY - Creating ID=N             ← 这行之后、直到下一行非 tag 行，都属于 N
SHOW_ENTITY|FULL_ENTITY - Updating [ref]
BLOCK_START BlockType=… Entity=[ref]
    tag=ZONE value=HAND                 ← 属于上面那条
```

遇到 `BLOCK_END` / `HIDE_ENTITY` / 其他行就作废。**不这么做会串实体**：实测把幸运币写成
`HERO_POWER`、把附魔 `BE_207e` 当成随从上场、真随从被覆盖。

`SHOW_ENTITY` 也是归属者 —— 这一条是后补的坑（2026-10-27 13:45:03）：任务/衍生牌登场是
`SHOW_ENTITY - Updating [id=123 …] CardID=TIME_025t` 后面跟一串 `tag=CONTROLLER/ZONE…`。
只认 FULL/BLOCK_START 时，这一串会挂到上一条 `BLOCK_START Entity=[id=84 场上的龙]` 上，
一句 `tag=ZONE value=SETASIDE` 就把场上的随从塞回 SETASIDE，场面凭空少一只。

**PowerTaskList 的实体行没有 `Entity=` 前缀**：

```
PowerTaskList.DebugPrintPower() -  FULL_ENTITY - Updating [entityName=… id=43 …] CardID=
```

正则写成 `Updating Entity=` 会一条都解析不到；而对手随从的 `tag=ZONE value=PLAY` 往往只在
PowerTaskList 里。跳过整段 ⇒ 对手场面永远少人、攻击落点错（BUG 01 的根因，之前的
“括号只许前进”只是绕过）。现在两层都读，`source=tasklist` 的方括号当当前状态用。

## 面（7 格）怎么摆

一方 7 格，N 个随从**居中连排**，`zonePos` 只表示“这 N 个里的第几个”，不是第几格：

```
起始列 = (7 - N) // 2 + 1        N=1 → 第 4 格；N=2 → 3,4；N=3 → 3,4,5
对方整行镜像：它的 1 号位显示在最右
```

按 `zonePos` 直接落到第 1..7 格是错的（随从会贴左/贴右），这条坑踩过。

## 工具

```bash
# 卡牌元数据（名字 / 类型 / 攻血），官方简体中文表 + 本地库合并，写成 .gz
python -X utf8 scripts/build_card_meta.py

# 一局的过程（换牌、出牌、攻击、伤害、死亡、结算）
python -X utf8 scripts/powerlog_replay.py <Power.log> --seg 7 --out logs/timeline-seg7.md

# 每回合场面（HTML/JSON，双方 7 格居中连排，带自检）
python -X utf8 scripts/boards_replay.py --log <Power.log> --seg 7 \
    --out logs/boards-seg7.html --json logs/boards-seg7.json

# 卡图（暴雪官方卡面，按需下载，不进仓库）
HTTPS_PROXY=http://127.0.0.1:7890 python -X utf8 scripts/fetch_card_images.py --cards BE_726 TLC_451
```

`--seg N` 是第 N 个 `GameState` 的 `CREATE_GAME` 之后的整局（0 基）。

## 已知边界

- 对手未揭示的手牌：日志里只有 `未知牌(eidNN)`，不是解析失败；
- 快照按“回合开始那一行”的行序判定；同一毫秒既有换回合又有死亡时以行序为准；
- 每段仍有约 60 行裸 `tag=` 找不到实体头行，未使用；
- `HEALTH` 可能滞后于 `DAMAGE`，会出现 `0/1(-3)` 这种显示，照日志不推算。

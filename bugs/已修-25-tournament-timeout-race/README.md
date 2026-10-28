---
id: B-25
state: 已修
module: run.enter_match
stage: 匹配
symptom_key: go_tournament 超时时新对局已经开始，被误判为进入对战失败
patterns: ["进入对战失败", "go_tournament 第1xx次"]
root_cause: 新对局只看 screen 日志的 mode==GAMEPLAY；界面日志卡在 TOURNAMENT 时整局被丢
related: [B-14]
reopened_count: 0
fp: 3fd40d432fe1
fixed_at: 2026-10-28T23:05:00
---

# 25 新对局已经开了，导航还在 TOURNAMENT 里点到超时

**状态：已修**

## 名称

`tournament-timeout-race`：`go_tournament` 只把 `screen` 日志的 `mode == GAMEPLAY`
当"进对局了"。真机上出现过界面日志没被认出来的情况：Power.log 里 `CREATE_GAME`
和 `BEGIN_MULLIGAN` 都已经打了，导航还在 TOURNAMENT 里每 8 秒点一次「确定」，
4 分钟后超时返回 False，`run.py` 判"进入对战失败"直接退出——**白丢一局**。

## 现象

```
[nav] 匹配中：点一次「确定」（可能弹了开赛错误）        ← 第 177、185 次…
[nav] go_tournament: mode=TOURNAMENT 第185次 seq_done=True (剩 2s)
[nav] 超时
[run] 进入对战失败
=== 收工：1 局 ===
```

而同一时刻客户端画面已经是第 1 回合、1 费（截图核对过）。

## 触发条件

1. 上一局结束，`enter_match` → `go_tournament` 开始排队；
2. 新对局开始（Power.log：22:51:37 `CREATE_GAME` + `BEGIN_MULLIGAN`；
   LoadingScreen：22:51:40 `OnSceneLoaded prevMode=TOURNAMENT currMode=GAMEPLAY`）；
3. 导航循环里 `self.sync.pump().mode` 一直没有变成 GAMEPLAY（界面日志/缓存的时序问题）；
4. 240s 到点返回 False → `run.py` 判失败退出，**客户端那一局没人打**。

## 触发场景

2026-10-28 22:51–22:52，`Hearthstone_2026_10_28_16_17_17`：

```
22:51:37.677  Power.log      CREATE_GAME + STEP=BEGIN_MULLIGAN
22:51:40.392  LoadingScreen  OnSceneLoaded prevMode=TOURNAMENT currMode=GAMEPLAY
22:52:54      run.py         超时 -> 进入对战失败 -> 收工（1 局）
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/run-engage-timeout.log`：引擎侧最后 8 行（匹配中 → 超时 → 退出）；
- `logs/powerlog-2251-game-started.log`：游戏侧 22:51:36–22:51:42 的
  `CREATE_GAME` / `BEGIN_MULLIGAN` / `OnSceneLoaded … currMode=GAMEPLAY`。

## 根因

`go_tournament` 的唯一成功判据：

```python
if m == GAMEPLAY:
    return True
```

`m` 来自 `LoadingScreen.log`。这条链路只要慢一拍/漏一行，新对局就"不存在"。
对局是否存在，Power.log 是更硬的证据（游戏自己写的 `CREATE_GAME` 段）。

## 修复

1. `navigator.go_tournament`：进入时记下 `seg_index`；循环里除 `m == GAMEPLAY` 外，
   再加一条"Power.log 出现新段且未结束 → 已进入对局"；
2. `run.enter_match`：`go_tournament` 超时返回 False 时，**再看一眼 Power.log**
   （`started and not finished`）→ 直接接管这一局，不再判"进入对战失败"；
3. `config.toml` 的 `match_timeout` 120s → 300s：高分段排队常超过 2 分钟，
   旧值会反复取消队列重排。

## 验证

- `tests/test_navigator.py` 4 组契约用例通过；
- 离线门禁 17/17；
- 真机日志时间线见上（修复后 `--attach` 接管同一局并正常出牌）。

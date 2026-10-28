---
id: B-05
state: 未修
module: engine.play_match
stage: 我方回合
symptom_key: 选择面板开着时引擎当成不是我的回合，整局空转
patterns: ["选择面板还开着"]
root_cause: 只看 my_action_window，没看 choice_open
related: []
reopened_count: 1
fp: fc5c0f9d4637


---

# 05 选择面板开着时引擎当成“不是我的回合”，整局空转

**状态：未修**

> 原 B-05 的修复在 2026-10-27 真机上复发（见「复发记录」），fixed_at 已作废，不再表示「已修好」。

## 名称

`choice-panel-not-polled`

## 现象

打出 `BE_726 克苏恩仪式` 后，游戏弹出 GENERAL 选择面板（4 个候选）；
引擎日志连续 60 秒只打 `等待中`，一次都不问盒子、也不点面板，直到人工中止。

## 触发条件

1. 游戏弹出选择面板（`GameState.DebugPrintEntityChoices` / `ChoiceCardMgr.WaitThenShowChoices`）；
2. 弹出时**不在“我的回合窗口”**（`my_action_window = False`，因为选牌发生在出牌结算里）；
3. 主循环第一道判断是 `if not st.my_action_window: sleep; continue` —— 选择面板不参与判断。

## 触发场景

test12（casual，`2026-10-25 13:14:24` 那局），第 2 回合结束时打出 `BE_726`：

```
13:15:52.5  Power.log: BLOCK_START BlockType=PLAY … BE_726（我们打出克苏恩仪式）
13:16:02.1  ChoiceCardMgr.WaitThenShowChoices() - id=3 BEGIN
13:16:04.0  DebugPrintEntityChoices - id=4 … ChoiceType=GENERAL CountMin=1 CountMax=1
              Entities[0]=BE_013t1 克苏恩的愤怒
              Entities[1]=BE_013t2 克苏恩的领域
              Entities[2]=BE_013t3 克苏恩的凝视
              Entities[3]=BE_013t4 克苏恩的仆从
13:16:04.1  桥收到盒子的 choice：{"actionName":"choice",
              "target":{"cardName":"克苏恩的仆从","cardId":"BE_013t4","ZONE_POSITION":4}}
13:16:04 ~ 13:16:05+  引擎日志只有「等待中 … turn=3 cur=2 me=2」
```

同一时刻我们解析出的状态（回放 Power.log 到 13:16:05）：

```
choice_open = True   choice_type = GENERAL
choices = [BE_013t1, BE_013t2, BE_013t3, BE_013t4]
turn = 3  cur = 2  me = 2   my_action_window = False
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/mouse.jsonl.gz`（126310 字节）
- `logs/recommendations.jsonl`（10381 字节）
- `logs/SOURCES.txt`：以上文件各自的原始路径

文件名保持原样，未改；`SOURCES.txt` 里写了每个文件的出处。

## 根因

`src/hspy/engine.py` 主循环：

```python
if not st.my_action_window:
    ... 打印“等待中”、sleep、continue
```

选择面板不算“能操作”，于是永远走不到“问盒子 / 点面板”。

## 修复

```python
if not st.my_action_window and not st.choice_open:   # 面板开着就继续往下走
    ...

# 动作前断言也分两种合法情形
if st.choice_open:
    self.stepper.require(len(st.choices) > 0, "choice_open", n=len(st.choices), ...)
else:
    self.stepper.require(st.my_action_window, "my_turn", ...)
```

`_execute` 里本来就有 `if st.choice_open: self._do_choice(plan, st)`，
所以放行之后会直接按盒子的 `target_position=4` 点第 4 个候选。

## 验证

- 回放 test12 的 Power.log 到 13:16:05：`choice_open=True`、`choices` 4 个、
  `my_action_window=False` —— 修复前必然被第一道判断挡住，修复后进入动作路径。
- `tests/test_offline.py` 全绿。
- 真机待验：下一局再出现选择面板时，应看到 `动作前重查 … choice`，
  并在 `actions.jsonl` 里出现 `action=choice` 的一步。

## 证据（原始日志）

本目录 `logs/` 下的原始文件（可直接 grep）：

```
logs/mouse.jsonl.gz    ← test12\mouse.jsonl.gz
logs/recommendations.jsonl    ← test12\recommendations.jsonl
```

核对方式：在 `logs/` 里按 README 上的时间戳/卡号直接搜；三份文件（鼠标 / 盒子应答 / 游戏侧叙述）互相对照。

## 复发记录 #1（2026-10-27 12:44）

- 症状：点击候选卡后 21 次「选择面板还开着」，seq 从 19612 起一动不动
- 原始日志：`logs/reopen1-015-112438-mouse.jsonl.gz`, `logs/reopen1-015-112438-powerlog_story.md`, `logs/reopen1-015-112438-README.md`, `logs/reopen1-015-112438-recommendations.jsonl`, `logs/reopen1-015-112438-run.log`
- 来源：`test\015-112438`

状态已改回「未修」：这条修复在真机上没有生效，先别当已修看。

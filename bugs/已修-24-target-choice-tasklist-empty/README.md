---
id: B-24
state: 已修
module: input.powerlog
stage: 我方回合
symptom_key: TARGET 选择面板 TaskList 为空导致整回合空过
patterns: ["等待中 cur=我", "面板亮着但 choice_open 为假"]
root_cause: DebugPrintEntityChoices 头部正则写死 TaskList=\d+，TARGET 面板的 TaskList 是空的
related: [B-05, B-15]
reopened_count: 0
fp: fed6776d0745
fixed_at: 2026-10-28T10:40:00
---

# 24 `ChoiceType=TARGET` 的头部 `TaskList=` 是空的，整个面板被无视

**状态：已修**

## 名称

`target-choice-tasklist-empty`：选目标面板的头部是

```
DebugPrintEntityChoices() - id=12 Player=… TaskList= ChoiceType=TARGET CountMin=1 CountMax=1
```

`TaskList=` 后面**没有数字**（直接跟空格和 ChoiceType）。旧正则写死 `TaskList=\d+`，
整条 header 匹配不上 → `choice_open` 永远是假 → 引擎把面板当不存在，
一直等"我的操作窗口"，直到烧绳把回合交出去。候选 `Entities[i]` 倒是照常进 `choices`，
所以日志里"有候选、但没有面板"。

## 现象

线上 2026-10-28 10:25:13 我方回合开始，10:25:18 弹出选目标面板
（克苏恩的凝视：三个敌人亮绿框，等我们点一个）。引擎侧：

```
[engine] 等待中 mode=GAMEPLAY turn=10 cur=2 me=2 hand=1 board=3
[engine] 局面 60s 未动，继续轮询 turn=10 cur=2 me=2 hand=1 board=3
```

一直等到 10:26:27 游戏**超时自动替我们选**（`DebugPrintEntitiesChosen id=12`），
这一回合等于没有操作。截图里"随从全亮绿框、时钟不走"就是它。

## 触发条件

1. 游戏要求选一个目标（`ChoiceType=TARGET`），头部 `TaskList=` 为空；
2. `classify_line` 的 header 正则 `TaskList=\d+` 匹配失败 → 返回 None；
3. 后面的 `Entities[i]=…` 仍被 `EV_CHOICE_ENTITY` 收进 `choices`，
   但 `choice_open` 从未置 True；
4. 引擎主循环 `if not my_action_window and not choice_open: 等待` → 空转到烧绳。

## 触发场景

2026-10-28 10:25:18，`Hearthstone_2026_10_28_09_56_21/Power.log`（第 2 局）：

```
10:25:18.935  DebugPrintEntityChoices id=12 … TaskList= ChoiceType=TARGET CountMin=1 CountMax=1
10:25:18.935    Entities[0]=钢铁魔像  zonePos=3
10:25:18.935    Entities[1]=古神主谋尤格-萨隆 zonePos=2
10:25:18.935    Entities[2]=库区守卫  zonePos=1
10:26:27.227  DebugPrintEntitiesChosen id=12 … 古神主谋尤格-萨隆   ← 69 秒后游戏替我们选的
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/powerlog-1025-target-choice.log`：面板头部 + 候选 + 69 秒后的 Chosen 原文。

## 根因

```python
r"DebugPrintEntityChoices\(\) - id=(\d+) Player=(\S+) TaskList=\d+ ChoiceType=…"
```

`TaskList` 是"这个选择属于哪个 task list"，TARGET 类面板可以为空。写死数字等于
把这一类面板整个丢掉。

## 修复

1. 头部正则改成 `TaskList=\S*`（允许空）；
2. `_do_choice` 增加 `TARGET` 分支：**点场面上的随从**（`target_rect`），
   不是点发现面板的卡牌坐标；盒子点名就用盒子那张，没点名点敌方第一个；
3. 回归用例：空 TaskList 的 TARGET 头部必须能置 `choice_open` 且候选顺序正确。

## 验证

```
tests/test_powerlog_rules.py
  OK   TARGET 面板（TaskList 为空）也能被识别，候选按日志顺序
```

真机日志回放：同一行现在得到 `choice_open=True, choice_type=TARGET, choices=3`；
修前为 `choice_open=False`。

---
id: B-15
state: 已修
module: coords.choices
stage: 选择面板
symptom_key: 「进行选择」4 张大牌面板点了没反应，面板不关、候选不变
patterns: ["选择面板没关"]
root_cause: 用发现面板的 233px 间距去点间距 340px 的大牌面板，落点在两张牌之间
related: [B-05]
reopened_count: 0
fixed_at: 2026-10-27T13:35:00
fp: 5e542c1cdbd9
---

# 15 「进行选择」4 张大牌面板：点在了两张牌之间，面板一直不关

**状态：已修**

## 现象

打出克苏恩仪式后弹出「进行选择」面板（4 张牌）。引擎认得出面板、也去点了，
但点了 15 次都关不掉：

```
[engine]   选择面板[4] 候选 ['BE_013t1', 'BE_013t2', 'BE_013t3', 'BE_013t4']；盒子要 BE_013t1 -> 第 1 个
[step 047] clicked n=1 clicks=[{'tag': 'lclick', 'client': [581, 485], …}]
```

`test/c1` 这局一共 15 行「选择面板」，步数停在 58，最后被人工停掉。

## 触发条件

1. 弹出的是 **`ChoiceType=GENERAL` 的 4 选 1 大牌面板**（克苏恩仪式那类）；
2. 引擎用 `coords.DISCOVER_4` 表计算落点 —— 那张表是按**发现面板**量的，牌心间距 233px；
3. 实际这种面板的牌心间距是 **340px**，于是第 1 个槽的落点 (581,485) 正好落在牌 1 与牌 2 的空隙里。

## 触发场景

2026-10-27 13:30–13:33 `test/c1`（截图已删除）。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/run-c1-choice-panel-loop.log`
- `logs/SOURCES.txt`

## 根因

坐标表选错：`engine._do_choice` 只看候选数 `n`，`n>=4` 就用 `DISCOVER_4`；
但发现面板和「进行选择」面板的布局不同（间距 233px vs 340px）。

截图实测（客户区 1905×982，牌面 y 276..701）：

| 槽 | 牌面 x 范围 | 牌心 |
|---|---|---|
| 1 | 319..574 | 447 |
| 2 | 659..914 | 787 |
| 3 | 999..1254 | 1127 |
| 4 | 1345..1600 | 1473 |

## 修复

1. `coords.CHOICE_GENERAL_4`：按截图量出的四张牌矩形（归一化后 `relative()` 还原为
   319..573 / 659..913 / 998..1252 / 1344..1598，牌心与实测误差 ≤6px）；
2. `Actions.choose_general()`：这些面板用它点；
3. `engine._do_choice` 按 `choice_type` 选表：

```python
elif (st.choice_type or "").upper() == "GENERAL" and n >= 4:
    self.actions.choose_general(idx, n)
else:
    self.actions.choose_discover(idx, n)
```

## 验证（离线）

```
tests/test_choice_geometry.py
  OK   四个牌心与实测一致（误差 <=6px）: [(446,488), (786,488), (1125,488), (1471,488)]
  OK   四个牌心都在牌面内，没有一个落在空隙里
  OK   「进行选择」面板间距 340px 明显大于发现面板 233px（所以不能共用表）
```

真机待验：同一面板下应看到点中的 x 落在 319..574（槽 1）等牌面内，并且面板立即关闭。

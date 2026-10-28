---
id: B-08
state: 未修
module: output.mouse
stage: 任意
symptom_key: 挂作者 csystem.dll 后进程在对局中被静默结束
patterns: []
root_cause: 闭源库内部终止宿主（待定位到具体开关）
related: []
reopened_count: 0
fp: c788004a0798
---

# 08 挂上作者的 csystem.dll 后，进程在进对局几十秒内被静默结束

**状态：未修**

## 现象

开着作者鼠标后端（`mouse_backend = "author"`）跑对局，进程在进入对局后 50~95 秒内消失：

- `finally` 里的收尾一行都没执行（没有 `[rec] 鼠标事件已落盘`、没有 `=== 收工`）；
- 没有任何 traceback（stdout/stderr 都已重定向、`-u` 无缓冲）；
- 退出码是 **0**（`subprocess.run` 实测）；
- 游戏侧没有跟着退出，界面停在"等玩家操作"，看起来像炉石卡住。

## 触发条件

`make_mouse(backend="author")` 加载 `libs/author/csystem.dll` 之后，引擎走到真实点击路径
（换牌/出牌/结束回合）后的几十秒内发生。换成 `mouse_backend = "sendinput"` 后同样的流程不再发生。

## 触发场景

2026-10-26 19:06–19:11，三次连续实测：

| 跑次 | 后端 | 起 | 死 | 用时 | 日志最后一行 |
|---|---|---|---|---|---|
| probe1 | author | 19:06:55 | 19:08:28 | 94s | `[engine] 等待中 mode=GAMEPLAY turn=2 …` |
| probe2 | author | 19:09:5x | 19:10:53 | 60s | `[powerlog] 按括号前进: eid=39 HAND -> PLAY` |
| probe3 | sendinput | 19:12:5x | 存活 3 分钟以上 | — | `[engine] 按盒子换牌: 替换 [2, 3]` |

## 已做的隔离实验（2026-10-26 19:25–19:33）

| 实验 | 做了什么 | 结果 |
|---|---|---|
| 只加载 DLL | `AuthorMouse(...)` 构造后空转 40 秒 | 存活 |
| + `limitMouseRange(False)` | `set_hooks(limit_range=False)` 后 25 秒 | 存活 |
| + `limitMouseRange(True)` | `set_hooks(limit_range=True)` 后 25 秒 | 存活 |
| + 一次真实移动 | `move((0,0) → 客户端中心, hwnd)` 后 20 秒 | 存活 |
| + 一次真实点击 | `left_click((60,491), hwnd)` 后 20 秒 | 存活 |
| + 连续 40 次点击 | 1 秒一次，在两个空白点之间来回移动+点击 | 存活，跑完 40 次 |

**结论：作者库本身（加载 / 开关 / 移动 / 点击 / 连续点击）不会杀进程。**
所以“挂上 csystem.dll 就会死”这个判断被推翻了，真正触发点还在整套流程里（录制钩子、
frida 桥、对局内点击、或游戏侧反作弊），需要继续二分。

## A/B 对照（2026-10-27 01:02–01:09，同一客户端、同一卡组、同一流程）

| 跑次 | 后端 | 结果 |
|---|---|---|
| test/t4 | **author**（csystem.dll） | 进对局 → 换牌「替换 [3]」→ **进程消失**，日志停在 01:03:01，无收尾、无 traceback |
| test/t5 | **sendinput**（我们自己的 SendInput） | 一直活着，**真的在打**：39 步、出牌成功、结束回合「回合已交出」，日志最后是 `等待中 turn=2 cur=2 hand=5 board=1` |

两次唯一不同就是鼠标后端。日志见 `logs/run-t4-author-mulligan-then-died.log` 与
`logs/run-t5-sendinput-playing.log`。

结论修正：作者库单独用（加载 / 开关 / 单次移动 / 单次点击 / 连续 40 次点击）不会杀进程；
**但在整套流程里（frida 桥 + --record 鼠标钩子 + 真实对局点击）跑到换牌/出牌阶段就会把进程带走**。
下一步二分：author + 不开 --record；author + 不挂 frida 桥。

## 当前可用配置

`config.toml` 里 `mouse_backend = "sendinput"` —— 这样能正常打；作者库那条路在定位清楚前不要开。

## 下一步（二分法）

1. 整套流程 + `mouse_backend = "sendinput"`（已跑过一次，probe3 存活 3 分钟以上）；
2. 整套流程 + `author`，但**不开 `--record`**（去掉我们的 LL 鼠标钩子）；
3. 整套流程 + `author` + `--record`，但**不挂 frida 桥**（用固定计划跑）；
4. 三者都在、逐项加回，看在哪一步复现。

哪一步复现，就把那一步的相关日志补进本目录。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/run-probe1-author.log`（作者库，死在「等待中」）
- `logs/run-probe2-author.log`（作者库，死在进对局后）
- `logs/run-probe3-sendinput.log`（sendinput，同一套流程存活）
- `logs/SOURCES.txt`：以上文件各自的原始路径

## 根因（当前判断，待定位到具体开关）

`csystem.dll` 是闭源库，内部有自己的钩子与看门狗。进程被"瞬间终结 + 退出码 0 + 无收尾"
说明不是 Python 层退出，而是库内部调用了进程级终止（或它的钩子把宿主带走）。

待确认：是 **`limitMouseRange(True)`**、**`mouseHook`/`acHook`**，还是**库一加载**就会这样。
下一轮实验：只开作者库、关掉 `limitMouseRange`，看是否还死。

## 修复（未开始）

先定位到具体开关，再决定：

- 若只是 `limitMouseRange` → 关掉它，其余照用作者库；
- 若加载即死 → 放弃作者库，回到 SendInput + 作者坐标表（`mouse_backend = "sendinput"`）。

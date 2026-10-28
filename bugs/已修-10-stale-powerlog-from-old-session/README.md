---
id: B-10
state: 已修
module: input.powerlog
stage: 读日志
symptom_key: 拿上一次会话的 Power.log 当本局，mode 永远 GAMEPLAY
patterns: []
root_cause: latest_log 在全部会话里挑最新
related: []
reopened_count: 0
fp: 9575af2d0df9
---

# 10 客户端这次会话没写 Power.log，脚本拿上一次会话的旧日志空转到超时

**状态：已修**

## 现象

客户端刚起、停在主菜单，跑 `run.py`：

```
[run] 进对局前界面: mode=GAMEPLAY
[nav] to_hub: mode=GAMEPLAY 第1次 (剩 120s)
[nav] 对局已结束，点「点击继续」离开结算界面      ← 连点，界面毫无变化
... 第9次 (剩 97s) / 第17次 (剩 73s)
```

120 秒后进程退出，游戏还停在主菜单——看起来就是"卡住"。

## 触发条件

1. 客户端这一次会话**没有生成 Power.log**：会话目录里只有
   `Hearthstone.log / ExceptionReporter.log / Downloader.log / Login.log / Decks.log /
   Spj.log / LuckyDraw.log`；
2. `PowerLog.latest_log()` 在 `Logs/` 下**所有**会话目录里挑 `Power.log` mtime 最新的那份
   → 挑到上一次会话（`Hearthstone_2026_10_26_18_54_42`，最后写入 19:26:10）的旧文件；
3. 旧文件里最后一局是 `mode=GAMEPLAY`、`finished=True` → `to_hub` 走「结算界面」分支，
   反复点 `(0.50, 0.93)`，而屏幕上根本没有那个按钮。

## 触发场景

- 2026-10-26 20:58 实验 B（同类现象见本目录 `logs/run-t1-nav-loop.log`（实验 B 那次没有单独留存））；
- 2026-10-27 00:52 `test/t1/run.log`：主菜单起跑，40 行日志全是「点继续」，
  进程 00:52:39 退出（当时屏幕：主菜单；截图已删除）。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/run-t1-nav-loop.log`（40 行，全是空点）
- `logs/session-dir-listing.txt`（这次会话目录里到底有哪些文件）
- `logs/SOURCES.txt`

## 根因

`src/hspy/input/powerlog.py` 的 `latest_log()`：

```python
for d in logs.iterdir():          # 遍历所有会话
    f = d / "Power.log"
    best = max(best, f.mtime)     # 挑 mtime 最新的
```

它无法区分"本次会话的日志"和"上一次会话的残留"。

## 修复

`latest_log()` 只看**最新会话目录**：目录里没有 `Power.log` 就返回 `None`，
让上层拿到"没有本局日志"这个事实，而不是拿旧文件继续跑。

## 待验证

修完之后同一场景下应当是：没有 Power.log → 状态为空 → 导航去点「传统对战」，
进对局后本次会话生成 `Power.log`，脚本才开始按真实状态走。

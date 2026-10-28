---
id: B-18
state: 已修
module: input.powerlog
stage: 重放
symptom_key: rebuild() 忽略 pinned 日志，重放的始终是最新会话那一份
patterns: ["rebuild", "pin_log"]
root_cause: rebuild() 里写死 latest_log()，没有优先用 self._path
related: []
reopened_count: 0
fixed_at: 2026-10-27T18:55:00
fp: 90b47cefdff1
---

# 18 rebuild() 忽略 pinned 日志：说好重放这一份，实际读的是最新那一局

**状态：已修**

## 现象

```python
log = PowerLog()
log.pin_log("tests/fixtures/powerlog-sample.log")
st = log.rebuild()
```

期望重放夹具，实际拿到的是**最新会话**的状态：

```
started=False turn=3 my_board=0 hand=0 entities=24
```

同一时刻夹具本身完全正常（修复后同一条命令）：

```
started=True turn=5 my_board=2 entities=90
```

## 触发条件

`PowerLog.rebuild()` 里取文件的写法是：

```python
f = self.latest_log()          # ← 不管有没有 pin 过
```

所以任何“指定一份日志来重放”的调用方（离线夹具、`tests/test_offline.py`、
排查时的单文件回放）都被静默换成了最新会话。

## 触发场景

2026-10-27 18:5x，给 `tests/test_offline.py` 造夹具时发现：夹具里明明有随从，
`rebuild()` 却报 `my_board=0`。同一份夹具用 `_feed()` 逐行喂进去是有随从的。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/rebuild-pinned-after-fix.txt`：修复前后同一条命令的输出对比

## 根因

`rebuild()` 没有优先使用 `self._path`（`pin_log` 设置的路径）。

## 修复

```python
f = self._path if self._path else self.latest_log()
```

## 验证

```
python -X utf8 -c "... pin_log('tests/fixtures/powerlog-sample.log'); st=log.rebuild() ..."
  -> started=True turn=5 my_board=2

tests/test_offline.py  （夹具优先，15 组测试全绿）
```

覆盖：pinned 日志会被重放（test_offline 的夹具路径）；夹具必须能解析出回合与随从

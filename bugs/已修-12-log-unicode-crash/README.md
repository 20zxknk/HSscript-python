---
id: B-12
state: 已修
module: engine._do_play
stage: 任意
symptom_key: 日志里打印 GBK 编不了的字符，抛 UnicodeEncodeError 打断对局
patterns: ["UnicodeEncodeError"]
root_cause: 字符串里带 ⚠ 等非 GBK 字符
related: []
reopened_count: 0
fp: e98890449f80
fixed_at: 2026-10-27T10:55:00

---

# 12 日志里打印 ⚠ 在 GBK 控制台上直接抛 UnicodeEncodeError，把对局打断

**状态：已修**

## 现象

对局打到第 3 回合、刚打出 CATA_210 之后，进程带着 traceback 退出：

```
[step 046] ok:action_effect action=play card=CATA_210 evidence=PLAY块
[engine]   动作前重查(主循环) … → play TIME_026 …
[run] 对局还没结束，脚本退出，**不自动认输**
=== 收工：1 局，统计 {'plans': 7, 'acts': 6, '…'} ===
```

`test/v1/err.log`：

```
Traceback (most recent call last):
  File "run.py", line 308, in main
    result = eng.play_match(...)
  File "src/hspy/engine.py", line 484, in _execute
    self._do_play(plan, st, resolved)
  File "src/hspy/engine.py", line 600, in _do_play
    print(f"[engine]   ⚠ 盒子槽 {box_pos} 不是…")
UnicodeEncodeError: 'gbk' codec can't encode character '\u26a0'
```

## 触发条件

1. 子进程的 stdout 是 GBK（本机默认，未设 PYTHONIOENCODING）；
2. 走到 `engine._do_play` 里「盒子槽位 vs 我们的槽位不一致」那条警告；
3. 该警告的字符串里有 `⚠`（U+26A0），GBK 编不了 → `print` 抛异常 → 整局中断。

## 触发场景

2026-10-27 09:55:33 `test/v1`：第 3 回合打出 CATA_210 后，准备打 TIME_026 时触发。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/err-v1-unicodeencodeerror.log`（traceback 原文）
- `logs/run-v1-before-crash.log`（崩溃前的 run.log）
- `logs/SOURCES.txt`

## 根因

代码里除了 `⚠` 还有 `✓ ✗ ☠ ²` 等 GBK 编不了的字符，分布在 `engine.py`、`state.py`、
`run.py` 和多个脚本里。只要控制台不是 UTF-8，任何一处打印都可能炸。

## 修复

1. 把所有 GBK 编不了的字符换成 ASCII 等价物：`⚠ -> [!]`、`✓ -> [OK]`、`✗ -> [X]`、
   `☠ -> [阵亡]`、`² -> 2`；
2. `run.py` 启动时对 stdout/stderr 调 `reconfigure(errors="replace")` 兜底：
   以后再冒出编码不了的字，最多显示成 `?`，不会再抛异常；
3. 新增 `tests/test_log_encoding.py`：解析 AST，检查所有**字符串常量**能否用 GBK 编码
   （注释和 docstring 不打印，不查）。这条门禁当场抓出 11 处历史遗留。

## 验证

```
python -X utf8 tests/test_log_encoding.py
  OK 字符串常量都能用 GBK 打印（扫了 51 个文件）
```

---
id: B-26
state: 已修
module: win.capture
stage: 收工
symptom_key: 赛后截图抓到空图，PIL 抛 cannot write empty image 把整轮跑挂掉
patterns: ["cannot write empty image", "Traceback"]
root_cause: 截图是诊断用途，空图时未兜底，异常直接冒到主循环
related: []
reopened_count: 0
fp: 120099ef30c6
fixed_at: 2026-10-29T04:55:00
---

# 26 赛后截图抓到空图，把整轮跑挂了

**状态：已修**

## 现象

2026-10-29 03:43，连续跑完第 30 局后，脚本按惯例截一张赛后图，Pillow 报
`ValueError: cannot write empty image`，异常冒到 `run.py` 主循环，整轮退出：

```
=== 第 30 局结果 === finished {...}
Traceback (most recent call last):
  File "run.py", line 351, in main
    win.capture(eng.window.hwnd, f".captures/run_game{games}.png")
  ...
ValueError: cannot write empty image
[run] 对局还没结束，脚本退出
```

## 触发条件

1. 一局结束，`run.py` 调 `win.capture()` 存截图；
2. 那一刻窗口抓不到客户区（最小化/正在关闭/尺寸为 0）；
3. `Image.frombuffer` 得到 0×0，`img.save()` 抛异常；
4. 截图调用没有 try，异常把整轮带崩。

## 触发场景

2026-10-29 03:43，`live-attach4` 那一轮（30 局）收尾时。

## 日志文件

- `logs/run-crash-0343.log`：退出前的 28 行原文（含 traceback）。

## 根因

截图是**诊断**用的，不是主流程；空图时应该跳过，不能把跑了几小时的进程带走。

## 修复

`win.capture()` / `win.capture_window()`：

- 客户区宽高 ≤ 0 时打印一行、返回 `None`；
- `img.save()` 包 try/except，失败也返回 `None`；
- 返回类型改成 `Path | None`，调用方（run.py、probe）本来就不看返回值。

## 验证

- 离线门禁 17/17；
- 手写空窗口场景（`client_rect` 返回 0×0）不再抛异常，只打印“客户区为空，跳过截图”。

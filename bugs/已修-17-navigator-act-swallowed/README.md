---
id: B-17
state: 已修
module: navigator.Navigator
stage: 构造
symptom_key: 构造 Navigator 时传入 act 会抛 UnboundLocalError，且注入的 act 被默认值覆盖
patterns: ["UnboundLocalError", "make_mouse"]
root_cause: make_mouse 在 if 分支里 import，却在分支外使用；并且无条件重新赋值 self.act
related: []
reopened_count: 0
fixed_at: 2026-10-27T18:10:00
fp: ef99efa1c9ef
---

# 17 构造 Navigator 时传 act 会抛 UnboundLocalError，注入的 act 也留不住

**状态：已修**

## 现象

`Navigator(hwnd=..., act=某个 Actions)` 时抛：

```
UnboundLocalError: cannot access local variable 'make_mouse' where it is not associated with a value
```

即使不抛，传进来的 `act` 也会被默认值覆盖——注入形同虚设。

## 触发条件

`Navigator.__post_init__` 原来的写法：

```python
if self.act is None:
    from .output.mouse import make_mouse
self.act = Actions(self.gw, make_mouse(dry_run=False))   # 缩进只到 if 里，这一行在 if 外
```

1. 只有 `act is None` 时才 import；但下一行无条件执行 → `act` 非空时名字不存在 → UnboundLocalError；
2. `self.act = ...` 也无条件执行 → 调用方注入的实例被丢掉。

## 触发场景

2026-10-27 第三方审计（`.captures/2026-10-27-工程质量评估.md`）在复现 `Navigator(act=...)`
时发现。navigator 当时覆盖率为 0%，没人测到过。

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/test-navigator-after-fix.txt`：修复后 `tests/test_navigator.py` 的输出
  （四条契约：注入的 act 不被覆盖、没注入能造、mode 读 sync、click 走 act）
- 复现环境与命令见审计报告 `.captures/2026-10-27-工程质量评估.md`

## 根因

缩进：import 与赋值都在 `if` 的作用域里，但赋值语句跑到了 `if` 外面。

## 修复

抽出模块级 `default_actions(gw)`：

```python
def default_actions(gw: GameWindow) -> Actions:
    from .output.mouse import make_mouse
    return Actions(gw, make_mouse(dry_run=False))

# __post_init__
if self.act is None:
    self.act = default_actions(self.gw)
```

## 验证

```
tests/test_navigator.py
  OK   注入的 act 不会被覆盖
  OK   没注入时能造出默认动作层
  OK   mode() 读的是 sync.pump().mode
  OK   click() 走的是注入的 act
```

覆盖：注入 act 不被覆盖 / 缺省能构造 / mode 与 click 走的都是注入对象

# 鼠标参数

鼠标层的三个节奏参数，全部来自对作者 DLL 的实测（每步 `Sleep(15.8)`、`PAUSE_STEP=7`、
pauseStep=7 时平均每步 26px），**不是拍出来的**。下面这段与源码逐字一致，
由 [`scripts/verify_type_equiv.py`](../../scripts/verify_type_equiv.py) 校验。

## 每步停顿 / 每步像素 / 分段数

一次移动被切成 `PAUSE_STEP` 段，每段之间睡 `STEP_SLEEP_MS` 毫秒；`STEP_PX_AT_DEFAULT`
是 pauseStep=7 时的平均每步像素，用来推算目标距离对应多少步。

<!-- type-equiv: STEP_SLEEP_MS -->
```python type-equiv
# ---- 以下数字是对作者 csystem.dll 的 simulateHumanMoveMouse 实测出来的 ----
# 用 SetCursorPos 逐步移动，每步之间 Sleep：
#   每步耗时 ≈ 15.7~15.9 ms（三组 pauseStep 都是这个值）
#   每步位移按 smoothstep 加减速：起点 7px → 中段 44px → 终点 2px
#   1350px 的移动：pauseStep=7 → 52 步，pauseStep=3 → 210 步，pauseStep=15 → 30 步
#   pauseStep=7 时平均每步 25.9px（≈ 26px）
STEP_SLEEP_MS = 15.8           # 作者 DLL 每步 Sleep 的实测中位数
```

<!-- type-equiv: STEP_PX_AT_DEFAULT -->
```python type-equiv
STEP_PX_AT_DEFAULT = 26.0      # pauseStep=7 时的平均每步像素
```

<!-- type-equiv: PAUSE_STEP -->
```python type-equiv
PAUSE_STEP = 7                 # 作者 ConfigEnum.PAUSE_STEP 默认值
```

## 轨迹形状

移动路径不是直线：先取三次贝塞尔控制点，再用余弦钟形速度
（`t = 0.5 - 0.5 * cos(pi * u)`）分配每段步长，长距离还有 30% 概率过冲再回拉。
落点在矩形内取二维截断高斯（`sigma=0.12`），并与最近 10 次点击保持至少 6px。

这套参数与「模板重放」（[`src/hspy/clone.py`](../../src/hspy/clone.py)）是两条路：
模板重放是默认，参数化版本留作模板库缺失时的回退。两者的判别器偏差分别是 0.77 与 1.65
（见 [0006](../adr/0006-behavior-clone-from-human-data.md)）。

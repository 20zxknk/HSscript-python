# 决策：鼠标自己写，不再调用作者的 csystem.dll

Status: implemented

取代 [0004](0004-use-authors-native-mouse.md)。

## 问题

0004 决定直接调作者的 `csystem.dll`。真机上暴露出两个问题：挂上那个 DLL 之后，进程会在
进对局几十秒内被静默结束（BUG 08），闭源、没有日志、无法定位；DLL 的行为也完全无法验证
和调试，出问题只能猜。

同时另有一条路已经验证可行：我们逆向出了作者的参数（每步 15.8ms、`PAUSE_STEP=7`、
smoothstep 曲线），也用真人数据做出了模板重放（见 [0006](0006-behavior-clone-from-human-data.md)）。

## 决定

自己实现鼠标层，行为对着实测数据抄：

移动用三次贝塞尔路径 + 余弦钟形速度 + 末端过冲修正（`src/hspy/output/mouse.py`）；
落点用矩形内二维截断高斯 + 与最近 10 次点击保持至少 6px；节奏用 `PAUSE_STEP=7` /
`STEP_SLEEP_MS=15.8`，与逆向出来的作者参数一致；另有行为克隆版
（[`src/hspy/clone.py`](../../src/hspy/clone.py)）回放真人录制的轨迹模板，判别器偏差
0.77，而参数化版本是 1.65。

## 后果

仓库里不再需要任何 DLL——`libs/` 已删除，全仓没有 `.dll`/`.exe`。鼠标行为变成可控可测
的代码：`tests/test_mouse_curve.py` 五组、`tests/test_clone.py` 四组，覆盖曲线形状、
落点分布、后端选择。

代价是作者那套配套（`mouseHook`、`acHook`）没有对应实现，只保留行为层面的模仿；也失去了
“对方一直在更新”的隐性维护——作者修过的坑，我们要自己再踩一遍。

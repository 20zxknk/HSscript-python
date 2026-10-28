# 决策：鼠标用作者的 csystem.dll，不自己仿曲线

Status: superseded

Superseded: [0007](0007-own-mouse-no-author-dll.md)——作者 DLL 闭源，挂上后进程会在进对局几十秒内被静默结束（见 BUG 08），鼠标层已改为自己实现。

## 问题

作者的鼠标移动曲线写在闭源 `csystem.dll` 里（`simulateHumanMoveMouse`），Kotlin 层只是
调它。我们当时自己写过 ease-out 插值加抖动，还为了“点不中”加过补偿：点不动就 ±130
试探，成功就把那个点记下来，下次优先用它。

那套补偿把首击被吞误判成坐标错，试出来的点又覆盖了作者本来的坐标表，最后 4 候选面板
必选错——作者的表本来是对的，是我们把它改坏了。

## 决定

直接调作者的库：移动与点击用 `simulateHumanMoveMouse` / `leftClick` / `rightClick`；
坐标语义是客户区坐标加真实 hwnd（实测标定过）；顺手开作者默认的 `limitMouseRange(True)`，
而 `mouseHook` / `acHook` 保持关闭；动作间隔按作者 `delay*` 的实际使用比例抽样
（Short / ShortMedium / Medium / Tiny / Long）。

## 后果

省掉了自己仿曲线的全部工作，坐标表也用作者那份经过验证的。补偿式的“试探/学习”被拿掉，
因为它的前提就是错的：首击被吞不是坐标错。

代价是两个：依赖 `csystem.dll`，还要求 `jvm.dll` 在搜索路径里；库闭源，行为只能靠实测
标定，出问题时没有源码可看。

这条决策后来被 [0007](0007-own-mouse-no-author-dll.md) 取代，因为“闭源只能实测”这件事
在实践中变成了“进程被静默结束且无法定位”。

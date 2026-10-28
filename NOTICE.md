# 来源与许可

> 本仓库（代码、文档、测试、台账、提交信息）由 **DeepSeek v4.1** 生成/改写，未经人工逐行审查。
> 见 [README 的警告](README.md)。

## 代码来源

`src/hspy/` 与 `scripts/` 的实现，是从本地旧仓库 `hs-py`（2026-10-24，提交 `7022d5d`）
搬进干净仓库后继续修的。搬进来之后的主要修改：

1. 窗口比例守卫、点击时不重复激活窗口（修掉出牌/攻击 0 次生效）；
2. Power.log 解析按真机日志重做（槽位、场面、裸 tag 归属、选择面板）；
3. 每一步用游戏侧证据核对（PLAY/ATTACK/POWER 块、回合交出、候选换组、牌离手）；
4. 导航去掉按 ESC、去掉盲点开赛错误；新对局以 Power.log 新段为准；
5. `run.py` 统一入口 + `--attach` 接管进行中的对局；只读自检 `cli.py`。

## 为什么用 Python

上游是 Java/Kotlin（Maven + JavaFX）。本机编译后运行会**异常闪退**（进程能起，进对局前后
无声退出，换 JDK/清缓存都没稳定），所以改成 Python 单进程：不依赖 JVM/JavaFX，出错能直接
看栈。

## 第三方

本项目没有复制上游源码，只把坐标表转写到本仓库：

| 本仓库 | 来源 |
|---|---|
| `src/hspy/geometry.py`、`coords.py` | 上游 [xjw580/Hearthstone-Script](https://github.com/xjw580/Hearthstone-Script) 的 `GameRect` 语义与坐标表（`GameUtil.kt` / `TournamentModeStrategy.kt` / `AdventureModeStrategy.kt`） |

其余全部是独立实现。桥脚本 `recommendation_server.py` **不在本仓库**，默认按路径引用
`../script-main/`（Frida 钩 HSAng 的 Qt 字符串层）。

## 许可

GPL-3.0，全文见 [LICENSE](LICENSE)。

上游是 GPL-3.0，且本项目的坐标表来自上游，属于派生作品，所以沿用同一协议。
MIT、Apache-2.0 这类允许闭源的协议不适用：换过去等于允许别人把这份代码闭源分发，
与上游的 GPL 冲突。

AGPL-3.0 也可以（GPLv3 允许与其组合），但它多一条"网络服务也要开源"，本项目用不上，
所以选 GPL-3.0。

## 使用边界

本机自用：只读游戏自己的 Power.log、只点鼠标，不读写游戏内存、不改游戏文件、不修改盒子
进程。使用它可能违反游戏服务条款，风险由使用者承担。

## 隐私

已提交的证据已脱敏：BattleTag → `玩家#0000`，本机路径 → `<HS_LOGS>` / `<REPO>` 等占位符，
游戏截图已删除。详见 [README 的「隐私」一节](README.md#隐私)。

# 文档

这一页和 `bugs-index.md` 都是 `scripts/build_docs.py` 生成的，别手改。

## 决策记录（ADR）

| 文件 | 决策 |
|---|---|
| [0001-architecture-three-layers.md](adr/0001-architecture-three-layers.md) | 决策：三层架构——日志进、盒子决策、鼠标出 |
| [0002-decision-comes-from-box.md](adr/0002-decision-comes-from-box.md) | 决策：决策完全交给盒子，不自研战术 |
| [0003-no-injection-frida-on-box-only.md](adr/0003-no-injection-frida-on-box-only.md) | 决策：不注入游戏进程，frida 只挂盒子 |
| [0004-use-authors-native-mouse.md](adr/0004-use-authors-native-mouse.md) | 决策：鼠标用作者的 csystem.dll，不自己仿曲线 |
| [0005-bug-ledger-uses-raw-logs.md](adr/0005-bug-ledger-uses-raw-logs.md) | 决策：缺陷台账用原始日志做证据 |
| [0006-behavior-clone-from-human-data.md](adr/0006-behavior-clone-from-human-data.md) | 决策：行为克隆——从真人录制的鼠标数据里学，而不是拍参数 |
| [0007-own-mouse-no-author-dll.md](adr/0007-own-mouse-no-author-dll.md) | 决策：鼠标自己写，不再调用作者的 csystem.dll |

## 手册

| 文件 | 内容 |
|---|---|
| [runbook.md](runbook.md) | 运行手册 |

## 参考

| 文件 | 内容 |
|---|---|
| [coords.md](reference/coords.md) | 坐标表 |
| [layout.md](reference/layout.md) | 仓库布局 |
| [mouse.md](reference/mouse.md) | 鼠标参数 |
| [powerlog.md](reference/powerlog.md) | Power.log 怎么读 |
| [types.md](reference/types.md) | 数据结构 |

## 缺陷台账

25 条，见 [bugs-index.md](bugs-index.md)。

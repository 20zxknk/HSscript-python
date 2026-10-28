# 仓库布局

这一页由 [`scripts/build_layout.py`](../../scripts/build_layout.py) 生成，每个模块的一句话取自它自己的 docstring——改代码不用改这一页，但忘了写 docstring 这里就会显示「（无 docstring）」。

## 顶层

| 目录 | 用途 | 入库 |
|---|---|---|
| `src/hspy/` | 代码：input → decision → output，加引擎 | 是 |
| `tests/` | 不需要真机的测试，含 `fixtures/powerlog-sample.log`（脱敏样例） | 是 |
| `scripts/` | 门禁、生成器、实验脚本（都可重复运行） | 是 |
| `bugs/` | 缺陷台账：一条一个目录，`logs/` 里放原始日志 | 是 |
| `evidence/` | 被文档直接引用的整局证据（如 `stable-v01-r1`） | 是 |
| `docs/` | 手册 / 参考 / 决策记录；`index.md` 与 `bugs-index.md` 是生成物 | 是 |
| `data/` | 行为克隆模板库（入库）；训练权重 `*.pt` `*.joblib` 不入库 | 部分 |
| `test/` | 每次运行的录制产物；被引用的证据会复制进 `bugs/` 或 `evidence/` | 否 |
| `logs/` | 运行日志；`_scratch/` 放一次性排查脚本 | 否 |
| `.captures/` | 截图（点击取证、审计报告） | 否 |
| `records/` | 每局 Power.log 的分段留档（`acceptance.py`、`check_sync.py` 读它） | 否 |
| `.obsidian/` | Obsidian 的个人配置 | 否 |
| `references/` | 界面模板图（`modes/casual.png`、`modes/wild.png`），`navigator.read_mode` 用它比对标题 | 是 |

## `src/hspy/`

| 文件 | 做什么 |
|---|---|
| `src/hspy/actlog.py` | 可对账的动作日志：每一步都记下"脚本怎么想 / 点了哪个像素 / 日志有没有反应"。 |
| `src/hspy/cli.py` | 命令行小工具（不参与对局流程，run.py 才是入口）。 |
| `src/hspy/clone.py` | 行为克隆的鼠标：轨迹从真人录制的模板库里挑，不再用参数化曲线。 |
| `src/hspy/config.py` | 运行期配置 —— 全部自动发现，零写死路径。 |
| `src/hspy/coords.py` | 坐标表 —— 从作者 xjw580/hs-script 逐条抄录，不要"顺手优化"。 |
| `src/hspy/decision/box.py` | 决策层：完全依赖盒子（HSAng 推荐）——通过作者那套 frida 内存桥拿推荐。 |
| `src/hspy/engine.py` | 引擎：轮询盒子推荐并执行，日志只负责同步回合/结束。 |
| `src/hspy/geometry.py` | 坐标几何层 —— 完全照抄作者 xjw580/hs-script 的 GameRect 约定。 |
| `src/hspy/humanize.py` | 像人一样的节奏模型（状态机 + 时序分布），不是"随机乱点"。 |
| `src/hspy/input/card_db.py` | 卡牌元数据：日志里读不到"这是不是随从"时，以卡池为准。 |
| `src/hspy/input/event_types.py` | 事件类型常量 —— 单独一个模块，避免 events/powerlog 循环 import。 |
| `src/hspy/input/powerlog.py` | 输入层：读炉石 Power.log，实时还原对局状态。 |
| `src/hspy/input/screenlog.py` | 输入层：界面状态 —— 照抄作者的 ScreenLogListener。 |
| `src/hspy/input/state.py` | 输入层：对局状态模型。 |
| `src/hspy/modes.py` | 房间流程：启动游戏 → 练习模式 → 进对局（只打旅店老板）。 |
| `src/hspy/navigator.py` | 导航：界面状态机，全部走 Sync 的动作-期望契约。 |
| `src/hspy/output/actions.py` | 输出层语义动作 —— 把"出牌/攻击/技能/结束回合"翻译成作者那套坐标 + 真实鼠标。 |
| `src/hspy/output/mouse.py` | 输出层：真实鼠标（SendInput），语义照抄作者 MouseUtil。 |
| `src/hspy/overlays.py` | 识别挡在主菜单上的覆盖层（目前是「赛事中心」弹窗）。 |
| `src/hspy/record.py` | 对局记录器：鼠标 LL 钩子 + 盒子推荐原文，统一到同一个时钟上。 |
| `src/hspy/sync.py` | 状态同步层 —— 按 DSH 的 event-sourced 模型重写。 |
| `src/hspy/verify.py` | 每一步都有输出 + 断言：让脚本的自述和 Power.log 能逐条对上。 |
| `src/hspy/watchdog.py` | 卡死取证：--debug 时把栈和心跳写到文件，事后能看它卡在哪一行。 |
| `src/hspy/win.py` | Windows 窗口工具：枚举窗口、取客户区、截图、前台。 |

## `scripts/`

| 脚本 | 做什么 |
|---|---|
| `acceptance.py` | 验收报表：把留档的对局逐局列出来（时间 / 对手 / 胜负 / 回合 / 出牌数 / 攻击数）。 |
| `boards_replay.py` | 把一局 Power.log 的每回合场面做成 HTML + JSON，并自证每个数字。 |
| `bug_index.py` | 缺陷台账的机器身份：给每条 bug 一个可重算的指纹，并校验台账一致性。 |
| `build_card_meta.py` | 生成卡牌元数据表 `data/card_meta.json`：{cardId: {name, type, attack, health, cost, text}}。 |
| `build_docs.py` | 生成 docs/index.md 与 docs/bugs-index.md（聚合层永远是生成的，不手写）。 |
| `build_layout.py` | 生成 docs/reference/layout.md：仓库布局（谁在哪、干什么、入不入库）。 |
| `check_adr.py` | 检查 docs/adr/*.md 是否符合决策记录格式（门禁用）。 |
| `check_bug_dupes.py` | 对一份真机日志查重：看它撞上了台账里哪几条（尤其「已修」的）。 |
| `check_links.py` | 检查 .md 里的相对链接目标是否存在（死链门禁）。 |
| `check_sync.py` | 同步自检：把录下来的 Power.log 重放一遍，在每个"选项快照"时刻检查 |
| `clone_play.py` | 让 CloneMouse 在真实窗口上跑一段，录成 mouse.jsonl，供判别器评分。 |
| `coverage_report.py` | 跑不需要真机的测试并出覆盖率报告，低于基线就失败（ratchet，只许涨不许跌）。 |
| `dry_actions.py` | 干跑：用 dry_run 鼠标把整条动作链跑一遍，验证坐标与顺序（不动真实鼠标）。 |
| `dry_engine.py` | 干跑引擎：把真实的盒子推荐（recs_*.jsonl 里的 data）喂给 Engine._execute。 |
| `extract_moves.py` | 从真人的 mouse.jsonl 里提取「移动片段」，归一化成可复用的模板库。 |
| `fetch_card_images.py` | 把需要的卡图下到 data/card_images/<cardId>.png。 |
| `human_record.py` | 录真人操作：装鼠标钩子，把每个事件写进 mouse.jsonl，用来校准 Humanizer。 |
| `human_stats.py` | 对比「真人操作」和「脚本操作」的鼠标统计量，用来校准 Humanizer。 |
| `join3.py` | 把 test/ 里的三份记录按时间对齐，打印"盒子说了什么 / 鼠标点了哪 / 游戏发生了什么"。 |
| `join_actions.py` | 把脚本的动作日志（logs/actions-*.jsonl）和 Power.log 逐条对账。 |
| `lstm_move.py` | LSTM 版轨迹生成（行为克隆的序列模型），用来和模板重放对比。 |
| `make_powerlog_fixture.py` | 从真实 Power.log 切一段脱敏样例做测试夹具（让离线测试真的离线）。 |
| `plot_traces.py` | 把四种轨迹画出来对比：真人 / LSTM 生成 / 模板重放 / 参数化(贝塞尔)。 |
| `powerlog_replay.py` | 把一段 Power.log 还原成一局完整对局，并自己校验自己。 |
| `powerlog_story.py` | 把一局 Power.log 讲成人能读的过程（按回合计，逐事件带原始时间戳）。 |
| `probe_rects.py` | 把「手牌/场面」预测矩形画在当前截图上，肉眼核对坐标有没有偏。 |
| `reopen_bug.py` | 把一条「已修」的 bug 回退成「未修」（复发流程）。 |
| `replay_powerlog.py` | 离线校验：同一份 Power.log，实时 fold 与从头重放必须得到同一状态（DSH 的 replay 不变量）。 |
| `run_all_tests.py` | 跑全部测试并汇总最后一行（门禁用同款）。 |
| `run_loop.py` | 连续跑：一局一个子目录，直到到点。 |
| `shrink_evidence.py` | 把台账里的 mouse.jsonl 压成 .gz，并同步 README 里的文件名。 |
| `train_discriminator.py` | 判别器：把鼠标记录切成 30 秒窗口，提取统计特征，训练分类器区分「真人 / 脚本」。 |
| `train_move_model.py` | 训练一个"轨迹生成"小模型（行为克隆的神经版本），并生成样本供判别器评分。 |
| `verify_bugs.py` | 把若干局的四份材料汇总成「每条 bug 有没有复现」的核对表。 |
| `verify_play_blocks.py` | 核对每条动作在 Power.log 里到底发生了什么（有没有真的 PLAY 块）。 |
| `verify_type_equiv.py` | 文档里的类型 / 常量必须与源码逐字一致——不过期靠这个脚本，不靠自觉。 |
| `window_dump.py` | 列出 HSAng（盒子）的所有窗口：位置、大小、扩展样式（是否点击穿透）。 |

## `tests/`

| 文件 | 管什么 |
|---|---|
| `test_bug_book.py` | 台账自测：文件夹名 / 状态行 / logs 三者必须一致（bugs/README.md 的收录标准）。 |
| `test_choice_geometry.py` | 「进行选择」4 大牌面板的坐标必须落在牌面上，不能落进两张牌之间。 |
| `test_clone.py` | 行为克隆（模板重放）的性质测试。 |
| `test_commit_msg_gate.py` | commit-msg 门禁的自测：真的能拦住该拦的提交。 |
| `test_engine_rules.py` | 引擎决策逻辑的离线回归测试（不需要真机）。 |
| `test_humanize.py` | Humanizer 的分布与状态机测试。 |
| `test_log_encoding.py` | 日志编码门禁：代码里的**字符串常量**必须能被 GBK 编码。 |
| `test_mouse_backend.py` | 鼠标后端：默认参数化（贝塞尔 + 随机落点 + 随机间隔），克隆要显式要。 |
| `test_mouse_curve.py` | 贝塞尔轨迹与高斯落点的性质测试（不需要真机）。 |
| `test_navigator.py` | Navigator 的两个契约：注入的 act 不许被覆盖；没注入时要能造出来。 |
| `test_offline.py` | 离线自检（不碰游戏、不点鼠标）：输入层解析、结果核对、坐标数学。 |
| `test_overlays.py` | 「赛事中心」弹窗判据：米色占比。用真机截图做回归，避免阈值漂移。 |
| `test_powerlog_rules.py` | Power.log 读法规则（docs/reference/powerlog.md）在**实时解析器**里的回归。 |
| `test_slot_arbitration.py` | 槽位裁决：改槽必须两个来源都点头（选项映射 + 手牌列表）。 |
| `test_slot_conflict.py` | B-06 的回归用例：盒子的 hand_position 与卡号冲突时，按游戏选项映射选槽。 |
| `test_type_equiv.py` | 文档里的类型块必须与源码逐字一致（BUG：文档里的类型过期 = 读者照着过期的东西写代码）。 |
| `test_watchdog.py` | 看门狗必须真的能装、能写心跳、能在退出时留 .exit；否则 --debug 只是个空参数。 |

## `bugs/`

一条缺陷一个目录，目录名就是状态：

```
<状态>-<NN>-<slug>/
    README.md      front-matter（身份）+ 现象 / 触发条件 / 场景 / 日志 / 根因 / 修复 / 验证
    logs/          那一局的原始文件，文件名不改
```

状态只有五个：`已修（实机验证）` / `已修` / `未修` / `误报` / `未核实`。
身份由 `scripts/bug_index.py` 校验（指纹、状态一致、verify.logs 存在），
格式由 `tests/test_bug_book.py` 校验（目录名 / 状态行 / logs 三者一致）。

## `docs/`

```
runbook.md              怎么起环境、怎么跑一局、跑不起来怎么查
reference/types.md      数据结构（与源码逐字一致，verify_type_equiv 校验）
reference/coords.md     坐标表（同上）
reference/mouse.md      鼠标参数（同上）
reference/layout.md     这一页（生成物）
adr/NNNN-*.md           决策记录（check_adr 校验格式）
index.md                生成物：决策 / 手册 / 参考 / 台账的总索引
bugs-index.md           生成物：台账索引
```

## 生成物一览

| 生成物 | 谁生成 | 谁检查过期 |
|---|---|---|
| `docs/index.md` | `scripts/build_docs.py` | `build_docs.py --check` |
| `docs/bugs-index.md` | 同上 | 同上 |
| `bugs/README.md` | 同上 | 同上 |
| `docs/reference/layout.md` | `scripts/build_layout.py` | `build_layout.py --check` |

## 不入库的东西

运行产物（`test/`、`logs/`、`.captures/`、`records/`）、工具缓存（`__pycache__`、
`.pytest_cache`、`.ruff_cache`）、训练权重（`data/*.pt`、`data/*.joblib`）、
Obsidian 配置（`.obsidian/`）、本机配置（`config.toml`）。
规则都在 [`.gitignore`](../../.gitignore)，改了忽略规则记得同步这一页。


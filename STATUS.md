# 项目状态

更新：2026-10-29

## 结论

可用。能连续打完对局，不需要人工干预，胜率 60% 以上。

## 对局数据

| 时段 | 局数 | 胜 | 负 | 胜率 |
|---|---|---|---|---|
| 10-28 16:22–21:22 | 42 | 30 | 12 | 71% |
| 10-28 22:55–10-29 03:43 | 30 | 19 | 11 | 63% |
| 10-28 12:30–12:58 | 5 | 4 | 1 | 80% |
| 合计（同一客户端会话） | 83 | 53 | 30 | 64% |

数据来自游戏 `Power.log` 的 `PLAYSTATE`，不是脚本自报。

## 稳定性

整夜 30 局（22:55–03:43）：

| 指标 | 数值 |
|---|---|
| 计划 / 执行 | 1289 / 1283 |
| 断言拦截 | 6（0.2 次/局） |
| `swallowed` | 451（15 次/局，多为选择面板重试） |
| 轮到我却「等待中」 | 0 |
| 进程退出 | 1 次（赛后截图空图，[BUG 26](bugs/已修-26-empty-screenshot-kills-run/README.md)，已修） |

## 已修复的关键问题

- [BUG 20](bugs/已修-20-option-zone-pos-stale/README.md)：手牌槽位读了选项括号里的旧 `zonePos`，`hand_slot` 每 6 步失败一次。
- [BUG 21](bugs/已修-21-powerlog-tasklist-ownership/README.md)：裸 `tag=` 归属漏了 `SHOW_ENTITY` / `BLOCK_START`，且跳过 `PowerTaskList`。
- [BUG 22](bugs/已修-22-card-db-membership/README.md)：幸运币被当非卡牌、附魔/地标被当随从。
- [BUG 23](bugs/已修-23-tasklist-current-player-replay/README.md)：`CURRENT_PLAYER` 被重放，操作窗口提前关闭，整回合空过。
- [BUG 24](bugs/已修-24-target-choice-tasklist-empty/README.md)：`ChoiceType=TARGET` 的 `TaskList=` 为空，选目标面板被忽略。
- [BUG 25](bugs/已修-25-tournament-timeout-race/README.md)：新对局已开始，导航仍判定超时。
- [BUG 26](bugs/已修-26-empty-screenshot-kills-run/README.md)：赛后截图空图导致整轮退出。

## 已知问题

- 按局统计不重置：`第 N 局结果` 里的数字是累计值。
- 选择面板偶尔仍报「面板没关」：实际会关，多等 1–2 秒。
- 客户端偶发冻结：画面与日志同时停止，需要重启客户端。
- 慢局会被单局上限截断：默认 900s，可用 `--seconds` 调整。

## 运行

```powershell
python run.py --games 5                 # 打 5 局
python run.py --games 0 --seconds 1800  # 一直打
python run.py --attach                  # 接管进行中的对局
```

环境准备与排错见[运行手册](docs/runbook.md)。

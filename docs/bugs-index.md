# 缺陷台账（自动生成，勿手改）

共 25 条。原始日志在各条目的 `logs/` 下，文件名保持原样。

| 目录 | 状态 | 标题 | 三份日志 |
|---|---|---|---|
| [已修-01-rival-minions-stuck-in-hand](../bugs/已修-01-rival-minions-stuck-in-hand/README.md) | 已修 | 01 对手随从永远进不了 `rival_board`（停在“手上”） | — |
| [已修-06-card-usable-wrong-entity](../bugs/已修-06-card-usable-wrong-entity/README.md) | 已修 | 06 用残缺的手牌名单查"这张牌能不能打"，抓到别的实体，合法的牌被拦 3 分半钟 | [OK] |
| [已修-10-stale-powerlog-from-old-session](../bugs/已修-10-stale-powerlog-from-old-session/README.md) | 已修 | 10 客户端这次会话没写 Power.log，脚本拿上一次会话的旧日志空转到超时 | — |
| [已修-11-new-match-waits-for-mulligan](../bugs/已修-11-new-match-waits-for-mulligan/README.md) | 已修 | 11 进对局的判据要求「换牌面板还开着」，进晚了就白等 60 秒再点「继续」搅局 | — |
| [已修-12-log-unicode-crash](../bugs/已修-12-log-unicode-crash/README.md) | 已修 | 12 日志里打印 ⚠ 在 GBK 控制台上直接抛 UnicodeEncodeError，把对局打断 | — |
| [已修-14-tournament-modal-blocks-hub](../bugs/已修-14-tournament-modal-blocks-hub/README.md) | 已修 | 14 主菜单被「赛事中心」弹窗挡住时，导航只会在 HUB 上空点到超时 | — |
| [已修-15-choice-general-panel-geometry](../bugs/已修-15-choice-general-panel-geometry/README.md) | 已修 | 15 「进行选择」4 张大牌面板：点在了两张牌之间，面板一直不关 | — |
| [已修-17-navigator-act-swallowed](../bugs/已修-17-navigator-act-swallowed/README.md) | 已修 | 17 构造 Navigator 时传 act 会抛 UnboundLocalError，注入的 act 也留不住 | — |
| [已修-18-rebuild-ignores-pinned-log](../bugs/已修-18-rebuild-ignores-pinned-log/README.md) | 已修 | 18 rebuild() 忽略 pinned 日志：说好重放这一份，实际读的是最新那一局 | — |
| [已修-19-slot-arbitration-stale-map](../bugs/已修-19-slot-arbitration-stale-map/README.md) | 已修 | 19 选项映射旧一拍就改错槽：hand_slot 断言失败，每 6 步重试一次 | — |
| [已修-20-option-zone-pos-stale](../bugs/已修-20-option-zone-pos-stale/README.md) | 已修 | 20 选项括号的 zonePos 旧一拍：`hand_slot` 每 6 步失败一次，整局卡死 | — |
| [已修-21-powerlog-tasklist-ownership](../bugs/已修-21-powerlog-tasklist-ownership/README.md) | 已修 | 21 裸 `tag=` 的归属缺了 SHOW_ENTITY / BLOCK_START，PowerTaskList 又被整段跳过 | — |
| [已修-22-card-db-membership](../bugs/已修-22-card-db-membership/README.md) | 已修 | 22 手牌/场面的"成员判定"：幸运币被排除、附魔和地标被算成随从 | — |
| [已修-23-tasklist-current-player-replay](../bugs/已修-23-tasklist-current-player-replay/README.md) | 已修 | 23 `CURRENT_PLAYER` 被重放一次，整回合的"能操作"窗口又关上了 | — |
| [已修-24-target-choice-tasklist-empty](../bugs/已修-24-target-choice-tasklist-empty/README.md) | 已修 | 24 `ChoiceType=TARGET` 的头部 `TaskList=` 是空的，整个面板被无视 | — |
| [已修-25-tournament-timeout-race](../bugs/已修-25-tournament-timeout-race/README.md) | 已修 | 25 新对局已经开了，导航还在 TOURNAMENT 里点到超时 | — |
| [已修-26-empty-screenshot-kills-run](../bugs/已修-26-empty-screenshot-kills-run/README.md) | 已修 | 26 赛后截图抓到空图，把整轮跑挂了 | — |
| [已修（实机验证）-02-bridge-stdout-off-by-one](../bugs/已修（实机验证）-02-bridge-stdout-off-by-one/README.md) | 已修（实机验证） | 02 读桥的 stdout 错位一轮，拿到的永远是上一次的推荐 | [OK] |
| [已修（实机验证）-03-hand-size-counts-zonePos-0](../bugs/已修（实机验证）-03-hand-size-counts-zonePos-0/README.md) | 已修（实机验证） | 03 手牌张数把 `zonePos=0` 的分身算成手牌，布局排宽 | [OK] |
| [已修（实机验证）-04-option-snapshot-resurrects-played-card](../bugs/已修（实机验证）-04-option-snapshot-resurrects-played-card/README.md) | 已修（实机验证） | 04 选项快照把已打出的牌塞回手牌、并把位置钉回旧值 | [OK] |
| [未修-05-choice-panel-not-polled](../bugs/未修-05-choice-panel-not-polled/README.md) | 未修 | 05 选择面板开着时引擎当成“不是我的回合”，整局空转 | [OK] |
| [未修-07-mulligan-hand-unreadable](../bugs/未修-07-mulligan-hand-unreadable/README.md) | 未修 | 07 换牌阶段读不到起手张数，整轮换牌被跳过（还打了“换牌完成”） | [OK] |
| [未修-08-author-dll-kills-process](../bugs/未修-08-author-dll-kills-process/README.md) | 未修 | 08 挂上作者的 csystem.dll 后，进程在进对局几十秒内被静默结束 | — |
| [未修-09-offline-reconnect-dialog-unhandled](../bugs/未修-09-offline-reconnect-dialog-unhandled/README.md) | 未修 | 09 客户端掉线弹「重新连接」时，导航不认识这个弹窗，只会在底部空点到超时 | — |
| [未修-16-attack-click-no-effect](../bugs/未修-16-attack-click-no-effect/README.md) | 未修 | 16 攻击点了没反应：日志 seq 冻住，同一步连续重试 10 次以上 | — |

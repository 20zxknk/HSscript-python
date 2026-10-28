# 运行手册

从零把环境跑起来，以及跑不起来时按什么顺序查。

相关：[三层架构](adr/0001-architecture-three-layers.md) · [行为克隆](adr/0006-behavior-clone-from-human-data.md) ·
[数据结构](reference/types.md) · [坐标表](reference/coords.md) · [鼠标参数](reference/mouse.md)

## 安装

Python 3.11+（开发机 3.12）。运行只要三个包：

```powershell
pip install pywin32 pillow pyyaml
```

`torch` 只有跑神经轨迹的实验脚本（`scripts/lstm_move.py`）要用，正常打牌不用装。

## 开跑前确认四件事

每一件都能让脚本卡住，而且卡住的样子不一样。

**① 炉石要经战网启动。** 直接跑 `Hearthstone.exe`，进游戏后会崩，日志里是：

```
[Services] Service Locator Shutdown Complete. Some services are in failure state
AssetBundle.Unload could not complete
```

`src/hspy/modes.py` 的 `launch_game()` 已经按正确方式做了：从注册表找 Battle.net，再执行
`Battle.net.exe --exec="launch WTCG"`。

**② 盒子要在自己的目录下启动。** 换个目录启动，Qt 起不来：

```powershell
Start-Process "<BOX_DIR>\HSAng.exe" -WorkingDirectory "<BOX_DIR>"
```

代码只按进程名 `HSAng.exe` 找窗口，找不到就报「盒子没开」。

**③ `log.config` 要有这几段。** 文件在 `%LOCALAPPDATA%\Blizzard\Hearthstone\log.config`，
缺段时日志根本不写：

```powershell
Select-String -Path "$env:LOCALAPPDATA\Blizzard\Hearthstone\log.config" -Pattern '^\[(Power|LoadingScreen|Screen|Decks|Arena)\]'
```

五行都命中才算够。

**④ 盒子要真的连上这一局。** 没连上时桥只返回空推荐，脚本会一直「无方案」。看盒子日志
`%TEMP%\Log\HSAParasiteMother.log`，应该有两行：

```
[ParasiteMother::Context::onConnected @509]: named pipe connected
[ParasiteMother::Context::onInitCommonServiceResponse @754]: service init: succ=true
```

## 跑

```powershell
python -u run.py --record test\r1 --games 1 --mode standard --deck 1 --seconds 900
```

只跑排名（`--mode` 支持 `casual` / `standard` / `wild`，默认 `casual`，这里只用 `standard`）。

快攻卡组把 `config.toml` 的 `think_scale` 调成 0.3（思考硬上限 1.5s）。快攻一回合就几秒，
长考反而像脚本，也真会烧绳；控制/组合技保持 1.0 就行。

跑完 `test\r1` 里是这几样：

```
mouse.jsonl             点了哪儿
recommendations.jsonl   盒子给过什么
powerlog_story.md       游戏侧发生了什么
README.md               三份材料的出处
```

`run.log` 不是 `run.py` 写的，是 `scripts\run_loop.py` 把 stdout 重定向出来的。单跑上面那条
命令，日志只在窗口里滚。

连续跑、每局留 `run.log`：

```powershell
python -u scripts\run_loop.py --folder test --hours 1.5 --mode standard --deck 1
```

它给每局建一个 `001-HHMMSS` 目录。

想抓卡死就加 `--debug`：每 15 秒把全线程栈 dump 到 `watchdog-<时间>.stack`，另外有 `.beat`
心跳；正常退出会多一个 `.exit`，没有就是被杀或崩的。**长跑别开 `--debug`**，faulthandler
和原生代码抢线程，跑久了可能把进程带崩（[BUG 23 的排查记录](../bugs/已修-23-tasklist-current-player-replay/README.md)）。

## 跑完先看什么

```powershell
Select-String -Path test\r1\run.log -Pattern 'swallowed|FAIL|等起手|无方案'
```

`swallowed` 是「点了但游戏没认」，`FAIL` 是断言没过，`等起手` 是换牌阶段读不到张数。
每条都能在[缺陷台账](bugs-index.md)里找到对应条目。

## 跑不起来怎么办

**`找不到炉石窗口`**：客户端自己退了。`Get-Process Hearthstone` 确认，按 ① 重新启动。

**卡在 HUB 空点**：

```
[nav] HUB 卡住 4 次（这个界面没有可点的返回，继续等）
```

主菜单被「赛事中心」弹窗盖住了（[BUG 14](../bugs/已修-14-tournament-modal-blocks-hub/README.md)）。
抓张客户区截图确认；临时办法是点客户区 `(72%, 22%)` 关掉弹窗。

**卡在 FATAL_ERROR**：客户端进了错误界面，通常是崩溃残留，重启客户端。

**换牌一直「等起手张数」**：

```
[engine] 等起手张数… n=0 hand=0 hint=0
```

换牌实体还没落定，或读不到带卡号的 HAND 实体（[BUG 07](../bugs/未修-07-mulligan-hand-unreadable/README.md)）。
这一轮会放弃换牌，不是卡死。

**推荐一直是空的**：盒子没连上（见 ④），或者还在换牌/开局动画。看 `recommendations.jsonl`
里 `plans` 是不是空就能确认。

**启动就退出，提示正在对局中**：客户端里有局没打完。`--concede` 只对本进程打的那一局有效，
启动时遇到残留对局脚本会直接返回 1，需要手工打完或放弃。

## 仓库布局

```
src/hspy/        代码（input / decision / output / engine）
tests/           不需要真机的测试 + fixtures/powerlog-sample.log（脱敏样例）
scripts/         门禁与工具（可重复运行）
bugs/            缺陷台账：一条一个目录，logs/ 里是原始日志
evidence/        被文档引用的整局证据
docs/            runbook / reference / adr；index 与 bugs-index 由 build_docs 生成
test/            每局录制产物（不入库）
logs/            运行日志（不入库）
data/            行为克隆模板（入库）与训练权重（不入库）
```

## 命令行

| 参数 | 默认 | 作用 |
|---|---|---|
| `--games N` | 0（不限） | 跑几局 |
| `--record DIR` | 不录 | 传了才录制 |
| `--mode NAME` | `casual` | 模式；这里只用 `standard` |
| `--deck N` | 1 | 卡位 |
| `--seconds N` | 900 | 单局上限 |
| `--minutes N` | 0（不限） | 整轮预算，和 `--games` 取先到者 |
| `--debug` | 关 | 看门狗（短跑排查用） |
| `--probe` | 关 | 每次点击前截图标落点 |
| `--concede` | 关 | 退出时认输本进程的对局 |
| `--close-game` | 关 | 结束时关客户端 |
| `--attach` | 关 | 挂到已在跑的对局 |

## 门禁与测试

提交时（`.githooks/pre-commit` → `pre-push`）：

```
scripts/check_adr.py              决策记录格式
scripts/verify_type_equiv.py      文档里的类型/常量与源码逐字一致
scripts/bug_index.py --check      台账身份
tests/test_bug_book.py            目录名 / 状态行 / logs 一致
scripts/build_docs.py --check     生成物是否过期
scripts/check_links.py            死链
```

全量测试：`python -X utf8 scripts/run_all_tests.py`。CI 跑的是同一份清单。

# hspy

自用的炉石传说自动打牌脚本：读 `Power.log`、取网易盒子的推荐、用真实鼠标执行。

仓库：<https://github.com/20zxknk/HSscript-python>

文档：[docs/index.md](docs/index.md)

## 状态

可用，但不是稳定版。2026-10-29 连续 30 局 19 胜 11 负；当天累计 83 局 53 胜 30 负。
数据与已知问题见 [STATUS.md](STATUS.md)。

自动打牌可能违反游戏服务条款并导致封号。全部代码由 DeepSeek v4.1 生成，未逐行人工审查。

## 运行

### 从源码

```powershell
pip install pywin32 pillow pyyaml
python run.py
```

需要 Windows、Python 3.11+、炉石客户端和网易盒子。环境准备见[运行手册](docs/runbook.md)。

### 常用参数

```powershell
python run.py --games 5                 # 打 5 局
python run.py --record test1            # 录制
python run.py --attach                  # 接管进行中的对局
```

完整参数见[运行手册](docs/runbook.md#命令行)。

## 开发

```powershell
python -X utf8 scripts/run_all_tests.py   # 全部离线测试
python -X utf8 -m pytest                  # 标准 pytest
```

目录与门禁见[仓库布局](docs/reference/layout.md)。

## 与上游

坐标表转写自 [xjw580/Hearthstone-Script](https://github.com/xjw580/Hearthstone-Script)（GPL-3.0）；
其余代码为独立实现。来源与依赖见 [NOTICE.md](NOTICE.md)。

## 许可

GPL-3.0，见 [LICENSE](LICENSE)。

---

有用记得点个 Star。

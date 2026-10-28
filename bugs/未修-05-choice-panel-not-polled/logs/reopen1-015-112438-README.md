# 本目录：一局的三份对照记录

| 文件 | 内容 | 时间字段 |
|---|---|---|
| `powerlog_story.md` | 这一局 Power.log 的逐事件叙述（回合 / 出牌 / 攻击 / 阵亡 / 结算） | 每行前 `` `HH:MM:SS.ffffff` `` |
| `recommendations.jsonl` | 每次向盒子要推荐收到的原文（`plans` + `raw_rec` + 桥返回的整行 JSON） | `t`（毫秒）+ `ts` |
| `mouse.jsonl` | 鼠标低层钩子记录（移动/按下/抬起/滚轮） | `t`（毫秒）+ `ts` |

## 怎么对照

1. 时间基准是同一台机器的本地时间：Power.log 行首 `D HH:MM:SS.fffffff`、
   另两份的 `t`（`HH:MM:SS.mmm`）可以直接对。
2. `mouse.jsonl` 每条有：
   - `sx/sy` 屏幕坐标，`cx/cy` 客户区坐标（客户区原点按窗口位置动态刷新）；
   - `injected=1` 表示这一下是脚本用 SendInput 发的，`0` 是物理鼠标（你自己动的）。
3. `recommendations.jsonl` 每条有 `n`（方案数）、`plans`（已解析字段）、
   `raw_rec`（盒子原始结构，含 `data/actionName/card/position`）、`raw`（桥那一行 JSON）。
4. 建议的读法：先按 `recommendations.jsonl` 找到某一步推荐 → 用它附近的 `t`
   去 `mouse.jsonl` 找那两下点击（`injected=1`）→ 再去 `powerlog_story.md` 找
   同一秒的游戏事件，就能看出"盒子说了什么 / 我们点了哪 / 游戏实际发生了什么"。

- Power.log 来源：`<HS_LOGS>\Hearthstone_2026_10_27_10_58_18\Power.log`
- 叙述起点偏移：`2191348` 字节（从该偏移往回找最近的 `CREATE_GAME`）

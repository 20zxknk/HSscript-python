---
id: B-02
state: 已修（实机验证）
module: decision.box
stage: 读桥
symptom_key: 读桥 stdout 错位一轮，拿到的永远是上一次的推荐
patterns: []
root_cause: 握手阶段把状态行当计划行
related: []
reopened_count: 0
verify: {build: "51254d0", logs: "bugs/已修（实机验证）-02-bridge-stdout-off-by-one"}
fp: 4e771789585c
fixed_at: 2026-10-25T13:00:00

---

# 02 读桥的 stdout 错位一轮，拿到的永远是上一次的推荐

**状态：已修（实机验证）**

## 名称

`bridge-stdout-off-by-one`

## 现象

盒子在 `03:36:12.806` 就产出了 `play TIME_025`，我们直到 `03:36:40.511` 才收到；
期间每次 `SCAN` 拿到的都是**上一次查询的应答**（payload 里的 `timestamp`
恰好等于上一次查询的时间）。

## 触发条件

桥 `recommendation_server.py` 启动时往 stdout 打**两行**：
`{"status":"loading"}` 和 `{"status":"ready"}`；
我们的 `BoxBridge._handshake()` 只读了一行，于是队列里永远多一行，
**之后每次 `scan()` 读到的都是上一次 `SCAN` 的应答**。

## 触发场景

test9 第 2、3 回合（`03:36:00`–`03:36:40`）：

```
03:36:01.175  盒子 optionId=3 end_turn
03:36:12.806  盒子 optionId=6 play TIME_025     ← 新决策
03:36:12.498  我们查询 → 拿到 optionId=3（timestamp=03:36:01.175）
03:36:18.267  我们查询 → 拿到 optionId=3（timestamp=03:36:12.498）
03:36:40.511  我们查询 → 才拿到 optionId=6
```

## 日志文件（原始文件，直接放在本目录 `logs/` 下）

- `logs/mouse.jsonl.gz`（102028 字节）
- `logs/powerlog_story.md`（2741 字节）
- `logs/recommendations.jsonl`（13849 字节）
- `logs/test10-mouse.jsonl.gz`（246856 字节）
- `logs/test10-powerlog_story.md`（6109 字节）
- `logs/test10-recommendations.jsonl`（91963 字节）
- `logs/SOURCES.txt`：以上文件各自的原始路径

文件名保持原样，未改；`SOURCES.txt` 里写了每个文件的出处。

## 根因

```python
# 旧代码：只读一行
line = self._readline(timeout=self.timeout)
```

桥先打 `loading` 再打 `ready`，握手只吃掉一行 → 之后所有应答错位一轮。

## 修复

- `_handshake()`：一直读到 `status == "ready"`（跳过 `loading`、非 JSON 行）；
- `scan()`：读到含 `"plans"` 的那一行为止（最多跳 4 行，其余打日志）。

## 验证

test10 全 15 个 `optionId` 与我们收到的顺序完全一致，延迟 0.02~0.45 s。

## 证据（原始日志）

本目录 `logs/` 下的原始文件（可直接 grep）：

```
logs/mouse.jsonl.gz    ← test9\mouse.jsonl.gz
logs/recommendations.jsonl    ← test9\recommendations.jsonl
logs/powerlog_story.md    ← test9\powerlog_story.md
logs/test10-mouse.jsonl.gz    ← test10\mouse.jsonl.gz
logs/test10-recommendations.jsonl    ← test10\recommendations.jsonl
logs/test10-powerlog_story.md    ← test10\powerlog_story.md
```

核对方式：在 `logs/` 里按 README 上的时间戳/卡号直接搜；三份文件（鼠标 / 盒子应答 / 游戏侧叙述）互相对照。

"""把一条「已修」的 bug 回退成「未修」（复发流程）。

    python -X utf8 scripts/reopen_bug.py --bug 05 --logs test/015-112438

做四件事：
  1. 目录名 已修* -> 未修，README 的 state 同步改；
  2. 把这次复发的原始日志复制进该条目的 logs/（不改名，带来源前缀）；
  3. README 追加「复发记录」段（时间、日志、现象）；
  4. front-matter 的 reopened_count +1。

为什么不新建一条：复发要挂在原条目上，才能看出「这个修复到底有没有用」。
"""
from __future__ import annotations

import argparse
import datetime
import io
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUGS = ROOT / "bugs"


def find(num: str) -> pathlib.Path:
    hits = [d for d in BUGS.iterdir() if d.is_dir() and d.name.split("-")[1:2] == [num]]
    if not hits:
        print(f"找不到 B-{num}", file=sys.stderr)
        raise SystemExit(2)
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bug", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    d = find(a.bug)
    state = d.name.split("-")[0]
    if not state.startswith("已修"):
        print(f"B-{a.bug} 当前是「{state}」，不是已修，无需 reopen")
        return 1

    logs_src = pathlib.Path(a.logs)
    if not logs_src.exists():
        print(f"日志目录不存在：{logs_src}", file=sys.stderr)
        return 2

    readme = d / "README.md"
    text = io.open(readme, encoding="utf-8").read()
    end = text.find("\n---", 3)
    front, body = text[3:end], text[end + 4:]
    front = re.sub(r"^state: .*$", "state: 未修", front, count=1, flags=re.M)
    m = re.search(r"^reopened_count: (\d+)$", front, flags=re.M)
    n = int(m.group(1)) + 1 if m else 1
    if m:
        front = re.sub(r"^reopened_count: \d+$", f"reopened_count: {n}", front, count=1, flags=re.M)
    else:
        front = front.rstrip() + f"\nreopened_count: {n}\n"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 复制日志
    copied = []
    for f in sorted(logs_src.glob("*")):
        if not f.is_file() or f.stat().st_size == 0:
            continue
        target = d / "logs" / f"reopen{n}-{logs_src.name}-{f.name}"
        shutil.copy(f, target)
        copied.append(target.name)

    # 正文顶部那行 **状态：…** 也要改（test_bug_book 读的是它）
    body = re.sub(r"^\*\*状态：[^*]*\*\*$", "**状态：未修**", body, count=1, flags=re.M)

    body = body.rstrip() + f"""

## 复发记录 #{n}（{stamp}）

- 症状：{a.note or "与本文现象相同"}
- 原始日志：{", ".join(f"`logs/{c}`" for c in copied) or "（来源目录里没有非空文件）"}
- 来源：`{logs_src}`

状态已改回「未修」：这条修复在真机上没有生效，先别当已修看。
"""
    io.open(readme, "w", encoding="utf-8", newline="\n").write("---" + front + "\n---" + body)

    new = d.with_name("未修-" + d.name.split("-", 1)[1])
    d.rename(new)
    print(f"B-{a.bug}: {d.name} -> {new.name}（reopened_count={n}，附日志 {len(copied)} 个）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""检查 docs/adr/*.md 是否符合决策记录格式（门禁用）。

    python -X utf8 scripts/check_adr.py          # 检查
    python -X utf8 scripts/check_adr.py --list    # 列出现有条目与状态

规则（本脚本是唯一依据；说明见 docs/runbook.md）：

  1. 第一行必须是 `# 决策：<标题>`；
  2. 第 3 行必须是 `Status: proposed|implemented|rejected|superseded`；
  3. 三个必需段按顺序出现：`## 问题`、`## 决定`、`## 后果`；
  4. `## 决定` 段里不许出现未来时（将/以后会/计划要/待实现）——那是提案体；
  5. `superseded` 必须写 `Superseded:` 行且链接到存在的文件；
  6. 正文里的相对链接必须指向存在的文件；
  7. 文件名必须是 `NNNN-<slug>.md`，编号不重复。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADR = ROOT / "docs" / "adr"
STATUSES = ("proposed", "implemented", "rejected", "superseded")
SECTIONS = ("## 问题", "## 决定", "## 后果")
FUTURE = ("将", "以后会", "计划要", "待实现", "计划在")
LINK = re.compile(r"\]\(([^)#]+?)(?:#[^)]*)?\)")


def check() -> int:
    errs: list[str] = []
    seen: dict[str, str] = {}
    files = sorted(ADR.glob("*.md"))
    if not files:
        errs.append("docs/adr/ 下没有 .md")
    for f in files:
        rel = f"docs/adr/{f.name}"
        m = re.match(r"^(\d{4})-.+\.md$", f.name)
        if not m:
            errs.append(f"{rel}: 文件名必须是 NNNN-<slug>.md")
            continue
        num = m.group(1)
        if num in seen:
            errs.append(f"{rel}: 编号 {num} 与 {seen[num]} 重复")
        seen[num] = f.name

        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines or not lines[0].startswith("# 决策："):
            errs.append(f"{rel}: 第一行必须是 `# 决策：<标题>`")
        status_line = next((l for l in lines[:6] if l.startswith("Status:")), "")
        status = status_line.split(":", 1)[1].strip() if status_line else ""
        if status not in STATUSES:
            errs.append(f"{rel}: Status 必须是 {'/'.join(STATUSES)}，实际 {status!r}")
        if status == "superseded":
            sup = next((l for l in lines[:10] if l.startswith("Superseded:")), "")
            if not sup:
                errs.append(f"{rel}: superseded 必须写 `Superseded: [NNNN](…md)`")

        # 段顺序
        pos = []
        for sec in SECTIONS:
            idx = next((i for i, l in enumerate(lines) if l.strip() == sec), None)
            if idx is None:
                errs.append(f"{rel}: 缺少 `{sec}`")
            pos.append(idx)
        if all(p is not None for p in pos) and pos != sorted(pos):
            errs.append(f"{rel}: 段落顺序必须是 问题 → 决定 → 后果")

        # 决定段不许未来时
        if pos[1] is not None:
            start = pos[1]
            end = pos[2] if pos[2] is not None else len(lines)
            body = "\n".join(lines[start:end])
            for w in FUTURE:
                if w in body:
                    errs.append(f"{rel}: `## 决定` 里出现未来时「{w}」（决策段要写现在的事实）")

        # 相对链接
        for link in LINK.findall("\n".join(lines)):
            if link.startswith(("http://", "https://", "mailto:", "obsidian://")):
                continue
            target = (f.parent / link).resolve()
            if not target.exists():
                errs.append(f"{rel}: 链接指向不存在的 {link}")

    if errs:
        print("决策记录格式不合格：", file=sys.stderr)
        for e in errs:
            print("  [X]", e, file=sys.stderr)
        return 1
    print(f"OK 决策记录 {len(files)} 篇：标题 / 状态 / 三段 / 无未来时 / 链接均可解析")
    return 0


def show() -> int:
    for f in sorted(ADR.glob("*.md")):
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        title = lines[0][len("# 决策："):] if lines and lines[0].startswith("# 决策：") else "?"
        status = next((l.split(":", 1)[1].strip() for l in lines[:6] if l.startswith("Status:")), "?")
        print(f"{f.name:<44}{status:<12}{title[:44]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    return show() if a.list else check()


if __name__ == "__main__":
    raise SystemExit(main())

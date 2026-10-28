"""生成 docs/index.md 与 docs/bugs-index.md（聚合层永远是生成的，不手写）。

    python -X utf8 scripts/build_docs.py           # 生成
    python -X utf8 scripts/build_docs.py --check   # 检查生成物是否与仓库一致（CI 用）
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BUGS = ROOT / "bugs"


def _title(text: str, fallback: str) -> str:
    """取文档标题：跳过 YAML front-matter，找第一行 `# ` 标题。"""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i, l in enumerate(lines[1:], start=1):
            if l.strip() == "---":
                lines = lines[i + 1:]
                break
    for l in lines:
        if l.startswith("# "):
            return l[2:].strip()
    return fallback


def bug_rows() -> list[tuple[str, str, str]]:
    rows = []
    for d in sorted(BUGS.iterdir()):
        if not d.is_dir():
            continue
        readme = d / "README.md"
        if not readme.exists():
            continue
        title = _title(readme.read_text(encoding="utf-8", errors="replace"), d.name)
        status = d.name.split("-")[0]
        logs = d / "logs"
        names = [p.name.lower() for p in logs.iterdir() if p.is_file()] if logs.exists() else []
        three = (any("mouse" in n for n in names)
                 and any("recommend" in n for n in names)
                 and any("story" in n for n in names))
        rows.append((d.name, status, title, "[OK]" if three else "—"))
    return rows


def adr_rows() -> list[tuple[str, str]]:
    rows = []
    for f in sorted((DOCS / "adr").glob("*.md")):
        title = _title(f.read_text(encoding="utf-8", errors="replace"), f.stem)
        rows.append((f.name, title))
    return rows


def render() -> dict[pathlib.Path, str]:
    bugs = bug_rows()
    adrs = adr_rows()
    out = {}
    out[DOCS / "bugs-index.md"] = (
        "# 缺陷台账（自动生成，勿手改）\n\n"
        f"共 {len(bugs)} 条。原始日志在各条目的 `logs/` 下，文件名保持原样。\n\n"
        "| 目录 | 状态 | 标题 | 三份日志 |\n|---|---|---|---|\n"
        + "".join(f"| [{n}](../bugs/{n}/README.md) | {s} | {t} | {x} |\n" for n, s, t, x in bugs)
    )
    out[ROOT / "bugs" / "README.md"] = (
        "# 缺陷台账\n\n"
        "一条缺陷一个目录，`logs/` 里是原始日志。这一页由 `scripts/build_docs.py` 生成。\n\n"
        "| 目录 | 状态 | 标题 |\n|---|---|---|\n"
        + "".join(f"| [{n}]({n}/README.md) | {s_} | {t} |\n" for n, s_, t, _ in bugs)
    )
    out[DOCS / "index.md"] = (
        "# 文档\n\n"
        "这一页和 `bugs-index.md` 都是 `scripts/build_docs.py` 生成的，别手改。\n\n"
        "## 决策记录（ADR）\n\n"
        "| 文件 | 决策 |\n|---|---|\n"
        + "".join(f"| [{n}](adr/{n}) | {t} |\n" for n, t in adrs)
        + "\n## 手册\n\n"
        + "| 文件 | 内容 |\n|---|---|\n"
        + "".join(
            f"| [{p.name}]({p.name}) | "
            f"{_title(p.read_text(encoding='utf-8', errors='replace'), p.stem)} |\n"
            for p in sorted(DOCS.glob("*.md"))
            if p.name not in ("index.md", "bugs-index.md")
        )
        + "\n## 参考\n\n"
        + "| 文件 | 内容 |\n|---|---|\n"
        + "".join(
            f"| [{p.name}](reference/{p.name}) | "
            f"{_title(p.read_text(encoding='utf-8', errors='replace'), p.stem)} |\n"
            for p in sorted((DOCS / "reference").glob("*.md"))
        )
        + "\n## 缺陷台账\n\n"
        f"{len(bugs)} 条，见 [bugs-index.md](bugs-index.md)。\n"
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查，不写盘")
    a = ap.parse_args()
    files = render()
    bad = []
    for path, text in files.items():
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        if a.check:
            if old != text:
                bad.append(path.relative_to(ROOT))
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    if a.check:
        if bad:
            print("生成物与仓库不一致（跑 python scripts/build_docs.py 重新生成）：", file=sys.stderr)
            for b in bad:
                print(f"  [X] {b}", file=sys.stderr)
            return 1
        print(f"OK 文档聚合一致（{len(files)} 个生成文件）")
    else:
        for p in files:
            print("写入", p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""检查 .md 里的相对链接目标是否存在（死链门禁）。

    python -X utf8 scripts/check_links.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\((?!https?://|mailto:|#)([^)#]+)(?:#[^)]*)?\)")


def md_files() -> list[pathlib.Path]:
    files = [ROOT / "README.md", ROOT / "NOTICE.md"]
    files += list((ROOT / "docs").rglob("*.md"))
    files += list((ROOT / "bugs").glob("*/README.md"))
    files.append(ROOT / "bugs" / "README.md")
    return [f for f in files if f.exists()]


def empty_markdown() -> list[pathlib.Path]:
    """0 字节的 md 是坏文件：看不出是漏写还是误建（曾在 Obsidian 里显示成空页）。"""
    bad = []
    for p in list(ROOT.rglob("*.md")):
        if any(part in (".git", "logs", ".captures", "records", "test") for part in p.parts):
            continue
        if p.stat().st_size == 0:
            bad.append(p)
    return bad


def main() -> int:
    bad = []
    for f in md_files():
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in LINK.finditer(text):
            target = (f.parent / m.group(1)).resolve()
            if not target.exists():
                bad.append(f"{f.relative_to(ROOT)}: 链接指向不存在的 {m.group(1)}")
    if bad:
        print("死链：", file=sys.stderr)
        for b in bad:
            print("  [X]", b, file=sys.stderr)
        return 1
    print(f"OK 链接检查通过（{len(md_files())} 个 md）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

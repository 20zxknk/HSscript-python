"""台账自测：文件夹名 / 状态行 / logs 三者必须一致（bugs/README.md 的收录标准）。"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path("bugs")
STATUSES = ("已修（实机验证）", "已修", "未修", "误报", "误判", "未核实")


def main() -> int:
    bad = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        m = re.match(r"^(" + "|".join(re.escape(s) for s in STATUSES) + r")-(\d{2})-(.+)$", d.name)
        if not m:
            bad.append(f"{d.name}: 目录名不符合 <状态>-<NN>-<短名>")
            continue
        st = m.group(1)
        r = d / "README.md"
        if not r.exists():
            bad.append(f"{d.name}: 缺 README.md")
            continue
        text = r.read_text(encoding="utf-8", errors="replace")
        line = re.search(r"^\*\*状态：(.*)\*\*$", text, re.M)
        if not line:
            bad.append(f"{d.name}: README 缺「**状态：」这一行")
            continue
        if not line.group(1).startswith(st):
            bad.append(f"{d.name}: 目录前缀是「{st}」，README 状态是「{line.group(1)}」")
        logs = d / "logs"
        if not logs.exists() or not any(p.is_file() for p in logs.iterdir()):
            bad.append(f"{d.name}: logs/ 是空的")
        if st == "已修（实机验证）":
            names = [p.name.lower() for p in logs.iterdir() if p.is_file()]
            need = (any("mouse" in n for n in names),
                    any("recommend" in n for n in names),
                    any("story" in n for n in names))
            if not all(need):
                bad.append(f"{d.name}: 标了「已修（实机验证）」但三份日志不齐"
                           f"（mouse={need[0]} recs={need[1]} story={need[2]}）")
    if bad:
        print("台账不一致：")
        for b in bad:
            print("  ✗", b)
        return 1
    n = sum(1 for d in ROOT.iterdir() if d.is_dir())
    print(f"OK 台账 {n} 条：目录前缀 / README 状态行 / logs 三者一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())

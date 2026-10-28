"""日志编码门禁：代码里的**字符串常量**必须能被 GBK 编码。

为什么：Windows 控制台/重定向默认是 GBK，`print("⚠ …")` 会抛
UnicodeEncodeError 并把整局打断（真机踩过：中盘打印一个 ⚠ 直接崩）。
注释和 docstring 不打印，不检查。
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGETS = sorted((ROOT / "src").rglob("*.py")) + [ROOT / "run.py"] + sorted((ROOT / "scripts").glob("*.py"))


def bad_strings(path: pathlib.Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                doc_nodes.add(id(body[0].value))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_nodes:
            try:
                node.value.encode("gbk")
            except UnicodeEncodeError:
                bad.append((node.lineno, node.value[:40]))
    return bad


def main() -> int:
    bad = []
    for p in TARGETS:
        if not p.exists():
            continue
        for line, text in bad_strings(p):
            bad.append(f"{p.relative_to(ROOT)}:{line}: {text!r}")
    if bad:
        print("这些字符串在 GBK 控制台下会打印失败：")
        for b in bad:
            print("  ✗", b)
        return 1
    print(f"OK 字符串常量都能用 GBK 打印（扫了 {len(TARGETS)} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

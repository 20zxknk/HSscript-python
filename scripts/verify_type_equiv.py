"""文档里的类型 / 常量必须与源码逐字一致——不过期靠这个脚本，不靠自觉。

    python -X utf8 scripts/verify_type_equiv.py --write   # 用源码覆盖文档里的块
    python -X utf8 scripts/verify_type_equiv.py --check   # 校验（门禁用）

约定：文档里用 ```python type-equiv 围住一段，块前一行写 `<!-- type-equiv: 符号名 -->`。
`docs/type-equiv.manifest.json` 登记每段对应哪个源文件里的哪个符号：

    {"doc": "docs/reference/types.md", "symbol": "GameState",
     "source": "src/hspy/input/state.py"}

`--check` 会用 ast 从源码把那个符号的整段定义（含 docstring）抽出来，逐字比对；
不一致就失败。所以文档里的类型永远等于代码里的类型，改代码不改文档过不了门禁。
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "type-equiv.manifest.json"

FENCE = re.compile(
    r"(?P<pre><!-- type-equiv: (?P<sym>[\w.]+) -->\n```python type-equiv\n)"
    r"(?P<body>.*?)"
    r"(?P<post>```)",
    re.S,
)


def find_symbol(path: pathlib.Path, symbol: str) -> str:
    """从源文件里抽出某个类/函数/赋值的整段源码（含前导注释与 docstring）。"""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    short = symbol.split(".")[-1]
    for node in tree.body:
        name = None
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name):
                name = t.id
        if name != short:
            continue
        start = node.lineno - 1
        # 往上吃掉紧邻的注释行（常量表通常带一段说明）
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        end = max(getattr(node, "end_lineno", node.lineno), node.lineno)
        return "\n".join(lines[start:end]).rstrip() + "\n"
    raise SystemExit(f"{path}: 找不到符号 {symbol}")


def project_fields(path: pathlib.Path, symbol: str) -> str:
    """只保留类的字段声明（AnnAssign）与 docstring，丢掉方法体与私有成员。

    文档要的是「有哪些字段、各是什么类型」，不是实现。把 200 行方法体贴进去，
    读者要的信息反而被埋掉（审计原话：455 行里 410 行源码，散文占 5%）。
    """
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    short = symbol.split(".")[-1]
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != short:
            continue
        start = node.lineno - 1
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        out = [lines[start]]
        doc = ast.get_docstring(node)
        if doc:
            out.append('    """' + doc.splitlines()[0] + '"""' if len(doc.splitlines()) == 1 else '    """')
            if len(doc.splitlines()) > 1:
                out.extend("    " + l for l in doc.splitlines())
                out.append('    """')
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.target.id.startswith("_"):
                    continue
                seg = ast.get_source_segment(src, item) or ""
                out.append("    " + seg.replace("\n", "\n    "))
        out.append("    # ……方法略（见源码）")
        return "\n".join(out).rstrip() + "\n"
    raise SystemExit(f"{path}: 找不到类 {symbol}")


def normalize(text: str) -> str:
    """比对时忽略行尾空白与多余空行。"""
    out = [l.rstrip() for l in text.splitlines()]
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    packed: list[str] = []
    for line in out:
        if not line.strip() and packed and not packed[-1].strip():
            continue
        packed.append(line)
    return "\n".join(packed)


def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return data.get("entries", data if isinstance(data, list) else [])


def run(write: bool) -> int:
    entries = load_manifest()
    if not entries:
        print("manifest 是空的（docs/type-equiv.manifest.json）", file=sys.stderr)
        return 1
    bad = 0
    seen = 0
    for e in entries:
        doc = ROOT / e["doc"]
        source = ROOT / e["source"]
        if not doc.exists():
            print(f"[X] 文档不存在: {e['doc']}", file=sys.stderr)
            bad += 1
            continue
        if not source.exists():
            print(f"[X] 源文件不存在: {e['source']}", file=sys.stderr)
            bad += 1
            continue
        if e.get("projection") == "fields":
            want = normalize(project_fields(source, e["symbol"]))
        else:
            want = normalize(find_symbol(source, e["symbol"]))
        text = doc.read_text(encoding="utf-8")
        matches = [m for m in FENCE.finditer(text) if m.group("sym") == e["symbol"]]
        if not matches:
            print(f"[X] {e['doc']}: 找不到 <!-- type-equiv: {e['symbol']} --> 块", file=sys.stderr)
            bad += 1
            continue
        if len(matches) > 1:
            print(f"[X] {e['doc']}: 符号 {e['symbol']} 的块出现 {len(matches)} 次", file=sys.stderr)
            bad += 1
            continue
        seen += 1
        m = matches[0]
        got = normalize(m.group("body"))
        if got == want:
            continue
        if write:
            new = text[: m.start("body")] + want + "\n" + text[m.end("body"):]
            doc.write_text(new, encoding="utf-8", newline="\n")
            print(f"更新 {e['doc']} ← {e['source']}::{e['symbol']}")
        else:
            print(f"[X] {e['doc']}: {e['symbol']} 与源码不一致（跑 --write 或改代码）", file=sys.stderr)
            bad += 1
    if bad:
        return 1
    print(f"OK 文档类型 {seen} 处与源码逐字一致（{len(entries)} 条登记）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    return run(write=not a.check)


if __name__ == "__main__":
    raise SystemExit(main())

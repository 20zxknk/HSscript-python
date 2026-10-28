"""生成 docs/reference/layout.md：仓库布局（谁在哪、干什么、入不入库）。

    python -X utf8 scripts/build_layout.py           # 生成
    python -X utf8 scripts/build_layout.py --check   # 校验生成物是否过期（门禁用）

目录说明最容易过期：手写一份，改两次代码就对不上。所以这里从代码里读 docstring，
从 git 里读「入不入库」，从 bugs/ 读台账规则，一行都不手抄。
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "reference" / "layout.md"


def docline(path: pathlib.Path) -> str:
    """取模块/文件的 docstring 第一行；没有就退回文件名。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        doc = ast.get_docstring(tree) or ""
    except SyntaxError:
        doc = ""
    first = doc.strip().splitlines()[0].strip() if doc.strip() else ""
    return first or "（无 docstring）"


def md_files() -> list[tuple[str, str]]:
    rows = []
    for p in sorted((ROOT / "src" / "hspy").rglob("*.py")):
        if p.name.startswith("_"):
            # 临时探针文件（门禁自测写的 _gate_probe.py）不算仓库布局
            continue
        rel = p.relative_to(ROOT).as_posix()
        rows.append((rel, docline(p)))
    return rows


def scripts() -> list[tuple[str, str]]:
    return [(p.name, docline(p)) for p in sorted((ROOT / "scripts").glob("*.py"))
            if not p.name.startswith("_")]


def tests() -> list[tuple[str, str]]:
    return [(p.name, docline(p)) for p in sorted((ROOT / "tests").glob("test_*.py"))]


def tracked(path: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode == 0


def render() -> str:
    out: list[str] = []
    out.append("# 仓库布局\n")
    out.append("这一页由 [`scripts/build_layout.py`](../../scripts/build_layout.py) 生成，"
               "每个模块的一句话取自它自己的 docstring——改代码不用改这一页，"
               "但忘了写 docstring 这里就会显示「（无 docstring）」。\n")

    out.append("## 顶层\n")
    out.append("| 目录 | 用途 | 入库 |\n|---|---|---|")
    out.append("| `src/hspy/` | 代码：input → decision → output，加引擎 | "
               f"{'是' if tracked('src/hspy') else '否'} |")
    out.append("| `tests/` | 不需要真机的测试，含 `fixtures/powerlog-sample.log`（脱敏样例） | 是 |")
    out.append("| `scripts/` | 门禁、生成器、实验脚本（都可重复运行） | 是 |")
    out.append("| `bugs/` | 缺陷台账：一条一个目录，`logs/` 里放原始日志 | 是 |")
    out.append("| `evidence/` | 被文档直接引用的整局证据（如 `stable-v01-r1`） | 是 |")
    out.append("| `docs/` | 手册 / 参考 / 决策记录；`index.md` 与 `bugs-index.md` 是生成物 | 是 |")
    out.append("| `data/` | 行为克隆模板库（入库）；训练权重 `*.pt` `*.joblib` 不入库 | 部分 |")
    out.append("| `test/` | 每次运行的录制产物；被引用的证据会复制进 `bugs/` 或 `evidence/` | 否 |")
    out.append("| `logs/` | 运行日志；`_scratch/` 放一次性排查脚本 | 否 |")
    out.append("| `.captures/` | 截图（点击取证、审计报告） | 否 |")
    out.append("| `records/` | 每局 Power.log 的分段留档（`acceptance.py`、`check_sync.py` 读它） | 否 |")
    out.append("| `.obsidian/` | Obsidian 的个人配置 | 否 |")

    out.append("| `references/` | 界面模板图（`modes/casual.png`、`modes/wild.png`），`navigator.read_mode` 用它比对标题 | 是 |")
    out.append("\n## `src/hspy/`\n\n| 文件 | 做什么 |\n|---|---|")
    for rel, doc in md_files():
        out.append(f"| `{rel}` | {doc} |")

    out.append("\n## `scripts/`\n\n| 脚本 | 做什么 |\n|---|---|")
    for name, doc in scripts():
        out.append(f"| `{name}` | {doc} |")

    out.append("\n## `tests/`\n\n| 文件 | 管什么 |\n|---|---|")
    for name, doc in tests():
        out.append(f"| `{name}` | {doc} |")

    out.append("""
## `bugs/`

一条缺陷一个目录，目录名就是状态：

```
<状态>-<NN>-<slug>/
    README.md      front-matter（身份）+ 现象 / 触发条件 / 场景 / 日志 / 根因 / 修复 / 验证
    logs/          那一局的原始文件，文件名不改
```

状态只有五个：`已修（实机验证）` / `已修` / `未修` / `误报` / `未核实`。
身份由 `scripts/bug_index.py` 校验（指纹、状态一致、verify.logs 存在），
格式由 `tests/test_bug_book.py` 校验（目录名 / 状态行 / logs 三者一致）。

## `docs/`

```
runbook.md              怎么起环境、怎么跑一局、跑不起来怎么查
reference/types.md      数据结构（与源码逐字一致，verify_type_equiv 校验）
reference/coords.md     坐标表（同上）
reference/mouse.md      鼠标参数（同上）
reference/layout.md     这一页（生成物）
adr/NNNN-*.md           决策记录（check_adr 校验格式）
index.md                生成物：决策 / 手册 / 参考 / 台账的总索引
bugs-index.md           生成物：台账索引
```

## 生成物一览

| 生成物 | 谁生成 | 谁检查过期 |
|---|---|---|
| `docs/index.md` | `scripts/build_docs.py` | `build_docs.py --check` |
| `docs/bugs-index.md` | 同上 | 同上 |
| `bugs/README.md` | 同上 | 同上 |
| `docs/reference/layout.md` | `scripts/build_layout.py` | `build_layout.py --check` |

## 不入库的东西

运行产物（`test/`、`logs/`、`.captures/`、`records/`）、工具缓存（`__pycache__`、
`.pytest_cache`、`.ruff_cache`）、训练权重（`data/*.pt`、`data/*.joblib`）、
Obsidian 配置（`.obsidian/`）、本机配置（`config.toml`）。
规则都在 [`.gitignore`](../../.gitignore)，改了忽略规则记得同步这一页。
""")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = render()
    if a.check:
        if not OUT.exists():
            print(f"[X] 缺 {OUT.relative_to(ROOT)}，跑 build_layout.py", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(f"[X] {OUT.relative_to(ROOT)} 与代码不一致，跑 python -X utf8 scripts/build_layout.py",
                  file=sys.stderr)
            return 1
        print("OK 仓库布局与代码一致")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"写入 {OUT.relative_to(ROOT)}（{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

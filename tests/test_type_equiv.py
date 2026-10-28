"""文档里的类型块必须与源码逐字一致（BUG：文档里的类型过期 = 读者照着过期的东西写代码）。

这里只验机制本身：抽取能不能对上、篡改会不会被发现、--write 能不能覆盖回来。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "verify_type_equiv.py"


def run(*args: str) -> int:
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return r.returncode


def test_current_docs_match() -> None:
    assert run("--check") == 0, "文档类型块与源码不一致（跑 --write）"
    print("OK   当前文档的类型块与源码逐字一致")


def test_tampered_block_is_caught() -> None:
    doc = ROOT / "docs" / "reference" / "coords.md"
    original = doc.read_text(encoding="utf-8")
    try:
        doc.write_text(original.replace("CHOICE_GENERAL_4 = (", "CHOICE_GENERAL_4 = (  # 手改了", 1),
                       encoding="utf-8", newline="\n")
        assert run("--check") != 0, "手改文档里的类型块，门禁居然通过了"
        print("OK   手改文档类型块会被门禁抓到")
    finally:
        doc.write_text(original, encoding="utf-8", newline="\n")
    assert run("--check") == 0, "恢复后仍不一致"
    print("OK   恢复原样后重新通过")


def test_write_restores_from_source() -> None:
    doc = ROOT / "docs" / "reference" / "coords.md"
    original = doc.read_text(encoding="utf-8")
    try:
        doc.write_text(original.replace("CHOICE_GENERAL_4 = (", "CHOICE_GENERAL_4 = (  # 手改了", 1),
                       encoding="utf-8", newline="\n")
        assert run("--write") == 0
        assert run("--check") == 0, "--write 之后仍不一致"
        print("OK   --write 能用源码覆盖回来")
    finally:
        doc.write_text(original, encoding="utf-8", newline="\n")


def test_manifest_points_at_real_symbols() -> None:
    data = json.loads((ROOT / "docs" / "type-equiv.manifest.json").read_text(encoding="utf-8"))
    entries = data["entries"]
    assert entries, "manifest 为空"
    for e in entries:
        assert (ROOT / e["source"]).exists(), f"源文件不存在: {e['source']}"
        text = (ROOT / e["doc"]).read_text(encoding="utf-8")
        assert f"<!-- type-equiv: {e['symbol']} -->" in text, f"{e['doc']} 缺 {e['symbol']} 块"
    print(f"OK   manifest {len(entries)} 条都指向真实文件与真实块")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组文档类型一致性用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

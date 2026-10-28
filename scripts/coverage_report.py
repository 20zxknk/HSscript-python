"""跑不需要真机的测试并出覆盖率报告，低于基线就失败（ratchet，只许涨不许跌）。

    python -X utf8 scripts/coverage_report.py                    # 出报告
    python -X utf8 scripts/coverage_report.py --min 37           # 全局地板（ratchet）
    python -X utf8 scripts/coverage_report.py --diff origin/master --diff-min 80
                                                                # 只看这次改动新增/修改的行
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

# 测试清单只有一处：scripts/run_all_tests.py。这里直接用它，避免两份名单漂移
# （曾经这里还留着已删除的 tests/test_author_mouse.py，导致 --min 直接 exit 1）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from run_all_tests import TESTS as ALL_TESTS  # noqa: E402

TESTS = [f"tests/{name}.py" for name in ALL_TESTS]
RUN_TESTS = [t for t in TESTS if pathlib.Path(t).exists()]


def run(*args: str) -> int:
    return subprocess.run([sys.executable, "-X", "utf8", *args]).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=0, help="全局覆盖率地板（百分比，ratchet）")
    ap.add_argument("--diff", default="", help="diff 覆盖率：和哪个 ref 比（如 origin/master、HEAD~1）")
    ap.add_argument("--diff-min", type=int, default=80, help="改动行覆盖率下限（默认 80）")
    a = ap.parse_args()

    missing = [t for t in TESTS if t not in RUN_TESTS]
    if missing:
        print(f"[!] 清单里有 {len(missing)} 个文件不存在，跳过：{missing}")
    run("-m", "coverage", "erase")
    for t in RUN_TESTS:
        if run("-m", "coverage", "run", "--source", "src", "-a", t) != 0:
            print(f"[X] 测试失败：{t}", file=sys.stderr)
            return 1
    if run("-m", "coverage", "report") != 0:
        return 1
    if a.min:
        if run("-m", "coverage", "report", f"--fail-under={a.min}") != 0:
            print(f"[X] 覆盖率低于基线 {a.min}%", file=sys.stderr)
            return 1
        print(f"OK 覆盖率不低于基线 {a.min}%")
    if a.diff:
        if run("-m", "coverage", "xml", "-o", "coverage.xml", "-q") != 0:
            return 1
        if run("-m", "diff_cover.diff_cover_tool", "coverage.xml",
               f"--compare-branch={a.diff}", f"--fail-under={a.diff_min}") != 0:
            print(f"[X] 改动的行覆盖率低于 {a.diff_min}%（看上面哪几行没被测到）", file=sys.stderr)
            return 1
        print(f"OK 改动的行覆盖率不低于 {a.diff_min}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

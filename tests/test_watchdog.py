"""看门狗必须真的能装、能写心跳、能在退出时留 .exit；否则 --debug 只是个空参数。"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hspy import watchdog  # noqa: E402


def test_install_beat_exit() -> None:
    d = pathlib.Path(tempfile.mkdtemp(prefix="wd-"))
    stack = watchdog.install(d, every=60)
    assert stack.exists() and stack.parent == d, stack
    watchdog.beat("测试心跳")
    beat = list(d.glob("watchdog-*.beat"))
    assert beat and "测试心跳" in beat[0].read_text(encoding="utf-8")
    print("OK   install 建了 .stack，beat 写了心跳")


def test_exit_marker_written() -> None:
    """子进程里装看门狗后正常退出，必须留下 .exit；没留下就说明 atexit 没挂上。"""
    d = pathlib.Path(tempfile.mkdtemp(prefix="wd-exit-"))
    code = (
        "import sys, pathlib;"
        f"sys.path.insert(0, r'{ROOT / 'src'}');"
        "from hspy import watchdog;"
        f"watchdog.install(pathlib.Path(r'{d}'), every=60);"
        "print('done')"
    )
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    exits = list(d.glob("watchdog-*.exit"))
    assert exits, f"没有 .exit，文件有：{[p.name for p in d.iterdir()]}"
    print("OK   正常退出留下 .exit（进程被杀的判据才成立）")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组看门狗用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

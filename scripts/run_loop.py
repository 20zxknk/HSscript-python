"""连续跑：一局一个子目录，直到到点。

    python -X utf8 scripts/run_loop.py --folder test --hours 3 --mode standard --deck 1

每局目录里有：
    mouse.jsonl / recommendations.jsonl / powerlog_story.md   三份记录
    run.log                                                  这一局的 stdout

（用 Start-Process 脱离终端启动，否则工具调用结束时子进程会被一起收走。）
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="test")
    ap.add_argument("--hours", type=float, default=3.0)
    ap.add_argument("--mode", default="standard")
    ap.add_argument("--deck", default="1")
    ap.add_argument("--seconds", type=float, default=900.0)
    ap.add_argument("--gap", type=float, default=6.0, help="局间间隔（秒）")
    a = ap.parse_args()

    folder = ROOT / a.folder
    folder.mkdir(parents=True, exist_ok=True)
    idx = 0
    for d in folder.iterdir():
        m = re.match(r"^(\d{3})-", d.name)
        if d.is_dir() and m:
            idx = max(idx, int(m.group(1)))

    end = time.time() + a.hours * 3600
    log = (folder / "loop.log").open("a", encoding="utf-8")
    while time.time() < end:
        idx += 1
        d = folder / f"{idx:03d}-{time.strftime('%H%M%S')}"
        d.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-u", str(ROOT / "run.py"), "--debug", "--games", "1",
               "--record", str(d), "--mode", a.mode, "--deck", a.deck,
               "--seconds", str(a.seconds)]
        t0 = time.time()
        line = f"[{time.strftime('%H:%M:%S')}] 第 {idx} 局 -> {d.name}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()
        with (d / "run.log").open("w", encoding="utf-8") as out:
            env = {"PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8"}
            import os
            e = dict(os.environ)
            e.update(env)
            rc = subprocess.run(cmd, cwd=str(ROOT), stdout=out,
                                stderr=subprocess.STDOUT, env=e,
                                timeout=a.seconds + 600).returncode
        line = f"[{time.strftime('%H:%M:%S')}] 第 {idx} 局结束 rc={rc} 用时 {time.time()-t0:.0f}s"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()
        time.sleep(a.gap)
    log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

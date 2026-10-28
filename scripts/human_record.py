"""录真人操作：装鼠标钩子，把每个事件写进 mouse.jsonl，用来校准 Humanizer。

用法（自己手动打几局，脚本只监听、不操作）：

    python -X utf8 scripts/human_record.py --out test/human1 --minutes 20

产出 test/human1/mouse.jsonl，每行：
    {"t": 1234.5, "ev": "move"/"ldown"/"lup", "cx": 952, "cy": 913, "injected": 0}
之后用 scripts/human_stats.py 对比"真人 vs 脚本"的分布。
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hspy.record import MouseHook  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="test/human1")
    ap.add_argument("--minutes", type=float, default=20.0)
    a = ap.parse_args()

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    path = out / "mouse.jsonl"
    hook = MouseHook(path)          # MouseHook 自己写 jsonl，不需要回调
    if not hook.start():
        print("[human] 钩子没挂上（权限？）", flush=True)
        return 1
    print(f"[human] 开始录制 {a.minutes:.0f} 分钟 -> {path}", flush=True)
    print("[human] 现在请你手动打几局（脚本只监听，不点任何东西）", flush=True)
    end = time.time() + a.minutes * 60
    try:
        while time.time() < end:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[human] 手动停止")
    finally:
        hook.stop()
    n = sum(1 for _ in path.open(encoding="utf-8"))
    print(f"[human] 录完 {n} 个事件 -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""跑全部测试并汇总最后一行（门禁用同款）。"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ["test_offline", "test_engine_rules", "test_type_equiv", "test_bug_book", "test_slot_conflict",
         "test_choice_geometry", "test_clone", "test_mouse_backend", "test_humanize",
         "test_mouse_curve", "test_log_encoding", "test_commit_msg_gate", "test_watchdog",
         "test_navigator", "test_overlays", "test_slot_arbitration", "test_powerlog_rules"]


def main() -> int:
    bad = 0
    for t in TESTS:
        r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tests" / f"{t}.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        last = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
        tail = last[-1] if last else "(无输出)"
        flag = "OK " if r.returncode == 0 else "FAIL"
        if r.returncode:
            bad += 1
        print(f"{flag} {t:<24}{tail[:60]}")
    print(f"\n失败 {bad} / {len(TESTS)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

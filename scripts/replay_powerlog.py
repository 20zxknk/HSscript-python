"""离线校验：同一份 Power.log，实时 fold 与从头重放必须得到同一状态（DSH 的 replay 不变量）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hspy.input.powerlog import PowerLog  # noqa: E402


def fingerprint(st) -> dict:
    return {
        "started": st.started,
        "finished": st.finished,
        "turn": st.turn,
        "my_id": st.my_id,
        "current_player": st.current_player,
        "players": sorted((p.pid, p.name, len(p.hand), len(p.board)) for p in st.players.values()),
        "entities": len(st.entities),
    }


def main() -> int:
    live = PowerLog()
    log = live.latest_log()
    print("日志:", log)
    live_states = []
    for _ in range(3):
        live.pump()
        live_states.append((live.seq, fingerprint(live.state)))
    print(f"实时 fold: seq={live.seq}  {live_states[-1][1]}")

    replay = PowerLog()
    st = replay.rebuild()
    print(f"从头重放: seq={replay.seq}  {fingerprint(st)}")

    a = live_states[-1][1]
    b = fingerprint(st)
    same = a == b
    print("\n状态一致:", "PASS" if same else "FAIL")
    if not same:
        for k in a:
            if a[k] != b[k]:
                print(f"  差异 {k}: live={a[k]!r} replay={b[k]!r}")
    print("seq 单调:", "PASS" if live_states[0][0] <= live_states[-1][0] else "FAIL")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())

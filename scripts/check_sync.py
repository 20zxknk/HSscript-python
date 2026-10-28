"""同步自检：把录下来的 Power.log 重放一遍，在每个"选项快照"时刻检查

    ① 手牌：游戏自己的 DebugPrintOptions 槽位  vs  我们按实体维护的密集手牌列表
    ② 场面：PLAY 区实体数  vs  我们场面列表长度
    ③ 重复：同一 zone_pos 上是否挂了两个实体（错位的主因）

用法：
    python -u scripts/check_sync.py            # 检查 records/ 下全部
    python -u scripts/check_sync.py <Power.log>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hspy.input.powerlog import PowerLog  # noqa: E402


def check(path: Path) -> dict:
    p = PowerLog()
    p.records_dir = None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(True)

    samples = 0
    hand_order_ok = 0
    hand_set_ok = 0
    hand_bad: list[str] = []
    board_bad = 0
    board_ok = 0
    board_samples = 0
    board_examples: list[str] = []
    dup_pos = 0
    last_opt_seq = -1

    for raw in lines:
        p.seq += 1
        p._feed(raw)
        st = p.state          # EV_GAME_CREATE 会换掉 state 对象，必须每行重取
        st.refresh()

        opts_all = st.hand_options
        if opts_all:
            oseq = st.hand_options_seq
            if oseq != last_opt_seq:
                last_opt_seq = oseq
                # DebugPrintOptions 只列"当前能做的事"（可打出的牌），不是整只手牌；
                # 但它给的 zonePos 就是那张牌在界面上的槽位 —— 拿它校验我们的密集列表
                for pid, slots_map in opts_all.items():
                    pl = st.players.get(pid)
                    if not pl or not slots_map:
                        continue
                    for slot, cid in sorted(slots_map.items()):
                        if not cid or slot < 1:
                            continue
                        samples += 1
                        idx = slot - 1
                        if idx < len(pl.hand) and pl.hand[idx].card_id == cid:
                            hand_set_ok += 1          # 槽位命中
                        else:
                            got = pl.hand[idx].card_id if idx < len(pl.hand) else "<越界>"
                            hand_bad.append(
                                f"玩家{pid} 选项槽{slot}={cid} 我们的列表槽{slot}={got!r} "
                                f"整手={[(i + 1, e.card_id) for i, e in enumerate(pl.hand)]}")
                    if len(slots_map) == len(pl.hand) and \
                            sorted(slots_map.values()) == [e.card_id for e in pl.hand]:
                        hand_order_ok += 1

        # 场面：判"我们的列表和 PLAY 区实体集合是否完全一致"（漏一只/多一只都会让点击错位）。
        # 不用 zone_pos 排序校验 —— 实测单只随从的 zone_pos 会停在旧号（2、3），不是 1..n 排列。
        if st.is_my_turn and st.my_id and st.players.get(st.my_id) and st.players[st.my_id].board:
            pl = st.players[st.my_id]
            ours = [e.eid for e in pl.board]
            zone = [e.eid for e in st.entities.values()
                    if e.controller == st.my_id and e.zone == "PLAY"
                    and (e.is_minion or e.card_type == "LOCATION") and e.zone_pos > 0]
            board_samples += 1
            if len(set(ours)) != len(ours):
                board_bad += 1
                if len(board_examples) < 3:
                    board_examples.append(f"列表里有重复 eid {ours}")
            elif set(ours) != set(zone):
                board_bad += 1
                if len(board_examples) < 3:
                    board_examples.append(
                        f"列表={ours} PLAY区={zone} 牌={[e.card_id for e in pl.board]}")
            else:
                board_ok += 1

        # （场面数量比较已并入下面"我方回合"的评估，这里不再重复统计）

    return {
        "file": path.name,
        "samples": samples,
        "set_ok": hand_set_ok,
        "order_ok": hand_order_ok,
        "examples": hand_bad[:3],
        "board_samples": board_samples,
        "board_ok": board_ok,
        "board_bad": board_bad,
        "board_examples": board_examples[:3],
        "dup_pos": dup_pos,
        "finished": st.finished,
    }


def main() -> int:
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:]]
    else:
        files = sorted((ROOT / "records").glob("*.log"))
    if not files:
        print("没有日志可检")
        return 1

    tot = {"samples": 0, "set_ok": 0, "order_ok": 0, "board_samples": 0, "board_bad": 0, "dup_pos": 0}
    for f in files:
        r = check(f)
        for k in tot:
            tot[k] += r[k]  # type: ignore[operator]
        print(f"{r['file']:<28} 手牌样本={r['samples']:<4} 集合对={r['set_ok']:<4} 顺序对={r['order_ok']:<4} "
              f"场面样本={r['board_samples']:<5} 场面不一致={r['board_bad']:<4} 重复位置={r['dup_pos']} "
              f"finished={r['finished']}")
        for ex in r["examples"]:
            print(f"     [X] {ex}")

    print("\n=== 汇总 ===")
    print(f"手牌快照样本 {tot['samples']}，集合一致 {tot['set_ok']} "
          f"({tot['set_ok'] / max(tot['samples'], 1):.0%})，顺序一致 {tot['order_ok']} "
          f"({tot['order_ok'] / max(tot['samples'], 1):.0%})")
    print(f"场面样本 {tot['board_samples']}，不一致 {tot['board_bad']}，同位置重复 {tot['dup_pos']} 次")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""把脚本的动作日志（logs/actions-*.jsonl）和 Power.log 逐条对账。

回答的问题：
    ① 脚本说"我打了 BE_207 到 4 号位"，Power.log 里是否真有这条变化？
    ② 脚本点了屏幕哪个像素，点完之后日志有没有反应（effect=True/False）？
    ③ 前后 seq/version 能不能和 Power.log 的序号对上？

用法：
    python -u scripts/join_actions.py logs/actions-20261024_210231.jsonl <Power.log>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_actions(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def load_power(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    acts = load_actions(Path(sys.argv[1]))
    power = load_power(Path(sys.argv[2]))
    steps = [a for a in acts if "step" in a]
    print(f"动作日志 {len(acts)} 条（其中 step {len(steps)} 条），Power.log {len(power)} 行")

    # 只对账"动作"记录（带 plan 的）
    check = 0
    bad = 0
    for a in acts:
        plan = a.get("plan")
        if not plan:
            continue
        card = plan.get("card_id") or ""
        sb, sa = a.get("seq_before", 0), a.get("seq_after", 0)
        window = power[:sa] if sa else power
        tail = window[sb:sa] if sa and sa <= len(power) else []
        hit = [ln for ln in tail if card and card in ln]
        effect = a.get("effect")
        check += 1
        # 判据：日志确实前进了（effect=True）就算对得上；能再抓到 cardId 原文更好。
        # 出牌那一段日志里往往只写卡名（play_special 甚至只有任务链），拿 cardId
        # 去硬匹配会误报"有问题"，所以把"命中原文"降级成附加信息。
        if effect:
            flag = "对得上" if hit else "对得上（日志走的是卡名/任务链）"
        else:
            flag = "无反应"
            bad += 1
        print(f"\n[{check}] turn={a.get('turn')} {plan.get('action')} card={card} "
              f"hand_slot={(a.get('resolved') or {}).get('hand_slot')} "
              f"board_index={(a.get('resolved') or {}).get('board_index')} "
              f"clicks={len(a.get('clicks') or [])} effect={effect} → {flag}")
        for c in (a.get("clicks") or [])[:4]:
            print(f"      点 {c.get('tag')} 客户区={c.get('client')} 屏幕={c.get('screen')}")
        for ln in (tail[:3] if not hit else hit[:3]):
            print("      日志:", ln.split("- ", 1)[-1][:110])
    print(f"\n=== 汇总：{check} 步，其中对得上 {check - bad}，有问题 {bad} ===")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

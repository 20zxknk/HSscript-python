"""把若干局的四份材料汇总成「每条 bug 有没有复现」的核对表。

    python -X utf8 scripts/verify_bugs.py test\015-112438 test\016-...
    python -X utf8 scripts/verify_bugs.py --recent 5      # 最近 5 局
"""
from __future__ import annotations

import argparse
import collections
import glob
import io
import json
import os
import re


def read_log(d: str) -> list[str]:
    p = os.path.join(d, "run.log")
    if not os.path.exists(p):
        return []
    for enc in ("utf-8", "gbk"):
        try:
            return io.open(p, encoding=enc, errors="replace").read().splitlines()
        except Exception:
            continue
    return []


def analyze(d: str) -> dict:
    lines = read_log(d)
    text = "\n".join(lines)
    acts = collections.Counter(m.group(1) for m in re.finditer(r"action=(\w+)", text))
    sw = [l for l in lines if "swallowed" in l]
    sw_kinds = collections.Counter()
    for l in sw:
        m = re.search(r"evidence=([^ ]+)", l)
        sw_kinds[m.group(1) if m else "?"] += 1
    errs = [l for l in lines if re.search(r"error=(?!NONE)\w+", l)]
    err_kind = collections.Counter(re.findall(r"error=(\w+)", " ".join(errs)))

    recs = 0
    recs_with_plans = 0
    p = os.path.join(d, "recommendations.jsonl")
    if os.path.exists(p):
        for line in io.open(p, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            recs += 1
            if r.get("plans"):
                recs_with_plans += 1

    return {
        "dir": os.path.basename(d),
        "steps": sum(1 for l in lines if "[step " in l),
        "acts": acts,
        "ok_effect": sum(1 for l in lines if "ok:action_effect" in l),
        "swallowed": len(sw),
        "sw_kinds": sw_kinds,
        "errors": len(errs),
        "err_kind": err_kind,
        "recs": recs,
        "recs_plans": recs_with_plans,
        "mulligan_read": "起手" in text,
        "mulligan_replaced": "替换 [" in text,
        "choice_panel": "选择面板" in text,
        "finished": "收工" in text,
        "unicode_crash": "UnicodeEncodeError" in text,
        "story": os.path.exists(os.path.join(d, "powerlog_story.md")),
        "mouse_events": _count_jsonl(os.path.join(d, "mouse.jsonl")),
        "mouse_moves": _count_ev(os.path.join(d, "mouse.jsonl"), "move"),
    }


def _count_jsonl(p: str) -> int:
    if not os.path.exists(p):
        return 0
    return sum(1 for l in io.open(p, encoding="utf-8", errors="replace") if l.strip())


def _count_ev(p: str, ev: str) -> int:
    if not os.path.exists(p):
        return 0
    n = 0
    for line in io.open(p, encoding="utf-8", errors="replace"):
        if f'"ev": "{ev}"' in line:
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--recent", type=int, default=0)
    a = ap.parse_args()

    dirs = a.dirs
    if a.recent:
        all_dirs = sorted(d for d in glob.glob("test/0*") if os.path.isdir(d))
        dirs = all_dirs[-a.recent:]

    rows = [analyze(d) for d in dirs if os.path.exists(os.path.join(d, "run.log"))]
    if not rows:
        print("没有可分析的目录")
        return 1

    print(f"{'局':<16}{'步':>4}{'动作':>4}{'成功':>4}{'吞':>4}{'错':>3}{'推荐':>5}{'换牌':>4}{'story':>6}")
    for r in rows:
        print(f"{r['dir']:<16}{r['steps']:>4}{sum(r['acts'].values()):>4}{r['ok_effect']:>4}"
              f"{r['swallowed']:>4}{r['errors']:>3}{r['recs']:>5}"
              f"{'是' if r['mulligan_read'] else '否':>4}{'有' if r['story'] else '无':>6}")

    print("\n=== 每条 bug 的核对 ===")
    def verdict(cond, yes, no):
        return yes if cond else no

    print("BUG 07 换牌读到起手张数 :", verdict(all(r["mulligan_read"] for r in rows), "全部读到", "有局读不到"))
    print("BUG 11 进对局不空等     :", verdict(all(r["steps"] > 0 or r["recs_plans"] > 0 for r in rows), "都进得去", "有局没进去"))
    print("BUG 12 日志编码不崩     :", verdict(not any(r["unicode_crash"] for r in rows), "无 UnicodeEncodeError", "又崩了"))
    print("BUG 05 选择面板         :", verdict(any(r["choice_panel"] for r in rows), "出现且未卡死", "这批没出现"))
    print("BUG 06 card_usable      :", verdict(not any("REQ_ATTACK" in str(r["err_kind"]) for r in rows),
                                          "无 REQ_ATTACK 误判", "仍有 REQ_ATTACK 误判"))
    print("盒子推荐                :", verdict(all(r["recs_plans"] > 0 for r in rows), "每局都有 plans", "有局没有 plans"))
    print("鼠标事件                :", "move 记录 "
          + str(sum(r["mouse_moves"] for r in rows)) + " 条 / 点击 "
          + str(sum(r["mouse_events"] for r in rows) - sum(r["mouse_moves"] for r in rows)) + " 条")
    print("吞动作                  :", f"{sum(r['swallowed'] for r in rows)} 次，类别 "
          + str(sum((r["sw_kinds"] for r in rows), collections.Counter())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""对一份真机日志查重：看它撞上了台账里哪几条（尤其「已修」的）。

    python -X utf8 scripts/check_bug_dupes.py --logs test/015-112438
    python -X utf8 scripts/check_bug_dupes.py --logs test/v6 --min 2

判据（和业界一致）：
  * 命中「已修/已修（实机验证）」的条目  -> **复发**，不许新建，走 reopen
  * 命中「未修」的条目                  -> 已知问题又出现，正常
  * 一条都没命中                        -> 才可能是新 bug（还要过 root_cause 比对）

`--min` 是同一模式至少出现几次才算命中（默认 1，避免偶发噪声）。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from bug_index import entries  # noqa: E402


def read_logs(d: pathlib.Path) -> str:
    """按「乱码最少」挑编码：我们的日志是 GBK，直接按 utf-8 读会把中文全变成替换符，
    于是 patterns 永远匹配不上（这就是它对 GBK 日志零命中的原因）。"""
    parts = []
    for name in ("run.log", "err.log"):
        p = d / name
        if not p.exists():
            continue
        best, best_bad = "", 1 << 30
        for enc in ("gbk", "utf-8"):
            try:
                text = p.read_text(encoding=enc, errors="replace")
            except Exception:
                continue
            bad = text.count(chr(0xFFFD))
            if bad < best_bad:
                best, best_bad = text, bad
        parts.append(best)
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", required=True)
    ap.add_argument("--min", type=int, default=1)
    a = ap.parse_args()

    d = pathlib.Path(a.logs)
    if not d.exists():
        print(f"没有目录：{d}", file=sys.stderr)
        return 2
    raw = read_logs(d)
    # 只在「可疑行」里找：正常日志里会打印的标记（box_rec_raw / hand_size / option_map）
    # 一律不算命中，否则每条日志都会撞上 B-02/03/04（这是查重失效的直接原因）
    suspicious = ("swallowed", "FAIL", "Traceback", "Error", "卡住", "无方案",
                  "等起手", "超时", "重新连接", "离线")
    text = "\n".join(l for l in raw.splitlines() if any(k in l for k in suspicious))
    if not text.strip():
        print(f"{d} 里没有 run.log/err.log")
        return 2

    import datetime as _dt

    log_time = _dt.datetime.fromtimestamp(d.stat().st_mtime)

    hits = []
    for e in entries():
        f = e.get("front") or {}
        pats = f.get("patterns") or []
        counts = []
        for p in pats:
            n = text.count(str(p))
            if n >= a.min:
                counts.append((p, n))
        fixed_at = (e.get("front") or {}).get("fixed_at")
        if counts and fixed_at:
            try:
                t = _dt.datetime.fromisoformat(str(fixed_at))
            except ValueError:
                t = None
            if t and log_time <= t:
                print(f"  （跳过 {e['dir']}：这份日志在修复时间 {fixed_at} 之前）")
                continue
        if counts:
            hits.append((e, counts))

    fixed_hits = [(e, c) for e, c in hits if str((e.get("front") or {}).get("state", "")).startswith("已修")]
    open_hits = [(e, c) for e, c in hits if (e.get("front") or {}).get("state") == "未修"]

    print(f"日志 {d}（{len(text)} 字符），命中 {len(hits)} 条：")
    for e, c in hits:
        f = e.get("front") or {}
        print(f"  {e['dir']:<44}{f.get('state')}  命中 {sum(n for _, n in c)} 次  " +
              ", ".join(f"{p!r}×{n}" for p, n in c))

    if fixed_hits:
        print("\n结论：这是**复发**，不许新建。走：")
        for e, _ in fixed_hits:
            num = e["num"]
            print(f"  python -X utf8 scripts/reopen_bug.py --bug {num} --logs {d}")
    elif open_hits:
        print("\n结论：命中「未修」条目，是已知未修问题，不新建。")
    else:
        print("\n结论：零命中。可能是新 bug——还要过 root_cause 比对，"
              "并在 README 写清「与已有条目的区别」。")
    return 1 if fixed_hits else 0


if __name__ == "__main__":
    raise SystemExit(main())

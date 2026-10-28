"""缺陷台账的机器身份：给每条 bug 一个可重算的指纹，并校验台账一致性。

    python -X utf8 scripts/bug_index.py            # 打印索引表
    python -X utf8 scripts/bug_index.py --check    # 校验（门禁用）
    python -X utf8 scripts/bug_index.py --fill     # 给缺 fp 的条目补上（写回 README）

README 顶部用 YAML front-matter 存身份（唯一真相，不另存 meta.json）：

    ---
    id: B-05
    state: 已修
    module: engine.turn
    stage: 我方回合
    symptom_key: 面板开着但引擎当成非我方回合
    patterns: ["选择了之后面板还开着", "无方案"]
    root_cause: "engine.play_match: 只看 my_action_window，没看 choice_open"
    related: [B-10]
    reopened_count: 0
    verify: {build: 51254d0, logs: test/v6}
    ---

fp = sha1("module|stage|symptom_key")[:12]，由脚本重算并与写入值比对（防手改绕过判重）。
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    print("需要 pyyaml：pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUGS = ROOT / "bugs"
STATUSES = ("已修（实机验证）", "已修", "未修", "误报", "误判", "未核实")
NAME_RE = re.compile(r"^(" + "|".join(re.escape(s) for s in STATUSES) + r")-(\d{2})-(.+)$")


def fp_of(front: dict) -> str:
    key = "|".join(str(front.get(k, "")).strip() for k in ("module", "stage", "symptom_key"))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def read_front(path: pathlib.Path) -> tuple[dict, str, str]:
    """返回 (front-matter, 标题行, 正文)。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}, text.splitlines()[0] if text else "", text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, "", text
    front_raw = text[3:end]
    body = text[end + 4:]
    try:
        front = yaml.safe_load(front_raw) or {}
    except yaml.YAMLError:
        front = {"__yaml_error__": True}
    first = next((l for l in body.splitlines() if l.startswith("# ")), "")
    return front, first, body


def entries() -> list[dict]:
    out = []
    for d in sorted(BUGS.iterdir()):
        if not d.is_dir():
            continue
        m = NAME_RE.match(d.name)
        readme = d / "README.md"
        if not readme.exists():
            out.append({"dir": d.name, "error": "缺 README.md"})
            continue
        front, title, body = read_front(readme)
        out.append({
            "dir": d.name, "path": d, "front": front, "title": title,
            "status_in_name": m.group(1) if m else None,
            "num": m.group(2) if m else None,
            "body": body,
        })
    return out


def check() -> int:
    errs = []
    seen_fp: dict[str, str] = {}
    seen_sym: dict[tuple, str] = {}
    for e in entries():
        if e.get("error"):
            errs.append(f"{e['dir']}: {e['error']}")
            continue
        f = e["front"]
        if not f:
            errs.append(f"{e['dir']}: README 顶部没有 YAML front-matter")
            continue
        if f.get("__yaml_error__"):
            errs.append(f"{e['dir']}: front-matter 不是合法 YAML")
            continue
        if not e["status_in_name"]:
            errs.append(f"{e['dir']}: 目录名不符合 <状态>-<NN>-<短名>")
            continue
        if str(f.get("id", "")) != f"B-{e['num']}":
            errs.append(f"{e['dir']}: id 应为 B-{e['num']}，实际 {f.get('id')!r}")
        if f.get("state") != e["status_in_name"]:
            errs.append(f"{e['dir']}: 目录状态 {e['status_in_name']} ≠ front-matter state {f.get('state')!r}")
        for k in ("module", "stage", "symptom_key", "root_cause"):
            if not str(f.get(k, "")).strip():
                errs.append(f"{e['dir']}: front-matter 缺 {k}")
        fp = fp_of(f)
        if not f.get("fp"):
            errs.append(f"{e['dir']}: front-matter 缺 fp（应为重算值 {fp}）")
        elif f["fp"] != fp:
            errs.append(f"{e['dir']}: fp 与重算值不一致（写入 {f.get('fp')} / 重算 {fp}）")
        if fp in seen_fp:
            errs.append(f"{e['dir']}: 与 {seen_fp[fp]} 指纹相同（{fp}）——同一缺陷，不许开两条")
        else:
            seen_fp[fp] = e["dir"]
        sym = (f.get("module"), f.get("symptom_key"))
        if sym in seen_sym:
            errs.append(f"{e['dir']}: 与 {seen_sym[sym]} 的 module+symptom_key 相同——大概率是同一缺陷")
        else:
            seen_sym[sym] = e["dir"]
        # ---- 三条「说了没做到」的检查（2026-10-27 审计加的）----
        # 1) 未修条目不许留着 fixed_at：那是「修过」的标记，和状态矛盾
        if e["status_in_name"] == "未修" and f.get("fixed_at"):
            errs.append(f"{e['dir']}: 状态是未修，却还留着 fixed_at={f['fixed_at']}")
        # 2) verify.logs 必须真的存在（曾经指向一个已被改名的目录）
        v = f.get("verify") or {}
        logs_path = str(v.get("logs") or "").strip()
        if logs_path and not (ROOT / logs_path).exists():
            errs.append(f"{e['dir']}: verify.logs 指向不存在的 {logs_path}")
        # 3) reopened_count 必须与正文「复发记录」节数一致
        n_sec = e["body"].count("## 复发记录")
        if int(f.get("reopened_count") or 0) != n_sec:
            errs.append(f"{e['dir']}: reopened_count={f.get('reopened_count')} "
                        f"但正文有 {n_sec} 节「复发记录」")
        if int(f.get("reopened_count") or 0) > 0:
            # 复发过的条目：要么还是未修，要么重新修好时必须留下「这次复发的根因」和「修复」，
            # 不允许只把状态改回已修（那正是"假修好"的做法）。
            if e["status_in_name"] == "未修":
                pass
            elif "复发确认的根因" not in e["body"] or "## 修复" not in e["body"]:
                errs.append(f"{e['dir']}: 复发过又改成已修，但 README 缺少「复发确认的根因」或「修复」段")
        if e["status_in_name"] == "已修（实机验证）":
            v = f.get("verify") or {}
            if not v.get("build") or not v.get("logs"):
                errs.append(f"{e['dir']}: 标了「实机验证」但没有 verify.build / verify.logs")
        # 正文里提到的证据文件必须真的存在（曾经写完「logs/xxx」就把文件压成 .gz，
        # 文档与磁盘对不上，而门禁只查「logs/ 非空」）
        for name in re.findall(r"logs/([\w.\-\u4e00-\u9fff]+\.(?:log|jsonl|gz|md|txt|png|webp))",
                               e["body"]):
            if not (e["path"] / "logs" / name).exists():
                errs.append(f"{e['dir']}: README 提到的 logs/{name} 不存在")

        logs = e["path"] / "logs"
        if not logs.exists() or not any(p.is_file() for p in logs.iterdir()):
            errs.append(f"{e['dir']}: logs/ 为空")
    if errs:
        print("台账校验失败：", file=sys.stderr)
        for x in errs:
            print("  [X]", x, file=sys.stderr)
        return 1
    print(f"OK 台账 {len(seen_fp)} 条：front-matter / 指纹唯一 / 状态一致 / logs 非空")
    return 0


def fill() -> int:
    """给缺 fp 的条目把 fp 写回 front-matter。"""
    n = 0
    for e in entries():
        if e.get("error") or not e["front"] or e["front"].get("fp"):
            continue
        f = e["front"]
        fp = fp_of(f)
        text = (e["path"] / "README.md").read_text(encoding="utf-8", errors="replace")
        if "fp:" in text.split("---")[1]:
            continue
        head, rest = text.split("\n---", 1) if "\n---" in text else (None, None)
        if head is None:
            continue
        text = head + f"\nfp: {fp}\n---" + rest
        (e["path"] / "README.md").write_text(text, encoding="utf-8", newline="\n")
        n += 1
    print(f"补了 {n} 条的 fp")
    return 0


def show() -> int:
    rows = []
    for e in entries():
        if e.get("error"):
            rows.append((e["dir"], "?", "?", "-", "-", ""))
            continue
        f = e["front"]
        rows.append((e["dir"], f.get("state", "?"), f.get("id", "?"),
                     fp_of(f) if f else "-", f.get("reopened_count", 0),
                     str(f.get("root_cause", ""))[:40]))
    w = max(len(r[0]) for r in rows) + 2
    print(f"{'目录':<{w}}{'state':<12}{'id':<6}{'fp':<14}{'重开':<4}根因")
    for r in rows:
        print(f"{r[0]:<{w}}{str(r[1]):<12}{str(r[2]):<6}{str(r[3]):<14}{str(r[4]):<4}{r[5]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--fill", action="store_true")
    a = ap.parse_args()
    if a.fill:
        return fill()
    if a.check:
        return check()
    return show()


if __name__ == "__main__":
    raise SystemExit(main())

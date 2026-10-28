"""把台账里的 mouse.jsonl 压成 .gz，并同步 README 里的文件名。

    python -X utf8 scripts/shrink_evidence.py            # 只报告
    python -X utf8 scripts/shrink_evidence.py --write    # 真的压

mouse.jsonl 是每局最长的原始文件（单条最大 2.5 MB），文本压缩率很高；
台账要的是「证据可查」，不是「随时能直接 grep」，所以压缩后仍算原始文件。
README 里凡是提到 mouse.jsonl 的地方一并改成 mouse.jsonl.gz，避免文档与磁盘不一致。
"""
from __future__ import annotations

import argparse
import gzip
import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def png_targets() -> list[pathlib.Path]:
    out = []
    for base in (ROOT / "bugs", ROOT / "evidence"):
        if base.exists():
            out.extend(sorted(base.rglob("*.png")))
    return out


def shrink_pngs(write: bool) -> None:
    """截图转 webp：台账里最大的 11 个文件全是 1905x982 的 PNG。"""
    from PIL import Image

    files = png_targets()
    before = sum(f.stat().st_size for f in files)
    after = 0
    for f in files:
        img = Image.open(f).convert("RGB")
        out = f.with_suffix(".webp")
        if write:
            img.save(out, "WEBP", quality=82, method=6)
        size = out.stat().st_size if out.exists() else int(f.stat().st_size * 0.18)
        after += size
        print(f"{f.relative_to(ROOT)}: {f.stat().st_size//1024} KB -> {size//1024} KB")
        if write:
            f.unlink()
    print(f"\n截图合计 {before/1048576:.1f} MB -> {after/1048576:.1f} MB")
    if write:
        n = 0
        for readme in sorted((ROOT / "bugs").rglob("README.md")):
            t = io.open(readme, encoding="utf-8").read()
            new = t.replace(".png", ".webp")
            if new != t:
                io.open(readme, "w", encoding="utf-8", newline="\n").write(new)
                n += 1
        for src in sorted((ROOT / "bugs").rglob("SOURCES.txt")):
            t = io.open(src, encoding="utf-8").read()
            new = t.replace(".png", ".webp")
            if new != t:
                io.open(src, "w", encoding="utf-8", newline="\n").write(new)
        print(f"README/SOURCES 同步改成 .webp: {n} 个 README")


def targets() -> list[pathlib.Path]:
    out = []
    for base in (ROOT / "bugs", ROOT / "evidence"):
        if not base.exists():
            continue
        out.extend(sorted(base.rglob("mouse.jsonl")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--png", action="store_true", help="把截图转 webp")
    a = ap.parse_args()
    if a.png:
        shrink_pngs(a.write)
        return 0

    files = targets()
    if not files:
        print("没有需要压缩的 mouse.jsonl（可能已经压过）")
        return 0

    before = sum(f.stat().st_size for f in files)
    after = 0
    for f in files:
        raw = f.read_bytes()
        gz = f.with_suffix(".jsonl.gz")
        if a.write:
            with gzip.open(gz, "wb", compresslevel=9) as out:
                out.write(raw)
        size = gz.stat().st_size if gz.exists() else len(raw) // 5
        after += size
        print(f"{f.relative_to(ROOT)}: {len(raw)//1024} KB -> {size//1024} KB")
        if a.write:
            f.unlink()

    print(f"\n合计 {before/1048576:.1f} MB -> {after/1048576:.1f} MB "
          f"（省 {100 - after*100/before:.0f}%）")

    if a.write:
        n = 0
        for readme in sorted((ROOT / "bugs").rglob("README.md")):
            s = io.open(readme, encoding="utf-8").read()
            new = s.replace("mouse.jsonl.gz", "mouse.jsonl").replace("mouse.jsonl", "mouse.jsonl.gz")
            if new != s:
                io.open(readme, "w", encoding="utf-8", newline="\n").write(new)
                n += 1
        print(f"README 里同步改名: {n} 个文件")
        # SOURCES.txt 里也可能写着
        m = 0
        for src in sorted((ROOT / "bugs").rglob("SOURCES.txt")):
            s = io.open(src, encoding="utf-8").read()
            new = s.replace("mouse.jsonl.gz", "mouse.jsonl").replace("mouse.jsonl", "mouse.jsonl.gz")
            if new != s:
                io.open(src, "w", encoding="utf-8", newline="\n").write(new)
                m += 1
        print(f"SOURCES.txt 里同步改名: {m} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

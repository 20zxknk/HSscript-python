"""「进行选择」4 大牌面板的坐标必须落在牌面上，不能落进两张牌之间。

实测值来自 .captures/choice-fail-133039.png / 133101.png（客户区 1905×982）：
  牌心 x ≈ 447 / 787 / 1127 / 1473，y ≈ 488
  牌面 x 范围：319..574 / 659..914 / 999..1254 / 1345..1600
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")

from hspy import coords  # noqa: E402

MEASURED = [(447, 488), (787, 488), (1127, 488), (1473, 488)]
SPANS = [(319, 574), (659, 914), (999, 1254), (1345, 1600)]
GAPS = [(574, 659), (914, 999), (1254, 1345)]


def centers() -> list[tuple[int, int]]:
    out = []
    for r in coords.CHOICE_GENERAL_4:
        x, y, w, h = r.relative(1905, 982)
        out.append((x + w // 2, y + h // 2))
    return out


def test_centers_match_measurement():
    got = centers()
    for i, ((gx, gy), (mx, my)) in enumerate(zip(got, MEASURED)):
        assert abs(gx - mx) <= 6 and abs(gy - my) <= 6, (i, (gx, gy), (mx, my))
    print("OK   四个牌心与实测一致（误差 <=6px）:", got)


def test_centers_inside_cards_not_gaps():
    for i, (gx, _) in enumerate(centers()):
        lo, hi = SPANS[i]
        assert lo < gx < hi, (i, gx, lo, hi)
        for glo, ghi in GAPS:
            assert not (glo <= gx <= ghi), f"槽 {i + 1} 的 x={gx} 落在空隙 {glo}..{ghi}"
    print("OK   四个牌心都在牌面内，没有一个落在空隙里")


def test_general_table_wider_than_discover():
    d = coords.DISCOVER_4[1].relative(1905, 982)
    gap_g = centers()[1][0] - centers()[0][0]
    gap_d = (d[0] + d[2] // 2) - (coords.DISCOVER_4[0].relative(1905, 982)[0] +
                                  coords.DISCOVER_4[0].relative(1905, 982)[2] // 2)
    assert gap_g > gap_d * 1.3, (gap_g, gap_d)
    print(f"OK   「进行选择」面板间距 {gap_g}px 明显大于发现面板 {gap_d}px（所以不能共用表）")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部通过（{len(tests)} 组面板几何用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

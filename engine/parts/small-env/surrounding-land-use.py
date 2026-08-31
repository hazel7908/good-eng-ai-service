#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0400 사업지역·주변지역 토지이용 파트 핸들러 — W1 (2026-08-31). 소환 최경량.

규약: build_slots / build_tables. 지식: rules/small-env/surrounding-land-use.md.
조서 = 0100 vars 공유, 시군 표 = 지역개황 원천, 사업지구 표 = 조서에서 유도.
⚠️ build_tables Windows 미검증.
"""
from collections import OrderedDict

from hwp_util import MISSING, col_begin, down, find_in_table, fit_rows, right, set_cell


def compute(v):
    """조서 행 → 사업지구 지목별 합산 + 구성비 (rule ③, 원주 99.45 역산 ✓)."""
    js = (v.get("조서") or {}).get("행") or []
    by = OrderedDict()
    for row in js:
        # 행 꼴: [읍면, 리, 지번, 지목, 지적면적, 사업부지, 진출입로, 소계, 비고] — 유연 인덱싱
        try:
            jimok, sogye = row[-6], row[-2]
            by[jimok] = by.get(jimok, 0) + (float(str(sogye).replace(",", "")) or 0)
        except (ValueError, TypeError, IndexError):
            continue
    total = sum(by.values())
    # 표 지목 열은 면적 내림차순이다 (원주 답 99.45 > 전 0.38 > 임 0.17 = 골든 머리 순).
    # 조서 등장 순으로 쓰면 값이 다른 지목 열에 박힌다.
    by = OrderedDict(sorted(by.items(), key=lambda kv: -kv[1]))
    r = {"지목합": by, "면적합": total}
    r["지목비율"] = {k: f"{a / total * 100:.2f}" for k, a in by.items()} if total else {}
    uses = v.get("지구용도") or []          # [{"구분": "보전관리지역", "면적": 23}]
    ut = sum(x.get("면적") or 0 for x in uses)
    r["용도비율"] = [{**x, "비율": (f"{(x.get('면적') or 0) / ut * 100:.2f}" if ut else None)}
                    for x in uses]
    r["용도합"] = ut
    return r


def build_slots(v):
    n = v.get("서술", {})
    tj = v.get("통계", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        "위치용도_서술": g(n, "위치용도"),
        "지목구성_서술": g(n, "지목구성"),
        "시군지목_서술": g(n, "시군지목"),      # 지역개황 2.2 값에서 생성 (D2 일반화 대상)
        "읍면지목_서술": g(n, "읍면지목"),
        "지구지목_서술": g(n, "지구지목"),
        "시군용도_서술": g(n, "시군용도"),
        "지구용도_서술": g(n, "지구용도"),
        "개발사업_서술": g(n, "개발사업"),      # 없음/있음 분기 (rule ④)
        "통계연보연도": g(tj, "통계연보연도"),
        "시군": g(v.get("사업", {}), "시군"),
    }


def build_tables(hwp, v):
    r = compute(v)
    cell = lambda x: set_cell(hwp, str(x) if x not in (None, "") else MISSING)

    print("  편입토지조서 (0100 공유)")
    js = (v.get("조서") or {}).get("행") or []
    if js and find_in_table(hwp, "지적면적"):
        fit_rows(hwp, "지적면적", 7, len(js))
        for i, row in enumerate(js):
            if i:
                down(hwp); col_begin(hwp)
            for val in row:
                cell(val); right(hwp)

    print("  시군·읍면 지목 표 / 시군 용도지역 표 — 지역개황 원천 (vars 행)")
    for name, anchor, base in [("시군지목표", "구성비(%)", 4),
                               ("시군용도표", "비도시지역", 2)]:
        rows = (v.get(name) or {}).get("행") or []
        if not rows:
            print(f"    {name} — 값 없음 (원주 잔존 ⚠️)")
            continue
        if find_in_table(hwp, anchor):
            down(hwp); col_begin(hwp)
            for i, row in enumerate(rows):
                if i:
                    down(hwp); col_begin(hwp)
                for val in row:
                    cell(val); right(hwp)

    print("  사업지구 지목 표 (조서 유도)")
    if r["지목합"] and find_in_table(hwp, "사업계획지구", skip=0):
        # 행 2개: 면적/구성비 — 열은 지목 수에 따라 가변 ⚠️ Windows 확정
        down(hwp); right(hwp)
        cell(f"{r['면적합']:,.0f}")
        for a in r["지목합"].values():
            right(hwp); cell(f"{a:,.0f}")
        down(hwp); col_begin(hwp); right(hwp, 2)
        cell("100.00")
        for p in r["지목비율"].values():
            right(hwp); cell(p)

    print("  사업지구 용도 표")
    if r["용도비율"] and find_in_table(hwp, "보전관리지역"):
        down(hwp); right(hwp)
        cell(f"{r['용도합']:,.0f}")
        for x in r["용도비율"]:
            right(hwp); cell(f"{x.get('면적'):,.0f}" if x.get("면적") else MISSING)
        down(hwp); col_begin(hwp); right(hwp, 2)
        cell("100.00")
        for x in r["용도비율"]:
            right(hwp); cell(x.get("비율"))

    print("  0400 표 편집 종료 (⚠️ Windows 검증 전)")

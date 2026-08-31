#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0724 토지이용 파트 핸들러 — W1 (2026-08-31). = 0400 + 0100 재조합 (rule ⑦→§16).

규약: build_slots / build_tables. 지식: rules/small-env/land-use.md.
compute 는 0400(surrounding-land-use)의 것을 그대로 쓴다 — 세 파트 값 불일치 금지.
⚠️ build_tables Windows 미검증. 문서 내 표 순서(9개):
   현황조사내용 → 시군지목 → 지구지목 → 시군용도 → 지구용도 → 조서
   → 영향예측내용 → 토지이용계획 → 피해방지계획
"""
import importlib.util
import pathlib

from hwp_util import MISSING, col_begin, down, find_in_table, fit_rows, right, set_cell

_p = pathlib.Path(__file__).with_name("surrounding-land-use.py")
_s = importlib.util.spec_from_file_location("part_small_env_surrounding_land_use", _p)
_slu = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_slu)
compute = _slu.compute          # 조서 → 지목 합산·구성비 (원주 99.45 역산 ✓)


def build_slots(v):
    n = v.get("서술", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        "사업명": g(v.get("사업", {}), "사업명"),
        "시군": g(v.get("사업", {}), "시군"),
        "조사시기": g(v.get("현황", {}), "조사시기"),
        # 서술 6종 — 0400 과 같은 vars 원천이되 문장은 0724 원문 꼴 (rule ②)
        "시군지목_서술": g(n, "시군지목"),
        "읍면지목_서술": g(n, "읍면지목"),
        "지구지목_서술": g(n, "지구지목"),
        "시군용도_서술": g(n, "시군용도"),
        "지구용도_서술": g(n, "지구용도"),
        "내부현황_서술": g(n, "내부현황"),      # (3) 위치·지목·주변 시설 한 문장
        "통계연보연도": g(v.get("통계", {}), "통계연보연도"),
    }


def build_tables(hwp, v):
    r = compute(v)
    cell = lambda x: set_cell(hwp, str(x) if x not in (None, "") else MISSING)

    print("  시군·읍면 지목 표 / 시군 용도지역 표 — 지역개황 원천 (0400 과 동일 vars)")
    for name, anchor in [("시군지목표", "구성비(%)"), ("시군용도표", "비도시지역")]:
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

    print("  사업지구 지목 표 (조서 유도 — 면적 내림차순)")
    # ⚠️ '사업계획지구'는 현황조사내용 표 조사범위 셀에 먼저 나온다 → skip=1
    # ⚠️ 지목 집합이 베이스 머리(답·전·임)와 다르면 머리 행도 재기입해야 한다 — Windows 확정
    if r["지목합"] and find_in_table(hwp, "사업계획지구", skip=1):
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

    print("  편입토지조서 (0100·0400 공유)")
    js = (v.get("조서") or {}).get("행") or []
    if js and find_in_table(hwp, "지적면적"):
        fit_rows(hwp, "지적면적", 7, len(js))
        for i, row in enumerate(js):
            if i:
                down(hwp); col_begin(hwp)
            for val in row:
                cell(val); right(hwp)

    print("  토지이용계획 (0100 공유 — 비율 유도)")
    rows = v.get("토지이용") or []
    total = sum(x.get("면적") or 0 for x in rows)
    if rows and find_in_table(hwp, "비 율(%)"):
        fit_rows(hwp, "비 율(%)", 4, len(rows))
        down(hwp); col_begin(hwp)
        for i, x in enumerate(rows):
            if i:
                down(hwp); col_begin(hwp)
            for val in [x.get("구분"), (f"{x['면적']:,.2f}" if x.get("면적") else None),
                        (f"{(x.get('면적') or 0) / total * 100:.2f}" if total else None), "-"]:
                cell(val); right(hwp)
        down(hwp); col_begin(hwp); right(hwp)
        cell(f"{total:,.2f}")
        right(hwp); cell("100.00")

    print("  피해방지계획 (0100 공유 — 설계 수량)")
    rows = (v.get("피해방지") or {}).get("행") or []
    if not rows:
        print("    피해방지 — 값 없음 (원주 잔존 ⚠️ leak_check 대상)")
    elif find_in_table(hwp, "수 량"):
        fit_rows(hwp, "수 량", 8, len(rows))
        down(hwp); col_begin(hwp)
        for i, row in enumerate(rows):
            if i:
                down(hwp); col_begin(hwp)
            for val in row:
                cell(val); right(hwp)

    print("  0724 표 편집 종료 (⚠️ Windows 검증 전)")

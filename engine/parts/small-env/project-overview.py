#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사업개요(0100) 파트 핸들러 — W1 (2026-08-31). 인풋 전개형 (계산은 비율뿐).

규약: build_slots(v) / build_tables(hwp, v). 지식: rules/small-env/project-overview.md.
⚠️ 인풋 순환 금지 — vars 는 신청서류에서 만든다 (rule §0). input/사업개요.txt 사용 금지.
⚠️ build_tables 는 Windows 미검증. 사업시행자 표의 열 구조 변형(2열↔3열)은 미지원 —
   기준 사업(원주 2열) 틀만. 대상사업 기준 셀은 통째 교체(조항 3계열 분기).
"""
from hwp_util import MISSING, col_begin, down, find_in_table, fit_rows, right, set_cell


def compute(v):
    r = {}
    rows = v.get("토지이용") or []
    total = sum(x.get("면적") or 0 for x in rows)
    r["토지이용"] = [
        {**x, "비율": (f"{(x.get('면적') or 0) / total * 100:.2f}" if total else None)}
        for x in rows
    ]
    r["토지이용_합"] = total
    js = (v.get("조서") or {}).get("행") or []
    # 조서 행: [..., 지적면적, 사업부지, 도로, 소계, 비고] — 숫자 열 합계 (합계 필드 덮기용)
    r["조서_행수"] = len(js)
    return r


def build_slots(v):
    sa, gj, bg, gw, il = (v.get("사업", {}), v.get("실시근거", {}), v.get("배경", {}),
                           v.get("경위", {}), v.get("일정", {}))
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        "사업명": g(sa, "사업명"),
        "위치": g(sa, "위치"),
        "면적": (f"{sa['면적_㎡']:,}" if sa.get("면적_㎡") else MISSING),
        "허가권자": g(sa, "허가권자"),
        "배경_서술": g(bg, "서술"),          # 5꼴 자유 서술 — 판단 (rule §2)
        "실시근거_서술": g(gj, "서술"),      # 단순형/증설형 분기 (rule §4-2)
        "경위_조사": g(gw, "조사"),
        "경위_작성": g(gw, "작성"),
        "경위_요청": g(gw, "요청"),
        "경위_알림": g(gw, "알림"),
        "착공일": g(il, "착공일"),
        "준공일": g(il, "준공일"),
    }


def build_tables(hwp, v):
    """표 편집 6종. 앵커·오프셋은 Windows 세션에서 확정."""
    r = compute(v)
    gj = v.get("실시근거", {})
    cell = lambda x: set_cell(hwp, str(x) if x not in (None, "") else MISSING)

    print("  실시근거 표 — 대상사업 기준 셀 통째 교체 + 사업규모")
    if gj.get("대상사업_기준") and find_in_table(hwp, "대 상 사 업"):
        right(hwp)
        cell(gj["대상사업_기준"])           # 조항 3계열 분기 (rule §4-1)
    if gj.get("규모_셀") and find_in_table(hwp, "사 업 규 모"):
        right(hwp)
        cell(gj["규모_셀"])                 # 단순형 "13,934㎡" / 증설형 3분할 텍스트

    print("  편입토지조서")
    js = (v.get("조서") or {}).get("행") or []
    if js and find_in_table(hwp, "지적면적"):
        fit_rows(hwp, "지적면적", 7, len(js))     # 원주 베이스 7행
        for i, row in enumerate(js):
            if i:
                down(hwp)
                col_begin(hwp)
            for val in row:
                cell(val)
                right(hwp)

    print("  사업시행자 (원주 2열 틀)")
    sh = (v.get("시행자") or {}).get("행") or []
    if sh and find_in_table(hwp, "성 명"):
        fit_rows(hwp, "성 명", 6, len(sh))        # 원주 베이스 6행
        down(hwp)
        col_begin(hwp)
        for i, row in enumerate(sh):
            if i:
                down(hwp)
                col_begin(hwp)
            for val in row:
                cell(val)
                right(hwp)

    print("  토지이용계획 (비율 계산)")
    tl = r["토지이용"]
    if tl and find_in_table(hwp, "비 율(%)"):
        fit_rows(hwp, "비 율(%)", 4, len(tl))     # 원주/괴산 베이스 4행 + 합계
        down(hwp)
        col_begin(hwp)
        for i, x in enumerate(tl):
            if i:
                down(hwp)
                col_begin(hwp)
            for val in [x.get("구분"), (f"{x['면적']:,.2f}" if x.get("면적") else None),
                        x.get("비율"), "-"]:
                cell(val)
                right(hwp)
        down(hwp)
        col_begin(hwp)
        right(hwp)
        cell(f"{r['토지이용_합']:,.2f}")
        right(hwp)
        cell("100.00")

    print("  발전설비·피해방지 (설계값 행)")
    for name, anchor, base in [("설비", "태양전지방식", 0), ("피해방지", "수 량", 8)]:
        rows = (v.get(name) or {}).get("행") or []
        if not rows:
            print(f"    {name} — 값 없음 (원주 잔존 ⚠️ leak_check 대상)")
            continue
        if find_in_table(hwp, anchor):
            if base:
                fit_rows(hwp, anchor, base, len(rows))
            down(hwp)
            col_begin(hwp)
            for i, row in enumerate(rows):
                if i:
                    down(hwp)
                    col_begin(hwp)
                for val in row:
                    cell(val)
                    right(hwp)

    print("  사업개요 표 편집 종료 (⚠️ Windows 검증 전)")

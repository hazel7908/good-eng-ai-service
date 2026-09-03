#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `resource-cycle` 핸들러 — C (2026-09-03 Mac). 지식: rules/strategic-env/resource-cycle.md.

규약: vars `slots` 평면 사전을 토큰에 준다(없으면 [확인 필요]). 관리구역·분뇨 값 토큰 · 매립/소각/기타/폐유 표는 비움(소환 0726 `calc_waste` 이식 자리).
BLANK 의 앵커·머리행은 Windows 실측 전 추정.
"""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("총매립용량", 3, 1), ("소각방식", 2, 1), ("시설명", 2, 1), ("잡품비(%)", 1, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = 0
        while k < limit and find_in_table(hwp, anchor, skip=k):
            n = blank_table_here(hwp, header_rows=hdr); print(f"  비움 `{anchor}` #{k + 1} — {n}셀"); k += 1
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음")
    if not BLANK:
        print("  표 편집 없음 (반고정 표 — 값은 빈칸 치환)")


EXPECT = ['관리구역_서술', '처리시설_서술', '분뇨_서술', '계획명_공백', '투입장비_서술', '폐기물통계연도', '통계연보연도', '시군', '관리구역_인구', '배출량', '일인당발생량', '분뇨발생량', '일인당분뇨', '계획명', '관리구역_면적']

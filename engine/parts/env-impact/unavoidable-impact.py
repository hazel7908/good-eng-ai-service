#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본환 `unavoidable-impact` 핸들러 — C (2026-09-03 Mac). 지식: rules/env-impact/unavoidable-impact.md.

요약장 규약: vars `slots` 평면 사전을 그대로 토큰에 준다(없으면 [확인 필요]). B 단계에서 9장 vars 조립으로 교체.
분야별 표 셀은 반고정 불릿(골프장 항목 `농약·비료`는 _확인필요).
"""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = []      # (앵커, 머리행 수, 상한)


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


EXPECT = ['불가피_도입', '불가피_자연생태', '불가피_대기', '불가피_수환경_1', '불가피_수환경_2', '불가피_토지_1', '불가피_토지_2', '불가피_토지_3', '불가피_생활', '불가피_사회경제', '사업명']

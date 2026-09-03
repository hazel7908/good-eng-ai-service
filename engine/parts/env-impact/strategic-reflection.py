#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본환 `strategic-reflection` 핸들러 — C (2026-09-03 Mac). 지식: rules/env-impact/strategic-reflection.md.

요약장 규약: vars `slots` 평면 사전을 그대로 토큰에 준다(없으면 [확인 필요]). B 단계에서 9장 vars 조립으로 교체.
협의내용↔반영 표 2개는 협의의견 문서 인풋 — 핸들러가 비운다(머리행만 남김).
"""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("협의내용", 1, 2)]      # (앵커, 머리행 수, 상한)


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


EXPECT = ['반영_도입', '사업명']

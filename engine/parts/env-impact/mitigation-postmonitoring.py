#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본환 `mitigation-postmonitoring` 핸들러 — C (2026-09-03 Mac). 지식: rules/env-impact/mitigation-postmonitoring.md.

요약장 규약: vars `slots` 평면 사전을 그대로 토큰에 준다(없으면 [확인 필요]). B 단계에서 9장 vars 조립으로 교체.
저감방안 표 5·사후조사 표 9는 반고정 틀 — 사업 고유 수치·보호종만 토큰.
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


EXPECT = ['저감_도입', '이식수목_주수', '방진망_제원', '급수공급', '오수처리계획', '생태면적률', '방음판넬_제원', '사후_수질_지점', '사후_대기_지점수', '사후_소음_공사지점수', '사후_소음_운영지점수', '보호종대책_1', '보호종대책_2', '보호종대책_3', '보호종대책_4', '보호종대책_5', '보호종대책_6', '사후_보호종_1', '사후_보호종_2', '사후_보호종_3', '사후_보호종_4', '사후_보호종_5', '사업명', '시군']

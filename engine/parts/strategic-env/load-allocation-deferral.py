#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `load-allocation-deferral` 핸들러 — C (2026-09-03 Mac). 규약: vars `slots` 평면 사전. 별첨 — 개요·경위 13·계획 범위 표·시설물 표·연기 사유·서식 셀 ≈75 통문장 + 값 12 (2장 vars 승계 자리). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = []


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
        print("  표 편집 없음")


EXPECT = ['유보_8', '유보_9', '유보_11', '유보_151', '유보_152', '유보_48', '유보_171', '유보_7', '유보_153', '유보_126', '유보_42', '유보_38', '유보_41', '유보_36', '유보_35', '유보_40', '유보_39', '유보_33', '유보_30', '유보_64', '유보_34', '유보_122', '유보_65', '유보_79', '유보_117', '유보_139', '유보_31', '유보_32', '유보_37', '유보_200', '유보_196', '유보_119', '유보_118', '유보_101', '유보_105', '유보_102', '유보_140', '유보_143', '유보_109', '유보_110', '유보_131', '유보_134', '유보_201', '유보_130', '유보_135', '유보_202', '표지연월', '하천지정근거', '하천1_유역_고시', '하천1_연장_고시', '하천1_유역', '하천1_연장', '하천2_연장_고시', '하천2_연장', '연장합_고시', '연장합', '하천2_유역_고시', '하천2_유역', '계획명_공백', '계획수립기관', '계획승인기관', '계획명', '하천지정일']

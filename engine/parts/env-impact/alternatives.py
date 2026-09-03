#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `alternatives` 핸들러 — C (2026-09-03 Mac). 규약: vars `slots` 평면 사전. 대안 사유·검토내용·비교 셀·수요 서술 ≈55 통문장 · 골프장 통계 표 5 비움(사업군 고유). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("골프장수", 2, 1), ("이용객 수(인)", 2, 1), ("18홀(인)", 2, 1), ("벨라스톤컨트리클럽", 1, 2)]


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


EXPECT = ['대안_72', '대안_167', '대안_166', '대안_139', '대안_53', '대안_73', '대안_121', '대안_242', '대안_243', '대안_49', '대안_146', '대안_45', '대안_100', '대안_271', '대안_164', '대안_116', '대안_41', '대안_136', '대안_145', '대안_37', '대안_95', '대안_138', '대안_88', '대안_120', '대안_94', '대안_89', '대안_161', '대안_158', '대안_134', '대안_109', '대안_90', '대안_118', '대안_155', '대안_83', '대안_84', '대안_111', '대안_154', '대안_160', '대안_92', '대안_87', '대안_93', '대안_85', '대안_68', '대안_59', '대안_61', '대안_66', '대안_113', '대안_159', '대안_63', '사업명_약칭', '사업명']

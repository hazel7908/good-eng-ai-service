#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `natural-assets` 핸들러 — C (2026-09-03 Mac). 규약: vars `slots` 평면 사전. 보호지역 확인 문장 9·현지조사·영향예측·저감 서술 ≈55 통문장 · 문헌·출현 표 비움 · ○× 조사항목 표 유지. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("문헌조사(격자번호)", 2, 1), ("대상종", 3, 1)]


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


EXPECT = ['자산_341', '자산_328', '자산_335', '자산_315', '자산_322', '자산_339', '자산_358', '자산_353', '자산_324', '자산_351', '자산_362', '자산_344', '자산_345', '자산_357', '자산_354', '자산_361', '자산_343', '자산_115', '자산_346', '자산_325', '자산_252', '자산_330', '자산_350', '자산_365', '자산_369', '자산_347', '자산_355', '자산_333', '자산_319', '자산_320', '자산_331', '자산_367', '자산_342', '자산_104', '자산_338', '자산_309', '자산_311', '자산_100', '자산_255', '자산_96', '자산_98', '자산_102', '자산_108', '자산_110', '자산_259', '자산_256', '자산_263', '자산_106', '자산_112', '자산_258', '자산_262', '자산_265', '하천1_명', '하천2_명']

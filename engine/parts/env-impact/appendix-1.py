#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `appendix-1` 핸들러 — C+ (2026-09-04 Mac). 규약: vars `slots`. 평가대행자 인적사항·명단·등록증·계약서·용어해설 — **회사 상시 고정, 토큰 0**(소환 0800 방침 · 개인정보 vars 금지) · 15.2 용역계약서 스캔은 기본 걷어내기(소재평 8장 부류 — shapeComment 청소 포함)."""
from hwp_util import MISSING, blank_tables

BLANK = []


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음")
    if not BLANK:
        print("  표 편집 없음")


EXPECT = []

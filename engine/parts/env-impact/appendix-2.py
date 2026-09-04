#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `appendix-2` 핸들러 — C+ (2026-09-04 Mac). 규약: vars `slots`. 동식물상 현지조사표·증빙 **스캔 이미지 묶음**(20줄) — 토큰 0 · 그림은 사업 고유(조사표·조사자 사진) → 기본 걷어내기 · 러프 산출물은 자리표시자 쪽(사람이 조사표 삽입)."""
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

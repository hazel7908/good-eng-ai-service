#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `appendix-3` 핸들러 — C+ (2026-09-04 Mac). 규약: vars `slots`. 측정사진·시험성적서·모델링 입력자료 — AERMOD 제목(TITLEONE + 페이지 머리 ×9)만 토큰 · 입력 전문은 `[모델링 필요]` 부류(할 일 3) · 측정사진·성적서 스캔은 걷어내기(측정 파트 vars 승계 자리)."""
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


EXPECT = ['사업명']

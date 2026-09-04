#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `topo-geology` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 지형지질(생태축 포함) — 표고경사·지질·능선 서술 수확 + 하천명 · 분석 표 비움(GIS 인풋). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("표고", 2, 3), ("경사", 2, 3), ("지층", 1, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['계획명', '시군', '서술_36', '하천1_명', '하천2_명', '서술_130', '서술_225', '읍면', '서술_384', '서술_386', '서술_596', '서술_667', '서술_703', '서술_1102']

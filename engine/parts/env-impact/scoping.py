#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `scoping` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 협의회 심의 — 심의기간·안건·위원구성 토큰(마스킹) · 위원 표·심의의견↔조치 표 14 비움(심의의견서 문서 인풋 · 위원 실명·소속 포함). 5.1 근거 절은 법령 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_table_here, blank_tables, find_in_table

BLANK = [("심의의견", 2, 14), ("직  위", 1, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")
    if not BLANK:
        print("  표 편집 없음")


EXPECT = ['안건', '심의기간', '위원구성', '사업명', '시군']

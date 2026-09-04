#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `noise-vib` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 소음진동 — 측정 결과·예측 서술 수확 + 하천명 · 측정·장비·이격 표 비움(B: 소환 0727 계산기). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("주간 평균", 2, 2), ("소음도", 2, 3), ("진동레벨", 2, 2), ("정온시설", 2, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['서술_506', '서술_170', '서술_242', '계획명_공백', '시군', '읍면', '하천1_명', '하천2_명']

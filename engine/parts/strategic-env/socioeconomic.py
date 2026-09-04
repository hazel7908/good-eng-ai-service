#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `socioeconomic` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 사회경제 — 지목·용도·인구·산업 서술 수확(소환 0724 문형) + 하천명 · 통계 표 비움(B: 통계 소싱). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("구성비", 2, 4), ("사업체수", 2, 2), ("세대", 2, 3), ("행정구역", 1, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['서술_19', '서술_527', '서술_18', '서술_268', '서술_961', '서술_656', '계획명', '시군', '읍면', '하천1_명', '하천2_명']

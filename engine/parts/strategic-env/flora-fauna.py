#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `flora-fauna` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 동식물상 — 결과 문장 수확 + 하천명 · 집계 표 비움 · **종목록 spec 밖**(J-1 · 표유출 ② 실패 정상). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("분류군", 3, 4), ("우점종", 2, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['계획명_공백', '시군', '읍면', '하천1_명', '하천2_명', '서술_575', '서술_761', '서술_1082', '서술_1147', '서술_1196', '서술_1333', '서술_1418', '서술_1450', '서술_1480', '서술_1505', '서술_1528', '서술_2532', '서술_2588', '서술_2592', '서술_2593', '서술_2622', '서술_2623', '서술_2657', '서술_2658', '서술_2688', '서술_2823', '서술_2827', '서술_2828', '서술_2872', '서술_2873', '서술_2918', '서술_2919', '서술_2956', '서술_2957', '서술_3361']

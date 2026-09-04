#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `landscape` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 경관 — 보호지역 정형·문화재·조망 서술 수확 + 하천명 · 문화재·조망점·생태자연도 표 비움. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("문화재", 2, 2), ("조망점", 2, 3), ("생태자연도", 1, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['서술_161', '서술_258', '서술_306', '서술_200', '서술_587', '서술_243', '서술_591', '서술_594', '서술_571', '서술_96', '서술_564', '서술_241', '서술_561', '서술_159', '서술_568', '서술_575', '서술_584', '서술_578', '계획명', '시군', '읍면', '하천1_명', '하천2_명']

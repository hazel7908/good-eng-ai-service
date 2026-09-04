#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `appendix` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 부록 — 인용문헌 사업 고유 줄 + 계획명·하천명·기상연보 · 참여자 명단 회사 고정 · 조사목록 캡션은 하천명 토큰이 처리. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("성명", 1, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['기상_기간', '관측소', '계획명', '시군', '읍면', '하천1_명', '하천2_명']

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `plan-overview` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 개발기본계획 개요(하천기본계획 본체 5,891줄) — 사업 고유 문장 수확(≤60) + 하천·행정명 토큰 · 시설·연장·사업비 표 비움.

⚠️ 대형 문서 인풋 장 — 계산·계획 표는 전부 비운다. BLANK 앵커는 Windows 실측 전 추정.
러프 산출물 = 골격 + 사업 고유 문장 토큰 + `[확인 필요]` 표 (하천기본계획/상위계획 원문은 사업 문서 인풋)."""
from hwp_util import MISSING, blank_tables

BLANK = [("시설물 설치계획", 2, 2), ("연장", 2, 6), ("사업비", 2, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['계획명', '서술_5', '서술_6', '계획명_공백', '서술_49', '하천1_명', '시군', '읍면', '하천2_명', '시도', '서술_4310', '서술_4311', '서술_4312', '서술_4313', '서술_4315', '서술_4316', '서술_4317', '서술_4320', '서술_4987', '서술_5282', '서술_5331', '서술_5392', '서술_5507', '서술_5578']

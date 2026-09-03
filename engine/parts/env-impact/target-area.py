#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `target-area` 핸들러 — C (2026-09-03 Mac). 지식: rules/env-impact/target-area.md.

규약: vars `slots` 평면 사전을 토큰에 준다(없으면 [확인 필요]). 평가항목별 대상지역 표(반고정 + 지점 수 토큰) · 예측기법 표 반고정.
BLANK 의 앵커·머리행은 Windows 실측 전 추정.
"""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = []


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = 0
        while k < limit and find_in_table(hwp, anchor, skip=k):
            n = blank_table_here(hwp, header_rows=hdr); print(f"  비움 `{anchor}` #{k + 1} — {n}셀"); k += 1
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음")
    if not BLANK:
        print("  표 편집 없음 (반고정 표 — 값은 빈칸 치환)")


EXPECT = ['위치', '면적', '사업기간', '관측소', '기상_기간', '환경질_지점수', '지표수질_지점수', '지하수질_지점수', '예측_하천수', '연보연도', '사업명']

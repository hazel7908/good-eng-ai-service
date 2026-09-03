#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `climate` 핸들러 — C (2026-09-03 Mac). 규약: vars `slots` 평면 사전. 기상연보 서술 7(문장 꼴이 소환과 다름 — 통문장) · 일람표·10년 표·월별 표 6은 kma.py 채움 전 비움 (열 구성이 소환과 달라 위임 불가). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("H(m)", 1, 1), ("평균최고", 1, 2), ("강수량", 1, 1), ("평균습도", 1, 1), ("일조시간", 1, 1), ("평균풍속", 1, 1), ("강수일", 1, 1)]


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


EXPECT = ['종합분석_서술', '기온_서술', '강수량_서술', '습도_서술', '일조_서술', '풍속_서술', '강수일_서술', '기간시작', '기간끝', '관측소', '연보최신', '계획명', '시군']

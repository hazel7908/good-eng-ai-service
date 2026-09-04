#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `public-opinion` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 의견수렴 — 기관·공고·공람·설명회 값 토큰(일자·장소 일부 마스킹) · 현수막 위치 표·의견↔반영 표 8 비움(검토의견 문서 인풋). 6.1 절차 서술은 법령 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_table_here, blank_tables, find_in_table

BLANK = [("옥계1리마을 초입", 0, 1), ("반영여부", 2, 8)]


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


EXPECT = ['의견수렴_도입', '공람기간', '제출기간', '기관의견_일자', '설명회_장소', '공고신문', '설명회_일시', '공람_홈페이지', '공람장소', '기관의견_일자2', '공고일', '공고지_1', '사업명', '공고지_2', '유역환경청_표기', '협의기관_표기', '승인기관_표기', '의견대상_1', '의견대상_3', '수립행정기관장', '의견대상_2', '시군']

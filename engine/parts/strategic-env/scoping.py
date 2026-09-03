#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `scoping` 핸들러 — C 틀 (2026-09-03 Mac). 규약: vars `slots`. 협의회 심의 — 심의기간·안건·위원 구성·의견서 제출자 8·심의 절 제목 8(전부 마스킹) 토큰 · 명단 표·심의의견 표 16 비움 · 6.3~6.4 평가항목 설정 표는 반고정 유지. 잔존 기관명은 비우는 표 셀뿐. 표는 전부 비운다(문서 인풋)."""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("의견서 제출여부", 1, 1), ("조치결과(계획)", 1, 16)]


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


EXPECT = ['안건', '심의기간', '위원구성', '심의의견서_3', '심의의견서_4', '심의의견서_5', '심의절_3', '심의절_4', '심의의견서_1', '심의의견서_2', '심의절_2', '심의의견서_6', '계획명', '심의의견서_7', '심의의견서_8', '심의절_7', '심의절_1', '심의절_8', '심의절_5', '심의절_6']

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `public-opinion` 핸들러 — C 틀 (2026-09-03 Mac). 규약: vars `slots`. 의견수렴 — 필요성·주관기관·대상·공람 기간/장소·일간지·설명회·의견기관 제목 토큰 · 설명회 표·제출의견 표 24 비움. 잔존 기관명은 비우는 표 셀·의견서 캡션뿐. 표는 전부 비운다(문서 인풋)."""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("장   소", 1, 1), ("조치계획 및 미반영 사유", 1, 24)]


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


EXPECT = ['필요성_서술', '공람장소', '공람기간', '의견수렴대상', '의견기관_6', '설명회1_일시', '의견기관_7', '의견기관_9', '의견기관_8', '공고일간지', '의견기관_10', '의견기관_5', '계획명_공백', '의견기관_1', '주관행정기관', '의견기관_2', '의견기관_4', '신문1', '신문2', '의견기관_3', '설명회1_장소']

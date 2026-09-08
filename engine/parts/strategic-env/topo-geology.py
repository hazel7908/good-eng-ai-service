#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `topo-geology` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 지형지질(생태축 포함) — 표고경사·지질·능선 서술 수확 + 하천명 · 분석 표 비움(GIS 인풋). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("표고", 2, 3), ("경사", 2, 3), ("지층", 1, 2),
         ("지질시대(지층명)", 1, 1), ("백두대간보호지역 편입면적", 2, 1),
         # ⚠️ 09-08 anchor_suggest — 되먹임 사각 18표 중 사업 고유 15개.
         #    능선축 위계별 계획목표(KEI 안내서)·둑마루폭·여유고 기준표는 **하천설계기준**
         #    이라 뺐다 — 전국 공통값이다.
         ("분포여부(●, ×)", 2, 1), ("소재지", 1, 1), ("고호", 1, 2),
         # ⚠️ 계획여유고는 머리 **1행**이다 — 2로 두면 첫 데이터 행이 살아남는다
         ("소류력", 2, 4), ("구 간(No.)", 1, 1), ("개선방향 (개소)", 2, 2),
         ("설치목적", 1, 2), ("여유고검토", 2, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['분지지형_절제목', '분지지형_서술1', '분지지형_서술2', '계획명', '시군', '서술_36', '하천1_명', '하천2_명', '서술_130', '서술_225', '읍면', '서술_384', '서술_386', '서술_596', '서술_667', '서술_703', '서술_1102']

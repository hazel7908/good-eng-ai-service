#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `air-quality` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 대기질 — 서술 수확 + 계획명·시군·하천명 · 측정 표 비움 · 정량 예측 없음(하천 계획 단계 — 정성 반고정). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("측정망", 1, 1), ("SO2", 2, 4),
         # ⚠️ 09-08 — 관측소별 문헌조사결과 2표 + 환경보전목표(용도지역별).
         #    고정: 공사장비 배출량(예시) · 입자크기별 구성비 · 세륜세차 기준 ·
         #    비산먼지 저감효과 — 전국 표준값이다.
         ("(년-월-일)", 2, 2), ("환경보전목표(24hr)", 1, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['서술_595', '계획명', '시군', '하천1_명', '하천2_명']

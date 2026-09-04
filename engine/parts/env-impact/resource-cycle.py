#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `resource-cycle` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 자원순환 — 현황 서술 9(시군 통계 — 소환 0726 rule·`calc_waste` 이식 자리)·예측 서술 9·값 2 = 22토큰 · 통계 표 9와 산정 표(폐유·인부·건폐·임목·농약·비료·슬러지)는 비움 · 저감방안(분리수거 요령 등)은 반고정. BLANK 앵커는 Windows 실측 전 추정.

B 단계: 현황 통계는 소환 0726 소싱(`전국 폐기물 발생 및 처리현황` — `stats_registry`)·산정은 `calc_waste.py` 이식.
"""
from hwp_util import MISSING, blank_tables

BLANK = [("1일1인당", 2, 1), ("재활용", 2, 4), ("총매립용량", 2, 1), ("소각방식", 2, 1), ("잡품비", 1, 1), ("정화조 처리대상인원", 2, 1), ("훼손수목", 2, 2), ("성분량", 2, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['관리구역_서술', '인부_서술', '훼손수목_서술', '슬러지SS_서술', '하수처리_서술', '농약원단위_서술', '슬러지_서술', '농약사용면적_주', '건설폐기물_서술', '폐농약_서술', '음식물_서술', '매립_서술', '소각_서술', '인부폐기물_서술', '생활폐기물_서술', '사업장폐기물_서술', '운영폐기물_서술', '폐유예측_서술', '지정폐기물_서술', '이식수목_주수', '사업명', '시군']

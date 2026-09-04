#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `topo-geology` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 지형지질 — 시군 지형·표고경사·특이지형·지반조사 도입·영향 서술 13토큰 · 표고/경사·시추·N값·토공·재해위험도 평가 표는 비움(GIS·시추 인풋 — 소환 0725 rule 참고) · 골프 안전 검토(2280~)는 사업개요 2.6 과 같은 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("구성비(%)", 2, 4), ("표준관입시험", 2, 2), ("지층개황", 1, 1), ("절토량", 1, 2), ("평가점수", 2, 4)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['시군지형_서술', '표고경사_서술', '지형현황_서술', '산지능선_서술', '지질노두_서술', '토공량_서술', '특이지형_서술', '영향예측_도입', '지형훼손_서술', '산줄기_서술', '사업명', '읍면리', '시군']

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `regional-overview` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 지역개황(소환 2장 축약) — 개황·지목·용도·보호지역·기초시설 서술 전부 토큰(지역개황 정형 문장 — 소환 `build_vars_regional` 이식 1순위 D2) · 종합표 ○×·통계 표는 비움 · 골프장 입지기준 발췌(241~290)는 반고정.

B 단계: 소환 `build_vars_regional` 절 조합 일반화(D2) — 서술·표를 통계 소싱으로 채운다.
"""
from hwp_util import MISSING, blank_tables

BLANK = [("구성비", 2, 3), ("해당유무", 1, 2), ("포장율(%)", 1, 1), ("배출시설", 2, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['청정연료_서술', '읍면개황_서술', '시군개황_서술', '배출허용_서술', '자연공원_서술', '지목_서술', '개황718_서술', '대기특별_서술', '대기권역_서술', '야생생물_서술', '도로_서술', '상수원_서술', '개황588_서술', '개황484_서술', '습지_서술', '생태경관_서술', '백두대간_서술', '수변_서술', '개황715_서술', '종합개황_도입', '산림유전_서술', '용도지역_서술', '사업명', '시군']

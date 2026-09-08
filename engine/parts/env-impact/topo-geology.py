#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `topo-geology` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 지형지질 — 시군 지형·표고경사·특이지형·지반조사 도입·영향 서술 13토큰 · 표고/경사·시추·N값·토공·재해위험도 평가 표는 비움(GIS·시추 인풋 — 소환 0725 rule 참고) · 골프 안전 검토(2280~)는 사업개요 2.6 과 같은 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("구성비(%)", 2, 4), ("표준관입시험", 2, 2), ("붕적층/", 1, 1), ("총토공량", 1, 1), ("절 토(㎥)", 1, 2), ("평가점수", 2, 4),
         # ⚠️ 09-08 — 되먹임 사각 10표 중 사업 고유 8개(산출물 머리 셀 실측).
         #    사후환경영향조사 계획은 표준 문안이라 뺐다.
         ("조 사 내 용", 1, 1), ("기호", 2, 1), ("분포심도(GL.-m)", 2, 1),
         ("시험심도(GL.(-)m)", 2, 1), ("상대밀도", 2, 1),
         # ⚠️ 09-08 — `공내지하수위` 는 **캡션**이라 셀에 없다(`find_in_table` 실패).
         #    시추공 수위 표 2개의 머리행 셀로 잡는다.
         ("지반고", 2, 3),   # ⚠️ 셀이 `지반고`/`EL(+)m` **두 문단**이라 붙여 쓰면 영원히 못 찾는다
         ("선정사유", 2, 1), ("지 반 정 수", 2, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['시군지형_서술', '표고경사_서술', '지형현황_서술', '산지능선_서술', '지질노두_서술', '토공량_서술', '특이지형_서술', '영향예측_도입', '지형훼손_서술', '산줄기_서술', '사업명', '읍면리', '시군']

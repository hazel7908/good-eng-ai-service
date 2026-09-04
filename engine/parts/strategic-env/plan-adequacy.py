#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `plan-adequacy` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 계획의 적정성(상위계획 검토 4,694줄) — 연계성 서술 수확 + 행정명 토큰 · 국가계획(국토종합 등) 발췌는 반고정 · **도·시군 계획 블록은 delete_range 후보**(검토서 3장 방식 — Windows 실측 후 확정).

⚠️ 대형 문서 인풋 장 — 계산·계획 표는 전부 비운다. BLANK 앵커는 Windows 실측 전 추정.
러프 산출물 = 골격 + 사업 고유 문장 토큰 + `[확인 필요]` 표 (하천기본계획/상위계획 원문은 사업 문서 인풋)."""
from hwp_util import MISSING, blank_tables

BLANK = [("추진전략", 1, 3), ("비전", 1, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['계획명', '서술_72', '시도', '서술_117', '서술_182', '서술_188', '하천1_명', '하천2_명', '시군', '읍면', '서술_1746', '서술_1749', '서술_1752', '서술_1851', '서술_1855', '서술_1860', '서술_1862', '서술_1865', '서술_1867', '서술_1868', '서술_1889', '서술_1926', '서술_1945', '서술_1946', '서술_2047', '서술_2434', '서술_2451', '서술_3525', '서술_3767', '서술_3784', '서술_4136']

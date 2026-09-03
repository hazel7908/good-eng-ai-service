#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `target-area` 핸들러 — C (2026-09-03 Mac). 지식: rules/strategic-env/target-area.md.

규약: vars `slots` 평면 사전을 토큰에 준다(없으면 [확인 필요]). 설정사유 표·대상범위 표는 하천 계획 반고정 — 도입·특성 서술 6 통문장만.
BLANK 의 앵커·머리행은 Windows 실측 전 추정.
"""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = []


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
    if not BLANK:
        print("  표 편집 없음 (반고정 표 — 값은 빈칸 치환)")


EXPECT = ['대상지역_도입', '공간적범위_서술', '입지적특성_서술', '환경적특성_서술', '설정사유_도입', '평가범위_도입', '동식물_조사범위', '대기소음_조사범위', '계획명']

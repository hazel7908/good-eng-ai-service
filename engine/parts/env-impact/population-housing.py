#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `population-housing` 핸들러 — C (2026-09-03 Mac). 지식: rules/env-impact/population-housing.md.

규약: vars `slots` 평면 사전을 토큰에 준다(없으면 [확인 필요]). 통계연보 5표(인구추이·취약계층·출생사망·이동·주거) — 0500 5.3 `extract_0500` 소싱 재사용 자리, 러프는 비움 · 골든 오탈 `충주시` 교정.
BLANK 의 앵커·머리행은 Windows 실측 전 추정.
"""
from hwp_util import MISSING, blank_table_here, find_in_table

BLANK = [("세대당", 2, 1), ("어린이(14세 이하)", 1, 1), ("출생(명)", 2, 1), ("순이동", 2, 1), ("종류별 주택수", 3, 1)]


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


EXPECT = ['인구추이_서술', '취약계층_서술', '인구증감_서술', '인구이동_서술', '주거_서술', '영향_공사시', '영향_운영시', '저감_공사시_1', '저감_공사시_2', '저감_운영시', '주민수용성_1', '주민수용성_2', '통계기준연도', '통계연보연도', '시군', '사업명']

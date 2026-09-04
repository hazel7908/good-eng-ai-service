#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `soil` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 토양 측정 파트(소환 측정 3파트 부류 — 측정성적서 인풋) — 지점·일시·서술 26토큰 · 측정결과 표(항목 22행 × 6값)·비옥토·농약(현황·산정)·비료 표는 비움 · 우려기준표 823~는 법령 반고정(conservation-goal 과 같은 표 — 판 고정). BLANK 앵커는 Windows 실측 전 추정.

측정결과 표(22항목 × 6값)는 머리 3행(지점번호|S-1~3|1·2차) — 앵커 `토양오염우려기준`(머리 우측 셀).
우려기준·대책기준 표(법령)는 손대지 않는다.
"""
from hwp_util import MISSING, blank_table_here, blank_tables, find_in_table

BLANK = [("토양오염우려기준", 2, 1), ("비옥토 미분포지역(㎡)", 1, 1), ("농약사용면적", 2, 2), ("비료살포", 2, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['폐유_서술', '농약영향_서술2', '비옥토_서술', '농약영향_서술3', '비료_서술', '유출영향_서술', '사후조사_도입', '부지정지_서술', '근로자_서술', '농약영향_서술1', '농약사용량_서술', '농약원단위_서술', '측정결과_서술', '측정지점_서술', '유발시설_서술', '영향예측_도입', '지점변경_주', '조사시기_2차', '측정일_2차', 'S2_위치', 'S3_위치_1차', 'S3_위치_2차', '조사시기_1차', 'S1_위치', '측정일_1차', '사업명']

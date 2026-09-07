#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `air-quality` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 대기질 — 측정(지점 3·결과)·예측(토공·초과·저감후) 서술 13토큰 · 측정결과·배출량·AERMOD 예측 표 비움(모델링 출력 인풋 — 할 일 3 · 소환 0722 rule) · 기준표·저감 서술 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("사업지구와의 이격거리", 1, 2), ("환경기준", 2, 3), ("배출계수", 1, 3), ("예측농도", 2, 4),
         # ⚠️ 09-07 실측 — `기준치 만족 여부` 는 띄어쓰기가 없고 머리행이 2행이다.
         #    `측정소` 는 머리행 1행 표라 2 로는 데이터 행을 지나쳤다. TM 좌표 표는 누락돼 있었다.
         ("기준치 만족여부", 2, 6), ("TM 좌표", 2, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['초과지역_서술', '측정결과_서술', '측정망_서술', '주변사업_서술', '측정지점_서술', '저감후_서술', '예측초과_서술', '토공량_서술', 'A1_주소', 'A2_주소', 'A3_주소', '사업명', '시군']

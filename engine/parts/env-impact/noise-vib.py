#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `noise-vib` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 소음진동 — 측정(지점 3·일시·결과)·예측(합성소음·초과·진동·발파·도로) 서술 20토큰 · 측정결과 표·장비 소음도·이격거리별 예측·장약량 표는 비움(소환 0727 계산기 이식 자리 — 골든 7건 검증된 그 사슬) · 법령 기준표(155~351)는 판 고정. BLANK 앵커는 Windows 실측 전 추정.

B 단계: 소환 0727 계산기(합성소음·거리감쇠 — 골든 7건 검증) 이식 + 발파(폭풍압 예측식) 인풋 규약.
"""
from hwp_util import MISSING, blank_tables

BLANK = [("주간평균", 2, 2), ("소음도(dB(A))", 1, 4), ("진동레벨", 1, 3), ("장약량", 2, 2), ("목표소음기준", 2, 2), ("이격거리", 2, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['발파_서술2', '진동예측_서술', '발파_서술1', '도로소음_서술', '진동영향_서술', '소음예측_서술', '조사지점_서술', '진동결과_서술', '소음결과_서술', '소음초과_서술', '정온시설_서술', 'NV1_주소', 'NV2_주소', 'NV3_주소', '조사일시_1차', '조사일시_2차', '사업명', 'NV1_지역', 'NV_일반지역']

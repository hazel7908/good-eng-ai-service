#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `greenhouse-gas` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 온실가스 — 사업 고유 서술 자동 수확 + 사업명·시군 · 배출량 산정 표는 비움(**계산 파트** — 배출계수×활동량, 활동량 인풋 규약은 B 단계) · 인벤토리·계수 표 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("총배출량", 1, 2), ("tCO2eq", 1, 6), ("배출계수", 1, 4), ("흡수량", 1, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['사업명_축약', '온실주석_1', '온실주석_2', '온실주석_3', '온실주석_4', '사업명_구칭', '온실1349_서술', '온실2508_서술', '온실2493_서술', '사업명', '시군']

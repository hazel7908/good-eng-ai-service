#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `water-total-load` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 총량검토서 — 1장 개요 값 8 + 산정 결과 서술 6 = 14토큰 · 생활계/토지계 부하량 사슬 표(오수·발생·배출·원단위·삭감) 전부 비움(계산 인풋 — 소환 0840 compute 확장은 B) · 기술지침 인용 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("오수발생량", 2, 8), ("발생부하량", 2, 8), ("배출부하량", 2, 6), ("원단위", 2, 6), ("건축계획", 1, 1), ("토지이용면적", 2, 4)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['배경_서술', '발생부하_전서술', '발생부하_후서술', '숙박오수_서술', '경위_24', '경위_21', '경위_20', '경위_18', '경위_23', '총량실시_서술', '경위_11', '재협의_서술', '경위_2', '경위_16', '경위_5', '경위_8', '경위_3', '경위_10', '경위_12', '경위_14', '경위_17', '경위_4', '경위_7', '경위_15', '경위_19', '경위_1', '경위_22', '경위_6', '경위_25', '위치', '경위_9', '경위_13', '주소_구표기', '사업기간', '사업명_공백', '사업명', '읍면리', '시행자', '사업비', '허가권자', '단위유역']

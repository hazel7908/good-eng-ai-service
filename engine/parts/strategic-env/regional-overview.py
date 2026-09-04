#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `regional-overview` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 지역개황(소환 2장) — 정형 서술 수확 + 하천명 · 종합표·통계 표 비움(B: build_vars_regional 이식). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("구성비", 2, 4), ("해당유무", 1, 2), ("배출시설", 2, 2), ("포장", 2, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['계획명', '시군', '서술_43', '서술_44', '읍면', '서술_101', '서술_181', '서술_183', '서술_185', '서술_187', '서술_189', '서술_228', '서술_269', '서술_271', '서술_286', '서술_308', '서술_310', '서술_318', '서술_357', '서술_371', '서술_373', '서술_377', '서술_439', '서술_473', '서술_515', '서술_550', '서술_597', '서술_617', '서술_667', '서술_691', '서술_729', '하천2_명', '하천1_명', '서술_927']

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `water-quality` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 수질 — 수계·측정·저질 서술 수확 + 하천명 · 측정 표 비움 · 수리수문은 별도 파트. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("BOD", 2, 5),
         ("저질", 2, 2),   # 측정지점 표(99칸) 포함 — 표 안 토큰 40개는 전역 지명 치환의 부수
                           #   효과라 비워도 expect 무손실(전 토큰 표 밖 출현 실측 09-08 ✓).
                           #   비토큰 잔존(고명리 514 ×3·위치변경 이력 칸)이 사업 고유라 비움이 정답
         ("유로연장", 1, 2), ("청 정", 1, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['계획명', '하천2_명', '하천1_명', '읍면', '시군', '서술_116', '서술_118', '서술_120', '서술_153', '서술_214', '서술_612', '서술_628', '서술_632', '서술_817', '서술_1050', '서술_1196', '서술_1311', '서술_1666']

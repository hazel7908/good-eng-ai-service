#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `water-quality` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 수질 — 수계·측정·저질 서술 수확 + 하천명 · 측정 표 비움 · 수리수문은 별도 파트. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("BOD", 2, 5),
         ("저질", 2, 2),   # 측정지점 표(99칸) 포함 — 표 안 토큰 40개는 전역 지명 치환의 부수
                           #   효과라 비워도 expect 무손실(전 토큰 표 밖 출현 실측 09-08 ✓).
                           #   비토큰 잔존(고명리 514 ×3·위치변경 이력 칸)이 사업 고유라 비움이 정답
         ("유로연장", 1, 2), ("청 정", 1, 1),
         # ⚠️ 09-08 anchor_propose — 미처리 18표 중 사업 고유 12개.
         #    🚨 고정: 하천생활환경기준(법령) · 토지이용도별 기초유출계수 표준값 ·
         #    유입시간의 표준값 — 전국 상수다.
         ("돼지", 1, 1), ("공급정수장", 1, 1), ("급수지역", 1, 1),
         ("제방보강 필요구간", 1, 1), ("구조물명칭", 1, 1), ("(EL.m)", 1, 1),
         ("예측지점좌표", 1, 1), ("공종별", 2, 2), ("강우강도식", 1, 1),
         ("Parameter", 1, 1), ("지속시간(분)", 1, 1), ("(mm/hr)", 1, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['계획명', '하천2_명', '하천1_명', '읍면', '시군', '서술_116', '서술_118', '서술_120', '서술_153', '서술_214', '서술_612', '서술_628', '서술_632', '서술_817', '서술_1050', '서술_1196', '서술_1311', '서술_1666']

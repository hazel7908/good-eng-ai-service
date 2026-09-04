#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `water-quality` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 수질(수리·수문 대확장 12,463줄) — 사업 고유 서술 자동 수확(지명·수계 낀 결과 문장 ≤22) · 측정·부하·우수유출·저류지·관개 표 비움(calc_water 확장은 B — 소환 0723 rule) · 이론·기준표 반고정. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("유로연장", 2, 3), ("하천연장", 2, 2), ("수질측정", 2, 4), ("BOD", 2, 8), ("먹는물", 2, 3), ("토사유출량", 2, 4), ("유출계수", 2, 4), ("강우강도", 2, 3), ("관개용수", 2, 2)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['수질149_서술', '수질11897_서술', '수질9455_서술', '수질379_서술', '수질75_서술', '수질11410_서술', '수질113_서술', '수질133_서술', '수질8522_서술', '수질20_서술', '수질147_서술', '사업명', '읍면리', '시군']

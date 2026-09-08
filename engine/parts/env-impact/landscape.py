#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `landscape` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 위락·경관 — 현황·조망·시뮬·저감 서술 9토큰 · 문화유산·공원 표와 조망점 총괄·분석 표는 비움(현장 인풋 — 소환 0728 부류) · 자연경관 심의 근거(139~235)는 법령 반고정 · 조경계획(670~)은 골프장 반고정 서술. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("문화유산", 2, 2), ("조망점 위치", 2, 2), ("예비조망점 선정", 1, 8),  # ⚠️ 09-08 anchor_check — 옛 앵커는 표 밖(캡션)이거나 문단 경계로 쪼개져 영원히 못 찾았다
         
         # ⚠️ 09-08 — 공원·체육시설 현황(시군 통계). 조명운영계획은 표준 문안이라 뺐다.
         ("도시자연공원", 2, 1), ("게이트", 2, 1),
         # ⚠️ 09-08 anchor_suggest — 조명운영계획(사업 고유 조명 계획)
         ("운영 계획", 1, 1)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['인접위치_서술', '청사거리_서술', '수계현황_서술', '경관하천_검토', '위락저감_서술', '시뮬_서술', '위락영향_서술', '공원_서술', '수계_서술', '조망점선정_서술', '농촌경관_서술', '스카이라인_서술', '이식입목_주수', '사업명', '시군']

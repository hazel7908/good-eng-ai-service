#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0600 입지의 타당성 파트 핸들러 — W3 (2026-09-03 Mac). 소환 최경량(표 편집 0).

규약: build_slots / build_tables. 지식: rules/small-env/site-suitability.md.
**자체 값이 없다** — 근거 불릿 전부 다른 파트 vars 의 승계(`승계` 노드). 판정 열(◦ 미해당 등)은
기준 패턴 유지 — 뒤집기는 실무자(`_확인필요` 1건). 표 6.1-2 는 태양광 전용(rule §5).
"""
from hwp_util import MISSING


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s = v.get("승계", {})
    out = {k: g(s, k) for k in (
        "식생보전등급", "생태자연도", "철새도래지", "철새도래지_이격", "평균경사도", "지형변화지수",
        "토공량", "면적", "지목", "단위유역", "배출허용기준_지역", "소음환경기준_지역", "생활진동_지역",
        "수질_하천구분", "수질_등급")}
    out["사업명"] = g(v.get("사업", {}), "사업명")      # 머리글 전용
    return out


def build_tables(hwp, v):
    print("  0600 — 표 편집 없음 (검토결과 열은 빈칸 치환으로 채워진다 · 판정은 기준 패턴 유지)")

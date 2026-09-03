#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0800 부록 파트 핸들러 — W3 (2026-09-03 Mac). 표 편집 0 (참여자 명단은 회사 상시 인력 고정).

규약: build_slots / build_tables. 지식: rules/small-env/appendix.md. 전부 승계(`승계` 노드) —
문헌목록은 0711 과 같은 조립(「」 + ", "). AERMOD 출력 전문은 `[모델링 필요]` 부류(할 일 3).
"""
from hwp_util import MISSING, MODELING


def 문헌목록(items):
    return ", ".join(f"「{x}」" for x in items) if items else None


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s = v.get("승계", {})
    out = {k: g(s, k) for k in (
        "통계연보연도", "시군", "도엽명", "도엽번호", "기상_기간", "관측소", "도폭",
        "측정지점_대기", "측정지점_수질", "측정지점_소음")}
    out["문헌목록"] = 문헌목록(s.get("문헌목록")) or MISSING
    out["AERMOD_SURFDATA"] = s.get("AERMOD_SURFDATA") or MODELING
    out["사업명"] = g(v.get("사업", {}), "사업명")
    return out


def build_tables(hwp, v):
    print("  0800 — 표 편집 없음 (참여자 명단·업자·용어해설 고정)")

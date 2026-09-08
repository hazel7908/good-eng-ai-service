#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토서 5장 부록 핸들러 — C 베이스 (2026-09-08 Mac). 표 편집 없음 — 계약·인적사항 셀은 spec 토큰.

지식: rules/disaster-review/_category.md §37 (부록 = 인용문헌 반고정, 별도 rule 없음).
⚠️ 총괄자 성명·주민번호·자격·인증번호는 spec 이 못 뚫었다(명단 표와 중복 문자열 — spec ⚠️
   참조). Windows cells 실측 확정 전까지 그 4자리는 기준 사업(원주 태장동) 값이 남는다 —
   되먹임에서는 정상, 다른 사업 생성 때는 base 잔존으로 검사에 걸리는 것이 맞다(의도된 빨강)."""
from hwp_util import MISSING


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    c = v.get("대행비용", {})
    return {"총괄자_연락처": g(v.get("총괄자", {}), "연락처"),
            "면적": g(c, "면적"), "표준품셈": g(c, "표준품셈"), "계약금액": g(c, "계약금액"),
            "비율": g(c, "비율"), "계약_비고": g(c, "비고"), "설계업체": g(v, "설계업체")}


def build_tables(hwp, v):
    print("  검토서 5장 부록 — 표 편집 없음 (명단 상시·문헌은 law_update 훅 몫)")

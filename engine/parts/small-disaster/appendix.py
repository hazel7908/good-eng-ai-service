#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 8장 부록 핸들러 (C, 2026-09-03). 표 편집 없음 — 인적사항·비용 셀은 spec 토큰."""
from hwp_util import MISSING


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    p, c = v.get("총괄자", {}), v.get("대행비용", {})
    return {"총괄자_성명": g(p, "성명"), "총괄자_주민번호": g(p, "주민번호"), "총괄자_자격": g(p, "자격"),
            "총괄자_연락처": g(p, "연락처"), "면적": g(c, "면적"), "표준품셈": g(c, "표준품셈"),
            "계약금액": g(c, "계약금액"), "비율": g(c, "비율"), "협력업체": g(v, "협력업체")}


def build_tables(hwp, v):
    print("  8장 부록 — 표 편집 없음")

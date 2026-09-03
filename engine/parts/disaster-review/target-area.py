#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토서 2장 핸들러 — 검토서 첫 핸들러 (C, 2026-09-03). 지식: rules/disaster-review/target-area.md.
설정/미설정 판정 열은 사업 판단 — 기준(원주) 패턴 유지 + [실무자 확인] (소재평 2장 ●/X 와 같은 방침)."""
from hwp_util import MISSING


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, 사유 = v.get("서술", {}), v.get("사유", {})
    return {"설정서술_입지": g(s, "입지"), "설정서술_계획": g(s, "계획"),
            **{f"사유_{k}": g(사유, k) for k in ("하천","내수1","내수2","내수3","내수4","토사","사면","바람","해안")}}


def build_tables(hwp, v):
    print("  검토서 2장 — 설정/미설정 열은 기준 패턴 유지 ([실무자 확인])")

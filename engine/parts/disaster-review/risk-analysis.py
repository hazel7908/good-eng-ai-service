#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토서 4장 위험요인 분석 핸들러 — C 베이스 (2026-09-03 Mac). 지식: rules/disaster-review/risk-analysis.md.

표 1: 방재시설 관리상태(구분·현황·관리상태·작동상태, n행 — 앵커 `작동상태` 머리) — 자료 없으면 비움.
3장 값 승계(하천명·위험지구 유무)는 vars 빌더에서 — 여기서는 받은 값을 그대로 쓴다.
"""
from hwp_util import MISSING, fit_rows, write_at


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, n, t, p = v.get("사업", {}), v.get("서술", {}), v.get("총괄", {}), v.get("방재성능", {})
    out = {"시군": g(s, "시군")}
    out.update({k: g(n, k) for k in ("지반조사_서술", "바람재해_서술", "해안재해_서술", "반영제안_도입", "반영제안_1", "반영제안_2")})
    out.update({k: g(t, k) for k in ("총괄_하천_지구", "총괄_해안", "중점_내수_사유", "중점_사면_사유")})
    out.update({f"방재성능_{k}": g(p, k) for k in ("1h", "2h", "3h")})
    return out


def build_tables(hwp, v):
    rows = v.get("방재시설_관리상태") or [[None, None, None]]     # [구분(현황), 관리상태, 작동상태]
    print(f"  방재시설 관리상태 표 — 앵커 `작동상태`(머리) · {len(rows)}행 3칸 ⚠️ 실측")
    fit_rows(hwp, "작동상태", 3, len(rows), start=1)
    for i, row in enumerate(rows):
        write_at(hwp, "작동상태", 1 + i, 0, list(row) + [None] * (3 - len(row)))

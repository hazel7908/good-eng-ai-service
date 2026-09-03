#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 5장 재해영향 저감대책 핸들러 — C 베이스 (2026-09-03 Mac). **계산 재현 금지** (rule §②).

규약: build_slots / build_tables. 지식: rules/small-disaster/mitigation.md.
build_tables 는 계산 표를 비운다 — 입경 매트릭스(유역별)·퇴사량·방류관·홍수추적·침투통 검토·배수시설 능력.
이론 표(침강속도·NCHRP 절차·사방댐 구분·공법 분류)는 반고정 — 손대지 않는다.
시설 개소수는 **7장 총괄표·6장 대장과 같은 원천**(rule §⑥) — vars `시설` 노드가 단일 원천.
"""
from hwp_util import MISSING, blank_table_here, find_in_table

RESULT_TABLES = [
    ("침강속도", 2, 3),          # 입경 매트릭스 (A·B·…)
    ("Pond명", 2, 1),            # 개발 중 퇴사량·침전부 용량
    ("개 발 전", 2, 3),          # 홍수추적 결과 (유역별)
    ("총 침투 능력", 2, 1),      # 침투통 저감능력 검토
    ("증/감홍수량", 2, 1),       # (같은 표 — 앵커 대체)
]


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, f, c = v.get("사업", {}), v.get("시설", {}), v.get("침사지", {})
    out = {"시군": g(s, "시군"), "계획고_서술": g(s, "계획고_서술"),
           "침사지_계획서술": g(c, "계획서술"), "침사지_바닥면적": g(c, "바닥면적"),
           "침사지_개소": g(f, "침사지_개소"), "침투통_개소": g(f, "침투통_개소"), "침투통_서술": g(f, "침투통_서술"),
           "유출증가_유역": g(f, "유출증가_유역")}
    for y in ("A", "B"):
        d = c.get(y, {})
        out.update({f"{y}_{k}": g(d, k) for k in ("유량", "배수면적", "토사유출량", "포착율", "포착량")})
    return out


def build_tables(hwp, v):
    for anchor, hdr, limit in RESULT_TABLES:
        k = 0
        while k < limit and find_in_table(hwp, anchor, skip=k):
            n = blank_table_here(hwp, header_rows=hdr)
            print(f"  비움 `{anchor}` #{k + 1} — {n}셀")
            k += 1
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 표 비우기 스킵")

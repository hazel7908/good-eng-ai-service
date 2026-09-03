#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0725 지형·지질 파트 핸들러 — W3 (2026-09-03 Mac).

규약: build_slots / build_tables. 지식: rules/small-env/topo-geology.md.
표 5종(표고·경사 / 동굴 / 비탈면 계획 / 토공계획 / 비탈면 보호) — 앵커·오프셋은 **Windows 셀 주소
실측 전 추정**이다 (`KeyIndicator`·HWPX cellAddr 로 확정할 것). 규약: 행마다 앵커에서 절대 오프셋.
⚠️ 동굴 표는 spec 의 `원주시`→`{{시군}}` 일괄 치환에 소재지 셀이 걸린다 → **항상 다시 쓴다**.
⚠️ 지형변화지표는 계산하지 않는다 (rule §3 — 골든 토공량 4,952 ≠ 절+성 10,061).
"""
from hwp_util import MISSING, fit_rows, write_at


def _n(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def compute(v):
    """토공 총량 = 절토 + 성토 · 발생 토량 검산(성토 − 절토) · 표고/경사 구성비 보완."""
    r = {}
    t = (v.get("영향") or {}).get("토공") or {}
    a, b = _n(t.get("절토")), _n(t.get("성토"))
    r["토공_총량"] = f"{a + b:,.0f}" if a is not None and b is not None else None
    r["토공_발생"] = t.get("발생") or (f"{b - a:,.0f}" if a is not None and b is not None else None)
    for key in ("표고", "경사"):
        rows = ((v.get("현황") or {}).get(key) or {}).get("표") or []
        tot = sum(_n(x[1]) or 0 for x in rows)
        r[key + "_표"] = [[x[0], x[1], (x[2] if len(x) > 2 and x[2] not in (None, "")
                                         else (f"{_n(x[1]) / tot * 100:.2f}" if tot and _n(x[1]) is not None else None))]
                          for x in rows]
        r[key + "_합"] = f"{tot:,.1f}" if rows else None
    return r


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, h = v.get("사업", {}), v.get("현황", {})
    pg, gs = h.get("표고", {}), h.get("경사", {})
    jl, ti = h.get("지질", {}), v.get("특이지형", {})
    return {
        "사업명": g(s, "사업명"), "시군": g(s, "시군"), "시군은": g(s, "시군은"), "읍면": g(s, "읍면"),
        "읍면리": g(s, "읍면리"), "위치_지번": g(s, "위치_지번"),
        "조사시기": g(h, "조사시기"), "시군_지형서술": g(h, "시군_지형서술"),
        "지목구성": g(h, "지목구성"), "지형특성": g(h, "지형특성"),
        "표고_최저": g(pg, "최저"), "표고_최고": g(pg, "최고"), "표고차": g(pg, "차"), "평균표고": g(pg, "평균"),
        "경사_최저": g(gs, "최저"), "경사_최고": g(gs, "최고"), "평균경사도": g(gs, "평균"),
        "도폭": g(jl, "도폭"), "지질시대": g(jl, "시대"), "지질기호": g(jl, "기호"), "암석": g(jl, "암석"),
        "동굴_서술": g(ti, "동굴_서술"), "백두대간_서술": g(ti, "백두대간_서술"),
    }


def build_tables(hwp, v):
    r = compute(v)
    W = lambda *a, **k: write_at(hwp, *a, **k)
    ti, ef = v.get("특이지형", {}), v.get("영향", {})

    print("  표고·경사 표 — 앵커 `면 적(㎡)`(B2, 첫 출현) · 데이터 1~6행 · 열 A~G (표고 3 | 경사 3 | 비고)")
    pg, gs = r["표고_표"], r["경사_표"]
    n = max(len(pg), len(gs), 1)
    fit_rows(hwp, "면 적(㎡)", 6, n, start=1)
    for i in range(n):
        a = pg[i] if i < len(pg) else ["-", "-", "-"]
        b = gs[i] if i < len(gs) else ["-", "-", "-"]
        W("면 적(㎡)", 1 + i, 0, list(a) + list(b) + ["-"])
    W("면 적(㎡)", 1 + n, 0, ["합 계", r["표고_합"], "100.00", "합 계", r["경사_합"], "100.00", "-"])   # 계산 필드 자리

    print("  동굴 표 — 앵커 `소재지`(머리) · 항상 다시 쓴다 (소재지 셀이 시군 치환에 걸린다)")
    rows = ti.get("동굴표") or [[None] * 5]
    fit_rows(hwp, "소재지", 1, len(rows), start=1)
    for i, row in enumerate(rows):
        W("소재지", 1 + i, 0, list(row) + [None] * (5 - len(row)))

    print("  비탈면 계획 표 — 라벨 열 앵커 4 + 지형변화지표 (from_anchor)")
    bt = ef.get("비탈면") or {}
    for label in ("최대절토사면고", "최대성토사면고", "최대절토고", "최대성토고"):
        vals = bt.get(label) or [None, None, None]
        W(label, 0, 1, vals, from_anchor=True)
    W("지형변화지표(㎥/㎡)", 0, 1, ef.get("지형변화지표") or [None, None], from_anchor=True)

    print("  토공계획표 — 앵커 `발생 토량(㎥)`(머리) · 1행 · 총량은 계산 필드 자리라 값으로")
    t = ef.get("토공") or {}
    W("발생 토량(㎥)", 1, 1, [t.get("절토"), t.get("성토"), r["토공_총량"], r["토공_발생"], "-"])

    print("  비탈면 보호 표 — 앵커 `계획법면`(A 병합 라벨) · 2행 · row_after 로 병합 벗어남")
    bh = ef.get("보호") or [[None] * 4, [None] * 4]
    fit_rows(hwp, "계획법면", 2, len(bh), start=0)
    for i, row in enumerate(bh):
        W("계획법면", 0, 1, list(row) + [""] * (5 - len(row)), from_anchor=True, row_after=i)

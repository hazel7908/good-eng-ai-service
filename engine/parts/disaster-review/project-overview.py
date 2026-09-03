#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토서 1장 계획의 개요 핸들러 — C 베이스 (2026-09-03 Mac). 지식: rules/disaster-review/project-overview.md.

표: 결정 조서 블록(~15표) **비움**(행정계획 문서 인풋) · 지목별/소유별 토지이용현황(전치 표 — 행 라벨 앵커) 채움 ·
토지이용계획(안) 비움(골든이 남의 값). 앵커·오프셋은 Windows 실측 전 추정.
"""
from hwp_util import MISSING, blank_table_here, find_in_table, write_at


def _n(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def compute(v):
    """지목별·소유별 표: 필지수 합·면적 합·구성비 (계산 필드 자리)."""
    r = {}
    for key in ("지목별", "소유별"):
        rows = (v.get("토지이용") or {}).get(key) or []       # [[구분, 필지수, 면적], ...]
        np_, na = sum(int(_n(x[1]) or 0) for x in rows), sum(_n(x[2]) or 0 for x in rows)
        r[key] = {"필지": [str(np_)] + [x[1] for x in rows], "면적": [f"{na:,.0f}"] + [f"{_n(x[2]):,.0f}" if _n(x[2]) is not None else None for x in rows],
                  "구성비": ["100.00"] + [f"{_n(x[2]) / na * 100:.2f}" if na and _n(x[2]) is not None else None for x in rows]}
    return r


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, n = v.get("계획", {}), v.get("서술", {})
    out = {k: g(s, k) for k in ("계획명", "위치", "조서_위치1", "조서_위치2", "시행자", "사업기간", "시군", "도시관리계획명")}
    out["면적"] = f"{_n(s.get('면적_㎡')):,.0f}" if _n(s.get("면적_㎡")) is not None else MISSING
    out.update({k: g(n, k) for k in ("배경_서술", "목적_서술", "실시근거_서술")})
    gw = v.get("경위") or []
    out.update({f"경위_{i}": (gw[i - 1] if i <= len(gw) else MISSING) for i in range(1, 17)})
    lb = v.get("위치도_라벨") or []
    out.update({f"위치도_라벨{i}": (lb[i - 1] if i <= len(lb) else MISSING) for i in range(1, 4)})
    return out


def _blank_all(hwp, anchor, header_rows, limit, skip=0):
    k = 0
    while k < limit and find_in_table(hwp, anchor, skip=skip + k):
        blank_table_here(hwp, header_rows=header_rows); k += 1
    print(f"  비움 `{anchor}` ×{k}" if k else f"    WARNING: 앵커 '{anchor}' 못 찾음")


def build_tables(hwp, v):
    r = compute(v)
    W = lambda *a, **k: write_at(hwp, *a, **k)
    print("  결정 조서 블록 — 도면표시/사유서/도로/용도지역/가구획지 표 비움 (행정계획 문서 인풋)")
    _blank_all(hwp, "도면표시", 3, 12)
    _blank_all(hwp, "변경전 도로명", 1, 1)
    # 🔬 실측: `용도지역 결정(대상지) : 변경없음` 은 **표가 아니라 문단**이다 —
    #    앵커로 쓸 수 없다. 그 아래 표(`구 분|면 적(㎡)|구성비(%)|비 고`)를 잡으려면
    #    표 안 머리가 필요한데 `구성비` 는 이 문서에 표 5곳에 있다 (표5·16·29·31·33).
    #    🚧 어느 것이 용도지역 결정조서인지 미확정 — 다음 배치에서 skip 실측.
    #    (지금은 비우지 못한다 = 다른 사업에 원주 값이 나간다.)
    print("  지목별·소유별 토지이용현황 — 전치 표, 행 라벨 앵커(필 지 수·면  적(㎡)·구성비(%)) skip 0/1 ⚠️ 실측")
    for k, key in enumerate(("지목별", "소유별")):
        d = r[key]
        W("필 지 수", 0, 1, d["필지"], from_anchor=True, skip=k)
        W("면  적(㎡)", 0, 1, d["면적"], from_anchor=True, skip=k)
        W("구성비(%)", 0, 1, d["구성비"], from_anchor=True, skip=k)
    print("  토지이용계획(안) — 비움 (골든 값이 남의 사업 잔재)")
    # 🔬 실측: `합계` 는 런이 갈려 한글 찾기에 안 걸린다(추출 텍스트엔 1회 있다).
    #    토지이용계획(안) 표는 `구성비` 를 가진 다섯 표 중 **마지막**이다 (표33).
    _blank_all(hwp, "구성비", 1, 1, skip=4)

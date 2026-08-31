#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0400 사업지역·주변지역 토지이용 파트 핸들러 — W1 (2026-08-31). 소환 최경량.

규약: build_slots / build_tables. 지식: rules/small-env/surrounding-land-use.md.
조서 = 0100 vars 공유, 시군 표 = 지역개황 원천, 사업지구 표 = 조서에서 유도.
⚠️ build_tables Windows 미검증.
"""
from collections import OrderedDict

from hwp_util import (MISSING, col_begin, down, find_in_table, fit_rows,
                      right, set_cell, write_at)


def compute(v):
    """조서 행 → 사업지구 지목별 합산 + 구성비 (rule ③, 원주 99.45 역산 ✓)."""
    js = (v.get("조서") or {}).get("행") or []
    by = OrderedDict()
    for row in js:
        # 행 꼴: [읍면, 리, 지번, 지목, 지적면적, 사업부지, 진출입로, 소계, 비고] — 유연 인덱싱
        try:
            jimok, sogye = row[-6], row[-2]
            by[jimok] = by.get(jimok, 0) + (float(str(sogye).replace(",", "")) or 0)
        except (ValueError, TypeError, IndexError):
            continue
    total = sum(by.values())
    # 표 지목 열은 면적 내림차순이다 (원주 답 99.45 > 전 0.38 > 임 0.17 = 골든 머리 순).
    # 조서 등장 순으로 쓰면 값이 다른 지목 열에 박힌다.
    by = OrderedDict(sorted(by.items(), key=lambda kv: -kv[1]))
    r = {"지목합": by, "면적합": total}
    r["지목비율"] = {k: f"{a / total * 100:.2f}" for k, a in by.items()} if total else {}
    uses = v.get("지구용도") or []          # [{"구분": "보전관리지역", "면적": 23}]
    ut = sum(x.get("면적") or 0 for x in uses)
    r["용도비율"] = [{**x, "비율": (f"{(x.get('면적') or 0) / ut * 100:.2f}" if ut else None)}
                    for x in uses]
    r["용도합"] = ut
    return r


def build_slots(v):
    n = v.get("서술", {})
    tj = v.get("통계", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        # ⚠️ 머리글 전용. spec 에만 뚫고 여기서 값을 안 주면 빈칸이 그대로 남는다.
        "사업명": g(v.get("사업", {}), "사업명"),
        "위치용도_서술": g(n, "위치용도"),
        "지목구성_서술": g(n, "지목구성"),
        "시군지목_서술": g(n, "시군지목"),      # 지역개황 2.2 값에서 생성 (D2 일반화 대상)
        "읍면지목_서술": g(n, "읍면지목"),
        "지구지목_서술": g(n, "지구지목"),
        "시군용도_서술": g(n, "시군용도"),
        "지구용도_서술": g(n, "지구용도"),
        "개발사업_서술": g(n, "개발사업"),      # 없음/있음 분기 (rule ④)
        "통계연보연도": g(tj, "통계연보연도"),
        "시군": g(v.get("사업", {}), "시군"),
    }


def joseo_total(rows):
    """편입토지조서 합계 행 4칸 — 지적면적·사업부지·진출입로·소계 합.

    ⚠️ 합계 행은 `=SUM` **계산 필드**다. 데이터 행만 채우고 두면 참조가 깨지거나
    기준 사업 값이 캐시된 채 남는다 (천안 0100 에 원주 `203,155`·`13,858`·`13,934` 가
    그대로 있었다 — 2026-08-31 실측). **엔진이 값으로 직접 쓴다.**
    행 꼴: [지번, 지목, 지적면적, 사업부지, 진출입로, 소계, 비고]
    """
    def num(x):
        try:
            return float(str(x).replace(",", ""))
        except (TypeError, ValueError):
            return None
    out = []
    for idx in (2, 3, 4, 5):
        vals = [num(r[idx]) for r in rows if len(r) > idx and num(r[idx]) is not None]
        out.append(f"{sum(vals):,.0f}" if vals else None)
    return out


def build_tables(hwp, v):
    """표 편집 5종. 앵커·오프셋·열 시작은 2026-08-31 셀 주소 실측 확정.

    구조(원주 실측): 편입토지조서 `지적면적`=D1 머리행, 데이터 2~8행, A=병합 라벨 →
    값은 B부터 7칸. 시군지목표 `면  적(㎢)`=B2, 4행(2~5), A=병합 → 라벨 B + 값 C~K 9칸.
    시군용도표 `비도시지역`=O1 머리행, 데이터 3~4행, 값 C~R 11칸(병합 열 건너뜀).
    """
    r = compute(v)
    cell = lambda x: set_cell(hwp, str(x) if x not in (None, "") else MISSING)
    W = lambda *a, **k: write_at(hwp, *a, **k)      # 공용 이동 규약 (hwp_util)

    # ⚠️ 자료가 없어도 **건너뛰지 않는다** — 건너뛰면 기준 사업(원주) 값이 그대로 실린다
    #    (rule §6-3 · 청양 골든셋). 행 수만큼 [확인 필요] 로 비운다.
    print("  편입토지조서 (0100 공유) — 값은 B열부터 7칸")
    js = (v.get("조서") or {}).get("행") or []
    BASE_JS = 7
    rows = js or [[None] * 7 for _ in range(BASE_JS)]
    if find_in_table(hwp, "지적면적"):
        fit_rows(hwp, "지적면적", BASE_JS, len(rows))
        for i, row in enumerate(rows):
            W("지적면적", 1 + i, 1, list(row)[-7:] if len(row) >= 7 else row)
        # 합계 행 — A(합계)는 A~C 병합이라 오른쪽 1칸이 곧 D열이다
        W("지적면적", 1 + len(rows), 1, joseo_total(js) + ["-"])

    print("  시군·읍면 지목 표 — 값은 C열부터 9칸")
    sj = (v.get("시군지목표") or {}).get("행") or []
    rows = sj or [[None] * 9 for _ in range(4)]
    for i, row in enumerate(rows[:4]):
        W("면  적(㎢)", i, 2, list(row)[-9:] if len(row) >= 9 else row)

    print("  시군 용도지역 표 — 값은 C열부터 11칸")
    sy = (v.get("시군용도표") or {}).get("행") or []
    rows = sy or [[None] * 11 for _ in range(2)]
    for i, row in enumerate(rows[:2]):
        W("비도시지역", 2 + i, 2, list(row)[-11:] if len(row) >= 11 else row)

    # ⚠️ 구성비 행도 라벨 칸(B=)을 건너뛴다 — col_off 를 1 로 두면
    #    라벨을 덮어써 표에서  가 사라진다 (2026-08-31 실측).
    print("  사업지구 지목 표 (조서 유도)")
    jm = r["지목합"]
    if jm:
        W("사업계획지구", 0, 2, [f"{r['면적합']:,.0f}"] + [f"{a:,.0f}" for a in jm.values()])
        W("사업계획지구", 0, 2, ["100.00"] + list(r["지목비율"].values()), row_after=1)
    else:
        W("사업계획지구", 0, 2, [None] * 4)
        W("사업계획지구", 0, 2, [None] * 4, row_after=1)

    print("  사업지구 용도 표")
    uz = r["용도비율"]
    if uz:
        W("보전관리지역", 1, 2,
          [f"{r['용도합']:,.0f}"] + [f"{x.get('면적'):,.0f}" if x.get("면적") else MISSING
                                    for x in uz])
        W("보전관리지역", 2, 2, ["100.00"] + [x.get("비율") for x in uz])
    else:
        W("보전관리지역", 1, 2, [None] * 3)
        W("보전관리지역", 2, 2, [None] * 3)

    print("  0400 표 편집 종료")

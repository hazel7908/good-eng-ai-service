#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0724 토지이용 파트 핸들러 — W1 (2026-08-31). = 0400 + 0100 재조합 (rule ⑦→§16).

규약: build_slots / build_tables. 지식: rules/small-env/land-use.md.
compute 는 0400(surrounding-land-use)의 것을 그대로 쓴다 — 세 파트 값 불일치 금지.
✅ build_tables Windows 실측 확정 (2026-09-01 원주 되먹임 **diff 0줄** — 표 7개
   원본 완전 재현). 이동은 공용 `hwp_util.write_at` 규약. 문서 내 표 순서(9개):
   현황조사내용 → 시군지목 → 지구지목 → 시군용도 → 지구용도 → 조서
   → 영향예측내용 → 토지이용계획 → 피해방지계획
"""
import importlib.util
import pathlib

from hwp_util import MISSING, find_in_table, fit_rows, write_at

_p = pathlib.Path(__file__).with_name("surrounding-land-use.py")
_s = importlib.util.spec_from_file_location("part_small_env_surrounding_land_use", _p)
_slu = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_slu)
compute = _slu.compute          # 조서 → 지목 합산·구성비 (원주 99.45 역산 ✓)


def build_slots(v):
    n = v.get("서술", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        "사업명": g(v.get("사업", {}), "사업명"),
        "시군": g(v.get("사업", {}), "시군"),
        "조사시기": g(v.get("현황", {}), "조사시기"),
        # 서술 6종 — 0400 과 같은 vars 원천이되 문장은 0724 원문 꼴 (rule ②)
        "시군지목_서술": g(n, "시군지목"),
        "읍면지목_서술": g(n, "읍면지목"),
        "지구지목_서술": g(n, "지구지목"),
        "시군용도_서술": g(n, "시군용도"),
        "지구용도_서술": g(n, "지구용도"),
        "내부현황_서술": g(n, "내부현황"),      # (3) 위치·지목·주변 시설 한 문장
        "통계연보연도": g(v.get("통계", {}), "통계연보연도"),
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
    """표 편집 7종. 구조는 0400 과 같다 — 셀 주소 실측(2026-08-31)으로 확정.

    A열이 세로 병합 라벨인 표가 많아 **열 오프셋을 명시**한다 (`write_at` 규약).
    ⚠️ 자료가 없어도 건너뛰지 않는다 — 건너뛰면 기준 사업 값이 그대로 실린다.
    """
    r = compute(v)
    W = lambda *a, **k: write_at(hwp, *a, **k)

    print("  시군 지목 표 — 값은 C열부터 9칸 (4행)")
    sj = (v.get("시군지목표") or {}).get("행") or []
    for i, row in enumerate((sj or [[None] * 9] * 4)[:4]):
        W("면  적(㎢)", i, 2, list(row)[-9:] if len(row) >= 9 else row)

    print("  시군 용도지역 표 — 값은 C열부터 11칸 (2행)")
    sy = (v.get("시군용도표") or {}).get("행") or []
    for i, row in enumerate((sy or [[None] * 11] * 2)[:2]):
        W("비도시지역", 2 + i, 2, list(row)[-11:] if len(row) >= 11 else row)

    print("  사업지구 지목 표 (조서 유도 — 면적 내림차순)")
    # ⚠️ `사업계획지구` 는 현황조사내용 표 조사범위 셀에 먼저 나온다 → skip=1
    # ⚠️ 그 칸은 두 행에 걸친 세로 병합이라 `down()` 이 안 먹는다 → row_after 로 우회
    jm = r["지목합"]
    if jm:
        W("사업계획지구", 0, 2, [f"{r['면적합']:,.0f}"] + [f"{a:,.0f}" for a in jm.values()], skip=1)
        W("사업계획지구", 0, 2, ["100.00"] + list(r["지목비율"].values()), skip=1, row_after=1)
    else:
        W("사업계획지구", 0, 2, [None] * 4, skip=1)
        W("사업계획지구", 0, 2, [None] * 4, skip=1, row_after=1)

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

    print("  편입토지조서 (0100·0400 공유) — 값은 B열부터 7칸")
    js = (v.get("조서") or {}).get("행") or []
    BASE_JS = 7
    rows = js or [[None] * 7 for _ in range(BASE_JS)]
    if find_in_table(hwp, "지적면적"):
        fit_rows(hwp, "지적면적", BASE_JS, len(rows))
        for i, row in enumerate(rows):
            W("지적면적", 1 + i, 1, list(row)[-7:] if len(row) >= 7 else row)
        W("지적면적", 1 + len(rows), 1, joseo_total(js) + ["-"])   # 합계 행 (=SUM 필드 덮기)

    print("  토지이용계획 (0100 공유 — 비율 유도)")
    tu = v.get("토지이용") or []
    BASE_TU = 4
    def _f2(x):
        try:
            return float(str(x).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0
    total = sum(_f2(x.get("면적")) for x in tu)
    if find_in_table(hwp, "비 율(%)"):
        rows = tu or [{}] * BASE_TU
        fit_rows(hwp, "비 율(%)", BASE_TU, len(rows))
        for i, x in enumerate(rows):
            a = _f2(x.get("면적")) if x.get("면적") is not None else None
            W("비 율(%)", 1 + i, 0,
              [x.get("구분"),
               (f"{a:,.2f}" if a is not None else None),
               (x.get("비율") or (f"{a / total * 100:.2f}" if a is not None and total else None)),
               "-"])
        # 합계 행 — 라벨(합    계) 다음 칸부터
        W("비 율(%)", 1 + len(rows), 1,
          [f"{total:,.2f}" if total else None, "100.00" if total else None, "-"])

    print("  피해방지계획 (0100 공유 — 설계 수량) — 규격~비고 4칸")
    # ⚠️ 셀 주소 실측(2026-08-31): 앵커 `수 량`=D1 머리행 · **데이터 9행**(8행 아님) ·
    #    `공 종`(A열)은 U형측구·집수정에서 **세로 병합**이라 행마다 쓰면 무너진다.
    #    `스틸그레이팅` 은 공종이 아니라 **비고(E4)** 다 — 평면 추출로는 공종처럼 보인다.
    #    → 규격·단위·수량·비고 4칸만 쓰고 공종 열은 건드리지 않는다.
    # 🚧 미해결: 공종 집합이 베이스와 다른 사업은 병합 구조를 다시 짜야 한다
    #    (지목 머리행 재기입과 같은 부류 — 지시서 ② '미확정' 항목).
    ph = (v.get("피해방지") or {}).get("행") or []
    BASE_PH = 9
    rows = ph or [[None] * 4 for _ in range(BASE_PH)]
    if find_in_table(hwp, "수 량"):
        fit_rows(hwp, "수 량", BASE_PH, len(rows))
        for i, row in enumerate(rows):
            W("수 량", 1 + i, 1, list(row)[-4:] if len(row) >= 4 else row)

    print("  0724 표 편집 종료")

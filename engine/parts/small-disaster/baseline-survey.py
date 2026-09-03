#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 3장 기초현황 조사 핸들러 — C 베이스 (2026-09-03 Mac).

규약: build_slots / build_tables. 지식: rules/small-disaster/baseline-survey.md.
표 9종 — 유역특성(유역×단계) · 하천 현황 · 관측소(셀 토큰 + 표고·개시일 2셀) · 연도별 기상(10행) · 토양 2 ·
재해발생현황(10년) · 시설물 · 탐문 2. 앵커·오프셋은 **Windows 실측 전 추정**.
자료 없는 표는 **비운다**(행 유지·`[확인 필요]`) — 건너뛰면 천안 값이 남는다.
값 승계: 유역특성은 4장 vars `유역` 과 같은 값(불일치 금지) · 기상은 kma.py(소환 0721 원천).
"""
from hwp_util import MISSING, blank_row, blank_table_here, find_in_table, fit_rows, write_at


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, y, h, t, d = v.get("사업", {}), v.get("요약", {}), v.get("현황", {}), v.get("토질", {}), v.get("재해", {})
    ob, w = h.get("관측소", {}), h.get("기상", {})
    out = {"시군": g(s, "시군"), "하천명": g(s, "하천명"), "위험지구명": g(s, "위험지구명"), "평가면적": g(s, "평가면적")}
    out.update({k: g(y, k) for k in ("방재시설_요약", "재해이력_요약", "지구지정_요약", "관련계획_요약")})
    out.update({k: g(h, k) for k in ("표고범위", "경사범위", "표고차", "하천자료_출처")})
    out.update({"관측소": g(ob, "이름"), "관측소_주소": g(ob, "주소"), "관측소_경도": g(ob, "경도"), "관측소_위도": g(ob, "위도"),
                "관측소_표고": g(ob, "표고"), "관측소_개시일": g(ob, "개시일")})
    out.update({k: g(w, k) for k in ("기상_기간", "평균기온", "평균강수량", "평균풍속", "평균습도")})
    out.update({k: g(t, k) for k in ("토양군", "표토", "배수등급", "지질구성")})
    sl = v.get("사면", {})
    out.update({f"급경사_{k}": g(sl, k) for k in ("이하비율", "이하면적", "초과비율", "초과면적")})
    out["산사태_서술"] = g(sl, "산사태_서술")
    out.update({k: g(d, k) for k in ("재해현황_서술", "탐문_서술1", "탐문_서술2", "탐문_장소", "탐문_일시", "탐문_피해년도", "탐문_피해원인")})
    tm = d.get("탐문") or [{}, {}]
    out["탐문1_연령"], out["탐문2_연령"] = g(tm[0] if tm else {}, "연령"), g(tm[1] if len(tm) > 1 else {}, "연령")
    p = v.get("관련계획", {})
    out.update({k: g(p, k) for k in ("하천기본계획_출처", "관련계획_서술", "계획홍수위_서술", "저감종합계획_연도",
                                    "저감종합계획_서술", "위험지구_서술")})
    return out


def _blank_all(hwp, anchor, header_rows, limit=6):
    """같은 머리를 가진 표를 전부 비운다 (자료 없음 = [확인 필요])."""
    k = 0
    while k < limit and find_in_table(hwp, anchor, skip=k):
        blank_table_here(hwp, header_rows=header_rows)
        k += 1
    if k == 0:
        print(f"    WARNING: 앵커 '{anchor}' 못 찾음")
    return k


def build_tables(hwp, v):
    W = lambda *a, **k: write_at(hwp, *a, **k)
    h, ob = v.get("현황", {}), v.get("현황", {}).get("관측소", {})

    print("  유역면적·유로연장 표 — 앵커 `유역평균경사`(머리) · 유역×단계 행 (4장 vars 승계) ⚠️ 실측")
    rows = h.get("유역특성") or []            # [유역, 단계, A, L, A/L, A/L², 경사]
    if rows:
        fit_rows(hwp, "유역평균경사", 6, len(rows), start=2)
        for i, row in enumerate(rows):
            W("유역평균경사", 2 + i, 0, list(row) + [None] * (7 - len(row)))
    else:
        for i in range(6):
            blank_row(hwp, "유역평균경사", 2 + i, keep_first=2)

    print("  하천 현황 표 — 앵커 `하 천 명` · 1행 (하천명 셀은 토큰)")
    r = h.get("하천") or {}
    W("하 천 명", 1, 1, [r.get("시점"), r.get("종점"), r.get("유로연장"), r.get("유역면적"), "-"])

    print("  관측소 표 — 앵커 `행  정  구  역`(부머리) · 관측소명 셀 1 (`천안`은 짧아 토큰 불가 · 나머지는 토큰) ⚠️ 실측")
    W("행  정  구  역", 1, 1, [ob.get("이름")])

    print("  연도별 기상 표 — 앵커 `평  균`(부머리) · 10행 × 6값 (kma.py 원천)")
    yrs = h.get("기상", {}).get("연도별") or []
    if yrs:
        fit_rows(hwp, "평  균", 10, len(yrs), start=1)
        for i, row in enumerate(yrs):
            W("평  균", 1 + i, 0, list(row) + [None] * (7 - len(row)))
    else:
        for i in range(10):
            blank_row(hwp, "평  균", 1 + i, keep_first=1)

    print("  토양분포현황 표 2 · 재해발생현황 표 · 시설물 표 — 자료 없으면 비움")
    _blank_all(hwp, "토양\n부호", 2) or _blank_all(hwp, "통명", 2)
    _blank_all(hwp, "이재민", 2)
    _blank_all(hwp, "B등급", 1)

    print("  주민탐문 결과표 2 — 앵커 `면담 일시`(머리) · 성명·거주년수 셀 (연령·장소·일시·피해년도·원인은 토큰)")
    for k, row in enumerate((v.get("재해", {}).get("탐문") or [{}, {}])[:2]):
        W("면담 일시", 1, 0, [row.get("성명")], skip=k)
        W("면담 일시", 1, 2, [row.get("거주년수")], skip=k)

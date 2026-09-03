#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토서 3장 기초현황 조사 핸들러 — C 베이스 (2026-09-03 Mac). 지식: rules/disaster-review/baseline-survey.md.

표: 관측소(관측소명 셀) · 연도별/월별 기상·월별강우 3(kma.py 원천 — 러프는 비움) · 재해발생현황 2(재해연보 I-2 — 비움) ·
지진 표(비움) · 위험지구 현황 3(내수/토사/사면 — **원주 지구명 유출 1순위**, fit_rows 또는 비움) · 방재시설 현황
(13행 × 대상지/주변 — vars) · 시설물 목록(비움). 앵커·머리행은 Windows 실측 전 추정.
"""
from hwp_util import MISSING, blank_table_here, delete_range, find_in_table, fit_rows, write_at

BLOCK_MARK = "[확인 필요] 이 절의 요약(풍수해저감종합계획·하천기본계획·상위계획 검토)은 시군 문서 인풋 — 기준 사업(원주) 본문은 걷어냈다"

BLANK = [("2011년", 2, 1), ("(호우발생", 3, 1), ("발생시각", 1, 1), ("시설물 구분", 1, 1), ("기     온", 2, 2), ("1월", 1, 3)]


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, ob, w, d, j = v.get("사업", {}), v.get("관측소", {}), v.get("기상", {}), v.get("재해", {}), v.get("지질", {})
    out = {k: g(s, k) for k in ("시군", "읍면동", "위치", "지역적범위_서술", "풍수해계획_연도")}
    out.update({"관측소": g(ob, "이름"), "관측소_주소": g(ob, "주소"), "관측소_위도": g(ob, "위도"), "관측소_경도": g(ob, "경도"), "관측소_개시일": g(ob, "개시일")})
    out.update({k: g(w, k) for k in ("기상_기간", "최다강수_시기", "최다강수_량")})
    out.update({"수계_서술1": g(v.get("수계", {}), "서술1"), "수계_서술2": g(v.get("수계", {}), "서술2")})
    out.update({"도폭": g(j, "도폭"), "도폭_연도": g(j, "도폭_연도")})
    out.update({k: g(d, k) for k in ("재해_기준연도", "재해_기간", "지진_시도_1", "지진_시도_2", "지진_시군_서술")})
    r = v.get("관련계획", {})
    out.update({k: g(r, k) for k in ("시도", "도종합계획_기간", "도시기본계획명", "하천기본계획_출처", "통계연보명")})
    out["관련계획_블록"] = r.get("블록") or BLOCK_MARK
    return out


def _blank_all(hwp, anchor, header_rows, limit):
    k = 0
    while k < limit and find_in_table(hwp, anchor, skip=k):
        blank_table_here(hwp, header_rows=header_rows); k += 1
    print(f"  비움 `{anchor}` ×{k}" if k else f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


def build_tables(hwp, v):
    W = lambda *a, **k: write_at(hwp, *a, **k)
    print("  관측소 표 — 앵커 `지    명`(부머리) · 관측소명 셀 1 ⚠️ 실측")
    W("지    명", 1, 0, [v.get("관측소", {}).get("이름")])
    print("  기상 3표 · 재해현황 2표 · 지진 표 · 시설물 목록 — 자료 없음 = 비움")
    for a, h, n in BLANK:
        _blank_all(hwp, a, h, n)
    print("  위험지구 현황 3표(내수/토사/사면) — 앵커 `지구명`(머리) skip 0/1/2 · n행 4칸 (원주 지구명 유출 1순위)")
    for k, key in enumerate(("내수", "토사", "사면")):
        rows = (v.get("위험지구") or {}).get(key) or []
        if rows:
            fit_rows(hwp, "지구명", 4, len(rows), start=1, skip=k)
            for i, row in enumerate(rows):
                W("지구명", 1 + i, 0, list(row) + [None] * (4 - len(row)), skip=k)
        elif find_in_table(hwp, "지구명", skip=k):
            blank_table_here(hwp, header_rows=1)
    print("  주민탐문 조사 표 3 — 앵커 `검토 의견` · 비움 (현장 인풋)")
    _blank_all(hwp, "검토 의견", 1, 3)
    print("  관련계획 조사 본문(≈2,200줄: 방재계획·하천기본계획 표·상위계획) — delete_range(`현황분석` → `기초현황 조사 결과`) ⚠️ 실측")
    if not (v.get("관련계획") or {}).get("본문유지"):
        delete_range(hwp, "현황분석", "기초현황 조사 결과")
    print("  방재시설 현황 표 — 앵커 `주 변 지 역`(머리) · 13행 × (대상지, 주변) ⚠️ 실측")
    cells = (v.get("방재시설") or {}).get("현황") or [[None, None]] * 13
    for i, row in enumerate(cells[:13]):
        W("주 변 지 역", 1 + i, 1, list(row)[:2])

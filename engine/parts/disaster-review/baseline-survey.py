#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토서 3장 기초현황 조사 핸들러 — C 베이스 (2026-09-03 Mac). 지식: rules/disaster-review/baseline-survey.md.

표: 관측소(관측소명 셀) · 연도별/월별 기상·월별강우 3(kma.py 원천 — 러프는 비움) · 재해발생현황 2(재해연보 I-2 — 비움) ·
지진 표(비움) · 위험지구 현황 3(내수/토사/사면 — **원주 지구명 유출 1순위**, fit_rows 또는 비움) · 방재시설 현황
(13행 × 대상지/주변 — vars) · 시설물 목록(비움). 앵커·머리행은 Windows 실측 전 추정.
"""
from hwp_util import (MISSING, blank_table_here, blank_tables, delete_range, find_in_table, fit_rows, write_at)

BLOCK_MARK = "[확인 필요] 이 절의 요약(풍수해저감종합계획·하천기본계획·상위계획 검토)은 시군 문서 인풋 — 기준 사업(원주) 본문은 걷어냈다"

# ⚠️ `기     온`(공백 낀 머리)은 한글 찾기가 못 찾았다(⑰) → `해면기압`(붙은 조각, 연도별·월별 두 표 공통 머리)
BLANK = [("2011년", 2, 1), ("(호우발생", 3, 1), ("발생시각", 1, 1), ("시설물 구분", 1, 1), ("해면기압", 2, 2), ("1월", 1, 3),
         # 09-09 옥계리 첫 생성 적발 — 손대지 않던 표 3부류 (되먹임은 못 본다):
         ("지정규모", 2, 1),        # 자연재해위험개선지구 현황 — 머리 2행(cellAddr 실측)
         ("취약지역유형", 1, 5)]    # 산사태 취약지역 지정내역 — '계속' 분할 5표.
                                    # ⚠️ 머리행에 값이 섞인 라벨-값 격자(`제2017-1호`·침수흔적 `2010년`)
                                    #    — header_rows=1 로는 그 한 칸이 남는다. 값 대조가 잡을 소량 잔존.


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
    z = v.get("지구지정", {})
    out.update({k: g(z, k) for k in ("급경사지_서술", "위험지구_하천_서술", "위험지구_토사_서술", "최근접위험지구_서술", "침수흔적_서술", "방재시설_요약")})
    out.update({"지반조사_사례": g(j, "지반조사_사례"), "지반조사_사례2": g(j, "지반조사_사례2"),
                "지반조사_사례3": g(j, "지반조사_사례3"), "시군약칭": g(s, "시군약칭")})
    out.update({k: g(z, k) for k in ("최근접_하천_서술", "최근접_내수_서술", "위험지구_내수_서술", "위험지구_사면_서술")})
    out.update({"조사결과_관련계획": g(z, "조사결과_관련계획"), "조사결과_배수": g(z, "조사결과_배수")})
    return out


def _blank_all(hwp, anchor, header_rows, limit):
    """공용 위임 — skip 을 앵커 생존 여부로 자동 결정."""
    k = blank_tables(hwp, anchor, header_rows, limit)
    print(f"  비움 `{anchor}` ×{k}" if k else f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")
    return k

def build_tables(hwp, v):
    W = lambda *a, **k: write_at(hwp, *a, **k)
    print("  관측소 표 — 앵커 `지    명`(부머리) · 관측소명 셀 1 ⚠️ 실측")
    W("지    명", 1, 0, [v.get("관측소", {}).get("이름")])
    print("  기상 3표 · 재해현황 2표 · 지진 표 · 시설물 목록 — 자료 없음 = 비움")
    for a, h, n in BLANK:
        _blank_all(hwp, a, h, n)
    # 🚨 `지구명` 머리 표가 **8개**다 (09-09 XML 실측 — 되먹임은 값이 자기 것이라 못 보던 자리):
    #    0·1 급경사지 현황(+계속) · 2 침수흔적 · 3 하천재해 목록 · **4 내수 · 5 토사 · 6 사면** · 7 (삭제범위 안)
    #    옛 skip 0/1/2 는 급경사지·침수흔적을 잡고 정작 위험지구 3표를 놔뒀다.
    print("  지구명 표 0~3(급경사지 2·침수흔적·하천재해 목록) — 시군 문서 인풋, 비움")
    _blank_all(hwp, "지구명", 1, 4)
    print("  위험지구 현황 3표(내수/토사/사면) — 앵커 `지구명` skip 4/5/6 · n행 4칸 (기준 사업 지구명 유출 1순위)")
    for k, key in ((4, "내수"), (5, "토사"), (6, "사면")):
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
    rows = v.get("방재시설_관리상태") or [[None, None, None]]
    print(f"  방재시설 관리상태 표(4장과 같은 표) — 앵커 `작동상태` · {len(rows)}행")
    fit_rows(hwp, "작동상태", 3, len(rows), start=1)
    for i, row in enumerate(rows):
        W("작동상태", 1 + i, 0, list(row) + [None] * (3 - len(row)))
    print("  방재시설 현황 표 — 앵커 `주 변 지 역`(머리) · 13행 × (대상지, 주변) ⚠️ 실측")
    cells = (v.get("방재시설") or {}).get("현황") or [[None, None]] * 13
    for i, row in enumerate(cells[:13]):
        W("주 변 지 역", 1 + i, 1, list(row)[:2])

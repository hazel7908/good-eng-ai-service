#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자원순환(0726) 파트 핸들러 — W1 (2026-08-31).

규약: build_slots(v) / build_tables(hwp, v). 지식: rules/small-env/resource-cycle.md ·
명세: templates/small-env/resource-cycle.slots.md · 계산: engine/calc_waste.py.
인부 계산은 수질 §3-6과 동일 갈림(vars `인부계산방식`) — 값은 수질 vars 와 동시 확정.

⚠️ build_tables 는 Windows 미검증. 성상별·기초시설 표 앵커는 표 캡션·머리 셀 추정 —
   지역개황 2.7 표와 동일 구조라 그쪽 앵커 요령(고유 문자열·출현 횟수 확인)을 따를 것.
"""
import math

from calc_waste import household_unit_kgpd, waste_oil_lpd
from calc_water import sewage_unit_Lpd
from hwp_util import (MISSING, blank_row, col_begin, down, find_in_table, fit_rows,
                      right, set_cell, write_at)


def compute(v):
    ye, tj = v.get("예측", {}), v.get("통계", {})
    r = {}

    equip = ye.get("장비") or []
    if equip:
        base = sum(e["대수"] * e["대당인원"] for e in equip)
        if ye.get("인부계산방식", "합_올림_곱2") == "합_올림_곱2":
            r["인부"] = math.ceil(base) * 2
        else:
            r["인부"] = math.ceil(base * 2)
        for e in equip:
            if e.get("연료_lph") and e.get("잡품비_pct"):
                e["폐유"] = round(waste_oil_lpd(e["연료_lph"], e["대수"], e["잡품비_pct"]), 2)
        oils = [e.get("폐유") for e in equip]
        r["폐유합"] = round(sum(o for o in oils if o), 2) if all(oils) else None
    else:
        r["인부"] = r["폐유합"] = None
    r["장비"] = equip

    if tj.get("생활폐_배출량_톤일") and tj.get("인구"):
        r["생활폐_원단위"] = round(household_unit_kgpd(tj["생활폐_배출량_톤일"], tj["인구"]), 2)
    else:
        r["생활폐_원단위"] = None
    if tj.get("분뇨처리량") and tj.get("인구"):
        r["분뇨_원단위"] = round(sewage_unit_Lpd(tj["분뇨처리량"], tj["인구"]), 2)
    else:
        r["분뇨_원단위"] = None
    for k, unit in [("생활폐", "생활폐_원단위"), ("분뇨", "분뇨_원단위")]:
        r[f"{k}_일량"] = (round(r[unit] * r["인부"], 2)
                          if r[unit] is not None and r["인부"] else None)
    return r


def build_slots(v):
    sa, hd, ye, tj = v.get("사업", {}), v.get("현황", {}), v.get("예측", {}), v.get("통계", {})
    r = compute(v)
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    narr = hd.get("서술", {})
    s = {
        "사업명": g(sa, "사업명"),
        "시군": g(sa, "시군"),
        "조사시기": g(hd, "조사시기"),
        "품셈연도": g(tj, "품셈연도"),
        "통계연보연도": g(tj, "통계연보연도"),
        "하수도통계연도": g(tj, "하수도통계연도"),
        "하수도공표일": g(tj, "하수도공표일"),
        "생활폐_배출량": g(tj, "생활폐_배출량_톤일"),
        "분뇨처리량": g(tj, "분뇨처리량"),
        "인구": (f"{tj['인구']:,}" if tj.get("인구") else MISSING),
        "인부수": r["인부"] or MISSING,
        "생활폐_일량": (f"{r['생활폐_일량']:.2f}" if r["생활폐_일량"] is not None else MISSING),
        "분뇨_일량": (f"{r['분뇨_일량']:.2f}" if r["분뇨_일량"] is not None else MISSING),
        "폐유_합": (f"{r['폐유합']:.2f}" if r["폐유합"] is not None else MISSING),
        "임목_서술": g(ye, "임목_서술"),
    }
    for key in ["관리구역", "생활폐", "사업장폐", "건설폐", "지정폐",
                "하수시설", "분뇨시설", "음식물시설", "매립시설", "소각시설"]:
        s[f"{key}_서술"] = narr.get(key) or MISSING
    return s


def build_tables(hwp, v):
    """표 편집 13종. 성상별·기초시설 표 값은 vars `성상별표`·`기초시설표` (지역개황 원천)."""
    hd = v.get("현황", {})
    r = compute(v)
    cell = lambda x: set_cell(hwp, str(x) if x not in (None, "") else MISSING)

    # ── 성상별 5표 선(先)비우기 — vars 에 없으면 **기준 사업 값이 그대로 남는다**
    #    (천안 채점 WRONG 5, 2026-08-31 실증 — "값 없음, 스킵"이 바로 그 함정이었다).
    #    다섯 표 모두 데이터가 `원주시` 라벨 한 행뿐이라, 라벨 셀을 문서 순서대로 찾아
    #    행을 비우고 라벨만 새 시군으로 바꾼다. vars 가 준 표는 아래 채움 루프가 덮는다.
    #    ⚠️ 되먹임(시군=원주시)이면 치환 뒤에도 라벨이 `원주시`라 다음 탐색이 같은 표를
    #    다시 문다 — skip=i 로 전진시킨다 (기상 C2 앵커 재생성 결함과 같은 부류).
    시군 = v.get("사업", {}).get("시군")
    for i in range(5):
        sk = i if 시군 == "원주시" else 0
        if not blank_row(hwp, "원주시", 0, keep_first=1, skip=sk):
            print(f"    WARNING: 성상별 {i+1}번째 표 — '원주시' 라벨 못 찾음")
            continue
        write_at(hwp, "원주시", 0, 0, [시군], skip=sk)   # 라벨 칸 = 시군 (없으면 [확인 필요])

    # 성상별 5표 + 기초시설 5표 — vars 에 {표이름: {"앵커": str, "skip": int, "행": [[...]]}}
    # 꼴로 담는다 (지역개황 2.7 과 동일 구조 — D2 일반화 전까지의 범용 채움).
    for group in ("성상별표", "기초시설표"):
        for name, spec in (hd.get(group) or {}).items():
            rows = spec.get("행") or []
            anchor = spec.get("앵커")
            if not rows or not anchor:
                print(f"  {name} — 값 없음, 스킵 (원주 잔존 위험 ⚠️ leak_check 대상)")
                continue
            print(f"  {name} ({len(rows)}행)")
            if not find_in_table(hwp, anchor, skip=spec.get("skip", 0)):
                print(f"    WARNING: 앵커 '{anchor}' 못 찾음")
                continue
            base = spec.get("베이스행", len(rows))
            if base != len(rows):
                fit_rows(hwp, anchor, base, len(rows))
            for i, row in enumerate(rows):
                if i:
                    down(hwp)
                    col_begin(hwp)
                for val in row:
                    cell(val)
                    right(hwp)

    print("  인부 표")
    equip = r["장비"]
    if equip and find_in_table(hwp, "대당 인원수(명)"):
        fit_rows(hwp, "대당 인원수(명)", 2, len(equip))
        for i, e in enumerate(equip):
            if i:
                down(hwp)
                col_begin(hwp)
            per = e["대수"] * e["대당인원"]
            for val in [e["명"], e["규격"], e["대수"], e["대당인원"], f"{per:.1f}"]:
                cell(val)
                right(hwp)

    print("  원단위·발생량 표")
    if find_in_table(hwp, "배출원단위"):
        # 행: 공사인부 | n | - / 배출원단위 | 생활 | 분뇨 | - / 발생량 | 생활 | 분뇨 | -
        down(hwp)      # ⚠️ 표 구조 추정 — Windows 확정
        col_begin(hwp)
        right(hwp)
        cell(r["인부"])
        for pair in ([r["생활폐_원단위"], r["분뇨_원단위"]], [r["생활폐_일량"], r["분뇨_일량"]]):
            down(hwp)
            col_begin(hwp)
            right(hwp)
            for val in pair:
                cell(f"{val:.2f}" if val is not None else None)
                right(hwp)

    print("  폐유 표")
    if equip and find_in_table(hwp, "연료사용량"):
        fit_rows(hwp, "연료사용량", 2, len(equip))
        down(hwp)
        col_begin(hwp)
        for i, e in enumerate(equip):
            if i:
                down(hwp)
                col_begin(hwp)
            for val in [e["명"], e["규격"], e["대수"], e.get("연료_lph"),
                        e.get("잡품비_pct"), e.get("폐유")]:
                cell(val)
                right(hwp)
        down(hwp)
        col_begin(hwp)
        right(hwp, 5)
        cell(f"{r['폐유합']:.2f}" if r["폐유합"] is not None else None)   # 합계 필드 덮기

    print("  자원순환 표 편집 종료 (⚠️ Windows 검증 전)")

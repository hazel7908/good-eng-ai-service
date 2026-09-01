#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사업개요(0100) 파트 핸들러 — W1 (2026-08-31). 인풋 전개형 (계산은 비율뿐).

규약: build_slots(v) / build_tables(hwp, v). 지식: rules/small-env/project-overview.md.
⚠️ 인풋 순환 금지 — vars 는 신청서류에서 만든다 (rule §0). input/사업개요.txt 사용 금지.
⚠️ build_tables 는 Windows 미검증. 사업시행자 표의 열 구조 변형(2열↔3열)은 미지원 —
   기준 사업(원주 2열) 틀만. 대상사업 기준 셀은 통째 교체(조항 3계열 분기).
"""
from hwp_util import (MISSING, col_begin, down, find_in_table, fit_rows,
                      left, right, set_cell, write_at)


def compute(v):
    r = {}
    rows = v.get("토지이용") or []
    total = sum(x.get("면적") or 0 for x in rows)
    r["토지이용"] = [
        # vars 에 비율이 명시돼 있으면 그것을 쓴다 (기본은 계산).
        # ⚠️ 원주 원본이 자기모순이다 — 45.23·6.59·40.57 은 반올림인데 `7.61` 만 절사다
        #    (1061.54/13934×100 = 7.6183). 공식을 절사로 바꾸면 나머지 셋이 깨진다.
        {**x, "비율": (x.get("비율")
                     or (f"{(x.get('면적') or 0) / total * 100:.2f}" if total else None))}
        for x in rows
    ]
    r["토지이용_합"] = total
    js = (v.get("조서") or {}).get("행") or []
    # 조서 행: [..., 지적면적, 사업부지, 도로, 소계, 비고] — 숫자 열 합계 (합계 필드 덮기용)
    r["조서_행수"] = len(js)
    return r


def build_slots(v):
    sa, gj, bg, gw, il = (v.get("사업", {}), v.get("실시근거", {}), v.get("배경", {}),
                           v.get("경위", {}), v.get("일정", {}))
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        "사업명": g(sa, "사업명"),
        "위치": g(sa, "위치"),
        "면적": (f"{sa['면적_㎡']:,}" if sa.get("면적_㎡") else MISSING),
        "허가권자": g(sa, "허가권자"),
        "배경_서술": g(bg, "서술"),          # 5꼴 자유 서술 — 판단 (rule §2)
        "실시근거_서술": g(gj, "서술"),      # 단순형/증설형 분기 (rule §4-2)
        "경위_조사": g(gw, "조사"),
        "경위_작성": g(gw, "작성"),
        "경위_요청": g(gw, "요청"),
        "경위_알림": g(gw, "알림"),
        "착공일": g(il, "착공일"),
        "준공일": g(il, "준공일"),
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
    """표 편집 6종. 앵커·오프셋은 Windows 세션에서 확정."""
    r = compute(v)
    gj = v.get("실시근거", {})
    cell = lambda x: set_cell(hwp, str(x) if x not in (None, "") else MISSING)

    print("  실시근거 표 — 대상사업 기준 셀 통째 교체 + 사업규모")
    if gj.get("대상사업_기준") and find_in_table(hwp, "대 상 사 업"):
        right(hwp)
        cell(gj["대상사업_기준"])           # 조항 3계열 분기 (rule §4-1)
    if gj.get("규모_셀") and find_in_table(hwp, "사 업 규 모"):
        right(hwp)
        cell(gj["규모_셀"])                 # 단순형 "13,934㎡" / 증설형 3분할 텍스트

    # 아래 4표는 셀 주소 실측(2026-08-31)으로 확정. `write_at` 규약 —
    # ⚠️ 자료가 없어도 건너뛰지 않는다. 건너뛰면 기준 사업 값이 그대로 실린다
    #    (실제로 천안 산출물에 원주 조서 값 27종이 남아 있었다. `leak_check` 는
    #     서술 문장만 보므로 게이트를 통과했다).
    W = lambda *a, **k: write_at(hwp, *a, **k)

    print("  편입토지조서 — 값은 B열부터 7칸 (A는 시군/읍면 세로 병합)")
    js = (v.get("조서") or {}).get("행") or []
    BASE_JS = 7
    rows = js or [[None] * 7 for _ in range(BASE_JS)]
    if find_in_table(hwp, "지적면적"):
        fit_rows(hwp, "지적면적", BASE_JS, len(rows))
        # 🚨 A열(행정구역)은 **세로 병합 한 칸**이라 값 열만 쓰면 기준 사업이 남는다 —
        #    천안 산출물에 `원주시`·`호저면`·`무장리` 가 그대로 있었다 (2026-09-01
        #    표유출검사 적발. 지번 셀은 비웠는데 이 칸만 남아 기존 게이트를 다 통과했다).
        #    조서의 행정구역은 **편입토지조서 원문에서 오는 값**이라 vars 로 받는다.
        W("지적면적", 1, 0, [(v.get("조서") or {}).get("행정구역")])
        for i, row in enumerate(rows):
            W("지적면적", 1 + i, 1, list(row)[-7:] if len(row) >= 7 else row)
        W("지적면적", 1 + len(rows), 1, joseo_total(js) + ["-"])   # 합계 행 (=SUM 필드 덮기)

    print("  사업시행자 — 구분·성명 2칸 (6행)")
    sh = (v.get("시행자") or {}).get("행") or []
    BASE_SH = 6
    rows = sh or [[None] * 2 for _ in range(BASE_SH)]
    if find_in_table(hwp, "성 명"):
        fit_rows(hwp, "성 명", BASE_SH, len(rows))
        for i, row in enumerate(rows):
            W("성 명", 1 + i, 0, list(row)[:2])

    print("  토지이용계획 (비율 계산) — 4칸 + 합계")
    tl = r["토지이용"]
    BASE_TL = 4
    rows = tl or [{}] * BASE_TL
    if find_in_table(hwp, "비 율(%)"):
        fit_rows(hwp, "비 율(%)", BASE_TL, len(rows))
        for i, x in enumerate(rows):
            W("비 율(%)", 1 + i, 0,
              [x.get("구분"),
               (f"{x['면적']:,.2f}" if x.get("면적") else None),
               x.get("비율"), "-"])
        tot = r["토지이용_합"]
        W("비 율(%)", 1 + len(rows), 1,
          [f"{tot:,.2f}" if tot else None, "100.00" if tot else None, "-"])

    print("  피해방지 — 규격~비고 4칸 (9행, A는 공종 세로 병합)")
    ph = (v.get("피해방지") or {}).get("행") or []
    BASE_PH = 9
    rows = ph or [[None] * 4 for _ in range(BASE_PH)]
    if find_in_table(hwp, "수 량"):
        fit_rows(hwp, "수 량", BASE_PH, len(rows))
        for i, row in enumerate(rows):
            W("수 량", 1 + i, 1, list(row)[-4:] if len(row) >= 4 else row)

    print("  발전설비 — 라벨 앵커 12행 + 용량 블록 2×6행")
    # 실측 구조(2026-08-31 셀 주소): A열 대분류(`태양광모듈` 2~13행 · `인버터` 14~25행)가
    # **세로 병합**, B=항목, C=발전소명(용량 행만), D=값, E=비고.
    # 🚨 `down()` 이 병합 블록을 통째로 건너뛰어 **행 오프셋이 불규칙하다**
    #    (앵커에서 +6 → B8, +7 → B14 로 9~13행을 건너뛴다). 그래서 행 오프셋을 쓰지 않고
    #    **각 행의 고유 라벨을 앵커로** 잡는다. 용량 블록만 C열로 나온 뒤 `row_after` 로 훑는다.
    # ⚠️ 라벨 충돌: `무게`⊂`모듈무게`, `정격전압`⊂`개방전압/정격전압` → skip 으로 가른다.
    seolbi = v.get("설비") or {}
    항목 = seolbi.get("항목") or {}
    SIMPLE = [("태양전지방식", 0), ("모듈의정격출력", 0), ("개방전압/정격전압", 0),
              ("단락전류/최대전류", 0), ("외형크기", 0), ("모듈무게", 0),
              ("주파수", 0), ("입력전압", 0), ("정격전압", 1), ("출력전압", 0),
              ("크기(W×D×H)", 0), ("무게", 1)]
    for lab, sk in SIMPLE:
        W(lab, 0, 1, [항목.get(lab), "-"], skip=sk, from_anchor=True)

    BASE_CAP = 6            # 발전소 수 (원주 6개소)
    # 🚨 용량 블록은 **앵커를 한 번만 잡고 C열에 머문 채 한 행씩 내려간다.**
    #    행마다 재탐색하면(`row_after=i`) 병합 때문에 한 행이 중복된다 — 인버터 블록에서
    #    `호저 태양광발전소` 가 두 번 찍혔다 (2026-08-31 실측).
    #    B열(`용량`)이 6행에 걸친 세로 병합이라, 오른쪽으로 한 칸 나와 C열에 선 뒤
    #    `왼쪽 2칸 → 아래 1행` 으로 다음 행 C 를 잡는다.
    for key, sk in [("모듈용량", 0), ("인버터용량", 1)]:
        rows = seolbi.get(key) or [[None] * 3 for _ in range(BASE_CAP)]
        if not find_in_table(hwp, "용량", skip=sk):
            print(f"    WARNING: 용량 블록(skip={sk}) 앵커 못 찾음")
            continue
        right(hwp)                                  # B(용량) → C(발전소명)
        for row in rows[:BASE_CAP]:
            vals = list(row)[:3]
            for k, val in enumerate(vals):
                set_cell(hwp, MISSING if val is None else str(val))
                if k < len(vals) - 1:
                    right(hwp)
            left(hwp, len(vals) - 1)                # 다시 C 열로
            down(hwp)                               # 다음 행

    print("  사업개요 표 편집 종료")

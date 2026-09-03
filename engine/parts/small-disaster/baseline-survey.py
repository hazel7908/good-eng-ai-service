#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 3장 기초현황 조사 핸들러 — C 베이스 (2026-09-03 Mac).

규약: build_slots / build_tables. 지식: rules/small-disaster/baseline-survey.md.
표 9종 — 유역특성(유역×단계) · 하천 현황 · 관측소(셀 토큰 + 표고·개시일 2셀) · 연도별 기상(10행) · 토양 2 ·
재해발생현황(10년) · 시설물 · 탐문 2. 앵커·오프셋은 **Windows 실측 전 추정**.
자료 없는 표는 **비운다**(행 유지·`[확인 필요]`) — 건너뛰면 천안 값이 남는다.
값 승계: 유역특성은 4장 vars `유역` 과 같은 값(불일치 금지) · 기상은 kma.py(소환 0721 원천).
"""
from hwp_util import (MISSING, blank_row, blank_table_here, blank_tables, find_in_table, fit_rows, josa, write_at)


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
    out["표토_조사"] = josa(t.get("표토"), "으로로")
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
    """공용 `hwp_util.blank_tables` 위임 — skip 을 앵커 생존 여부로 자동 결정 (충주 3장 3건의 답)."""
    k = blank_tables(hwp, anchor, header_rows, limit)
    if k == 0:
        print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")
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
        # 🚨 `blank_row` 는 **한 열만** 지운다(앵커 열). 이걸로 비우면 나머지 칸에
        #    기준 사업 값이 그대로 남는다 — 충주 3장에서 `0.110, 0.162` 가 실제로
        #    표유출검사 ③에 걸렸다 (09-03). 행 전체는 `blank_table_here` 다.
        # ⚠️ 머리는 **1행**(두 줄 셀 `산정\n지점` — 행이 아니라 셀 안 문단이다).
        #    header_rows=2 는 첫 데이터 행(A 개발전 …)을 남긴다 → ③ 잔존 5값의 원인 후보.
        _blank_all(hwp, "유역평균경사", 1, limit=2)

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
        _blank_all(hwp, "평  균", 1, limit=1)      # 〃 blank_row 는 한 열만 지운다

    print("  토양분포현황 표 2 · 재해발생현황 표 2 · 시설물 표 — 자료 없으면 비움")
    # 🔬 실측: 머리는 **1행**(`토양부호|토양통명|…`)이고 줄바꿈이 없다.
    #    `header_rows=2` 로 두면 **첫 데이터 행(`YdB 예천 양토…`)이 안 지워진다** —
    #    다른 사업에 천안 토양이 그대로 나간다 (09-03 되먹임 실측).
    #    ⚠️ 앵커는 `통명` 이다 — XML 상 한 셀인 `토양부호` 는 런이 `토양`/`부호` 로
    #       갈려 있어 **한글 찾기로는 안 걸린다**(XML 로 읽은 머리 문자열을 그대로
    #       앵커로 쓰면 안 되는 자리다).
    _blank_all(hwp, "통명", 1)
    # 토양분포현황(2) — ③ 실유출(1.27·11.43·40,705…). 머리 1행(`토양군|토양의 성질|침투율|면적|구성비`),
    # Type A~D 4행. 고정 설명 셀(⚪유출률…)을 살리려 **면적·구성비 두 칸만** [확인 필요]로 쓴다.
    # 🔬 실측 (09-03): 머리는 `토양군|토양의 성질|침투율(㎜/hr)|평가대상지역|면적(㎡)|구성비(%)|TypeA`
    #    — 앵커 `침투율`=C 열이고 면적은 **E**, 구성비는 F 다. `col_off=3` 은 D(평가대상지역)라
    #    한 칸 왼쪽이었다(그래서 `1.27·40,705` 가 남았다). col_begin 기준 **4**.
    # 🔬 실측 셀 주소 (09-03): 머리 2행(`토양군|토양의 성질|침투율(㎜/hr)|평가대상지역`
    #    / `면적(㎡)|구성비(%)`) · 데이터 3~6행 · **7행이 합계**.
    #    앵커 `침투율`=C1(2행 병합) → down(1)=3행. col_begin 기준 **면적=3 · 구성비=4**.
    #    ⚠️ col_off 를 4 로 두면 구성비만 비워지고 **면적이 남는다**(`40,705` 가 그렇게 샜다).
    #    C열(침투율 범위 `1.27~3.81` 등)은 **TYPE별 상수**라 건드리지 않는다 — 골든 2/2 동일.
    for i in range(5):                      # 3~6행 + 7행 합계
        W("침투율", 1 + i, 3, [None, None])
    # 재해발생현황 — ③ 실유출. 표가 **둘**이다(연도 전반 5 + 후반 5 — 둘째는 캡션 없음, 천안 L740~).
    # 머리는 1행(`구  분|단위|연도…`) — header_rows=2 는 이재민 행(2행)을 남긴다. limit=2 로 두 표 다.
    _blank_all(hwp, "이재민", 1, limit=2)
    _blank_all(hwp, "B등급", 1)

    print("  주민탐문 결과표 2 — 앵커 `면담 일시`(머리) · 성명·거주년수 셀 (연령·장소·일시·피해년도·원인은 토큰)")
    for k, row in enumerate((v.get("재해", {}).get("탐문") or [{}, {}])[:2]):
        # 🚨 `col_begin` 은 **세로 병합된 A1(`면담 주민` 라벨)** 로 간다 — col 0 에 쓰면
        #    라벨이 덮이고 뒤가 한 칸씩 밀린다 (실측: A1 이 `최○○` 가 되고 거주년수가
        #    연령 칸으로 갔다). 실측 배치: A1[2x1] 라벨 · B2[1x2] 성명 · D2 연령 · E2 거주년수.
        W("면담 일시", 1, 1, [row.get("성명")], skip=k)
        W("면담 일시", 1, 3, [row.get("거주년수")], skip=k)

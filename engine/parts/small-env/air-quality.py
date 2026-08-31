#!/usr/bin/env python3
"""대기질(0722) 파트 핸들러 — 2026-08-31 R1 리팩터로 generate.py 에서 분리 (로직 불변).

규약: build_slots(v) / build_tables(hwp, v). 지식 출처: rules/small-env/air-quality.md
"""
from hwp_util import (MODELING, _fmt, _pp_label, append_rows, col_begin, down,
                      fill_row, find_in_table, left, right, set_cell)

def slots_air_quality(v):
    """vars → 베이스 문서 빈칸 (텍스트 19종). 키는 air-quality.slots.md A절과 일치."""
    import calc_air
    hd, gi, ye, ga = v["현황"], v["기상"], v["예측"], v["저감"]
    pts = ye["지점"]
    daily = calc_air.daily_volume(ye["총토공량_㎥"], ye["토공기간_일"])
    trips = calc_air.trips_per_day(daily)

    return {
        "사업명": v["사업"]["사업명"],
        "조사시기": _fmt(hd.get("조사시기")),
        "측정일시": _fmt(hd.get("측정일시")),
        "측정지점_주소": _fmt(hd["측정지점"]["주소"]),
        # rule §5 — 자체측정·전 항목 만족이 기본. 인용/초과 사업은 vars 로 문장을 준다
        "측정결과_서술": hd.get("측정결과_서술",
                          "전 항목이 대기환경 기준치 이내를 만족하는 것으로 나타났다"),
        "예측지점_수": len(pts),
        "부지기상_기상대": gi["부지기상_기상대"],
        "상층기상": gi["상층기상"],
        "총토공량": f'{ye["총토공량_㎥"]:,.2f}',
        "토공기간": ye["토공기간_일"],
        "일작업량": f"{daily:.2f}",
        "예측결과_서술": ye.get("예측결과_서술",
                          "공사시 주변 정온시설의 대기질 영향을 예측한 결과 전지점에서 "
                          "대기환경 기준을 만족하는 것으로 조사되었다."),
        "기상연보_연도": gi["기상연보_연도"],
        "품셈_연도": ye.get("품셈_연도", 2023),
        # 주석 표기 — 평창은 나눗셈 원값(5.33), 청주는 올림(2). 1:1 갈림 → vars
        "운반횟수": ye.get("운반횟수_주석", trips),
        "이동거리": ye["이동거리_km"],
        "사업종류_운영시": ye.get("운영시_문구",
                           "본 사업은 태양광발전시설 조성사업으로"),
        "저감효과_도입": ga.get("저감효과_도입",
                          "공사시 주변지역 대기질의 영향이 미미할 것으로 예상되나, 비산먼지 "
                          "저감을 위해 각종 방안 (살수, 차속제한 등)을 필요시 실시할 계획이며,"),
        "저감후_서술": ga.get("저감후_서술",
                         "각종 저감방안의 실시 후 전 항목이 전 지점에서 대기환경기준"
                         "(24시간 기준)을 만족하는 것으로 나타났다."),
    }


def tables_air_quality(hwp, v):
    """표 편집 — air-quality.slots.md B절. 베이스(청주)는 PP 5행."""
    import calc_air as ca
    hd, gi, ye, ga = v["현황"], v["기상"], v["예측"], v["저감"]
    pts = ye["지점"]
    n = len(pts)
    BASE_ROWS = 5
    P = gi["강수일수_P"]
    U = gi["평균풍속_U"]
    # 실무 엑셀은 일작업량을 소수 2자리(54.92)로 반올림한 값으로 후속 계산한다 — 재현
    daily = round(ca.daily_volume(ye["총토공량_㎥"], ye["토공기간_일"]), 2)
    trips = ca.trips_per_day(daily)
    vkt = ca.vkt_per_day(trips, ye["이동거리_km"])
    lbl_pt = _pp_label(ye, "지점표")       # 영향예측지점 — 청주 `P - 1`
    lbl_pr = _pp_label(ye, "예측표")       # 예측결과·저감후 — 청주 `P-1`

    print("  측정지점")
    if find_in_table(hwp, "A - 1"):
        right(hwp); set_cell(hwp, _fmt(hd["측정지점"]["주소"]))
        right(hwp); set_cell(hwp, _fmt(hd["측정지점"].get("토지이용")))
        right(hwp); set_cell(hwp, _fmt(hd["측정지점"].get("이격거리_m")))

    print("  기상개황 (2일)")
    for i, day in enumerate(hd.get("기상개황", [])[:2]):
        anchor = ["2024.01.09", "2024.01.10"][i]       # 베이스(청주) 일자 셀
        if find_in_table(hwp, anchor):
            fill_row(hwp, [day["일자"], day["일기"], day["기온"], day["습도"],
                           day["풍향"], day["풍속"], day["기압"]])
        else:
            print(f"    WARNING: 기상개황 앵커 '{anchor}' 못 찾음")

    print("  측정결과 (6항목)")
    if find_in_table(hwp, "A - 1", skip=1):
        m = hd["측정결과"]
        # 열 순서는 베이스(청주) 고정: SO2 CO NO2 PM-10 PM-2.5 O3 (slots.md B)
        for k in ("SO2", "CO", "NO2", "PM10", "PM25", "O3"):
            right(hwp); set_cell(hwp, _fmt(m[k]))      # None → [확인 필요]

    print("  영향예측지점")
    if find_in_table(hwp, "XTM"):
        append_rows(hwp, "XTM", BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            fill_row(hwp, [lbl_pt.format(n=p["번호"]), p["이름"], p["방향"],
                           p["이격거리_m"], _fmt(p.get("XTM")), _fmt(p.get("YTM")),
                           _fmt(p.get("비고", "-"))])
        for j in range(max(0, BASE_ROWS - n)):     # 남는 행(베이스 잔재) 삭제
            if j == 0:
                down(hwp)
            hwp.HAction.Run("TableDeleteRow")

    print("  일 작업량 산정")
    # ⚠️ '사업계획지구' 는 현황조사내용 표의 '▪ 대상범위 : 사업계획지구 중심…' 셀에
    #    부분매칭된다 (평창 1차 검증 실측) — 헤더 '절 토(㎥)' 에서 내려간다
    if find_in_table(hwp, "절 토(㎥)"):
        down(hwp)
        fill_row(hwp, [f'{ye["절토_㎥"]:,.2f}', f'{ye["성토_㎥"]:,.2f}',
                       f'{ye["총토공량_㎥"]:,.2f}', ye["토공기간_일"], f"{daily:.2f}"])

    print("  투입장비대수")
    if find_in_table(hwp, "굴삭기"):
        right(hwp, 2)                       # 장비명→규격→일작업량
        set_cell(hwp, f"{daily:.2f}")
        right(hwp); set_cell(hwp, f"{daily / 8:.2f}")
    # 덤프 장비별 작업량 — 청주 원본 52.5 는 오기. 상세표 57.2 로 낸다 (slots.md B ⚠️)
    if find_in_table(hwp, "52.5"):
        set_cell(hwp, "57.2")

    print("  q1 계수 (E · P)")
    if find_in_table(hwp, "kg/VKT"):
        right(hwp); set_cell(hwp, f"{ca.e_q1(P, ca.K_PM10):.4f}")
        down(hwp); set_cell(hwp, f"{ca.e_q1(P, ca.K_PM25):.4f}")
    if find_in_table(hwp, "강수일수("):
        left(hwp); set_cell(hwp, P)

    print("  이동거리 산정")
    if find_in_table(hwp, "운반횟수(회/일)"):
        down(hwp)
        fill_row(hwp, [trips, ye["이동거리_km"], 1, f"{vkt:.2f}"])

    print("  q1 산정")
    # ⚠️ "덤프트럭 운행" 계열 앵커는 계수표 캡션 셀과 얽혀 skip 지도가 흔들린다 (1·2차 실측).
    #    산정표 헤더의 `㎏`(U+338F)가 유일 앵커다 — 계수표는 ASCII `kg/VKT` 를 쓴다.
    if find_in_table(hwp, "배출계수(㎏/VKT)"):
        q10, q25 = ca.q1_kg_day(P, vkt, ca.K_PM10), ca.q1_kg_day(P, vkt, ca.K_PM25)
        down(hwp)                       # 헤더 → PM-10 행 E 셀
        fill_row(hwp, [f"{ca.e_q1(P, ca.K_PM10):.4f}", f"{vkt:.2f}",
                       f"{q10:.4f}", f"{ca.g_per_sec(q10):.4f}"])
        # PM-2.5 행 — g/sec 셀에서 내려가 역순으로. VKT 는 세로 병합이라
        # left 2회째가 병합 셀에 닿는다 (2차 검증 실측 — 0.0951 이 VKT 를 덮었다). E 는 3회.
        down(hwp)
        set_cell(hwp, f"{ca.g_per_sec(q25):.4f}")
        left(hwp); set_cell(hwp, f"{q25:.4f}")
        left(hwp, 2); set_cell(hwp, f"{ca.e_q1(P, ca.K_PM25):.4f}")

    print("  q2 계수·산정")
    E2 = ye["E_q2"]
    q2 = ca.q2_kg_day(E2, daily)
    q2_10, q2_25 = ca.tsp_to_pm(q2)
    if find_in_table(hwp, "0.0902lb"):
        set_cell(hwp, f'배출계수({ye["E_q2_lb"]}lb/ton×0.454kg/lb)')
        left(hwp); set_cell(hwp, E2)
    if find_in_table(hwp, "연간 건조일수"):
        left(hwp); set_cell(hwp, 365 - P)
    if find_in_table(hwp, "기타 장비 운행시", skip=1):
        right(hwp, 2)
        fill_row(hwp, [E2, f"{daily:.2f}", 1.75,
                       f"{q2_10:.4f}", f"{ca.g_per_sec(q2_10):.4f}"])
        if find_in_table(hwp, "0.1304"):
            set_cell(hwp, f"{q2_25:.4f}")
            right(hwp); set_cell(hwp, f"{ca.g_per_sec(q2_25):.4f}")

    print("  q3 계수·산정")
    E3_10, E3_25 = ye["E_q3_PM10"], ye["E_q3_PM25"]      # 표기용 (유효자리 보존 문자열 허용)
    q3_10 = ca.q3_kg_day(float(E3_10), daily)
    q3_25 = ca.q3_kg_day(float(E3_25), daily)
    if find_in_table(hwp, "0.00024lb"):
        set_cell(hwp, f'배출계수({ye["E_q3_PM10_lb"]}lb/ton×0.454kg/lb)')
        left(hwp); set_cell(hwp, E3_10)
    if find_in_table(hwp, "평균풍속("):
        left(hwp); set_cell(hwp, U)
    if find_in_table(hwp, "토량 상·하적시"):
        right(hwp, 2)
        fill_row(hwp, [ye.get("E_q3_산정", E3_10), f"{daily:.2f}", 1.75,
                       f"{q3_10:.4f}", f"{ca.g_per_sec(q3_10):.4f}"])
        # PM-2.5 행 — kg·g 만 역순으로 (E25 는 daily·비중 병합 너머라 left 수가 불안정.
        #             값이 사업마다 다르면 여기도 보정 필요 — rule §6-5)
        down(hwp)
        set_cell(hwp, f"{ca.g_per_sec(q3_25):.4f}")
        left(hwp); set_cell(hwp, f"{q3_25:.4f}")

    print("  q4 계수·산정")
    q4 = ca.q4_kg_day(daily)
    q4_10, q4_25 = ca.tsp_to_pm(q4)
    if find_in_table(hwp, "연간 건조일수", skip=1):
        left(hwp); set_cell(hwp, 365 - P)
    if find_in_table(hwp, "바람에 의한 흐트러짐", skip=1):
        right(hwp, 2)
        fill_row(hwp, ["0.00004", f"{daily:.2f}", 1.75, f"{q4:.4f}",
                       f"{q4_10:.4f}", f"{ca.g_per_sec(q4_10):.5f}"])
        down(hwp)
        set_cell(hwp, f"{ca.g_per_sec(q4_25):.5f}")
        left(hwp); set_cell(hwp, f"{q4_25:.4f}")

    print("  총 배출량")
    Q1 = ye.get("Q1", {"PM10": 0.0049, "PM25": 0.0045, "NO2": 0.1655})  # 장비 4/4 고정
    g = ca.g_per_sec
    # ⚠️ 자릿수·소계는 전부 **표시값 연쇄**다 (§6-1) — q4 만 5자리이고,
    #    소계·합계는 표에 적힌 반올림 문자열들을 다시 합산한다 (원값 합산은 0.0001 어긋난다).
    rows_q = [(f"{g(ca.q1_kg_day(P, vkt, ca.K_PM10)):.4f}", f"{g(ca.q1_kg_day(P, vkt, ca.K_PM25)):.4f}"),
              (f"{g(q2_10):.4f}", f"{g(q2_25):.4f}"),
              (f"{g(q3_10):.4f}", f"{g(q3_25):.4f}"),
              (f"{g(q4_10):.5f}", f"{g(q4_25):.5f}")]
    sub10 = sum(float(r[0]) for r in rows_q)
    sub25 = sum(float(r[1]) for r in rows_q)
    if find_in_table(hwp, "장비가동시(연료사용)"):
        right(hwp)
        fill_row(hwp, [Q1["PM10"], Q1["PM25"], Q1["NO2"]])
        # skip 지도: "덤프트럭 운행시"=계수표 캡션 셀 다음(1) · "기타 장비 운행시"=계수표+산정표 다음(2)
        # "토량 상․하적시"(U+2024)=총배출량 행뿐(0 — 계수표는 ㆍ, 산정표는 · 로 가운뎃점이 다르다)
        for name, skip_n, (g10, g25) in zip(
                ["덤프트럭 운행시", "기타 장비 운행시", "토량 상․하적시", "바람에 의한 흐트러짐"],
                [1, 2, 0, 2],
                rows_q):
            if find_in_table(hwp, name, skip=skip_n):
                right(hwp)
                fill_row(hwp, [g10, g25, "-"])
        if find_in_table(hwp, "소계"):
            right(hwp)
            fill_row(hwp, [f"{sub10:.4f}", f"{sub25:.4f}", "-"])
        if find_in_table(hwp, "합      계"):
            right(hwp)
            fill_row(hwp, [f'{Q1["PM10"] + sub10:.4f}', f'{Q1["PM25"] + sub25:.4f}',
                           f'{Q1["NO2"]:.4f}'])

    print("  예측결과")
    if n != BASE_ROWS:
        print(f"    WARNING: 예측결과 표는 병합 3행 구조라 행 확장 미구현 — PP {n} ≠ {BASE_ROWS}")
    m = hd["측정결과"]
    for i, p in enumerate(pts[:BASE_ROWS]):
        w = p.get("가중치")
        if not find_in_table(hwp, lbl_pr.format(n=p["번호"])):
            continue
        right(hwp, 2)       # P-n → 현황치 → 첫 값
        base_vals = [f'{m["PM10"]:.2f}', f'{m["PM25"]:.2f}', f'{m["NO2"]:.4f}']
        fill_row(hwp, base_vals)
        right(hwp); set_cell(hwp, f'{p["이름"]}\r\n({p["이격거리_m"]}m)')
        right(hwp); set_cell(hwp, f'XTM : {_fmt(p.get("XTM"))}\r\nYTM : {_fmt(p.get("YTM"))}')
        # 가중치·예측치 행
        # ⚠️ 예측치 행에서 col_begin 을 쓰면 병합된 P-n 셀로 가 라벨을 덮는다 (1차 실측)
        #    — "예측치" 라벨 셀을 직접 찾는다. NO2 는 4자리 (골든 0.0058)
        if find_in_table(hwp, "가중치", skip=i):
            right(hwp)
            fill_row(hwp, [f'{w["PM10"]:.2f}', f'{w["PM25"]:.2f}',
                           f'{w["NO2"]:.4f}'] if w else [MODELING] * 3)
        if find_in_table(hwp, "예측치", skip=i):
            right(hwp)
            fill_row(hwp, [f'{m["PM10"] + w["PM10"]:.2f}',
                           f'{m["PM25"] + w["PM25"]:.2f}',
                           f'{m["NO2"] + w["NO2"]:.4f}'] if w else [MODELING] * 3)

    print("  환경보전목표")
    tg = ga.get("환경보전목표", {"PM10": 100, "PM25": 35, "NO2": 0.06})
    for key, label in (("PM10", "PM-10(ppm)"), ("PM25", "PM-2.5(ppm)"), ("NO2", "NO2(ppm)")):
        if find_in_table(hwp, label):
            right(hwp); set_cell(hwp, tg[key])
            right(hwp); set_cell(hwp, tg[key])

    print("  저감 후 표 ×2 (가중치 ×0.5)")
    for tab, key, nd in (("PM-10", "PM10", 2), ("PM-2.5", "PM25", 2)):
        anchor = f"저감 전 {tab}"
        if not find_in_table(hwp, anchor):
            print(f"    WARNING: '{anchor}' 못 찾음")
            continue
        # 헤더가 2단(저감 전/후 ┬ 현황·가중·예측)이라 anchor 에서 한 번 더 내려간다.
        # append_rows(need<base)는 find 를 다시 하지 않으므로 이 down 이 유효하다 (3차 실측 보정)
        down(hwp)
        append_rows(hwp, anchor, BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            w = p.get("가중치")
            if w:
                # ⚠️ HALF_UP + 표시값 연쇄 — 0.99×0.5=0.495 는 0.50(실무), float round 는 0.49.
                #    예측치도 반올림된 가중치로 더한다 (11.00+0.06=11.06)
                b = w[key]
                half = ca.round_half_up(ca.mitigated_weight(b), 2)
                fill_row(hwp, [lbl_pr.format(n=p["번호"]),
                               f'{m[key]:.2f}', f"{b:.2f}", f'{m[key] + b:.2f}',
                               f'{m[key]:.2f}', f"{half:.2f}", f'{m[key] + half:.2f}'])
            else:
                fill_row(hwp, [lbl_pr.format(n=p["번호"]),
                               f'{m[key]:.2f}', MODELING, MODELING,
                               f'{m[key]:.2f}', MODELING, MODELING])
        # PP 수가 베이스(5)보다 적으면 남는 행(청주 잔재)을 지운다.
        # ⚠️ TableDeleteRow 후 커서는 당겨진 다음 행에 남는다 — down 은 첫 번째만 (4차 실측)
        for j in range(max(0, BASE_ROWS - n)):
            if j == 0:
                down(hwp)
            hwp.HAction.Run("TableDeleteRow")





build_slots = slots_air_quality
build_tables = tables_air_quality

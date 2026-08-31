#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수질(0723) 파트 핸들러 — W1 신규 (2026-08-31). R1 구조의 첫 정식 입주자.

규약: build_slots(v) / build_tables(hwp, v). 지식: rules/small-env/water-quality.md ·
빈칸 명세: templates/small-env/water-quality.slots.md · 계산: engine/calc_water.py.

✅ 2026-08-31 Windows 실측으로 앵커·오프셋 확정 (천안 첫 생성). 셀 주소를 직접 읽어
   맞췄고, 그 과정에서 잡은 것: 배수유역 표 7개는 앵커가 **첫 데이터 행**이라 오프셋이
   0부터고, B9·B15 는 **머리행이 두 줄**이라 데이터가 3·4행이며, 하천일람은 **9열**이다.
   ⚠️ 아직 못 본 길: 유역 수 n>0 인 채움 경로 (천안은 배수유역 자료가 없어 n=0 이다).
   그 경로의 행 늘리기/줄이기는 유역 자료가 있는 사업에서 확인할 것.
값 표기는 골든 관행: ha 4자리 · ㎥/sec 4자리 · ㎥/일 콤마 2자리 · ton/일 4자리 · SS 2자리.
"""
import math

from calc_water import (after_stages, basin_size_wonju, mixed_ss_mgL, sediment_tpd,
                        sewage_unit_Lpd, ss_untreated_mgL, storm_runoff_cms)
from hwp_util import (MISSING, blank_row, col_begin, down, find_in_table,
                      fit_rows, right, set_cell)


def _f(x, nd):
    return MISSING if x is None else f"{x:.{nd}f}"


def _comma(x, nd=2):
    return MISSING if x is None else f"{x:,.{nd}f}"


def _add(a, b):
    """둘 다 있을 때만 더한다.

    ⚠️ `(a or 0) + (b or 0)` 은 **자료가 없는데 0 을 지어낸다.** 천안 첫 생성에서
    합류 유량 칸에 `0.0000` 이 찍혀 나갔다 — 환각 금지(common.md §1) 위반이다.
    """
    return None if a is None or b is None else a + b


def compute(v):
    """vars → 계산 사슬 전체. slots 와 tables 가 **같은 결과**를 쓴다 (변수 일관성).

    값이 모자라면 해당 결과를 None 으로 둔다 — 토큰·셀에는 [확인 필요] 로 나간다.
    """
    hd, gi, ye, tj, ga = v["현황"], v["기상"], v["예측"], v["통계"], v["저감"]
    C = ye.get("유출계수", 0.3)                      # 계열 A 기본 (rule §3-2)
    S = ye.get("토사원단위", 300)
    density = ye.get("토사비중", 2.65)
    I = gi.get("강우강도")
    days = gi.get("강우일수")
    eff = ga.get("제거효율")

    # ★ 원칙: **끝까지 원값으로 계산하고 표시할 때만 반올림한다** (rule §3-0).
    #   괴산·원주·옥천 혼합값이 이 경로로만 4/4 정합한다 — 절사·표시값 연쇄 아님.
    r = {"C": C, "S": S, "비중": density, "basins": []}
    m2s = ye.get("배수유역_㎡") or []
    for m2 in m2s:
        ha = m2 / 10000
        b = {"㎡": m2, "ha": ha}
        if I:
            b["cms_raw"] = storm_runoff_cms(C, I, ha)
            b["cms"] = round(b["cms_raw"], 4)
            b["cmd_raw"] = b["cms_raw"] * 86400
            b["cmd"] = round(b["cmd_raw"], 2)
        if days:
            b["qs_raw"] = sediment_tpd(S, ha, density, days)
            b["qs"] = round(b["qs_raw"], 4)
        r["basins"].append(b)

    bs = r["basins"]
    full = bs and all("cmd" in b and "qs" in b for b in bs)
    if full:
        cms_raw = sum(b["cms_raw"] for b in bs)
        cmd_raw = sum(b["cmd_raw"] for b in bs)
        qs_raw = sum(b["qs_raw"] for b in bs)
        ss_raw = ss_untreated_mgL(qs_raw, cmd_raw)
        r["_raw"] = {"cms": cms_raw, "cmd": cmd_raw, "qs": qs_raw, "ss": ss_raw}
        r["cms합"] = round(cms_raw, 4)
        r["cmd합"] = round(cmd_raw, 2)
        r["qs합"] = round(qs_raw, 4)
        r["무처리SS"] = round(ss_raw, 2)
    else:
        r["_raw"] = None
        r["cms합"] = r["cmd합"] = r["qs합"] = r["무처리SS"] = None

    q1 = hd.get("측정값", {}).get("유량")
    c1 = hd.get("측정값", {}).get("SS")
    r["Q1"], r["C1"] = q1, c1
    if full and q1 is not None and c1 is not None:
        r["혼합"] = round(mixed_ss_mgL(q1, c1, cms_raw, ss_raw), 2)
    else:
        r["혼합"] = None

    # 인부 — 계산 순서 갈림 (rule §3-6): 원주 합→올림→×2 ↔ 괴산·충주 ×2→합→올림
    equip = ye.get("장비") or []
    if equip:
        base = sum(e["대수"] * e["대당인원"] for e in equip)
        if ye.get("인부계산방식", "합_올림_곱2") == "합_올림_곱2":
            r["인부"] = math.ceil(base) * 2
        else:
            r["인부"] = math.ceil(base * 2)
    else:
        r["인부"] = None

    if tj.get("분뇨처리량") and tj.get("인구"):
        r["원단위"] = round(sewage_unit_Lpd(tj["분뇨처리량"], tj["인구"]), 2)
        r["분뇨발생량"] = (round(r["원단위"] * r["인부"], 2) if r["인부"] else None)
    else:
        r["원단위"] = r["분뇨발생량"] = None

    # 침사지 — 규모(원주 연쇄)·효과·최종 혼합. 전부 원값 연쇄, 표시만 반올림
    if full:
        for b in bs:
            b["침사지"] = basin_size_wonju(b["cmd_raw"])
    r["효율"] = eff
    if full and eff:
        for b in bs:
            b["qs_1단"] = round(after_stages(b["qs_raw"], eff, 1), 4)
            b["qs_2단"] = round(after_stages(b["qs_raw"], eff, 2), 4)
        ss1_raw = after_stages(ss_raw, eff, 1)
        ss2_raw = after_stages(ss_raw, eff, 2)
        r["SS_1단"] = round(ss1_raw, 2)
        r["SS_2단"] = round(ss2_raw, 2)
        if q1 is not None and c1 is not None:
            r["혼합_1단"] = round(mixed_ss_mgL(q1, c1, cms_raw, ss1_raw), 2)
            r["혼합_2단"] = round(mixed_ss_mgL(q1, c1, cms_raw, ss2_raw), 2)
        else:
            r["혼합_1단"] = r["혼합_2단"] = None
    else:
        r["SS_1단"] = r["SS_2단"] = r["혼합_1단"] = r["혼합_2단"] = None
    return r


def build_slots(v):
    """vars → 본문 토큰 (spec.py EXPECT 와 일치). Mac --dry-run 으로 점검."""
    sa, hd, gi, tj, ga = v["사업"], v["현황"], v["기상"], v["통계"], v["저감"]
    r = compute(v)
    g = lambda d, k: d.get(k) or MISSING
    return {
        "사업명": g(sa, "사업명"),
        "시군": g(sa, "시군"),
        "합류하천명": g(sa, "합류하천명"),
        "조사시기": g(hd, "조사시기"),
        "정온시설_이격": g(hd, "정온시설_이격"),
        "정온시설_이름": g(hd, "정온시설_이름"),
        "하천서술": g(hd, "하천서술"),
        "측정지점_위치": g(hd, "측정지점_위치"),
        "측정일시": g(hd, "측정일시"),
        "측정결과_서술": g(hd, "측정결과_서술"),     # rule §5-2 갈림 — vars 판단값
        "기상대": g(gi, "기상대"),
        "IDF지점": g(gi, "IDF지점"),
        "기상연보연도": g(gi, "기상연보연도"),
        "강우일수": g(gi, "강우일수"),
        "우수유출_초당": _f(r["cms합"], 4),
        "우수유출_일량": _comma(r["cmd합"]),
        "토사유출_합": _f(r["qs합"], 4),
        "무처리SS": _f(r["무처리SS"], 2),
        "혼합농도": _f(r["혼합"], 2),
        "인부수": r["인부"] if r["인부"] else MISSING,
        "하수도통계연도": g(tj, "하수도통계연도"),
        "통계연보연도": g(tj, "통계연보연도"),
        "분뇨처리량": g(tj, "분뇨처리량"),
        "인구": _comma(tj.get("인구"), 0) if tj.get("인구") else MISSING,
        "분뇨발생량": _f(r["분뇨발생량"], 2),
        "침사후SS_1단": _f(r["SS_1단"], 2),
        "침사후SS_2단": _f(r["SS_2단"], 2),
        "최종혼합": _f(r["혼합_2단"], 2),
        "침사지_개소": g(ga, "침사지_개소"),        # 원주 자기모순 자리 — 판단값 (rule §6)
        "운영시_배수시설": g(ga, "운영시_배수시설"),
    }


# ------------------------------------------------------------
# 표 편집 — 앵커·오프셋 Windows 실측 확정 (2026-08-31). n>0 채움 경로만 미검증
# ------------------------------------------------------------
BASE_BASINS = 2         # 원주 베이스의 배수유역 행 수
BASE_EQUIP = 2          # 원주 베이스의 장비 행 수 (굴삭기·덤프트럭)


def _basin_rows(hwp, anchor, n_rows, fill_one, skip=0, has_total=False):
    """유역 행 표 공통: 앵커 → 행 수 맞춤 → 행별 채움 콜백.

    🚨 **유역 수를 모를 때(n_rows=0) 행을 0으로 줄이면 안 된다.** 머리행만 남은
       껍데기가 되고, 뒤 표들이 쓰는 `배수유역 1` 앵커까지 사라진다 — 실제로 B14 가
       그렇게 `앵커 못 찾음` 으로 실패했다 (2026-08-31 천안 첫 생성). 기준 사업 행
       수를 유지하고 `[확인 필요]` 로 비운다 (`hwp_util.blank_row` 원칙).
    ⚠️ 라벨 열(`배수유역 N`)은 남긴다 — **뒤 표의 앵커**라서 지우면 연쇄로 무너진다.
    has_total: 합계 행이 있는 표(B3·B8·B14). 그 행의 `=SUM` 필드도 함께 비운다 —
       안 비우면 원주 합계가 천안 이름 아래 남는다.
    """
    if not find_in_table(hwp, anchor, skip=skip):
        print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 스킵")
        return False
    if n_rows == 0:
        # ⚠️ **오프셋이 0부터다.** 앵커 `배수유역 1` 은 머리행이 아니라 **첫 데이터 행**의
        #    라벨 칸이다. `row_off=1` 로 시작하면 첫 행이 통째로 안 지워져 원주 값이
        #    그대로 남는다 — 7개 표 전부에서 실제로 그랬다 (2026-08-31 실측:
        #    3,547 · 0.3547 · 239.9 · 6,126.66 · 426.17 · 639.36 · 85.23).
        for k in range(BASE_BASINS):
            blank_row(hwp, anchor, k, keep_first=1, skip=skip)
        if has_total:
            blank_row(hwp, anchor, BASE_BASINS, keep_first=1, skip=skip)
        print("    유역 수 미상 — 행 유지하고 [확인 필요] 로 비움")
        return False                                        # 합계 계산은 건너뛴다
    # 🚨 **`fit_rows` 를 쓰면 안 된다.** 그쪽은 `find_in_table(anchor)` 를 skip 없이
    #    다시 부른다 — 같은 앵커를 쓰는 표가 7개라 **전부 첫 표(B3)로 끌려가** 거기에
    #    겹쳐 쓴다. 원주(2유역) 재생성에서 `배수유역 1` 표가 8개로 늘고 내용이 통째로
    #    밀렸다 (2026-08-31 실측). blank_row 의 skip 누락과 같은 부류다.
    cur = BASE_BASINS
    while cur > n_rows:                       # 줄이기 — 마지막 데이터 행을 지운다
        if not find_in_table(hwp, anchor, skip=skip):
            return False
        down(hwp, cur - 1)                    # 앵커 행이 곧 첫 데이터 행 (오프셋 0부터)
        hwp.HAction.Run("TableDeleteRow")
        cur -= 1
    while cur < n_rows:                       # 늘리기 — 마지막 데이터 행 **아래**에 넣는다.
        if not find_in_table(hwp, anchor, skip=skip):
            return False
        down(hwp, cur - 1)
        # ⚠️ `TableAppendRow` 는 **표 맨 끝**에 붙어 합계 행 아래로 간다. 여기선 안 된다.
        hwp.HAction.Run("TableInsertLowerRow")
        cur += 1
    if not find_in_table(hwp, anchor, skip=skip):
        return False
    col_begin(hwp)
    for i in range(n_rows):
        if i:
            down(hwp)
            col_begin(hwp)
        fill_one(i)
    return True


def build_tables(hwp, v):
    """표 편집 17종 (slots.md B절). 앵커·오프셋은 2026-08-31 실측 확정."""
    hd, gi, ye, ga = v["현황"], v["기상"], v["예측"], v["저감"]
    r = compute(v)
    bs = r["basins"]
    n = len(bs)
    cell = lambda x: set_cell(hwp, str(x) if x is not None else MISSING)

    print("  B1 — 수질 측정결과 (값 8 + 등급)")
    mv = hd.get("측정값", {})
    grade = hd.get("측정등급", {})
    # skip=1: 현황조사내용 표의 "수온(pH)" 가 먼저 걸린다 (원주 L15)
    if find_in_table(hwp, "pH", skip=1):
        for i, k in enumerate(["pH", "BOD", "TOC", "SS", "DO", "T-P", "T-N", "유량"]):
            if i:
                down(hwp); col_begin(hwp)
            right(hwp); cell(mv.get(k))
            if k not in ("T-N", "유량"):                 # 이 둘은 기준 열이 '-'
                right(hwp); cell(grade.get(k))

    print("  B2 — 영향예측지점 (하천명·좌표)")
    if find_in_table(hwp, "XTM"):
        # 원주 행: P - 1 | 소하천 | {{측정지점_위치}} | XTM | YTM | -
        down(hwp); col_begin(hwp); right(hwp)
        cell(hd.get("측정하천명"))
        right(hwp, 2)
        cell(hd.get("예측지점_XTM"))
        right(hwp)
        cell(hd.get("예측지점_YTM"))

    print("  B16 — 하천일람")
    # 🚨 자료가 없다고 **건너뛰면 원주 하천(섬강·한강)이 천안 보고서에 실린다.**
    #    실제로 첫 생성에서 섬강 2·한강 4·횡성·여주·정선·김포가 그대로 나갔고
    #    smoke_check 는 통과했다 (leak_check 는 서술 문장만 본다). 비워서 내보낸다.
    # ⚠️ **9열이다.** slots.md 는 "2행 8열" 이라고 적었지만 원주 실측은
    #    하천명·수계·유역·(2)·(3)·등급·기점~종점·유로연장·유역면적 = 9칸이고,
    #    8칸만 채우면 마지막 유역면적에 원주 `1,490.06` 이 남는다 (2026-08-31 실측).
    rivers = hd.get("하천일람") or [[None] * 9, [None] * 9]
    if find_in_table(hwp, "기점 ~ 종점"):
        fit_rows(hwp, "기점 ~ 종점", 2, len(rivers))
        for i, row in enumerate(rivers):
            if i:
                down(hwp); col_begin(hwp)
            for val in row:                                # 하천명~유역면적 8칸
                cell(val); right(hwp)

    print("  B4 — IDF 조견표")
    idf = gi.get("IDF표") or [[None] * 10, [None] * 10]     # [앞 10값, 뒤 10값]
    if find_in_table(hwp, "지속시간(분)"):                  # 없으면 비운다 (원주 강우강도 잔존 방지)
        for half in idf:
            down(hwp); col_begin(hwp); right(hwp)
            for val in half:
                cell(val); right(hwp)
            down(hwp); col_begin(hwp)                      # 다음 지속시간 행 건너뜀

    print("  B6 — 월별 강수일")
    rain = gi.get("월별강수일") or []
    # 없으면 12개월 + 합계 13칸을 비운다. `sum([])` 은 0 이라 **0 을 쓰면 거짓말**이 된다.
    vals = (rain + [sum(rain)]) if rain else [None] * 13
    if find_in_table(hwp, "강수일"):
        for val in vals:
            right(hwp); cell(val)

    print("  B3 — 배수유역")
    def basin_area(i):
        fill = [f"배수유역 {i+1}", _comma(bs[i]["㎡"], 0), _f(bs[i]["ha"], 4), "-"]
        for val in fill:
            cell(val); right(hwp)
    if _basin_rows(hwp, "배수유역 1", n, basin_area, has_total=True):
        down(hwp); col_begin(hwp); right(hwp)              # 합계 행 — =SUM 필드를 값으로 덮는다
        cell(_comma(sum(b["㎡"] for b in bs), 0)); right(hwp)
        cell(_f(sum(b["ha"] for b in bs), 4))

    print("  B5 — 우수유출량 산정결과")
    def runoff(i):
        b = bs[i]
        for val in [f"배수유역 {i+1}", _f(b["ha"], 4), r["C"], gi.get("강우강도"),
                    _f(b.get("cms"), 4), _comma(b.get("cmd")), "-"]:
            cell(val); right(hwp)
    if _basin_rows(hwp, "배수유역 1", n, runoff, skip=1, has_total=True):
        down(hwp); col_begin(hwp); right(hwp)          # 합계 행 (=SUM 필드를 값으로 덮는다)
        cell(_f(sum(b["ha"] for b in bs), 4)); right(hwp, 3)
        cell(_f(r["cms합"], 4)); right(hwp)
        cell(_comma(r["cmd합"]))

    print("  B7 — 토사유출량 산정결과")
    def sediment(i):
        b = bs[i]
        # ⚠️ **6열이다 — 비고 열이 없다.** 7값을 쓰면 한 칸씩 밀려 유역 2 의
        #    토사유출량 자리에 `-` 가 들어간다 (2026-08-31 원주 재생성 실측).
        for val in [f"배수유역 {i+1}", _f(b["ha"], 4), r["S"], r["비중"],
                    gi.get("강우일수"), _f(b.get("qs"), 4)]:
            cell(val); right(hwp)
    if _basin_rows(hwp, "배수유역 1", n, sediment, skip=2, has_total=True):
        down(hwp); col_begin(hwp); right(hwp)          # 합계 행
        cell(_f(sum(b["ha"] for b in bs), 4)); right(hwp, 4)
        cell(_f(r["qs합"], 4))

    print("  B8 — 무처리 SS (유역별 행 + 합계 필드 덮기)")
    def untreated(i):
        b = bs[i]
        # 유역별 행에도 SS 는 **합산값**을 쓴다 (원주 실측 — 두 행 모두 426.17)
        for val in [f"배수유역 {i+1}", _comma(b.get("cmd")), _f(b.get("qs"), 4),
                    _f(r["무처리SS"], 2), "-"]:
            cell(val); right(hwp)
    if _basin_rows(hwp, "배수유역 1", n, untreated, skip=3, has_total=True):
        down(hwp); col_begin(hwp); right(hwp)
        for val in [_comma(r["cmd합"]), _f(r["qs합"], 4), _f(r["무처리SS"], 2)]:
            cell(val); right(hwp)

    print("  B9 — 무처리 혼합")
    # ⚠️ **머리행이 두 줄이다.** 앵커 `순간 혼합농도(단순혼합)` 는 F1 이고 데이터는 3행
    #    (`A3:P-1`). `down(1)` 은 2행 = 부머리행이라 거기에 값을 쓰고 정작 데이터 행에는
    #    원주 값(`426.17`)이 남았다 (2026-08-31 셀 주소 실측).
    if find_in_table(hwp, "순간 혼합농도(단순혼합)"):
        down(hwp, 2); col_begin(hwp); right(hwp)
        for val in [r["Q1"], r["C1"], _f(r["cms합"], 4), _f(r["무처리SS"], 2),
                    _f(_add(r["Q1"], r["cms합"]), 4), _f(r["혼합"], 2)]:
            cell(val); right(hwp)

    print("  B10 — 공사인부 산정")
    equip = ye.get("장비") or []
    if equip and find_in_table(hwp, "대당 인원수(명)"):
        fit_rows(hwp, "대당 인원수(명)", BASE_EQUIP, len(equip))
        for i, e in enumerate(equip):
            if i:
                down(hwp); col_begin(hwp)
            for val in [e["명"], e["규격"], e["대수"], e["대당인원"],
                        _f(e["대수"] * e["대당인원"], 1)]:
                cell(val); right(hwp)

    print("  B11 — 오수발생량")
    if find_in_table(hwp, "분뇨발생량", skip=1):
        right(hwp); cell(r["인부"])
        right(hwp); cell(f"{_f(r['원단위'], 2)}(ℓ/인ㆍ일)")
        right(hwp); cell(f"{_f(r['분뇨발생량'], 2)}(ℓ/일)")

    print("  B12 — 침사지 규모")
    def size(i):
        b = bs[i]
        need, built, vol = b.get("침사지", (None, None, None))
        for val in [f"배수유역 {i+1}", _comma(b.get("cmd")), "639.36", need, "15",
                    built, "2", vol, "-"]:
            cell(val); right(hwp)
    _basin_rows(hwp, "배수유역 1", n, size, skip=4)

    print("  B13 — 침사지 설치제원")
    spec_rows = ga.get("침사지_제원") or []                 # [{용량, WLH}] — X(설계)
    def dims(i):
        b = bs[i]
        row = spec_rows[i] if i < len(spec_rows) else {}
        vol = b.get("침사지", (None, None, None))[2]
        # ⚠️ **5열이고 WLH 는 한 칸이다** (셀 주소 실측 A~E · `D2="2.5 × 5.0 × 2.0"`).
        #    추출 텍스트에서는 셀 안 줄바꿈 때문에 `2.5 / × / 5.0 / × / 2.0` 다섯 줄로
        #    보이지만 칸은 하나다 — **평면화된 텍스트로 열 수를 세면 안 된다**
        #    (2026-08-31: 9칸으로 잘못 읽고 고쳤다가 되돌렸다).
        for val in [f"배수유역 {i+1}", _comma(b["㎡"], 0),
                    f"{row.get('용량', MISSING)}({_f(vol, 1)})",
                    row.get("WLH", MISSING), "-"]:
            cell(val); right(hwp)
    _basin_rows(hwp, "배수유역 1", n, dims, skip=5)

    print("  B14 — 설치 전후 효과")
    def effect(i):
        b = bs[i]
        for val in [f"배수유역 {i+1}", r["효율"] or MISSING, _f(b.get("qs"), 4),
                    _f(b.get("qs_1단"), 4), _f(b.get("qs_2단"), 4),
                    _f(r["무처리SS"], 2), _f(r["SS_1단"], 2), _f(r["SS_2단"], 2),
                    "2단 설치"]:
            cell(val); right(hwp)
    if _basin_rows(hwp, "배수유역 1", n, effect, skip=6, has_total=True):
        down(hwp); col_begin(hwp); right(hwp, 2)           # 합계 행 (필드 덮기)
        for val in [_f(r["qs합"], 4),
                    _f(sum(b.get("qs_1단") or 0 for b in bs), 4) if r["효율"] else MISSING,
                    _f(sum(b.get("qs_2단") or 0 for b in bs), 4) if r["효율"] else MISSING]:
            cell(val); right(hwp)

    print("  B15 — 최종 혼합 (1단·2단)")
    # ⚠️ B9 와 같은 두 줄 머리행. 데이터는 3행(1단)·4행(2단) — 단계마다 앵커에서
    #    다시 잡아 **절대 오프셋**으로 간다. 이어서 down() 하면 한 줄씩 밀린다.
    if find_in_table(hwp, "순간 혼합농도(단순혼합)", skip=1):
        for off, (stage, c2, mix) in zip((2, 3),
                              [("1단", r["SS_1단"], r["혼합_1단"]),
                               ("2단", r["SS_2단"], r["혼합_2단"])]):
            find_in_table(hwp, "순간 혼합농도(단순혼합)", skip=1)
            down(hwp, off); col_begin(hwp); right(hwp)
            for val in [r["Q1"], r["C1"], _f(r["cms합"], 4), _f(c2, 2),
                        _f(_add(r["Q1"], r["cms합"]), 4), _f(mix, 2)]:
                cell(val); right(hwp)

    print(f"  수질 표 편집 종료 — 유역 {n}개 기준")

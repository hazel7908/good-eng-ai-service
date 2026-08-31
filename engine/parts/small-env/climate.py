#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기상(0721) 파트 핸들러 — W1 (2026-08-31). 순수 통계 조회 파트 (분기 없음).

규약: build_slots(v) / build_tables(hwp, v). 지식: rules/small-env/climate.md ·
명세: templates/small-env/climate.slots.md. 요약 문장 값은 vars 의 월별·연도별
데이터에서 **유도**한다 (vars 에 중복 저장 금지 — slots.md).

⚠️ build_tables 는 Windows 미검증. 특히 월별 표 앵커(강수량·일조시간 등)는
   조사내용 표 셀(L14)·10년 표 헤더에도 걸린다 — skip 값은 추정이며 Windows 확정 대상.
값 표기: vars 의 문자열을 그대로 쓴다 (연보 표기 보존 — 재포맷 금지).
"""
from hwp_util import MISSING, col_begin, down, find_in_table, right, set_cell

# 🚨 C2 앵커로 **연도(`2014`)를 쓰면 안 된다.** 빈칸 치환이 `{{기간시작}}` → `2014` 로
#    바꾸는 순간, 10년 표보다 **앞에 있는 현황조사내용 표**(`▪ 시간적 범위 - 2014~2023년`)에
#    같은 문자열이 생겨 검색이 거기를 먼저 잡는다. 실제로 조사범위·조사방법 행이 10년 표
#    데이터로 덮여 나갔다 (2026-08-31 원주 되먹임 실측).
#    ⚠️ **천안(vars 비어 있음)에서는 안 드러난다** — `기간시작` 이 `[확인 필요]` 라
#    `2014` 가 10년 표에만 있었다. 채움 경로에서만 나타나는 결함이다.
#    → 머리행 라벨을 앵커로 쓴다. `평균최고` 는 표 안에서 C2 머리행이 첫 번째다
#      (두 번째는 월별 기온 표의 행 라벨 — C3 가 skip=1 로 쓴다).
C2_ANCHOR = "평균최고"          # C2 10년 표 부머리행 라벨 (덮어쓰지 않는 칸)
C2_ROW0 = 1                     # 앵커 행에서 첫 데이터 행까지의 거리
BASE_YEARS = 10                 # 10년 표의 데이터 행 수 (고정 — 자료 없을 때 비울 만큼)


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _peak(months, biggest=True):
    """월별 리스트 → (값 문자열, '7월') — 표기 문자열은 vars 그대로 보존."""
    vals = [(_num(x), i, x) for i, x in enumerate(months) if _num(x) is not None]
    if len(vals) != 12:
        return None, None
    v = max(vals) if biggest else min(vals)
    return str(v[2]), f"{v[1] + 1}월"


def compute(v):
    yb = v.get("기상연보", {})
    r = {"관측소": yb.get("관측소", {}), "기간": yb.get("기간") or [None, None],
         "연도별": yb.get("연도별") or [], "월별": yb.get("월별", {}),
         "최다풍향": yb.get("최다풍향")}
    r["최신"] = r["연도별"][-1] if r["연도별"] else {}
    for key, big in [("강수량", True), ("습도", True), ("습도min", False),
                     ("일조", True), ("일조min", False), ("강수일", True),
                     ("풍속", True), ("풍속min", False)]:
        col = key.replace("min", "")
        val, mon = _peak(r["월별"].get(col) or [], biggest=big)
        r[f"{key}_피크"] = (val, mon)
    # 10년 평균 (종합분석 필드 재입력용 — 표기 자릿수는 Windows 실측 후 확정, 기본 2자리)
    rows = r["연도별"]
    if len(rows) == 10:
        # ⚠️ **천단위 콤마를 붙인다.** 원주 원본의 `=AVG` 캐시값이 `1,086.01`·`2,332.86`
        #    이다 — 콤마 없이 내면 강수량·일조 두 칸이 원본과 어긋난다 (2026-08-31 실측:
        #    8개 중 6개만 맞았다). 1,000 미만 값에는 영향이 없다.
        avg = lambda k: f"{sum(_num(x[k]) for x in rows) / 10:,.2f}"
        r["평균행"] = {k: avg(k) for k in ("평균", "최고", "최저", "강수량",
                                           "강수일", "습도", "풍속", "일조")}
    else:
        r["평균행"] = None
    return r


def build_slots(v):
    sa, hd = v.get("사업", {}), v.get("현황", {})
    r = compute(v)
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    latest = r["최신"]
    avg = r["평균행"] or {}
    s = {
        "사업명": g(sa, "사업명"),
        "조사시기": g(hd, "조사시기"),
        "관측소": g(r["관측소"], "표기"),
        "기간시작": r["기간"][0] or MISSING,
        "기간끝": r["기간"][1] or MISSING,
        "연보최신": r["기간"][1] or MISSING,
        "기온_평균최고": g(latest, "최고"),
        "기온_평균": g(latest, "평균"),
        "기온_평균최저": g(latest, "최저"),
        "강수량_총": g(latest, "강수량"),
        "습도_평균": g(latest, "습도"),
        "일조_총": g(latest, "일조"),
        "강수일_총": g(latest, "강수일"),
        "풍속_평균": g(latest, "풍속"),
        "최다풍향": r["최다풍향"] or MISSING,
    }
    for tok, key in [("강수량_최고", "강수량"), ("습도_최고", "습도"),
                     ("일조_최고", "일조"), ("강수일_최대", "강수일"), ("풍속_최고", "풍속")]:
        val, mon = r[f"{key}_피크"]
        s[tok] = val or MISSING
        s[tok.replace("최고", "최고월").replace("최대", "최대월")] = mon or MISSING
    for tok, key in [("습도_최저", "습도min"), ("일조_최저", "일조min"), ("풍속_최저", "풍속min")]:
        val, mon = r[f"{key}_피크"]
        s[tok] = val or MISSING
        s[tok + "월"] = mon or MISSING
    for tok, key in [("연평균기온", "평균"), ("연평균최고", "최고"), ("연평균최저", "최저"),
                     ("연강수량", "강수량"), ("연강수일", "강수일"), ("연평균습도", "습도"),
                     ("연평균풍속", "풍속"), ("연일조", "일조")]:
        s[tok] = avg.get(key, MISSING)
    return s


def build_tables(hwp, v):
    """표 편집 8종 (slots.md B절). 행 수 고정 — fit_rows 불필요."""
    r = compute(v)
    obs = r["관측소"]
    cell = lambda x: set_cell(hwp, str(x) if x not in (None, "") else MISSING)

    def _tail(vals, x):
        """월별 표 끝칸(합계·평균)을 **월별 값과 같은 소수 자릿수**로 맞춘다.

        ⚠️ 끝칸 값은 10년 표의 최신 연도 칸에서 온다. 그런데 원주 원본은 같은 값을
        두 표에서 **다른 자릿수**로 쓴다 — 10년 표 `2,297.60` ↔ 월별 표 `2,297.6`.
        그대로 옮기면 월별 표에 `2,297.60` 이 찍힌다 (2026-08-31 되먹임 실측).
        """
        if x is None:
            return None
        nd = max((len(str(m).split(".")[1]) for m in vals
                  if "." in str(m)), default=0)
        try:
            num = float(str(x).replace(",", ""))
        except ValueError:
            return x
        return f"{num:,.{nd}f}"

    print("  C1 — 관측지점 일람표")
    ilr = obs.get("일람", {})
    if find_in_table(hwp, "H(m)"):
        down(hwp)
        col_begin(hwp)
        for val in [obs.get("지점"), obs.get("이름"), ilr.get("북위"), ilr.get("동경"),
                    ilr.get("H"), ilr.get("Hb"), ilr.get("ht"), ilr.get("ha"), ilr.get("hr")]:
            cell(val)
            right(hwp)

    print("  C2 — 기상종합분석 10년 표 (+평균행 필드 덮기)")
    # 🚨 **자료가 없다고 건너뛰면 기준 사업(원주) 값이 그대로 실린다.** 천안 첫 생성에서
    #    18.67·13.45·1,391.7·2,297.6·63.94 가 남았다 (수질 하천일람과 같은 부류).
    #    행 수는 고정이므로 10년치를 [확인 필요] 로 채운다.
    rows = r["연도별"] or [{}] * BASE_YEARS
    if find_in_table(hwp, C2_ANCHOR):
        # ⚠️ 행마다 앵커에서 다시 잡아 **절대 오프셋**으로 간다 — 행이 9칸(A~I)이라
        #    마지막 칸의 `right()` 가 이미 다음 행 첫 칸으로 넘어가서, 이어서 `down()`
        #    하면 한 행씩 건너뛴다 (2026-08-31 실측).
        def write_row(off, vals):
            if not find_in_table(hwp, C2_ANCHOR):
                return
            down(hwp, C2_ROW0 + off)
            col_begin(hwp)
            for val in vals:
                cell(val)
                right(hwp)

        for i, y in enumerate(rows):
            write_row(i, [y.get("연도"), y.get("평균"), y.get("최고"), y.get("최저"),
                          y.get("강수량"), y.get("강수일"), y.get("습도"),
                          y.get("풍속"), y.get("일조")])

        # 평균 행 — `=AVG` 필드라 기준 사업 값이 캐시돼 있다. 자료가 없어도 반드시 덮는다.
        avgrow = r["평균행"] or {}
        if find_in_table(hwp, C2_ANCHOR):
            down(hwp, C2_ROW0 + len(rows))   # 데이터 10행 다음 = 평균 행
            col_begin(hwp)
            right(hwp)                       # '평 균' 라벨 셀 건너뜀
            for k in ("평균", "최고", "최저", "강수량", "강수일", "습도", "풍속", "일조"):
                cell(avgrow.get(k))
                right(hwp)

    print("  C3 — 월별 기온 (3행)")
    mm = r["월별"]
    # ⚠️ skip=1 추정: '평균최고' 는 10년 표 헤더에 먼저 나온다
    if find_in_table(hwp, "평균최고", skip=1):          # 자료 없으면 비운다 (원주 값 잔존 방지)
        for i, key in enumerate(["평균최고", "평균", "평균최저"]):
            find_in_table(hwp, "평균최고", skip=1)   # C2 와 같은 이유로 절대 오프셋
            down(hwp, i)
            col_begin(hwp)
            # 커서 = 행 라벨 셀 (첫 행은 앵커 자체) → 값 13개(12개월+평균)를 오른쪽으로
            tail = r["최신"].get({"평균최고": "최고", "평균": "평균", "평균최저": "최저"}[key])
            series = list(mm.get(key) or [None] * 12)
            for val in series + [_tail(series, tail)]:
                right(hwp)
                cell(val)

    # 월별 단일행 표 5종 — 앵커 skip 은 전부 추정 (조사내용 표 L14 셀에 같은 낱말)
    for label, key, skip, tailkey in [
        ("강수량", "강수량", 2, "강수량"), ("평균습도", "습도", 1, "습도"),
        ("일조시간", "일조", 2, "일조"), ("강수일", "강수일", 1, "강수일"),
        ("평균풍속", "풍속", 1, "풍속"),
    ]:
        vals = mm.get(key) or [None] * 12                # 없으면 비운다
        print(f"  월별 {label} (skip={skip})")
        if find_in_table(hwp, label, skip=skip):
            for val in list(vals) + [_tail(vals, r["최신"].get(tailkey))]:
                right(hwp)
                cell(val)

    print("  기상 표 편집 종료")

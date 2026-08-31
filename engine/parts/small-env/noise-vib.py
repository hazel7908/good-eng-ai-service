#!/usr/bin/env python3
"""소음·진동(0727) 파트 핸들러 — 2026-08-31 R1 리팩터로 generate.py 에서 분리 (로직 불변).

규약: build_slots(v) / build_tables(hwp, v) 를 내보낸다 (generate.load_part_handlers).
지식 출처: rules/small-env/noise-vib.md · 빈칸 명세: templates/small-env/noise-vib.slots.md
"""
from calc import (attenuate, composite_noise, composite_vib, distance_for_level,
                  mitigation_series, sound_panel_reduction, target, verdict)
from hwp_util import (MISSING, SHADE, _fmt, _pp_label, append_rows, bold_row,
                      clone_para, col_begin, delete_range, down, fill_row,
                      find_in_table, right, set_bold, set_cell, shade_row)

WORK_HOURS = 8          # 표 19 주석 `주) 일 작업시간 : 8시간 기준` (5/5 확인)


def _per_hour(daily):
    """시간당 작업량 = 일 작업량 ÷ 8. 원주 201.22→25.15 · 괴산 190→23.75 · 천안 44.10→5.51"""
    if daily is None:
        return MISSING
    return f"{float(daily) / WORK_HOURS:.2f}"


def _expanded(ga):
    """저감 확장절(2 분산투입 · 3 방음판넬 · 4 최종 저감대책 + 표 29)을 두는가.

    rule §4-1 — 상회 0건이면 통째로 빠진다 (여주·천안). 괴산은 0건인데도 뒀다.
    옛 키 `최종저감대책표_포함` 을 그대로 받는다 — 이름이 표 하나만 가리켜 오해를 샀다.
    """
    if "저감_확장절_포함" in ga:
        return ga["저감_확장절_포함"]
    return ga.get("최종저감대책표_포함", True)


def _dist_list(ye, kind, default):
    """이격거리별 표(21·24)의 구분 거리. **사업마다 다르다** (rule §3-2).

    청양은 150 이 빠지고 400 이 들어가며 표 24 첫 칸이 7.5(=r₀) 다.
    둘째 칸도 101 ↔ 100 이 2:2 로 갈려 규칙이 없다 → vars 로 준다.
    """
    v = (ye.get("이격거리표") or {}).get(kind)
    return list(v) if v else default


def _pred_sentence(pts, equip):
    """예측소음도 결과 서술 — rule §5-2.

    상회 지점이 없으면 `전 지점에서 …`, 있으면 그 지점을 앞에 밝힌다.
    원주(P-1 상회) → `P-1 지점을 제외한 전 지점에서 …` / 괴산·천안(0건) → `전 지점에서 …`
    """
    c = composite_noise(equip)
    over = [p for p in pts
            if attenuate(c, p["이격거리_m"], "noise") > target(p["종류"], "noise")]
    tail = "전 지점에서 기준치를 만족하는 것으로 예측되었다"
    if not over:
        return tail
    names = "·".join(f'P-{p["번호"]}' for p in over)
    return f"{names} 지점을 제외한 {tail}"


def slots_noise_vib(v):
    """vars → 베이스 문서 빈칸 채울 값 (텍스트 치환분).

    키 이름은 templates/small-env/noise-vib.slots.md 와 일치해야 한다.
    """
    hd, gi, ye, ga = v["현황"], v["기준"], v["예측"], v["저감"]
    pts = ye["지점"]
    equip = ye["투입장비"]
    nearest = min(p["이격거리_m"] for p in pts)

    # rule §4-3 — 도입 문장과 삽도 캡션이 함께 바뀐다
    borrowed = hd["측정자료_출처유형"] != "자체측정"

    return {
        "사업명": v["사업"]["사업명"],
        "조사시기": _fmt(hd["조사시기"]),
        "측정일시": _fmt(hd["측정일시"]),
        "측정지점_주소": _fmt(hd["측정지점"]["주소"]),
        # rule §2-3 — 단위 표기가 갈린다. `25m` 은 괴산 1건뿐이고 원주·천안은 `250`/`350`.
        # 코드에 `m` 을 박지 않는다. 붙여야 하면 vars 에서 표기를 준다.
        "측정지점_이격거리": (hd["측정지점"].get("이격거리_표기")
                        or str(hd["측정지점"]["이격거리_m"])),
        "측정지점_비고": _fmt(hd["측정지점"]["비고"]),

        # 서술문은 소수 1자리 (`49.0dB(A)`), 표 셀은 원값 (`49`) — 골든셋 2/2 일치
        "소음_주간평균": f'{hd["소음"]["주간_평균"]:.1f}',
        "소음_야간평균": f'{hd["소음"]["야간_평균"]:.1f}',
        "진동_주간평균": f'{hd["진동"]["주간_평균"]:.1f}',
        "진동_심야평균": f'{hd["진동"]["심야_평균"]:.1f}',

        "소음환경기준_지역": gi["소음환경기준_지역"],
        "소음환경기준_주간": gi["소음환경기준_주간"],
        "소음환경기준_야간": gi["소음환경기준_야간"],
        "생활진동규제_지역": gi["생활진동규제_지역"],
        "생활진동규제_주간": gi["생활진동규제_주간"],
        "생활진동규제_심야": gi["생활진동규제_심야"],

        "측정결과_도입": ("측정자료를 검토한 결과" if borrowed
                       else "사업계획지구 주변 1개 지점의 소음 측정 결과"),
        "측정지점도_캡션": ("소음\u2024진동 측정지점도(주변 사업지 측정자료)" if borrowed
                        else "소음\u2024진동 측정지점도"),

        "진동측정결과_도입": ("측정자료를 검토한 결과" if borrowed
                         else "사업계획지구 주변 1개 지점의 진동 측정 결과"),
        "현황_자료유형": "문헌자료" if borrowed else "측정자료",
        "현황_소제목_접미": "(문헌자료)" if borrowed else "",
        "측정지점_도입": (
            "본 사업시행으로 인한 영향을 파악하기 위하여 인근사업지의 측정자료를 인용하였다."
            if borrowed else
            "본 사업시행으로 인하여 직·간접적인 영향이 예상되는 지역 중 사업계획지구와 "
            "가장 인접한 1개 지점을 선정하여 소음·진동 측정을 실시하였다."),

        # rule §5-2 — 상회 지점이 있으면 그 지점을 앞에 밝힌다 (원주 P-1. 3/3 일관)
        "예측소음도_결과서술": _pred_sentence(pts, equip),

        "예측지점_수": len(pts),
        "최인접_이격거리": nearest,
        "공종": ye["공종"],
        "일작업량": _fmt(ye.get("일작업량_㎥")),
        # 표 19 — `주) 일 작업시간 : 8시간 기준` (천안 대기질편에서 확인, 원주 25.15 검산 일치)
        "시간당작업량": _per_hour(ye.get("일작업량_㎥")),
        # rule §4-1 — 확장절이 없는 사업은 1)절 제목에 `필요시` 가 붙는다
        "저감1_접두": "" if _expanded(ga) else "필요시 ",

        # rule §5-1 — 상회 여부로 갈리지 않는다. 자동 판정도 하드코딩도 하지 않는다.
        # 기본값은 베이스 문서(원주) 값 = 2/5. `미미할` 은 괴산 1건뿐이다.
        "소음영향_서술": ye.get("소음영향_서술", "있을"),
        "진동영향_서술": ye.get("진동영향_서술", "없을"),

        # rule §4-2 — 수치 65 는 5/5 고정, 지역 문자만 갈린다
        "목표기준_지역문자": ga["목표기준_지역문자"],
        "목표소음_주거": target("R", "noise"),
        "목표소음_축사": target("L", "noise"),
        "목표진동_주거": target("R", "vib"),
        "목표진동_축사": target("L", "vib"),
    }


# 원주 베이스 문서에 표시가 걸려 있는 행 — 여기서 옮긴다
BASE_MARK = {"표9": "나", "표10": "가", "표11": "가"}


def legal_tables_noise_vib(hwp, v):
    """법령표 9·10·11 의 해당 행 표시 (rule §1).

    ⚠️ 표 9 는 **볼드**, 표 10·11 은 **음영**이다 — 서식이 서로 다르다.
    그리고 표 9 는 소음환경기준("가"~"라"), 표 10·11 은 생활소음/진동 규제기준(가·나)로
    **분류 체계가 다르다.** 하나로 통일하면 틀린다 (`common.md`).
    """
    gi, ga = v["기준"], v["저감"]
    z9 = gi["소음환경기준_지역"]                                   # "가"~"라"
    z11 = gi["생활진동규제_지역"].strip()[:1]                       # '가' | '나'
    z10 = (gi.get("생활소음규제_지역") or gi["생활진동규제_지역"]).strip()[:1]

    print(f"  법령표 — 표9 “{z9}” · 표10 {z10} · 표11 {z11}")

    # 표 9 소음환경기준 — 일반지역 블록. 도로변지역에도 같은 문자열이 있으나
    # 문서 순서상 일반지역이 먼저라 skip 이 필요 없다.
    if z9 != BASE_MARK["표9"]:
        bold_row(hwp, f'"{BASE_MARK["표9"]}"지역', 3, False)
        bold_row(hwp, f'"{z9}"지역', 3, True)
    else:
        print("    표9 — 베이스와 같아 건너뜀")

    # 표 10 생활소음 — 해당 지역 블록의 `공사장` 행에 음영 (4칸).
    # `공사장` 은 표 10 안에 두 번(가 블록 · 나 블록) 나오고 그 앞 표에는 없다.
    if z10 != BASE_MARK["표10"]:
        shade_row(hwp, "공사장", 4, None, skip=0 if BASE_MARK["표10"] == "가" else 1)
        shade_row(hwp, "공사장", 4, SHADE, skip=0 if z10 == "가" else 1)
    else:
        print("    표10 — 베이스와 같아 건너뜀")

    # 표 10·11 지역 라벨 볼드 — 베이스(원주)에만 있다. 괴산·옥천 정답은 **보통**이다 (2:1).
    # 텍스트 비교로는 안 잡히는 서식이라 그동안 EXTRA 로 남아 있었다.
    # skip 으로 표 10/11 을 가르면 어긋난다 — 표마다 구분되는 앵커를 쓴다.
    # 표 10 은 셀 안에서 `녹지지역,` 뒤에 줄이 바뀌고, 표 11 은 한 줄로 이어진다.
    if not ga.get("법령표_라벨볼드", False):
        for anchor in ("가. 주거지역, 녹지지역,", "가. 주거지역, 녹지지역, 관리지역"):
            if find_in_table(hwp, anchor):
                set_bold(hwp, False)

    # 표 11 생활진동 — 해당 행 전체(3칸)에 음영.
    # 앵커가 표 10 에도 있어 skip=1 로 표 11 을 잡는다.
    if z11 != BASE_MARK["표11"]:
        old = "가. 주거지역" if BASE_MARK["표11"] == "가" else "나. 그 밖의 지역"
        new = "가. 주거지역" if z11 == "가" else "나. 그 밖의 지역"
        shade_row(hwp, old, 3, None, skip=1)
        shade_row(hwp, new, 3, SHADE, skip=1)
    else:
        print("    표11 — 베이스와 같아 건너뜀")


def tables_noise_vib(hwp, v):
    """표 편집. 표 인덱스·구조는 rules/small-env/noise-vib.md §1 참조."""
    hd, ye, ga = v["현황"], v["예측"], v["저감"]
    pts = ye["지점"]
    equip = ye["투입장비"]
    c_noise, c_vib = composite_noise(equip), composite_vib(equip)
    n = len(pts)
    BASE_ROWS = 5           # 원주 베이스 문서의 PP 행 수
    lbl_pt = _pp_label(ye, "지점표")      # 표 14
    lbl_pr = _pp_label(ye, "예측표")      # 표 22 · 25 · 29

    print("  표 6 — 소음측정결과")
    if find_in_table(hwp, "N - 1"):
        s = hd["소음"]
        for x in s["주간"] + [s["주간_평균"]] + s["야간"] + [s["야간_평균"]]:
            right(hwp); set_cell(hwp, x)

    print("  표 7 — 진동측정결과")
    # skip=1: 표 5 의 'N·V - 1' 안에 있는 'V - 1' 을 건너뛴다
    if find_in_table(hwp, "V - 1", skip=1):
        t = hd["진동"]
        for x in t["주간"] + [t["주간_평균"]] + t["심야"] + [t["심야_평균"]]:
            right(hwp); set_cell(hwp, x)

    # rule §4-3 — 인용 케이스는 표 5·6·7 아래에 출처 주석이 붙는다. 베이스(원주)에는 없다.
    cite = hd.get("인용출처")
    if hd["측정자료_출처유형"] != "자체측정" and cite:
        note = f"자) {cite}"
        print(f"  출처 주석 3곳 — {note[:40]}")
        REF = "자) 건설기계류 소음특성, 국립환경과학원. 2003"
        # 빈칸은 [2/4] 에서 이미 치환됐다 — 삽도 캡션은 치환된 문자열로 잡는다
        for dst in ("(나) 측정일시", "2) 진동", "측정지점도(주변 사업지"):
            clone_para(hwp, REF, dst, note)

    legal_tables_noise_vib(hwp, v)

    # 표 5 측정지점 지점명 — 표 7 검색(`V - 1` skip=1)이 끝난 뒤에 바꾼다.
    # 인풋은 세 사업 다 `NV - 1` 인데 원주·괴산 정답은 `N·V - 1`, 청양은 `NV - 1` 이다.
    # 작성자 판단이라 인풋에서 유도할 수 없다 → vars (rule §2-3)
    name = hd["측정지점"].get("지점명")
    if name and find_in_table(hwp, "N·V - 1"):
        print(f"  표 5 — 측정지점명 → {name}")
        set_cell(hwp, name)

    print("  표 14 — 영향예측지점")
    if find_in_table(hwp, "XTM"):
        append_rows(hwp, "XTM", BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            # XTM/YTM — 대기질편(0722)에 실좌표가 있으면 vars 로 온다 (rule §2-4).
            fill_row(hwp, [lbl_pt.format(n=p["번호"]), p["이름"], p["방향"],
                           p["이격거리_m"], p.get("XTM") or "-",
                           p.get("YTM") or "-", _fmt(p["비고"])])

    print("  표 21 — 이격거리별 소음도")
    if find_in_table(hwp, "구분(m)"):
        # rule §3-2 — 첫 칸은 목표기준 도달거리(4/4). 둘째 칸부터는 규칙이 없다
        # (101↔100 이 2:2, 청양은 150 대신 400). vars 로 주지 않으면 아래 기본값.
        first = round(distance_for_level(target("R", "noise"), c_noise))
        second = round(distance_for_level(60, c_noise))
        ds = _dist_list(ye, "소음", [first, second, 150, 200, 300, 500, 1000])
        for d in ds:
            right(hwp); set_cell(hwp, d)
        down(hwp); col_begin(hwp); set_cell(hwp, "소음도(dB(A))")
        for d in ds:
            right(hwp); set_cell(hwp, round(attenuate(c_noise, d, "noise"), 1))

    print("  표 22 — 정온시설 예측소음도")
    if find_in_table(hwp, "예측소음도"):
        append_rows(hwp, "예측소음도", BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            pred = round(attenuate(c_noise, p["이격거리_m"], "noise"), 1)
            lim = target(p["종류"], "noise")
            fill_row(hwp, [lbl_pr.format(n=p["번호"]), p["이름"], p["방향"],
                           p["이격거리_m"], pred, lim, verdict(pred, lim)])

    print("  표 24 — 이격거리별 진동도")
    # ⚠️ '진동레벨(dB(V))' 로 찾으면 표 23(합성진동레벨)이 먼저 걸린다 — PoC 오류
    if find_in_table(hwp, "구분(m)", skip=1):
        # 구분 행도 덮어쓴다 — 이전에는 베이스 문서(원주) 값을 그대로 뒀다.
        dv = _dist_list(ye, "진동", [50, 100, 150, 200, 300, 500, 1000])
        for d in dv:
            right(hwp); set_cell(hwp, d)
        down(hwp); col_begin(hwp); set_cell(hwp, "진동레벨(dB(V))")
        for d in dv:
            right(hwp); set_cell(hwp, round(attenuate(c_vib, d, "vib"), 1))

    print("  표 25 — 정온시설 예측진동도")
    if find_in_table(hwp, "예측진동도"):
        append_rows(hwp, "예측진동도", BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            pred = round(attenuate(c_vib, p["이격거리_m"], "vib"), 1)
            lim = target(p["종류"], "vib")
            fill_row(hwp, [lbl_pr.format(n=p["번호"]), p["이름"], p["방향"],
                           p["이격거리_m"], pred, lim, verdict(pred, lim)])

    if not _expanded(ga):
        # rule §4-1 — 없어지는 것은 표 29 하나가 아니다. 2)·3)·4) 절이 통째로 빠진다.
        print("  저감 확장절 제거 — 2) 분산투입 · 3) 방음판넬 · 4) 최종 저감대책 + 표 29")
        delete_range(hwp, "2) 장비의 분산투입", "(다) 진동")
        return

    # 표 26 환경보전목표 — 행 이름이 갈린다 (rule §2-6).
    # `주거시설` 은 목표기준 문장에도 나와 찾기/바꾸기로는 잡을 수 없다 → 셀로 간다.
    r_lbl = ga.get("환경보전목표_주거라벨", "주거시설")
    l_lbl = ga.get("환경보전목표_축사라벨", "축사")
    if (r_lbl, l_lbl) != ("주거시설", "축사"):
        print(f"  표 26 — 환경보전목표 행 이름 → {r_lbl} · {l_lbl}")
        # ⚠️ 헤더(`환경보전목표`)에서 내려가면 병합 셀 때문에 자리가 어긋난다.
        #    `주거시설` 셀을 직접 잡는다 — 목표기준 문장의 `주거시설` 은 표 밖이라 걸리지 않는다.
        if find_in_table(hwp, "주거시설"):
            set_cell(hwp, r_lbl)
            down(hwp)
            set_cell(hwp, l_lbl)

    print("  표 29 — 최종 저감대책 후 예측소음도")
    sub = ga["분산투입_감산량"]
    path = ga.get("반올림_경로", "A")          # rule §3-3 — 1:1 이라 vars 로 준다
    show_sub = ga.get("분산후_감산량_병기", False)   # 청양은 `44.9(-4.9)` 로 쓴다

    # ③ 가설방음판넬 — ②까지 해도 목표를 못 맞추는 지점이 하나라도 있으면 열이 생긴다
    series = [mitigation_series(p["이격거리_m"], equip, sub, path) for p in pts]
    limits = [float(target(p["종류"], "noise")) for p in pts]
    panels = [sound_panel_reduction(s[2], l) for s, l in zip(series, limits)]
    has_panel = any(x is not None for x in panels)

    if find_in_table(hwp, "최종예측치"):
        if has_panel:
            # 최종예측치 열 **왼쪽**에 열을 끼워 넣는다 (rule §3-3 — 청양만 10칸)
            print(f"    가설방음판넬 열 추가 — 상회 {sum(x is not None for x in panels)}지점")
            # ⚠️ 최종예측치 열 **왼쪽에** 넣으면 그 열의 음영을 물려받는다.
            #    분산후 열로 옮겨 **오른쪽에** 넣어야 서식이 깨끗하다.
            hwp.HAction.Run("TableLeftCell")
            hwp.HAction.Run("TableInsertRightColumn")
            find_in_table(hwp, "최종예측치")
            hwp.HAction.Run("TableLeftCell")
            set_cell(hwp, "가설방음\r\n판넬")

        append_rows(hwp, "최종예측치", BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            b, low, disp = series[i]
            lim, panel = limits[i], panels[i]
            d1 = round(disp, 1)
            fin = round(d1 - panel, 2) if panel is not None else d1
            row = [lbl_pr.format(n=p["번호"]), p["이름"], p["이격거리_m"],
                   round(b, 1), round(low, 1),
                   f"{d1}(-{sub})" if show_sub else d1]
            if has_panel:
                row.append(f"-{panel}" if panel is not None else "-")
            row += [fin, lim, verdict(fin, lim)]
            fill_row(hwp, row)




build_slots = slots_noise_vib
build_tables = tables_noise_vib

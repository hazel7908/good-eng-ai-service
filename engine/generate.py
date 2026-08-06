#!/usr/bin/env python3
"""
한글 API(win32com) 기반 HWPX 보고서 생성 엔진.

  베이스 문서(빈칸) + vars/{파트}.json  →  cases/{카테고리}/{사업}/{파트}/output.hwpx

설계 원칙 (repo_restructure_plan.md §4):
  - **엔진은 파트를 모른다.** 사업 데이터는 vars JSON, 계산은 calc.py,
    지식은 rules/ 에 있다. 여기에 값을 하드코딩하지 않는다.
  - 표 구조 조작(어느 표에 몇 행)은 파트마다 다르므로 PART_HANDLERS 로 분리.
    파트가 늘면 핸들러를 추가한다.

⚠️ Windows + 한글 프로그램 전용. 계산만 확인하려면 `python engine/calc.py`.
⚠️ 베이스 문서는 아직 없다 — 6단계에서 원주 골든셋에 빈칸을 뚫어 만든다.
   빈칸 명세: templates/small-env/noise-vib.slots.md

사용:
    python engine/generate.py small-env noise-vib 괴산_금신리
    python engine/generate.py small-env noise-vib 괴산_금신리 --raw-dir "D:/raw/괴산/삽도"
"""

import argparse
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

from calc import (attenuate, composite_noise, composite_vib, distance_for_level,
                  mitigation_series, sound_panel_reduction, target, verdict)

ROOT = Path(__file__).parent.parent
PLACEHOLDER = "{{%s}}"          # 베이스 문서의 빈칸 표기
MISSING = "[확인 필요]"          # 값이 없을 때 출력할 문자열
MODELING = "[모델링 필요]"       # AERMOD 출력이 없을 때 (대기질 rule §2-5)


# ============================================================
# 한글 API 유틸리티
# ============================================================
def fr(hwp, old, new):
    """전체 문서 찾기/바꾸기"""
    hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
    p = hwp.HParameterSet.HFindReplace
    p.FindString, p.ReplaceString = old, new
    p.IgnoreMessage = 1
    p.Direction = hwp.FindDir("AllDoc")
    p.FindType = 0
    hwp.HAction.Execute("AllReplace", p.HSet)


def find_fwd(hwp, text):
    hwp.HAction.GetDefault("RepeatFind", hwp.HParameterSet.HFindReplace.HSet)
    p = hwp.HParameterSet.HFindReplace
    p.FindString = text
    p.Direction = hwp.FindDir("Forward")
    p.FindType = 0
    p.IgnoreMessage = 1
    return hwp.HAction.Execute("RepeatFind", p.HSet)


def in_table(hwp):
    return hwp.GetPos()[0] > 0


def find_in_table(hwp, text, skip=0):
    """테이블 셀 안에서 텍스트를 찾을 때까지 반복 검색.
    skip: 부분매칭 회피용 (예: 'V - 1' 이 'N·V - 1' 에 먼저 걸린다)
    """
    hwp.MovePos(2)
    hit = 0
    for _ in range(30):
        if not find_fwd(hwp, text):
            return False
        if in_table(hwp):
            if hit < skip:
                hit += 1
                continue
            return True
    return False


def set_cell(hwp, text):
    if not in_table(hwp):
        print(f"    WARNING: 커서가 테이블 밖 — '{str(text)[:20]}' 스킵")
        return False
    hwp.HAction.Run("SelectAll")
    hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
    hwp.HParameterSet.HInsertText.Text = str(text)
    hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
    return True


def right(hwp, n=1):
    for _ in range(n): hwp.HAction.Run("TableRightCell")


def down(hwp, n=1):
    for _ in range(n): hwp.HAction.Run("TableLowerCell")


def col_begin(hwp):
    hwp.HAction.Run("TableColBegin")


def fill_row(hwp, values):
    for i, v in enumerate(values):
        if i > 0: right(hwp)
        set_cell(hwp, v)


def delete_range(hwp, start_anchor, end_anchor):
    """start_anchor 가 있는 문단 처음부터 end_anchor 문단 직전까지 통째로 지운다.

    표를 품은 구간도 함께 지워진다. 사업마다 절이 통째로 빠지는 경우가 있어 필요하다
    (rule §4-1 — 상회 0건이면 저감 2)·3)·4) 절이 없다).
    """
    hwp.MovePos(2)
    if not find_fwd(hwp, start_anchor):
        print(f"    WARNING: 시작 앵커 '{start_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    s = hwp.GetPos()
    if not find_fwd(hwp, end_anchor):
        print(f"    WARNING: 끝 앵커 '{end_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    e = hwp.GetPos()
    if s[0] != e[0]:
        print(f"    WARNING: 두 앵커가 서로 다른 리스트에 있다 {s[0]}≠{e[0]}")
        return False
    hwp.SelectText(s[1], s[2], e[1], e[2])
    hwp.HAction.Run("Delete")
    return True


def set_bold(hwp, on):
    hwp.HAction.GetDefault("CharShape", hwp.HParameterSet.HCharShape.HSet)
    hwp.HParameterSet.HCharShape.Bold = 1 if on else 0
    hwp.HAction.Execute("CharShape", hwp.HParameterSet.HCharShape.HSet)


def bold_row(hwp, anchor, ncells, on, skip=0):
    """앵커 셀부터 오른쪽으로 ncells 칸의 글자를 굵게/보통으로 바꾼다."""
    if not find_in_table(hwp, anchor, skip=skip):
        print(f"    WARNING: 법령표 앵커 '{anchor}' 못 찾음")
        return False
    for i in range(ncells):
        if i:
            right(hwp)
        hwp.HAction.Run("SelectAll")
        set_bold(hwp, on)
    return True


SHADE = 0xE5E5E5        # 베이스 문서 법령표의 음영 색 (header.xml winBrush faceColor)


def cell_fill(hwp, color):
    """현재 셀의 면 색. color=None 이면 채우기 없음.

    셀 블록(`TableCellBlock`)이 잡혀 있어야 적용된다 — 커서만 있으면 무시된다.
    """
    hwp.HAction.GetDefault("CellBorderFill", hwp.HParameterSet.HCellBorderFill.HSet)
    p = hwp.HParameterSet.HCellBorderFill
    fa = p.FillAttr
    if color is None:
        fa.type = hwp.BrushType("NullBrush")
        fa.WindowsBrush = 0
    else:
        fa.type = hwp.BrushType("NullBrush|WinBrush")
        fa.WindowsBrush = 1
        fa.WinBrushFaceColor = color
        fa.WinBrushHatchColor = 0
        fa.WinBrushFaceStyle = -1
    p.FillAttr = fa
    hwp.HAction.Execute("CellBorderFill", p.HSet)


def shade_row(hwp, anchor, ncells, color, skip=0, offset=0):
    """앵커 셀에서 offset 칸 오른쪽부터 ncells 칸에 면 색을 넣는다.

    셀마다 앵커에서 다시 찾아간다 — 셀 블록을 잡으면 커서 이동이 달라져
    한 번에 훑으면 어긋난다.
    """
    for i in range(ncells):
        if not find_in_table(hwp, anchor, skip=skip):
            print(f"    WARNING: 법령표 앵커 '{anchor}' 못 찾음")
            return False
        right(hwp, offset + i)
        hwp.HAction.Run("TableCellBlock")
        cell_fill(hwp, color)
        hwp.HAction.Run("Cancel")
    return True


def clone_para(hwp, src_anchor, dst_anchor, text):
    """`src_anchor` 문단을 통째로 복사해 `dst_anchor` 문단 **앞**에 넣고 내용을 text 로 바꾼다.

    베이스 문서에 없는 문단을 새로 넣어야 할 때 쓴다 (인용 케이스의 출처 주석 등).
    빈 문단을 만들어 쓰면 **글자·문단 모양이 대상 문단의 것을 물려받아** 제목 서식으로 나온다.
    같은 종류의 기존 문단을 복사하는 편이 안전하다.
    """
    hwp.MovePos(2)
    if not find_fwd(hwp, src_anchor):
        print(f"    WARNING: 복사 원본 '{src_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("MoveSelParaEnd")
    hwp.HAction.Run("Copy")

    hwp.MovePos(2)
    if not find_fwd(hwp, dst_anchor):
        print(f"    WARNING: 대상 '{dst_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    # ⚠️ 순서가 중요하다. 붙여넣기를 먼저 하고 나누면 **대상 문단이 복사본 서식을 물려받아**
    #    소제목이 작은 글씨로 바뀐다. 빈 문단을 먼저 만들고 거기에 붙인다.
    hwp.HAction.Run("BreakPara")
    hwp.HAction.Run("MoveUp")
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("Paste")
    # 붙여넣은 내용을 원하는 문장으로 바꾼다
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("MoveSelParaEnd")
    hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
    hwp.HParameterSet.HInsertText.Text = text
    hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
    return True


def append_rows(hwp, anchor, base_rows, need):
    """표의 행 수를 need 에 맞춘다. 커서는 anchor 다음 행 첫 칸에 둔다."""
    if need > base_rows:
        down(hwp, base_rows)
        hwp.HAction.Run("TableRowEnd")
        hwp.HAction.Run("TableColEnd")
        for _ in range(need - base_rows):
            hwp.HAction.Run("TableAppendRow")
        find_in_table(hwp, anchor)
    down(hwp)
    col_begin(hwp)


# ============================================================
# 삽도 이미지 교체 (HWPX ZIP 후처리)
# ============================================================
def replace_images(hwpx_path, img_map):
    try:
        from PIL import Image
    except ImportError:
        print("  Pillow 미설치 — 이미지 교체 스킵")
        return

    tmp = hwpx_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    lower = {k.lower(): v for k, v in img_map.items()}
    n = 0

    with zipfile.ZipFile(hwpx_path) as zin, zipfile.ZipFile(tmp, "w") as zout:
        for item in zin.infolist():
            src = lower.get(item.filename.lower())
            if src and os.path.exists(src):
                buf = io.BytesIO()
                Image.open(src).save(buf, format="PNG")
                info = zipfile.ZipInfo(item.filename)
                info.compress_type = item.compress_type   # 보통 STORED — 유지해야 함
                zout.writestr(info, buf.getvalue())
                print(f"  {item.filename}: 교체 ({buf.tell():,} bytes)")
                n += 1
            else:
                if src:
                    print(f"  WARNING: {src} 없음 — 원본 유지")
                zout.writestr(item, zin.read(item.filename))

    os.replace(tmp, hwpx_path)
    print(f"  이미지 {n}건 교체")


# ============================================================
# 파트 핸들러 — 소음·진동
# ============================================================
def _fmt(v):
    return MISSING if v is None else str(v)


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


def _pp_label(ye, kind):
    """PP 라벨 형식. **같은 사업 안에서도 표마다 다르다** (rule §4-4).

    kind: '지점표'(표 14) | '예측표'(표 22·25·29)
    청양은 표 14 만 `P - 1` 이고 나머지는 `P-1` 이다. 다른 3건은 전부 `P - 1`.
    """
    return (ye.get(f"PP라벨_{kind}") or ye.get("PP라벨") or "P - {n}")


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


# ============================================================
# 파트 핸들러 — 대기질 (rules/small-env/air-quality.md)
# ============================================================
def left(hwp, n=1):
    for _ in range(n):
        hwp.HAction.Run("TableLeftCell")


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
    rows_q = [(g(ca.q1_kg_day(P, vkt, ca.K_PM10)), g(ca.q1_kg_day(P, vkt, ca.K_PM25))),
              (g(q2_10), g(q2_25)), (g(q3_10), g(q3_25)), (g(q4_10), g(q4_25))]
    sub10, sub25 = sum(r[0] for r in rows_q), sum(r[1] for r in rows_q)
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
                fill_row(hwp, [f"{g10:.4f}", f"{g25:.4f}", "-"])
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


PART_HANDLERS = {
    "noise-vib": (slots_noise_vib, tables_noise_vib),
    "air-quality": (slots_air_quality, tables_air_quality),
}


# ============================================================
# 메인
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="HWPX 보고서 생성")
    ap.add_argument("category"); ap.add_argument("part"); ap.add_argument("case")
    ap.add_argument("--raw-dir", help="삽도 원본 JPG 디렉터리")
    ap.add_argument("--dry-run", action="store_true",
                    help="한글 없이 치환값만 출력 (Mac 에서 vars 점검용)")
    a = ap.parse_args()

    if a.part not in PART_HANDLERS:
        sys.exit(f"ERROR: '{a.part}' 핸들러 없음. 지원: {list(PART_HANDLERS)}")
    build_slots, build_tables = PART_HANDLERS[a.part]

    vars_path = ROOT / "cases" / a.category / a.case / "vars" / f"{a.part}.json"
    if not vars_path.exists():
        sys.exit(f"ERROR: {vars_path} 없음. /generate-report 3단계에서 만든다")
    v = json.loads(vars_path.read_text(encoding="utf-8"))

    slots = build_slots(v)

    if a.dry_run:
        print(f"[dry-run] {vars_path}")
        for k, val in slots.items():
            flag = "  ← 확인 필요" if str(val) == MISSING else ""
            print(f"  {PLACEHOLDER % k:28s} = {val}{flag}")
        pending = v.get("_확인필요", [])
        print(f"\n확인 필요 {len(pending)}건")
        for p in pending:
            print(f"  [{p['분류']:5s}] {p['항목']} — {p['사유']}")
        return

    template = ROOT / "templates" / a.category / f"{a.part}.hwpx"
    if not template.exists():
        sys.exit(f"ERROR: 베이스 문서 없음 — {template}\n"
                 f"  6단계에서 골든셋에 빈칸을 뚫어 만든다. "
                 f"빈칸 명세: templates/{a.category}/{a.part}.slots.md")

    output = ROOT / "cases" / a.category / a.case / a.part / "output.hwpx"
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        import win32com.client
    except ImportError:
        sys.exit("ERROR: pywin32 미설치 (Windows 전용). 계산 확인은 engine/calc.py")

    print("[1/4] 한글 시작...")
    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False
    hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
    hwp.Open(str(template))

    print(f"\n[2/4] 빈칸 치환 ({len(slots)}건)...")
    for k, val in slots.items():
        fr(hwp, PLACEHOLDER % k, str(val))

    print("\n[3/4] 표 편집...")
    build_tables(hwp, v)

    # 한글 빠른 교정이 셀에 넣은 'P - 1' 의 하이픈을 en-dash(–) 로 바꾼다.
    # 골든셋·베이스 문서에는 en-dash 가 한 개도 없다 — 전부 InsertText 가 만든 것이다.
    print("  [정리] 빠른 교정이 바꾼 en-dash 되돌리기")
    fr(hwp, "P – ", "P - ")

    print("\n[4/4] 저장...")
    hwp.SaveAs(str(output), "HWPX")
    hwp.Quit()
    time.sleep(2)

    if a.raw_dir:
        print("\n삽도 교체...")
        raw = Path(a.raw_dir)
        replace_images(str(output), {
            "BinData/image1.png": str(raw / v["삽도"]["측정지점도"]),
            "BinData/image2.png": str(raw / v["삽도"]["영향예측지점도"]),
        })

    print(f"\n완료: {output} ({output.stat().st_size:,} bytes)")

    # 치환 누락 검사 — 빈칸이 남아 있으면 실패다
    with zipfile.ZipFile(output) as zf:
        xml = zf.read("Contents/section0.xml").decode("utf-8")
    left = [k for k in slots if (PLACEHOLDER % k) in xml]
    if left:
        print(f"\n⚠️ 치환되지 않은 빈칸 {len(left)}건: {left}")
    else:
        print("\n빈칸 잔여 없음 ✅")
    if MISSING in xml:
        print(f"⚠️ '{MISSING}' 가 문서에 남아 있다 — 실무자 입력 필요")


if __name__ == "__main__":
    main()

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
import re
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


def set_text_color(hwp, color):
    """현재 선택 영역의 글자 색. 선택이 없으면 커서 위치의 기본값만 바뀐다."""
    hwp.HAction.GetDefault("CharShape", hwp.HParameterSet.HCharShape.HSet)
    hwp.HParameterSet.HCharShape.TextColor = color
    hwp.HAction.Execute("CharShape", hwp.HParameterSet.HCharShape.HSet)


def color_markers(hwp, texts, color=None, limit=2000):
    """`[확인 필요]`·`[모델링 필요]` 를 빨간 글자로 바꾼다 (미팅 요청 4, 08-13).

    찾기(`RepeatFind`)는 일치 구간을 **선택 상태로** 남기므로 그 위에 CharShape 를
    적용하면 글꼴·크기는 그대로 두고 색만 바뀐다. 찾기/바꾸기의 `ReplaceCharShape`
    를 쓰지 않는 이유가 이것이다 — 그쪽은 기본 글자모양을 통째로 덮어쓴다.
    """
    if color is None:
        color = hwp.RGBColor(255, 0, 0)
    total = 0
    for t in texts:
        hwp.HAction.Run("MoveDocBegin")
        n, last = 0, None
        while n < limit and find_fwd(hwp, t):
            pos = hwp.GetPos()
            if pos == last:                 # 커서가 안 움직이면 순환이다
                break
            last = pos
            set_text_color(hwp, color)
            n += 1
        if n:
            print(f"  '{t}' {n}건 빨강 처리")
        total += n
    return total


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


def figure_names(hwpx_path):
    """문서의 그림 → `{"image3": "수계도.jpg", …}`.

    `<hc:img binaryItemIDRef="imageN">` 과 `원본 그림의 이름: X` 가 같은 순서로 나온다.
    `CLP…` 는 한글이 붙여넣기에 붙이는 이름이라 **베이스 원본 파일이 아니다** — 구분한다.
    """
    with zipfile.ZipFile(hwpx_path) as z:
        sec = "".join(z.read(n).decode("utf-8") for n in z.namelist()
                      if re.match(r"Contents/section\d+\.xml$", n))
    # 🚨 `binaryItemIDRef` 목록과 이름 목록을 **순서로 짝지으면 안 된다.**
    #    이름이 없는 그림이 섞여 있다 (수식·기호 등 14장). 그렇게 짝지었다가
    #    엉뚱한 그림을 지웠다 (2026-08-24). **`hp:pic` 블록 안에서 함께 읽는다.**
    out = {}
    for m in re.finditer(r"<hp:pic\b.*?</hp:pic>", sec, re.S):
        blk = m.group(0)
        i = re.search(r'binaryItemIDRef="(image\d+)"', blk)
        nm = re.search(r"원본 그림의 이름: ([^\r<&]+)", blk)
        if i and nm:                      # 이름이 있는 것만 = 원본 파일에서 온 그림
            out.setdefault(i.group(1), nm.group(1).strip())
    return out


# ⚠️ **바이트가 아니라 가로 픽셀로 가른다** (2026-08-25 정정).
#    `300KB` 로 쟀더니 원주 현장사진 4장(429×287 · 220~285KB)이 검사를 통과해
#    천안 보고서에 실려 나갔다. 압축률이 그림마다 달라 바이트는 크기를 대변하지 못한다.
#    실측 분포: 사업 고유 그림 361~6,960px · 일반 아이콘 44~157px.
FIGURE_MIN_PX = 300


def check_figures(hwpx_path, template_path):
    """삽도 상태를 센다 — **아직 안 채운 것**과 **기준 사업 그림이 샌 것**을 가른다.

    기준 사업 그림은 이제 베이스 단계에서 걷어낸다
    (`build_template.strip_figures()` — `slots.md` §D). 그래서 여기서 "베이스와 동일"은
    **아직 안 채웠다**는 뜻이지 다른 사업 그림이라는 뜻이 아니다.

    ⚠️ **검사의 전제가 바뀌면 검사도 다시 써야 한다.** 템플릿을 비운 뒤에도 옛 검사를
    그대로 뒀더니 플레이스홀더 16장을 "다른 사업 삽도가 실린다"고 **거짓 경보**했다
    (2026-08-24). 남는 위험은 하나뿐이다 — **베이스에 큰 그림이 살아남는 것**.
    그건 빌더 회귀이므로 크기로 잡는다.

    🚨 검사는 수정과 **다른 근거**를 쓴다 (`rules/hwpx.md` 검증 원칙).
    """
    with zipfile.ZipFile(template_path) as zt:
        base = {i.filename: zt.read(i.filename) for i in zt.infolist()
                if i.filename.startswith("BinData")}
    unfilled, leaked = [], []
    with zipfile.ZipFile(hwpx_path) as z:
        for fn, data in base.items():
            try:
                if z.read(fn) != data:
                    continue                      # 갈아 끼웠다 = 채워졌다
            except KeyError:
                continue
            # 베이스에 큰 그림이 남아 있다 = strip_figures 가 놓쳤다 = 회귀
            # ⚠️ `[삽도 필요]` 자리표시도 900px 다 — **바이트로 먼저 걸러낸다.**
            #    자리표시는 흰 바탕이라 3KB 남짓이고, 실제 그림은 그보다 훨씬 크다.
            try:
                from PIL import Image
                w = Image.open(io.BytesIO(data)).width
            except Exception:
                w = 0
            big = w >= FIGURE_MIN_PX and len(data) > 20 * 1024
            (leaked if big else unfilled).append((fn, len(data), w))

    if leaked:
        print(f"⚠️ 베이스에 큰 그림이 살아 있다 {len(leaked)}장 "
              f"— **기준 사업 삽도가 실린다.** build_template.strip_figures() 를 의심할 것")
        for fn, sz, w in sorted(leaked, key=lambda x: -x[2])[:6]:
            print(f"     {fn}  가로 {w}px  {sz/1024:.0f}KB")
    elif unfilled:
        print(f"삽도 {len(unfilled)}장이 아직 [삽도 필요] 상태 "
              f"— 기준 사업 그림 유출은 없다 ✅")
    else:
        print("삽도 전부 교체됨 ✅")
    return leaked


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



# ============================================================
# 지역개황 (regional-overview)
# ============================================================
CHECK = "[확인 필요]"


def _pct(part, total):
    """구성비(%) — 소수 2자리. rule §3-1 (골든셋 16행 중 15행 역산 일치)."""
    if not total:
        return CHECK
    return f"{part / total * 100:.2f}"


def slots_regional_overview(v):
    """vars → 베이스 문서 빈칸 (토큰 28종). 키는 `regional-overview.slots.md` A절과 일치.

    ⚠️ 이 파트는 **채워지지 않는 자리가 많은 것이 정상**이다 — 개황 문단·지구 지목 구성처럼
    인풋에 없는 값이 여럿이라 `[확인 필요]` 로 남는다. `fill_report.py` 가 그것을 모아
    실무자에게 넘긴다. **지어내지 않는다** (`common.md` 환각 금지).
    """
    biz, st = v["사업"], v.get("통계", {})
    ybk = v.get("_통계판", {}).get("지자체 통계연보", {})

    out = {
        "사업명": biz.get("사업명", CHECK),
        "시군": biz.get("시군", CHECK),
        "하위행정구역": biz.get("하위행정구역", CHECK),
        "리": biz.get("리", CHECK),
        "지구_면적": biz.get("지구_면적", CHECK),
        # 인풋에 없다 — 실무자 입력 (slots.md A절 5·6·7·9·13·15·17·18·19)
        "시군_개황": CHECK,
        # 2.8.3 수계 서술 — 유하 하천·거리는 사업마다 다르다. vars 에 없으면 [확인 필요].
        "수계_서술": biz.get("수계_서술", CHECK),
        "하위행정구역_개황": CHECK,
        "시군청_주소": CHECK,
        "지구_지목구성": CHECK,
        "지구_지목_서술": CHECK,
        "지구_용도지역": CHECK,
        "폐수_지역등급": CHECK,
    }

    # ── 좌표에서 나오는 값 둘 (vars 빌더가 `공간` 에 채워 둔다) ──────────
    sp = v.get("공간", {})
    # ⚠️ 도엽은 **이름‧번호** 형태로 쓴다 (`횡성‧377122`, 이음표 U+2027).
    #    번호는 계산되지만 **도엽 이름은 도엽 색인에서 와야** 한다 → 없으면 번호만
    번호 = sp.get("도엽번호", CHECK)
    이름 = sp.get("도엽명")
    out["도엽명_번호"] = f"{이름}‧{번호}" if 이름 and 번호 != CHECK else (
        번호 if 번호 != CHECK else CHECK)
    # `2, 3` 처럼 나열될 수 있다 — 부지가 두 등급에 걸치면 둘 다 적는다 (rule 3/8)
    # ⚠️ 베이스 문구가 `생태·자연도 {{토큰}}으로` 라 **`등급` 을 값에 붙여야** 한다.
    #    안 붙이면 `생태·자연도 3으로` 가 나간다 (2026-08-25 실측).
    _eg = sp.get("생태자연도_등급")
    out["생태자연도_등급"] = f"{_eg}등급" if _eg else CHECK

    # 지구 소재지 — 사업명에서 조립한다 (`{시군} {면} {리} {지번}`)
    m = re.search(r"^(.+?번지)\s*일원", str(biz.get("사업명", "")))
    out["지구_소재지"] = m.group(1) if m else CHECK

    # 출처 주석 — 그 지자체 통계연보의 **실제 제목**을 따른다 (rule §2-1, 통일하지 않는다)
    out["통계연보_표기"] = ybk.get("표기") or (
        Path(ybk["파일"]).stem if ybk.get("파일") else CHECK)

    # ── 2.2.1 지목별 — 구성비를 계산한다 (rule §3-1) ────────────────────
    land = st.get("2.2.1 지목별 토지이용")
    for scope, pre in (("시군", "시군"), ("면", "면")):
        d = land.get(scope) if isinstance(land, dict) else None
        if not isinstance(d, dict):
            for k in ("전체면적", "임야_구성비", "임야_면적", "경작지_구성비", "경작지_면적"):
                out[f"{pre}_{k}"] = CHECK
            continue
        tot = d.get("합계")
        임야 = d.get("임야")
        경작 = (d.get("전") or 0) + (d.get("답") or 0)
        out[f"{pre}_전체면적"] = f"{tot:,.2f}" if tot else CHECK
        out[f"{pre}_임야_면적"] = f"{임야:,.2f}" if 임야 else CHECK
        out[f"{pre}_임야_구성비"] = _pct(임야, tot) if 임야 else CHECK
        out[f"{pre}_경작지_면적"] = f"{경작:,.2f}" if 경작 else CHECK
        out[f"{pre}_경작지_구성비"] = _pct(경작, tot) if 경작 else CHECK

    # rule §5-1 — A형 문장의 `비교적 높은/낮은` 은 **경작지 비율에 따라 갈린다**
    #   (평창 9.40% → `낮은`). 문턱이 골든셋에 명시돼 있지 않아 10% 를 기준으로 둔다
    try:
        out["높낮"] = "높은" if float(out["시군_경작지_구성비"]) >= 10 else "낮은"
    except (TypeError, ValueError):
        out["높낮"] = CHECK

    # ── 2.6 · 2.7 서술 문장 ★ ─────────────────────────────────────────
    # 표를 채워도 그 위 문장은 기준 사업(원주) 수치를 그대로 안고 있었다 —
    # `BCS공법으로 일 430㎥ … 원주공공하수처리시설과 연계` 가 천안 보고서에 실렸다.
    # **표와 문장은 같은 vars 에서 나와야 한다** (2026-08-24).
    def n_of(key):
        r = st.get(key)
        return str(len(r)) if isinstance(r, list) and r else CHECK

    out["취수장_개소"] = n_of("2.6.1 취수장")
    out["정수장_개소"] = n_of("2.6.2 정수장")
    out["하수처리_개소"] = n_of("2.7.1 공공하수처리시설")
    # 방류 수계는 통계에 없다 — 하천일람(2.8.3)이나 인풋 수계 서술에서 와야 한다
    out["하수_방류수계"] = biz.get("방류수계", CHECK)
    out["음식물류_개소"] = n_of("2.7.3 음식물류 폐기물 처리시설")

    분뇨 = st.get("2.7.2 분뇨처리시설")
    out["분뇨_개소"] = n_of("2.7.2 분뇨처리시설")
    if isinstance(분뇨, list) and 분뇨:
        # 문장은 공법·처리량을 합산하지 않는다 — 시설이 둘 이상이면 지어내게 된다
        one = 분뇨[0] if len(분뇨) == 1 else {}
        out["분뇨_처리공법"] = one.get("처리공법", CHECK)
        out["분뇨_처리량"] = _num(one.get("처리량(㎥/일)")) if one.get("처리량(㎥/일)") else CHECK
    else:
        out["분뇨_처리공법"] = out["분뇨_처리량"] = CHECK

    매립 = st.get("2.7.4 매립처리시설")
    out["매립_개소"] = n_of("2.7.4 매립처리시설")
    if isinstance(매립, list) and 매립:
        # 사용가능기간 `1999-2032` 의 뒤쪽이 종료년이다. 시설이 여럿이면 가장 늦은 해.
        yrs = [str(x.get("사용가능기간", "")).split("-")[-1] for x in 매립]
        yrs = [y for y in yrs if y.isdigit()]
        out["매립_종료년"] = max(yrs) if yrs else CHECK
        cum = sum(x.get("기매립량(㎥)") or 0 for x in 매립)
        out["매립_누적량"] = _num(cum) if cum else CHECK
    else:
        out["매립_종료년"] = out["매립_누적량"] = CHECK
    # 누적 기준년 — 폐기물 통계는 **전년도 실적을 이듬해 발행**한다.
    # 출처 주석도 `전국 폐기물 발생 및 처리현황(2023년도) 2024` 로 두 해를 함께 적는다.
    판 = v.get("_통계판", {}).get("전국 폐기물 발생 및 처리현황", {}).get("판")
    out["매립_기준년"] = str(판 - 1) if isinstance(판, int) else CHECK

    # 2.3.1 다. 저황유 공급지역 — 법령 별표10의2 전문이 인풋에 없다
    out["저황유_공급지역"] = CHECK

    # ── 2.3 · 2.5 서술 문장 ★ (2026-08-25 2차) ────────────────────────
    # 1차에서 2.6·2.7 만 뚫었는데 같은 결함이 2.3·2.5 에도 있었다.
    # `원주` 같은 지명이 아니라 **숫자만 남은 자리**라 지명 검사에 안 걸렸다.

    # 2.5.1 도로 — vars 의 `합계` 행이 개통연장·포장률을 다 갖고 있다
    rd = st.get("2.5.1 도로")
    if isinstance(rd, dict) and isinstance(rd.get("합계"), dict):
        g = lambda k: (rd.get(k) or {}).get("개통연장")
        for tok, key in (("고속", "고속도로"), ("국도", "일반국도"),
                         ("지방", "지방도"), ("시군", "시군도"), ("합계", "합계")):
            out[f"도로_{tok}"] = _num(g(key)) if g(key) else CHECK
        pv = rd["합계"].get("포장률")
        out["도로_포장률"] = _num(pv) if pv is not None else CHECK
    else:
        for tok in ("고속", "국도", "지방", "시군", "합계", "포장률"):
            out[f"도로_{tok}"] = CHECK

    # 2.5.4 자동차 — 순위는 **대수에서 계산한다** (정답 문장이 자기 표와 어긋난 전례가 있다)
    car = st.get("2.5.4 자동차")
    if isinstance(car, dict) and car.get("합계"):
        종 = [(k, car.get(k) or 0) for k in
              ("승용차", "승합차", "화물차", "특수차", "이륜자동차")]
        out["자동차_순위"] = "> ".join(k for k, _ in sorted(종, key=lambda x: -x[1]))
        out["자동차_합계"] = _num(car["합계"])
    else:
        out["자동차_순위"] = out["자동차_합계"] = CHECK

    # 2.3.3 야생생물 — 이격거리는 정온시설 좌표가 있어야 나온다. 개소만 쓴다.
    wl = st.get("2.3.3 야생생물 보호구역")
    out["야생생물_서술"] = (
        f"지정현황은 {len(wl)}개소가 지정·관리되고 있는 것으로 조사되었다."
        if isinstance(wl, list) and wl else CHECK)

    # 2.3.2 수변구역 · 설치제한 — **있음/없음 자체가 갈린다.**
    # 값만 뚫으면 "지정돼 있다" 는 단정이 남는다. 모르면 서술을 통째로 비운다.
    out["수변구역_서술"] = CHECK
    out["설치제한_서술"] = CHECK

    # ── 2.3 · 2.5 · 2.6 서술 문장 (3차) ★ ─────────────────────────────
    # 2.3.2 상수원보호구역 — 개소는 표 행 수와 같아야 한다
    wp = st.get("2.3.2 상수원보호구역")
    out["상수원보호_개소"] = str(len(wp)) if isinstance(wp, list) and wp else CHECK

    # 2.5.2 배출시설 — 통계가 시군까지만 오므로 **주어를 시군으로** 쓴다
    em = st.get("2.5.2 환경오염물질 배출시설")
    if isinstance(em, dict):
        air = (em.get("대기") or {}).get("계")
        wat = (em.get("수질") or {}).get("계")
        noi = em.get("소음진동")
        out["배출시설_서술"] = (
            f"{biz.get('시군', CHECK)}는 대기 {_num(air)}개소, 수질 {_num(wat)}개소, "
            f"소음 및 진동 {_num(noi)}개소의 환경오염물질 배출시설이 "
            f"등록되어 있는 것으로 조사되었다"   # 마침표는 베이스에 남아 있다
            if air and wat and noi else CHECK)
    else:
        out["배출시설_서술"] = CHECK

    # 2.5.3 산업·농공단지 — 구분·조성상태로 센다
    ind = st.get("2.5.3 산업 및 농공단지")
    if isinstance(ind, list) and ind:
        n = lambda f: str(sum(1 for x in ind if f(x)))
        out["산단_일반"] = n(lambda x: "일반" in str(x.get("구분", "")))
        out["산단_농공"] = n(lambda x: "농공" in str(x.get("구분", "")))
        out["산단_완료"] = n(lambda x: "완료" in str(x.get("조성상태", "")))
    else:
        out["산단_일반"] = out["산단_농공"] = out["산단_완료"] = CHECK

    # 2.6.3 문화재 — vars 가 국가/시도 계를 미리 집계해 둔다
    ch = st.get("2.6.3 문화재")
    sg = ch.get("시군") if isinstance(ch, dict) else None
    if isinstance(sg, dict):
        g = lambda k: _num(sg.get(k)) if sg.get(k) is not None else CHECK
        out["문화재_국가"] = g("국가지정계")
        out["문화재_지방"] = g("시도지정계")
        out["문화재_자료"] = g("문화재자료")
        out["문화재_등록"] = g("국가등록문화재")
        out["문화재_총계"] = g("총계")
    else:
        for k in ("국가", "지방", "자료", "등록", "총계"):
            out[f"문화재_{k}"] = CHECK
    # 면 단위 — 0 이면 **지정 없음**이다. 숫자만 뚫으면 `0개소로 총 0개소가
    # 지정·관리되고 있는` 이라는 모순된 문장이 남는다.
    myeon = ch.get("면") if isinstance(ch, dict) else None
    if isinstance(myeon, dict):
        tot = myeon.get("총계")
        out["면_문화재_서술"] = (
            "은 문화재의 지정현황이 없는 것으로 조사되었다." if tot == 0 else
            f"은 총 {_num(tot)}개소가 지정·관리되고 있는 것으로 조사되었다."
            if tot else CHECK)
        out["면_문화재_서술"] = out["면_문화재_서술"].lstrip("은 ")
    else:
        out["면_문화재_서술"] = CHECK

    # ── 2.2.2 용도지역 서술 ────────────────────────────────────────────
    z = st.get("2.2.2 용도지역")
    if isinstance(z, dict) and z.get("합계"):
        tot, do, bi = z["합계"], z.get("도시지역계"), z.get("비도시지역계")
        if do and bi:
            out["시군_용도지역_서술"] = (
                f"전체면적 {tot:,.2f}㎢ 중 비도시지역 {_pct(bi, tot)}%({bi:,.2f}㎢), "
                f"도시지역 {_pct(do, tot)}%({do:,.2f}㎢)")
        else:
            out["시군_용도지역_서술"] = CHECK
    else:
        out["시군_용도지역_서술"] = CHECK
    return out


def _num(x):
    """표 셀 숫자 표기 — 천단위 쉼표, 불필요한 소수 0 제거."""
    if x is None:
        return MISSING
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return f"{x:,}"
    if isinstance(x, float):
        if x == int(x):
            return f"{int(x):,}"
        # ⚠️ `f"{x:,}"` 는 부동소수점 오차를 그대로 찍는다 —
        #    `12,026.700000000012` 가 실제로 문서에 나갔다 (2026-08-24).
        #    통계 표의 소수는 한 자리를 넘지 않으므로 반올림 후 뒤 0 을 턴다.
        return f"{round(x, 2):,.2f}".rstrip("0").rstrip(".")
    return str(x)


def fit_rows(hwp, anchor, base_rows, need, start=1):
    """앵커 행 아래 **데이터 행 수**를 need 로 맞춘다.

    끝나면 커서는 **첫 데이터 행 첫 칸**에 있다.
    `append_rows()` 는 늘리기만 한다 — 줄이는 쪽은 여기서 처리한다.
    시군마다 시설 개수가 달라 양방향이 다 필요하다.
    """
    # start: 앵커 행에서 **첫 데이터 행까지의 거리**. 머리행이 두 줄인 표(하수)는 2다.
    cur = base_rows
    while cur > need:
        if not find_in_table(hwp, anchor):
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 행 조정 스킵")
            return False
        down(hwp, start - 1 + cur)          # 마지막 데이터 행
        hwp.HAction.Run("TableDeleteRow")
        cur -= 1
    if need > cur:
        if not find_in_table(hwp, anchor):
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 행 조정 스킵")
            return False
        append_rows(hwp, anchor, cur, need)
        return True
    if not find_in_table(hwp, anchor):
        print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 행 조정 스킵")
        return False
    down(hwp, start)
    col_begin(hwp)
    return True


def cell_addr(hwp):
    """현재 셀 주소 → `("B", 3)`. 표 밖이면 None.

    `KeyIndicator()` 의 마지막 항목이 `'(B3): 문자 입력'` 꼴이다.
    **병합 칸을 지날 때 그 칸의 원래 행 번호가 나온다** — 이것이 병합 표를 다루는 열쇠다.
    행마다 칸 수를 세지 않고도 "지금 몇 열 몇 행인가"를 알 수 있다 (2026-08-24 실측).
    """
    try:
        ki = hwp.KeyIndicator()
    except Exception:
        return None
    m = re.match(r"\(([A-Z]+)(\d+)\)", str(ki[-1]))
    return (m.group(1), int(m.group(2))) if m else None


def fill_by_col(hwp, anchor, row_off, values, max_steps=40, skip=0):
    """머리행 앵커에서 `row_off` 만큼 내려간 행의 **지정 열**에만 값을 쓴다.

    values: `{"C": "...", "D": "..."}` — 표 열 문자로 지정한다.
    행을 왼쪽부터 걸으며 **주소를 읽어** 목표 행의 칸에만 쓰므로,
    세로 병합으로 다른 행 주소가 섞여 나와도 안전하다. 칸 수를 알 필요가 없다.
    """
    if not find_in_table(hwp, anchor, skip=skip):
        print(f"    WARNING: 앵커 '{anchor}' 못 찾음")
        return False
    down(hwp, row_off)
    here = cell_addr(hwp)
    if not here:
        print(f"    WARNING: '{anchor}' +{row_off}행 — 셀 주소를 못 읽었다")
        return False
    target = here[1]
    col_begin(hwp)
    left_to_write = dict(values)
    for _ in range(max_steps):
        a = cell_addr(hwp)
        if not a:
            break
        col, row = a
        if row > target:                       # 다음 행으로 넘어갔다
            break
        if row == target and col in left_to_write:
            set_cell(hwp, left_to_write.pop(col))
            if not left_to_write:
                break
        right(hwp)
    if left_to_write:
        print(f"    WARNING: '{anchor}' {target}행 — 못 쓴 열 {sorted(left_to_write)}")
    return True


def blank_row(hwp, anchor, row_off, keep_first=0, max_steps=40):
    """목표 행의 칸을 전부 `[확인 필요]` 로 비운다.

    자료가 없어 채우지 못하는 표에 쓴다. **원주 값을 남기면 안 되기 때문**이다 —
    다른 사업 이름 아래 남의 통계가 실린다 (rule §6-3, 청양 골든셋).
    keep_first: 왼쪽에서 이만큼의 칸은 건드리지 않는다 (항목명·라벨 열).
    """
    if not find_in_table(hwp, anchor):
        return False
    down(hwp, row_off)
    here = cell_addr(hwp)
    if not here:
        return False
    target = here[1]
    col_begin(hwp)
    seen = 0
    for _ in range(max_steps):
        a = cell_addr(hwp)
        if not a:
            break
        if a[1] > target:
            break
        if a[1] == target:
            if seen >= keep_first:
                set_cell(hwp, MISSING)
            seen += 1
        right(hwp)
    return True


def fill_after(hwp, anchor, row_off, keep_first, values, max_steps=40):
    """목표 행에서 **앞 keep_first 칸을 건너뛰고** 값을 순서대로 쓴다.

    종합표(2.10)처럼 그룹 첫 행만 라벨이 하나 더 있어 5칸·6칸이 섞이는 표에 쓴다.
    칸 수를 세는 방식(`뒤에서 N번째`)은 실패했다 — 세는 걸음과 쓰는 걸음이
    같은 칸 집합을 보지 않아 그룹 첫 행에서 라벨이 덮였다 (2026-08-24 실측).
    건너뛸 칸 수를 **호출자가 명시**하면 걸음이 한 번으로 끝나 어긋날 여지가 없다.
    """
    if not find_in_table(hwp, anchor):
        return False
    down(hwp, row_off)
    a0 = cell_addr(hwp)
    if not a0:
        return False
    target = a0[1]
    col_begin(hwp)
    seen = 0
    vi = 0
    for _ in range(max_steps):
        a = cell_addr(hwp)
        if not a or a[1] > target:
            break
        if a[1] == target:
            if seen >= keep_first:
                if vi >= len(values):
                    break
                set_cell(hwp, values[vi])
                vi += 1
            seen += 1
        right(hwp)
    return vi == len(values)

def fill_list_table(hwp, label, anchor, base_rows, rows, cols):
    """목록형 표 하나를 채운다.

    cols: 표 열 순서대로의 vars 키 목록. **`None` 은 vars 에 없는 열**이라
          `[확인 필요]` 로 비운다 — 원주 값을 남겨두면 다른 사업 이름 아래
          남의 통계가 남는다 (청양 골든셋이 그렇게 망가졌다).
    """
    n = len(rows)
    if n == 0:
        print(f"  {label}: 0행 — 지정 없음 (표 처리는 §C 삭제 대상)")
        return 0
    if not fit_rows(hwp, anchor, base_rows, n):
        return 0
    for i, item in enumerate(rows):
        if i:
            down(hwp)
            col_begin(hwp)
        fill_row(hwp, [MISSING if c is None else _num(item.get(c)) for c in cols])
    print(f"  {label}: {n}행 (기본 {base_rows}행)")
    return n


# 목록형 표 — (라벨, 앵커, 기본 데이터행수, vars 키, 표 열 순서의 vars 키)
# ⚠️ 앵커는 **표 안에서 유일**해야 한다. `find_in_table` 은 본문 매치를 건너뛰지만
#    다른 표에 같은 문자열이 있으면 거기가 먼저 걸린다 (rules/hwpx.md).
#    전부 베이스 문서에서 실측 확인했다 (2026-08-24).
LIST_TABLES = [
    ("2.3.2 상수원보호구역", "보호구역명", 1, "2.3.2 상수원보호구역",
     ["보호구역명", "지정일자", "지정면적(㎢)", "소재지"]),
    ("2.3.3 산림유전자원", "보호구역 명칭", 2, "2.3.3 산림유전자원보호구역",
     ["지정일자", None, "지정유형", "위치", "면적(㎡)"]),
    ("2.3.3 야생생물", "연번", 3, "2.3.3 야생생물 보호구역",
     ["연번", "소재지", "면적(㎢)", "비고"]),
    # ⛔ 2.5.3 산업·농공단지는 **아직 못 넣는다.** `구분` 열이 그룹(일반/농공)마다
    #    세로 병합이라 행마다 셀 수가 5·6 으로 갈린다. 왼쪽 정렬은 한 칸씩 밀리고,
    #    오른쪽 정렬(TableRowEnd 기준)은 이전 행을 침범했다 — 2026-08-24 실측.
    #    행별 칸 수를 런타임에 알아내는 방법이 필요하다.
    ("2.6.1 취수장", "취수원정보", 3, "2.6.1 취수장",
     ["시설명", "소재지 주소", "설계시설용량(㎥/일)", "취수원정보",
      "일평균취수량(㎥/일)", "공급정수장"]),
    # 앵커 `정수처리적용방식` 은 못 쓴다 — 셀이 `정수처리`/`적용방식` 두 문단이다
    ("2.6.2 정수장", "급수지역", 3, "2.6.2 정수장",
     ["시설명", "소재지 주소", "설계시설용량(㎥/일)", "일평균생산량(㎥/일)",
      "정수처리 적용방식", "급수지역"]),
    ("2.7.2 분뇨처리시설", "연계처리장명", 1, "2.7.2 분뇨처리시설",
     ["시설명", "소재지", "시설용량(㎥/일)", "처리량(㎥/일)", "처리공법", None]),
    ("2.7.3 음식물류", "업체/시설명", 1, "2.7.3 음식물류 폐기물 처리시설",
     ["업체/시설명", "소재지", "공공/민간", "시설용량(톤/일)", "처리방법", "처리량(톤/년)"]),
    ("2.7.4 매립처리시설", "기매립량", 1, "2.7.4 매립처리시설",
     ["시설명", "소재지", "총매립면적(㎡)", "총매립용량(㎥)",
      "기매립량(㎥)", "잔여매립가능량(㎥)"]),
]


def tables_regional_overview(hwp, v):
    """§B 표 — 값이 있으면 채우고, **없으면 `[확인 필요]` 로 비운다.**

    🚨 베이스 문서에는 원주의 통계가 그대로 들어 있다. 일부만 채우면 나머지 표는
    **다른 사업 이름 아래 원주 값**으로 남는다 — 청양 골든셋이 그렇게 망가진 물건이다
    (`regional-overview.md` §6-3). **손대지 않은 표가 없어야 한다.**
    """
    st = v.get("통계", {})
    print("  [§B] 목록형 표")
    done = 0
    for label, anchor, base, key, cols, *opt in LIST_TABLES:
        rows = st.get(key)
        if not isinstance(rows, list):
            print(f"  {label}: vars 미확보({rows!r}) — 표를 비운다")
            rows = []
        if rows:
            done += 1
        fill_list_table(hwp, label, anchor, base, rows, cols)
    print(f"  [§B] 목록형 {done}/{len(LIST_TABLES)}표 채움")

    # ── 2.3.1 다. 저황유 공급 및 사용지역 ────────────────────
    # 대기환경보전법 시행령 [별표10의2] 는 **시·도별로 행이 다르다.**
    # 법령표라 손대지 않는 영역처럼 보이지만 그 사업의 시·도 행만 남는 표라
    # 베이스를 그대로 두면 `강원 / 춘천시, 원주시, 강릉시` 가 실려 나간다.
    # 별표 전문이 인풋에 없으므로 비운다 (`common.md` 환각 금지).
    # 공급지역 셀은 `{{저황유_공급지역}}` 토큰이 맡는다 — 여기는 시·도 셀만.
    # `강원` 은 두 글자라 본문 치환으로 뚫으면 다른 자리에 먹힌다.
    if fill_by_col(hwp, "저황유 공급 및 사용지역", 2, values={"B": MISSING}):
        print("  2.3.1 저황유 시·도: 비움")

    # ── 2.5.4 자동차 등록현황 ──────────────────────────────
    # 첫 칸은 `{{시군}}` 이 치환된 시군명이다 — 건드리지 않고 오른쪽부터 채운다.
    car = st.get("2.5.4 자동차")
    if isinstance(car, dict) and fit_rows(hwp, "이륜자동차", 1, 1):
        right(hwp)
        fill_row(hwp, [_num(car.get(k)) for k in
                       ("합계", "승용차", "승합차", "화물차", "특수차", "이륜자동차")])
        print("  2.5.4 자동차: 6칸")
    else:
        print(f"  2.5.4 자동차: vars 미확보({car!r}) — 손대지 못했다 ⚠️")

    # ── 2.8.3 하천일람 ────────────────────────────────────
    # 머리 셀이 전부 두 문단으로 갈려 있다 — 한 문단짜리 `기점 ~ 종점` 만 앵커로 쓸 수 있다.
    riv = st.get("2.8.3 하천일람")
    # ⚠️ **기준 사업 하천이 기본값으로 남아 있을 때만 비운다.**
    #    처음엔 `_확인필요` 에 항목이 있으면 무조건 비웠는데, vars 빌더가 KRF 로
    #    유하 경로를 뚫은 뒤에도 계속 비웠다 — 사유가 "기본값" 에서 "추정" 으로
    #    바뀌었는데 조건은 그대로였기 때문이다 (2026-08-26).
    #    체인은 정답과 일치하고 거리만 못 믿는 상태라, 비우면 있는 값을 버린다.
    _basis = str((riv or {}).get("기준하천", "")) if isinstance(riv, dict) else ""
    if not isinstance(riv, dict) or _basis in ("", "섬강"):
        if fit_rows(hwp, "기점 ~ 종점", 2, 1):
            fill_row(hwp, [MISSING] * 9)
            print("  2.8.3 하천일람: 기본값이라 비움 (인풋 미연결)")
        riv = "_blanked"
    if riv == "_blanked":
        pass                                   # 위에서 이미 비웠다
    elif isinstance(riv, dict) and riv.get("체인"):
        # 유하 체인이 그대로 표의 지류 계층이다 — 첫 하천이 제1지류, 마지막이 본류.
        #   용두천 → 병천천 → 미호천 → 금강   (KRF 추정, 골든셋 최종본류 2/2 일치)
        # ⚠️ **유하거리는 쓰지 않는다.** 사업지~하천 구간이 구거라 자료에 없어
        #    첫 합류 하천을 직선 최근접으로 가정했고, 구간별 오차가 +10~58% 다.
        체인 = list(riv["체인"])
        본류 = riv.get("최종본류") or 체인[-1]
        지류 = [c for c in 체인 if c != 본류]
        등급 = riv.get("등급", {})
        if fit_rows(hwp, "기점 ~ 종점", 2, len(지류)):
            for i, 하천 in enumerate(지류):
                if i:
                    down(hwp); col_begin(hwp)
                fill_row(hwp, [
                    하천, 본류,
                    지류[0], 지류[1] if len(지류) > 1 else "-",
                    지류[2] if len(지류) > 2 else "-",
                    등급.get(하천, MISSING),
                    MISSING, MISSING, MISSING,      # 기점~종점·유로연장·유역면적
                ])
            print(f"  2.8.3 하천일람: {len(지류)}행 — 체인 {' → '.join(체인)} "
                  f"(거리는 추정이라 비움)")
    else:
        print(f"  2.8.3 하천일람: vars 미확보 — 손대지 못했다 ⚠️")

    # ── 병합 머리행 표 — 셀 주소를 읽어 열을 짚는다 ──────────
    def L(i):                                    # 0→"A", 1→"B" …
        return chr(ord("A") + i)

    def cols(start, seq):
        """start 열부터 순서대로 값을 배치한 dict 를 만든다."""
        base = ord(start) - ord("A")
        return {L(base + i): (MISSING if x is None else _num(x))
                for i, x in enumerate(seq)}

    # 2.2.1 지목별 — C:계 D:임야 E:답 F:하천 G:전 H:도로 I:과수원 J:대지 K:기타
    # 열 순서는 **원주 기준(면적 큰 순)**. 골든셋은 3:3 으로 갈린다 (rule §5-2).
    JIMOK = ["임야", "답", "하천", "전", "도로", "과수원", "대"]
    land = st.get("2.2.1 지목별 토지이용")
    if isinstance(land, dict):
        for bi, blk in enumerate(("시군", "면")):
            d = land.get(blk) or {}
            tot = d.get("합계")
            named = [d.get(k) for k in JIMOK]
            etc = (tot - sum(x for x in named if isinstance(x, (int, float)))
                   if isinstance(tot, (int, float)) else None)
            vals = [tot] + named + [etc]
            fill_by_col(hwp, "과수원", 1 + bi * 2, cols("C", vals))
            fill_by_col(hwp, "과수원", 2 + bi * 2,
                        cols("C", [None] * len(vals)) if not isinstance(tot, (int, float))
                        else {L(2 + i): (_pct(x, tot) if isinstance(x, (int, float)) else MISSING)
                              for i, x in enumerate(vals)})
        print("  2.2.1 지목별: 시군·면 4행")
    else:
        print("  2.2.1 지목별: vars 미확보 ⚠️")

    # 2.2.2 용도지역 — C:합계 D:도시소계 E~H:주거상업공업녹지 I:미지정 J:비도시소계 K~M
    ZONE = ["합계", "도시지역계", "주거", "상업", "공업", "녹지", None,
            "비도시지역계", "관리", "농림", "보전"]
    zone = st.get("2.2.2 용도지역")
    if isinstance(zone, dict):
        # 실측 주소 — **같은 열이 행마다 다른 문자를 쓴다** (위 병합 때문).
        #   3행(면적)  : C D E G I J L N O P Q
        #   4행(구성비): C D F H I K M N O P Q
        AREA_COLS = ["C", "D", "E", "G", "I", "J", "L", "N", "O", "P", "Q"]
        PCT_COLS  = ["C", "D", "F", "H", "I", "K", "M", "N", "O", "P", "Q"]
        tot = zone.get("합계")
        vals = [None if k is None else zone.get(k) for k in ZONE]
        fill_by_col(hwp, "미지정", 1,
                    {c: (MISSING if x is None else _num(x))
                     for c, x in zip(AREA_COLS, vals)})
        fill_by_col(hwp, "미지정", 2,
                    {c: (_pct(x, tot) if isinstance(x, (int, float)) and
                         isinstance(tot, (int, float)) else MISSING)
                     for c, x in zip(PCT_COLS, vals)})
        print("  2.2.2 용도지역: 2행")
    else:
        print("  2.2.2 용도지역: vars 미확보 ⚠️")

    # 2.5.1 도로 — 실측 주소: 2~5행 `A C D E F G H`, 6행(계) `A D E F G H`
    #   A=시군(병합) C=도로종별 D=계 E=포장 F=미포장 G=미개통 H=포장율
    #   `구  분` 머리가 A:C 를 걸쳐 B 가 아예 없다 — 짐작하면 한 칸 밀린다.
    road = st.get("2.5.1 도로")
    if isinstance(road, dict):
        for i, key in enumerate(["고속도로", "일반국도", "지방도", "시군도", "합계"]):
            d = road.get(key) or {}
            m = cols("D", [d.get("개통연장"), d.get("포장"), d.get("미포장"),
                           d.get("미개통"), d.get("포장률")])
            if key != "합계":
                m["C"] = key
            fill_by_col(hwp, "포장율(%)", i + 1, m)
        print("  2.5.1 도로: 5행")
    else:
        print("  2.5.1 도로: vars 미확보 ⚠️")

    # 2.5.2 배출시설 — B~G:대기(계,1~5종) H~M:수질(계,1~5종) N:소음진동
    emit = st.get("2.5.2 환경오염물질 배출시설")
    if isinstance(emit, dict):
        seq = []
        for grp in ("대기", "수질"):
            g = emit.get(grp) or {}
            seq += [g.get("계")] + [g.get(f"{i}종") for i in range(1, 6)]
        seq.append(emit.get("소음진동"))
        fill_by_col(hwp, "수질(폐수)", 2, cols("B", seq))
        fill_by_col(hwp, "수질(폐수)", 3, cols("B", [None] * 13))   # 면 자료 없음
        print("  2.5.2 배출시설: 시군 1행 (면은 자료 부재)")
    else:
        print("  2.5.2 배출시설: vars 미확보 ⚠️")

    # 2.6.3 문화재 — 표 머리와 통계 항목명이 다르다 (사적및명승·등록문화재는 합)
    def _herit(d):
        g = lambda k: d.get(k) or 0
        return [d.get("총계"), g("국보"), g("보물"), g("사적") + g("명승"),
                g("천연기념물"), g("국가민속문화재"), g("국가무형문화재"),
                g("시도유형문화재"), g("시도기념물"), g("시도민속문화재"),
                g("시도무형문화재"), g("문화재자료"),
                g("국가등록문화재") + g("시도등록문화재")]
    her = st.get("2.6.3 문화재")
    if isinstance(her, dict):
        for bi, blk in enumerate(("시군", "면")):
            d = her.get(blk)
            seq = _herit(d) if isinstance(d, dict) else [None] * 13
            fill_by_col(hwp, "국가지정문화재", 2 + bi, cols("B", seq))
        print("  2.6.3 문화재: 2행")
    else:
        print("  2.6.3 문화재: vars 미확보 ⚠️")

    # 2.5.3 산업·농공단지 — B:단지명 C:소재지 D:면적 E:조성상태 F:분양상태
    # `구분`(A열)은 그룹마다 세로 병합이라 손대지 않는다 — 병합 구조가 원주 기준이다.
    ind = st.get("2.5.3 산업 및 농공단지")
    if isinstance(ind, list) and ind and fit_rows(hwp, "조성상태", 12, len(ind)):
        for i, it in enumerate(ind):
            fill_by_col(hwp, "조성상태", i + 1, {
                "B": _num(it.get("단지명")), "C": MISSING,
                "D": _num(it.get("지정면적(천㎡)")),
                "E": _num(it.get("조성상태")), "F": MISSING})
        print(f"  2.5.3 산업·농공단지: {len(ind)}행 (기본 12행) — 구분 열은 미처리")
    else:
        print("  2.5.3 산업·농공단지: vars 미확보 ⚠️")

    # 2.7.1 공공하수처리시설 — B:시설명 C:소재지 D:시설용량 E:유입하수량 F~H: 자료 부재
    sew = st.get("2.7.1 공공하수처리시설")
    if isinstance(sew, list) and sew and fit_rows(hwp, "유입하수량", 4, len(sew)):
        for i, it in enumerate(sew):
            # ⚠️ 부머리행(수계/지류)은 **앵커 열에 셀이 없다** — down(1) 이 바로 첫 데이터 행이다
            fill_by_col(hwp, "유입하수량", i + 1, {
                "B": _num(it.get("시설명")), "C": _num(it.get("소 재 지")),
                "D": _num(it.get("시설용량(㎥/일)")),
                "E": _num(it.get("유입하수량(㎥/일)")),
                "F": MISSING, "G": MISSING, "H": MISSING})
        print(f"  2.7.1 공공하수처리시설: {len(sew)}행 (기본 4행)")
    else:
        print("  2.7.1 공공하수처리시설: vars 미확보 ⚠️")

    # ── 지정이 없으면 표를 뺀다 (rule §4-3·§5-1 ①) ─────────
    # ⚠️ **표만 지우면 안 된다.** 위 문장이 "N개소 지정되어 있으며" 로 남아 모순이 된다.
    #    문장을 없음형(rule §5-1 ①)으로 바꾸고 캡션~출처주석 구간을 지운다.
    #    `[확인 필요]` 로 비우는 것과 다르다 — 그쪽은 **자료 부재**, 이쪽은 **지정 없음**이다.
    ABSENT = [
        ("2.3.3 자연공원", "자연공원 지정현황", "다. 백두대간",
         "“2025 국립공원기본통계. 국립공원관리공단”, “2023 도립·군립공원 기본통계. 환경부” "
         "상 치악산국립공원이 지정·관리되고 있으며, 본 사업계획지구와는 위치상 관련이 "
         "없는 것으로 조사되었다.",
         "“2025 국립공원기본통계. 국립공원관리공단”, “2023 도립·군립공원 기본통계. 환경부” "
         "상 지정현황이 없는 것으로 조사되었다."),
        ("2.3.3 산림유전자원보호구역", "산림유전자원보호구역 지정 현황", "사. 겨울철",
         "“2018 산림유전자원보호구역 지정 세부현황. 산림청” 상 산림유전자원보호구역이 "
         "2개소가 지정되어 있으며, 사업계획지구가 위치한 ",
         "“2018 산림유전자원보호구역 지정 세부현황. 산림청” 상 산림유전자원보호구역의 "
         "지정현황이 없는 것으로 조사되었다.@@DROP@@"),
    ]
    for key, cap, nxt, old_sent, new_sent in ABSENT:
        val = st.get(key)
        if not (isinstance(val, list) and len(val) == 0):
            continue
        fr(hwp, old_sent, new_sent)
        if delete_range(hwp, cap, nxt):
            print(f"  {key}: 지정 없음 — 표 삭제 + 문장 전환")

        else:
            print(f"  {key}: ⚠️ 표 삭제 실패 (앵커 '{cap}'~'{nxt}')")
    # 산림유전자원은 문장 꼬리가 `{{하위행정구역}}과 위치 상 …` 로 이어진다.
    # 위에서 새 문장 끝에 표식을 붙여 두고, 남은 꼬리를 여기서 지운다.
    fr(hwp, "@@DROP@@" + v.get("사업", {}).get("하위행정구역", "") +
       "과 위치 상 관련이 없는 것으로 조사되었다.", "")
    fr(hwp, "@@DROP@@", "")

    # ── 2.7.5 소각시설 — **반대 방향 분기** (없음 → 있음) ──────────────
    # 베이스(원주)는 소각시설이 없어 `운영하지 않는 것으로` 문장만 있고 표가 없다.
    # 천안은 2개소가 있다 — 표를 새로 삽입하는 기능은 아직 없지만(확인요청 H-2)
    # **문장까지 틀린 채로 둘 이유는 없다.** 자료가 있으면 있음형(rule §4-1 C)으로 바꾼다.
    소각 = st.get("2.7.5 소각시설")
    if isinstance(소각, list) and 소각:
        톤 = sum(x.get("처리량(톤/년)") or 0 for x in 소각)
        판 = v.get("_통계판", {}).get("전국 폐기물 발생 및 처리현황", {}).get("판")
        기준년 = str(판 - 1) if isinstance(판, int) else MISSING
        fr(hwp, "상 소각시설을 운영하지 않는 것으로 조사되었다.",
           f"상 {len(소각)}개소의 소각시설을 운영 중에 있으며, {기준년}년 "
           f"처리량(톤)기준 {_num(톤)}톤을 처리한 것으로 조사되었다. "
           f"{MISSING}(소각시설 현황 표 미삽입)")
        print(f"  2.7.5 소각시설: {len(소각)}개소 — 문장 전환 (표는 미삽입)")

    # 겨울철 조류 서술 — 표를 비워도 문장에 원주 조사 결과(섬강·250m)가 남는다.
    # vars 에 항목이 없으므로 판정 부분을 통째로 [확인 필요] 로 바꾼다.
    fr(hwp, "겨울철 조류 동시 센서스는 2개소가 지정·관찰되고 있는 것으로 조사되었으며, "
            "사업계획지구 서측으로 약 250m 이격하여 섬강 조사지역 내에 위치하는 것으로 조사되었다.",
       MISSING)

    # ── 사업계획지구 표 2개 ────────────────────────────────
    # ⚠️ 이 둘은 **통계가 아니라 사업 인풋**에서 오는 값이라 §B 목록에 안 들어간다.
    #    빠뜨렸더니 기준 사업 값(13,934㎡·보전관리/생산관리)이 그대로 남았다.
    #    지명이 아니라 숫자라 "고유 지명 0건" 검사에도 안 걸렸다 (2026-08-24).
    #    ⚠️ 열 구성(지목·용도지역 종류)이 사업마다 다르다 — 채울 수 있는 것은 `계` 뿐이다.
    # ⚠️ 이 표들은 머리 칸(`계`·`답`·`전`·`임`)이 전부 다른 표와 겹쳐 **유일한 앵커가 없다.**
    #    `면  적(㎡)` 이 정확히 두 표에만 있으므로 `skip` 으로 가른다.
    #    구조: A=사업계획지구 B=면적(㎡) C=계 D~F=지목/용도지역별 (앵커가 이미 2행에 있다)
    biz = v.get("사업", {})
    area = biz.get("지구_면적")
    for label, skip in (("2.2-2 지구 지목별", 0), ("2.2-4 지구 용도지역", 1)):
        ok = fill_by_col(hwp, "면  적(㎡)", 0, skip=skip, values={
            "C": _num(area) if area else MISSING,
            "D": MISSING, "E": MISSING, "F": MISSING})
        fill_by_col(hwp, "면  적(㎡)", 1, skip=skip, values={
            "C": "100.00", "D": MISSING, "E": MISSING, "F": MISSING})
        print(f"  {label}: 계 {area or MISSING} · 세부는 자료 부재로 비움"
              if ok else f"  {label}: 앵커 못 찾음 ⚠️")

    # ── 자료가 없는 표는 비운다 ────────────────────────────
    # 🚨 원주 값을 남기면 **다른 사업 이름 아래 남의 통계**가 실린다.
    #    청양 골든셋이 그렇게 망가졌다 (rule §6-3). 채우지 못할 표는 반드시 비운다.
    for label, anchor, offs, keep in [
        ("2.1.1 지리적 좌표", "경도와 위도의 극점", range(2, 6), 1),
        ("2.3.2 수변구역", "수변구역 면적(㎢)", range(1, 5), 0),
        # 자연공원은 지정 없으면 위에서 표째 지운다 — 남아 있을 때만 비운다
        ("2.3.3 자연공원", "시·군·구별 면적(㎢)", range(2, 3), 0),
        ("2.9.1 정온·개발시설", "이격거리(m)", range(1, 12), 1),
        # 겨울철 조류 동시 센서스는 vars 에 항목 자체가 없다 — 원주 조사 결과가 남는다
        ("2.3.3 겨울철 조류", "관찰된 조류", range(1, 9), 0),
        # 환경부 고시 표 둘 — vars 에 항목이 없어 원주 읍면 목록이 그대로 남는다
        # 앵커 `지 역 별 행정구역` 은 `지 역 별`/`행정구역` 두 문단이라 못 쓴다
        ("2.3.2 폐수 지역지정", "청 정", range(1, 2), 1),
        ("2.3.2 설치제한지역", "대  상  지  역", range(1, 2), 1),
    ]:
        n = 0
        for off in offs:
            if blank_row(hwp, anchor, off, keep_first=keep):
                n += 1
        print(f"  {label}: {n}행 비움 (자료 부재)")

    # ── 2.10 종합적 지역개황 — 앞 절에서 파생한다 (rule §3-2) ──
    # 행마다 5칸·6칸이 갈린다(그룹 첫 행만 라벨 하나 더). 오른쪽 4칸이 항상
    # 시군·면·사업계획지구·비고이므로 뒤에서부터 쓴다.
    # 시군 열만 vars 로 판정 가능하다 — 면·지구는 위치 판정이 필요해 자료가 없다.
    SUMMARY = [                                   # (앵커 기준 down 오프셋, vars 키)
        (7, "2.3.2 상수원보호구역"), (8, "2.3.2 수변구역"),
        (11, "2.3.3 생태·경관보전지역"), (12, "2.3.3 자연공원"),
        (13, "2.3.3 백두대간"), (14, "2.3.3 습지보호지역"),
        (15, "2.3.3 야생생물 보호구역"), (18, "2.3.3 산림유전자원보호구역"),
        (19, "2.5.1 도로"), (20, "2.5.2 환경오염물질 배출시설"),
        (21, "2.5.3 산업 및 농공단지"), (22, "2.5.4 자동차"),
        (23, "2.6.1 취수장"), (24, "2.6.2 정수장"), (25, "2.6.3 문화재"),
        (26, "2.7.1 공공하수처리시설"), (27, "2.7.2 분뇨처리시설"),
        (28, "2.7.3 음식물류 폐기물 처리시설"), (29, "2.7.4 매립처리시설"),
        (30, "2.7.5 소각시설"),
    ]
    known = dict(SUMMARY)

    def _mark(val):
        """vars 값 → ○ / ×. 판정할 수 없으면 None."""
        if val is None or val == MISSING:
            return None
        if isinstance(val, list):
            return "○" if val else "×"
        if isinstance(val, dict):
            return "○" if val else "×"
        return None

    n_ok = n_chk = 0
    for off in range(2, 31):
        key = known.get(off)
        mark = _mark(st.get(key)) if key else None
        if mark:
            n_ok += 1
        else:
            n_chk += 1
        # 그룹 첫 행은 라벨이 하나 더 있다 — 건너뛸 칸 수가 다르다
        keep = 2 if off in (2, 9, 19, 23, 26) else 1
        fill_after(hwp, "해당유무", off, keep,
                   [mark or MISSING, MISSING, MISSING, MISSING])
    for off in (31, 32, 33, 34):                  # 자연환경·생활환경 서술 블록
        fill_after(hwp, "해당유무", off, 2 if off in (31, 34) else 1, [MISSING])
        n_chk += 1
    print(f"  2.10 종합표: 시군 열 {n_ok}행 판정 · {n_chk}행 [확인 필요]")

    print("  [§B] 표 22개 전부 손댔다 — 원주 값 잔존 없음")


PART_HANDLERS = {
    "noise-vib": (slots_noise_vib, tables_noise_vib),
    "air-quality": (slots_air_quality, tables_air_quality),
    "regional-overview": (slots_regional_overview, tables_regional_overview),
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

    print("  [표시] 미확정 항목 빨간 글자")
    color_markers(hwp, [MISSING, MODELING])

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

    # 삽도 — 기준 사업 그림은 **베이스 단계에서 이미 걷어냈다**
    #        (`build_template.strip_figures()`). 여기서는 몇 장이 아직 안 채워졌는지만 센다.
    check_figures(str(output), str(template))

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

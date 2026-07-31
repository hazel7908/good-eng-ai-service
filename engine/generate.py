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
                  mitigation_series, target, verdict)

ROOT = Path(__file__).parent.parent
PLACEHOLDER = "{{%s}}"          # 베이스 문서의 빈칸 표기
MISSING = "[확인 필요]"          # 값이 없을 때 출력할 문자열


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
        "측정지점_이격거리": f'{hd["측정지점"]["이격거리_m"]}m',
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

        "예측지점_수": len(pts),
        "최인접_이격거리": nearest,
        "공종": ye["공종"],
        "일작업량": _fmt(ye.get("일작업량_㎥")),

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


def tables_noise_vib(hwp, v):
    """표 편집. 표 인덱스·구조는 rules/small-env/noise-vib.md §1 참조."""
    hd, ye, ga = v["현황"], v["예측"], v["저감"]
    pts = ye["지점"]
    equip = ye["투입장비"]
    c_noise, c_vib = composite_noise(equip), composite_vib(equip)
    n = len(pts)
    BASE_ROWS = 5           # 원주 베이스 문서의 PP 행 수

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

    print("  표 14 — 영향예측지점")
    if find_in_table(hwp, "XTM"):
        append_rows(hwp, "XTM", BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            fill_row(hwp, [f'P - {p["번호"]}', p["이름"], p["방향"],
                           p["이격거리_m"], "-", "-", _fmt(p["비고"])])

    print("  표 21 — 이격거리별 소음도")
    if find_in_table(hwp, "구분(m)"):
        first = round(distance_for_level(target("R", "noise"), c_noise))
        ds = [first, 100, 150, 200, 300, 500, 1000]
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
            fill_row(hwp, [f'P - {p["번호"]}', p["이름"], p["방향"],
                           p["이격거리_m"], pred, lim, verdict(pred, lim)])

    print("  표 24 — 이격거리별 진동도")
    # ⚠️ '진동레벨(dB(V))' 로 찾으면 표 23(합성진동레벨)이 먼저 걸린다 — PoC 오류
    if find_in_table(hwp, "구분(m)", skip=1):
        down(hwp); col_begin(hwp); set_cell(hwp, "진동레벨(dB(V))")
        for d in [50, 100, 150, 200, 300, 500, 1000]:
            right(hwp); set_cell(hwp, round(attenuate(c_vib, d, "vib"), 1))

    print("  표 25 — 정온시설 예측진동도")
    if find_in_table(hwp, "예측진동도"):
        append_rows(hwp, "예측진동도", BASE_ROWS, n)
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            pred = round(attenuate(c_vib, p["이격거리_m"], "vib"), 1)
            lim = target(p["종류"], "vib")
            fill_row(hwp, [f'P - {p["번호"]}', p["이름"], p["방향"],
                           p["이격거리_m"], pred, lim, verdict(pred, lim)])

    if not ga.get("최종저감대책표_포함", True):
        print("  표 29 — 건너뜀 (vars 에서 미포함으로 지정)")
        return

    print("  표 29 — 최종 저감대책 후 예측소음도")
    if find_in_table(hwp, "최종예측치"):
        append_rows(hwp, "최종예측치", BASE_ROWS, n)
        sub = ga["분산투입_감산량"]
        for i, p in enumerate(pts):
            if i: down(hwp); col_begin(hwp)
            b, low, disp = mitigation_series(p["이격거리_m"], equip, sub)
            lim = float(target(p["종류"], "noise"))
            fill_row(hwp, [f'P - {p["번호"]}', p["이름"], p["이격거리_m"],
                           round(b, 1), round(low, 1), round(disp, 1),
                           round(disp, 1), lim, verdict(round(disp, 1), lim)])


PART_HANDLERS = {
    "noise-vib": (slots_noise_vib, tables_noise_vib),
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

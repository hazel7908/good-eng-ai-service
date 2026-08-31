#!/usr/bin/env python3
"""
한글 API(win32com) 기반 HWPX 보고서 생성 엔진 — 얇은 드라이버.

  베이스 문서(빈칸) + vars/{파트}.json  →  cases/{카테고리}/{사업}/{파트}/output.hwpx

설계 원칙 (repo_restructure_plan.md §4 · 전환계획 §10 R1):
  - **엔진은 파트를 모른다.** 파트 핸들러는 engine/parts/{카테고리}/{파트}.py 에 있고
    파일이 존재하면 자동 등록이다. 계산은 calc*.py, 지식은 rules/, 사업 값은 vars.
  - 카테고리에 핸들러가 없으면 **동명 파트로 폴백**한다 (이식의 기본 동작, R3).
  - 공용 한글 API 유틸은 hwp_util.py.

⚠️ Windows + 한글 프로그램 전용. Mac 에서는 --dry-run 으로 치환값만 점검한다.

사용:
    python engine/generate.py small-env noise-vib 괴산_금신리
    python engine/generate.py small-env noise-vib 괴산_금신리 --raw-dir "D:/raw/괴산/삽도"
"""

import argparse
import importlib.util
import json
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))          # parts 가 hwp_util·calc 를 찾도록

from hwp_util import (MISSING, MODELING, PLACEHOLDER, ROOT, check_figures,
                      color_markers, fr, replace_images)

PARTS_DIR = Path(__file__).parent / "parts"


def load_part_handlers(category, part):
    """engine/parts/{category}/{part}.py → (build_slots, build_tables).

    카테고리에 파일이 없으면 동명 파트가 정확히 하나일 때만 폴백한다 —
    여럿이면 어느 카테고리 것인지 알 수 없으므로 멈춘다 (R3).
    """
    path = PARTS_DIR / category / f"{part}.py"
    if not path.exists():
        cands = sorted(PARTS_DIR.glob(f"*/{part}.py"))
        if len(cands) == 1:
            print(f"  [핸들러 폴백] {category}/{part} 없음 → {cands[0].parent.name}/{part}")
            path = cands[0]
        elif not cands:
            known = ", ".join(sorted(f"{p.parent.name}/{p.stem}"
                                     for p in PARTS_DIR.glob("*/*.py")))
            sys.exit(f"ERROR: 핸들러 없음 — {path}\n  지원: {known}")
        else:
            sys.exit(f"ERROR: '{part}' 핸들러가 여러 카테고리에 있다: "
                     f"{[str(c) for c in cands]}\n"
                     f"  engine/parts/{category}/{part}.py 를 명시적으로 만들 것")
    spec = importlib.util.spec_from_file_location(
        f"part_{category}_{part}".replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for fn in ("build_slots", "build_tables"):
        if not hasattr(mod, fn):
            sys.exit(f"ERROR: {path} 에 {fn}() 없음 — 파트 모듈 규약 위반")
    return mod.build_slots, mod.build_tables


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

    build_slots, build_tables = load_part_handlers(a.category, a.part)
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

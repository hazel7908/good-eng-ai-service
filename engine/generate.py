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
import re
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))          # parts 가 hwp_util·calc 를 찾도록

import law_update
import table_leak
from hwp_util import (MISSING, MODELING, PLACEHOLDER, ROOT, check_figures,
                      color_markers, console_utf8, fr, open_hwp, quit_hwp,
                      replace_images)

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
    console_utf8()          # cp949 콘솔에서 진행 로그가 생성을 죽이지 않도록
    ap = argparse.ArgumentParser(description="HWPX 보고서 생성")
    ap.add_argument("category"); ap.add_argument("part"); ap.add_argument("case")
    ap.add_argument("--raw-dir", help="삽도 원본 JPG 디렉터리")
    ap.add_argument("--dry-run", action="store_true",
                    help="한글 없이 치환값만 출력 (Mac 에서 vars 점검용)")
    ap.add_argument("--no-law-update", action="store_true",
                    help="법령 인용 최신화 훅을 끈다 (되먹임은 자동으로 꺼진다)")
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

    # 🚨 **생성 실패와 게이트 통과가 동시에 성립했다** (2026-09-08 실측).
    #    핸들러가 ImportError 로 죽어 생성이 중단됐는데 **옛 산출물이 그대로 남아 있어**
    #    `smoke_check` 이 그걸 보고 초록을 냈다. 로그의 `비움 0` 이 아니었으면 못 봤다.
    #    → 시작할 때 치워 두고, **끝까지 성공했을 때만** 되돌린다. 도중에 죽으면
    #      산출물이 없어서 게이트가 자연히 빨개진다 (제일 값싸고 빈틈없다).
    prev = output.with_suffix(".hwpx.prev")
    if output.exists():
        if prev.exists():
            prev.unlink()
        output.rename(prev)

    try:
        import win32com.client
    except ImportError:
        sys.exit("ERROR: pywin32 미설치 (Windows 전용). 계산 확인은 engine/calc.py")

    print("[1/4] 한글 시작...")
    # 🚨 읽기 전용으로 열리면 표 편집이 **조용히 전부 무시된다** — open_hwp 주석 참조
    hwp = open_hwp(template)

    # ⚠️ try/finally 가 방어의 나머지 절반이다. 도중에 예외가 나면 Quit() 이 안 불려
    #    한글이 템플릿을 붙든 채 살아남고, **다음 실행이 읽기 전용으로 열려** 표가
    #    기준 사업 값 그대로 나간다 (2026-08-31 실측 — 진행 로그 한 줄의 인코딩
    #    오류가 천안 소음진동 표 7개를 원주 값으로 만들었다).
    saved = False
    law_n, law_의심 = 0, []
    try:
        print(f"\n[2/4] 빈칸 치환 ({len(slots)}건)...")
        for k, val in slots.items():
            fr(hwp, PLACEHOLDER % k, str(val))

        print("\n[3/4] 표 편집...")
        build_tables(hwp, v)

        # 한글 빠른 교정이 셀에 넣은 'P - 1' 의 하이픈을 en-dash(–) 로 바꾼다.
        # 골든셋·베이스 문서에는 en-dash 가 한 개도 없다 — 전부 InsertText 가 만든 것이다.
        print("  [정리] 빠른 교정이 바꾼 en-dash 되돌리기")
        fr(hwp, "P – ", "P - ")

        # 법령 인용 자동 최신화 (지시서 ㉙) — 베이스는 판 고정, 산출물만 최신이 된다.
        # ⚠️ 되먹임은 배치 대조가 목적이라 법령 diff 가 섞이면 결함과 구분이 안 된다 → 자동 OFF.
        기준 = (table_leak.CATEGORY_BASE.get(a.category) or {}).get("기준사업")
        if a.no_law_update:
            print("  [법령] --no-law-update — 최신화 건너뜀")
        elif a.case == 기준:
            print(f"  [법령] 되먹임({기준}) — 최신화 건너뜀 (배치 대조가 목적)")
        else:
            law_n, law_의심 = law_update.apply(hwp, fr, a.category, a.part)

        print("  [표시] 미확정 항목 빨간 글자")
        color_markers(hwp, [MISSING, MODELING])

        print("\n[4/4] 저장...")
        hwp.SaveAs(str(output), "HWPX")
        saved = True
    finally:
        quit_hwp(hwp)       # 프로세스가 실제로 죽을 때까지 대기 (다음 실행의 읽기 전용 방지)
    if not saved:
        sys.exit("ERROR: 생성이 중단됐다 — 위 오류를 먼저 고칠 것 "
                 f"(옛 산출물은 {prev.name} 로 치워 뒀다 — 게이트가 빨개지는 것이 정상)")
    if prev.exists():
        prev.unlink()          # 성공 — 옛 판은 버린다
    time.sleep(2)

    if a.raw_dir:
        print("\n삽도 교체...")
        raw = Path(a.raw_dir)
        replace_images(str(output), {
            "BinData/image1.png": str(raw / v["삽도"]["측정지점도"]),
            "BinData/image2.png": str(raw / v["삽도"]["영향예측지점도"]),
        })

    print(f"\n완료: {output} ({output.stat().st_size:,} bytes)")

    # 법령 최신화 **사후 검산** — `fr()` 은 몇 건을 바꿨는지 안 알려준다.
    # 구번호가 그대로 남아 있으면 치환이 조용히 실패한 것이다 (지시서 ㉙ 요구).
    if law_n:
        from extract import extract as _ex
        _t = _ex(str(output))
        적용, 실패, 미등록 = law_update.verify(_t, a.category, a.part)
        print(f"  [법령] 검산 — 신표기 {적용}건 확인"
              + (f" · ❌ 구표기 잔존 {len(실패)}건" if 실패 else " · 구표기 잔존 0"))
        for e in 실패[:5]:
            print(f"     ❌ {e['old'][:70]}")
        if 미등록:
            print(f"  [법령] map 에 없는 고시번호 {len(미등록)}종 — " + ", ".join(미등록[:6]))
        (output.parent / "law-update.json").write_text(json.dumps(
            {"시도": law_n, "확인": 적용, "구표기잔존": [e["old"] for e in 실패],
             "map밖_고시번호": 미등록,
             "인용오류의심": [e["인용"] for e in law_의심],
             "근거": "법제처 API 대조 map " + str(law_update.load().get("생성일", ""))},
            ensure_ascii=False, indent=1), encoding="utf-8")

    # 삽도 — 기준 사업 그림은 **베이스 단계에서 이미 걷어냈다**
    #        (`build_template.strip_figures()`). 여기서는 몇 장이 아직 안 채워졌는지만 센다.
    check_figures(str(output), str(template))

    # 치환 누락 검사 — 빈칸이 남아 있으면 실패다
    # 🚨 **섹션이 여럿인 문서가 있다** — `section0.xml` 만 읽으면 뒤 섹션의 빈칸을
    #    통째로 못 본다. 동식물상은 4섹션이라 이 게이트가 헛통과했다 (09-03).
    #    `smoke_check`·`leak_check`·`table_leak` 은 이미 전 섹션을 읽는다.
    with zipfile.ZipFile(output) as zf:
        xml = "".join(zf.read(n).decode("utf-8") for n in sorted(zf.namelist())
                      if re.match(r"Contents/section\d+\.xml$", n))
    left = [k for k in slots if (PLACEHOLDER % k) in xml]
    if left:
        print(f"\n⚠️ 치환되지 않은 빈칸 {len(left)}건: {left}")
    else:
        print("\n빈칸 잔여 없음 ✅")
    if MISSING in xml:
        print(f"⚠️ '{MISSING}' 가 문서에 남아 있다 — 실무자 입력 필요")


if __name__ == "__main__":
    main()

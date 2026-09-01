#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""러프 단계 스모크 게이트 — 생성물 하나에 대한 공통 검사 5종을 한 명령으로 (전환계획 §5-2 · §10 R5).

    python engine/smoke_check.py <카테고리> <파트> <사업>

  ① 빈칸 잔여 0     — `{{…}}` 토큰이 문서에 남아 있으면 실패
  ①-2 계산 필드 오류 — `잘못된 계산식` (한글 표 합계 참조 깨짐)
  ② 기준 사업 유출   — leak_check (베이스·생성물 공통 숫자, 서술 문장만)
  ③ [확인 필요] 목록 — 개수 + vars `_확인필요` 대조 (실무자 작업 목록의 원천)
  ④ PDF 육안        — Windows 전용(`engine/to_pdf.py`) 안내만 출력. 그림·레이아웃은
                       텍스트 검사에 전부 안 걸린다 (hwpx.md 검증 원칙 3)

정밀 채점(score_*)은 보완 단계의 일이다 — 러프 단계 게이트는 "실무자가 안심하고
이어받을 수 있는 상태"(WRONG 0 + 미확정 표시)만 본다.
"""
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hwp_util import console_utf8          # noqa: E402  (경로 삽입 뒤라야 한다)

ROOT = Path(__file__).parent.parent
TOKEN = re.compile(r"\{\{[^}]{1,40}\}\}")
MARKS = ["[확인 필요]", "[모델링 필요]", "[현장조사 필요]", "[실무자 확인]"]


def doc_text(path):
    z = zipfile.ZipFile(path)
    return "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                   if re.match(r"Contents/section\d+\.xml$", n))


def main():
    console_utf8()
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    category, part, case = sys.argv[1:4]
    output = ROOT / "cases" / category / case / part / "output.hwpx"
    template = ROOT / "templates" / category / f"{part}.hwpx"
    vars_path = ROOT / "cases" / category / case / "vars" / f"{part}.json"
    if not output.exists():
        sys.exit(f"ERROR: 생성물 없음 — {output}")

    xml = doc_text(output)
    fails = 0

    # ① 빈칸 잔여
    tokens = sorted(set(TOKEN.findall(xml)))
    if tokens:
        fails += 1
        print(f"① 빈칸 잔여 ❌ {len(tokens)}종: {tokens[:10]}")
    else:
        print("① 빈칸 잔여 0 ✅")

    # ①-2 한글 계산 필드 오류
    # ⚠️ 표 합계·곱셈을 한글 **계산 필드**로 넣은 자리는 행을 늘이거나 셀을 갈아
    #    끼우면 참조가 깨지고, 문서에는 `잘못된 계산식` 이라는 **글자로 남는다.**
    #    빈칸도 아니고 유출도 아니라 ①②③ 어디에도 안 걸린다 —
    #    원주 수질 생성물에서 9건이 채점 단계에서야 드러났다 (2026-08-31).
    bad_field = xml.count("잘못된 계산식")
    if bad_field:
        fails += 1
        print(f"①-2 계산 필드 오류 ❌ {bad_field}건 — 표 합계 참조가 깨졌다 "
              f"(행 삽입·셀 교체 뒤 재계산 필요)")
    else:
        print("①-2 계산 필드 오류 0 ✅")

    # ② 기준 사업 유출
    if template.exists():
        r = subprocess.run([sys.executable, str(ROOT / "engine" / "leak_check.py"),
                            str(template), str(output)],
                           capture_output=True, text=True,
                           # ⚠️ 기본 인코딩(cp949)으로 읽으면 자식의 한글 출력에서
                           #    UnicodeDecodeError 가 나 stdout 이 통째로 없어진다.
                           #    유출이 있을 때 그 내역을 못 찍는다 (2026-08-31).
                           encoding="utf-8", errors="replace")
        leaked = r.returncode != 0
        fails += 1 if leaked else 0
        print(f"② 기준 사업 유출 {'❌' if leaked else '✅'}")
        if leaked:
            print("   " + r.stdout.strip().replace("\n", "\n   "))
    else:
        print(f"② 기준 사업 유출 — 건너뜀 (베이스 없음: {template})")

    # ②-2 표 유출 — leak_check(서술만)가 못 잡는 표 값·지명·뒤섞인 값 (증거인계 문서 §4).
    #     되먹임(원주)이면 검사기가 스스로 건너뛴다. 경고(표동일)는 실패가 아니다 — 훑기 목록.
    r2 = subprocess.run([sys.executable, str(ROOT / "engine" / "table_leak.py"),
                         category, part, case],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    t_leak = r2.returncode != 0
    fails += 1 if t_leak else 0
    print(f"②-2 표 유출 {'❌' if t_leak else '✅'}")
    if r2.stdout.strip():
        print("   " + r2.stdout.strip().replace("\n", "\n   "))

    # ③ [확인 필요] 목록 — 실패가 아니라 실무자 작업 목록이다
    counts = {m: xml.count(m) for m in MARKS if xml.count(m)}
    total = sum(counts.values())
    print(f"③ 미확정 표시 {total}건 " + (f"{counts}" if counts else "— 전부 확정 ✅"))
    if vars_path.exists():
        pending = json.loads(vars_path.read_text(encoding="utf-8")).get("_확인필요", [])
        print(f"   vars _확인필요 {len(pending)}건 — 내역서: engine/fill_report.py 로 생성")

    # ④ PDF 육안
    print("④ PDF 육안 — Windows 에서: python engine/to_pdf.py 후 페이지 이미지 확인"
          " (그림·레이아웃은 텍스트 검사에 안 걸린다)")

    print(f"\n{'통과 ✅' if fails == 0 else f'실패 {fails}건 ❌'} — {output.name} ({category}/{part}/{case})")
    return fails


if __name__ == "__main__":
    sys.exit(main())

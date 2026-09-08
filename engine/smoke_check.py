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
# ⚠️ 한글 **수식**에 `{{` 가 나온다 — `sqrt {{tau _{0}} over {rho }}` (전략 수리수문 09-07).
#    느슨한 `\{\{[^}]+\}\}` 는 이걸 빈칸으로 보고 게이트를 빨갛게 만든다.
#    토큰 이름은 한글·영숫자·밑줄뿐이다 — 공백·중괄호가 있으면 토큰이 아니다.
TOKEN = re.compile(r"\{\{[0-9A-Za-z_가-힣]{1,40}\}\}")
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

    # ⓪ **산출물이 지금 코드로 만들어진 것인가** (2026-09-08 신설)
    # 🚨 생성이 도중에 죽어도 옛 산출물이 남아 있으면 아래 검사가 전부 초록을 낸다 —
    #    실제로 그렇게 통과했다. generate 가 `.prev` 로 치우는 것이 1차 방어이고,
    #    이건 **다른 근거**로 거는 2차다 (검사와 수정은 근거를 나눈다 — rules/hwpx.md).
    #    판정: 산출물이 **핸들러·베이스·vars 중 무엇보다도 오래되었으면** 낡은 것이다.
    src = [template, vars_path,
           ROOT / "engine" / "parts" / category / f"{part}.py"]
    older = [s.name for s in src if s.exists() and s.stat().st_mtime > output.stat().st_mtime]
    if older:
        print(f"⓪ 산출물이 낡았다 ❌ — {', '.join(older)} 보다 오래됐다 (재생성할 것)")
        fails += 1
    else:
        print("⓪ 산출물 신선도 ✅")

    # ⓪-2 **베이스가 되쓰이지 않았는가** (2026-09-08 — caef5f7 사고: generate 가 베이스를
    #     직접 열어 한글이 되썼고, 토큰이 사라지면 ①빈칸 잔여가 영원히 초록이라 못 잡는다.
    #     .work.hwpx 사본 방식이 1차 방어, 이건 git 근거의 2차다. 의도한 베이스 재빌드
    #     중이면 이 경고는 무시하고 커밋하면 된다 — 그 외의 templates/ 변경은 전부 사고다.
    import subprocess as _sp
    dirty = _sp.run(["git", "status", "--porcelain", "--", "templates/"],
                    capture_output=True, text=True, cwd=ROOT).stdout.strip()
    if dirty:
        print("⓪-2 templates/ 가 변경돼 있다 ❌ — 베이스 되쓰기 의심 (의도한 재빌드가 아니면"
              " git checkout 으로 복원):\n     " + dirty.replace("\n", "\n     "))
        fails += 1
    else:
        print("⓪-2 베이스 무변경 ✅")

    # ⓪-3 **비우기 앵커가 베이스에서 실제로 잡히는가** (2026-09-08 신설)
    #     앵커가 표 밖 캡션이거나 문단 경계로 쪼개져 있으면 `blank_tables` 가 0을 돌려주고
    #     **그 표는 기준 사업 값 그대로 나간다.** 생성은 성공으로 끝나고 ①②③ 어디에도
    #     안 걸린다 — 로그의 WARNING 한 줄이 유일한 흔적인데 배치에서는 묻힌다.
    try:
        import anchor_check as _ac
        _base = ROOT / "templates" / category / f"{part}.hwpx"
        _hd = ROOT / "engine" / "parts" / category / f"{part}.py"
        if _base.exists() and _hd.exists():
            _blank, _err = _ac.load_blank(_hd)
            _paras = _ac.paragraphs(_base) if _blank else []
            _dead = [a for a, *_ in (_blank or [])
                     if not any(a in t and intbl for t, intbl in _paras)]
            if _err:
                print(f"⓪-3 핸들러 로드 실패 ❌ — {_err}")
                fails += 1
            elif _dead:
                print(f"⓪-3 못 찾는 앵커 {len(_dead)}개 ❌ — 그 표는 기준 사업 값이 남는다: {_dead}")
                fails += 1
            else:
                print(f"⓪-3 앵커 {len(_blank or [])}개 전부 잡힘 ✅")
    except Exception as e:                     # 검사기 탓에 게이트가 죽으면 안 된다
        print(f"⓪-3 앵커 검사 건너뜀 — {type(e).__name__}: {e}")

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
    # 🚨 **되먹임에는 원리상 무의미하다** — `leak_check` 는 베이스↔산출물의 **공통 숫자**를
    #    의심하는데, 기준 사업 자기 생성은 값이 같은 것이 정상이다. ②-2 는 이미 스스로
    #    건너뛰는데 ② 만 안 건너뛰어 소재평 3장이 **법령 숫자로 거짓 실패**했다
    #    (`한국지질도(1/50,000)` 의 `00` · `자연재해대책법시행령 제55조` 의 `55`. 09-03).
    try:
        sys.path.insert(0, str(ROOT / "engine"))
        from table_leak import CATEGORY_BASE            # noqa: PLC0415
        _feedback = (CATEGORY_BASE.get(category) or {}).get("기준사업") == case
    except Exception:                                    # noqa: BLE001
        _feedback = False
    if _feedback:
        print("② 기준 사업 유출 ✅")
        print("   되먹임(기준 사업 자기 생성) — 서술 숫자 대조는 무의미하다. 건너뜀")
    elif template.exists():
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

    # ⚠️ 자식이 **죽어도** returncode 는 0 이 아니다 — stderr 를 안 찍으면 크래시가
    #    "유출 있음" 으로 둔갑한다. 실제로 table_leak 이 cp949 에서 죽어 네 파트가
    #    거짓 실패로 나왔다 (2026-09-01).
    if t_leak and not r2.stdout.strip() and r2.stderr.strip():
        print("   ⚠️ 검사기가 죽었다 (유출이 아니라 오류):")
        print("   " + r2.stderr.strip().splitlines()[-1])

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

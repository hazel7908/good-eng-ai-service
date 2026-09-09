#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spec `replace` 의 old 문자열이 **한 문단 안에 온전히** 있는가 — 빌드 전 MISS 예보.

🚨 한글 찾기/바꾸기는 **문단 경계를 못 넘는다.** 셀 안이 두 문단이면
(`충청북도 제천시` / `수산면 고명리`) 결합형 `old` 는 조용히 MISS 난다 —
빌드를 돌려야 그때 알 수 있고, 베이스 재빌드는 한 번이 수십 분이다.
`anchor_check` 가 비우기 앵커에 하는 일을 **spec 치환 문자열**에 하는 것이다.

`(1)`·`(가)` 같은 자동 번호 필드가 old 에 들어가도 MISS 가 나는데(본문 텍스트가 아니다)
그건 이 검사로는 안 보인다 — 문단 재조립에도 안 잡히기 때문이다. → `없음` 으로 뜬다.

  python engine/spec_para_check.py [카테고리] [파트]
  python engine/spec_para_check.py            # 전수
종료코드 1 = 쪼개짐·없음 있음.
"""
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwp_util import console_utf8  # noqa: E402
import anchor_check as AC          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def check(cat: str, part: str, quiet=False):
    spec_p = ROOT / "templates" / cat / f"{part}.spec.py"
    if not spec_p.exists():
        return None
    sp = importlib.util.spec_from_file_location("s", spec_p)
    m = importlib.util.module_from_spec(sp)
    try:
        sp.loader.exec_module(m)
    except Exception as e:
        print(f"  ⚠️ {cat}/{part} spec 로드 실패 — {type(e).__name__}: {e}")
        return None
    SPEC = getattr(m, "SPEC", None) or {}
    pairs = SPEC.get("replace") or []
    if not pairs:
        return None

    src = Path(SPEC.get("src") or SPEC.get("source") or "")
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        src = ROOT / "templates" / cat / f"{part}.hwpx"   # 원천이 없으면 베이스로 근사
        if not src.exists():
            return None
    paras = [t for t, _ in AC.paragraphs(src)]
    flat_ns = re.sub(r"\s", "", "".join(paras))

    ok = split = missing = 0
    for old, _new in pairs:
        if any(old in p for p in paras):
            ok += 1
        elif re.sub(r"\s", "", old) in flat_ns:
            split += 1
            if not quiet:
                print(f"  🚨 {cat}/{part} 문단 경계로 쪼개짐 — 빌드에서 MISS 난다")
                print(f"      {old[:74]}")
        else:
            missing += 1
            if not quiet:
                print(f"  ❌ {cat}/{part} 원천에 없음 (자동 번호 필드일 수도 있다)")
                print(f"      {old[:74]}")
    return ok, split, missing


def main():
    console_utf8()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) == 2:
        r = check(*args)
        if r:
            print(f"\n  replace {sum(r)}건 — 한 문단 ✅ {r[0]} · 쪼개짐 {r[1]} · 없음 {r[2]}")
        return 1 if r and (r[1] or r[2]) else 0

    tot = [0, 0, 0]
    n = 0
    for spec in sorted(ROOT.glob("templates/*/*.spec.py")):
        r = check(spec.parent.name, spec.stem.replace(".spec", ""))
        if not r:
            continue
        n += 1
        tot = [a + b for a, b in zip(tot, r)]
    print(f"\n  spec {n}개 · replace {sum(tot)}건 — 한 문단 ✅ {tot[0]} · "
          f"쪼개짐 {tot[1]} · 없음 {tot[2]}")
    return 1 if tot[1] or tot[2] else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전 spec 순차 시뮬레이션 검증 — 골든 재추출(㉒) 뒤 어긋난 spec 을 한 번에 찾는다.

각 `templates/{cat}/{part}.spec.py` 에 대해:
  ① replace 를 골든 txt 에 순서대로 적용하며 old 미출현(MISS)을 센다
  ② 치환 결과의 토큰 집합 == expect 인지
  ③ U+2007(고정폭 공백)이 replace old 에 들어 있으면 경고 — **한글 찾기가 일반 공백과
     다르게 취급해 조용히 실패한다**(㉑ soil 실측). paras 로 라우팅할 것.
  ④ paras 앵커가 골든에 있는지 (참고용 — 원본 xml 에만 있는 앵커는 MISS 로 떠도 정상일 수 있다)

    python engine/spec_verify.py                 # 전부
    python engine/spec_verify.py env-impact      # 카테고리 하나

⚠️ 여기서의 MISS 는 **후보**다 — 머리글 전용 문자열(사업명)·원본 xml 에만 있는 문자열
   (`대안_8b`)은 txt 대조로 못 본다. 빌더 check(xml 병행)가 최종 판정이다.
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FW = " "


def load_spec(p):
    sp = importlib.util.spec_from_file_location("s", p)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m.SPEC


def verify(spec_path):
    cat, part = spec_path.parent.name, spec_path.name.replace(".spec.py", "")
    spec = load_spec(spec_path)
    src = re.sub(r"\s*\(.*\)$", "", spec["source"])           # 파생 표기 괄호 제거 (⑰ 함정)
    gold = ROOT / "golden" / cat / src / f"{part}.txt"
    if not gold.exists():
        for alt in (ROOT / "golden").glob(f"*/{src}/{part}.txt"):
            gold = alt
            break
    if not gold.exists():
        return (cat, part, "골든없음", 0, 0, 0, [])
    txt = gold.read_text(encoding="utf-8")
    ok_miss = set(spec.get("txt_miss_ok", ()))
    cur, miss, fw = txt, [], []
    for old, new in spec["replace"]:
        if old not in txt and old not in ok_miss:
            # 머리글 전용 사업명은 추출 txt 에 안 잡힌다 (dry-run 검사 예외 — 소환 climate 주석)
            if new.strip() == "{{사업명}}":
                pass
            else:
                miss.append(old[:36])
        if FW in old:
            fw.append(new[:24])
        cur = cur.replace(old, new)
    for old in ok_miss:                        # xml 전용 문자열 — 토큰 집합 계산에는 참여시킨다
        for o, n in spec["replace"]:
            if o == old:
                cur += " " + n
    if any(n.strip() == "{{사업명}}" and o not in txt for o, n in spec["replace"]):
        cur += " {{사업명}}"
    toks = set(re.findall(r"\{\{(\w+)\}\}", cur))
    toks |= {t for _, n in spec.get("paras", []) for t in re.findall(r"\{\{(\w+)\}\}", n)}
    exp = set(spec["expect"])
    para_miss = [o[:24] for o, _ in spec.get("paras", []) if o not in txt]
    return (cat, part, "OK" if not miss and toks == exp and not fw else "확인",
            len(miss), len(exp - toks) + len(toks - exp), len(fw),
            miss[:3] + (["expect≠토큰: " + str(sorted((toks ^ exp))[:4])] if toks != exp else [])
            + [f"U+2007 in replace: {x}" for x in fw[:2]] + [f"paras 앵커 txt 미출현: {x}" for x in para_miss[:2]])


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else None
    bad = total = 0
    for sp in sorted(ROOT.glob("templates/*/*.spec.py")):
        if want and sp.parent.name != want:
            continue
        cat, part, v, m, t, f, notes = verify(sp)
        total += 1
        flag = "  " if v == "OK" else "✗ "
        if v != "OK":
            bad += 1
            print(f"{flag}{cat}/{part}: MISS {m} · expect차 {t} · fw {f}")
            for n in notes:
                print(f"     · {n}")
    print(f"\n{total} spec 중 확인 필요 {bad}")


if __name__ == "__main__":
    main()

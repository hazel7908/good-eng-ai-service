#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비우기 앵커 후보 제안 — 베이스의 표를 훑어 **아직 아무 앵커도 안 닿는 표**를 보여 준다.

`untouched_tables` 는 산출물에서 "손대지 않은 표"를 캡션으로 알려 준다. 그다음이 늘
막혔다 — 그 표를 어떤 문자열로 잡을 것인가. 캡션은 표 밖이라 앵커가 못 되고
(`anchor_check` 참조), 머리 셀은 줄바꿈으로 갈려 있기 일쑤다.

이 도구는 베이스에서 표마다
  · 바로 앞 캡션 문단
  · 머리행 셀들 중 **한 문단 안에 온전히 있고 문서에서 드물게 나오는** 것
  · 이미 닿는 BLANK 앵커가 있는지
를 뽑아 준다. 고를 수 있는 것만 고르게 하는 것이 요점이다.

  python engine/anchor_suggest.py <카테고리> <파트> [--all]
"""
import importlib.util
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwp_util import console_utf8  # noqa: E402
import anchor_check as AC          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def blank_anchors(cat, part):
    f = ROOT / "engine" / "parts" / cat / f"{part}.py"
    if not f.exists():
        return []
    spec = importlib.util.spec_from_file_location("h", f)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except Exception:
        return []
    return [a for a, *_ in (getattr(m, "BLANK", None) or [])]


def main():
    console_utf8()
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cat, part = sys.argv[1], sys.argv[2]
    show_all = "--all" in sys.argv
    base = ROOT / "templates" / cat / f"{part}.hwpx"
    z = zipfile.ZipFile(base)
    xml = "".join(z.read(n).decode("utf-8", "replace")
                  for n in sorted(z.namelist()) if AC.SEC.match(n))

    paras = AC.paragraphs(base)
    freq = {}
    for t, intbl in paras:
        if intbl:
            freq[t.strip()] = freq.get(t.strip(), 0) + 1

    anchors = blank_anchors(cat, part)
    caps = [(m.start(), AC._unesc("".join(re.findall(r"<hp:t>(.*?)</hp:t>", m.group(0), re.S))))
            for m in re.finditer(r"<hp:p\b(?:(?!<hp:p\b).)*?</hp:p>", xml, re.S)]

    n_hit = n_miss = 0
    for tm in re.finditer(r"<hp:tbl\b.*?</hp:tbl>", xml, re.S):
        blk, start = tm.group(0), tm.start()
        cells = {}
        for c in re.finditer(r"<hp:tc\b.*?</hp:tc>", blk, re.S):
            b = c.group(0)
            a = re.search(r'colAddr="(\d+)"[^>]*rowAddr="(\d+)"', b)
            if not a:
                continue
            ps = [AC._unesc("".join(re.findall(r"<hp:t>(.*?)</hp:t>", pm.group(0), re.S)))
                  for pm in re.finditer(r"<hp:p\b(?:(?!<hp:p\b).)*?</hp:p>", b, re.S)]
            cells.setdefault(int(a.group(2)), []).append(
                (int(a.group(1)), [x.strip() for x in ps if x.strip()]))
        if not cells:
            continue
        flat = " ".join(t for r in cells.values() for _, ps in r for t in ps)
        hit = [a for a in anchors if a in flat]
        if hit and not show_all:
            n_hit += 1
            continue
        n_miss += 1
        cap = next((t.strip() for p, t in reversed(caps) if p < start and t.strip()), "")
        print(f"\n▸ {cap[:70]}")
        if hit:
            print(f"   (이미 닿음: {hit})")
        # 머리 두 행에서 앵커 후보 — 문단 하나로 온전하고 문서 안에서 드문 것
        cand = []
        for r in sorted(cells)[:2]:
            for _, ps in sorted(cells[r]):
                for t in ps:
                    if 2 <= len(t) <= 24 and freq.get(t, 9) <= 2 and not t.isdigit():
                        cand.append((freq.get(t, 9), t))
        seen, out = set(), []
        for f_, t in sorted(cand):
            if t not in seen:
                seen.add(t)
                out.append(f"{t!r}({f_})")
        print("   후보:", ", ".join(out[:6]) or "(없음 — 머리 셀이 전부 흔하거나 쪼개짐)")
        print("   머리:", " | ".join("".join(ps) for _, ps in sorted(cells[sorted(cells)[0]]))[:100])
    print(f"\n닿는 표 {n_hit} · 아직 안 닿는 표 {n_miss}")


if __name__ == "__main__":
    main()

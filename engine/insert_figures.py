#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""삽도 삽입 — `figures/` 의 PNG 를 생성물의 해당 자리에 갈아 끼운다.

    python engine/insert_figures.py small-env regional-overview 천안_화덕리

맥이 만든 그림을 윈도우에서 넣고 눈으로 확인하는 인계 지점이다
(→ `docs/20260825_삽도_명세_지역개황.md`).

## 자리를 어떻게 찾나

`BinData` 번호는 **사업마다 달라진다** — 한글이 저장할 때 다시 매기기 때문이다.
그래서 번호를 박아 두지 않고 **캡션으로 찾는다**: `<hp:pic>` 블록 바로 뒤
문단이 그 그림의 캡션이다 (`_category.md` 3단 구조).

## 액자 비율

BinData 를 갈아 끼우면 그림이 **기존 액자 크기에 맞춰 늘어난다.** 액자 비율과
그림 비율이 10% 넘게 어긋나면 경고한다 — 찌그러진 채로 나가면 눈으로만 잡힌다.
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 파일명 → 캡션에 들어 있어야 할 말 (rule `regional-overview.md` §1 삽도 6종)
FIGURES = {
    "생태자연도": "생태·자연도",
    "식생보전등급도": "식생보전등급도",
    "수계흐름모식도": "수계흐름모식도",
    "수계도": "수계도",
    "정온시설도": "정온시설 및 개발시설",
    "지역개황도": "지역개황도",
}


def pic_slots(hwpx):
    """`{캡션: (imageN, 액자 가로, 액자 세로)}` — 캡션은 그림 바로 뒤 문단."""
    z = zipfile.ZipFile(hwpx)
    sec = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                  if re.match(r"Contents/section\d+\.xml$", n))
    out = {}
    for m in re.finditer(r"<hp:pic\b.*?</hp:pic>", sec, re.S):
        blk = m.group(0)
        i = re.search(r'binaryItemIDRef="(image\d+)"', blk)
        sz = re.search(r'<hp:sz\s+width="(\d+)"[^>]*height="(\d+)"', blk)
        if not (i and sz):
            continue
        tail = sec[m.end():m.end() + 1200]
        caps = [re.sub(r"<[^>]*>", "", t).strip()
                for t in re.findall(r"<hp:t>(.*?)</hp:t>", tail, re.S)]
        # ⚠️ 캡션이 **출처 주석 뒤**에 오는 그림이 있다 (수계도).
        #    `자)`·`주)` 로 시작하는 줄은 건너뛴다.
        cap = next((c for c in caps
                    if c and not c.startswith(("자)", "주)"))), "")
        out.setdefault(cap, (i.group(1), int(sz.group(1)), int(sz.group(2))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category")
    ap.add_argument("part")
    ap.add_argument("case")
    a = ap.parse_args()

    base = ROOT / "cases" / a.category / a.case / a.part
    out, figdir = base / "output.hwpx", base / "figures"
    if not out.exists():
        sys.exit(f"생성물 없음 — {out}")
    if not figdir.is_dir():
        sys.exit(f"삽도 폴더 없음 — {figdir}\n  맥에서 만든 PNG 를 여기 두면 된다 "
                 f"(docs/20260825_삽도_명세_지역개황.md §4)")

    from PIL import Image
    slots = pic_slots(out)
    img_map, warn = {}, 0
    for stem, kw in FIGURES.items():
        png = figdir / f"{stem}.png"
        if not png.exists():
            print(f"  {stem:14} — 파일 없음, 건너뜀")
            continue
        hit = next(((c, v) for c, v in slots.items() if kw in c), None)
        if not hit:
            print(f"  {stem:14} ⚠️ 캡션 '{kw}' 을 문서에서 못 찾았다")
            warn += 1
            continue
        cap, (iid, fw, fh) = hit
        iw, ih = Image.open(png).size
        want, got = fw / fh, iw / ih
        if abs(want - got) / want > 0.10:
            print(f"  {stem:14} ⚠️ 액자 비율 {want:.2f} ↔ 그림 비율 {got:.2f} "
                  f"— **찌그러진다.** 권장 {round(iw * want / got)}x{ih}")
            warn += 1
        # 확장자는 문서에 실린 것을 그대로 쓴다 (내용은 PNG 로 넣는다)
        real = next((n for n in zipfile.ZipFile(out).namelist()
                     if n.lower().startswith(f"bindata/{iid.lower()}.")), None)
        if not real:
            print(f"  {stem:14} ⚠️ {iid} 항목을 찾지 못했다")
            warn += 1
            continue
        img_map[real] = str(png)
        print(f"  {stem:14} → {real}  액자 {fw/7200*25.4:.0f}x{fh/7200*25.4:.0f}mm")

    if not img_map:
        sys.exit("\n넣을 그림이 없다.")
    sys.path.insert(0, str(ROOT / "engine"))
    from hwp_util import replace_images, check_figures
    print()
    replace_images(str(out), img_map)
    check_figures(str(out), str(ROOT / "templates" / a.category / f"{a.part}.hwpx"))
    if warn:
        print(f"\n⚠️ 경고 {warn}건 — PDF 로 눈으로 확인할 것 "
              f"(`python engine/to_pdf.py {out}`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLANK 앵커 정적 검사 — 베이스 HWPX 에 **찾을 수 있는 문자열로 존재하는가**.

🚨 2026-09-08 실측: `지반고EL(+)m` 은 셀 안에 있는데도 영원히 안 잡힌다 —
그 칸이 `지반고` / `EL(+)m` **두 문단**이라 한글 찾기가 경계를 못 넘는다.
평면화한 추출 텍스트로 앵커를 고르면 반드시 밟는 함정이다(CLAUDE.md §6 같은 뿌리).

앵커가 안 잡히면 `blank_tables` 는 0을 돌려주고 **기준 사업 값이 그대로 남는다.**
생성은 성공으로 끝나고 게이트도 통과한다 — 그래서 실행 전에 정적으로 본다.

  python engine/anchor_check.py [카테고리]
종료코드 1 = 못 찾는 앵커 있음.
"""
import importlib.util
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwp_util import console_utf8  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEC = re.compile(r"Contents/section\d+\.xml$")


def _unesc(s: str) -> str:
    return (re.sub(r"<[^>]+>", "", s).replace("&lt;", "<")
            .replace("&gt;", ">").replace("&amp;", "&"))


def paragraphs(hwpx: Path):
    """(문단 텍스트, 표 안인가) 목록.

    한글 찾기는 **문단**을 넘지 못하고, `find_in_table` 은 **표 안**만 인정한다.
    두 조건을 따로 봐야 `공내지하수위`(캡션이라 표 밖)와
    `지반고EL(+)m`(칸 안이지만 두 문단)을 구별해 말해 줄 수 있다.

    ⚠️ **알려진 한계** (2026-09-09) — 문단 안에 바닥글·각주가 `<hp:ctrl>` 로 끼면
    비탐욕 매칭이 거기서 끊겨 **한 문장을 둘로 쪼갠 것처럼** 보인다. 실측 오탐은
    2,295건 중 1건(본환 저감 파트 도입 문장). 고치려고 두 가지를 시도했다가 **둘 다
    되돌렸다**: ①`<hp:ctrl>` 통째 제거 → **표가 그 안에 있어** 앵커들이 표 밖으로 둔갑
    ②바닥글·머리글만 제거 → **머리글에도 진짜 치환 대상(사업명)이 있어** 오탐이 11+34로
    늘었다. 오탐 1건을 알고 쓰는 편이 낫다 — 고치려면 문단 깊이 파싱을 제대로 해야 한다.
    """
    z = zipfile.ZipFile(hwpx)
    xml = "".join(z.read(n).decode("utf-8", "replace")
                  for n in sorted(z.namelist()) if SEC.match(n))
    # ⚠️ 표 안 판정은 **깊이**로 센다. `<hp:tc>...</hp:tc>` 를 비탐욕 매칭하면
    #    중첩표에서 바깥 칸이 안쪽 닫힘에 먼저 끊겨 뒷부분이 "표 밖"으로 둔갑한다.
    depth, marks = 0, []
    for m in re.finditer(r"<(/?)hp:tc\b", xml):
        depth += -1 if m.group(1) else 1
        marks.append((m.start(), depth))

    def in_table(i):
        d = 0
        for pos, dep in marks:
            if pos > i:
                break
            d = dep
        return d > 0

    out = []
    for m in re.finditer(r"<hp:p\b(?:(?!<hp:p\b).)*?</hp:p>", xml, re.S):
        runs = re.findall(r"<hp:t>(.*?)</hp:t>", m.group(0), re.S)
        if not runs:
            continue
        out.append((_unesc("".join(runs)), in_table(m.start())))
    return out


def load_blank(py: Path):
    spec = importlib.util.spec_from_file_location(py.stem.replace("-", "_"), py)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except Exception as e:                       # 핸들러가 깨져 있으면 그것부터 알린다
        return None, f"{type(e).__name__}: {e}"
    return getattr(m, "BLANK", None) or [], None


def main():
    console_utf8()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    bad = defaultdict(list)
    n_anchor = n_part = 0
    for py in sorted(ROOT.glob("engine/parts/*/*.py")):
        cat = py.parent.name
        if only and cat != only:
            continue
        base = ROOT / "templates" / cat / f"{py.stem}.hwpx"
        if not base.exists():
            continue
        blank, err = load_blank(py)
        if err:
            bad[f"{cat}/{py.stem}"].append(("(핸들러 로드 실패)", err))
            continue
        if not blank:
            continue
        n_part += 1
        paras = paragraphs(base)
        for anchor, *_ in blank:
            n_anchor += 1
            if any(anchor in t and intbl for t, intbl in paras):
                continue
            if any(anchor in t for t, _ in paras):
                why = "표 밖(캡션·본문) — find_in_table 이 안 본다"
            elif anchor in re.sub(r"\s", "", "".join(t for t, _ in paras)):
                why = "문단 경계로 쪼개짐 — 찾기가 못 넘는다"
            else:
                why = "베이스에 없음"
            bad[f"{cat}/{py.stem}"].append((anchor, why))

    print(f"검사 {n_part}파트 · 앵커 {n_anchor}개")
    if not bad:
        print("못 찾는 앵커 0 ✅")
        return 0
    tot = sum(len(v) for v in bad.values())
    print(f"🚨 못 찾는 앵커 {tot}개 — 그 표는 기준 사업 값이 그대로 남는다\n")
    for loc, items in sorted(bad.items()):
        print(f"  {loc}")
        for a, why in items:
            print(f"     {a!r:44s} {why}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

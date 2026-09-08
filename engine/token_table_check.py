#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비우기 앵커가 **spec 이 채우는 표**를 겨누고 있지 않은가 (anchor_check 의 거울상).

🚨 2026-09-08 실측: 본환 소음진동 조사지점 표에 앵커를 달았더니, 그 표는 내용이
   `{{NV1_주소}}`·`{{NV1_지역}}` 토큰이라 **비우기가 spec 이 채운 값을 도로 지운다.**
   되먹임으로는 영원히 안 드러난다 — 채운 값이 곧 기준 사업 값이라 지워도 티가 안 난다.

토큰이 라벨 한둘로 섞인 표(`하천명 | {{하천1_명}}` + 숫자 데이터)는 비워도 된다.
그래서 **비율**로 가른다 — 데이터 칸 중 토큰 칸이 임계 이상이면 경고한다.

⚠️ **이 검사는 문자열 포함만 본다 — limit 과 문서 순서는 못 본다.** 같은 앵커가
   `limit` 안에서 어느 표에 닿는지는 실행해 봐야 안다. 그래서 경고는 "이 앵커가
   토큰 표에 닿을 수 있다"까지고, 확정은 되먹임이 아니라 **다른 사업 산출물에서
   spec 값이 살아 있는지**로 한다.

  python engine/token_table_check.py [카테고리] [--ratio 0.3]
종료코드 1 = 경고 있음.
"""
import importlib.util
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwp_util import console_utf8  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEC = re.compile(r"Contents/section\d+\.xml$")
TOK = re.compile(r"\{\{[0-9A-Za-z_가-힣]{1,40}\}\}")


def main():
    console_utf8()
    only = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    ratio = 0.30
    if "--ratio" in sys.argv:
        ratio = float(sys.argv[sys.argv.index("--ratio") + 1])
    warn = 0
    for py in sorted(ROOT.glob("engine/parts/*/*.py")):
        cat, part = py.parent.name, py.stem
        if only and cat != only:
            continue
        base = ROOT / "templates" / cat / f"{part}.hwpx"
        if not base.exists():
            continue
        sp = importlib.util.spec_from_file_location("h", py)
        m = importlib.util.module_from_spec(sp)
        try:
            sp.loader.exec_module(m)
        except Exception:
            continue
        blank = getattr(m, "BLANK", None) or []
        if not blank:
            continue
        z = zipfile.ZipFile(base)
        xml = "".join(z.read(n).decode("utf-8", "replace")
                      for n in sorted(z.namelist()) if SEC.match(n))
        for tm in re.finditer(r"<hp:tbl\b.*?</hp:tbl>", xml, re.S):
            cells = [re.sub(r"<[^>]+>", "", c.group(0)).strip()
                     for c in re.finditer(r"<hp:tc\b.*?</hp:tc>", tm.group(0), re.S)]
            filled = [c for c in cells if c]
            if not filled:
                continue
            tok = [c for c in filled if TOK.search(c)]
            r = len(tok) / len(filled)
            if r < ratio:
                continue
            flat = " ".join(filled)
            hit = [a for a, *_ in blank if a in flat]
            if not hit:
                continue
            warn += 1
            print(f"  🚨 {cat}/{part}  앵커 {hit}")
            print(f"      칸 {len(filled)}개 중 토큰 {len(tok)}개 ({r:.0%}) — "
                  f"비우면 spec 이 채운 값을 지운다")
            print(f"      {sorted(set(TOK.findall(flat)))[:5]}")
    print(f"\n  경고 {warn}건 (임계 {ratio:.0%})")
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())

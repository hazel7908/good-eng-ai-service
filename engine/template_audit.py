#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""베이스 오염 점검 — spec 이 뚫으라는 토큰이 실제 베이스에 있는가.

🚨 **베이스가 생성물로 덮이는 사고가 있었다** (2026-09-08 적발). 소환 대기질 베이스는
   08-06 커밋에서 토큰 19종 → 0 이 되고 평창 값이 박힌 채 **한 달을 갔다.**
   ⚠️ **어떤 게이트도 못 잡는다** — 토큰이 없으면 `빈칸 잔여 0` 이 늘 초록이다.
   생성은 `.work.hwpx` 사본을 열도록 고쳤지만(재발 방지), **이미 오염된 것**은
   따로 찾아야 한다. spec 의 기대 토큰과 베이스 실물을 대조한다.

사용: python engine/template_audit.py [카테고리]
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOK = re.compile(r"\{\{([0-9A-Za-z_가-힣]{1,40})\}\}")


def tokens(hwpx):
    z = zipfile.ZipFile(hwpx)
    xml = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                  if re.match(r"Contents/section\d+\.xml$", n))
    return set(TOK.findall(re.sub(r"<[^>]+>", "", xml)))


def spec_expect(spec_path):
    """spec 의 `expect` 목록 — 실행하지 않고 원문에서 뽑는다(부작용·의존성 회피)."""
    t = spec_path.read_text(encoding="utf-8")
    m = re.search(r'"expect"\s*:\s*\[(.*?)\]', t, re.S)
    if m:
        return set(re.findall(r'["\']([^"\']+)["\']', m.group(1)))
    # expect 가 없으면 replace 목표 문자열의 토큰을 센다
    return set(TOK.findall(t))


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    bad = 0
    print("# 베이스 오염 점검 — spec 기대 토큰 vs 베이스 실물\n")
    for spec in sorted((ROOT / "templates").glob("*/*.spec.py")):
        cat, part = spec.parent.name, spec.name[:-8]
        if only and cat != only:
            continue
        tpl = spec.parent / f"{part}.hwpx"
        if not tpl.exists():
            continue
        want, have = spec_expect(spec), tokens(tpl)
        miss = want - have
        if not want:
            continue
        ratio = len(have & want) / len(want)
        flag = "🚨" if ratio < 0.5 else ("⚠️" if miss else "  ")
        if miss:
            bad += 1
            print(f"{flag} {cat}/{part:24} spec {len(want):3} · 베이스 {len(have):3} · "
                  f"없는 토큰 {len(miss)}")
            for k in sorted(miss)[:6]:
                print(f"     - {{{{{k}}}}}")
            if len(miss) > 6:
                print(f"     … 외 {len(miss) - 6}종")
    print(f"\n토큰이 빠진 베이스 {bad}종" + ("" if bad == 0 else "  ← 오염 의심"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

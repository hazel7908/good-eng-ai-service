# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""표 **셀 단위** 잔존값 대조 — `table_leak` 의 '표동일' 이 놓치는 부분 잔존을 본다.

사용: python engine/table_residual.py <카테고리> <파트> <사업>
      python engine/table_residual.py --files <베이스.hwpx> <산출물.hwpx>

🚨 왜 필요한가 (2026-09-09 검토서 3장 옥계리 실증)
`table_leak` 의 ②-2 는 **표 전체가 베이스와 같을 때** ⚠️ 를 낸다. 그런데 실제 결함은
`header_rows` 가 한 행 어긋나거나 행 예산이 모자라 **첫 데이터 행만 / 뒤쪽 절반만** 남는
꼴로 나온다 — 표는 "달라졌으므로" 검사를 조용히 통과한다. 옥계리에서 이 대조가
`table_leak` 통과분 너머로 **10표를 더 잡았다**: 이재민 `11·29` 한 행 · 재해이력
`2011(7.26-7.29) … 189,999` · 하천재해 위험지구 **11행**(21행짜리가 9행에서 잘렸다) ·
표고/경사/토양 분석 5표 · 주민탐문 면담자 인적사항.

🔎 `base_residue.py` 와 짝이지 겹치지 않는다 — 저쪽은 **베이스**를 지명(문자)으로 훑고,
이쪽은 **베이스↔산출물**을 숫자(값)로 대조한다. 지명이 안 든 순수 수치 잔존
(`64,223㎡`·이재민 `11·29`)은 이쪽에서만 보인다.

판정: 베이스와 산출물의 표를 **머리행(r0) 서명**으로 짝짓고, 데이터 행(r>0)에서
`(행번호, 셀 텍스트)` 가 **그대로 같고 숫자를 품은** 칸을 잔존으로 본다.
`[확인 필요]`·`-` 는 제외한다.

⚠️ **잔존 = 결함이 아니다.** 법령 조문·문헌 분류표·전국 기준표는 같은 것이 정답이다
(옥계리 잔여 7표가 전부 그 부류). 사람이 표 이름을 보고 가른다 — 이 도구는
**볼 자리를 줄여 주는 것**이지 판정하지 않는다. 되먹임(기준 사업 자기 생성)에는
원리상 무의미하다(값이 자기 것이라 전부 잔존으로 뜬다).
"""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hwp_util import console_utf8          # noqa: E402

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
DIGIT = re.compile(r"[0-9]")
ROOT = Path(__file__).parent.parent


def _cell_text(tc):
    return "\n".join("".join(t.text or "" for t in p.iter(f"{{{HP}}}t"))
                     for p in tc.iter(f"{{{HP}}}p")).strip()


def tables(path):
    """(행번호, 셀 텍스트) 목록을 표마다 돌려준다 — 구조는 `cellAddr` 직독."""
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            if not re.match(r"Contents/section\d+\.xml$", name):
                continue
            for tbl in ET.fromstring(zf.read(name)).iter(f"{{{HP}}}tbl"):
                cells = []
                for tc in tbl.iter(f"{{{HP}}}tc"):
                    addr = tc.find(f"{{{HP}}}cellAddr")
                    if addr is not None:
                        cells.append((int(addr.get("rowAddr")), _cell_text(tc)))
                yield cells


def _sig(cells):
    return " | ".join(t for r, t in cells if r == 0)[:120]


def compare(base_path, out_path, show=14):
    base = {}
    for cells in tables(base_path):
        base.setdefault(_sig(cells), []).append(cells)
    hits = 0
    for cells in tables(out_path):
        cand = base.get(_sig(cells))
        if not cand:
            continue                       # 베이스에 없는 표(새로 만든 표) — 대조 불가
        same_as = {(r, t) for r, t in cand[0] if r > 0}
        left = [(r, t) for r, t in cells
                if r > 0 and (r, t) in same_as
                and DIGIT.search(t) and "확인 필요" not in t and t != "-"]
        if left:
            hits += 1
            print(f"■ {_sig(cells)[:90]}".replace("\n", "/"))
            print("   잔존:", " · ".join(f"r{r}:{t[:24]}" for r, t in left[:show]).replace("\n", "/"))
    print(f"\n표 {hits}개에 기준 사업 값 잔존 (숫자 든 셀 기준) "
          f"— 법령·문헌 고정표는 정상이다. 표 이름으로 가를 것")
    return hits


def main():
    console_utf8()
    a = sys.argv[1:]
    if a[:1] == ["--files"] and len(a) == 3:
        compare(a[1], a[2])
        return
    if len(a) != 3:
        sys.exit(__doc__)
    cat, part, case = a
    compare(ROOT / "templates" / cat / f"{part}.hwpx",
            ROOT / "cases" / cat / case / part / "output.hwpx")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
HWPX 에서 표를 읽는다 — **읽기 전용**.

전국 통계가 전부 엑셀은 아니다. 수변구역·생태경관보전지역·습지 지정현황은
**한글 문서로 배포**된다 (`.hwpx`). 그 표를 값으로 꺼내야 한다.

⚠️ `rules/hwpx.md` 의 **"Python XML 직접 조작 금지"** 는 **쓰기**에 대한 것이다
(재직렬화하면 네임스페이스가 깨져 한글이 파일을 거부한다). 여기는 **읽기만** 한다 —
파일을 열지도 고치지도 않는다.

    python engine/hwpx_table.py <파일.hwpx>            # 표 목록
    python engine/hwpx_table.py <파일.hwpx> --table 0  # 한 표 펼치기
"""
import argparse
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}


def _cell_text(tc):
    """셀 안의 모든 문자열을 잇는다. 줄바꿈은 공백으로."""
    parts = [t.text or "" for t in tc.iter(f"{{{NS['hp']}}}t")]
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def tables(path):
    """HWPX 의 모든 표를 `[[셀…]…]` 로 돌려준다. 본문 순서대로."""
    out = []
    with zipfile.ZipFile(path) as z:
        secs = sorted(n for n in z.namelist()
                      if re.fullmatch(r"Contents/section\d+\.xml", n))
        for name in secs:
            root = ET.fromstring(z.read(name))
            for tbl in root.iter(f"{{{NS['hp']}}}tbl"):
                rows = []
                for tr in tbl.iter(f"{{{NS['hp']}}}tr"):
                    rows.append([_cell_text(tc)
                                 for tc in tr.iter(f"{{{NS['hp']}}}tc")])
                if rows:
                    out.append(rows)
    return out


def pick(path, must_have, min_rows=2):
    """머리글에 `must_have` 가 다 들어 있는 표를 고른다.

    한 문서에 표가 여럿이라(설명표·범례) 이름으로 골라야 한다.
    """
    for t in tables(path):
        if len(t) < min_rows:
            continue
        head = " ".join(t[0] + (t[1] if len(t) > 1 else []))
        if all(re.search(k, head) for k in must_have):
            return t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hwpx")
    ap.add_argument("--table", type=int)
    ap.add_argument("--rows", type=int, default=8)
    a = ap.parse_args()
    ts = tables(a.hwpx)
    if a.table is None:
        print(f"표 {len(ts)}개")
        for i, t in enumerate(ts):
            w = max(len(r) for r in t)
            print(f"  [{i}] {len(t)}행 × 최대 {w}열 | 첫 행: {' | '.join(t[0])[:90]}")
        return 0
    for r in ts[a.table][:a.rows]:
        print(" | ".join(c[:28] for c in r))
    return 0


if __name__ == "__main__":
    sys.exit(main())

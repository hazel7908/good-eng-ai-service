#!/usr/bin/env python3
"""볼드(강조) 런 지명 검사 — 텍스트 추출로는 안 보이는 서식 유출을 잡는다.

배경(2026-09-07, PDF 육안 ② 설계 판단): 저황유 표처럼 **해당 시군 행만 볼드**로
강조하는 표가 있다. 빈칸 치환·표 비우기는 텍스트만 다루므로 기준 사업 지명이
강조된 채 남아도 leak_check·table_leak·되먹임 전부 못 본다 — 검사와 수정은 다른
근거 원칙대로 **XML charPr 직독**으로 감시한다(수정은 자동화하지 않는다 —
fill-report 의 '강조 행 확인' 몫).

사용:
  python engine/bold_check.py <hwpx> <지명 정규식>
  python engine/bold_check.py templates/strategic-env/regional-overview.hwpx "제천|수산면"

출력: 볼드 런 중 정규식 매치 목록(전후 문맥). 종료코드 1 = 매치 있음.
"""
import re
import sys
import zipfile

BOLD_ID = re.compile(r'<hh:charPr id="(\d+)".*?</hh:charPr>', re.S)
RUN = re.compile(r'<hp:run charPrIDRef="(\d+)"[^>]*>(.*?)</hp:run>', re.S)
T = re.compile(r"<hp:t[^>]*>([^<]*)</hp:t>")


def bold_texts(hwpx: str):
    with zipfile.ZipFile(hwpx) as z:
        hdr = z.read("Contents/header.xml").decode("utf-8")
        secs = [z.read(n).decode("utf-8") for n in z.namelist()
                if re.match(r"Contents/section\d+\.xml$", n)]
    bold = {m.group(1) for m in BOLD_ID.finditer(hdr) if "<hh:bold/>" in m.group(0)}
    out = []
    for sec in secs:
        for m in RUN.finditer(sec):
            if m.group(1) in bold:
                txt = "".join(T.findall(m.group(2)))
                if txt.strip():
                    out.append(txt)
    return out


def check(hwpx: str, pattern: str) -> int:
    pat = re.compile(pattern)
    hits = []
    for txt in bold_texts(hwpx):
        if pat.search(txt):
            hits.append(txt.strip()[:80])
    if hits:
        print(f"⚠️ 볼드 강조에 지명 잔존 {len(hits)}건 — {hwpx}")
        for h in dict.fromkeys(hits):
            print(f"   {h}")
    else:
        print(f"✓ 볼드 지명 0 — {hwpx}")
    return 1 if hits else 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sys.exit(check(sys.argv[1], sys.argv[2]))

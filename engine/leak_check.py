# -*- coding: utf-8 -*-
"""기준 사업 유출 검사 — **베이스와 생성물에 같이 있는 값**을 찾는다.

지명 정규식(`원주|호저|…`)으로는 못 잡는다. `{{시군}}` 이 치환되고 나면
**숫자만 원주로 남기** 때문이다. 실제로 그렇게 5건이 숨어 있었다 (2026-08-25).

토큰이 뚫린 자리는 값이 바뀌므로 안 걸리고, **안 뚫린 자리만** 걸린다.

    python leak_check.py <베이스.hwpx> <생성물.hwpx>
"""
import re
import sys
import zipfile

NUM = re.compile(r"\d[\d,]*\.?\d*")
# 법령 고시 번호·개정일·축척은 사업과 무관하다
SKIP = re.compile(r"^(19|20)\d\d$|^(10|100|25,000|0\.\d+)$")


def paras(path):
    z = zipfile.ZipFile(path)
    xml = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                  if re.match(r"Contents/section\d+\.xml$", n))
    return ["".join(re.findall(r"<hp:t>(.*?)</hp:t>", p, re.S))
            for p in re.findall(r"<hp:p[ >].*?</hp:p>", xml, re.S)]


def strip_cite(t):
    """법령 인용을 지운다 — 고시번호·개정일은 사업과 무관한데 숫자가 많다.

    따옴표 안(`“…”`)과 괄호 안의 `제N호`·개정일이 대부분이다.
    이걸 안 지우면 오탐 12건이 실제 유출 5건을 묻어 버린다.
    """
    t = re.sub(r"[“\"][^”\"]*[”\"]", " ", t)     # 인용 부호 안
    t = re.sub(r"\([^)]*\)", " ", t)              # 괄호 안
    t = re.sub(r"<[^>]*>|&lt;[^&]*&gt;", " ", t)  # <표 2.10-1> 같은 참조
    t = re.sub(r"시설용량 \d+㎥/일", " ", t)         # 법정 기준값
    return t


def narrative(ls):
    """서술 문장만 — 표 셀은 짧고 종결어미가 없다."""
    return [x for x in ls if len(x) > 40 and re.search(r"(조사|확인|나타났|예측)되었다", x)]


def main():
    base, gen = sys.argv[1], sys.argv[2]
    tn, on = narrative(paras(base)), narrative(paras(gen))
    # ⚠️ 문턱을 3자리로 두면 `대기 31개소, 수질 17개소` 같은 **두 자리 유출을 놓친다**
    #    (2026-08-25 실측 — 배출시설·산업단지 두 문장이 그렇게 숨어 있었다).
    tnums = {m for x in tn for m in NUM.findall(strip_cite(x))
             if len(m.replace(",", "").replace(".", "")) >= 2 and not SKIP.match(m)}
    hits = []
    for x in on:
        common = sorted({m for m in NUM.findall(strip_cite(x)) if m in tnums})
        if common:
            hits.append((common, x))
    print(f"베이스 서술 {len(tn)}개 · 생성 서술 {len(on)}개 · 의심 {len(hits)}개\n")
    for common, x in hits:
        print(f"  ⚠️ {common}")
        print(f"     {x[:116]}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

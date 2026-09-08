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
    # 🚨 **런 사이 서식 태그가 문장에 섞인다** — 형광펜이 칠해진 문장에서
    #    `<hp:markpenBegin color="#FFFF00"/>` 가 그대로 들어와 `#FFFF00` 의 `00` 이
    #    숫자로 잡혔다 (충주 3장 지질도 문장, 09-03). 남은 태그를 벗긴다.
    return [re.sub(r"<[^>]+>", "", "".join(re.findall(r"<hp:t>(.*?)</hp:t>", p, re.S)))
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
    # ⚠️ **오염물질 이름에 든 숫자는 값이 아니다** — `PM-10`·`PM-2.5` 의 `10,`·`2.5` 가
    #    베이스·산출물 공통이라 유출로 잡혔다 (평창 대기질 09-03). 항목 표기를 지운다.
    t = re.sub(r"PM\s*-?\s*(?:10|2\.5)|NO\s*2|SO\s*2|O\s*3|CO|TSP", " ", t)
    # 법령 조문 번호 — `제55조`·`제4항`·`제1호` 는 사업과 무관하다 (충주 3장 방재시설 문장).
    t = re.sub(r"제\s*\d+\s*조(?:의\s*\d+)?|제\s*\d+\s*항|제\s*\d+\s*호", " ", t)
    return t


def narrative(ls):
    """서술 문장만 — 표 셀은 짧고 종결어미가 없다."""
    return [x for x in ls if len(x) > 40 and re.search(r"(조사|확인|나타났|예측)되었다", x)]


def headers(path):
    """머리말·꼬리말 블록 안 텍스트 — 어미 필터 없이 전수.

    🚨 fr() 은 머리말에 닿는데 검사기들이 머리말을 지우거나(표 파싱) 어미 필터로
    걸러서(서술 검사) **머리말 리터럴 유출이 게이트를 통과**했다
    (2026-09-08 Windows 실측 — 전략 natural-assets `{{계획명}}` 규약 누락 리터럴).
    검사와 수정은 다른 근거 — 여기서는 블록을 직접 떠서 본다."""
    z = zipfile.ZipFile(path)
    xml = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                  if re.match(r"Contents/section\d+\.xml$", n))
    out = []
    for blk in re.findall(r"<hp:(?:header|footer)[ >].*?</hp:(?:header|footer)>", xml, re.S):
        for p in re.findall(r"<hp:p[ >].*?</hp:p>", blk, re.S):
            t = re.sub(r"<[^>]+>", "", "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", p, re.S)))
            if t.strip():
                out.append(t.strip())
    return out


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
    # 머리말·꼬리말 — 실패 판정은 **치환 실패({{…}} 잔존)만**. 베이스의 비토큰 머리말은
    #  고정 문구일 수 있어 자동 판정하지 않고 목록으로 보여준다(리터럴 사업명이면
    #  베이스 규약 위반 — natural-assets 사고 부류를 사람이 한눈에 잡게).
    hleaks = [x for x in headers(gen) if "{{" in x]
    hb = sorted({x for x in headers(base) if "{{" not in x})
    print(f"베이스 서술 {len(tn)}개 · 생성 서술 {len(on)}개 · 의심 {len(hits)}개"
          + (f" · 머리말 치환실패 {len(hleaks)}건" if hleaks else "") + "\n")
    if hb:
        print("  [머리말 비토큰 — 리터럴 사업명 여부 확인] " + " | ".join(x[:40] for x in hb[:5]))
    for x in hleaks:
        print(f"  ⚠️ [머리말 치환실패] {x[:100]}")
    for common, x in hits:
        print(f"  ⚠️ {common}")
        print(f"     {x[:116]}")
    return 1 if hits or hleaks else 0


if __name__ == "__main__":
    sys.exit(main())

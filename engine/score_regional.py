#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지역개황 채점 — **항목 목록을 정답 문서에서 뽑는다.**

    python engine/score_regional.py 천안_화덕리 [--detail]

## 왜 이렇게 세는가

2026-08-25 에 채점의 **분모가 틀렸다**는 것이 드러났다. 그때까지 항목은
`템플릿의 토큰 개수` 였다. 토큰은 *우리가 뚫기로 한 자리*다 — 안 뚫은 자리는
분모에 없고, 그래서 점수가 **자기 사각지대를 못 봤다.**

실제로 도로·자동차·야생생물·설치제한·수변구역 다섯 문장이 기준 사업(원주) 값을
그대로 안고 나갔는데 `WRONG 0` 으로 보고됐다. 토큰이 아니라 세지 않았기 때문이다.

그래서 **정답 문서에서 항목을 뽑는다.** 사업마다 달라지는 자리는 셋이다.

    서술 문장 · 표 · 삽도

토큰은 따로 세지 않는다 — **문장이나 표 안에 살기 때문**이다. 따로 세면 이중
계산이고, 문장 단위로 세면 **안 뚫은 자리도 자동으로 분모에 들어온다.**

## 판정

| 판정 | 뜻 |
|---|---|
| OK | 값이 같다 |
| 문형 | 값은 같고 문장 형태가 다르다 (F-2 계열) |
| 일부 | 값 일부만 맞다 |
| WRONG | 값이 다르다 — **고쳐야 한다** |
| 확인필요 | `[확인 필요]` 로 비웠다 (자료 부재) |
| 없음 | 정답에 있는데 우리 문서에 없다 |
| 잉여 | 우리 문서에만 있다 (기준 사업에서 딸려온 절) |
"""
import argparse
import difflib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
END = re.compile(r"(조사|확인|나타났|예측)되었다")
SEC = re.compile(r"^(2\.\d+)(?:\.\d+)?[\s가-힣]")
NUM = re.compile(r"\d[\d,]*\.?\d*")
CHECK = "[확인 필요]"


def cite(t):
    """법령 인용을 지운다 — 고시번호·개정일은 사업과 무관한데 숫자가 많다."""
    t = re.sub(r"[“\"][^”\"]*[”\"]", " ", t)
    t = re.sub(r"[‘'][^’']*[’']", " ", t)      # 정답은 홑따옴표로도 인용한다
    t = re.sub(r"\([^)]*\)", " ", t)
    return re.sub(r"&lt;.*?&gt;|<[^>]*>", " ", t)


def nums(t):
    return {m for m in NUM.findall(cite(t)) if len(m.replace(",", "").replace(".", "")) >= 2}


def read_gen(case, part):
    """생성물 — hwpx 에서 문단 텍스트를 뽑는다 (txt 는 낡아 있을 수 있다)."""
    p = ROOT / "cases/small-env" / case / part / "output.hwpx"
    z = zipfile.ZipFile(p)
    xml = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                  if re.match(r"Contents/section\d+\.xml$", n))
    # ⚠️ **표 안 문단을 먼저 걷어낸다.** 표 셀도 `<hp:p>` 라, 안 걷어내면
    #    `[확인 필요]` 로 비운 셀 301개가 전부 "문장" 으로 잡힌다 (2026-08-25 실측).
    while True:
        n2 = re.sub(r"<hp:tbl[ >/](?:(?!<hp:tbl[ >/]).)*?</hp:tbl>", " ", xml, flags=re.S)
        if n2 == xml:
            break
        xml = n2
    return [re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", "".join(
        re.findall(r"<hp:t>(.*?)</hp:t>", q, re.S))))
        for q in re.findall(r"<hp:p[ >].*?</hp:p>", xml, re.S)]


def group(lines):
    """`2.N` 단위로 묶는다. 하위 절까지 쪼개면 제목 표기 차이로 짝이 어긋난다."""
    cur, d = "머리", {}
    for t in (x.strip() for x in lines):
        m = SEC.match(t)
        if m and len(t) < 40:
            cur = m.group(1)
        d.setdefault(cur, []).append(t)
    return d


def sentences(block):
    """⚠️ `[확인 필요]` 로 통째로 비운 문단은 **짧아서 빠진다.** 그러면 정답 문장이
    짝을 못 찾아 `없음` 으로 잡히는데, 실제로는 우리가 비운 자리다."""
    # ⚠️ 문턱을 35자로 두면 **짧은 문장이 통째로 빠진다** — 정답의
    #    `사업계획지구의 식생보전등급은 Ⅴ등급으로 조사되었다.` 가 30자다 (2026-08-25 실측).
    #    표 셀은 종결어미가 없어 END 필터가 막아 준다.
    return [t for t in block
            if (len(t) > 18 and END.search(t)) or (CHECK in t and len(t) < 19)]


def judge(o, g):
    a, b = nums(o), nums(g)
    r = difflib.SequenceMatcher(None, cite(o), cite(g)).ratio()
    if CHECK in o:
        return "확인필요", r
    if a == b:
        return ("OK", r) if r > 0.85 else ("문형", r)
    return ("일부", r) if (a & b) else ("WRONG", r)


def pair_up(og, gg):
    """한 `2.N` 묶음 안에서만 짝을 짓는다 — 구간을 좁혀야 엉뚱한 짝이 안 생긴다."""
    # ⚠️ 정답을 하나씩 훑으며 최선을 집으면 **앞 문장이 뒤 문장의 짝을 가져간다**.
    #    시군·면 문장처럼 형태가 닮은 쌍이 서로 엇갈린다 — 전체 후보를 유사도 순으로
    #    정렬해 높은 것부터 확정한다.
    cand = sorted(
        ((difflib.SequenceMatcher(None, cite(o), cite(g)).ratio(), i, j)
         for i, o in enumerate(og) for j, g in enumerate(gg)),
        reverse=True)
    uo, ug, out = set(), set(), []
    for r, i, j in cand:
        if r < 0.35 or i in uo or j in ug:
            continue
        uo.add(i); ug.add(j)
        out.append((og[i], gg[j]))
    # 남은 것끼리 **순서대로** 잇는다 — `[확인 필요]` 로 비운 문장은 유사도가
    # 낮아 짝을 못 찾는데, 그것은 `없음` 이 아니라 `확인필요` 다.
    ro = [i for i in range(len(og)) if i not in uo]
    rg = [j for j in range(len(gg)) if j not in ug]
    for i, j in zip(ro, rg):
        out.append((og[i], gg[j]))
    out += [(None, gg[j]) for j in rg[len(ro):]]
    out += [(og[i], None) for i in ro[len(rg):]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--part", default="regional-overview")
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()

    gold = ROOT / "golden/small-env" / a.case / f"{a.part}.txt"
    if not gold.exists():
        sys.exit(f"정답 없음 — {gold}")
    G = group(gold.read_text(encoding="utf-8").splitlines())
    O = group(read_gen(a.case, a.part))

    tally, rows = {}, []
    for sec in sorted(set(G) | set(O), key=lambda s: [int(x) for x in s[2:].split(".")]
                      if s.startswith("2.") else [99]):
        for o, g in pair_up(sentences(O.get(sec, [])), sentences(G.get(sec, []))):
            if g is None:
                v, r = "잉여", 0.0
            elif o is None:
                v, r = "없음", 0.0
            else:
                v, r = judge(o, g)
            tally[v] = tally.get(v, 0) + 1
            rows.append((sec, v, r, o, g))

    n = sum(tally.values())
    print(f"서술 문장 {n}항목  (정답 {sum(len(sentences(v)) for v in G.values())} · "
          f"생성 {sum(len(sentences(v)) for v in O.values())})\n")
    for k in ("OK", "문형", "일부", "WRONG", "확인필요", "없음", "잉여"):
        if tally.get(k):
            print(f"  {k:6} {tally[k]:>3}   {tally[k]/n*100:5.1f}%")
    good = tally.get("OK", 0) + tally.get("문형", 0)
    print(f"\n  값이 맞는 문장 {good}/{n} = {good/n*100:.1f}%")

    if a.detail or tally.get("WRONG"):
        print("\n── WRONG · 잉여 ──")
        for sec, v, r, o, g in rows:
            if v in ("WRONG", "잉여") or (a.detail and v != "OK"):
                print(f"  [{sec} {v}] 유사도 {r:.2f}")
                if o: print(f"     생성 {o[:104]}")
                if g: print(f"     정답 {g[:104]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

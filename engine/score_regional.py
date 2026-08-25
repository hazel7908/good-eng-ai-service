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
import json
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


# 절 → 그 절이 인용하는 통계 자료 (vars `_통계판` 의 키)
SEC_SOURCE = {"2.2": "지자체 통계연보", "2.5": "지자체 통계연보",
              "2.6": "상수도통계", "2.7": "하수도통계"}


def edition_state(case, sec):
    """그 절이 쓰는 통계가 **발행처 최신임이 확인됐는가**.

    `build_vars_regional.py` 가 생성 때 발행처를 확인하고 `_통계판.최신확인` 에 적는다.
    값이 정답지와 달라도 **최신이 확인된 자료면 우리가 틀린 게 아니다.**

    ⚠️ 다만 `확인됨` 이 곧 `옳다` 는 아니다 — 우리 값이 그 판 원자료와 맞는지
    (**역추적 실증**)는 원자료가 있는 쪽에서 따로 해야 한다. 그걸 빼면 진짜 오류가
    숨는다 — 매립에서 정답지 자릿수 오류가 그렇게 숨어 있었다.
    """
    src = SEC_SOURCE.get(sec)
    if not src:
        return None
    f = ROOT / "cases/small-env" / case / "vars/regional-overview.json"
    if not f.exists():
        return None
    e = json.loads(f.read_text(encoding="utf-8")).get("_통계판", {}).get(src, {})
    mark = str(e.get("최신확인", ""))
    if mark.startswith("✅"):
        return "판차이"          # 발행처 최신 확인 — 자료가 갱신된 것이다
    return "판미확인"             # 최신인지 모른다 — 옳은지도 모른다


def judge(o, g):
    a, b = nums(o), nums(g)
    r = difflib.SequenceMatcher(None, cite(o), cite(g)).ratio()
    if CHECK in o:
        return "확인필요", r
    # ⚠️ **정답 값을 다 담았으면 OK 다.** 우리 쪽에 값이 더 있는 것은 감점 사유가
    #    아니다 — 정답 txt 추출이 표 일부를 놓친 것이거나(법령표에서 실제로 나왔다)
    #    표에 행이 더 있는 정상 상황이다. `a == b` 만 OK 로 보면 **더 채울수록
    #    점수가 내려간다** (2026-08-26 정정).
    if b <= a:
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


# ============================================================
# 표 · 삽도
# ============================================================
def _top_tables(xml):
    """**최상위 표만** 잘라 낸다. 표 안에 표가 들어가면 비탐욕 정규식이
    바깥 여는 태그와 안쪽 닫는 태그를 짝지어 쓰레기를 만든다."""
    out, depth, start = [], 0, None
    for m in re.finditer(r"<hp:tbl[ >/]|</hp:tbl>", xml):
        if m.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                out.append((start, m.end()))
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return out


def _text(frag):
    return [re.sub(r"<[^>]*>", "", t).strip()
            for t in re.findall(r"<hp:t>(.*?)</hp:t>", frag, re.S)]


def tables_of(case, part):
    """생성물에서 (캡션, 셀 텍스트) 목록을 뽑는다.

    캡션은 표 **바로 앞 문단**이다 (`_category.md` 3단 구조: 서술 → 표 → 출처).
    ⚠️ 셀에 글자가 하나도 없는 표는 **삽도 액자**다 — 표로 세지 않는다.
    """
    p = ROOT / "cases/small-env" / case / part / "output.hwpx"
    z = zipfile.ZipFile(p)
    out = []
    for n in sorted(x for x in z.namelist()
                    if re.match(r"Contents/section\d+\.xml$", x)):
        xml = z.read(n).decode("utf-8")
        # ⚠️ 머리글·바닥글도 표로 짜여 있다 — 본문 표가 아니므로 걷어낸다.
        xml = re.sub(r'<hp:(header|footer)[ >].*?</hp:\1>', " ", xml, flags=re.S)
        pos = 0
        for a, b in _top_tables(xml):
            cells = [c for c in _text(xml[a:b]) if c]
            caps = [c for c in _text(xml[pos:a]) if c]
            pos = b
            if not cells:
                continue                      # 삽도 액자
            # ⚠️ `도로` 처럼 **짧은 소제목**이 캡션 자리에 걸린다 — 4자 미만은 건너뛴다.
            cap = next((c for c in reversed(caps)
                        if len(c) >= 4 and not c.startswith(("자)", "주)"))
                       and not re.match(r"^2\.\d", c)), "")
            out.append((cap, " ".join(cells)))
    return out


def gold_table(lines, cap, head=""):
    """정답 txt 에서 표를 찾아 `자)` 직전까지 가져온다.

    ⚠️ 유사도만 쓰면 놓친다 — 정답 캡션에는 `소음환경기준   (단위 : Leq dB(A))`
    처럼 **단위 표기가 붙는다.** 포함 관계를 먼저 본다.
    캡션이 비면(표 앞이 제목뿐) **머리행 첫 칸**으로 찾는다.
    """
    def norm(t):
        return re.sub(r"\s+", "", t)

    keys = [k for k in (cap, head) if k and len(norm(k)) >= 4]
    if not keys:
        return None
    bi, best = -1, 0.0
    for i, t in enumerate(lines):
        t = t.strip()
        if not t or len(t) > 80:
            continue
        nt = norm(t)
        for k in keys:
            nk = norm(k)
            r = difflib.SequenceMatcher(None, nt, nk).ratio()
            # ⚠️ 포함을 1.0 으로 쳐 주면 `도로` 같은 짧은 캡션이 아무 줄에나 걸린다.
            #    **가점**으로만 준다 — 길이가 충분할 때만.
            if len(nk) >= 6 and nk in nt:
                r = min(1.0, r + 0.3)
            if r > best:
                best, bi = r, i
    if bi < 0 or best < 0.6:
        return None
    body = []
    for t in lines[bi + 1:]:
        t = t.strip()
        if t.startswith(("자)", "주)")) or (body and re.match(r"^2\.\d", t)):
            break
        body.append(t)
        if len(body) > 400:
            break
    return " ".join(body)


# 표 캡션 → 절. 판이 갈리는 표만 적는다.
TBL_SEC = {"지목별 토지이용": "2.2", "용도지역 현황": "2.2", "도로현황": "2.5",
           "자동차 등록현황": "2.5", "문화재": "2.5",
           "취수장": "2.6", "정수장": "2.6",
           "공공하수처리시설": "2.7", "분뇨처리시설": "2.7",
           "음식물류": "2.7", "매립처리시설": "2.7"}


def score_tables(case, part, gold_lines):
    tally, rows = {}, []
    for cap, cells in tables_of(case, part):
        head = " ".join(cells.split()[:3])      # 머리행 앞부분 — 캡션이 없을 때 쓴다
        g = gold_table(gold_lines, cap, head)
        a = {m for m in NUM.findall(cite(cells)) if len(m.replace(",", "").replace(".", "")) >= 2}
        if g is None:
            v = "잉여"
        else:
            b = {m for m in NUM.findall(cite(g)) if len(m.replace(",", "").replace(".", "")) >= 2}
            if not a and not b:
                v = "OK"                      # 값 없는 법령표·머리표
            elif CHECK in cells and not (a & b):
                v = "확인필요"
            elif b <= a and a:          # 정답 값을 다 담았다 — 더 있어도 감점 아니다
                v = "OK"
            elif a & b:
                v = "일부"
            else:
                v = "WRONG"
        if v in ("WRONG", "일부"):
            sec = next((x for k, x in TBL_SEC.items() if k in cap), None)
            st = edition_state(case, sec) if sec else None
            if st:
                v = st
        tally[v] = tally.get(v, 0) + 1
        rows.append((v, cap, a))
    return tally, rows


# 삽도 6종 — `rules/small-env/regional-overview.md` §1 (8/8 사업 공통)
FIGURES = ["생태·자연도", "식생보전등급도", "수계흐름모식도", "수계도",
           "정온시설 및 개발시설 현황", "지역개황도"]


def score_figures(case, part):
    """`[삽도 필요]` 자리표시면 MISSING 이다. 채운 삽도가 생기면 여기서 갈린다."""
    p = ROOT / "cases/small-env" / case / part / "output.hwpx"
    z = zipfile.ZipFile(p)
    names = [n for n in z.namelist() if n.startswith("BinData/")]
    filled = sum(1 for n in names if z.getinfo(n).file_size > 300_000)
    return {"MISSING": len(FIGURES) - min(filled, len(FIGURES)),
            **({"OK": min(filled, len(FIGURES))} if filled else {})}


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
                if v in ("WRONG", "일부"):
                    st = edition_state(a.case, sec)
                    if st:
                        v = st
            tally[v] = tally.get(v, 0) + 1
            rows.append((sec, v, r, o, g))

    n = sum(tally.values())
    print(f"서술 문장 {n}항목  (정답 {sum(len(sentences(v)) for v in G.values())} · "
          f"생성 {sum(len(sentences(v)) for v in O.values())})\n")
    for k in ("OK", "문형", "일부", "판차이", "판미확인", "WRONG", "확인필요", "없음", "잉여"):
        if tally.get(k):
            print(f"  {k:6} {tally[k]:>3}   {tally[k]/n*100:5.1f}%")
    good = tally.get("OK", 0) + tally.get("문형", 0)
    print(f"\n  값이 맞는 문장 {good}/{n} = {good/n*100:.1f}%")

    # ── 표 · 삽도 ────────────────────────────────────────────────
    gl = gold.read_text(encoding="utf-8").splitlines()
    tt, trows = score_tables(a.case, a.part, gl)
    ft = score_figures(a.case, a.part)
    tn, fn = sum(tt.values()), sum(ft.values())
    print(f"\n표 {tn}항목")
    for k in ("OK", "일부", "판차이", "판미확인", "WRONG", "확인필요", "잉여"):
        if tt.get(k):
            print(f"  {k:6} {tt[k]:>3}   {tt[k]/tn*100:5.1f}%")
    print(f"\n삽도 {fn}항목")
    for k, v in ft.items():
        print(f"  {k:6} {v:>3}")

    total = n + tn + fn
    ok = (tally.get("OK", 0) + tally.get("문형", 0) + tt.get("OK", 0)
          + ft.get("OK", 0))
    print(f"\n{chr(61)*46}\n항목 단위 합계 — 문장 {n} · 표 {tn} · 삽도 {fn} = {total}항목")
    print(f"  OK(문형 포함)  {ok}/{total} = {ok/total*100:.1f}%")
    wrong = tally.get("WRONG", 0) + tt.get("WRONG", 0)
    print(f"  WRONG          {wrong}")

    if a.detail:
        print("\n── 표 상세 ──")
        for v, cap, _ in trows:
            if v != "OK":
                print(f"  [{v}] {cap[:56]}")

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

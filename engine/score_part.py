#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파트 범용 채점기 — 생성물(output.hwpx) vs 정답지. **검증 단계에서만 쓴다.**

`score_regional.py` 는 지역개황 전용(절 번호 `2.N` · 통계 판 추적 · 열 미결 판정)이다.
여기서는 그 **판정 로직을 그대로 빌려** 쓰고 절 나누기만 파트 3단 구조로 바꾼다 —
`가. 현 황` / `나. 사업시행으로 인한 영향예측` / `다. 저감방안` (`_category.md` §2, 7/7).

    python engine/score_part.py 천안_화덕리 --part water-quality
    python engine/score_part.py 천안_화덕리 --part climate --write

⚠️ **로직을 복사하지 않는다.** 판정(`judge`)·짝짓기(`pair_up`)·표 대조(`score_tables`)는
   지역개황 채점기의 것을 import 해서 쓴다. 두 벌이 되면 조용히 갈라진다
   (삽도 PSD 에서 같은 이유로 `_draw_element` 를 한 벌로 뒀다).

## 분모는 정답에서 뽑는다 ★

템플릿 토큰에서 뽑으면 **안 뚫은 자리가 분모에서 사라진다** — 지역개황에서 서술 문장
10건이 그렇게 조용히 빠졌다 (결과보고 08-24). 정답 문장·표를 세는 이유다.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import score_regional as S  # noqa: E402

ROOT = S.ROOT

# 파트 3단 구조. ⚠️ 수질 정답의 등급 설명행(`가. 매우좋음: 용존산소가 …`)도 이 꼴로
#    시작하지만 40자를 넘어 `group()` 의 길이 문턱에서 걸러진다.
SEC_PART = re.compile(r"^([가-다])\.\s*[가-힣]")
ORDER = {"가": 0, "나": 1, "다": 2, "머리": -1}


def _with_equations(xml):
    """수식(`hp:equation`)의 원문을 본문 텍스트에 섞어 넣는다.

    ⚠️ **수식은 `<hp:t>` 에 없다.** 별도 개체라 텍스트만 훑으면 통째로 빠지고,
    그 표는 '우리 쪽 숫자 0' 이 되어 **거짓 WRONG** 이 된다 — 천안 수질에서 실제로
    4건(합리식·RUSLE·혼합식·Stokes)이 그렇게 잡혔다. 문서는 멀쩡했다.
    재해 파트는 계산 사슬이 수식 표로 가득하므로 여기서 막아 둔다.

        <hp:script>Qw= {1} over {360} ·C·I·A</hp:script>
    """
    return re.sub(r"<hp:script[^>]*>(.*?)</hp:script>",
                  lambda m: f"<hp:t>{m.group(1)}</hp:t>", xml, flags=re.S)


MARK = "楴䵴"   # hwp 추출의 자동번호 필드 잔재 — 재해 골든의 절·표·삽도 제목 앞에 붙는다


def _disaster_grouper(gold_lines):
    """재해 파트 절 나누기 — `가.` 3단이 없다. **골든의 `楴䵴` 제목 줄을 경계**로 묶고,
    같은 제목 줄이 생성물에서는 마커 없이 나오므로 제목 집합으로 양쪽을 똑같이 가른다.
    (`small-disaster/_variants.md` §2 — 절 번호가 자동 필드라 텍스트에 숫자가 없다.)"""
    heads = {ln.strip().lstrip(MARK).strip() for ln in gold_lines if ln.strip().startswith(MARK)}

    def norm(x):
        # 생성물(hwpx) 쪽은 같은 자동번호 필드가 `<hp:titleMark ignore="1"/>` **태그**로 남는다 —
        # 골든의 `楴䵴` 와 같은 정체다 (2026-09-02 실측). 태그를 벗겨야 제목이 짝을 찾는다.
        return re.sub(r"<[^>]+>", "", x).strip().lstrip(MARK).strip()

    def group(lines):
        cur, d = "머리", {}
        for t in (norm(x) for x in lines):
            if t in heads and len(t) < 40:
                cur = t
            d.setdefault(cur, []).append(t)
        return d
    return group


def score(case, part, category="small-env"):
    S.CATEGORY = category                # 경로(cases/golden)를 카테고리로
    gold = ROOT / "golden" / category / case / f"{part}.txt"
    if not gold.exists():
        sys.exit(f"정답 없음 — {gold}")
    out = ROOT / "cases" / category / case / part / "output.hwpx"
    if not out.exists():
        sys.exit(f"생성물 없음 — {out}\n  먼저 generate.py 로 만든다 (Windows)")

    S.PREPROCESS = _with_equations       # 수식 표를 읽는다 (거짓 WRONG 방지)
    gold_raw = gold.read_text(encoding="utf-8").splitlines()   # 표 대조용 — 마커를 남긴다
    gold_lines = gold_raw                                       # (gold_table 이 마커 줄에서 블록을 끊는다)
    if category == "small-env":
        S.SEC = SEC_PART                 # 절 나누기만 갈아 끼운다
        grouper = S.group
    else:
        # 재해 — 마커 제목 경계로 묶는다. 문장 짝짓기용 골든 줄은 마커를 벗긴다.
        grouper = _disaster_grouper(gold_raw)
        gold_lines = [ln.lstrip(MARK) if ln.startswith(MARK) else ln for ln in gold_raw]
        # 문체가 다르다 — `하였다`(공학 채택)·`판단된다`(공학 판단)·`한다`(계획·시행).
        # 소환 어미(조사되었다 등)만 보면 재해 서술이 통째로 0항목이 된다 (_category §2).
        S.END = re.compile(r"(되었다|하였다|판단된다|한다|였다)\.?$")
    G = grouper(gold_lines)
    O = grouper(S.read_gen(case, part))

    tally, rows = {}, []
    for sec in sorted(set(G) | set(O), key=lambda s: ORDER.get(s, 9)):
        for o, g in S.pair_up(S.sentences(O.get(sec, [])), S.sentences(G.get(sec, []))):
            if g is None:
                v, r = "잉여", 0.0
            elif o is None:
                v, r = "없음", 0.0
            else:
                v, r = S.judge(o, g)
            tally[v] = tally.get(v, 0) + 1
            rows.append((sec, v, r, o, g))

    t_tally, t_rows = S.score_tables(case, part, gold_raw)     # 마커 있는 줄 — 블록 경계
    return tally, rows, t_tally, t_rows


def summary(tally, t_tally):
    """OK + 문형 = 값이 맞은 것. WRONG 은 **0 이어야 한다** (러프 원칙)."""
    all_t = {}
    for d in (tally, t_tally):
        for k, v in d.items():
            all_t[k] = all_t.get(k, 0) + v
    n = sum(all_t.values())
    ok = all_t.get("OK", 0) + all_t.get("문형", 0)
    return n, ok, all_t


def main():
    ap = argparse.ArgumentParser(description="파트 채점 — 생성물 vs 정답지")
    ap.add_argument("case")
    ap.add_argument("--part", required=True)
    ap.add_argument("--category", default="small-env",
                    help="small-env(기본) · small-disaster · disaster-review …")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--write", action="store_true", help="validation.md 저장")
    a = ap.parse_args()

    tally, rows, t_tally, t_rows = score(a.case, a.part, a.category)
    n, ok, all_t = summary(tally, t_tally)

    print(f"# {a.case} · {a.part}\n")
    print(f"서술 {sum(tally.values())}항목 · 표 {sum(t_tally.values())}개 = 합 {n}")
    print(f"OK+문형 {ok}/{n} = {ok/n*100:.1f}%" if n else "항목 0")
    print("  " + " · ".join(f"{k} {v}" for k, v in sorted(all_t.items(), key=lambda x: -x[1])))
    wrong = all_t.get("WRONG", 0)
    print(f"\n{'⚠️ WRONG ' + str(wrong) + '건 — 고쳐야 한다' if wrong else '✅ WRONG 0'}")

    bad = [r for r in rows if r[1] in ("WRONG", "일부", "없음")]
    if bad:
        print(f"\n## 손봐야 할 서술 {len(bad)}건")
        for sec, v, r, o, g in bad[:40 if a.detail else 12]:
            print(f"  [{v}] {sec}  생성: {(o or '—')[:60]}")
            print(f"        {' ' * len(v)}정답: {(g or '—')[:60]}")
    if t_rows:
        print(f"\n## 손봐야 할 표 {len(t_rows)}건")
        for row in t_rows[:20]:
            print("  " + " | ".join(str(x)[:50] for x in row))

    if a.write:
        p = ROOT / "cases" / a.category / a.case / a.part / "validation.md"
        lines = [f"# 검증 — {a.case} · {a.part}", "",
                 f"> 자동 채점 `engine/score_part.py`. **정답지는 이 단계에서만 연다.**", "",
                 f"- 항목 {n} (서술 {sum(tally.values())} · 표 {sum(t_tally.values())})",
                 f"- **OK+문형 {ok}/{n} = {ok/n*100:.1f}%**" if n else "- 항목 0",
                 f"- 판정: " + " · ".join(f"{k} {v}" for k, v in sorted(all_t.items(), key=lambda x: -x[1])),
                 f"- **WRONG {wrong}건**" + ("" if wrong else " ✅"), ""]
        if bad:
            lines += ["## 손봐야 할 서술", "", "| 판정 | 절 | 생성 | 정답 |", "|---|---|---|---|"]
            lines += [f"| {v} | {sec} | {(o or '—')[:70]} | {(g or '—')[:70]} |"
                      for sec, v, r, o, g in bad]
        if t_rows:
            lines += ["", "## 손봐야 할 표", "",
                      "```", *[" | ".join(str(x)[:60] for x in r) for r in t_rows], "```"]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n→ {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

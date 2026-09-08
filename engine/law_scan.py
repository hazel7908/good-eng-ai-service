#!/usr/bin/env python3
"""법령 인용 목록 스캐너 — 법령 개정 감시(할 일 7) ①단계.

베이스 문서 전체(templates/**/*.hwpx)에서 인용 법령을 전수 수집한다.
베이스 미배치 파트(본환·전략 23종)는 spec 의 골든 원천 txt 를 대신 읽는다 —
베이스는 그 txt 에서 만들어지므로 인용 목록은 같다.

잡는 것 세 갈래:
  ① 낫표 인용 「…법」「…시행규칙」 (조문은 벗겨 법령명으로 묶는다)
  ② 고시 번호 — 낫표 없이 `환경부고시 제2007-107호` 꼴로도 나온다
  ③ 기준표 제목 — `대기환경기준` 처럼 캡션 없는 맨 줄 (별표 본문 복사 후보)

날짜·판 단서(시행일·법률 제N호·고시연도)를 같은 줄에서 함께 긁는다 —
연도가 박힌 인용이 낡음 위험 1순위다.

출력: catalog/review/law_citations.json (② 시행일자 대조의 인풋) + stdout 요약
"""
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
from extract import extract_hwpx  # noqa: E402

CATS = ["small-env", "small-disaster", "disaster-impact", "disaster-review",
        "env-impact", "strategic-env"]

# 낫표 안 조문 표기 — 법령명 뒤에 붙는 것만 벗긴다
ART = re.compile(r"\s*제\s*\d+\s*조.*$")
BRACKET = re.compile(r"「([^」]{2,80})」")
NOTICE = re.compile(r"([가-힣]{2,12}(?:부|처|청|위원회|시|군|도)?\s?고시)\s*제?\s*(\d{4}\s*[-–]\s*\d+)호")
DATE = re.compile(r"(?:시행\s*)?\b(19|20)\d{2}\s*[.년]\s*\d{1,2}\s*[.월]?(?:\s*\d{1,2})?")
LAWNO = re.compile(r"(법률|대통령령|환경부령|국토교통부령|행정안전부령|총리령)\s*제\s*[\d,]+호")
BYULPYO = re.compile(r"별표\s*\d*")
# 기준표 제목 — 맨 줄 전체가 제목(+단위 표기)인 것만. 앞머리는 번호 표기만 허용
STD_TITLE = re.compile(r"^(?:\(?\d+\)?[.)]\s*|[가-힣]\.\s*|\(\d+\)\s*)?"
                       r"([가-힣·]{1,14}\s?(?:환경기준|허용기준|규제기준|방류수수질기준))"
                       r"\s*(?:\(단위.*)?$")
NOTICE_NO = re.compile(r"제(\d{4}-\d+)호")

# ── 낫표 없는 인용 ─────────────────────────────────────────────────
# 「」 만 보면 놓친다. `지하수법 시행규칙 <별표3>` `토양환경보전법 시행규칙 [별표3]`
# `수질환경보전법 제30조` 처럼 맨이름 인용이 실제 베이스에 있다 (09-08 실측 28건).
# 조문·시행령·별표가 뒤따르는 자리만 본다 — 문장 속 일반 명사와 구분되는 유일한 단서다.
BARE = re.compile(
    r"((?:[가-힣ㆍ·‧∙]{1,14}\s?){1,6}(?:법률|법|조례|(?<!시행)규칙))"
    r"\s*(?=시행령|시행규칙|<\s*별표|\[\s*별표|별표|제\s*\d+\s*조)")
# 이름 왼쪽에 문장이 붙어 나온다 (`대하여 산업안전보건법`) — 토큰을 왼쪽부터 떼며 줄인다.
CONNECT = ("관한", "관련", "및", "등에", "대한", "위한", "따른")   # 이름의 일부다. 못 뗀다
GENERIC = {"법", "법률", "규칙", "조례", "시행령", "시행규칙", "동법", "같은법",
           "관한 법률", "관한 규칙", "관련 법률", "동법시행령", "동법시행규칙",
           "같은법 시행규칙", "같은법 시행령", "동법 시행규칙", "동법 시행령"}


def trim_bare(name: str) -> str:
    """맨이름 인용을 후보로 정규화한다. 법령명이 아니면 빈 문자열.

    ⚠️ 왼쪽 문장 꼬리(`대하여 산업안전보건법`)는 여기서 **떼지 않는다.**
    짧은 쪽부터 고르면 `지하수의 수질보전등에 관한 규칙` 이 `수질보전등에 관한 규칙` 으로
    잘려 법제처 조회가 되레 실패한다. 꼬리는 `law_check` 가 API 조회 실패 시
    한 토큰씩 떼며 재조회해 판별한다 — 판정을 바깥 근거에 맡긴다.
    """
    s = name.strip()
    if s in GENERIC or len(s) < 4 or re.search(r"[(\[<]", s):
        return ""
    if re.match(r"^(동법|같은\s?법|해당\s?법)", s):
        return ""
    # 대명사 인용은 이름이 아니다 — `제5조 및 동법 시행령` 의 `조 및 동법`, `사업시행자는 법`.
    # 앞말이 무엇이든 **마지막 낱말이 `법`·`동법`·`같은법`** 이면 가리키는 법이 딴 데 있다.
    if s.split()[-1] in ("법", "동법", "같은법", "해당법", "그법", "본법"):
        return ""
    return s


SUFFIX_CLASS = [
    ("시행규칙", "시행규칙"), ("시행령", "시행령"), ("특별법", "법률"),
    ("법률", "법률"), ("법", "법률"), ("조례", "자치법규"), ("고시", "행정규칙"),
    ("훈령", "행정규칙"), ("예규", "행정규칙"), ("지침", "행정규칙"),
    ("규정", "행정규칙"), ("기준", "행정규칙"), ("규칙", "규칙"),
]


def norm(name: str) -> str:
    s = name.replace(" ", " ")
    for d in "ㆍ‧∙･⸳․":
        s = s.replace(d, "·")
    s = re.sub(r"\s+", " ", s).strip()
    return ART.sub("", s).strip()


def classify(name: str) -> str:
    if "고시" in name or NOTICE_NO.search(name):
        return "행정규칙"
    if name.endswith(("방법", "요령")):        # `…산정방법` 은 고시류다 — `법` 접미 오분류 방지
        return "행정규칙"
    for suf, cls in SUFFIX_CLASS:
        if name.endswith(suf):
            return cls
    return "기타"


def load_spec_source(spec_path: Path):
    sp = importlib.util.spec_from_file_location("s", spec_path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    src = re.sub(r"\s*\(.*\)$", "", m.SPEC["source"])
    part = spec_path.name.replace(".spec.py", "")
    cat = spec_path.parent.name
    gold = ROOT / "golden" / cat / src / f"{part}.txt"
    if not gold.exists():
        for alt in (ROOT / "golden").glob(f"*/{src}/{part}.txt"):
            return alt
    return gold if gold.exists() else None


def scan_targets():
    """(cat, part, 텍스트, 출처표기) 를 낸다."""
    for cat in CATS:
        tdir = ROOT / "templates" / cat
        if not tdir.exists():
            continue
        hwpx_parts = set()
        for f in sorted(tdir.rglob("*.hwpx")):
            part = f.stem if f.parent == tdir else f"{f.parent.name}/{f.stem}"
            hwpx_parts.add(f.stem)
            yield cat, part, extract_hwpx(str(f)), "베이스"
        for sf in sorted(tdir.glob("*.spec.py")):
            part = sf.name.replace(".spec.py", "")
            if part in hwpx_parts:
                continue
            gold = load_spec_source(sf)
            if gold is None:
                print(f"⚠️ 골든 원천 없음: {cat}/{part}", file=sys.stderr)
                continue
            yield cat, part, gold.read_text(encoding="utf-8"), "골든원천(베이스 대기)"


def scan():
    laws = defaultdict(lambda: {"class": "", "count": 0, "parts": set(),
                                "clues": set(), "별표": False, "고시번호": "", "샘플": ""})
    std_tables = defaultdict(lambda: {"count": 0, "parts": set()})
    scanned = []
    for cat, part, txt, kind in scan_targets():
        scanned.append((cat, part, kind))
        loc = f"{cat}/{part}"
        for line in txt.splitlines():
            hits = [norm(m) for m in BRACKET.findall(line)]
            for m in NOTICE.finditer(line):
                hits.append(norm(f"{m.group(1)} 제{m.group(2).replace(' ', '')}호"))
                # ⚠️ 번호 앞의 이름을 같이 따려다 되레 망가뜨렸다 (09-08 실측):
                #    `자연재해위험개선지구 관리지침(제2023-63호)` 은 **골든의 인용 오기**라
                #    그 이름을 믿으면 10파트가 쓰는 실무지침 번호가 엉뚱한 고시로 치환된다.
                #    번호만 있고 이름을 모르는 고시는 `law_check.NOTICE_ALIAS` 에
                #    **근거를 확인한 것만** 손으로 적는다.
            bare = set()
            for m in BARE.finditer(re.sub(r"「[^」]*」", " ", line)):
                t = trim_bare(norm(m.group(1)))
                if t:
                    bare.add(t)
            hits += sorted(bare)
            for name in hits:
                # 토큰·장절 참조·대명사 인용(동법)·한 글자짜리는 법령이 아니다
                if (not name or "{{" in name or len(name) < 3 or re.match(r"^\d+장\b", name)
                        or re.match(r"^(동법|같은\s?법)\b", name) or name == "수단·방법"):
                    continue
                e = laws[name]
                e["class"] = e["class"] or classify(name)
                no = NOTICE_NO.search(name)
                if no:
                    e["고시번호"] = no.group(1)
                if not e["샘플"]:
                    e["샘플"] = re.sub(r"\s+", " ", line.strip())[:140]
                e["count"] += 1
                e["parts"].add(loc)
                if BYULPYO.search(line):
                    e["별표"] = True
                for pat in (DATE, LAWNO):
                    mm = pat.search(line)
                    if mm:
                        e["clues"].add(mm.group(0).strip())
            m = STD_TITLE.match(line.strip())
            if m:
                t = norm(m.group(1))
                std_tables[t]["count"] += 1
                std_tables[t]["parts"].add(loc)
    return laws, std_tables, scanned


def main():
    laws, std_tables, scanned = scan()
    out = {
        "생성일": "2026-09-07",
        "스캔": {"파트수": len(scanned),
               "베이스": sum(1 for *_, k in scanned if k == "베이스"),
               "골든원천": sum(1 for *_, k in scanned if k != "베이스")},
        "법령": {k: {"class": v["class"], "count": v["count"],
                   "parts": sorted(v["parts"]), "별표인용": v["별표"],
                   "고시번호": v["고시번호"], "날짜단서": sorted(v["clues"]),
                   "샘플": v["샘플"]}
               for k, v in sorted(laws.items(), key=lambda x: -x[1]["count"])},
        "기준표제목": {k: {"count": v["count"], "parts": sorted(v["parts"])}
                  for k, v in sorted(std_tables.items(), key=lambda x: -x[1]["count"])},
    }
    dst = ROOT / "catalog" / "review" / "law_citations.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    by_class = defaultdict(int)
    for v in laws.values():
        by_class[v["class"]] += 1
    print(f"스캔 {len(scanned)}파트 (베이스 {out['스캔']['베이스']} · 골든원천 {out['스캔']['골든원천']})")
    print(f"법령 {len(laws)}종 · 인용 {sum(v['count'] for v in laws.values())}건 · "
          + " ".join(f"{c} {n}" for c, n in sorted(by_class.items(), key=lambda x: -x[1])))
    print(f"별표 본문 인용 {sum(1 for v in laws.values() if v['별표'])}종 · "
          f"날짜 단서 보유 {sum(1 for v in laws.values() if v['clues'])}종 · "
          f"기준표 제목 {len(std_tables)}종")
    print(f"→ {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

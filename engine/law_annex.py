#!/usr/bin/env python3
"""별표 본문 대조 — 법령 개정 감시(할 일 7) ③단계 (기준표 8종 우선).

베이스 90파트의 환경기준·규제기준 표 숫자를 법제처 별표·서식 API 의 **현행 별표
본문**과 대조한다. 기준표 8종은 별표 둘로 전부 덮인다:
  - 환경정책기본법 시행령 별표1 「환경기준」 → 대기·소음·수질(하천/호소 생활환경)
  - 소음·진동관리법 시행규칙 별표8 「생활소음·진동의 규제기준」 → 생활소음/진동

별표 HWP 를 내려받아 자체 추출기(extract_hwp)로 읽는다 — HTML 서비스는 동적 셸이라
본문이 없다. 숫자 비교는 값 집합(연도·시각·조문 번호 제외): 베이스에만 있는 값이
개정 의심이다. ⚠️ 표기 차이(단위 병기·반올림)로 오탐이 나올 수 있어 결과는 목록으로
남겨 사람이 본다 — 자동 판정으로 쓰지 않는다.

출력: catalog/review/law_annex_result.json + stdout 요약
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
from extract import extract_hwp  # noqa: E402
from law_scan import STD_TITLE, scan_targets  # noqa: E402
from law_check import get_oc  # noqa: E402

CACHE = ROOT / "catalog" / "review" / ".law_api_cache"

# 별표 레지스트리 — (검색어, 관련법령명, 별표명 머리)
ANNEXES = {
    "env": ("환경기준", "환경정책기본법 시행령", "환경기준"),
    "noise": ("생활소음", "소음ㆍ진동관리법 시행규칙", "생활소음ㆍ진동의 규제기준"),
}

# ── 본문 인용 별표 — 기준표 캡션이 아니라 절 본문에 통째 복사되는 별표 (09-08 확장).
#   0100 실시근거의 [별표4] 가 협의 대상 **문턱 숫자**(보전관리 5,000·생산관리 7,500㎡ …)를
#   담는다 — 문턱이 바뀌면 협의 대상 판정 자체가 틀리는 반려급 자리다.
#   (재해 별표1 인용부는 유형 분류 텍스트라 숫자 대조 대상이 아니다 — law_check 판 감시로 충분)
#   {키: (검색어, 관련법령명, 별표명 머리, 베이스 인용 앵커 정규식, 블록 끝 정규식)}
BODY_ANNEXES = {
    "sea4": ("소규모 환경영향평가 대상사업", "환경영향평가법 시행령",
             "소규모 환경영향평가 대상사업의 종류",
             re.compile(r"\[?별표\s*4\]?\s*소규모\s*환경영향평가\s*대상사업"),
             re.compile(r"^\s*(사\s*업\s*규\s*모|협의요청시기)")),
}
# 기준표 제목 → (별표 키, 별표 안 절 이름)
TITLE_MAP = {
    "대기환경기준": ("env", "대기"),
    "소음환경기준": ("env", "소음"),
    "수질환경기준": ("env", "수질"),
    "생활환경기준": ("env", "수질"),
    "하천생활환경기준": ("env", "수질"),
    "호소생활환경기준": ("env", "수질"),
    "생활소음 규제기준": ("noise", "생활소음"),
    "생활진동 규제기준": ("noise", "생활진동"),
}

NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
SKIP_CTX = re.compile(r"(\d{1,2}\s*:\s*\d{2}|\d{4}\s*[.년]\s*\d{1,2}\s*[.월]|제\s*\d+\s*[조항호목]"
                      r"|PM\s*-\s*\d+|별표\s*\d+|제\s*\d+호|\d+\s*pixel)")
FIG_META = re.compile(r"^(그림입니다|원본 그림의|사진 찍은 날짜)")


def fetch_annex(oc: str, key: str) -> str:
    txt_f = CACHE / f"annex_{key}.txt"
    if txt_f.exists():
        return txt_f.read_text(encoding="utf-8")
    q, law, prefix = (ANNEXES.get(key) or BODY_ANNEXES[key][:3])
    url = ("http://www.law.go.kr/DRF/lawSearch.do?OC=" + oc
           + "&target=licbyl&type=JSON&display=100&query=" + urllib.parse.quote(q))
    d = json.load(urllib.request.urlopen(url, timeout=30))
    rows = d["licBylSearch"]["licbyl"]
    rows = [rows] if isinstance(rows, dict) else rows
    hit = next(r for r in rows if r["관련법령명"] == law and r["별표명"].startswith(prefix))
    hwp_f = CACHE / f"annex_{key}.hwp"
    urllib.request.urlretrieve("http://www.law.go.kr" + hit["별표서식파일링크"], hwp_f)
    txt = extract_hwp(str(hwp_f))
    txt_f.write_text(txt, encoding="utf-8")
    return txt


def numbers(lines) -> set:
    vals = set()
    for ln in lines:
        if FIG_META.match(ln.strip()):
            continue
        clean = re.sub(r"^\s*\d+[.)]\s", " ", ln)        # 비고 나열 번호
        clean = SKIP_CTX.sub(" ", clean)
        for m in NUM.findall(clean):
            v = float(m.replace(",", ""))
            if 1900 <= v <= 2099 and "." not in m:      # 연도
                continue
            vals.add(v)
    return vals


# 별표 안 최상위 절 이름 — 비고 나열(`1. 공사장…`)을 절 경계로 오인하지 않도록 한정한다
SECTION_NAMES = {"env": "대기|소음|수질", "noise": "생활소음|생활진동"}


def annex_section(txt: str, key: str, section: str) -> set:
    lines = txt.splitlines()
    pat = re.compile(rf"^\s*\d+\.\s*({SECTION_NAMES[key]})")
    starts = [i for i, ln in enumerate(lines)
              if pat.match(ln) and re.match(rf"^\s*\d+\.\s*{section}", ln)]
    if not starts:
        return numbers(lines)                            # 절 구분 실패 — 전체로 비교(보수적)
    i = starts[0]
    end = next((j for j in range(i + 1, len(lines)) if pat.match(lines[j])), len(lines))
    return numbers(lines[i:end])


def base_block(lines, idx) -> list:
    out = []
    for ln in lines[idx + 1: idx + 80]:
        if STD_TITLE.match(ln.strip()) and len(ln.strip()) < 60:
            break
        out.append(ln)
    return out


def main():
    oc = get_oc()
    annex_nums = {}
    annex_meta = {}
    for key in ANNEXES:
        txt = fetch_annex(oc, key)
        annex_meta[key] = txt.splitlines()[0]
        for title, (k, sec) in TITLE_MAP.items():
            if k == key:
                annex_nums[title] = annex_section(txt, key, sec)
    print("현행 별표:", " · ".join(annex_meta.values()), "\n")

    results = []
    for cat, part, txt, kind in scan_targets():
        lines = txt.splitlines()
        for i, ln in enumerate(lines):
            m = STD_TITLE.match(ln.strip())
            if not m:
                continue
            title = m.group(1).replace(" ", " ").strip()
            title = re.sub(r"\s+", " ", title)
            for t, nums in annex_nums.items():
                if title.endswith(t) or t.endswith(title):
                    base = numbers(base_block(lines, i))
                    only = sorted(base - nums)
                    results.append({"part": f"{cat}/{part}", "기준표": t,
                                    "베이스값": len(base), "현행불포함": only,
                                    "_base": sorted(base)})
                    break

    # 기준표 단위 합의 판정 — 인스턴스 과반에 나오는 값만 진짜 표 값으로 본다.
    # 파트별 국소 소음(옆 표 실측값·문맥 숫자)은 과반을 못 넘어 떨어진다.
    from collections import Counter, defaultdict
    by_title = defaultdict(list)
    for r in results:
        by_title[r["기준표"]].append(r)
    verdicts = []
    for t, rs in by_title.items():
        cnt = Counter()
        for r in rs:
            cnt.update(set(r["_base"]))
        need = max(2, (len(rs) + 1) // 2)
        consensus = {v for v, c in cnt.items() if c >= need}
        missing = sorted(consensus - annex_nums[t])
        verdicts.append({"기준표": t, "인스턴스": len(rs), "합의값": len(consensus),
                         "현행별표에없음": missing})
    for r in results:
        del r["_base"]

    # ── 본문 인용 별표 대조 — 인용 앵커 줄부터 블록 끝(사업 규모 행 전)까지의 숫자가
    #    현행 별표 전문의 숫자 집합에 들어 있는지 본다 (베이스 ⊆ 현행 = 정상).
    body_verdicts = []
    for key, (_q, _law, _pfx, anchor, blk_end) in BODY_ANNEXES.items():
        cur = numbers(fetch_annex(oc, key).splitlines())
        for cat, part, txt, kind in scan_targets():
            lines = txt.splitlines()
            for i, ln in enumerate(lines):
                if not anchor.search(ln):
                    continue
                blk = []
                for x in lines[i: i + 40]:
                    if blk and blk_end.match(x):
                        break
                    blk.append(x)
                base = numbers(blk)
                body_verdicts.append({"별표": key, "part": f"{cat}/{part}",
                                      "베이스값": sorted(base),
                                      "현행에없음": sorted(base - cur)})
                break

    dst = ROOT / "catalog" / "review" / "law_annex_result.json"
    dst.write_text(json.dumps({"별표": annex_meta, "판정": verdicts, "대조": results,
                               "본문별표": body_verdicts},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    if body_verdicts:
        print(f"\n본문 인용 별표 {len(BODY_ANNEXES)}종 · 인용 {len(body_verdicts)}곳:")
        for v in body_verdicts:
            mark = "🚨" if v["현행에없음"] else "✅"
            print(f"  {mark} {v['별표']} {v['part']} — 베이스 {len(v['베이스값'])}값, "
                  f"현행에 없음: {v['현행에없음'] or '0'}")
    print(f"기준표 인스턴스 {len(results)}곳 → 기준표 {len(verdicts)}종 합의 판정:")
    for v in sorted(verdicts, key=lambda x: -len(x["현행별표에없음"])):
        mark = "🚨" if v["현행별표에없음"] else "✅"
        print(f"  {mark} {v['기준표']} ({v['인스턴스']}곳·합의 {v['합의값']}값) "
              f"현행에 없음: {v['현행별표에없음'][:14] or '0'}")
    print(f"→ {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

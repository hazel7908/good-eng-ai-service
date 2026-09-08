#!/usr/bin/env python3
"""법령 시행일자 대조 — 법령 개정 감시(할 일 7) ②단계.

law_scan.py 가 뽑은 인용 목록(catalog/review/law_citations.json)을 법제처
국가법령정보 오픈API(law.go.kr)와 대조한다.

- 법률·시행령·시행규칙 → target=law : 현행 시행일자·공포번호·소관부처
- 중앙 행정규칙(고시·지침·규정·기준) → target=admrul : 현행 발령번호·발령일자
  인용에 고시번호가 있으면 현행 발령번호와 직접 비교해 STALE/CURRENT 를 판정한다.

인증키: 환경변수 LAW_OC 또는 ~/.lawapi.env (LAW_OC=...). 저장소에 커밋하지 않는다.
응답은 catalog/review/.law_api_cache/ 에 캐시 — 재실행 무료. --fresh 로 무시.

출력: catalog/review/law_check_result.json + stdout 요약
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "catalog" / "review" / ".law_api_cache"
LOCAL_GOV = re.compile(r"(횡성군|강원도|충청북도|충청남도|천안시|원주시|괴산군|청양군|평창군|충주시|청주시|옥천군)\s?고시")
NOTICE_NO = re.compile(r"제(\d{4}-\d+)호")
# 명칭 정리 — 괄호 속 고시번호·날짜, 앞뒤 부처 표기를 벗겨 질의어를 만든다
PAREN = re.compile(r"[(\[（].*?[)\]）]")
TAIL = re.compile(r"[,.]?\s*(\d{4}\.\s*\d{1,2}\.?.*|(?:행정안전부|환경부|국토교통부|산림청|고용노동부|산업통상자원부|국립환경과학원|한강홍수통제소)\s?고시\s*제.*)$")


# 번호만 인용된 고시의 질의 명칭 — law_citations.json 의 샘플 줄에서 사람이 확인해 채웠다.
# None = 문서에도 명칭이 없어 질의 불가(확인 필요) · "사업고유" = 사업별 지자체 고시(감시 제외)
NOTICE_ALIAS = {
    "2019-75": "백두대간보호지역 지정",
    "2007-107": "배출허용기준(폐수)적용을 위한 지역지정",
    "2018-23": "대기보전특별대책지역지정 및 동지역내 대기오염저감을 위한 종합대책",
    "2015-201": "연료용 유류 등의 황함유기준",
    "2025-102": "한강유역 폐수배출시설 설치제한을 위한 대상 지역 및 시설 지정",
    "2025-46": "팔당ㆍ대청호 상수원 수질보전 특별대책지역 지정 및 특별종합대책",
    "2024-212": "생태계교란 생물 지정 고시",
    "2021-59": "건축물의 용도별 오수발생량 및 정화조 처리대상인원 산정방법",
    "2018-153": "건축물의 용도별 오수발생량 및 정화조 처리대상인원 산정방법",
    "2019-5": "재해영향평가등의 협의 실무지침",
    "2023-1": "재해영향평가등의 협의 실무지침",
    "2023-135": "골프장의 중점 환경영향평가항목",
    "2018-53": "토양오염공정시험기준",
    "2009-193": "에너지 사용계획 수립 및 협의절차 등에 관한 규정",
    "2014-691": None,       # Tier 3 고시안 — API 의 Tier 2 와 다른 문서, 오매칭 방지
    "2022-79": "소음·진동공정시험기준",
    "2014-32": "골프장의 입지기준 및 환경보전 등에 관한 규정",
    "2019-47": "도시생태현황지도의 작성방법에 관한 지침",
    "2015-191": None,       # 한강홍수통제소 지정 고시 — API 의 산정지침과 다른 문서
    "2006-227": "중권역별 물환경 목표기준",
    "2019-105": None,
    "2012-1577": None,
    "2017-139": "사업고유", "2019-174": "사업고유",
    "2020-380": "사업고유", "2022-532": "사업고유",   # {{시군}} 산사태취약지역 지정 고시
}


def get_oc() -> str:
    oc = os.environ.get("LAW_OC")
    if not oc:
        env = Path.home() / ".lawapi.env"
        if env.exists():
            for ln in env.read_text().splitlines():
                if ln.startswith("LAW_OC="):
                    oc = ln.split("=", 1)[1].strip()
    if not oc:
        sys.exit("LAW_OC 없음 — ~/.lawapi.env 에 LAW_OC=... 를 넣을 것")
    return oc


def api_search(oc: str, target: str, query: str, fresh: bool = False):
    CACHE.mkdir(exist_ok=True)
    key = re.sub(r"[^\w가-힣]", "_", f"{target}_{query}")[:100]
    cf = CACHE / f"{key}.json"
    if cf.exists() and not fresh:
        return json.loads(cf.read_text(encoding="utf-8"))
    url = ("http://www.law.go.kr/DRF/lawSearch.do?OC=" + oc
           + f"&target={target}&type=JSON&display=20&query=" + urllib.parse.quote(query))
    with urllib.request.urlopen(url, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    time.sleep(0.4)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"_error": raw[:300]}
    cf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def rows(data, root_key, item_key):
    body = data.get(root_key, {})
    items = body.get(item_key, [])
    return [items] if isinstance(items, dict) else list(items)


def norm_name(s: str) -> str:
    """이름 비교용 정규화. **가운뎃점과 공백은 지운다** — 표기 변이지 다른 법이 아니다.

    베이스가 `소음진동관리법` 으로 쓰는데 현행 정식 명칭은 `소음ㆍ진동관리법` 이다.
    점 하나로 `명칭불일치` 가 뜨면 진짜 구명칭 인용(문화재보호법→문화유산법)이 묻힌다.
    """
    for d in "ㆍ‧∙･⸳․·":
        s = s.replace(d, "")
    return re.sub(r"\s+", "", s)


def bare_rule_name(name: str) -> str:
    s = PAREN.sub("", name)
    s = TAIL.sub("", s)
    s = re.sub(r"\s*별표\s*\d*\s*$", "", s)
    s = re.sub(r"^\s*[가-힣]+(부|처|청|위원회)\s*(제정|고시)?\s*", "", s) if re.match(r"^\s*[가-힣]+(부|처|청|위원회)\s?고시\s*제", s) else s
    return s.strip(" ·,.-[]「」")


def trim_candidates(name: str):
    """맨이름 인용은 문장 꼬리를 달고 온다 — 왼쪽 토큰을 한 개씩 떼며 후보를 만든다.

    `law_scan` 이 `수급인은 해당 사업장의 근로자에 대하여 산업안전보건법` 까지 잡아 온다.
    어디까지가 이름인지는 사전이 아니라 **법제처 조회 성공 여부**로 가른다 —
    회사 표준이 없는 자리를 규칙으로 굳히지 않는다.
    """
    tok = name.split()
    conn = ("관한", "관련", "및", "등에", "대한", "위한", "따른", "등")
    out = [name]                              # ⚠️ 원래 이름은 길이와 무관하게 항상 조회한다
    for i in range(1, len(tok)):              #    (`하천법`·`건축법` 이 길이 필터에 걸려 죽었다)
        c = " ".join(tok[i:])
        if len(c) < 3 or tok[i] in conn:      # `관한 규칙` 은 이름이 아니다 — 꼬리 조각
            continue
        out.append(c)
        # 법령명 띄어쓰기 관행 — `…수질보전등에 관한` 은 원문이 `… 등에 관한` 이다.
        v = re.sub(r"(?<=[가-힣])등에\s*관한", " 등에 관한", c)
        if v != c:
            out.append(v)
    return out


def check_laws(oc, laws, fresh):
    out = []
    targets = {k: v for k, v in laws.items() if v["class"] in ("법률", "시행령", "시행규칙", "규칙")}
    for name, v in sorted(targets.items(), key=lambda x: -len(x[1]["parts"])):
        used, hits, exact = name, [], []
        for cand in trim_candidates(name):
            data = api_search(oc, "law", cand, fresh)
            h2 = rows(data, "LawSearch", "law")
            e2 = [h for h in h2 if norm_name(h.get("법령명한글", "")) == norm_name(cand)]
            if h2 and not hits:          # 조회명은 **결과가 나온** 후보만 — 마지막 후보가 아니다
                hits, used = h2, cand
            if e2:
                used, hits, exact = cand, h2, e2
                break
        r = {"인용": name, "class": v["class"], "파트수": len(v["parts"]), "parts": v["parts"]}
        if used != name:
            r["조회명"] = used
        if exact:
            h = exact[0]
            r |= {"판정": "현행확인", "현행시행일": h.get("시행일자"), "공포번호": h.get("공포번호"),
                  "제개정": h.get("제개정구분명"), "소관부처": h.get("소관부처명")}
        elif hits:
            r |= {"판정": "명칭불일치", "후보": [h.get("법령명한글") for h in hits[:3]]}
        else:
            r |= {"판정": "검색0건"}
        out.append(r)
    return out


def check_admrules(oc, laws, fresh):
    # 고시번호 단위로 묶는다 — 같은 규칙의 표기 변형을 하나로
    groups = {}
    for name, v in laws.items():
        if v["class"] != "행정규칙" or LOCAL_GOV.search(name):
            continue
        no = v["고시번호"]
        gk = no or norm_name(bare_rule_name(name))
        g = groups.setdefault(gk, {"표기": [], "고시번호": no, "parts": set(), "샘플": ""})
        g["표기"].append(name)
        g["parts"] |= set(v["parts"])
        g["샘플"] = g["샘플"] or v.get("샘플", "")
        if no and not g["고시번호"]:
            g["고시번호"] = no
    out = []
    for gk, g in sorted(groups.items(), key=lambda x: -len(x[1]["parts"])):
        # 질의어 — 번호 아닌 명칭 표기 중 가장 긴 것
        names = [bare_rule_name(n) for n in g["표기"]]
        names = [n for n in names if len(n) >= 4 and not NOTICE_NO.search(n)]
        r = {"인용": sorted(g["표기"], key=len)[-1], "인용고시번호": g["고시번호"],
             "파트수": len(g["parts"]), "parts": sorted(g["parts"]), "샘플": g["샘플"]}
        if not names:
            alias = NOTICE_ALIAS.get(g["고시번호"], "")
            if alias == "사업고유":
                r["판정"] = "사업고유"
                out.append(r)
                continue
            if not alias:
                r["판정"] = "명칭미상"      # 번호만 인용 — 샘플 줄로 사람이 확인
                out.append(r)
                continue
            names = [alias]
        q = sorted(names, key=len)[-1]
        data = api_search(oc, "admrul", q, fresh)
        hits = rows(data, "AdmRulSearch", "admrul")
        exact = [h for h in hits if norm_name(h.get("행정규칙명", "")) == norm_name(q)]
        pick = exact or hits[:1]
        if pick:
            h = pick[0]
            cur_no = h.get("발령번호", "")
            r |= {"질의": q, "현행명": h.get("행정규칙명"), "현행발령번호": cur_no,
                  "현행발령일": h.get("발령일자"), "소관부처": h.get("소관부처명"),
                  "정확일치": bool(exact)}
            if g["고시번호"] and cur_no:
                r["판정"] = "CURRENT" if g["고시번호"] == cur_no else "STALE"
            else:
                r["판정"] = "현행확인"
        else:
            r |= {"질의": q, "판정": "검색0건"}
        out.append(r)
    return out


def main():
    fresh = "--fresh" in sys.argv
    oc = get_oc()
    d = json.loads((ROOT / "catalog" / "review" / "law_citations.json").read_text(encoding="utf-8"))
    laws = d["법령"]
    law_res = check_laws(oc, laws, fresh)
    rule_res = check_admrules(oc, laws, fresh)
    out = {"생성일": time.strftime("%Y-%m-%d"), "법령": law_res, "행정규칙": rule_res}
    dst = ROOT / "catalog" / "review" / "law_check_result.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=list), encoding="utf-8")

    def n(res, *verdicts):
        return sum(1 for r in res if r["판정"] in verdicts)
    print(f"법령 {len(law_res)}종: 현행확인 {n(law_res,'현행확인')} · 명칭불일치 {n(law_res,'명칭불일치')} · 검색0건 {n(law_res,'검색0건')}")
    print(f"행정규칙 {len(rule_res)}묶음: STALE {n(rule_res,'STALE')} · CURRENT {n(rule_res,'CURRENT')} · "
          f"현행확인 {n(rule_res,'현행확인')} · 명칭미상 {n(rule_res,'명칭미상')} · 검색0건 {n(rule_res,'검색0건')}")
    print("\n== STALE (인용 ≠ 현행 발령번호) ==")
    for r in rule_res:
        if r["판정"] == "STALE":
            print(f"  제{r['인용고시번호']}호 → 현행 제{r['현행발령번호']}호({r['현행발령일']}) "
                  f"{r.get('현행명','')} — {r['파트수']}파트")
    print(f"→ {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

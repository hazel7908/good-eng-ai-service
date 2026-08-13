#!/usr/bin/env python3
"""
NAS 정본 카탈로그 빌더 — 전수 (전체 폴더 → 클러스터링 → 정본 선택).

  1. 전체 프로젝트 후보 수집 (0.평가서 + 연도폴더; 담당자 사본은 위치경로로 연결)
  2. 클러스터링(dedup) — 강한 신호(관리번호 코어 / 위치+사업자)만 자동 병합, 약한 건 플래그
  3. 정본 선택 — 내용 우선(실물 有 > superseded 제외 > 출처·완성도)
  4. 유니크 셋 출력 → catalog/data/nas_catalog.json + catalog/review/catalog_review.md

설계 근거: docs/reorg_strategy.md §3 "중복 해소 & 정본 선택 규칙"
(이전 v0는 0.평가서 166건만 척추로 삼았으나 전수 확장으로 대체됨)
"""
import json, re
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
# 2026-08-13 부터 스냅샷은 .gz 보관 (전수 70MB+). 구경로(비압축)도 겸용.
_p = ROOT / "catalog/data/nas_index.json.gz"
if _p.exists():
    import gzip
    idx = json.load(gzip.open(_p, "rt", encoding="utf-8"))
else:
    idx = json.load(open(ROOT / "catalog/data/nas_index.json", encoding="utf-8"))

# ⚠️ 현행 카탈로그 v1(290건)은 7/21 depth-3 제한 인덱스에서 빌드된 잠정본이다.
#    전수 인덱스 기반 v2 재빌드는 NAS 업로드 완료(8월 말) 후 — CLAUDE.md 다음 할 일.

# ---------- 트리 평탄화 ----------
ALL = []  # (name, path, node)
def walk(node, path=""):
    for name, ch in node.get("dirs", {}).items():
        p = f"{path}/{name}"
        ALL.append((name, p, ch))
        walk(ch, p)
walk(idx, "/backupenv")

def node_counts(node):
    return len(node.get("dirs", {})), len(node.get("files", []))

def top_of(path):
    parts = path.split("/")
    return parts[2] if len(parts) > 2 else "?"

# ---------- 파싱 규칙 (v0에서 가져옴) ----------
STATUS = ["완료","완","보류","취하","반려","부동의","사업중지","중지중","중지","진행중","진행",
          "사업취소","취소","미수","추적중단","타절","보완"]
SUPERSEDED = ["취하","반려","부동의","취소","사업취소","타절","중지","중지중","사업중지","추적중단","X","x"]
KIND = ["태양광","풍력","공장","근린생활","근생","개간","축사","돈사","야영장","캠핑장","물류창고",
        "관광농원","도로","소하천","하천","지방정원","골프","CC","산업단지","공동주택","주택","대지조성",
        "토취장","석산","채석","버섯재배사","제조업","배수지","활주로","우량농지","교량","교차로","주기장"]

def detect_types(s):
    t = []
    if "소규모환경" in s or "소환" in s: t.append("소규모환경영향평가")
    elif "환경영향평가" in s: t.append("환경영향평가")
    if "전략환경" in s: t.append("전략환경영향평가")
    if "자연환경영향" in s or "자연환경에" in s: t.append("자연환경영향평가")
    if "사후환경" in s: t.append("사후환경영향조사")
    if "환경보전방안" in s: t.append("환경보전방안검토")
    if "환경성검토" in s: t.append("환경성검토")
    if "비점오염" in s: t.append("비점오염원신고")
    if "배출시설" in s or "배수설비" in s: t.append("배출시설허가")
    if "수질오염총량" in s: t.append("수질오염총량검토")
    if "소규모재해" in s or "소재평" in s or "소재" in s: t.append("소규모재해영향평가")
    elif "재해영향성" in s: t.append("재해영향성검토")
    elif "재해영향평가" in s or "제영향평가" in s or "재평" in s: t.append("재해영향평가")
    if "우수유출" in s: t.append("우수유출저감대책")
    if "경관성" in s: t.append("경관성검토")
    return t

LOC_RE = re.compile(r'[가-힣]{2,}(?:특별자치시|광역시|시|군|구)|[가-힣]{2,}(?:읍|면)|[가-힣]{2,}리(?=[\s\d])|[가-힣]{2,}동(?=[\s\d])')
DONGRI_RE = re.compile(r'[가-힣]{2,}리|[가-힣]{2,}동')

def parse(name):
    e = {"원본이름": name}
    # 관리번호 (환/재 계열)
    m = re.match(r'([환재])(\d\d)-((?:사|명|외)?\d+(?:-\d+)?)', name)
    subseries = None
    e["관리번호"] = None; e["번호유형"] = "정식"
    if m:
        e["관리번호"] = m.group(0)
        subseries = {"사":"사후","명":"명화외주","외":"외주"}.get(m.group(3)[0])
        if m.group(3).startswith("외"): e["번호유형"] = "외주"
        elif m.group(3).startswith("99"): e["번호유형"] = "임시"
    # 번호 코어 (YY-NN) — 소스 간 매칭 키. 연도폴더 "24-17"·"환24-17" 둘 다 "24-17"
    # 번호코어는 이름 맨 앞(실제 관리번호 위치)에서만 추출.
    # search로 아무 데나 잡으면 번지("1018-1번지"→"18-1") 조각을 관리번호로 오인함.
    mc = re.match(r'([환재])?((?:1[89]|2[0-6]))-(\d+)', name)
    e["번호코어"] = f"{mc.group(2)}-{int(mc.group(3))}" if mc else None  # zero-pad 정규화 (24-01 == 24-1)
    dom_prefix = mc.group(1) if mc else None
    # 괄호: 상태 / 사업자
    상태, 사업자 = None, None
    for g in re.findall(r'\(([^()]*)\)', name):
        g = g.strip()
        if not g: continue
        if any(g == w or g.startswith(w) for w in STATUS):
            상태 = g
        elif re.search(r'㈜|\(주\)|측량|설계|공사|개발|산업|건설|엔지니어링|이엔지|솔라|쏠라|전력|발전|테크', g) \
             or re.fullmatch(r'[가-힣]{2,4}', g):
            사업자 = g
    e["상태"] = 상태; e["사업자"] = 사업자
    # superseded 여부
    e["superseded"] = bool(re.search(r'\((?:X|x|타절|취하|반려|부동의|취소|사업취소|중지|사업중지|추적중단)', name)) \
                      or (상태 in SUPERSEDED if 상태 else False)
    # 종류
    types = detect_types(name)
    if not types and subseries == "사후": types = ["사후환경영향조사"]
    e["보고서종류"] = types
    kind = next((k for k in KIND if k in name), None)
    e["사업종류"] = kind
    # 영역
    영역 = set()
    if dom_prefix == "환": 영역.add("환경")
    if dom_prefix == "재": 영역.add("재해")
    if any(("환경" in t or "비점" in t or "배출" in t or "수질" in t or "경관" in t) for t in types): 영역.add("환경")
    if any(("재해" in t or "우수유출" in t) for t in types): 영역.add("재해")
    e["영역"] = sorted(영역)
    e["_domprefix"] = {"환":"환경","재":"재해"}.get(dom_prefix)
    # 위치
    e["위치토큰"] = list(dict.fromkeys(DONGRI_RE.findall(name)))
    locs = LOC_RE.findall(name)
    e["위치"] = " ".join(dict.fromkeys(locs))
    return e

# ---------- 1. 후보 수집 ----------
candidates = []  # dict: parse결과 + path, source, node정보
def add_candidate(name, path, node, source):
    e = parse(name)
    nd, nf = node_counts(node)
    e["path"] = path; e["source"] = source
    e["has_content"] = (nd > 0 or nf > 0)
    e["has_report"] = any("보고서" in cn for cn in node.get("dirs", {}))
    e["_nf"] = nf; e["_nd"] = nd
    candidates.append(e)

# 0.평가서/{재해,환경}
for dom in ["재해","환경"]:
    for name, node in idx["dirs"]["0. 평가서"]["dirs"][dom]["dirs"].items():
        add_candidate(name, f"/backupenv/0. 평가서/{dom}/{name}", node, "0.평가서")
# 연도폴더
for yr in ["2018","2021","2022","2023","2024","2025"]:
    if yr not in idx["dirs"]: continue
    for name, node in idx["dirs"][yr]["dirs"].items():
        if name in ("ㅎㅈ","폴더모음") or len(name) < 4: continue  # 잡폴더 스킵
        add_candidate(name, f"/backupenv/{yr}/{name}", node, "연도")

# ---------- 2. 클러스터링 (union-find, 강한 신호만 자동 병합) ----------
parent = list(range(len(candidates)))
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb

def dom_compat(a, b):
    da, db = a["_domprefix"], b["_domprefix"]
    return da is None or db is None or da == db

# 클러스터링용 번호코어: 임시(99)·외주 번호는 제외 (여러 사업이 공유 → 오병합)
for c in candidates:
    c["_ckey"] = c["번호코어"] if c["번호유형"] == "정식" else None

# 자동 병합은 반드시 위치토큰이 겹칠 때만 (번지·순번·임시번호 오병합 방지):
#   그 위에서 (같은 번호코어 & 도메인 호환) 또는 (같은 사업자) 이면 병합
n = len(candidates)
for i in range(n):
    ci = candidates[i]
    ti = set(ci["위치토큰"])
    if not ti:
        continue
    for j in range(i+1, n):
        cj = candidates[j]
        if not (ti & set(cj["위치토큰"])):
            continue  # 위치 안 겹치면 병합 금지
        if (ci["_ckey"] and ci["_ckey"] == cj["_ckey"] and dom_compat(ci, cj)) \
           or (ci["사업자"] and ci["사업자"] == cj["사업자"]):
            union(i, j)

clusters = defaultdict(list)
for i in range(n):
    clusters[find(i)].append(i)
clusters = list(clusters.values())

# ---------- 3. 정본 선택 (내용 우선) ----------
def canonical_score(c):
    s = 0
    if c["has_content"]: s += 100
    if c["has_report"]: s += 50
    if c["superseded"]: s -= 80
    if c["상태"] and c["상태"].startswith("완"): s += 20
    # 출처 순위 (약한 tiebreak)
    s += {"연도": 5, "0.평가서": 3}.get(c["source"], 0)
    s += min(c["_nf"], 30) * 0.1  # 파일 많을수록 약간 가점
    return s

# 약한 중복 후보(위치+종류만 겹침, 자동병합 안 함) 탐지용
weakkey = defaultdict(set)  # (loc, kind) -> set(cluster_root)
for i in range(n):
    c = candidates[i]
    if c["사업종류"]:
        for loc in c["위치토큰"]:
            weakkey[(loc, c["사업종류"])].add(find(i))

entries = []
for ci, members in enumerate(clusters):
    cs = [candidates[m] for m in members]
    canon = max(cs, key=canonical_score)
    # 영역/종류/사업자: 클러스터 종합
    영역 = sorted(set(x for c in cs for x in c["영역"]))
    종류 = list(dict.fromkeys(t for c in cs for t in c["보고서종류"]))
    사업자 = canon["사업자"] or next((c["사업자"] for c in cs if c["사업자"]), None)
    상태 = canon["상태"] or next((c["상태"] for c in cs if c["상태"]), None)
    관리번호_best = next((c["관리번호"] for c in cs if c["관리번호"]), None)  # 클러스터 중 정식(환/재) 번호 우선
    번호코어_best = next((c["번호코어"] for c in cs if c["번호코어"]), None)
    flags = []
    root = find(members[0])
    # 약한 중복 후보
    for loc in canon["위치토큰"]:
        if canon["사업종류"]:
            others = weakkey.get((loc, canon["사업종류"]), set()) - {root}
            if others: flags.append(f"중복가능({loc}·{canon['사업종류']})")
    if len({c["_domprefix"] for c in cs if c["_domprefix"]}) > 1:
        flags.append("영역혼재_확인")
    if not canon["has_content"]:
        flags.append("정본불명_실물없음")
    if canon["superseded"] and not any(not c["superseded"] and c["has_content"] for c in cs):
        flags.append("전부_superseded")
    flags = list(dict.fromkeys(flags))
    entries.append({
        "관리번호": 관리번호_best, "번호코어": 번호코어_best,
        "정규화이름": None,  # 아래서 채움
        "원본이름_정본": canon["원본이름"],
        "영역": 영역, "보고서종류": 종류, "상태": 상태, "사업자": 사업자,
        "사업종류": canon["사업종류"], "위치": canon["위치"],
        "정본경로_추정": canon["path"], "정본출처": canon["source"],
        "위치경로": [c["path"] for c in sorted(cs, key=canonical_score, reverse=True)],
        "출처수": len(cs), "플래그": flags, "검수상태": "미검수",
    })

# 정규화 이름 (번호 없어도 위치+종류로 생성, 번호 없으면 ID 부여 플래그)
def normalize(e):
    # 번호는 원본에 있는 것만 사용 — 관리번호(클러스터 중 정식) 우선, 없으면 번호코어. 접두 합성·지어내기 안 함.
    num = e["관리번호"] or e["번호코어"]
    locs = LOC_RE.findall(e["원본이름_정본"])[:2]
    typ = "/".join(e["보고서종류"]) if e["보고서종류"] else (f"{e['영역'][0]}(종류미상)" if e["영역"] else "기타")
    parts = ([num] if num else []) + ([" ".join(locs)] if locs else []) + ([e["사업종류"]] if e["사업종류"] else [])
    name = " ".join(parts) + f" · {typ}"
    if e["상태"]: name += f" ({e['상태']})"
    if e["사업자"]: name += f" [{e['사업자']}]"
    return name
for i, e in enumerate(entries):
    e["정규화이름"] = normalize(e)
    myr = re.search(r'\d\d', e["번호코어"] or e["관리번호"] or "")  # 연도 = 코어 or 관리번호(외/명 계열)에서
    e["id"] = f"ENG-20{myr.group(0)}-{i:03d}" if myr else f"ENG-0000-{i:03d}"
    if not e["관리번호"] and not e["번호코어"]:   # 관리번호·코어 둘 다 없을 때만 (외/명은 번호 있음)
        e["플래그"].append("번호미상_ID부여")

# ---------- 출력: 통계 ----------
print(f"후보 폴더: {len(candidates)}  (0.평가서 {sum(1 for c in candidates if c['source']=='0.평가서')} + 연도 {sum(1 for c in candidates if c['source']=='연도')})")
print(f"클러스터(유니크 사업): {len(entries)}")
multi = [e for e in entries if e["출처수"] > 1]
print(f"  다중출처(병합됨): {len(multi)}  /  단일출처: {len(entries)-len(multi)}")
fc = Counter()
for e in entries:
    for f in e["플래그"]: fc[re.sub(r'\(.*','',f)] += 1
print(f"  플래그 분포: {dict(fc)}")
print(f"  정본출처 분포: {dict(Counter(e['정본출처'] for e in entries))}")

print("\n[다중출처 병합 예시 5]")
for e in sorted(multi, key=lambda x:-x["출처수"])[:5]:
    print(f"  ▸ {e['정규화이름']}  (출처 {e['출처수']}, 정본={e['정본출처']})")
    for p in e["위치경로"][:4]:
        print(f"       {p[:78]}")

# JSON 저장
json.dump(entries, open(ROOT/"catalog/data/nas_catalog.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

# ---------- 사람용 트리 (영역 → 종류 → 정규화 이름) ----------
def short_flags(fl):
    m = {"정본불명_실물없음":"실물없음","번호미상_ID부여":"번호미상","중복가능":"중복?",
         "전부_superseded":"폐기?","영역혼재_확인":"영역확인"}
    tags = [m.get(re.sub(r'\(.*','',f), re.sub(r'\(.*','',f)) for f in fl]
    return ("  ‹" + " ".join(dict.fromkeys(tags)) + "›") if tags else ""

byarea = defaultdict(lambda: defaultdict(list))
for e in entries:
    area = e["영역"][0] if e["영역"] else "미분류"
    typ = e["보고서종류"][0] if e["보고서종류"] else "기타"
    byarea[area][typ].append(e)

multi = sum(1 for e in entries if e["출처수"] > 1)
# 플래그 요약 (뜻 + 건수)
flagmeta = [
    ("실물없음", "정본불명_실물없음", "아직 NAS에 업로드 안 됨 (연도폴더에도 실물 없음)"),
    ("번호미상", "번호미상_ID부여", "순번 폴더라 관리번호 없음 → 우리가 ID 부여"),
    ("중복?",   "중복가능",        "위치+종류 겹치는 다른 클러스터 있음 → 같은 사업인지 확인"),
    ("폐기?",   "전부_superseded", "클러스터 전부 취하/타절 → 진행 여부 확인"),
    ("영역확인", "영역혼재_확인",   "환·재 접두가 섞임 → 영역 확인"),
]
flagcnt = Counter()
for e in entries:
    for f in e["플래그"]: flagcnt[re.sub(r'\(.*', '', f)] += 1
nflagged = sum(1 for e in entries if e["플래그"])
미분류N = sum(1 for e in entries if not e["영역"])

L = ["# NAS 정본 카탈로그 v1 — 검수용 (전수)", "",
     f"> 전체 폴더 {len(candidates)}개(0.평가서+연도) → 클러스터링 → **유니크 사업 {len(entries)}건**. 병합 {multi}건.",
     "> 정본 선택 규칙: `reorg_strategy.md` §3", "",
     "## 플래그 요약",
     f"`‹…›` = **확인 항목(오류 아님)**. 플래그 달린 엔트리 {nflagged}/{len(entries)}건. 사람 판단 워크리스트는 `nas_catalog_todo.md`.", "",
     "| 태그 | 의미 | 건수 |", "|---|---|--:|"]
for tag, key, desc in flagmeta:
    L.append(f"| `{tag}` | {desc} | {flagcnt.get(key, 0)} |")
L.append(f"| *(미분류)* | 영역(재해/환경) 판정 불가 — 아래 트리 `미분류/` 섹션 | {미분류N} |")
L += ["", "## 트리 (영역 → 종류 → 정규화 이름)", "", "```"]
L.append(f"정본 카탈로그 v1  ({len(entries)}건, 전수)")
areas = [a for a in ["환경","재해","미분류"] if a in byarea]
for ai, area in enumerate(areas):
    al = ai == len(areas)-1
    ab, ac = ("└─ ","   ") if al else ("├─ ","│  ")
    tot = sum(len(v) for v in byarea[area].values())
    L.append(f"{ab}{area}/  ({tot})")
    types = sorted(byarea[area])
    for ti, typ in enumerate(types):
        tl = ti == len(types)-1
        tb, tc = ("└─ ","   ") if tl else ("├─ ","│  ")
        lst = sorted(byarea[area][typ], key=lambda x: x["번호코어"] or "zz")
        L.append(f"{ac}{tb}{typ}/  ({len(lst)})")
        for li, e in enumerate(lst):
            lb = "└─ " if li == len(lst)-1 else "├─ "
            src = "" if e["출처수"]==1 else f"  ({e['출처수']}출처)"
            L.append(f"{ac}{tc}{lb}{e['정규화이름']}{src}{short_flags(e['플래그'])}")
L.append("```")
open(ROOT/"catalog/review/catalog_review.md","w",encoding="utf-8").write("\n".join(L))

# ---------- 검수 필요 워크리스트 (사람 판단 항목만 따로) ----------
def has_flag(e, key): return any(f.startswith(key) for f in e["플래그"])
미분류 = [e for e in entries if not e["영역"]]
중복후보 = [e for e in entries if has_flag(e, "중복가능")]
폐기 = [e for e in entries if has_flag(e, "전부_superseded")]
혼재 = [e for e in entries if has_flag(e, "영역혼재")]

W = ["# NAS 카탈로그 — 검수 필요 워크리스트 (자동 생성)", "",
     "> `catalog/build_catalog.py`가 생성. **사람이 확정해야 하는 항목만** 모음.",
     "> 확인 후 결과를 카탈로그에 반영하면 됨. (전체 트리는 `nas_catalog_review.md`)", ""]

W.append(f"## ① 영역 미상 — {len(미분류)}건")
W.append("이름에 평가종류(소규모환경/재해영향평가 등)가 없어 **재해/환경 판정 불가**.")
W.append("**확인법**: 정본경로 폴더 안 보고서·계약서 열람 또는 담당자. 확인 후 영역·종류 기입.\n")
for e in sorted(미분류, key=lambda x: x["정본경로_추정"] or ""):
    hint = " · ".join(x for x in [e["사업종류"], e["상태"]] if x)
    W.append(f"- [ ] {e['원본이름_정본']}" + (f"  ({hint})" if hint else ""))
    W.append(f"      `{e['정본경로_추정']}`")

W.append(f"\n## ② 중복 후보 — {len(중복후보)}건")
W.append("같은 위치+종류라 자동병합 안 함. **같은 사업인지** 확인 후 병합/분리.\n")
for e in sorted(중복후보, key=lambda x: x["정규화이름"] or ""):
    dup = " ".join(f for f in e["플래그"] if f.startswith("중복가능"))
    W.append(f"- [ ] {e['정규화이름']}  ‹{dup}›")
    W.append(f"      `{e['정본경로_추정']}`")

if 폐기 or 혼재:
    W.append(f"\n## ③ 기타 — 전부폐기 {len(폐기)}건 · 영역혼재 {len(혼재)}건")
    W.append("전부폐기=클러스터 전부 취하/타절(진행여부 확인) · 영역혼재=환·재 접두 섞임(영역 확인)\n")
    for e in 폐기 + 혼재:
        W.append(f"- [ ] {e['정규화이름'] or e['원본이름_정본']}  ‹{' '.join(e['플래그'])}›")
        W.append(f"      `{e['정본경로_추정']}`")

open(ROOT/"catalog/review/catalog_todo.md","w",encoding="utf-8").write("\n".join(W))

print(f"\n[✓] catalog/data/nas_catalog.json ({len(entries)} 유니크 사업)")
print(f"[✓] catalog/review/catalog_review.md (전체 트리)")
print(f"[✓] catalog/review/catalog_todo.md (검수: 미분류 {len(미분류)}·중복후보 {len(중복후보)}·기타 {len(폐기)+len(혼재)})")

#!/usr/bin/env python3
"""
통계 원자료 카탈로그 빌더 — 지역개황(0200)이 인용하는 통계의 소재 지도.

보고서를 분류하는 build_catalog.py 와 **축이 다르다**. 여기서 다루는 것은
사업이 아니라 **통계 자료**다 (지자체 × 회차 / 자료종류 × 발행연도).

  1. NAS 인덱스에서 통계 원자료 후보 수집
  2. 두 갈래로 분류 — 지자체 통계연보 / 전국 통계
  3. 지자체·회차·기준연도·배포형식 파싱  ← **형식이 곧 자동화 가능성이다**
  4. → catalog/data/stats_catalog.json + catalog/review/stats_catalog.md

설계 근거: docs/20260819_통계원자료_소싱실증.md §5 "통계 관리 체계 — 관리 단위 제안"
"""
import json, re, gzip
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
idx = json.load(gzip.open(ROOT / "catalog/data/nas_index.json.gz", "rt", encoding="utf-8"))

# ---------- 1. 수집 ----------
# 전국 통계는 rule small-env/regional-overview.md §2-2 의 목록과 짝을 이룬다.
NATIONAL = [
    ("상수도통계",   r"상수도\s*통계"),
    ("하수도통계",   r"하수도\s*통계"),
    ("폐기물처리현황", r"폐기물\s*발생\s*및\s*처리현황|전국\s*폐기물"),
    ("음식물류처리시설", r"음식물류\s*폐기물\s*처리시설"),
    ("하천일람",     r"하천\s*일람"),
    ("상수원보호구역", r"상수원\s*보호구역.*지정현황|상수원보호구역현황"),
    ("보호구역지정현황", r"(야생생물|야생동물|습지|산림유전자원|생태.?경관)\s*보호?구역.*(지정)?현황"),
    ("자연공원",     r"국립공원기본통계|도립.?군립공원\s*기본통계"),
    ("조류센서스",   r"조류\s*동시\s*센서스"),
]
YEARBOOK = re.compile(r"통계\s*연보")
# 교육/에너지 등 다른 축의 연보는 지역개황이 쓰지 않는다.
NOT_YEARBOOK = re.compile(r"교육통계연보|에너지통계연보|환경통계연보|교통량\s*통계연보|상시\s*통계연보|목차")

DOC_EXT = {"pdf", "zip", "hwp", "hwpx", "xls", "xlsx", "xlsb", "csv"}

rows = []
def walk(node):
    p = node.get("path", "")
    for f in node.get("files", []):
        name = f if isinstance(f, str) else f.get("name", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in DOC_EXT:
            continue
        if YEARBOOK.search(name) and not NOT_YEARBOOK.search(name):
            rows.append(("지자체통계연보", name, p, ext))
            continue
        for kind, pat in NATIONAL:
            if re.search(pat, name):
                rows.append((kind, name, p, ext))
                break
    for ch in node.get("dirs", {}).values():
        walk(ch)
walk(idx)

# ---------- 2. 파싱 ----------
# 지자체 이름은 파일명에 없을 때가 많다 (`통계연보.pdf`) — 경로에서 찾는다.
SIGUN = (
    "가평|강릉|강화|고성|공주|과천|괴산|김포|남양주|논산|단양|당진|동해|보령|보은|부여|삼척|서산|"
    "성남|세종|속초|아산|안성|양구|양양|양주|양평|여주|연천|영동|영월|예산|오산|옥천|용인|원주|"
    "음성|의왕|이천|인제|정선|제천|증평|진천|천안|철원|청양|청주|춘천|충주|태백|태안|평창|포천|"
    "하남|홍성|홍천|화성|화천|횡성|"
    # 다른 권역 — 전략환경영향평가 등에서 간간이 나온다
    "성주|칠곡|경산|구미|김천|상주|문경|영주|안동|남원|정읍|김제|부안"
)
# 도 단위 연보는 시군과 축이 다르다 (지역개황은 시군 판을 쓴다).
RE_DO = re.compile(r"(강원|경기|충북|충남|전북|전남|경북|경남)\s*(도)?\s*통계연보")
RE_SIGUN = re.compile(rf"({SIGUN})\s*(시|군)?")
RE_HOE = re.compile(r"제?\s?(\d{1,3})\s?회")
RE_YEAR = re.compile(r"(19|20)(\d{2})")

def parse_sigun(name, path):
    m = RE_DO.search(name)
    if m:
        return m.group(1) + "도"
    m = RE_SIGUN.search(name)
    if m:
        return m.group(1)
    # 경로는 뒤쪽(사업 폴더)일수록 신뢰도가 높다
    for seg in reversed(path.split("/")):
        m = RE_SIGUN.search(seg)
        if m:
            return m.group(1)
    return None

def parse_year(name):
    ys = [int(m.group(0)) for m in RE_YEAR.finditer(name)]
    ys = [y for y in ys if 1990 <= y <= 2030]
    return min(ys) if ys else None      # 파일명의 첫 연도 = 기준연도인 경우가 많다

def parse_form(name, ext):
    """배포 형식 — 자동화 가능성을 가르는 축 (소싱실증 §3).

    zip 안을 열어보지 않고 파일명으로 추정한다. 확정은 실제 내려받은 뒤에만 가능하다."""
    if ext in ("xlsx", "xls", "xlsb", "csv"):
        return "엑셀"
    if ext in ("hwp", "hwpx"):
        return "한글"
    if ext == "zip":
        return "엑셀(추정)" if re.search(r"엑셀|excel|xls", name, re.I) else "묶음(미확인)"
    if ext == "pdf":
        return "PDF(스캔여부 미확인)"
    return ext

entries = []
for kind, name, path, ext in rows:
    hoe = RE_HOE.search(name)
    entries.append({
        "종류": kind,
        "지자체": parse_sigun(name, path) if kind == "지자체통계연보" else None,
        "회차": int(hoe.group(1)) if hoe else None,
        "연도": parse_year(name),
        "형식": parse_form(name, ext),
        "파일명": name,
        "경로": path,
    })

# ---------- 3. 중복 묶기 ----------
# 같은 판이 사업 폴더마다 복사돼 있다 (당진 제61회 4벌 등). 사본 경로를 한 항목에 모은다.
merged = {}
for e in entries:
    key = (e["종류"], e["지자체"], e["회차"], e["연도"], e["파일명"])
    if key in merged:
        merged[key]["사본"].append(e["경로"])
    else:
        e = dict(e); e["사본"] = [e.pop("경로")]
        merged[key] = e
out = sorted(merged.values(), key=lambda e: (e["종류"], e["지자체"] or "", -(e["연도"] or 0)))

data_dir = ROOT / "catalog/data"; data_dir.mkdir(parents=True, exist_ok=True)
json.dump(out, open(data_dir / "stats_catalog.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------- 4. 리뷰 문서 ----------
yb = [e for e in out if e["종류"] == "지자체통계연보"]
nat = [e for e in out if e["종류"] != "지자체통계연보"]
by_sigun = defaultdict(list)
for e in yb:
    by_sigun[e["지자체"] or "(미상)"].append(e)

L = []
A = L.append
A("# 통계 원자료 카탈로그 — 지역개황(0200) 인용 통계의 소재 지도\n")
A("> `catalog/build_stats_catalog.py` 자동 생성. 축은 **사업이 아니라 통계 자료**다.")
A("> 근거·배경: [`docs/20260819_통계원자료_소싱실증.md`](../../docs/20260819_통계원자료_소싱실증.md)")
A(f"> 스냅샷: `nas_index.json.gz` ({idx.get('_meta',{}).get('crawled','?')})\n")
A(f"**고유 {len(out)}건** (사본 포함 {sum(len(e['사본']) for e in out)}건) "
  f"— 지자체 통계연보 {len(yb)} · 전국 통계 {len(nat)}\n")

A("## 1. 지자체 통계연보 — 지자체 × 회차\n")
A("| 지자체 | 보유 판 | 형식 | 최신 |")
A("|---|--:|---|---|")
for s, es in sorted(by_sigun.items(), key=lambda kv: -len(kv[1])):
    forms = Counter(e["형식"] for e in es)
    newest = max(es, key=lambda e: (e["연도"] or 0, e["회차"] or 0))
    label = f"{newest['연도'] or '?'}" + (f" (제{newest['회차']}회)" if newest["회차"] else "")
    A(f"| {s} | {len(es)} | {' · '.join(f'{k} {v}' for k, v in forms.most_common())} | {label} |")

A("\n## 2. 배포 형식 분포 — **자동화 가능성의 축** ★\n")
A("| 형식 | 건수 | 처리 |")
A("|---|--:|---|")
NOTE = {"엑셀": "✅ 바로 표로 변환", "엑셀(추정)": "✅ 압축 풀어 확인 (파일명 CP949)",
        "한글": "⭕ 통계청 배포 원본 — 파싱 가능", "PDF(스캔여부 미확인)": "⚠️ 스캔이면 OCR 필요",
        "묶음(미확인)": "⚠️ 열어봐야 안다"}
for k, v in Counter(e["형식"] for e in yb).most_common():
    A(f"| {k} | {v} | {NOTE.get(k,'')} |")

A("\n## 3. 전국 통계 — 자료종류 × 발행연도\n")
A("| 자료 | 건수 | 연도 폭 |")
A("|---|--:|---|")
for k, es in sorted(((k, [e for e in nat if e["종류"] == k]) for k in {e["종류"] for e in nat}),
                    key=lambda kv: -len(kv[1])):
    ys = sorted({e["연도"] for e in es if e["연도"]})
    A(f"| {k} | {len(es)} | {f'{ys[0]}~{ys[-1]}' if ys else '—'} |")

A("\n## 4. 중복 — 같은 판이 사업 폴더마다 복사돼 있다\n")
dup = sorted([e for e in out if len(e["사본"]) > 1], key=lambda e: -len(e["사본"]))[:12]
A("| 사본 수 | 자료 |")
A("|--:|---|")
for e in dup:
    A(f"| {len(e['사본'])} | {e['파일명'][:52]} |")
A("\n> 최신판이 어느 것인지 파일명만으로는 알 수 없다. **이 카탈로그가 그 답을 대신한다.**")

rev = ROOT / "catalog/review"; rev.mkdir(parents=True, exist_ok=True)
(rev / "stats_catalog.md").write_text("\n".join(L), encoding="utf-8")
print(f"고유 {len(out)}건 (통계연보 {len(yb)} · 전국 {len(nat)}) → catalog/data/stats_catalog.json")
print(f"                                              → catalog/review/stats_catalog.md")

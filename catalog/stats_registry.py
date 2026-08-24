#!/usr/bin/env python3
"""
지역개황이 쓰는 **통계 자료 전수 목록**과 보유 현황.

세 가지를 한자리에 놓는다.

    ① 필요   — 어느 절이 무엇을 쓰나 (`.claude/rules/small-env/regional-overview.md` §2)
    ② 보유   — 우리가 값을 뜬 판(매니페스트) · NAS 에 있는 판(`stats_catalog`)
    ③ 발행처 — 최신판을 어디서 받나

⚠️ **NAS 최신 ≠ 발행처 최신.** 2026-08-24 실측 — 상수도통계 2024판은 골든셋이
인용했는데 **NAS 전체에 없었다.** NAS 는 "우리가 가진 것" 이지 "최신" 이 아니다.
그래서 격차는 **발행처 ↔ 보유** 로 잰다.

    python catalog/stats_registry.py            # 전수 목록 + 보유 현황
    python catalog/stats_registry.py --todo     # 아직 손 안 댄 것만
    python catalog/stats_registry.py --scan     # NAS 표준 창고 + 로컬을 훑어 보유 정리
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "catalog/data/stats_values.manifest.json"
CATALOG = ROOT / "catalog/data/stats_catalog.json"

# 상태 표기
DONE, PART, TODO = "✅", "◐", "❌"

# ── ① 필요 자료 전수 ───────────────────────────────────────────────────────
# `취득` 은 **실측으로 확인된 것만** ✅ 로 적는다. 확인 안 한 것은 `None` 이다 —
# 추측해서 적으면 나중에 그것이 근거로 쓰인다 (`common.md` 환각 금지).
REGISTRY = [
    # ── 연 1회 전국 통계 ────────────────────────────────────────────────
    dict(자료="상수도통계", 찾기=r"상수도\s*통계", 절=["2.6.1 취수장", "2.6.2 정수장"],
         기관="기후에너지환경부 / 국가상수도정보시스템", 주기="연 1회",
         목록="https://www.waternow.go.kr/web/board/STAT?pMENUID=9",
         상세="https://www.waternow.go.kr/web/board/STAT/{id}/?pMENUID=9",
         받기="GET /jfile/readDownloadFile.do?fileId=..&fileSeq=..",
         취득="확인", 파서=DONE),
    dict(자료="하수도통계", 찾기=r"하수도\s*통계", 절=["2.7.1 공공하수처리시설", "2.7.2 분뇨처리시설"],
         기관="기후에너지환경부 / 하수도정보시스템", 주기="연 1회",
         목록="https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/list.do",
         상세="POST /bbs/lay1/WS10000015/{id}/view.do  (bbsId=BBS_000007 필수)",
         받기="GET /bbs/fileDownload.do?atcmtFileId=..&fileSn=..",
         취득="확인", 파서=DONE),
    dict(자료="전국 폐기물 발생 및 처리현황", 찾기=r"폐기물\s*발생\s*및\s*처리현황|폐기물처리현황|폐기물2\d{3}", 절=["2.7.4 매립처리시설", "2.7.5 소각시설"],
         기관="기후에너지환경부·한국환경공단 / 자원순환정보시스템", 주기="연 1회(12월 공표)",
         목록="https://www.recycling-info.or.kr/rrs/stat/envStatList.do?bbsId=BBSMSTR_000000000002&s_nttSj=KEC006",
         상세="https://www.recycling-info.or.kr/rrs/stat/envStatDetail.do?nttId={id}",
         받기="POST /cmm/fms/FileDownload.do  (atchFileId·fileSn)",
         취득="확인", 파서=DONE, 비고="`02_06 처리업체현황_Ⅰ` 의 `1-가. 공공소각`·`1-다. 공공매립` 시트"),
    dict(자료="음식물류 폐기물 처리시설 현황", 찾기=r"음식물류", 절=["2.7.3 음식물류"],
         기관="기후에너지환경부", 주기="연 1회",
         목록=None, 취득=None, 파서=DONE,
         비고="2023판 엑셀. ⚠️ 발행처 경로 미확인 — 창고 사본으로 쓴다"),
    dict(자료="산업입지정보시스템", 찾기=r"산업단지|농공단지|산업입지", 절=["2.5.3 산업 및 농공단지"],
         기관="한국산업단지공단", 주기="분기",
         목록="https://www.data.go.kr/data/3041272/fileData.do", 취득="확인", 파서=DONE,
         비고="공공데이터포털 파일데이터 (국가승인통계 399003호). **2025년 4분기판 취득**. "
              "⚠️ 원자료는 **천㎡ 반올림** — 골든셋은 ㎡ 정밀값을 쓰면서 머리는 `면적(천㎡)` 라 적었다"),
    dict(자료="한국하천일람", 찾기=r"하천일람", 절=["2.8.3 수계"],
         기관="환경부 / 국가하천정보", 주기="연 1회",
         목록=None, 취득=None, 파서=DONE,
         비고="⚠️ **시군이 아니라 하천으로 찾는다** → `engine/stats_irregular.py`. "
              "시도별 시트. `engine/hydro.py`(삽도)는 하천망 공간자료를 따로 쓴다"),

    # ── 2.3.2 수환경 ────────────────────────────────────────────────────
    dict(자료="상수원보호구역 지정현황", 찾기=r"상수원보호구역", 절=["2.3.2 수환경"],
         기관="환경부", 주기="수시", 목록=None, 취득=None, 파서=DONE,
         비고="채색 VWorld `LT_C_UM710` · 표는 2024.12월 엑셀 (원주 1행 정답 일치)"),
    dict(자료="수변구역 지정현황", 찾기=r"수변구역", 절=["2.3.2 수환경"],
         기관="환경부(유역청)", 주기="수시", 목록=None, 취득=None, 파서=DONE,
         비고="**hwpx** — 시군 면적이 셀 안 목록에 있다 → `engine/stats_hwpx.py`"),
    dict(자료="폐수배출시설 설치제한지역", 찾기=r"설치제한", 절=["2.3.2 수환경"],
         기관="환경부", 주기="수시", 목록=None, 취득=None, 파서=TODO),
    dict(자료="배출허용기준 지역지정", 찾기=r"배출허용기준|2007-107", 절=["2.3.2 수환경"],
         기관="환경부고시 제2007-107호", 주기="고시(사실상 고정)",
         목록=None, 취득="법령", 파서=TODO, 비고="법령 별표 — 개정일만 관리"),

    # ── 2.3.3 자연생태환경 ──────────────────────────────────────────────
    dict(자료="야생생물 보호구역 지정현황", 찾기=r"야생생물|야생동물", 절=["2.3.3 자연생태환경"],
         기관="환경부", 주기="연 1회", 목록=None, 취득=None, 파서=DONE,
         비고="⚠️ **시군 열이 없다** — 이름 안에서 찾는다 → `stats_irregular.py`. "
              "창고 최신이 **2017.12월**(골든셋도 그 판). 더 새 판은 발행처 미확인"),
    dict(자료="습지보호지역·람사르", 찾기=r"습지|람사", 절=["2.3.3 자연생태환경"],
         기관="환경부", 주기="수시", 목록=None, 취득=None, 파서=DONE,
         비고="**텍스트 PDF** 4쪽 ('24.12월 = 골든셋 인용판) → `stats_pdf.py`"),
    dict(자료="자연공원(국립·도립·군립)", 찾기=r"국립공원|도립공원|군립공원|도립·군립", 절=["2.3.3 자연생태환경"],
         기관="환경부·국립공원공단", 주기="연 1회", 목록=None, 취득=None, 파서=DONE,
         비고="**텍스트 PDF** (스캔 아님) → `engine/stats_pdf.py`. 원주·평창 합계검산 OK. ⚠️ 골든셋은 **175.668**(치악산)인데 2024·2025판 모두 **176.567** — 더 옛 판이다(창고에 없음)"),
    dict(자료="백두대간보호지역", 찾기=r"백두대간", 절=["2.3.3 자연생태환경"],
         기관="산림청", 주기="수시", 목록=None, 취득=None, 파서=DONE,
         비고="산림청 고시 **텍스트 PDF** 192쪽(시군별 필지 목록) → `stats_pdf.py`. `0. 산줄기/` 의 shp 는 삽도용 공간자료로 별개"),
    dict(자료="산림유전자원보호구역", 찾기=r"산림유전자원", 절=["2.3.3 자연생태환경"],
         기관="산림청", 주기="연 1회", 목록=None, 취득=None, 파서=DONE,
         비고="2023년말 엑셀. 원주 골든셋 1행 정답 일치. ⚠️ **위 요약 블록 때문에 `머리글행=[6,7]` 로 못 박아야** 한다"),
    dict(자료="겨울철 조류 동시 센서스", 찾기=r"센서스", 절=["2.3.3 자연생태환경"],
         기관="국립생물자원관", 주기="연 1회", 목록=None, 취득=None, 파서=TODO,
         비고="NAS jdw 에 2022·2023 **PDF** + 센서스지도"),
    dict(자료="생태·경관보전지역", 찾기=r"생태경관|생태·경관", 절=["2.3.3 자연생태환경"],
         기관="해양수산부(공공데이터포털 WFS)", 주기="수시",
         목록="https://www.data.go.kr", 취득="API", 파서=DONE,
         비고="`engine/ecgy.py` 판정 8/8 · **지정현황 표는 hwpx 로 해결(F-10 닫힘)** — 평창 79.259 정답 일치. ⚠️ 면적이 판마다 다르다(`24.5월` 80.426, `24.3.8확대`)"),

    # ── 공간 자료 ───────────────────────────────────────────────────────
    dict(자료="생태·자연도", 찾기=r"생태자연도|생태·자연도", 절=["2.8.1 생태·자연도"],
         기관="국립생태원 EcoBank", 주기="수시", 목록=None, 취득="API", 파서=DONE,
         비고="`engine/ecology.py` — 등급 판정 골든셋 8/8"),

    # ── 지자체별 ────────────────────────────────────────────────────────
    dict(자료="지자체 통계연보", 찾기=r"통계연보", 절=["2.1.1 지리적 특성", "2.2.1 지목별 토지이용",
                                    "2.2.2 용도지역", "2.5.1 도로",
                                    "2.5.2 환경오염물질 배출시설", "2.5.4 자동차",
                                    "2.6.3 문화재"],
         기관="각 지자체", 주기="연 1회 (지자체마다 다름)",
         목록=None, 취득=None, 파서=PART,
         비고="`engine/stats_extract.py` 가 **6절** 처리. "
              "⚠️ **2.1.1 극점 좌표는 엑셀 편에 아예 없다** (천안 2023판 전 시트 전 행 확인). "
              "통계연보 **책자 본문**의 위치·연혁 절에만 있다 → hwp/PDF 파싱이거나 `[확인 필요]`. "
              "배포 형식도 제각각 — 엑셀 4 / zip 43 / **스캔 PDF 34** (확인요청 F-4)"),
]


# 회사 표준 통계 창고 — 실무자 한 명이 이미 모아 둔 곳 (2026-08-24 발견)
WAREHOUSE = "/backupenv/jdw/3. 자료"
LOCAL = ROOT / "raw_data/nas/stats/_national"
HOLDINGS = ROOT / "catalog/data/stats_holdings.json"

# 파싱 난이도 — **형식이 곧 작업량이다**
def fmt_of(name):
    n = name.lower()
    if n.endswith((".xlsx", ".xls", ".xlsb")):
        return "엑셀"
    if n.endswith((".hwp", ".hwpx")):
        return "한글"
    if n.endswith(".pdf"):
        return "PDF"
    if n.endswith(".zip"):
        return "묶음"
    if n.endswith((".shp", ".tif")):
        return "공간자료"
    return "기타"


def basis_of(name):
    """파일명에서 기준 시점을 읽는다. `('24.12월` · `2023년말` · `2022` 등."""
    m = re.search(r"[\'\(]?(\d{2})[\.\-](\d{1,2})월", name)
    if m:
        yy = int(m.group(1))
        return 2000 + yy + (0 if yy < 90 else -100), int(m.group(2))
    m = re.search(r"(20\d\d)", name)
    if m:
        return int(m.group(1)), None
    # `''24년 기준` — 세기 없이 두 자리만 쓰는 파일이 꽤 있다
    m = re.search(r"['\"\u2018\u2019]*(\d{2})년", name)
    return (2000 + int(m.group(1)), None) if m else (None, None)


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def status():
    man = load(MANIFEST) or {"판": []}
    cat = load(CATALOG) or []
    have = {}
    for e in man["판"]:
        have.setdefault(e["자료"], []).append(e["판"])
    nas = {}
    for x in cat:
        if x.get("연도"):
            nas.setdefault(x["종류"], set()).add(x["연도"])

    # stats_catalog 의 `종류` 는 축약형이라 이름을 맞춰 준다
    ALIAS = {"상수도통계": "상수도통계", "하수도통계": "하수도통계",
             "전국 폐기물 발생 및 처리현황": "폐기물처리현황",
             "음식물류 폐기물 처리시설 현황": "음식물류처리시설",
             "한국하천일람": "하천일람", "자연공원(국립·도립·군립)": "자연공원",
             "산림유전자원보호구역": "보호구역지정현황",
             "겨울철 조류 동시 센서스": "조류센서스",
             "상수원보호구역 지정현황": "상수원보호구역",
             "지자체 통계연보": "지자체통계연보"}

    print("# 지역개황 통계 자료 전수 — 필요 · 보유 · 발행처\n")
    print("| 자료 | 쓰는 절 | 파서 | 값 보유(판) | NAS 최신 | 발행처 취득 |")
    print("|---|--:|:--:|---|:--:|:--:|")
    for r in REGISTRY:
        vals = have.get(r["자료"], [])
        nyr = sorted(nas.get(ALIAS.get(r["자료"], r["자료"]), []), reverse=True)
        취득 = {"확인": "✅ 실측", "API": "✅ API", "법령": "— 법령", None: "❓ 미확인"}[r.get("취득")]
        print(f"| {r['자료']} | {len(r['절'])} | {r['파서']} | "
              f"{'·'.join(map(str, sorted(vals))) or '—'} | {nyr[0] if nyr else '—'} | {취득} |")

    # ⚠️ **절 수는 자료 수와 다르다** — 2.3.2 수환경 한 절에 자료가 4종, 2.3.3 은 6종 들어간다.
    #    자료를 세면 절을 부풀린다. 고유 절로 센다.
    all_secs, done_secs = set(), set()
    for r in REGISTRY:
        all_secs |= set(r["절"])
        if r["파서"] == DONE:
            done_secs |= set(r["절"])
    # 통계연보는 부분 완료 — 6절 처리, 2.1.1 만 미착수
    done_secs |= {s for s in REGISTRY[-1]["절"] if not s.startswith("2.1.1")}

    done = sum(1 for r in REGISTRY if r["파서"] == DONE)
    part = sum(1 for r in REGISTRY if r["파서"] == PART)
    print(f"\n**자료 {len(REGISTRY)}종 — 파서 완료 {done} · 부분 {part} · 미착수 "
          f"{len(REGISTRY) - done - part}**")
    print(f"**절 {len(done_secs)}/{len(all_secs)} 완료**  "
          f"(남은 절: {', '.join(sorted(all_secs - done_secs))})")
    print(f"\n발행처 취득 경로 실측 확인: "
          f"{sum(1 for r in REGISTRY if r.get('취득') in ('확인', 'API'))}/{len(REGISTRY)}종")


def todo():
    print("# 아직 손 안 댄 것\n")
    for r in REGISTRY:
        if r["파서"] == DONE:
            continue
        print(f"- **{r['자료']}** ({', '.join(r['절'])})")
        print(f"    기관 {r['기관']} · 주기 {r['주기']}")
        print(f"    발행처 {r.get('목록') or '❓ 미확인'}")
        if r.get("비고"):
            print(f"    {r['비고']}")


def scan():
    """NAS 표준 창고와 로컬을 훑어 **자료별 최신 보유**를 정리한다.

    ⚠️ 발행처 최신과는 다르다 — 이것은 *"우리가 뭘 갖고 있나"* 다.
    2026-08-24 실측에서 상수도 2024판은 **NAS 전체에 없었다.**
    """
    names = []
    try:
        sys.path.insert(0, str(ROOT / "catalog"))
        from synology_filestation import connect      # noqa
        for f in connect().list_folder(WAREHOUSE):
            if not f.get("isdir"):
                names.append((f["name"], f.get("additional", {}).get("size", 0), WAREHOUSE))
    except Exception as e:
        print(f"⚠️ NAS 조회 실패 ({e}) — 로컬만 본다")
    for p in sorted(LOCAL.glob("*")):
        names.append((p.name, p.stat().st_size, str(LOCAL.relative_to(ROOT))))

    out = {"갱신": __import__("datetime").date.today().isoformat(),
           "창고": WAREHOUSE, "자료": {}}
    print("# 자료별 최신 보유 — NAS 표준 창고 + 로컬\n")
    print("| 자료 | 최신 보유 | 형식 | 파일 | 사본 |")
    print("|---|:--:|:--:|---|--:|")
    for r in REGISTRY:
        pat = r.get("찾기")
        if not pat:
            continue
        hit = [(n, sz, loc) for n, sz, loc in names if re.search(pat, n)]
        ranked = sorted(hit, key=lambda x: (basis_of(x[0])[0] or 0,
                                            basis_of(x[0])[1] or 0), reverse=True)
        if not ranked:
            print(f"| {r['자료']} | — | — | **없음** | 0 |")
            out["자료"][r["자료"]] = {"최신": None, "사본": 0}
            continue
        top = ranked[0]
        yr, mo = basis_of(top[0])
        basis = f"{yr}" + (f".{mo}월" if mo else "")
        print(f"| {r['자료']} | {basis} | {fmt_of(top[0])} | {top[0][:44]} | {len(hit)} |")
        out["자료"][r["자료"]] = {
            "최신": basis, "형식": fmt_of(top[0]), "파일": top[0],
            "위치": top[2], "사본": len(hit),
        }
    HOLDINGS.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {HOLDINGS.relative_to(ROOT)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--todo", action="store_true")
    ap.add_argument("--scan", action="store_true")
    a = ap.parse_args()
    if a.scan:
        return scan()
    return todo() if a.todo else status()


if __name__ == "__main__":
    sys.exit(main() or 0)

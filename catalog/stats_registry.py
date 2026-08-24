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
"""
import argparse
import json
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
    dict(자료="상수도통계", 절=["2.6.1 취수장", "2.6.2 정수장"],
         기관="기후에너지환경부 / 국가상수도정보시스템", 주기="연 1회",
         목록="https://www.waternow.go.kr/web/board/STAT?pMENUID=9",
         상세="https://www.waternow.go.kr/web/board/STAT/{id}/?pMENUID=9",
         받기="GET /jfile/readDownloadFile.do?fileId=..&fileSeq=..",
         취득="확인", 파서=DONE),
    dict(자료="하수도통계", 절=["2.7.1 공공하수처리시설", "2.7.2 분뇨처리시설"],
         기관="기후에너지환경부 / 하수도정보시스템", 주기="연 1회",
         목록="https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/list.do",
         상세="POST /bbs/lay1/WS10000015/{id}/view.do  (bbsId=BBS_000007 필수)",
         받기="GET /bbs/fileDownload.do?atcmtFileId=..&fileSn=..",
         취득="확인", 파서=DONE),
    dict(자료="전국 폐기물 발생 및 처리현황", 절=["2.7.4 매립처리시설", "2.7.5 소각시설"],
         기관="기후에너지환경부·한국환경공단 / 자원순환정보시스템", 주기="연 1회(12월 공표)",
         목록="https://www.recycling-info.or.kr/rrs/stat/envStatList.do?bbsId=BBSMSTR_000000000002&s_nttSj=KEC006",
         상세="https://www.recycling-info.or.kr/rrs/stat/envStatDetail.do?nttId={id}",
         받기="POST /cmm/fms/FileDownload.do  (atchFileId·fileSn)",
         취득="확인", 파서=TODO, 비고="2024판 결과표 zip 확보 (엑셀 9개)"),
    dict(자료="음식물류 폐기물 처리시설 현황", 절=["2.7.3 음식물류"],
         기관="기후에너지환경부", 주기="연 1회",
         목록=None, 취득=None, 파서=TODO,
         비고="NAS jdw 폴더에 2022·2023판 엑셀. 발행처 경로 미확인"),
    dict(자료="산업입지정보시스템", 절=["2.5.3 산업 및 농공단지"],
         기관="한국산업단지공단", 주기="수시",
         목록="https://www.industryland.or.kr", 취득=None, 파서=TODO),
    dict(자료="한국하천일람", 절=["2.8.3 수계"],
         기관="환경부 / 국가하천정보", 주기="연 1회",
         목록=None, 취득=None, 파서=TODO,
         비고="NAS jdw 에 2022판 엑셀(권역별·시도별). `engine/hydro.py` 는 하천망 공간자료를 따로 쓴다"),

    # ── 2.3.2 수환경 ────────────────────────────────────────────────────
    dict(자료="상수원보호구역 지정현황", 절=["2.3.2 수환경"],
         기관="환경부", 주기="수시", 목록=None, 취득=None, 파서=TODO,
         비고="채색은 VWorld `LT_C_UM710` 로 해결됨. **표는 아직**"),
    dict(자료="수변구역 지정현황", 절=["2.3.2 수환경"],
         기관="환경부(유역청)", 주기="수시", 목록=None, 취득=None, 파서=TODO),
    dict(자료="폐수배출시설 설치제한지역", 절=["2.3.2 수환경"],
         기관="환경부", 주기="수시", 목록=None, 취득=None, 파서=TODO),
    dict(자료="배출허용기준 지역지정", 절=["2.3.2 수환경"],
         기관="환경부고시 제2007-107호", 주기="고시(사실상 고정)",
         목록=None, 취득="법령", 파서=TODO, 비고="법령 별표 — 개정일만 관리"),

    # ── 2.3.3 자연생태환경 ──────────────────────────────────────────────
    dict(자료="야생생물 보호구역 지정현황", 절=["2.3.3 자연생태환경"],
         기관="환경부", 주기="연 1회", 목록=None, 취득=None, 파서=TODO),
    dict(자료="습지보호지역·람사르", 절=["2.3.3 자연생태환경"],
         기관="환경부", 주기="수시", 목록=None, 취득=None, 파서=TODO),
    dict(자료="자연공원(국립·도립·군립)", 절=["2.3.3 자연생태환경"],
         기관="환경부·국립공원공단", 주기="연 1회", 목록=None, 취득=None, 파서=TODO,
         비고="NAS jdw 에 2022 도립·군립 / 2024 국립 기본통계 **PDF**"),
    dict(자료="백두대간보호지역", 절=["2.3.3 자연생태환경"],
         기관="산림청", 주기="수시", 목록=None, 취득=None, 파서=TODO,
         비고="NAS jdw `0. 산줄기/` 에 **shp** — 공간자료다"),
    dict(자료="산림유전자원보호구역", 절=["2.3.3 자연생태환경"],
         기관="산림청", 주기="연 1회", 목록=None, 취득=None, 파서=TODO,
         비고="NAS jdw 에 2015·2024 엑셀"),
    dict(자료="겨울철 조류 동시 센서스", 절=["2.3.3 자연생태환경"],
         기관="국립생물자원관", 주기="연 1회", 목록=None, 취득=None, 파서=TODO,
         비고="NAS jdw 에 2022·2023 **PDF** + 센서스지도"),
    dict(자료="생태·경관보전지역", 절=["2.3.3 자연생태환경"],
         기관="해양수산부(공공데이터포털 WFS)", 주기="수시",
         목록="https://www.data.go.kr", 취득="API", 파서=DONE,
         비고="`engine/ecgy.py` — 판정 8/8 · 평창 이격거리 1.04km 일치"),

    # ── 공간 자료 ───────────────────────────────────────────────────────
    dict(자료="생태·자연도", 절=["2.8.1 생태·자연도"],
         기관="국립생태원 EcoBank", 주기="수시", 목록=None, 취득="API", 파서=DONE,
         비고="`engine/ecology.py` — 등급 판정 골든셋 8/8"),

    # ── 지자체별 ────────────────────────────────────────────────────────
    dict(자료="지자체 통계연보", 절=["2.1.1 지리적 특성", "2.2.1 지목별 토지이용",
                                    "2.2.2 용도지역", "2.5.1 도로",
                                    "2.5.2 환경오염물질 배출시설", "2.5.4 자동차",
                                    "2.6.3 문화재"],
         기관="각 지자체", 주기="연 1회 (지자체마다 다름)",
         목록=None, 취득=None, 파서=PART,
         비고="`engine/stats_extract.py` 가 **6절** 처리 (2.1.1 미착수). "
              "⚠️ 배포 형식이 제각각 — 엑셀 4 / zip 43 / **스캔 PDF 34** (확인요청 F-4)"),
]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--todo", action="store_true")
    a = ap.parse_args()
    return todo() if a.todo else status()


if __name__ == "__main__":
    sys.exit(main() or 0)

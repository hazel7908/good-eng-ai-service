#!/usr/bin/env python3
"""
지역개황 vars 빌더 — 사업 인풋 + 통계 → `cases/{사업}/vars/regional-overview.json`.

**생성(`generate.py`)은 통계를 모른다.** 엔진은 vars 만 읽으므로, 표는 여기서
값으로 확정돼 있어야 한다. `calc.py`(소음진동)·`calc_air.py`(대기질)와 같은 자리다.

    python engine/build_vars_regional.py 원주_무장리
    python engine/build_vars_regional.py 원주_무장리 --dry-run

## 판을 여기서 **고정한다** ★

한 보고서 안에서 판이 섞이면 출처 주석이 거짓말이 된다 — 골든셋에서 실제로 네 건
나왔다 (천안은 출처 `2023` 인데 값은 2021판, 게다가 다른 열). 그래서

  · 최초 생성 때 **보유 최신으로 고정**하고 판·지문을 vars 에 박는다
  · 재생성은 vars 의 판을 그대로 쓴다 — 다시 고르지 않는다
  · 갱신은 `--refresh` 를 줄 때만

⚠️ **통계 확인 때문에 생성이 멈추면 안 된다.** 자료가 없으면 `[확인 필요]` 로 두고 넘어간다.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import stats_extract as YB                                 # noqa: E402
import stats_irregular as IRR                              # noqa: E402
import stats_pdf as PDF                                    # noqa: E402
from stats_national import SOURCES, gun_key               # noqa: E402

CHECK = "[확인 필요]"
VALUES = ROOT / "catalog/data/stats_values"
MANIFEST = ROOT / "catalog/data/stats_values.manifest.json"
NAT = ROOT / "raw_data/nas/stats/_national"

# 절 → 어떤 경로로 오는가. `stats_values` 는 이미 뜬 값이라 **오프라인**이다.
FROM_VALUES = list(SOURCES)          # 전국 통계 — 값 저장소 조회
FROM_IRREGULAR = {
    "2.3.2 수변구역": ("수변구역", r"수변구역.*hwpx$"),
    "2.3.3 생태·경관보전지역": ("생태경관보전지역", r"생태경관보전지역.*hwpx$"),
    "2.3.3 야생생물 보호구역": ("야생생물보호구역", r"야생생물보호구역.*xlsx$"),
    "2.8.3 하천일람": ("하천일람", r"한국하천일람.*시도별.*xlsx$"),
}
FROM_PDF = {
    "2.3.3 자연공원": ("자연공원", r"국립공원기본통계\.pdf$"),
    "2.3.3 습지보호지역": ("습지보호지역", r"습지보호지역.*pdf$"),
    "2.3.3 백두대간": ("백두대간", r"산림청고시.*백두대간.*pdf$"),
}


def latest(pattern):
    """`raw_data` 에서 정규식에 맞는 **가장 새 판**을 고른다. 없으면 None."""
    cands = [p for p in NAT.rglob("*") if re.search(pattern, p.name)]
    if not cands:
        return None

    def key(p):
        m = re.search(r"(20\d\d)", p.name)
        return int(m.group(1)) if m else 0
    return max(cands, key=key)


def load_values():
    """값 저장소를 통째로 읽는다 — {(자료, 판): 문서}."""
    out = {}
    for f in sorted(VALUES.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[(d["자료"], d["판"])] = d
    return out


def pick_edition(store, 자료):
    """그 자료의 **가장 새 판**을 고른다."""
    yrs = [y for (s, y) in store if s == 자료]
    return max(yrs) if yrs else None


def 사업정보(case_dir):
    """사업개요에서 시군·면·리·사업명·면적을 읽는다. 못 읽으면 `[확인 필요]`."""
    txt = (case_dir / "input/사업개요.txt").read_text(encoding="utf-8", errors="replace")
    info = {k: CHECK for k in ("사업명", "시군", "구", "하위행정구역", "리", "지구_면적")}
    # ⚠️ **자치구가 끼는 사업이 있다** — `천안시 동남구 동면 화덕리`.
    #    rule §4-2 의 "면 ↔ 구 (7:1)" 변이다. 구를 선택항으로 두지 않으면 못 읽는다.
    m = re.search(r"([가-힣]+[시군])\s+(?:([가-힣]+구)\s+)?([가-힣]+[읍면동])\s+([가-힣]+리)"
                  r"\s*(\d[\d\-]*)?번지?\s*일원\s*(.+?조성사업)", txt)
    if m:
        info.update({"시군": m.group(1), "구": m.group(2) or "",
                     "하위행정구역": m.group(3), "리": m.group(4),
                     "사업명": m.group(0).strip()})
    if (a := re.search(r"사업계획지구의?\s*면적은\s*([\d,]+)\s*㎡", txt)):
        info["지구_면적"] = a.group(1)
    return info


def build(case, refresh=False):
    case_dir = ROOT / "cases/small-env" / case
    if not (case_dir / "input/사업개요.txt").exists():
        sys.exit(f"ERROR: {case_dir}/input/사업개요.txt 없음")

    info = 사업정보(case_dir)
    시군 = info["시군"]
    if 시군 == CHECK:
        sys.exit("ERROR: 사업개요에서 시군을 못 읽었다 — 수동으로 vars 를 채울 것")

    store = load_values()
    man = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"판": []}
    지문 = {(e["자료"], e["판"]): e["원자료"]["sha256"][:12] for e in man["판"]}

    out = {
        "_meta": {
            "카테고리": "small-env", "파트": "regional-overview", "사업": case,
            "작성일": date.today().isoformat(),
            "출처": f"cases/small-env/{case}/input/ + 전국 통계 값 저장소. golden/ 미참조",
            "규칙": ".claude/rules/small-env/regional-overview.md",
            "주의": [
                "골든셋에서 값을 베끼지 않는다. 베끼면 검증이 부정이 된다.",
                "판(`_통계판`)은 **여기서 고정**된다 — 재생성해도 같은 값이 나온다.",
                "새 판으로 갈아타려면 `--refresh` 를 명시할 것.",
            ],
        },
        "사업": info,
        "_통계판": {},
        "통계": {},
        "_확인필요": [],
    }

    def 확인필요(항목, 분류, 사유):
        out["_확인필요"].append({"항목": 항목, "분류": 분류, "사유": 사유})

    # ── 전국 통계 (값 저장소 — 오프라인) ────────────────────────────────
    for sec in FROM_VALUES:
        자료 = SOURCES[sec]["자료"]
        yr = pick_edition(store, 자료)
        if yr is None:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "자료부재", f"{자료} 값 저장소에 없음 — build_stats_values 실행")
            continue
        blk = store[(자료, yr)]["절"].get(sec, {})
        rows = blk.get("값", {}).get(gun_key(시군), [])
        out["통계"][sec] = rows
        out["_통계판"][자료] = {"판": yr, "지문": 지문.get((자료, yr), CHECK)}
        if not rows:
            확인필요(f"통계.{sec}", "판단",
                     f"{시군} 해당 행 0 — 실제로 없는지(0개소) 표기 차이인지 확인")

    # ── 모양이 다른 것 (엑셀·한글) ──────────────────────────────────────
    for sec, (fn, pat) in FROM_IRREGULAR.items():
        p = latest(pat)
        if not p:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "자료부재", f"원자료 없음 (/{pat}/)")
            continue
        key = "섬강" if fn == "하천일람" else 시군      # 하천은 시군이 아니라 하천명이다
        try:
            out["통계"][sec] = getattr(IRR, fn)(str(p), key)
        except Exception as e:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "판단", f"읽기 실패: {e}")
        out["_통계판"][sec] = {"파일": p.name}
        if fn == "하천일람":
            확인필요(f"통계.{sec}", "X",
                     "유하 하천명은 인풋(본문 수계 서술)에서 온다 — 지금은 기본값")

    # ── PDF ────────────────────────────────────────────────────────────
    for sec, (fn, pat) in FROM_PDF.items():
        p = latest(pat)
        if not p:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "자료부재", f"원자료 없음 (/{pat}/)")
            continue
        try:
            r = getattr(PDF, fn)(str(p), 시군)
        except Exception as e:
            r, _ = CHECK, 확인필요(f"통계.{sec}", "판단", f"읽기 실패: {e}")
        out["통계"][sec] = r if r else []      # 빈 목록 = 지정현황 없음 (정상)
        out["_통계판"][sec] = {"파일": p.name}
        if isinstance(r, dict) and r.get("합계검산") == CHECK:
            확인필요(f"통계.{sec}", "판단", "시도 합계 검산 실패 — 표를 눈으로 확인할 것")

    # ── 통계연보 (지자체별 — 사업마다 원자료가 필요하다) ────────────────
    YB_SECS = ("2.2.1 지목별 토지이용", "2.2.2 용도지역", "2.5.1 도로",
               "2.5.2 환경오염물질 배출시설", "2.5.4 자동차", "2.6.3 문화재")
    yb = sorted((ROOT / "raw_data/nas/stats" / case).glob("*통계연보*")) or \
         sorted((ROOT / "raw_data/nas/stats" / case).glob("*.zip"))
    if not yb:
        for sec in YB_SECS:
            out["통계"][sec] = CHECK
        확인필요("통계.통계연보 6절", "자료부재",
                 f"{시군} 통계연보 원자료가 raw_data/nas/stats/{case}/ 에 없다 (확인요청 F-4)")
    elif yb[0].suffix.lower() == ".pdf":
        for sec in YB_SECS:
            out["통계"][sec] = CHECK
        확인필요("통계.통계연보 6절", "자료부재",
                 f"통계연보가 **스캔 PDF** ({yb[0].name}) — 값을 못 꺼낸다 (확인요청 F-4)")
    else:
        out["_통계판"]["지자체 통계연보"] = {"파일": yb[0].name}
        면 = info["하위행정구역"] if info["하위행정구역"] != CHECK else None
        try:
            book = YB.YearBook(str(yb[0]))
        except Exception as e:
            book = None
            for sec in YB_SECS:
                out["통계"][sec] = CHECK
            확인필요("통계.통계연보 6절", "판단", f"통계연보 열기 실패: {e}")
        if book:
            # ⚠️ **어느 연도 행을 쓸지는 회사 표준이 없다** (확인요청 F-1).
            #    지금 기본값은 "최신 행" — 정답지는 절마다 다른 행을 쓰고 있었다.
            calls = {
                "2.2.1 지목별 토지이용": lambda: {
                    "시군": YB.land_use(book), "면": YB.land_use(book, region=면) if 면 else CHECK},
                "2.2.2 용도지역": lambda: YB.zoning(book),
                "2.5.1 도로": lambda: YB.roads(book),
                "2.5.2 환경오염물질 배출시설": lambda: YB.emitters(book),
                "2.5.4 자동차": lambda: YB.vehicles(book),
                # ⚠️ 표에 **시군 전체와 면이 함께** 들어간다 (지목별과 같은 구성).
                #    면만 내면 "천안시 국가지정 14개소" 문장을 못 만든다
                "2.6.3 문화재": lambda: {
                    "시군": YB.heritage(book),
                    "면": YB.heritage(book, region=면) if 면 else CHECK},
            }
            for sec, fn in calls.items():
                try:
                    out["통계"][sec] = fn()
                except Exception as e:
                    out["통계"][sec] = CHECK
                    확인필요(f"통계.{sec}", "판단", f"통계연보에서 못 읽음: {e}")
            확인필요("통계.통계연보 6절", "판단",
                     "연도 행은 **최신 행**을 기본값으로 썼다 — 회사 표준 확인 필요 (F-1)")

    # ── 좌표에서 나오는 값 둘 ──────────────────────────────────────────
    #    ⚠️ **여기서 실패해도 생성을 막지 않는다.** 네트워크·키·조서 서식 어느 것이
    #       어긋나도 `[확인 필요]` 로 떨어뜨리고 넘어간다 (`common.md` 환각 금지).
    out["공간"] = {"도엽번호": CHECK, "생태자연도_등급": CHECK}
    # ⚠️ **지번까지 넣어야 한다.** 리까지만 주면 VWorld 가 `무장리 1` (리 대표점)로
    #    매칭해 **사업지와 다른 곳**을 짚는다 — 원주에서 생태자연도가 1등급으로 나왔다
    #    (정답 2,3등급). `지구_소재지` 는 사업명에서 뽑은 `…578번지` 다.
    m0 = re.search(r"^(.+?번지)\s*일원", str(info.get("사업명", "")))
    주소 = m0.group(1) if m0 else f'{info["시군"]} {info["하위행정구역"]} {info["리"]}'.strip()
    lon = lat = None
    try:
        import map_fetch
        x, y, matched = map_fetch.geocode(주소)      # EPSG:3857 + 매칭된 주소
        lon, lat = map_fetch.merc_to_lonlat(x, y)
        out["공간"]["지오코딩_주소"] = matched
        out["공간"]["좌표_3857"] = [x, y]
    except Exception as e:
        확인필요("공간.좌표", "판단", f"지오코딩 실패({주소}): {e}")

    if lon is not None:
        # ① 도엽번호 — **순수 계산이다.** 네트워크도 폴리곤도 필요 없다 (골든셋 8쌍 일치)
        try:
            import map_fetch
            out["공간"]["도엽번호"] = map_fetch.sheet25k(lon, lat)
        except Exception as e:
            확인필요("공간.도엽번호", "판단", f"계산 실패: {e}")

        # ② 생태·자연도 등급 — **`ecology._site_rings()` 를 그대로 쓴다.**
        #    조서 읽기·법정동코드·필지 경계·좌표변환·**임야 조각 탐침**까지 그 안에 있고,
        #    골든셋 8/8 을 낸 것이 바로 그 경로다. 손으로 재구현하면 조각 탐침이 빠져
        #    원주가 정답 `2,3등급` 대신 `3` 으로 나온다 (실제로 그랬다).
        try:
            import ecology
            site, probes = ecology._site_rings(case, lon, lat)
            r = ecology.assess(lon, lat, site_rings=site, site_probes=probes)
            grades = r.get("등급들") or []
            out["공간"]["생태자연도_등급"] = ", ".join(grades) if grades else CHECK
            out["공간"]["_생태자연도_상세"] = r
            if not site:
                확인필요("공간.생태자연도_등급", "판단",
                         "**중심점으로 판정**했다 — 편입토지조서를 못 읽었거나 필지 경계를 "
                         "못 받았다. 두 등급에 걸릴 때 나열이 빠질 수 있다 (rule §2.8.1)")
        except Exception as e:
            확인필요("공간.생태자연도_등급", "판단", f"EcoBank 판정 실패: {e}")


    # ── 자료가 아예 없는 자리 ──────────────────────────────────────────
    out["통계"]["2.1.1 지리적 좌표"] = CHECK
    확인필요("통계.2.1.1 지리적 좌표(극점)", "자료부재",
             "통계연보 **엑셀 편에 없다** — 책자 본문에만 (확인요청 G-6)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="판을 다시 고른다")
    a = ap.parse_args()

    v = build(a.case, refresh=a.refresh)
    filled = sum(1 for x in v["통계"].values()
                 if x not in (CHECK,) and x != [] and x is not None)
    print(f"# {a.case} — 통계 {filled}/{len(v['통계'])} 절 채움 · "
          f"확인필요 {len(v['_확인필요'])}건")
    print("\n## 고정된 판")
    for k, s in v["_통계판"].items():
        print(f"   {k}: {s}")
    print("\n## 확인 필요")
    for c in v["_확인필요"]:
        print(f"   [{c['분류']}] {c['항목']} — {c['사유']}")

    if a.dry_run:
        return 0
    out = ROOT / "cases/small-env" / a.case / "vars/regional-overview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {out.relative_to(ROOT)}  {out.stat().st_size/1024:.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

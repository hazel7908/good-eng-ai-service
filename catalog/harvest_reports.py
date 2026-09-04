#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NAS 파트별 보고서 txt 수확 — 본환·전략 골든셋 확보 (2026-09-03, 지시서 ⑭).

`golden/{카테고리}/{사업}/{슬러그}.txt` 를 만든다. 원본 hwp 는 `raw_data/nas/{카테고리}/`
에 두고 **커밋하지 않는다** (naming.md — 표지·간지·목차도 커밋 대상이 아니다).

⚠️ 슬러그는 소환 것을 그대로 쓰되(`docs/naming.md`), 본환·전략에만 있는 장은 새로 지었다.
   아래 표의 `NEW` 표시가 그것이다 — **Mac 확정 전까지 잠정**이다.

    python catalog/harvest_reports.py env-impact --limit 1     # 속도 측정
    python catalog/harvest_reports.py env-impact
    python catalog/harvest_reports.py strategic-env
"""
import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "catalog"))
from hwp_util import console_utf8                      # noqa: E402
from extract import extract                            # noqa: E402
from synology_filestation import connect               # noqa: E402

# ⚠️ `nas_index.json.gz` 의 경로는 **공유폴더 `/backupenv` 기준 상대 경로**다.
#    그대로 API 에 넣으면 code=408(없는 폴더)로 조용히 빈 목록이 온다 (09-03 실측).
SHARE = "/backupenv"

TARGETS = {
    "env-impact": {
        "사업": "횡성_벨라스톤CC",
        # ⚠️ **인덱스(08-31 크롤) 경로가 이미 낡았다.** `/0. 평가서/환경/환24-30 …` 은
        #    live NAS 에 없다 — 사업들이 **연도 폴더**(`환경/2024/`) 아래로 재편됐다.
        #    같은 이름의 빈 껍데기 폴더가 원래 자리에 남아 있어 `list` 가 조용히
        #    0건을 돌려준다 (code 408 도 아니다). 경로는 live 로 확인할 것 (09-03).
        "nas": ("/0. 평가서/환경/2024/환24-30 벨라스톤cc 9홀 증설사업 환경영향평가, "
                "재해영향평가, 지질조사(㈜진원)/2. 보고서/2. 본안"),
        # (파일명 조각, 슬러그) — 조각은 파일명에 그대로 들어 있는 부분
        "map": [
            ("0100 요약문", "summary"),                       # NEW
            ("0200 사업의 개요", "project-overview"),
            ("0300 환경영향평가 대상지역", "target-area"),
            ("0400 지역개황", "regional-overview"),
            ("0500 평가항목 범위", "scoping"),                 # NEW
            ("0600 주민의견", "public-opinion"),               # NEW
            ("0700 대안설정", "alternatives"),                 # NEW
            ("0800 환경보전목표", "conservation-goal"),        # NEW
            ("0911 동식물상", "flora-fauna"),
            ("0912 자연환경자산", "natural-assets"),           # NEW
            ("0921 기상", "climate"),
            ("0922 대기질", "air-quality"),
            ("0923 온실가스", "greenhouse-gas"),               # NEW
            ("0931 수질", "water-quality"),
            ("0941 토지이용", "land-use"),
            ("0942 토양", "soil"),                             # NEW
            ("0943 지형지질", "topo-geology"),
            ("0951 친환경적자원순환", "resource-cycle"),
            ("0952 소음진동", "noise-vib"),
            ("0953 위락경관", "landscape"),
            ("0961 인구주거", "population-housing"),           # NEW
            ("1000 전략환경영향평가 협의내용", "strategic-reflection"),   # NEW
            ("1100 환경에 미치는 영향의 저감방안", "mitigation-postmonitoring"),  # NEW
            ("1200 불가피한 환경영향", "unavoidable-impact"),  # NEW
            ("1300 주민의 생활환경", "resident-damage"),       # NEW
            ("1400 종합평가 및 결론", "conclusion"),
            ("1500 부록-1 부1-16.hwp", "appendix-1"),          # 블랙마킹본은 제외
            ("1500 부록-2", "appendix-2"),
            ("1500 부록-3", "appendix-3"),
            ("수질오염총량검토서", "water-total-load"),
        ],
    },
    "strategic-env": {
        "사업": "충북_수산천고명천",
        "nas": "/2021/1. 수산천 고명천 전략(충북도청 211130)/3. 보고서/03. 본안",
        "map": [
            ("01 요약문", "summary"),
            ("02 개발기본계획의 개요", "plan-overview"),       # NEW
            ("03 개발기본계획의 대안", "alternatives"),
            ("04 전략환경영향평가 대상지역", "target-area"),
            ("05 지역개황", "regional-overview"),
            ("06 환경영향평가협의회", "scoping"),
            ("07 주민 및 관계행정기관", "public-opinion"),
            ("08 계획의 적정성", "plan-adequacy"),             # NEW
            ("09.1.1 동식물상", "flora-fauna"),
            ("09.1.2 자연환경자산", "natural-assets"),
            ("09.1.3 지형 및 생태축", "topo-geology"),
            ("09.1.4 경관", "landscape"),
            ("09.1.5 수환경", "water-quality"),
            ("09.1.6 수환경", "hydrology"),                    # NEW
            ("09.2.1 환경기준 부합성(기상)", "climate"),
            ("09.2.2 환경기준 부합성(대기질)", "air-quality"),
            ("09.2.3 환경기준 부합성(소음진동)", "noise-vib"),
            ("09.2.4 자원에너지", "resource-cycle"),
            ("09.3 사회", "socioeconomic"),                    # NEW
            ("10 종합평가 및 결론", "conclusion"),
            ("11 부록 (완)1-100, 101-123, 124-129.hwp", "appendix"),   # 마킹본 제외
            ("지역개발 부하량", "load-allocation-deferral"),   # NEW
        ],
    },
}


def main():
    console_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("category", choices=sorted(TARGETS))
    ap.add_argument("--limit", type=int, default=0, help="앞에서 n건만 (속도 측정용)")
    ap.add_argument("--skip-existing", action="store_true", default=True)
    ap.add_argument("--reextract", action="store_true",
                    help="이미 받아 둔 원본으로 txt 만 다시 뽑는다 (추출기 개선 후 재추출)")
    args = ap.parse_args()

    t = TARGETS[args.category]
    raw = ROOT / "raw_data" / "nas" / args.category / t["사업"]
    out = ROOT / "golden" / args.category / t["사업"]
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    if args.reextract:
        # 🔬 추출기 v2 재추출 — NAS 접속 없이 로컬 원본만 쓴다 (㉒, 09-04).
        n = 0
        for frag, slug in t["map"]:
            hit = [f for f in raw.glob("*.hwp") if frag in f.name]
            if not hit:
                print(f"  ⚠️ 로컬 원본 없음: {frag} → {slug}")
                continue
            src = sorted(hit, key=lambda x: len(x.name))[0]
            txt = out / f"{slug}.txt"
            before = txt.read_text(encoding="utf-8") if txt.exists() else ""
            txt.write_text(extract(str(src)), encoding="utf-8")
            after = txt.read_text(encoding="utf-8")
            n += 1
            mark = "=" if before == after else "≠"
            print(f"  {mark} {slug:28} {before.count(chr(10)):>7,}줄 → {after.count(chr(10)):>7,}줄")
        print(f"재추출 {n}건 → {out}")
        return

    fs = connect()
    nas = SHARE + t["nas"]
    files = {f["name"]: f for f in fs.list_folder(nas)}
    print(f"NAS 파일 {len(files)}개 · 대상 {len(t['map'])}개")

    plan = []
    for frag, slug in t["map"]:
        hit = [n for n in files if frag in n and n.lower().endswith(".hwp")]
        if not hit:
            print(f"  ⚠️ 못 찾음: {frag!r} → {slug}")
            continue
        if len(hit) > 1:
            hit = sorted(hit, key=len)          # 짧은 쪽 = 마킹/수정 접미사 없는 원본
            print(f"  ℹ️ 후보 {len(hit)}개 → {hit[0]!r} 선택 ({slug})")
        info = files[hit[0]]
        size = info.get("size") or (info.get("additional") or {}).get("size") or 0
        plan.append((hit[0], slug, size))
    if args.limit:
        plan = sorted(plan, key=lambda x: x[2])[: args.limit]
    total = sum(s for _, _, s in plan)
    print(f"내려받을 {len(plan)}건 · {total / 1e9:.2f} GB\n")

    done = 0
    for name, slug, size in plan:
        txt = out / f"{slug}.txt"
        local = raw / name
        if args.skip_existing and txt.exists():
            print(f"  건너뜀(이미 있음) {slug}")
            continue
        t0 = time.time()
        if not local.exists() or (size and local.stat().st_size != size):
            fs.download(f"{nas}/{name}", str(raw))
        dl = time.time() - t0
        try:
            txt.write_text(extract(str(local)), encoding="utf-8")
            lines = txt.read_text(encoding="utf-8").count("\n")
        except Exception as e:                    # noqa: BLE001
            print(f"  ❌ 추출 실패 {slug}: {type(e).__name__}: {e}")
            continue
        done += 1
        print(f"  ✅ {slug:28} {size / 1e6:7.1f} MB  받기 {dl:5.1f}s  "
              f"추출 {time.time() - t0 - dl:5.1f}s  {lines:,}줄")
    print(f"\n수확 {done}건 → {out}")


if __name__ == "__main__":
    main()

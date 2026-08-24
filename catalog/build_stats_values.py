#!/usr/bin/env python3
"""
전국 통계 **값 저장소** 빌드 — 원자료에서 값을 떠서 우리 쪽에 남긴다.

**좌표만 갖고 있으면 안 되는 이유가 실측으로 나왔다.**
괴산 금신리 골든셋의 유입하수량 `5,822.3` 은 우리가 확보한 하수도통계 **2021·2022·2023
어느 판에도 없다.** 같은 "2023 하수도통계" 라도 배포본이 여럿이고 값이 다르기 때문이다.
원자료를 가리키기만 하면 **그 보고서가 어느 값을 썼는지 영영 되짚을 수 없다.**

그래서 판마다 **값 + 판 지문(sha256)** 을 남긴다.
`sheet_georef.json` 을 커밋하는 것과 같은 논리다 — **다시 만들 수 없는 값**이라서.

    python catalog/build_stats_values.py                  # 로컬 원자료 전부
    python catalog/build_stats_values.py --list           # 무엇이 있고 무엇이 없나
    python catalog/build_stats_values.py --show 괴산군     # 판을 가로질러 본다

출력이 **둘로 갈린다** — 기준은 *다시 만들 수 있는가* 다 (`CLAUDE.md` 삽도 대목과 같은 규약).

    catalog/data/stats_values.manifest.json   ← **커밋**. 판 지문·출처·좌표·행수
    catalog/data/stats_values/{자료}_{판}.json ← **커밋 안 함**. 값 본체 (NAS 로 공유)

값 본체는 원자료 + 이 코드로 **재생성된다.** 반면 *"그 보고서가 어느 판을 썼나"* 는
원자료가 교체되면 **영영 못 만든다** — 그래서 매니페스트만 남긴다.
자료가 12종으로 늘면 값 본체는 10~20MB 가 되고, 재빌드마다 통째로 바뀐다.
git 히스토리는 되돌릴 수 없으므로 **처음부터 나눈다.**
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
from stats_national import SOURCES, extract_all           # noqa: E402

RAW = ROOT / "raw_data/nas/stats/_national"
OUT = ROOT / "catalog/data/stats_values"
MANIFEST = ROOT / "catalog/data/stats_values.manifest.json"

# 발행처 — 새 판을 어디서 받는지. 목록 URL 은 규칙적이라 신판 감시에도 쓴다.
PUBLISHER = {
    "전국 폐기물 발생 및 처리현황": {
        "기관": "기후에너지환경부·한국환경공단 / 자원순환정보시스템",
        "목록": "https://www.recycling-info.or.kr/rrs/stat/envStatList.do"
                "?bbsId=BBSMSTR_000000000002&s_nttSj=KEC006",
        "상세": "https://www.recycling-info.or.kr/rrs/stat/envStatDetail.do?nttId={id}",
    },
    "전국산업단지현황통계": {
        "기관": "한국산업단지공단 (국가승인통계 399003호)",
        "목록": "https://www.data.go.kr/data/3041272/fileData.do",
        "받기": "POST /tcs/dss/selectFileDataDownload.do → "
                "GET /cmm/cmm/fileDownload.do?atchFileId=..&fileDetailSn=..",
    },
    "상수원보호구역 지정현황": {
        "기관": "기후에너지환경부",
        "목록": None,          # ❓ 발행처 경로 미확인 — NAS 창고 사본으로 쓴다
    },
    "음식물류 폐기물 처리시설 현황": {
        "기관": "기후에너지환경부",
        "목록": None,          # ❓ 발행처 경로 미확인 — NAS 창고 사본으로 쓴다
    },
    "상수도통계": {
        "기관": "환경부(기후에너지환경부) / 국가상수도정보시스템",
        "목록": "https://www.waternow.go.kr/web/board/STAT?pMENUID=9",
        "상세": "https://www.waternow.go.kr/web/board/STAT/{id}/?pMENUID=9",
    },
    "하수도통계": {
        "기관": "환경부(기후에너지환경부) / 하수도정보시스템",
        "목록": "https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/list.do",
        "상세": "https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/{id}/view.do",
    },
}


# 파일명 → 자료. 폐기물은 **결과표 zip 안의 특정 엑셀**이라 파일명이 길다.
NAME_TO_SRC = [
    (r"상수도통계", "상수도통계"),
    (r"하수도통계", "하수도통계"),
    (r"처리업체현황_Ⅰ", "전국 폐기물 발생 및 처리현황"),
    (r"음식물류", "음식물류 폐기물 처리시설 현황"),
    (r"상수원보호구역", "상수원보호구역 지정현황"),
    (r"산업단지현황조사", "전국산업단지현황통계"),
]


def edition_of(path):
    """파일명에서 (자료, 판) 을 읽는다. 판은 **기준연도**다 (공표연도가 아니다)."""
    name = path.name
    m = re.search(r"(20\d\d)", name)
    if not m:
        m2 = re.search(r"[\'\(](\d{2})[\.\-]\d{1,2}월", name)
        if not m2:
            return None
        m = m2
        m = type("M", (), {"group": lambda self, i: str(2000 + int(m2.group(1)))})()
    for pat, src in NAME_TO_SRC:
        if re.search(pat, name.replace(" ", "")):
            return src, int(m.group(1))
    return None


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while (b := f.read(chunk)):
            h.update(b)
    return h.hexdigest()


def build(path, src, year):
    secs = {s: spec for s, spec in SOURCES.items() if spec["자료"] == src}
    doc = {
        "자료": src,
        "판": year,
        "발행처": PUBLISHER.get(src, {}),
        "원자료": {
            "파일명": path.name,
            "크기": path.stat().st_size,
            # ⚠️ 판 지문 — 같은 연도라도 배포본이 갈린다. 이것이 판을 가르는 유일한 근거다
            "sha256": sha256(path),
        },
        "추출": {"일자": date.today().isoformat(), "도구": "engine/stats_national.py"},
        "절": {},
    }
    for sec in secs:
        try:
            values, sheet, missing = extract_all(path, sec)
        except KeyError as e:
            doc["절"][sec] = {"오류": str(e)}
            print(f"    ⚠️ {sec}: {e}")
            continue
        doc["절"][sec] = {
            "시트": sheet,
            "원자료에_없는_열": missing,
            "시군수": len(values),
            "행수": sum(len(v) for v in values.values()),
            "값": dict(sorted(values.items())),
        }
        print(f"    {sec}: 시군 {len(values)} · 행 {sum(len(v) for v in values.values())}"
              + (f"  ⚠️ 없는 열 {missing}" if missing else ""))
    return doc


def show(gun):
    """한 시군을 **판마다 나란히** 펼친다.

    값 저장소를 두는 이유가 여기 있다 — 원자료 8벌(90MB)을 열지 않고
    *"어느 판에서 값이 어떻게 바뀌었나"* 를 바로 본다.
    """
    docs = sorted((json.loads(f.read_text(encoding="utf-8")) for f in OUT.glob("*.json")),
                  key=lambda d: (d["자료"], d["판"]))
    if not docs:
        print("값 저장소가 비었다 — 먼저 인자 없이 실행할 것"); return 1
    for sec in SOURCES:
        lines = []
        for d in docs:
            blk = d["절"].get(sec)
            if not blk or "값" not in blk:
                continue
            for row in blk["값"].get(gun, []):
                vals = " | ".join(f"{v:,}" if isinstance(v, (int, float)) else str(v)
                                  for v in row.values())
                lines.append(f"  {d['판']}판  {vals}")
        if lines:
            print(f"\n## {sec} — {gun}")
            print("        " + " | ".join(SOURCES[sec]["열"]))
            print("\n".join(lines))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="원자료 보유 현황만 본다")
    ap.add_argument("--show", metavar="시군", help="한 시군을 판마다 나란히 본다")
    a = ap.parse_args()

    if a.show:
        return show(a.show)

    found = {}
    for p in sorted(list(RAW.glob("*.xlsx")) + list(RAW.glob("*/*.xlsx"))):
        ed = edition_of(p)
        if ed:
            found[ed] = p

    if a.list:
        print("## 로컬 원자료 (raw_data, 커밋 제외)")
        for (src, yr), p in sorted(found.items()):
            print(f"  {src} {yr}판  {p.name}  {p.stat().st_size/1e6:.1f}MB")
        print("\n## 값 저장소 (커밋 대상)")
        for f in sorted(OUT.glob("*.json")) if OUT.exists() else []:
            print(f"  {f.name}  {f.stat().st_size/1024:.0f}KB")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "설명": "전국 통계 값 저장소의 판 목록. 값 본체는 커밋하지 않는다 — "
                "`python catalog/build_stats_values.py` 로 재생성하거나 NAS 에서 받는다.",
        "갱신": date.today().isoformat(),
        "판": [],
    }
    for (src, yr), p in sorted(found.items()):
        print(f"\n== {src} {yr}판 — {p.name}")
        doc = build(p, src, yr)
        out = OUT / f"{src}_{yr}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"    → {out.relative_to(ROOT)}  {out.stat().st_size/1024:.0f}KB")
        manifest["판"].append({
            "자료": src, "판": yr,
            "발행처": doc["발행처"].get("목록"),
            "원자료": doc["원자료"],                       # 파일명·크기·sha256
            "값파일": {"이름": out.name,
                       "크기": out.stat().st_size,
                       "sha256": sha256(out)},            # NAS 사본이 같은지 대조용
            "절": {sec: {k: v for k, v in blk.items() if k != "값"}
                   for sec, blk in doc["절"].items()},
            "추출일": doc["추출"]["일자"],
        })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {MANIFEST.relative_to(ROOT)}  {MANIFEST.stat().st_size/1024:.0f}KB  (커밋 대상)")
    print(f"  값 본체 {len(manifest['판'])}개는 커밋하지 않는다 — NAS 로 공유")
    return 0


if __name__ == "__main__":
    sys.exit(main())

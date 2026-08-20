#!/usr/bin/env python3
"""
수계 서술(2.8.3) → 수계흐름모식도 입력.

지역개황 본문에는 물이 흘러가는 경로가 **문장으로** 적혀 있다.

    "사업계획지구와 인접한 구거를 따라 약 1.93km 유하하여 섬강(국가)에 합류되며,
     이후 남서쪽으로 약 32.61km를 유하하여 최종 수계 본류인 한강(국가)으로 유입된다.
     … 총 유하거리는 약 34.54km이다."

그림 2.8-3(수계흐름모식도)은 **이 문장을 그림으로 옮긴 것**이다. 그래서 새로 조사할 값이
없다 — 문장에서 뽑아 `figure_overlay.py` 의 `watercourse` 요소에 그대로 넣으면 된다.

검증: `python engine/watercourse.py --self-test`   (골든셋 8건)

⚠️ **문장이 사업마다 제법 다르다.** 구간 거리가 아예 안 적힌 구간이 있고(괴산 금신리),
   총 유하거리 문장이 없는 사업도 있다(괴산 후평리·평창). 그래서 **구간 합과 본문 총계를
   맞춰 보고, 어긋나면 경고를 단다** — 조용히 틀린 그림을 그리지 않기 위해서다.
"""
import argparse, glob, json, os, re, sys

RIVER = r'([가-힣]{1,5}(?:천|강|저수지|소류지|소하천)(?:\s*\([^)]{1,12}\))?)'
DIST = r'약?\s*([\d.]+)\s*(km|m)'
# `유하하여` 뒤에 붙는 수식어는 사업마다 순서가 다르다 —
#   "최종 수계 본류인 한강" · "최종 합류 수계인 금강" · 그냥 "섬강"
MID = r'[^.]{0,10}?유하하여\s*(?:(?:최종|수계|본류인|합류|수계인)\s*){0,4}'
TOTAL = r'총\s*유하거리는?\s*약?\s*([\d.]+)\s*km'


def _km(value, unit):
    return float(value) / 1000 if unit == "m" else float(value)


def parse(text, site_label="사업계획지구"):
    """수계 서술에서 모식도 입력을 뽑는다 → figure_overlay 의 `watercourse` 요소."""
    i = text.find("2.8.3 수")
    seg = text[i:].split("하천일람")[0] if i >= 0 else text   # 서술 문단만 (표 앞까지)

    pairs = re.findall(DIST + MID + RIVER, seg)
    m = re.search(TOTAL, seg)
    total_txt = m.group(1) if m else None

    nodes = [site_label] + [r.strip() for _, _, r in pairs]
    links = [f"{d}{u}" for d, u, _ in pairs]
    sum_km = round(sum(_km(d, u) for d, u, _ in pairs), 2)

    warn = []
    if not pairs:
        warn.append("구간을 하나도 찾지 못했습니다 — 문장 형태가 다릅니다")
    if total_txt is None:
        warn.append("본문에 총 유하거리 문장이 없습니다 — 구간 합으로 대신했습니다")
    elif abs(float(total_txt) - sum_km) > 0.5:
        warn.append(f"구간 합({sum_km}km)과 본문 총계({total_txt}km)가 어긋납니다 — "
                    "거리가 적히지 않은 구간이 있을 수 있습니다")

    total = float(total_txt) if total_txt else sum_km
    return {
        "type": "watercourse",
        "nodes": nodes,
        "links": links,
        "total": f"총 유하거리 {total:g}km",
        "_sum_km": sum_km,
        "_total_in_text": float(total_txt) if total_txt else None,
        "_warn": warn,
    }


# ── 자체 검증 — 골든셋 8건 ──────────────────────────────────────────────────
def self_test(root="golden/small-env"):
    files = sorted(glob.glob(f"{root}/*/regional-overview.txt"))
    if not files:
        print(f"[skip] 골든셋이 없습니다: {root}")
        return True
    clean = 0
    for f in files:
        name = os.path.basename(os.path.dirname(f))
        r = parse(open(f, encoding="utf-8").read())
        flag = "OK  " if not r["_warn"] else "WARN"
        if not r["_warn"]:
            clean += 1
        print(f"  [{flag}] {name:<12} 구간 {len(r['links'])}개 · 합 {r['_sum_km']}km"
              f" · 본문 {r['_total_in_text'] or '없음'}")
        print(f"          {' → '.join(r['nodes'])}")
        for w in r["_warn"]:
            print(f"          ⚠ {w}")
    print(f"\n경고 없이 통과 {clean}/{len(files)} — 나머지는 경고를 달아 넘긴다")
    return True


def main():
    ap = argparse.ArgumentParser(description="수계 서술 → 수계흐름모식도 입력")
    ap.add_argument("file", nargs="?", help="지역개황 텍스트 파일")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("-o", "--out", help="spec JSON 으로 저장")
    a = ap.parse_args()

    if a.self_test or not a.file:
        sys.exit(0 if self_test() else 1)

    r = parse(open(a.file, encoding="utf-8").read())
    for w in r["_warn"]:
        print(f"⚠ {w}", file=sys.stderr)
    if a.out:
        # canvas 는 넣지 않는다 — figure_overlay 가 노드 수에 맞춰 잡는다
        spec = {"elements": [{k: v for k, v in r.items() if not k.startswith("_")}]}
        json.dump(spec, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"→ {a.out}")
    else:
        print(json.dumps({k: v for k, v in r.items() if not k.startswith("_")},
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

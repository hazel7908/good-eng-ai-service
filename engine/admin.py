#!/usr/bin/env python3
"""
행정구역명 라벨 — 지역개황도·수계도에 얹는 큰 글자.

정답 지역개황도의 `평 창 군` · `미 탄 면` 같은 큰 글자는 **지도에 있던 게 아니다.**
실무자가 낱자를 하나씩 박스에 담아 얹은 것이다. 그래서 우리도 얹어야 한다.

경계는 VWorld 에서 온다 — 시도 `LT_C_ADSIDO_INFO` · 시군구 `LT_C_ADSIGG_INFO` ·
읍면동 `LT_C_ADEMD_INFO` · 리 `LT_C_ADRI_INFO`.

    python engine/admin.py --lonlat 128.5697 37.3095 --half-m 8900 \\
        --center-px 2215 2217 --px-per-m 0.245 --canvas 4352 4352 -o labels.json

⚠️ **라벨 자리는 구역 중심이 아니다.** 광역 삽도에서는 구역 대부분이 화면 밖이라
   중심을 쓰면 라벨이 화면 밖으로 나간다. **화면 안에 들어온 부분의 중심**에 놓는다.
"""
import argparse, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parcels as P                                    # _get · _key 재사용

LEVELS = {
    "시도":   ("LT_C_ADSIDO_INFO", "ctp_kor_nm"),
    "시군구": ("LT_C_ADSIGG_INFO", "sig_kor_nm"),
    "읍면동": ("LT_C_ADEMD_INFO", "emd_kor_nm"),
    "리":     ("LT_C_ADRI_INFO", "li_kor_nm"),
}


def fetch(level, lon, lat, half_deg):
    data, key = LEVELS[level]
    box = f"BOX({lon-half_deg},{lat-half_deg},{lon+half_deg},{lat+half_deg})"
    fs, err = P._get(data=data, geomFilter=box, geometry="true", size="100")
    if err:
        return [], err
    out = []
    for f in fs:
        p = f["properties"]
        nm = p.get(key) or next((v for k, v in p.items()
                                 if isinstance(v, str) and k.endswith("kor_nm")), "")
        if nm:
            out.append({"name": nm, "rings": P._rings(f["geometry"])})
    return out, None


def _visible_center(pts, w, h, margin=0.06):
    """화면 안에 들어온 점들의 중심. 가장자리 여백 안쪽으로 당긴다."""
    mx, my = w * margin, h * margin
    inside = [(x, y) for x, y in pts if -mx <= x <= w + mx and -my <= y <= h + my]
    if not inside:
        return None
    cx = sum(x for x, _ in inside) / len(inside)
    cy = sum(y for _, y in inside) / len(inside)
    return [min(max(cx, mx * 2), w - mx * 2), min(max(cy, my * 2), h - my * 2)]


def _push_out(at, center, r):
    """사업지 둘레를 비운다 — 라벨이 표적을 덮으면 삽도가 못 쓰게 된다."""
    dx, dy = at[0] - center[0], at[1] - center[1]
    dist = math.hypot(dx, dy)
    if dist >= r:
        return at
    if dist < 1:
        return [center[0], center[1] + r]
    return [center[0] + dx / dist * r, center[1] + dy / dist * r]


def to_elements(regions, origin_lonlat, center_px, px_per_m, canvas, size=None,
                protect_px=0):
    """행정구역 → figure_overlay 의 `admin` 요소. 화면 밖 구역은 버린다."""
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    cx_m, cy_m = tr.transform(*origin_lonlat)
    ox, oy = center_px
    k = px_per_m / math.cos(math.radians(origin_lonlat[1]))
    w, h = canvas

    els, seen = [], set()
    for r in regions:
        if r["name"] in seen:
            continue
        pts = []
        for ring in r["rings"]:
            for lon, lat in ring:
                x, y = tr.transform(lon, lat)
                pts.append((ox + (x - cx_m) * k, oy - (y - cy_m) * k))
        at = _visible_center(pts, w, h)
        if at is None:
            continue
        if protect_px:
            at = _visible_center([_push_out(at, center_px, protect_px)], w, h) or at
        seen.add(r["name"])
        el = {"type": "admin", "at": [round(at[0], 1), round(at[1], 1)],
              "text": r["name"]}
        if size:
            el["size"] = size
        els.append(el)
    return els


def _avoid(els, gap=170):
    """라벨끼리 너무 붙으면 뒤엣것을 버린다 — 광역 삽도는 구역이 촘촘하다."""
    out = []
    for e in els:
        if all(math.dist(e["at"], o["at"]) > gap for o in out):
            out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser(description="행정구역명 라벨")
    ap.add_argument("--lonlat", nargs=2, type=float, required=True)
    ap.add_argument("--half-m", type=float, default=9000)
    ap.add_argument("--levels", nargs="*", default=["시군구", "읍면동"])
    ap.add_argument("--center-px", nargs=2, type=float, required=True)
    ap.add_argument("--px-per-m", type=float, required=True)
    ap.add_argument("--canvas", nargs=2, type=int, required=True)
    ap.add_argument("--size", type=int, help="글자 크기(px)")
    ap.add_argument("--gap", type=int, default=170, help="라벨 최소 간격(px)")
    ap.add_argument("--protect", type=int, default=0,
                    help="사업지 둘레 이 반경(px) 안에는 라벨을 두지 않는다")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()

    lon, lat = a.lonlat
    half_deg = a.half_m / 88000.0                      # 대략 — bbox 는 넉넉하면 된다
    els = []
    for lv in a.levels:
        regs, err = fetch(lv, lon, lat, half_deg)
        if err:
            print(f"  [warn] {lv} — {err}", file=sys.stderr)
            continue
        got = to_elements(regs, (lon, lat), a.center_px, a.px_per_m, a.canvas, a.size,
                          a.protect)
        print(f"  {lv:<6} {len(regs):>3}건 → 화면 안 {len(got)}개")
        els += got
    els = _avoid(els, a.gap)
    print(f"  겹침 정리 후 {len(els)}개")
    if a.out:
        json.dump({"elements": els}, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"→ {a.out}")


if __name__ == "__main__":
    main()

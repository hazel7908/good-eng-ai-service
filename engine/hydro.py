#!/usr/bin/env python3
"""
하천망 → 수계도의 흐름선.

수계도(그림 2.8-2)는 사업지 주변 하천을 그리고 흐름 방향에 화살표를 단다.
그 하천 경로가 국가 자료에 있다 — VWorld `LT_C_WKMSTRM` (하천망)이다.
`riv_nm`(하천명)·`cat_nam`(지방2급하천 같은 등급)까지 함께 온다.

**본문 수계 서술에 나온 하천만 골라 그린다.** 주변 하천을 다 그리면 정답보다 복잡해진다 —
`watercourse.py` 가 본문에서 뽑아 주는 하천명이 그대로 필터가 된다.

    python engine/watercourse.py 지역개황.txt        # 하천명이 나온다
    python engine/hydro.py --lonlat 127.63 36.76 --names 문방천 달천 \\
        --center-px 850 800 --px-per-m 0.49 -o flow.json

⚠️ **아직 실전에 못 쓴다.** 하천망이 선이 아니라 **면**(하천 구역)으로 온다.
   면에서 물길을 뽑으려고 중심선을 근사했지만, 저수지처럼 폭이 넓어지는 구간에서 깨진다
   (천안 용두천 실측 — 화살표가 물길이 아니라 저수지 가장자리에 붙었다).
   **선형 하천 자료를 찾는 것이 먼저다.** 하천 구역을 면으로 칠하는 데는 그대로 쓸 수 있다.

⚠️ 흐름 **방향**은 자료의 점 순서를 따른다. 상류→하류가 보장되지 않으므로 본문의 유하
   순서와 어긋나면 `--reverse` 로 뒤집는다.
"""
import argparse, json, sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import parcels as P                                     # _get · _key · DOMAIN 재사용

STREAM = "LT_C_WKMSTRM"


def fetch_streams(lon, lat, half_deg=0.04, names=None):
    """사업지 주변 하천망. `names` 를 주면 그 하천만 남긴다."""
    box = f"BOX({lon-half_deg},{lat-half_deg},{lon+half_deg},{lat+half_deg})"
    fs, err = P._get(data=STREAM, geomFilter=box, geometry="true", size="1000")
    if err:
        return [], err
    out = []
    for f in fs:
        nm = f["properties"].get("riv_nm", "")
        if names and not any(n in nm or nm in n for n in names):
            continue
        for line in _lines(f["geometry"]):
            out.append({"name": nm, "grade": f["properties"].get("cat_nam", ""),
                        "path": line})
    return out, None


def _lines(geom):
    if geom["type"] == "LineString":
        return [geom["coordinates"]]
    if geom["type"] == "MultiLineString":
        return geom["coordinates"]
    if geom["type"] in ("Polygon", "MultiPolygon"):
        # ⚠️ 하천망은 **선이 아니라 면**으로 온다 — 하천 구역이다.
        #    그대로 쓰면 화살표가 물길이 아니라 물가를 따라 한 바퀴 돈다.
        return [_centerline(r) for r in P._rings(geom)]
    return []


def _far_point(ring, i):
    """`i` 번 점에서 가장 먼 점의 인덱스."""
    import math
    return max(range(len(ring)),
               key=lambda j: math.dist(ring[i], ring[j]))


def _centerline(ring):
    """길쭉한 면(하천 구역)의 **중심선 근사**.

    하천 구역은 물길을 감싼 가늘고 긴 고리다. 고리에서 가장 멀리 떨어진 두 점이
    상류 끝과 하류 끝이므로, 거기서 고리를 둘로 끊으면 좌안과 우안이 된다.
    두 기슭의 대응점을 짝지어 중점을 이으면 물길이 나온다.

    ⚠️ 근사다. 지류가 갈라지거나 저수지처럼 폭이 넓으면 실제 물길과 어긋난다."""
    if len(ring) < 6:
        return ring
    a = _far_point(ring, 0)
    b = _far_point(ring, a)
    i, j = (a, b) if a < b else (b, a)
    left, right = ring[i:j + 1], ring[j:] + ring[:i + 1]
    right = right[::-1]                       # 같은 방향으로 훑도록 뒤집는다
    if len(left) < 2 or len(right) < 2:
        return ring
    n = max(len(left), len(right), 2)
    out = []
    for t in range(n):
        p = left[min(len(left) - 1, round(t * (len(left) - 1) / (n - 1)))]
        q = right[min(len(right) - 1, round(t * (len(right) - 1) / (n - 1)))]
        out.append([(p[0] + q[0]) / 2, (p[1] + q[1]) / 2])
    return out


def _simplify(path, keep=40):
    """점을 솎는다 — 화살표 간격 계산이 점 수에 휘둘리지 않게."""
    if len(path) <= keep:
        return path
    step = len(path) / keep
    out = [path[int(i * step)] for i in range(keep)]
    return out + [path[-1]]


def _clip(pts, w, h, pad=40):
    """화면 밖 구간을 잘라 **화면 안 토막들**로 나눈다.

    하천은 수십 km 짜리다. 통째로 두면 화면 안 구간이 몇 점 남지 않아 화살표가
    엉뚱한 데 찍히거나 아예 사라진다."""
    segs, cur = [], []
    for p in pts:
        if -pad <= p[0] <= w + pad and -pad <= p[1] <= h + pad:
            cur.append(p)
        elif cur:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return [s for s in segs if len(s) >= 2]


def to_elements(streams, origin_lonlat, center_px, px_per_m, label=True, reverse=False,
                canvas=None):
    """하천 경로 → figure_overlay 의 `flow` + 하천명 `place`."""
    import math
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    cx, cy = tr.transform(*origin_lonlat)
    ox, oy = center_px
    k = px_per_m / math.cos(math.radians(origin_lonlat[1]))

    els, seen = [], set()
    for s in streams:
        pts = []
        for lon, lat in s["path"]:
            x, y = tr.transform(lon, lat)
            pts.append([round(ox + (x - cx) * k, 1), round(oy - (y - cy) * k, 1)])
        # 화면으로 자른 **뒤에** 솎는다 — 먼저 솎으면 화면 안 구간이 사라진다
        for seg in (_clip(pts, *canvas) if canvas else [pts]):
            seg = _simplify(seg, 40)
            if len(seg) < 2:
                continue
            if reverse:
                seg.reverse()
            els.append({"type": "flow", "path": seg,
                        "count": max(2, min(8, len(seg) // 5))})
            if label and s["name"] and s["name"] not in seen:
                seen.add(s["name"])
                mid = seg[len(seg) // 2]
                els.append({"type": "place", "at": [mid[0], mid[1] - 18],
                            "text": s["name"]})
    return els


# ── 지도에서 직접 물길 읽기 ─────────────────────────────────────────────────
# 하천망 자료가 면형이라 물길을 못 뽑는다. 그런데 **지형도에는 이미 하천이 파란 선으로
# 그려져 있다.** 그 색을 짚어 내면 경로를 자료 없이 얻는다.
# 국토지리정보원 `korean_map` 실측색 (평창 L14).
RIVER_RGB = (176, 211, 228)


def river_mask(im, rgb=RIVER_RGB, tol=20):
    """지도 이미지에서 하천 픽셀만 남긴 마스크."""
    from PIL import Image
    px = im.convert("RGB").load()
    w, h = im.size
    m = Image.new("1", (w, h), 0)
    mp = m.load()
    r0, g0, b0 = rgb
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - r0) <= tol and abs(g - g0) <= tol and abs(b - b0) <= tol:
                mp[x, y] = 1
    return m


def flow_arrows(mask, origin_px, grid=300, min_frac=0.05, top=8, step=6):
    """하천 마스크 → 화살표 지점과 방향.

    정답 수계도를 보면 화살표가 **하천 굽이를 따라가지 않는다.** 주요 지점 6~7 개에
    방향만 맞게 찍혀 있다. 그러니 물길 전체를 복원할 필요가 없다 —
    격자로 잘라 칸마다 **하천 픽셀이 뻗은 쪽(주축)** 만 구하면 된다.

    ⚠️ 주축은 방향이 두 갈래다(±180°). **하천이 넓어지는 쪽을 하류로 본다** —
       물은 아래로 갈수록 모여 넓어지기 때문이다. 폭 차이가 뚜렷하지 않으면
       사업지에서 멀어지는 쪽으로 둔다 (사업지에서 물이 빠져나가는 그림이라).
       본문 유하 순서와 어긋나면 `--reverse` 로 뒤집는다."""
    import math
    w, h = mask.size
    mp = mask.load()
    ox, oy = origin_px
    cells = []
    for gy in range(0, h, grid):
        for gx in range(0, w, grid):
            xs = ys = n = 0
            pts = []
            for y in range(gy, min(gy + grid, h), step):
                for x in range(gx, min(gx + grid, w), step):
                    if mp[x, y]:
                        pts.append((x, y))
                        xs += x
                        ys += y
                        n += 1
            if n < (grid / step) ** 2 * min_frac:
                continue
            mx, my = xs / n, ys / n
            sxx = sum((x - mx) ** 2 for x, _ in pts) / n
            syy = sum((y - my) ** 2 for _, y in pts) / n
            sxy = sum((x - mx) * (y - my) for x, y in pts) / n
            theta = 0.5 * math.atan2(2 * sxy, sxx - syy)     # 주축 각도
            dx, dy = math.cos(theta), math.sin(theta)

            def width_at(sx, sy, rad=grid // 3):
                """(sx,sy) 둘레의 하천 픽셀 수 — 하천이 얼마나 넓은지."""
                c = 0
                for yy in range(max(0, int(sy - rad)), min(h, int(sy + rad)), step):
                    for xx in range(max(0, int(sx - rad)), min(w, int(sx + rad)), step):
                        if mp[xx, yy]:
                            c += 1
                return c

            reach = grid * 0.8
            fwd = width_at(mx + dx * reach, my + dy * reach)
            bwd = width_at(mx - dx * reach, my - dy * reach)
            if abs(fwd - bwd) >= max(3, (fwd + bwd) * 0.15):
                if fwd < bwd:                       # 넓어지는 쪽이 하류다
                    dx, dy = -dx, -dy
            elif (mx - ox) * dx + (my - oy) * dy < 0:
                dx, dy = -dx, -dy                   # 폭이 비슷하면 사업지에서 멀어지는 쪽
            spread = max(sxx, syy)                            # 길쭉할수록 물길답다
            # 정답은 **사업지에서 물이 빠져나가는 쪽에 화살표를 몰아 준다.**
            # 굵기만 보고 고르면 멀리 있는 큰 강에만 찍힌다 — 거리로 눌러 준다.
            dist = math.hypot(mx - ox, my - oy)
            score = spread * n / (1 + dist / grid)
            cells.append({"at": [round(mx, 1), round(my, 1)],
                          "dir": [round(dx, 4), round(dy, 4)],
                          "n": n, "spread": round(spread, 1),
                          "score": round(score, 1)})
    cells.sort(key=lambda c: -c["score"])
    return cells[:top]


def arrows_to_elements(cells, length=90, reverse=False):
    """화살표 지점 → figure_overlay 의 `flow` 요소 (짧은 두 점짜리 경로)."""
    els = []
    for c in cells:
        dx, dy = c["dir"]
        if reverse:
            dx, dy = -dx, -dy
        x, y = c["at"]
        els.append({"type": "flow",
                    "path": [[x - dx * length / 2, y - dy * length / 2],
                             [x + dx * length / 2, y + dy * length / 2]],
                    "count": 1})
    return els


def river_labels(lon, lat, half_deg, center_px, px_per_m, canvas,
                 names=None, size=None, gap=260, min_pts=40, avoid=()):
    """하천명 라벨 — 이름은 **자료에서**, 자리는 **화면 안 물길 위**에서.

    하천망 자료는 지오메트리가 면형이라 물길로는 못 쓰지만 **이름은 정확하다.**
    면 안의 점을 고르면 그 자리는 물 위이므로 라벨 자리로 충분하다.

    `avoid` 에 이미 놓인 라벨 자리(행정구역명 등)를 주면 그 둘레를 피한다."""
    import math
    from pyproj import Transformer
    import admin as A

    streams, err = fetch_streams(lon, lat, half_deg, names)
    if err:
        return [], err
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    cx_m, cy_m = tr.transform(lon, lat)
    ox, oy = center_px
    k = px_per_m / math.cos(math.radians(lat))
    w, h = canvas

    by = {}
    for s in streams:
        if len(s["path"]) < min_pts:
            continue
        pts = by.setdefault(s["name"], [])
        for lo, la in s["path"]:
            x, y = tr.transform(lo, la)
            pts.append((ox + (x - cx_m) * k, oy - (y - cy_m) * k))

    els = []
    for nm, pts in sorted(by.items(), key=lambda kv: -len(kv[1])):
        at = A._visible_center(pts, w, h)
        if at is None:
            continue
        # 이미 놓인 것(다른 하천명·행정구역명·장식)과 겹치면 **물길 위 다른 점**으로 옮긴다.
        # 그냥 버리면 큰 하천이 좋은 자리를 차지하고 작은 하천이 사라진다.
        block = [e["at"] for e in els] + list(avoid)
        if block and min(math.dist(at, b) for b in block) < gap:
            mx, my = w * 0.10, h * 0.10          # 가장자리에 붙으면 글자가 잘린다
            inside = [p for p in pts if mx <= p[0] <= w - mx and my <= p[1] <= h - my]
            if not inside:
                continue
            at = list(max(inside, key=lambda p: min(math.dist(p, b) for b in block)))
            if min(math.dist(at, b) for b in block) < gap * 0.5:
                continue                          # 그래도 붙으면 포기한다

        el = {"type": "river", "at": [round(at[0], 1), round(at[1], 1)], "text": nm}
        if size:
            el["size"] = size
        els.append(el)
    return els, None


def main():
    ap = argparse.ArgumentParser(description="하천망 → 수계도 흐름선")
    ap.add_argument("--lonlat", nargs=2, type=float, required=True)
    ap.add_argument("--names", nargs="*", help="본문에 나온 하천명 (없으면 주변 전부)")
    ap.add_argument("--center-px", nargs=2, type=float)
    ap.add_argument("--px-per-m", type=float)
    ap.add_argument("--half-deg", type=float, default=0.04, help="조회 반경 (도)")
    ap.add_argument("--reverse", action="store_true", help="흐름 방향을 뒤집는다")
    ap.add_argument("--no-label", action="store_true")
    ap.add_argument("--canvas", nargs=2, type=int, help="삽도 크기 — 밖으로 나간 구간을 자른다")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()

    streams, err = fetch_streams(*a.lonlat, a.half_deg, a.names)
    if err:
        sys.exit(err)
    if not streams:
        sys.exit("하천을 찾지 못했습니다 — 이름을 빼고 다시 해 보세요")
    by = {}
    for s in streams:
        by.setdefault(f"{s['name']} ({s['grade']})", 0)
        by[f"{s['name']} ({s['grade']})"] += len(s["path"])
    for n, c in sorted(by.items(), key=lambda x: -x[1]):
        print(f"  {n:<28} {c:>5}점")

    if a.out and a.center_px and a.px_per_m:
        els = to_elements(streams, a.lonlat, a.center_px, a.px_per_m,
                          not a.no_label, a.reverse, a.canvas)
        json.dump({"elements": els}, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"→ {a.out}  ({len(els)}개 요소)")


if __name__ == "__main__":
    main()

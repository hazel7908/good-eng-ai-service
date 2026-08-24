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
import argparse, json, math, os, re, sys

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


def _area_center(rings_px, w, h, margin=0.06, avoid=(), keep=0):
    """구역이 **화면에서 차지하는 면**의 중심. 경계선이 아니라 면을 본다.

    `avoid` 를 주면 그 자리들에서 `keep` 픽셀 넘게 떨어진 곳 중 **면 중심에 가장 가까운
    점**을 고른다. 겹친다고 라벨을 버리면 구역이 통째로 사라진다 — 괴산에서 `괴산군` 이
    `2.0km` 반경 라벨과 65px 이라 없어졌다.

    ⚠️ 꼭짓점 평균을 쓰면 **경계를 맞댄 이웃 구역들이 같은 자리로 수렴한다** —
       화면에 경계선 주변만 보이면 양쪽 구역의 화면 안 꼭짓점이 같은 선이기 때문이다.
       괴산에서 청주시·괴산군·미원면 라벨이 셋 다 x≈841 에 겹쳤다."""
    from PIL import Image, ImageDraw
    sc = 6                                   # 1/6 로 줄여 그린다 — 중심만 필요하다
    m = Image.new("1", (max(1, w // sc), max(1, h // sc)), 0)
    d = ImageDraw.Draw(m)
    for ring in rings_px:
        if len(ring) >= 3:
            d.polygon([(x / sc, y / sc) for x, y in ring], fill=1)
    px = m.load()
    pts = [(xx, yy) for yy in range(m.height) for xx in range(m.width) if px[xx, yy]]
    if not pts:
        return None
    cx = sum(p[0] for p in pts) / len(pts) * sc
    cy = sum(p[1] for p in pts) / len(pts) * sc
    mx, my = w * margin, h * margin

    def clamp(x, y):
        return [min(max(x, mx * 2), w - mx * 2), min(max(y, my * 2), h - my * 2)]

    if not avoid or all(math.dist(clamp(cx, cy), a) > keep for a in avoid):
        return clamp(cx, cy)
    # 면 안에서 다시 고른다 — 비켜 있으면서 중심에 가장 가까운 자리
    best = None
    for xx, yy in pts:
        p = clamp(xx * sc, yy * sc)
        if any(math.dist(p, a) <= keep for a in avoid):
            continue
        d = math.dist(p, (cx, cy))
        if best is None or d < best[0]:
            best = (d, p)
    return best[1] if best else None


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


def _label_box(text, canvas_w, size=None):
    """`draw_admin` 이 그릴 낱자 띠의 (반폭, 반높이). 화면 밖으로 밀리지 않게 재 둔다."""
    k = max(0.6, min(1.2, canvas_w / 1400))
    px = size or int(52 * k)
    box = px + max(4, round(px * 0.12)) * 2
    gap = round(px * 0.14)
    return (len(text) * box + (len(text) - 1) * gap) / 2, box / 2


def _split(name):
    """`청주시상당구` → `청주시` · `상당구`.

    ⚠️ 정답은 이 둘을 **두 줄로 쌓는다.** 한 줄로 쓰면 낱자 띠가 두 배로 길어져
       (괴산에서 501px) 화면 밖으로 밀려 잘린다."""
    m = re.match(r"^(.+?[시군])(.+구)$", name)
    return [m.group(1), m.group(2)] if m else [name]


def to_elements(regions, origin_lonlat, center_px, px_per_m, canvas, size=None,
                protect_px=0, avoid=(), keep=0):
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
        rings_px = []
        for ring in r["rings"]:
            rings_px.append([(ox + (tr.transform(lon, lat)[0] - cx_m) * k,
                              oy - (tr.transform(lon, lat)[1] - cy_m) * k)
                             for lon, lat in ring])
        # 화면에 조금도 안 걸치면 건너뛴다 (래스터화 비용을 아낀다)
        xs = [p[0] for ring in rings_px for p in ring]
        ys = [p[1] for ring in rings_px for p in ring]
        if max(xs) < 0 or min(xs) > w or max(ys) < 0 or min(ys) > h:
            continue
        at = _area_center(rings_px, w, h, avoid=avoid, keep=keep)
        if at is None:
            continue
        if protect_px:
            at = _push_out(at, center_px, protect_px)
        seen.add(r["name"])
        lines = _split(r["name"].replace(" ", ""))
        # ⚠️ 라벨 **폭을 재서** 안쪽으로 당긴다. 그냥 화면 안 중심에 두면 가장자리
        #    구역에서 낱자 띠가 잘린다 (괴산 `청주시상당구` 501px ↔ 여백 184px).
        for i, line in enumerate(lines):
            hw, hh = _label_box(line, w, size)
            ly = at[1] + (i - (len(lines) - 1) / 2) * hh * 2.4
            el = {"type": "admin",
                  "at": [round(min(max(at[0], hw + 8), w - hw - 8), 1),
                         round(min(max(ly, hh + 8), h - hh - 8), 1)],
                  "text": line, "_g": r["name"]}
            if size:
                el["size"] = size
            els.append(el)
    return els


def settlement_anchor(name, lon, lat, half_deg, to_px):
    """리명 라벨의 **마을 자리** 찾기 — 국가지명(자연부락 점)에서.

    행정구역의 기하 중심은 마을과 무관한 산속일 수 있다. 정답 삽도는 리명을
    **본마을 자리**에 붙인다. 국가지명 점 중 리명 어간을 품은 부락(수청리 → `상수청`)이
    있으면 그 자리를 쓴다. 없으면 None — 기하 중심으로 떨어진다.

    ⚠️ 어간 매칭 휴리스틱이다. 본마을 이름이 리명과 무관한 리에서는 못 찾는다."""
    stem = name[:-1] if name.endswith(("리", "동")) else name
    if len(stem) < 2:
        return None
    box = f"BOX({lon-half_deg},{lat-half_deg},{lon+half_deg},{lat+half_deg})"
    fs, err = P._get(data="LT_P_NSNMSSITENM", geomFilter=box, geometry="true",
                     size="100")
    if err:
        return None
    for f in fs:
        nm = f["properties"].get("land_kpyo", "")
        if stem in nm:
            lo, la = f["geometry"]["coordinates"]
            return to_px(lo, la)
    return None


def _avoid(els, gap=170):
    """라벨끼리 너무 붙으면 뒤엣것을 버린다 — 광역 삽도는 구역이 촘촘하다.

    ⚠️ `청주시` / `상당구` 처럼 **한 구역을 두 줄로 쌓은 것끼리는 예외**다.
       서로 붙어 있는 것이 정상인데 그냥 재면 아랫줄이 사라진다."""
    out = []
    for e in els:
        g = e.get("_g")
        if all(math.dist(e["at"], o["at"]) > gap
               for o in out if not (g and o.get("_g") == g)):
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

#!/usr/bin/env python3
"""
베이스 지도 취득 — 좌표만 주면 삽도용 지도 이미지를 만든다.

`figure_overlay.py` 가 "그리는 쪽"이라면 이 모듈은 **"받아 오는 쪽"** 이다.
지금까지 실무자가 브라우저 화면을 캡처해 이어붙이던 자리를 대체한다
(위성사진 한 장에 화면 4장을 이어붙인 흔적이 골든셋 PSD 에 남아 있다).

  좌표(EPSG:3857) → 타일 좌표 → 타일 N×N 다운로드 → 합성 → PNG + 메타

메타에는 **`px_per_m` 이 들어간다** — `figure_overlay.py` 의 `polar`(정온시설 자동 배치)가
그대로 쓰는 값이라, 지도 취득과 오버레이가 한 줄로 이어진다.

사용:
    python engine/map_fetch.py --address "괴산군 청안면 금신리 155-1" --source ngii -o base.png
    python engine/map_fetch.py --xy 14208655.63 4406482.02 --source ecvam -o base.png
    python engine/map_fetch.py --xy ... --source egis --layer me:na_plg_conservation -o base.png
    python engine/map_fetch.py --list-sources

인증:
    ECVAM 은 API 키가 필요하다 → `~/.ecvam.env` 의 `ECVAM_API_KEY`
      (신청: ecvam.neins.go.kr → 오픈API → 신청. **사용 URL 은 `QGIS` 로 등록**한다)
    NGII(국토지리정보원) 는 `~/.ngii.env` 의 `NGII_API_KEY` — 회원가입 + 관리자 승인이 필요하다
    VWorld 는 `~/.vworld.env` 의 `VWORLD_API_KEY` — **지오코딩(주소→좌표)에 쓴다**
    EGIS 는 키가 필요 없다 (2026-08-19 실측).

⚠️ 출처마다 이용 조건이 다르다. 보고서 납품에 쓰기 전 약관을 확인할 것
   (ECVAM 약관 제11조 — 사전 승낙 없는 영리행위 금지). → docs/20260819_삽도_자동화.md §2
"""
import argparse, io, math, os, sys, urllib.request
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow 가 필요합니다: .venv/bin/pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
TILE = 256
R = 20037508.342789244          # Web Mercator 반지름 (EPSG:3857 경계)

# 국토지리정보원 WMTS 는 **EPSG:5179(UTM-K)** 를 쓴다 — Web Mercator 가 아니다.
# 격자 정의는 국토정보맵의 OpenLayers 객체에서 직접 읽어 확인했다 (2026-08-20).
NGII_ORIGIN = (-200000.0, 4000000.0)
NGII_RES = [2088.96, 1044.48, 522.24, 261.12, 130.56, 65.28, 32.64,
            16.32, 8.16, 4.08, 2.04, 1.02, 0.51, 0.255]        # L05 … L18
NGII_LEVELS = {f"L{5 + i:02d}": r for i, r in enumerate(NGII_RES)}

# ⚠️ 서버가 **Referer 와 User-Agent 를 둘 다 요구**한다. 하나라도 없으면
#    `Access_Denied` 15바이트 또는 HTTP 400 이 온다 (실측).
NGII_HEADERS = {"Referer": "https://QGIS", "User-Agent": "Mozilla/5.0"}

# ── 출처 정의 ────────────────────────────────────────────────────────────────
# 어느 삽도에 쓰는지는 docs/20260819_삽도_자동화.md §2 의 표와 짝을 이룬다.
SOURCES = {
    "ecvam": {
        "kind": "tms",
        "url": "https://webgis.neins.go.kr/tms/{layer}/{key}/{z}/{x}/{y}",
        "layer": "ECVAM_nem_ecvam",     # TMS 매뉴얼 실측 — 접두어 `ECVAM_` 이 붙는다
        "key_env": ("~/.ecvam.env", "ECVAM_API_KEY"),
        "note": "국토환경성평가지도 (타 파트 삽도)",
    },
    "ngii": {
        "kind": "wmts5179",
        "url": ("https://map.ngii.go.kr/openapi/Gettile.do?apikey={key}&layer={layer}"
                "&style=korean&tilematrixset=EPSG%3A5179&Service=WMTS&Request=GetTile"
                "&Version=1.0.0&Format=image%2Fpng&TileMatrix={z}&TileCol={x}&TileRow={y}"),
        # 실측한 레이어 이름 — 지도 뷰어 JS 에서 확인했다.
        #   korean_map 일반지도 · satellite_map 위성영상 · hybrid_map 라벨(투명)
        #   white_map/white_edu_map 백지도 · night_map · color_map_red/green/blue(색각)
        # ⚠️ `airmap` 은 이름은 있는데 **빈 응답**이 온다. 위성영상은 satellite_map 이다.
        # 위성 + 라벨은 `--layer satellite_map+hybrid_map` 처럼 `+` 로 겹쳐 받는다.
        "layer": "korean_map",
        "key_env": ("~/.ngii.env", "NGII_API_KEY"),
        "note": "국토지리정보원 지형도 — 지역개황도·수계도 베이스",
    },
    "egis": {
        "kind": "wms",
        "url": "https://api.mcee.go.kr/geoserver/me/wms",
        "layer": "me:raster_landcover_change_80-10",
        "key_env": None,                 # 인증키 불필요 (실측)
        "note": "환경부 환경주제도 — 자연환경·물환경·기후대기 120종",
    },
}


def load_key(spec):
    """`~/.ecvam.env` 같은 파일에서 키를 읽는다. **키를 로그에 남기지 않는다.**"""
    path, var = spec
    p = Path(path).expanduser()
    if not p.exists():
        sys.exit(f"인증 파일이 없습니다: {p}\n  ECVAM 키 신청 → ecvam.neins.go.kr / 오픈API / 신청")
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(var + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{p} 안에 {var} 가 없습니다")


# ── 지오코딩 (주소 → 좌표) ──────────────────────────────────────────────────
VWORLD_SEARCH = "https://api.vworld.kr/req/search"
VWORLD_KEY_ENV = ("~/.vworld.env", "VWORLD_API_KEY")
VWORLD_DOMAIN = "http://localhost"      # 키 신청 때 등록한 서비스URL 과 같아야 한다


def geocode(address, domain=VWORLD_DOMAIN):
    """주소 → EPSG:3857 좌표. **사업 주소 한 줄에서 삽도까지 이어지는 첫 칸이다.**

    ECVAM 사이트도 내부적으로 이 API 를 부른다 — 그 화면에서 읽던 좌표와 소수점까지 같다.
    지번이면 `parcel`, 도로명(`…로`·`…길`)이면 `road` 로 분류가 갈린다."""
    import json as _json
    import urllib.parse
    key = load_key(VWORLD_KEY_ENV)
    last = address.strip().split()[-1] if address.strip() else ""
    category = "road" if last and last[-1] in "로길" else "parcel"
    q = urllib.parse.urlencode({
        "service": "search", "version": "2.0", "request": "search",
        "size": 5, "page": 1, "crs": "EPSG:3857", "format": "json",
        "type": "address", "category": category,
        "apiKey": key, "domain": domain, "query": address,
    })
    data = _json.loads(urllib.request.urlopen(f"{VWORLD_SEARCH}?{q}", timeout=30).read())
    res = data.get("response", {})
    if res.get("status") != "OK" or res.get("record", {}).get("total") in ("0", 0, None):
        raise LookupError(f"주소를 찾지 못했습니다: {address} (category={category})")
    it = res["result"]["items"][0]
    return (float(it["point"]["x"]), float(it["point"]["y"]),
            it["address"].get("parcel") or it["address"].get("road") or address)


# ── 좌표 변환 ────────────────────────────────────────────────────────────────
def merc_to_lonlat(mx, my):
    lon = mx / R * 180.0
    lat = math.degrees(2 * math.atan(math.exp(my / R * math.pi)) - math.pi / 2)
    return lon, lat


def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def resolution(lat, z):
    """m/px — Web Mercator 는 위도에 따라 축척이 달라진다."""
    return 156543.03392804097 * math.cos(math.radians(lat)) / (2 ** z)


def pick_zoom(source, lat, radius_m, span=3, size=768, margin=1.25):
    """**반경 radius_m 이 화면에 들어오는 가장 상세한 축척**을 고른다.

    정온시설 표의 가장 먼 지점을 넣으면 된다 — 지도를 너무 넓게 잡아 지점이 한 덩어리로
    뭉치거나, 너무 좁게 잡아 지점이 잘리는 일을 막는다.
    `margin` 은 라벨이 가장자리에서 잘리지 않게 두는 여유다."""
    need = radius_m * margin
    if SOURCES[source]["kind"] == "wmts5179":
        half_px = span * TILE / 2
        ok = [(lvl, r) for lvl, r in NGII_LEVELS.items() if half_px * r >= need]
        if not ok:
            return max(NGII_LEVELS, key=lambda k: NGII_LEVELS[k])   # 가장 넓은 축척
        return min(ok, key=lambda t: t[1])[0]                        # 그중 가장 상세한 것
    # 웹 메르카토르 계열(ECVAM/EGIS) — 줌이 1 오르면 해상도가 절반
    half_px = (span * TILE if SOURCES[source]["kind"] == "tms" else size) / 2
    for z in range(19, 4, -1):
        if half_px * resolution(lat, z) >= need:
            return z
    return 10


# ── 취득 ────────────────────────────────────────────────────────────────────
def fetch_tms(src, key, z, tx, ty, span):
    """타일 span×span 장을 받아 이어붙인다. 실무자가 손으로 하던 그 작업이다."""
    half = span // 2
    canvas = Image.new("RGB", (TILE * span, TILE * span), (255, 255, 255))
    got = 0
    for dx in range(-half, half + 1):
        for dy in range(-half, half + 1):
            url = src["url"].format(layer=src["layer"], key=key,
                                    z=z, x=tx + dx, y=ty + dy)
            try:
                data = urllib.request.urlopen(url, timeout=30).read()
                im = Image.open(io.BytesIO(data)).convert("RGB")
                canvas.paste(im, ((dx + half) * TILE, (dy + half) * TILE))
                got += 1
            except Exception as e:
                print(f"  [warn] 타일 {z}/{tx+dx}/{ty+dy} — {type(e).__name__}", file=sys.stderr)
    return canvas, got


def fetch_ngii(src, key, level, mx, my, span):
    """국토지리정보원 지형도 — EPSG:5179 타일을 span×span 받아 합성한다."""
    try:
        from pyproj import Transformer
    except ImportError:
        sys.exit("pyproj 가 필요합니다: .venv/bin/pip install pyproj")
    tr = Transformer.from_crs("EPSG:3857", "EPSG:5179", always_xy=True)
    X, Y = tr.transform(mx, my)
    res = NGII_LEVELS[level]
    ox, oy = NGII_ORIGIN
    fx, fy = (X - ox) / (TILE * res), (oy - Y) / (TILE * res)
    c0, r0 = int(fx), int(fy)
    half = span // 2
    canvas = Image.new("RGB", (TILE * span, TILE * span), (255, 255, 255))
    got = 0
    # `satellite_map+hybrid_map` — 뒤 레이어를 앞 레이어 위에 겹친다 (라벨은 투명 PNG).
    layers = src["layer"].split("+")
    for dx in range(-half, half + 1):
        for dy in range(-half, half + 1):
            urls = [src["url"].format(key=key, layer=L, z=level,
                                      x=c0 + dx, y=r0 + dy) for L in layers]
            tile = None
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers=NGII_HEADERS)
                    im = Image.open(io.BytesIO(
                        urllib.request.urlopen(req, timeout=30).read()))
                except Exception as e:
                    print(f"  [warn] 타일 {level}/{c0+dx}/{r0+dy} — {type(e).__name__}",
                          file=sys.stderr)
                    continue
                if tile is None:
                    tile = im.convert("RGB")
                else:
                    # 라벨층 — 투명도를 살려 겹친다. hybrid_map 은 **팔레트+투명** PNG 라
                    # 그냥 붙이면 배경까지 덮어 위성이 사라진다. RGBA 로 펴서 마스크를 쓴다.
                    if im.mode == "P" and "transparency" in im.info:
                        im = im.convert("RGBA")
                    tile.paste(im, (0, 0), im if im.mode in ("RGBA", "LA") else None)
            if tile is not None:
                canvas.paste(tile, ((dx + half) * TILE, (dy + half) * TILE))
                got += 1
    cx = (fx - c0 + half) * TILE
    cy = (fy - r0 + half) * TILE
    return canvas, got, res, (cx, cy)


def fetch_wms(src, layer, mx, my, half_m, size):
    """BBOX 로 한 장을 받는다. WMS 는 타일을 이어붙일 필요가 없다."""
    bbox = f"{mx-half_m},{my-half_m},{mx+half_m},{my+half_m}"
    q = (f"{src['url']}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS={layer}"
         f"&BBOX={bbox}&WIDTH={size}&HEIGHT={size}&SRS=EPSG:3857"
         f"&FORMAT=image/png&STYLES=")
    data = urllib.request.urlopen(q, timeout=60).read()
    return Image.open(io.BytesIO(data)).convert("RGB")


def sheet25k(lon, lat):
    """경위도 → 1:25,000 도엽번호 (예: 미탄 378113).

    도엽은 이름이 곧 격자다 — 번호만 알면 네 모서리 경위도가 나온다.
    `위도2 + 경도1 + 1:50,000 칸2 + 1:25,000 사분면1` 여섯 자리.

      37 8 11 3  =  북위 37°대 · 동경 128°대 · 1°×1° 를 4×4 로 쪼갠 11번 칸(북서부터
                    동쪽으로) · 그 칸을 다시 넷으로 쪼갠 남서(3) 사분면

    골든셋 8건의 본문 도엽번호(진천 367024 · 미탄 378113 등)로 검증했다."""
    d_lat, d_lon = int(lat), int(lon)
    row50 = int((d_lat + 1 - lat) / 0.25)         # 북쪽부터 0..3
    col50 = int((lon - d_lon) / 0.25)
    n50 = row50 * 4 + col50 + 1
    top = d_lat + 1 - row50 * 0.25
    left = d_lon + col50 * 0.25
    quad = (1 if lat > top - 0.125 else 3) + (0 if lon < left + 0.125 else 1)
    return f"{d_lat}{d_lon % 10}{n50:02d}{quad}"


def sheets25k(lon, lat, half_m=0):
    """반경 안에 걸치는 도엽 전부 — 사업지가 도엽 경계에 걸칠 수 있다.

    옥천 정답은 `대전 367104, 옥천 367113` 처럼 **둘을 병기**한다. 삽도 범위(반경)를
    주면 네 귀퉁이가 밟는 도엽을 모아 온다."""
    dd = half_m / 111320.0
    out = []
    for dx in (-dd, dd):
        for dy in (-dd, dd):
            no = sheet25k(lon + dx, lat + dy)
            if no not in out:
                out.append(no)
    return sorted(out)


def sheet25k_corners(no):
    """도엽번호 → (서, 남, 동, 북) 경위도. 도엽 스캔의 좌표 맞춤(georeferencing)에 쓴다."""
    d_lat, d_lon10, n50, quad = int(no[:2]), int(no[2]), int(no[3:5]), int(no[5])
    d_lon = 120 + d_lon10 if d_lon10 >= 4 else 130 + d_lon10   # 한국은 124~131°E
    row50, col50 = divmod(n50 - 1, 4)
    top = d_lat + 1 - row50 * 0.25
    left = d_lon + col50 * 0.25
    if quad in (3, 4):
        top -= 0.125
    if quad in (2, 4):
        left += 0.125
    return (left, top - 0.125, left + 0.125, top)


def fetch(source, mx, my, z=15, span=3, size=768, layer=None):
    """→ (이미지, 메타). 메타의 `px_per_m` 은 figure_overlay 의 `polar` 에 그대로 넣는다."""
    src = SOURCES[source]
    lon, lat = merc_to_lonlat(mx, my)

    if src["kind"] == "wmts5179":
        src = dict(src, layer=layer or src["layer"])
        key = load_key(src["key_env"])
        level = f"L{z:02d}" if isinstance(z, int) else str(z)
        if level not in NGII_LEVELS:
            sys.exit(f"레벨은 L05~L18 입니다 (받은 값: {level})")
        img, got, res, (cx, cy) = fetch_ngii(src, key, level, mx, my, span)
        meta = {"source": source, "layer": src["layer"], "level": level,
                "tiles": f"{got}/{span*span}", "px_per_m": round(1 / res, 6),
                "m_per_px": round(res, 4), "center_px": [round(cx, 1), round(cy, 1)],
                "lonlat": [round(lon, 6), round(lat, 6)]}
        return img, meta

    if src["kind"] == "tms":
        key = load_key(src["key_env"])
        fx, fy = lonlat_to_tile(lon, lat, z)
        img, got = fetch_tms(src, key, z, int(fx), int(fy), span)
        res = resolution(lat, z)                       # m/px
        # 요청 좌표는 중앙 타일 안의 임의 지점이다 — 캔버스 원점을 정확히 잡아 준다.
        half = span // 2
        cx = (fx - int(fx) + half) * TILE
        cy = (fy - int(fy) + half) * TILE
        meta = {"source": source, "layer": src["layer"], "z": z, "tiles": f"{got}/{span*span}",
                "px_per_m": round(1 / res, 6), "m_per_px": round(res, 4),
                "center_px": [round(cx, 1), round(cy, 1)], "lonlat": [round(lon, 6), round(lat, 6)]}
        return img, meta

    layer = layer or src["layer"]
    half_m = size / 2 * resolution(lat, z)
    img = fetch_wms(src, layer, mx, my, half_m, size)
    res = 2 * half_m / size
    meta = {"source": source, "layer": layer, "z": z,
            "px_per_m": round(1 / res, 6), "m_per_px": round(res, 4),
            "center_px": [size / 2, size / 2], "lonlat": [round(lon, 6), round(lat, 6)]}
    return img, meta


def main():
    ap = argparse.ArgumentParser(description="베이스 지도 취득 (좌표 → 지도 이미지)")
    ap.add_argument("--xy", nargs=2, type=float, metavar=("X", "Y"),
                    help="EPSG:3857 좌표")
    ap.add_argument("--address", help="사업 주소 — 지오코딩해서 좌표를 얻는다 (VWorld 키 필요)")
    ap.add_argument("--source", default="ecvam", choices=list(SOURCES))
    ap.add_argument("--layer", help="WMS 레이어 (egis 전용)")
    ap.add_argument("--zoom", type=int, default=15,
                    help="ecvam/egis 는 웹 줌(0~19), ngii 는 5~18 (L05~L18)")
    ap.add_argument("--fit", type=float, metavar="M",
                    help="이 반경(m)이 들어오도록 축척을 자동으로 고른다 — "
                         "정온시설 표의 가장 먼 거리를 넣으면 된다")
    ap.add_argument("--span", type=int, default=3, help="타일 격자 크기 (홀수)")
    ap.add_argument("--size", type=int, default=768, help="WMS 출력 크기")
    ap.add_argument("-o", "--out")
    ap.add_argument("--list-sources", action="store_true")
    a = ap.parse_args()

    if not a.xy and a.address:
        x, y, matched = geocode(a.address)
        print(f"지오코딩: {matched}\n   → EPSG:3857 ({x:.2f}, {y:.2f})")
        a.xy = [x, y]

    if a.list_sources or not a.xy:
        for k, v in SOURCES.items():
            auth = "키 필요" if v["key_env"] else "키 불필요"
            print(f"  {k:<8} {v['kind'].upper():<4} {auth:<8} {v['note']}")
        return

    zoom = a.zoom
    if a.fit:
        lon, lat = merc_to_lonlat(a.xy[0], a.xy[1])
        picked = pick_zoom(a.source, lat, a.fit, a.span, a.size)
        zoom = picked if isinstance(picked, str) else picked
        print(f"축척 자동 선택: 반경 {a.fit:.0f}m → {picked}")
    img, meta = fetch(a.source, a.xy[0], a.xy[1], zoom, a.span, a.size, a.layer)
    out = a.out or f"map_{a.source}.png"
    img.save(out)
    print(f"→ {out}  {img.size}")
    for k, v in meta.items():
        print(f"   {k:<10} {v}")
    print(f"\n   figure_overlay 연결: polar 의 origin={meta['center_px']}, "
          f"px_per_m={meta['px_per_m']}")


if __name__ == "__main__":
    main()

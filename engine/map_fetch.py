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
    python engine/map_fetch.py --xy 14208655.63 4406482.02 --source ecvam -o base.png
    python engine/map_fetch.py --xy ... --source egis --layer me:na_plg_conservation -o base.png
    python engine/map_fetch.py --list-sources

인증:
    ECVAM 은 API 키가 필요하다 → `~/.ecvam.env` 의 `ECVAM_API_KEY`
      (신청: ecvam.neins.go.kr → 오픈API → 신청. **사용 URL 은 `QGIS` 로 등록**한다)
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


def fetch_wms(src, layer, mx, my, half_m, size):
    """BBOX 로 한 장을 받는다. WMS 는 타일을 이어붙일 필요가 없다."""
    bbox = f"{mx-half_m},{my-half_m},{mx+half_m},{my+half_m}"
    q = (f"{src['url']}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS={layer}"
         f"&BBOX={bbox}&WIDTH={size}&HEIGHT={size}&SRS=EPSG:3857"
         f"&FORMAT=image/png&STYLES=")
    data = urllib.request.urlopen(q, timeout=60).read()
    return Image.open(io.BytesIO(data)).convert("RGB")


def fetch(source, mx, my, z=15, span=3, size=768, layer=None):
    """→ (이미지, 메타). 메타의 `px_per_m` 은 figure_overlay 의 `polar` 에 그대로 넣는다."""
    src = SOURCES[source]
    lon, lat = merc_to_lonlat(mx, my)

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
                    help="EPSG:3857 좌표 (ECVAM 주소검색이 돌려주는 그 좌표)")
    ap.add_argument("--source", default="ecvam", choices=list(SOURCES))
    ap.add_argument("--layer", help="WMS 레이어 (egis 전용)")
    ap.add_argument("--zoom", type=int, default=15)
    ap.add_argument("--span", type=int, default=3, help="타일 격자 크기 (홀수)")
    ap.add_argument("--size", type=int, default=768, help="WMS 출력 크기")
    ap.add_argument("-o", "--out")
    ap.add_argument("--list-sources", action="store_true")
    a = ap.parse_args()

    if a.list_sources or not a.xy:
        for k, v in SOURCES.items():
            auth = "키 필요" if v["key_env"] else "키 불필요"
            print(f"  {k:<8} {v['kind'].upper():<4} {auth:<8} {v['note']}")
        return

    img, meta = fetch(a.source, a.xy[0], a.xy[1], a.zoom, a.span, a.size, a.layer)
    out = a.out or f"map_{a.source}.png"
    img.save(out)
    print(f"→ {out}  {img.size}")
    for k, v in meta.items():
        print(f"   {k:<10} {v}")
    print(f"\n   figure_overlay 연결: polar 의 origin={meta['center_px']}, "
          f"px_per_m={meta['px_per_m']}")


if __name__ == "__main__":
    main()

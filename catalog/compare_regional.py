#!/usr/bin/env python3
"""
지역개황도 — **골든셋 전수 대조**. 정답과 같은 베이스 위에서 우리 도구를 돌린다.

지금까지 삽도 대조는 평창 1건이었다. "5종 전부 정답에 근접" 이라는 말의 표본이 하나면
근거가 약하다 — 생태자연도에서 8/8 이 버그 둘에 가려져 있던 것과 같은 위험이다.

세 조각이 갖춰져 전수가 가능해졌다 (2026-08-23):

    ① 골든셋 8건의 도엽 베이스     `catalog/harvest_sheets.py`
    ② 정답 삽도                   PSD 를 통째로 합성하면 그대로 나온다
    ③ 좌표 맞춤값                 `catalog/psd_georef.py` — 레이어에서 자동 추출

지역개황도는 **주소 한 줄이면 그려진다.** 필지 경계가 들어가지 않아(6km 반경이라 점이다)
편입토지조서도 필요 없다.

    python catalog/compare_regional.py            # 전 사업 생성·비교 이미지
    python catalog/compare_regional.py --site 청주_호명리
"""
import argparse, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
SHEETS = os.path.join(ROOT, "raw_data/nas/sheets")
ANSWERS = os.path.join(ROOT, "raw_data/nas/answers")
OUT = os.path.join(ROOT, "raw_data/nas/compare")
GEOREF = os.path.join(ROOT, "catalog/data/sheet_georef.json")

# 주소는 골든셋 8건의 사업 주소다 (`engine/ecgy.py` 와 같은 목록)
ADDR = {
    "평창_수청리": "강원특별자치도 평창군 미탄면 수청리 73",
    "괴산_금신리": "충청북도 괴산군 청안면 금신리 155-1",
    "괴산_후평리": "충청북도 괴산군 청천면 후평리 산1",
    "옥천_사양리": "충청북도 옥천군 군서면 사양리 산39-1",
    "원주_무장리": "강원특별자치도 원주시 호저면 무장리 578",
    "천안_화덕리": "충청남도 천안시 동남구 동면 화덕리 30",
    "청주_호명리": "충청북도 청주시 청원구 북이면 호명리 430",
    "충주_율능리": "충청북도 충주시 엄정면 율능리 91-2",
}

# 정답 실측값 (청주). 위성사진과 달리 **밝은 지형도 위**라 흰 선이 보이지 않는다.
RING_COLOR = [127, 127, 125]
RING_FILL = [150, 140, 110, 58]
RADII = [1000, 2000, 3000, 4000, 5000, 6000]


def build(site, verbose=True):
    import map_fetch as M, admin as A
    from pyproj import Transformer
    from PIL import Image

    base = os.path.join(SHEETS, site, "지역개황도.png")
    if not os.path.exists(base):
        base = os.path.join(SHEETS, site, "대상지역설정도.png")
    if not os.path.exists(base):
        return None, "베이스가 없습니다"
    g = json.load(open(GEOREF, encoding="utf-8")).get(site, {}).get("지역개황도")
    if not g:
        return None, "좌표 맞춤값이 없습니다"

    anchor, ppm = g["anchor_px"], g["px_per_m"]
    W, H = Image.open(base).size
    x, y, _ = M.geocode(ADDR[site])
    lon, lat = Transformer.from_crs("EPSG:3857", "EPSG:4326",
                                    always_xy=True).transform(x, y)

    els = [{"type": "rings", "origin": anchor, "radii_m": RADII, "px_per_m": ppm,
            "label_deg": 0, "short": True, "color": RING_COLOR, "fill": RING_FILL},
           {"type": "target", "at": anchor},
           {"type": "label", "at": [anchor[0], anchor[1] - 120],
            "text": "사업계획지구", "from": anchor}]
    regs = []
    for lv in ("시도", "시군구", "읍면동"):
        r, err = A.fetch(lv, lon, lat, 0.35)
        if err:
            continue
        regs += A.to_elements(r, (lon, lat), anchor, ppm, (W, H),
                              protect_px=int(1200 * ppm))
    els += A._avoid(regs, int(700 * ppm))
    els += [{"type": "scalebar", "at": [W - 560, H - 120],
             "length_px": int(1000 * ppm), "label": "1.0km"},
            {"type": "north", "at": [W - 160, H - 190]}]

    os.makedirs(OUT, exist_ok=True)
    spec = os.path.join(OUT, f"{site}.spec.json")
    json.dump({"base": base, "elements": els}, open(spec, "w", encoding="utf-8"),
              ensure_ascii=False)
    out = os.path.join(OUT, f"{site}.jpg")
    subprocess.run([sys.executable, os.path.join(ROOT, "engine/figure_overlay.py"),
                    spec, "-o", out], check=True, capture_output=True)
    return out, None


def side_by_side(site, our):
    from PIL import Image
    ans = os.path.join(ANSWERS, f"{site}.jpg")
    if not os.path.exists(ans):
        return None
    a = Image.open(ans).convert("RGB")
    b = Image.open(our).convert("RGB")
    w = 1150
    a.thumbnail((w, w)); b.thumbnail((w, w))
    c = Image.new("RGB", (max(a.width, b.width), a.height + b.height + 14),
                  (255, 255, 255))
    c.paste(a, (0, 0)); c.paste(b, (0, a.height + 14))
    p = os.path.join(OUT, f"{site}.대조.jpg")
    c.save(p, quality=85)
    return p


def main():
    ap = argparse.ArgumentParser(description="지역개황도 전수 대조")
    ap.add_argument("--site", help="한 사업만")
    a = ap.parse_args()

    sites = [a.site] if a.site else sorted(ADDR)
    ok = 0
    for site in sites:
        our, err = build(site)
        if err:
            print(f"  ✗ {site:<12} {err}")
            continue
        cmp = side_by_side(site, our)
        ok += 1
        print(f"  ○ {site:<12} → {os.path.basename(our)}"
              f"{' · 대조 ' + os.path.basename(cmp) if cmp else ' (정답 없음)'}")
    print(f"\n{ok}/{len(sites)}건 생성 → {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
생태·자연도 — 삽도 베이스 + 등급 판정.

출처는 **국립생태원 EcoBank** 다 (환경부 EGIS 에서 이관됐다). 공공데이터포털 키가 필요하고
`~/.ecobank.env` 의 `ECOBANK_API_KEY` 를 읽는다.

    WMS  지도 이미지 → 삽도 베이스 (등급별 색이 법정 표준이라 그대로 쓴다)
    WFS  폴리곤 + 속성 → **본문 서술의 근거값**

WFS 가 지오메트리와 속성을 함께 준다. 속성조회를 따로 부를 일이 없다.

| 필드 | 뜻 |
|---|---|
| `eczm_grad` | 생태자연도 등급 |
| `plnt_cln_ttle` · `cln_symbl` | 식물군락 명칭 · 기호 (`상수리나무군락` · `Qa`) |
| `vtn_evl_grad` · `tpgrph_evl_grad` | 식생 · 지형 평가등급 |

⚠️ **키가 Encoding 형이면 그대로 못 쓴다.** 공공데이터포털은 Encoding·Decoding 두 벌을
   주는데, Encoding 키를 다시 URL 인코딩하면 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 가 난다.
   여기서는 어느 쪽이 저장돼 있든 `unquote` 를 한 번 걸어 맞춘다.

⚠️ 좌표계가 **EPSG:5186**(중부원점)이다. NGII 의 5179 와도 다르다.

검증: `python engine/ecology.py --self-test`   (골든셋)
"""
import argparse, glob, io, os, re, sys, urllib.parse, urllib.request

BASE = "https://apis.data.go.kr/B553084/ecoapi/EcologyzmpService"
CRS = "EPSG:5186"

# 폴리곤에 안 걸리면 몇 등급으로 볼 것인가.
# 생태자연도는 1·2등급과 별도관리지역을 그리고 나머지는 3등급이다.
# 골든셋 8건이 모두 3등급이고 천안 실측에서도 사업지가 폴리곤 밖이었다.
# ⚠️ 그래도 **단정하지 않는다** — 자료가 안 덮인 것인지 3등급인지 구분할 길이 없다.
GRADE_UNSET = "3"

# 등급 9 는 속성(군락명·평가등급)이 전부 비어 있다 — 식생 평가가 아니라 법정 보호구역이라
# 그렇다. **별도관리지역**으로 본다. 보고서 문장이 "1등급 권역 및 별도관리지역"을 함께 묻는다.
GRADE_SPECIAL = "9"
GRADE_LABEL = {"1": "1등급", "2": "2등급", "3": "3등급", "9": "별도관리지역"}

# WMS 출력에서 실측한 등급별 색 (평창 수청리 — 네 등급이 다 나오는 자리다).
# 우리가 칠하는 것이 아니라 **읽어서 범례를 만들기 위한** 값이다.
GRADE_COLOR = {"1": (26, 168, 0), "2": (146, 208, 80),
               "3": (255, 255, 255), "9": (255, 128, 0)}


def legend_items(grades=("1", "2", "3", "9")):
    """등급 범례 → `figure_overlay` 의 legend items. 지도 아래 가로띠로 쓴다."""
    return [[list(GRADE_COLOR[g]), GRADE_LABEL[g]] for g in grades]


def _key():
    path = os.path.expanduser("~/.ecobank.env")
    if not os.path.exists(path):
        sys.exit("~/.ecobank.env 가 없습니다 (ECOBANK_API_KEY) — 공공데이터포털에서 발급")
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("ECOBANK_API_KEY"):
            # Encoding 키든 Decoding 키든 여기서 한 벌로 맞춘다
            return urllib.parse.unquote(line.split("=", 1)[1].strip().strip("'\""))
    sys.exit("~/.ecobank.env 에 ECOBANK_API_KEY 가 없습니다")


def _bbox(x, y, half_m):
    return f"{x-half_m},{y-half_m},{x+half_m},{y+half_m}"


def to_5186(lon, lat):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(lon, lat)


def wms(lon, lat, half_m=900, size=768, transparent=True):
    """삽도 베이스 이미지. 등급별 색은 법정 표준이라 우리가 칠하지 않는다."""
    from PIL import Image
    x, y = to_5186(lon, lat)
    q = {"ServiceKey": _key(), "srs": CRS, "bbox": _bbox(x, y, half_m),
         "width": str(size), "height": str(size), "format": "image/png",
         "transparent": "true" if transparent else "false"}
    d = urllib.request.urlopen(f"{BASE}/wms/getEcologyzmpWMS?"
                               + urllib.parse.urlencode(q), timeout=40).read()
    if d[:4] != b"\x89PNG":
        sys.exit(f"이미지가 아닙니다 — {d[:200]!r}")
    im = Image.open(io.BytesIO(d))
    # 지형도 위에 겹칠 것이므로 알파를 살린다
    return im.convert("RGBA") if transparent else im.convert("RGB")


FIELDS = ["eczm_grad", "plnt_cln_ttle", "cln_symbl", "vtn_evl_grad",
          "tpgrph_evl_grad", "amplt_evl_grad", "smld_evl_grad", "frph_agcl_code"]


def wfs(lon, lat, half_m=900):
    """폴리곤 + 속성. 반환 = [{필드…, 'rings': [[(x,y)…]]}] (좌표는 EPSG:5186)."""
    x, y = to_5186(lon, lat)
    q = {"ServiceKey": _key(), "srs": CRS, "bbox": _bbox(x, y, half_m)}
    d = urllib.request.urlopen(f"{BASE}/wfs/getEcologyzmpWFS?"
                               + urllib.parse.urlencode(q), timeout=60
                               ).read().decode("utf-8", "replace")
    out = []
    for f in re.findall(r"<gml:featureMember>(.*?)</gml:featureMember>", d, re.S):
        rec = {}
        for k in FIELDS:
            m = re.search(rf"<open:{k}>(.*?)</open:{k}>", f, re.S)
            rec[k] = m.group(1).strip() if m else ""
        rec["rings"] = [
            [tuple(map(float, p.split(",")[:2])) for p in co.split()]
            for co in re.findall(r"<gml:coordinates>(.*?)</gml:coordinates>", f, re.S)]
        out.append(rec)
    return out


def _inside(ring, x, y):
    n = len(ring)
    c, j = False, n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def _overlaps(a, b):
    """두 폴리곤이 겹치는지 — 한쪽 점이 다른 쪽 안에 있으면 겹친 것으로 본다.

    ⚠️ 근사다. 변끼리만 스치는 경우는 놓친다. 실무에서 사업지와 등급 구역이 그렇게
       만나는 일은 드물어 이 정도로 충분하다."""
    return (any(_inside(b, x, y) for x, y in a)
            or any(_inside(a, x, y) for x, y in b))


def assess(lon, lat, half_m=900, site_rings=None):
    """사업지 등급과 주변 분포 → 본문 서술에 그대로 들어가는 값.

    정답 문장은 이렇게 쓴다:
        "생태·자연도 3등급으로 지정되어 있으며, 1등급 권역 및 별도관리지역은
         분포하지 않는 것으로 조사되었다"

    ⚠️ **"분포하지 않는다"의 범위는 사업계획지구다.** 주변 1~2km 로 넓히면 1등급이
       흔히 잡힌다 (골든셋 7건 중 5건). `site_rings`(EPSG:5186 폴리곤)를 주면 그 안에서
       판정하고, 없으면 중심점 하나로 판정한다."""
    x, y = to_5186(lon, lat)
    feats = wfs(lon, lat, half_m)

    def touches(f):
        if site_rings:
            return any(len(r) >= 3 and len(sr) >= 3 and _overlaps(sr, r)
                       for r in f["rings"] for sr in site_rings)
        return any(len(r) >= 3 and _inside(r, x, y) for r in f["rings"])

    on_site = [f for f in feats if touches(f)]
    hit = on_site[0] if on_site else None

    def tally(fs):
        d = {}
        for f in fs:
            g = f["eczm_grad"] or "?"
            d[g] = d.get(g, 0) + 1
        return dict(sorted(d.items()))

    site = tally(on_site)
    return {
        "등급": (hit or {}).get("eczm_grad") or GRADE_UNSET,
        "등급명": GRADE_LABEL.get((hit or {}).get("eczm_grad") or GRADE_UNSET, "?"),
        "폴리곤에_걸림": hit is not None,
        "식물군락": (hit or {}).get("plnt_cln_ttle", ""),
        "군락기호": (hit or {}).get("cln_symbl", ""),
        "사업지_등급분포": site,
        "주변_등급분포": tally(feats),
        # 보고서 문장이 묻는 것 — **사업지 기준**이다
        "사업지_1등급": "1" in site,
        "사업지_별도관리": GRADE_SPECIAL in site,
        "주변_1등급": "1" in tally(feats),
        "판정범위": "사업지 폴리곤" if site_rings else "중심점 1개",
        "피처수": len(feats),
    }


# ── 자체 검증 — 골든셋 ──────────────────────────────────────────────────────
ADDR = re.compile(r"[가-힣]+(?:시|군)\s?[가-힣]+(?:읍|면|동)\s?[가-힣]+리\s?산?\d+(?:-\d+)?")
GRADE = re.compile(r"생태[·・]?자연도\s*(\d)\s*등급|(\d)\s*등급으로\s*지정")


def self_test(root="golden/small-env"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import map_fetch as M
    files = sorted(glob.glob(f"{root}/*/regional-overview.txt"))
    if not files:
        print(f"[skip] 골든셋이 없습니다: {root}")
        return True
    ok = n = 0
    for f in files:
        name = os.path.basename(os.path.dirname(f))
        txt = open(f, encoding="utf-8").read()
        a, g = ADDR.search(txt), GRADE.search(txt)
        want = (g.group(1) or g.group(2)) if g else None
        if not a or not want:
            print(f"  [skip] {name:<12} 본문에서 "
                  f"{'주소' if not a else '등급'}를 못 찾았습니다")
            continue
        try:
            mx, my, _ = M.geocode(a.group(0))
        except Exception as e:
            print(f"  [skip] {name:<12} 지오코딩 실패 ({a.group(0)}) {e}")
            continue
        r = assess(*M.merc_to_lonlat(mx, my))
        n += 1
        good = r["등급"] == want
        ok += good
        print(f"  [{'OK  ' if good else 'MISS'}] {name:<12} 정답 {want}등급 · 판정 "
              f"{r['등급']}등급{'' if r['폴리곤에_걸림'] else ' (폴리곤 밖)'}"
              f" · 주변 {r['주변_등급분포']}")
    print(f"\n{ok}/{n} 일치")
    return ok == n


def main():
    ap = argparse.ArgumentParser(description="생태·자연도 — 베이스 이미지 + 등급 판정")
    ap.add_argument("--lonlat", nargs=2, type=float)
    ap.add_argument("--half-m", type=float, default=900)
    ap.add_argument("--size", type=int, default=768)
    ap.add_argument("--opaque", action="store_true", help="투명 배경 대신 흰 배경")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("-o", "--out", help="베이스 이미지 저장")
    a = ap.parse_args()

    if a.self_test or not a.lonlat:
        sys.exit(0 if self_test() else 1)

    r = assess(*a.lonlat, a.half_m)
    print(f"생태·자연도 {r['등급']}등급"
          f"{'' if r['폴리곤에_걸림'] else '  (폴리곤 밖 — 미지정이라 3등급으로 봅니다)'}")
    if r["식물군락"]:
        print(f"  식물군락 {r['식물군락']} ({r['군락기호']})")
    print(f"  판정 범위 {r['판정범위']} · 주변 등급 분포 {r['주변_등급분포']}"
          f" · 피처 {r['피처수']}개")
    print(f"  사업지 안 — 1등급 권역 {'분포함 ⚠️' if r['사업지_1등급'] else '분포하지 않음'}"
          f" · 별도관리지역 {'분포함 ⚠️' if r['사업지_별도관리'] else '분포하지 않음'}")
    if r["주변_1등급"] and not r["사업지_1등급"]:
        print("  (주변에는 1등급이 있습니다 — 보고서 문장은 사업지 기준입니다)")

    if a.out:
        im = wms(*a.lonlat, a.half_m, a.size, not a.opaque)
        im.save(a.out)
        print(f"→ {a.out}  {im.size}")


if __name__ == "__main__":
    main()

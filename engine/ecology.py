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
            # ⚠️ 태그에 속성이 붙어 온다 — `<gml:coordinates xmlns:gml=… cs="," ts=" ">`.
            #    닫힌 꺾쇠만 찾으면 그런 피처의 지오메트리를 통째로 놓친다 —
            #    별도관리지역이 전부 그 형태라 폴리곤이 하나도 안 잡힌다.
            for co in re.findall(r"<gml:coordinates[^>]*>(.*?)</gml:coordinates>", f, re.S)]
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


def _site_samples(site_rings, n=18):
    """사업지 안에 격자 표본점을 뿌린다 — 겹침을 '면적 비율' 로 재기 위해서.

    꼭짓점 포함 여부로 겹침을 판정하면 **경계가 스치기만 해도 걸린다.** 사업지(농경지)가
    숲(2등급) 가장자리에 붙어 있는 것이 보통이라, 지적도와 생태자연도의 경계선이 조금만
    어긋나도 가짜 겹침이 난다 (천안 실측). 표본점 비율이면 스침은 0~2% 로 떨어진다."""
    xs = [p[0] for r in site_rings for p in r]
    ys = [p[1] for r in site_rings for p in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pts = []
    for i in range(n):
        for j in range(n):
            x = x0 + (x1 - x0) * (i + 0.5) / n
            y = y0 + (y1 - y0) * (j + 0.5) / n
            if any(len(r) >= 3 and _inside(r, x, y) for r in site_rings):
                pts.append((x, y))
    return pts


def assess(lon, lat, half_m=900, site_rings=None, site_probes=()):
    """사업지 등급과 주변 분포 → 본문 서술에 그대로 들어가는 값.

    정답 문장은 이렇게 쓴다:
        "생태·자연도 3등급으로 지정되어 있으며, 1등급 권역 및 별도관리지역은
         분포하지 않는 것으로 조사되었다"

    ⚠️ **"분포하지 않는다"의 범위는 사업계획지구다.** 주변 1~2km 로 넓히면 1등급이
       흔히 잡힌다 (골든셋 7건 중 5건). `site_rings`(EPSG:5186 폴리곤)를 주면 그 안에서
       판정하고, 없으면 중심점 하나로 판정한다."""
    x, y = to_5186(lon, lat)
    feats = wfs(lon, lat, half_m)

    if site_rings:
        # 사업지 표본점 중 몇 % 가 등급 폴리곤에 덮이는가 — 스침(<10%)은 무시한다.
        # "분포하는가" 는 더 민감하게 본다 (2% — 일부라도 실제로 물리면 분포다).
        samples = _site_samples(site_rings)
        cover = []
        for f in feats:
            if not samples:
                break
            c = sum(1 for pt in samples
                    if any(len(r) >= 3 and _inside(r, *pt) for r in f["rings"]))
            frac = c / len(samples)
            if frac >= 0.02:
                cover.append((frac, f))
        cover.sort(key=lambda t: -t[0])
        # 판정 등급의 문턱은 25% — "사업지구는 N등급" 은 **주된 등급**을 말한다.
        # 정답들이 그렇게 판단한다: 평창은 2등급이 15% 덮여도 3등급으로 적었다.
        # (경계 디지털화 오차로 좁은 부지는 이웃 폴리곤이 10%대까지 침범해 보인다)
        # "분포하는가"(1등급·별도관리 경고)는 2% 부터 잡는다.
        on_site = [f for frac, f in cover if frac >= 0.25]
        present = [f for frac, f in cover]
        # 다등급 — 정답 문장은 "2, 3등급으로 지정" 처럼 **걸리는 등급을 다 나열한다**
        # (후평리 65% · 평창 15% 모두 2등급을 적었다). 나열 문턱은 "분포" 와 같은 2%.
        # 안 덮인 부분이 25% 넘으면 3등급(미지정)도 함께 적는다.
        grades = sorted({f["eczm_grad"] for frac, f in cover})
        # 저편입 필지 탐침 — 나열에만 넣고 주된 판정에는 안 넣는다
        for X, Y in site_probes:
            for f in feats:
                if any(len(r) >= 3 and _inside(r, X, Y) for r in f["rings"]):
                    grades = sorted(set(grades) | {f["eczm_grad"]})
                    break
        if 1 - sum(frac for frac, _ in cover) >= 0.25 or not grades:
            grades = sorted(set(grades) | {GRADE_UNSET})
    else:
        on_site = [f for f in feats
                   if any(len(r) >= 3 and _inside(r, x, y) for r in f["rings"])]
        present = on_site
    hit = on_site[0] if on_site else None

    def tally(fs):
        d = {}
        for f in fs:
            g = f["eczm_grad"] or "?"
            d[g] = d.get(g, 0) + 1
        return dict(sorted(d.items()))

    site = tally(present)
    if not site_rings:
        grades = [(hit or {}).get("eczm_grad") or GRADE_UNSET]
    return {
        "등급들": grades,
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


# ── 삽도 조립 — 정답과 같은 3층 ────────────────────────────────────────────
def compose(lon, lat, topo_png, res, center_px, alpha=0.34):
    """지형도 + 등급 채색 반투명 + 군락기호 → (합성 이미지, 라벨 요소들).

    정답 생태자연도가 이 3층이다. 채색만 있으면 등고선·마을이 안 보이고,
    지형도만 있으면 등급이 없다.

    ⚠️ 채색 투명도를 45% 로 하니 **등고선·지명이 눌려 죽었다** — 34% 가 정답의 느낌이다.
       군락기호도 지명보다 크면 코드가 지도를 덮은 것처럼 보인다. 기호는 작게(26),
       지명은 `admin` 낱자 박스로 따로 얹는 것이 정답 구성이다.

    ⚠️ 좌표계 정합이 관건이다 — 지형도는 EPSG:5179 타일인데 EcoBank 는 5186 이 기본이다.
       **WMS 가 5179 bbox 도 받아 준다.** 지형도 캔버스의 5179 bbox 를 역산해 같은
       크기로 받으면 픽셀이 정확히 맞는다. 근사 재투영이 필요 없다.

    `topo_png`/`res`/`center_px` 는 map_fetch 가 지형도를 줄 때 나온 값 그대로다
    (res = m_per_px)."""
    import math, urllib.request
    from PIL import Image
    from pyproj import Transformer

    base = Image.open(topo_png).convert("RGBA")
    W, H = base.size
    cx_px, cy_px = center_px
    X, Y = Transformer.from_crs("EPSG:4326", "EPSG:5179",
                                always_xy=True).transform(lon, lat)
    left, top = X - cx_px * res, Y + cy_px * res

    q = {"ServiceKey": _key(), "srs": "EPSG:5179",
         "bbox": f"{left},{top - H * res},{left + W * res},{top}",
         "width": str(W), "height": str(H), "format": "image/png",
         "transparent": "true"}
    d = urllib.request.urlopen(f"{BASE}/wms/getEcologyzmpWMS?"
                               + urllib.parse.urlencode(q), timeout=60).read()
    ov = Image.open(io.BytesIO(d)).convert("RGBA")
    ov.putalpha(ov.getchannel("A").point(lambda v: int(v * alpha)))
    base.alpha_composite(ov)

    # 군락기호 라벨 — WFS(5186) 폴리곤 중심을 5179 픽셀로 옮긴다
    tr = Transformer.from_crs("EPSG:5186", "EPSG:5179", always_xy=True)
    els, seen = [], []
    half = max(W, H) * res / 2 + 200
    for f in wfs(lon, lat, half):
        sym = f["cln_symbl"]
        ring = max(f["rings"], key=len, default=None)
        if not sym or not ring or len(ring) < 8:
            continue
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        x, y = tr.transform(cx, cy)
        px, py = (x - left) / res, (top - y) / res
        if not (40 < px < W - 40 and 40 < py < H - 40):
            continue
        if any(math.dist((px, py), s) < 150 for s in seen):
            continue
        seen.append((px, py))
        els.append({"type": "place", "at": [round(px, 1), round(py, 1)],
                    "text": sym, "size": 26})
    return base.convert("RGB"), els


# ── 자체 검증 — 골든셋 ──────────────────────────────────────────────────────
# 사업지 주소 표기가 사업마다 다르다 —
#   `천안시 동남구 동면 화덕리 31-1`  ← 시와 읍면 사이에 **구**가 낀다
#   `옥천군 군서면 사양리 산 39-1`    ← `산` 뒤에 **공백**이 온다
#   `천안시 동남구 동면 화덕리 31-1`  ← 읍면 이름이 **한 글자**일 수 있다 (동면)
ADDR = re.compile(r"[가-힣]{1,5}(?:시|군)\s?(?:[가-힣]{1,3}구\s?)?"
                  r"[가-힣]{1,5}(?:읍|면|동)\s?[가-힣]{1,5}리\s?(?:산\s?)?\d+(?:-\d+)?")
# ⚠️ 등급이 **여러 개**일 수 있다 — 후평리 정답은 "2, 3등급으로 지정" 이다.
#    한 자리만 집는 정규식은 뒤의 3만 가져와 정답을 왜곡한다. 실제로 그 함정에 빠져
#    후평리를 "정답 3등급" 으로 잘못 읽고 자료 차수 문제를 의심했었다.
#    문구 변형도 있다 — "3등급으로 지정"(대부분) · "3등급 권역으로 확인"(충주).
GRADE = re.compile(r"생태[·・]?자연도[는은]?\s*([\d,\s]+?)\s*등급(?:으로\s*지정|\s*권역으로)")


def _site_rings(name, lon, lat):
    """사업개요의 편입토지조서로 사업지 폴리곤(EPSG:5186)을 만든다. 없으면 None."""
    import parcels as P
    from pyproj import Transformer
    for path in (f"cases/small-env/{name}/input/사업개요.txt",
                 f"raw_data/{name}/사업개요.txt"):
        if not os.path.exists(path):
            continue
        rows, err, _ = P.parse_survey(open(path, encoding="utf-8").read())
        if err:
            return None, []
        code, e2 = P.bjd_code(lon, lat)
        if not code:
            return None, []
        pc, _ = P.fetch(rows, code)
        tr = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True)
        # ⚠️ 편입률이 낮은 필지는 **모양에서 뺀다** — 원주 산59-1 은 임야 184,166㎡ 중
        #    23㎡(0.01%)만 편입인데, 필지 전체 링을 쓰면 사업지가 거대한 숲으로 둔갑한다.
        rings = [[tr.transform(x, y) for x, y in ring]
                 for p in pc if p["편입률"] >= 0.5 for ring in p["rings"]]
        # 대신 그 필지의 **사업지와 맞닿은 경계 지점**을 탐침으로 남긴다.
        # 편입 조각은 반드시 사업지에 붙어 있으므로, 접점의 등급이 곧 조각의 등급이다.
        #
        # ⚠️ 단, **임야 조각만** 본다. 골든셋이 여기서 갈린다(1:1) — 원주는 임야 23㎡
        #    조각의 2등급을 나열했고, 천안은 구거 15㎡ 조각의 등급을 나열하지 않았다.
        #    임야는 숲이라 등급이 있을 소지가 크고 구거·도로 조각은 등급성이 없다는
        #    기제로 가르지만, 관측이 1:1 이라 규칙으로 굳힌 것은 아니다.
        # 조각이 본체와 **직접 안 닿을 수도 있다** — 원주는 사이에 또 다른 조각(579-1 전)이
        # 끼어 산59-1 이 본체에서 40m 넘게 떨어져 보였다. 반경 컷 대신
        # **본체에 가장 가까운 꼭짓점 몇 개**를 짚으면 연쇄 조각도 덮는다.
        import math
        probes = []
        body = [pt for r in rings for pt in r]
        for p_ in pc:
            if p_["편입률"] >= 0.5 or not p_["소계"] or p_["지목"] != "임":
                continue
            verts = [tr.transform(x, y) for ring in p_["rings"] for x, y in ring]
            verts.sort(key=lambda v: min(math.dist(v, b) for b in body))
            probes += verts[:5]
        return (rings or None), probes
    return None, []
    return None


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
        g = GRADE.search(txt)
        want = set(re.findall(r"\d", g.group(1))) if g else None
        # ⚠️ 본문 첫 지번이 사업지라는 보장이 없다 — 문화재·보호수 위치가 먼저 나온다.
        #    폴더 이름의 **리 이름과 맞는 주소만** 쓴다 (옥천 사양리인데 우산리를 잡았다).
        ri = name.split("_")[-1]
        a = next((m for m in ADDR.finditer(txt) if ri in m.group(0)), None)
        if not a or not want:
            print(f"  [skip] {name:<12} 본문에서 "
                  f"{'사업지 주소(' + ri + ')' if not a else '등급'}를 못 찾았습니다")
            continue
        try:
            mx, my, _ = M.geocode(a.group(0))
        except Exception as e:
            print(f"  [skip] {name:<12} 지오코딩 실패 ({a.group(0)}) {e}")
            continue
        lon, lat = M.merc_to_lonlat(mx, my)
        # 사업개요(편입토지조서)가 있으면 **사업지 폴리곤 겹침**으로 판정한다 —
        # 실전 경로와 같다. 없으면 중심점 하나로 떨어진다.
        site, probes = _site_rings(name, lon, lat)
        r = assess(lon, lat, site_rings=site, site_probes=probes)
        n += 1
        got = set(r["등급들"])
        good = got == want
        ok += good
        print(f"  [{'OK  ' if good else 'MISS'}] {name:<12} 정답 {','.join(sorted(want))}등급"
              f" · 판정 {','.join(sorted(got))}등급 ({r['판정범위']})"
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

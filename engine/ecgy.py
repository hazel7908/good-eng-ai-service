#!/usr/bin/env python3
"""
생태·경관보전지역 — 지정 여부·이격거리·삽도 채색.

지역개황 §가 의 첫 절이다. 정답 문장은 두 꼴로 갈린다:

    없을 때  "괴산군은 …상 생태·경관보전지역의 지정현황이 없는 것으로 조사되었다"
    있을 때  "평창군은 …상 생태·경관보전지역이 1개소 지정되어 있으며,
             사업계획지구로부터 1.04km 이격하여 위치하는 것으로 조사되었다"

골든셋 8건 중 7건이 "없음", 1건(평창)만 "있음" 이다. 그래서 **지역 특수 항목**이다 —
있을 때만 지역개황도에 구역을 채색하고 지정현황 표를 넣는다.

출처는 공공데이터포털 `해양수산부_생태경관보전지역` WFS 다. 이름이 해수부인데
내용은 내륙 구역(동강유역·지리산…)까지 담고 있다. 키는 EcoBank 와 **같은 계정 키**라
`~/.ecobank.env` 를 그대로 읽는다 (공공데이터포털은 계정당 인증키가 하나다).

    python engine/ecgy.py --self-test          # 골든셋 검증
    python engine/ecgy.py --lonlat 128.5697 37.3095 --sigungu 평창군

⚠️ **bbox 파라미터가 먹지 않는다** (넣으면 0건이 온다). 전량(10건)을 받아 로컬에서
   자른다. 전국 자료라 오히려 이 편이 "시군 안에 있는가" 판정에 맞다.

⚠️ **시·도 지정분이 빠져 있다.** 환경부 지정현황은 33개소인데 이 API 는 10건뿐이다
   (국가 지정분 + 서울시 3개소). 나머지는 별도 데이터셋 `해양수산부_시도생태경관보전지역`
   이다 — 미발급이면 **"없음" 판정이 불완전**하다.

⚠️ **면적은 API 로 재계산하지 않는다.** 동강유역 폴리곤 순면적은 94.99㎢ 인데 정답
   표는 79.259㎢ 다. 표의 면적·특징·지정일자는 환경부 지정현황 표에서 와야 한다.
"""
import argparse, json, math, os, re, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ⚠️ 데이터셋이 둘인데 **`생태경관보전지역` 하나가 전국 33개소 전량**이다 —
#    이름은 국가분 같지만 시·도 지정분(관악산·남산·태화강…)까지 다 들어 있고,
#    환경부 "생태·경관보전지역 지정 현황" 33개소와 건수가 맞는다.
#    `시도생태경관보전지역`(24건, `apVhdService_SidoEcolandscapeV2`)은 **쓰지 않는다** —
#    그 33건의 부분집합이라 합치면 같은 구역을 두 번 세고, 속성도 못 쓴다
#    (지정연도가 전부 `1892`, 관리기관이 광양백운산인데 서울시). 다시 뒤지지 말 것.
URL = ("https://apis.data.go.kr/1192000/apVhdService_EcgyScenePresvArea"
       "/getOpnEcgyScenePresvAreaWFS")
CACHE_DIR = os.path.join(ROOT, "raw_data/cache")
CRS = "EPSG:5179"                                   # WFS 가 이 좌표계로 준다

# ⚠️ **`maxFeatures` 를 빠뜨리면 조용히 10건만 온다.** 기본 상한이 10 이고 경고가 없다 —
#    처음에 이걸 모르고 10건으로 검증해 8/8 을 받았다. 33건으로 다시 재도 8/8 이었지만,
#    맞은 것은 우연에 가깝다. `numOfRows`·`pageNo` 는 이 API 에서 아무 효과가 없다.
MAX_FEATURES = "1000"


def _key():
    path = os.path.expanduser("~/.ecobank.env")
    if not os.path.exists(path):
        sys.exit("~/.ecobank.env 가 없습니다 — 공공데이터포털 인증키")
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("ECOBANK_API_KEY"):
            return urllib.parse.unquote(line.split("=", 1)[1].strip().strip("'\""))
    sys.exit("~/.ecobank.env 에 ECOBANK_API_KEY 가 없습니다")


def _parse(xml, kind):
    """WFS GML → [{'name', 'kind', 'rings'(외곽), 'holes'(구멍)}]. 좌표는 EPSG:5179.

    ⚠️ 피처 태그가 곧 레이어 이름이라 **데이터셋마다 다르다** (`opn_ecgy_scene_presv_area_a`
       ↔ 시도판). featureMember 로 싸여 오지도 않는다. 그래서 태그를 고정하지 않고
       `ofbd-DB:*` 중 **이름 필드를 가진 것**을 피처로 본다."""
    out = []
    for m in re.finditer(r"<ofbd-DB:([a-zA-Z_]+)[\s>]", xml):
        tag = m.group(1)
        if not tag.endswith("_a"):                  # 면 레이어만 (`_a` = area)
            continue
        end = xml.find(f"</ofbd-DB:{tag}>", m.end())
        if end < 0:
            continue
        f = xml[m.end():end]
        # 이름 필드가 데이터셋마다 다르다 — `area_nm` ↔ `..._krnm`(한글명).
        # ⚠️ 영문명(`..._ennm`)이 먼저 나오는 자리가 있어 **한글명을 먼저 찾는다**.
        nm = (re.search(r"<ofbd-DB:(?:\w*krnm|area_nm)>(.*?)</ofbd-DB:", f, re.S)
              or re.search(r"<ofbd-DB:\w*nm>(.*?)</ofbd-DB:", f, re.S))
        rec = {"name": nm.group(1).strip() if nm else "", "kind": kind,
               "rings": [], "holes": []}
        for gk, key in (("exterior", "rings"), ("interior", "holes")):
            for blk in re.findall(rf"<gml:{gk}>(.*?)</gml:{gk}>", f, re.S):
                for pl in re.findall(r"<gml:posList[^>]*>(.*?)</gml:posList>",
                                     blk, re.S):
                    v = [float(t) for t in pl.split()]
                    rec[key].append(list(zip(v[0::2], v[1::2])))
        if rec["rings"]:
            out.append(rec)
    return out


def _wfs(url, cache, refresh):
    if refresh or not os.path.exists(cache):
        q = {"ServiceKey": _key(), "maxFeatures": MAX_FEATURES}
        d = urllib.request.urlopen(url + "?" + urllib.parse.urlencode(q),
                                   timeout=200).read().decode("utf-8", "replace")
        os.makedirs(CACHE_DIR, exist_ok=True)
        open(cache, "w", encoding="utf-8").write(d)
        return d
    return open(cache, encoding="utf-8").read()


def fetch(refresh=False):
    """전국 지정구역 33개소 → [{'name', 'kind', 'rings'(외곽), 'holes'(구멍)}]."""
    return _parse(_wfs(URL, os.path.join(CACHE_DIR, "ecgy.xml"), refresh), "전국")


def _seg_dist(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _inside(ring, x, y):
    c, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def _bbox(rings):
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return min(xs), min(ys), max(xs), max(ys)


def distance(site_rings, area):
    """사업지 ↔ 지정구역 최단거리(m). 겹치면 0. 좌표는 둘 다 EPSG:5179."""
    spts = [p for r in site_rings for p in r]
    for ring in area["rings"]:
        if any(_inside(ring, *p) for p in spts):
            return 0.0
    best = float("inf")
    # 양방향으로 잰다 — 한쪽 꼭짓점만 보면 긴 변을 가로지르는 최근접을 놓친다
    for ring in area["rings"]:
        for i in range(len(ring)):
            a, b = ring[i - 1], ring[i]
            for p in spts:
                best = min(best, _seg_dist(p, a, b))
    for ring in site_rings:
        for i in range(len(ring)):
            a, b = ring[i - 1], ring[i]
            for r in area["rings"]:
                for p in r:
                    best = min(best, _seg_dist(p, a, b))
    return best


def in_region(areas, boundary):
    """시군 경계 안(또는 걸친) 지정구역만 — 정답 문장이 **시군 단위**로 세기 때문이다.

    "평창군은 … 1개소 지정되어 있으며" 의 1개소가 이 값이다."""
    out, rb = [], _bbox(boundary)
    for a in areas:
        ab = _bbox(a["rings"])
        if ab[2] < rb[0] or ab[0] > rb[2] or ab[3] < rb[1] or ab[1] > rb[3]:
            continue
        # 꼭짓점을 7 개마다 성기게 훑는다 — 구역 하나가 링 390 개짜리(동강)라
        # 전수로 보면 느리고, 시군 대 구역은 크기 차가 커서 이 정도로 갈린다
        hit = any(_inside(br, *p) for br in boundary
                  for ring in a["rings"] for p in ring[::7])
        if not hit:
            hit = any(_inside(ring, *p) for ring in a["rings"]
                      for br in boundary for p in br[::7])
        if hit:
            out.append(a)
    return out


def region_rings(sigungu, lon, lat, half_deg=0.35):
    """시군 경계 폴리곤(EPSG:5179). 못 찾으면 (None, 사유).

    ⚠️ VWorld 의 시군구 이름은 **특례시에서 구까지 붙는다** — `천안시동남구` ·
       `청주시청원구`. 정답 문장은 `천안시는…` 이라 접두로 맞추고 구를 모두 합친다."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import admin as A
    from pyproj import Transformer
    to5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    regs, err = A.fetch("시군구", lon, lat, half_deg)
    cand = [r for r in regs if r["name"].startswith(sigungu)]
    if not cand:
        return None, f"시군 경계를 못 찾았습니다 ({sigungu}) {err or ''}"
    return [[to5179.transform(*p) for p in ring]
            for r in cand for ring in r["rings"]], None


def assess(site_rings, boundary, refresh=False):
    """본문 서술에 그대로 들어가는 값.

    반환 {'개소', '지역명', '이격거리_m', '문장'}"""
    hit = in_region(fetch(refresh), boundary)
    if not hit:
        return {"개소": 0, "지역명": [], "이격거리_m": None,
                "문장": "생태·경관보전지역의 지정현황이 없는 것으로 조사되었다"}
    d = min(distance(site_rings, a) for a in hit)
    # 사업지가 점 하나면 이격거리는 **근사**다 — 평창은 중심점 1.20km ↔ 폴리곤 1.04km(정답).
    approx = sum(len(r) for r in site_rings) < 3
    return {"개소": len(hit), "지역명": [a["name"] for a in hit],
            "이격거리_m": round(d, 1),
            **({"⚠️": "중심점 기준 근사 — 편입토지조서로 사업지 폴리곤을 주십시오"}
               if approx else {}),
            "문장": f"생태·경관보전지역이 {len(hit)}개소 지정되어 있으며, 사업계획지구로부터 "
                    f"{d/1000:.2f}km 이격하여 위치하는 것으로 조사되었다"}


def to_elements(areas, center_5179, center_px, px_per_m, canvas=None,
                min_px=6.0, color=None):
    """지정구역 → `figure_overlay` 의 `zone` 요소. 있을 때만 채색한다.

    `zone` 규약은 **링 하나에 요소 하나**다 (`points`). 라벨은 구역마다 첫 링에만 단다.
    동강유역은 링이 390 개라 화면 밖·티끌 조각은 버린다 — 안 그러면 삽도가 무거워지고
    지도 밖 여백에 점이 찍힌다."""
    cx, cy = center_5179
    ox, oy = center_px
    els = []
    for a in areas:
        first = True
        for ring in a["rings"]:
            pts = [[round(ox + (x - cx) * px_per_m, 1),
                    round(oy - (y - cy) * px_per_m, 1)] for x, y in ring]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if max(xs) - min(xs) < min_px and max(ys) - min(ys) < min_px:
                continue
            if canvas:
                w, h = canvas
                if max(xs) < 0 or min(xs) > w or max(ys) < 0 or min(ys) > h:
                    continue
            el = {"type": "zone", "points": pts}
            if color:
                el["color"] = list(color)
            if first:
                el["label"] = a["name"]
                first = False
            els.append(el)
    return els


# ─────────────────────────────────────────────────────────────── 검증

# 골든셋 8건 — (사업, 주소, 시군, 정답 개소, 정답 이격 km)
GOLDEN = [
    ("평창_수청리", "강원특별자치도 평창군 미탄면 수청리 73", "평창군", 1, 1.04),
    ("괴산_금신리", "충청북도 괴산군 청안면 금신리 155-1", "괴산군", 0, None),
    ("괴산_후평리", "충청북도 괴산군 청천면 후평리 산1", "괴산군", 0, None),
    ("옥천_사양리", "충청북도 옥천군 군서면 사양리 산39-1", "옥천군", 0, None),
    ("원주_무장리", "강원특별자치도 원주시 호저면 무장리 578", "원주시", 0, None),
    ("천안_화덕리", "충청남도 천안시 동남구 동면 화덕리 30", "천안시", 0, None),
    ("청주_호명리", "충청북도 청주시 청원구 북이면 호명리 430", "청주시", 0, None),
    ("충주_율능리", "충청북도 충주시 엄정면 율능리 91-2", "충주시", 0, None),
]


def _site_rings_평창():
    """평창 사업지 폴리곤(EPSG:5179) — 편입토지조서 → 연속지적도.

    ⚠️ 이 한 건이 **유일한 양성 사례**다. 골든셋 8건 중 7건이 "없음" 이라
       개소 판정만으로는 *항상 0 을 내는 버그*도 7/8 을 통과한다 (생태자연도에서
       같은 착시에 데었다). 그래서 거리까지 재서 정답 1.04km 와 맞춘다."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import parcels as P, map_fetch as M
    from pyproj import Transformer
    txt_path = os.path.join(ROOT, "raw_data/평창_수청리/사업개요.txt")
    if not os.path.exists(txt_path):
        return None
    rows, _, _ = P.parse_survey(open(txt_path, encoding="utf-8").read())
    x, y, _ = M.geocode("강원특별자치도 평창군 미탄면 수청리 73")
    lon, lat = Transformer.from_crs("EPSG:3857", "EPSG:4326",
                                    always_xy=True).transform(x, y)
    code, err = P.bjd_code(lon, lat)
    if err:
        return None
    to5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    return [[to5179.transform(*pt) for pt in ring]
            for pc in P.fetch(rows, code)[0] for ring in pc["rings"]]


def self_test():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import map_fetch as M
    from pyproj import Transformer
    to4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    to5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    areas = fetch()
    print(f"지정구역 {len(areas)}건 — {', '.join(a['name'] for a in areas)}\n")

    ok = 0
    for site, addr, sigungu, n_ans, km_ans in GOLDEN:
        x, y, _ = M.geocode(addr)
        lon, lat = to4326.transform(x, y)
        rr, err = region_rings(sigungu, lon, lat)
        if rr is None:
            print(f"  ✗ {site:<12} {err}")
            continue
        # 개소 판정에는 사업지 폴리곤이 필요 없다 — 중심점으로 대신한다.
        # 이격거리는 **폴리곤으로 재야 정답과 맞는다** (평창: 중심점 1.20 ↔ 폴리곤 1.04)
        res = assess([[to5179.transform(lon, lat)]], rr)
        mark = "○" if res["개소"] == n_ans else "✗"
        ok += res["개소"] == n_ans
        extra = f" · {res['지역명']}" if res["개소"] else ""
        print(f"  {mark} {site:<12} 개소 {res['개소']} (정답 {n_ans}){extra}")
    print(f"\n개소 판정 {ok}/{len(GOLDEN)}")

    # 유일한 양성 사례의 이격거리 — 여기가 실제로 무언가를 증명하는 자리다
    site = _site_rings_평창()
    if site is None:
        print("  [skip] 평창 이격거리 — raw_data 인풋이 없습니다")
        return ok == len(GOLDEN)
    dong = next(a for a in areas if a["name"] == "동강유역")
    km = distance(site, dong) / 1000
    good = abs(km - 1.04) < 0.005
    print(f"  {'○' if good else '✗'} 평창 이격거리 {km:.2f}km (정답 1.04km)")
    return ok == len(GOLDEN) and good


def main():
    ap = argparse.ArgumentParser(description="생태·경관보전지역")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="WFS 캐시 갱신")
    ap.add_argument("--lonlat", nargs=2, type=float)
    ap.add_argument("--sigungu", help="시군구 이름 (예: 평창군)")
    ap.add_argument("--survey", help="편입토지조서 텍스트 — 이격거리를 사업지 폴리곤으로 잰다")
    a = ap.parse_args()

    if a.self_test:
        sys.exit(0 if self_test() else 1)
    if a.refresh and not a.lonlat:
        print(f"지정구역 {len(fetch(True))}건 → {CACHE_DIR}")
        return
    if not (a.lonlat and a.sigungu):
        ap.error("--lonlat 과 --sigungu 가 필요합니다")

    from pyproj import Transformer
    to5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    lon, lat = a.lonlat
    rr, err = region_rings(a.sigungu, lon, lat)
    if rr is None:
        sys.exit(err)
    site = [[to5179.transform(lon, lat)]]
    if a.survey:
        import parcels as P
        rows, _, _ = P.parse_survey(open(a.survey, encoding="utf-8").read())
        code, e2 = P.bjd_code(lon, lat)
        if e2:
            sys.exit(e2)
        site = [[to5179.transform(*pt) for pt in ring]
                for pc in P.fetch(rows, code)[0] for ring in pc["rings"]]
    res = assess(site, rr, a.refresh)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

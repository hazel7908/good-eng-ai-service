#!/usr/bin/env python3
"""
편입토지조서 → 사업지 경계 폴리곤.

사업개요에는 **편입토지조서**가 있다. 어느 필지가 얼마나 사업에 들어가는지 적은 표다.

    구분  지번   지목  지적면적  사업부지  진출입로  소계   비고
    금신리 153   전    3,157     670      -       670   기허가
          155-1 답    1,246     903      -       903   금회증설

이 표의 **지번만 있으면 필지 경계를 국가 자료에서 받아올 수 있다** — VWorld 연속지적도다.
그림에 폴리곤을 그리려고 설계도서(dwg)를 기다릴 필요가 없다.

    주소 → 지오코딩 → 좌표 → 필지 1건 조회 → **법정동코드** → 조서 지번과 붙여 PNU → 폴리곤

`비고` 열이 정답 삽도의 **구역 구분**이다. 증설 사업은 기허가지와 금회 부지를 다른 색으로
그린다 (증설·변경 7건 중 6건).

⚠️ **색과 이름은 회사 표준이 없다 — 사업마다 다르다.** 기허가지가 파랑 3 : 빨강 1,
   범례 문구는 6건이 전부 다르다 (`금회사업부지`·`금회증설 부지`·`공장증설부지`…).
   그래서 여기서 정하지 않고 **`vars` 에서 받는다.** 기본값은 다수를 따라 금회 빨강 ·
   기허가 파랑이다. → `docs/20260819_삽도_자동화.md` §4-3 표

   구분을 유지해야 하는 진짜 이유는 색이 아니라 **계산**이다. 증설 3건 모두 이격거리와
   작업량을 **금회 부지 기준**으로 낸다 (3/3). 두 폴리곤은 따로 나와야 한다.

⚠️ **필지 경계는 사업지 경계와 같지 않다.** 조서의 `사업부지` 면적이 `지적면적` 보다 작으면
   필지 일부만 들어간다는 뜻이라, 필지 전체를 그리면 **실제보다 넓게** 그려진다.
   편입률을 함께 계산해 낮은 필지에는 경고를 단다. 정확한 경계는 설계도서라야 한다.

검증: `python engine/parcels.py --self-test`
"""
import argparse, glob, itertools, json, os, re, sys, urllib.parse, urllib.request

VWORLD_DATA = "https://api.vworld.kr/req/data"
CADASTRE = "LP_PA_CBND_BUBUN"          # 연속지적도
DOMAIN = "http://localhost"

# 지번은 `산` 이 붙을 수 있다 — 임야다 (원주 산59-1). PNU 의 산여부 자리가 달라진다.
JIBUN = re.compile(r"(산)?(\d{1,5})(?:-(\d{1,4}))?")
# HWP 표를 텍스트로 뽑으면 ㎡ 가 깨져 숫자에 들러붙는다 — `2,737浵ࡦ` (청양)
NUM = re.compile(r"^-$|^[\d,]+(?:\.\d+)?")


def _n(s):
    s = s.strip()
    if s == "-":
        return 0
    m = NUM.match(s)
    return float(m.group(0).replace(",", "")) if m and m.group(0) != "-" else None


def _cols(lines):
    """헤더에서 **숫자 열이 몇 개인지** 읽는다 — 첫 짐작일 뿐이다.

    조서 서식이 사업마다 다르다. 4열(지적면적·사업부지·진출입로·소계)이 흔하고
    여주는 2열(지적면적·편입면적)이다. 열 수를 모르면 비고의 `-` 를 숫자로 먹는다.
    **마지막 숫자 열이 언제나 사업에 편입되는 면적**이라 그것만 쓰면 된다.

    ⚠️ 헤더가 다층이면 이 계산이 어긋난다 — 평창은 공동 사업이라 편입면적 아래에
       **사업자별 열 3개 + 계**가 더 붙는데, 헤더 줄에서는 `편입면적` 다음이 바로
       `비고` 라 2열로 보인다. 그래서 `parse_survey` 가 **합계 행과 맞는 열 수를
       골라** 이 짐작을 바로잡는다."""
    try:
        i, j = lines.index("지목"), lines.index("비고")
    except ValueError:
        return 4
    return max(2, j - i - 1)


def _scan(lines, n):
    """숫자 열이 n 개라고 보고 필지를 훑는다."""
    rows, k = [], 0
    while k < len(lines):
        m = JIBUN.fullmatch(lines[k])
        # 지번 → 지목(한 글자) → 숫자 n 개 → 비고
        if m and k + n + 2 < len(lines) and re.fullmatch(r"[가-힣]", lines[k + 1]):
            nums = [_n(lines[k + 2 + t]) for t in range(n)]
            if all(v is not None for v in nums):
                rows.append({
                    "지번": lines[k], "지목": lines[k + 1],
                    "산": bool(m.group(1)),
                    "지적면적": nums[0], "소계": nums[-1],
                    "비고": lines[k + 2 + n],
                })
                k += n + 3
                continue
        k += 1
    return rows


def parse_survey(text):
    """편입토지조서 → 필지 목록. HWP 표라 셀이 한 줄씩 떨어져 나온다."""
    i = text.find("편입토지조서")
    if i < 0:
        return [], "편입토지조서를 찾지 못했습니다", None
    seg = text[i:]
    end = seg.find("합계")     # ⚠️ `소계` 는 열 이름으로도 쓰여 끝 표시어가 못 된다
    body, tail = (seg[:end], seg[end:end + 260]) if end > 0 else (seg, "")
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    guess = _cols(lines)
    tail_nums = [_n(x) for x in tail.split("\n")[1:12]] if tail else []
    tail_nums = [v for v in tail_nums if v is not None]

    def total_for(n):
        return tail_nums[n - 1] if len(tail_nums) >= n else (
            tail_nums[-1] if tail_nums else None)

    # 짐작한 열 수부터 넓혀 가며 **합계 행과 맞는 것**을 고른다.
    # 서식 변이를 일일이 따라가는 대신 조서가 스스로 검산하게 한다.
    best = cand = None
    for n in [guess] + [c for c in range(2, 8) if c != guess]:
        rows = _scan(lines, n)
        if not rows:
            continue
        t = total_for(n)
        if t is not None and abs(sum(r["소계"] for r in rows) - t) < 2:
            return rows, None, t              # 합계 행과 맞으면 그것으로 확정
        if best is None:
            best = (rows, t)
        # 합계 행이 없는 조서도 있다 (평창은 `소계` 로 끝내고 진출입로 블록이 또 붙는다).
        # 그럴 때는 **편입면적이 0 인 필지가 없는** 쪽을 고른다 —
        # 편입되지 않는 필지를 조서에 올릴 이유가 없기 때문이다.
        if cand is None and all(r["소계"] > 0 for r in rows) and len(rows) > 1:
            cand = (rows, t)
    if cand:
        return cand[0], None, cand[1]
    if best is None:
        return [], "조서에서 필지를 읽지 못했습니다", None
    return best[0], None, best[1]


def survey_address(text):
    """조서 머리에 적힌 **지역명 + 첫 지번** → 지오코딩용 주소.

    조서는 `구분` 열에 시군·읍면·리를 한 줄씩 적는다. 본문 첫 줄의 사업명에서
    뽑는 것보다 이쪽이 견고하다 — 사업명 표기가 제각각이다."""
    rows, err, _ = parse_survey(text)
    if err:
        return None
    i = text.find("편입토지조서")
    lines = [l.strip() for l in text[i:].split("\n") if l.strip()]
    try:
        start = lines.index("비고") + 1
    except ValueError:
        return None
    area = []
    for l in lines[start:start + 6]:
        if re.fullmatch(r"[가-힣]+(?:시|군|구|읍|면|동|리)", l):
            area.append(l)
        elif area:
            break
    return " ".join(area + [rows[0]["지번"]]) if area else None


def _get(**kw):
    key = _key()
    p = {"service": "data", "request": "GetFeature", "data": CADASTRE, "key": key,
         "domain": DOMAIN, "format": "json", "size": "100", "crs": "EPSG:4326"}
    p.update(kw)
    r = json.loads(urllib.request.urlopen(
        f"{VWORLD_DATA}?{urllib.parse.urlencode(p)}", timeout=25).read())
    res = r.get("response", {})
    if res.get("status") != "OK":
        return [], res.get("error", {}).get("text", res.get("status"))
    return res.get("result", {}).get("featureCollection", {}).get("features", []), None


def _key():
    path = os.path.expanduser("~/.vworld.env")
    if not os.path.exists(path):
        sys.exit("~/.vworld.env 가 없습니다 (VWORLD_API_KEY)")
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("VWORLD_API_KEY"):
            return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("~/.vworld.env 에 VWORLD_API_KEY 가 없습니다")


def bjd_code(lon, lat):
    """좌표 → 법정동코드. 그 자리 필지를 하나 집어 PNU 앞 10자리를 뗀다."""
    fs, err = _get(geomFilter=f"POINT({lon} {lat})", size="1")
    if err or not fs:
        return None, err or "그 좌표에 필지가 없습니다"
    return fs[0]["properties"]["pnu"][:10], None


def pnu_of(code, jibun, san=False):
    """법정동코드 + 지번 → PNU 19자리 (코드10 + 산여부1 + 본번4 + 부번4)."""
    m = JIBUN.fullmatch(jibun.strip())
    if not m:
        return None
    san = san or bool(m.group(1))
    return f"{code}{2 if san else 1}{int(m.group(2)):04d}{int(m.group(3) or 0):04d}"


def _rings(geom):
    """폴리곤 하나든 여럿이든 바깥 링을 전부 모은다 — 필지가 조각나 있을 수 있다."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def area_m2(ring):
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True)
    p = [tr.transform(x, y) for x, y in ring]
    return abs(sum(p[i][0] * p[i - 1][1] - p[i - 1][0] * p[i][1]
                   for i in range(len(p)))) / 2


def fetch_bonbun(code, jibun):
    """본번 계열을 통째로 받는다 — `155` 를 넣으면 155·155-1·155-2… 가 다 온다.

    **이미 시행된 사업**은 지적이 갈라져 조서 지번이 그대로 없다. 그럴 때 본번 계열을 다
    합치면 조서의 지적면적과 다시 맞는다 (괴산 4개 본번 모두 ±1%)."""
    m = JIBUN.fullmatch(jibun.strip())
    if not m:
        return []
    pre = f"{code}{2 if m.group(1) else 1}{int(m.group(2)):04d}"
    fs, _ = _get(attrFilter=f"pnu:like:{pre}", geometry="true")
    return fs


def fetch(rows, code, expand=False):
    """조서 필지들의 경계를 받아 온다. 지적면적과 대조해 **스스로 검증**한다."""
    out, warn = [], []
    seen = set()
    for r in rows:
        pnu = pnu_of(code, r["지번"], r.get("산", False))
        fs, err = _get(attrFilter=f"pnu:=:{pnu}", geometry="true")
        if err or not fs:
            warn.append(f"{r['지번']} — 필지를 찾지 못했습니다 ({err or 'PNU ' + pnu})")
            continue
        rings = [g for f in fs for g in _rings(f["geometry"])]
        got = sum(area_m2(g) for g in rings)
        off = r["지적면적"] and abs(got - r["지적면적"]) > r["지적면적"] * 0.10
        if off and expand:
            # 갈라진 사업 — 본번 계열을 통째로 받아 메운다. 중복은 PNU 로 막는다.
            fs2 = [f for f in fetch_bonbun(code, r["지번"])
                   if f["properties"]["pnu"] not in seen]
            if fs2:
                seen.update(f["properties"]["pnu"] for f in fs2)
                rings = [g for f in fs2 for g in _rings(f["geometry"])]
                got = sum(area_m2(g) for g in rings)
                off = abs(got - r["지적면적"]) > r["지적면적"] * 0.10
                warn.append(f"{r['지번']} — 지적이 갈라져 본번 계열 {len(fs2)}필지로 대신했습니다"
                            f" ({got:,.0f}㎡ ↔ 조서 {r['지적면적']:,.0f}㎡)")
        elif off:
            warn.append(f"{r['지번']} — 지적도 {got:,.0f}㎡ ↔ 조서 {r['지적면적']:,.0f}㎡ "
                        "(10% 넘게 어긋납니다)")
        seen.add(pnu)
        ratio = r["소계"] / r["지적면적"] if r["지적면적"] else 1.0
        out.append(dict(r, pnu=pnu, rings=rings, 지적도면적=round(got), 편입률=round(ratio, 3)))
    return out, warn


# 증설 사업의 두 구역 — 기본 색·이름. **회사 표준이 아니라 다수값이다.**
# 기허가지 파랑 3 : 빨강 1, 범례 문구는 7건이 전부 달랐다. 사업별로 vars 가 덮어쓴다.
# → docs/20260819_삽도_자동화.md §4-3
ZONE_DEFAULT = {
    "사업계획지구": {"color": "red",  "label": "사업계획지구"},
    "금회":        {"color": "red",  "label": "금회사업부지"},
    "기허가":      {"color": "blue", "label": "기허가지"},
}


def is_expansion(parcels):
    """증설 사업인가 — 조서에 금회 부지가 따로 적혀 있으면 그렇다."""
    return any("금회" in (p.get("비고") or "") for p in parcels)


def zone_of(비고, expansion):
    """조서 `비고` → 구역 키.

    ⚠️ **비증설 사업은 나누지 않는다.** 정답도 `사업계획지구` 한 덩어리 빨강이다 (2/2).
       나누면 `공유수면`·`-` 같은 비고가 기허가지로 잘못 묶여 파랗게 나온다 (천안 586).

    증설이면 `금회` 가 든 것만 금회, 나머지가 기허가다. 표기는 사업마다 다르다
    (`금회증설`·`금회 신규`·`금회사업`)."""
    if not expansion:
        return "사업계획지구"
    return "금회" if "금회" in (비고 or "") else "기허가"


def to_elements(parcels, origin_lonlat, center_px, px_per_m, min_ratio=0.05,
                crs="EPSG:3857", zones=None, legend=False):
    """필지 폴리곤 → figure_overlay 요소들.

    구역은 조서의 `비고` 로 나눈다 — 증설 사업은 기허가지와 금회 부지를 다른 색으로
    그린다 (증설·변경 7건 중 6건).

    ⚠️ **색과 이름은 여기서 정하지 않는다.** 회사 표준이 없어 사업마다 다르다.
       `zones` 로 덮어쓴다 — `{"금회": {"color": "yellow", "label": "금회 신규부지"}}`.
       기본값은 다수를 따른다 (`ZONE_DEFAULT`).

    `legend=True` 면 범례 요소를 함께 낸다. **구역이 둘일 때만** 붙는다 —
    비증설 사업은 정답도 `사업계획지구` 한 항목이라 여기서 만들지 않는다 (2/2).

    지도 위 지시선 라벨(`금회 신규부지` → 화살표)은 **만들지 않는다.** 괴산 1건뿐이고
    (1/7) 나머지는 전부 범례에 넣는다."""
    z = {k: dict(v) for k, v in ZONE_DEFAULT.items()}
    for k, v in (zones or {}).items():
        z.setdefault(k, {}).update(v)
    import math
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    cx_m, cy_m = tr.transform(*origin_lonlat)
    ox, oy = center_px
    # Web Mercator 는 위도가 올라갈수록 늘어난다 — 그 배율을 빼야 실제 거리와 맞는다.
    # EPSG:5186 같은 **평면 직각좌표계는 이미 미터**라 보정하지 않는다.
    k = (px_per_m / math.cos(math.radians(origin_lonlat[1]))
         if crs == "EPSG:3857" else px_per_m)

    def px(ring):
        out = []
        for lon, lat in ring:
            x, y = tr.transform(lon, lat)
            out.append([round(ox + (x - cx_m) * k, 1), round(oy - (y - cy_m) * k, 1)])
        return out

    # 구역끼리 **한 덩어리로 합친다.** 필지마다 선을 그으면 안쪽에 격자가 생긴다 —
    # 정답에는 외곽선 하나뿐이다.
    expansion = is_expansion(parcels)
    groups = {}
    for p in parcels:
        if p["편입률"] < min_ratio:          # 스치듯 지나가는 필지는 그리지 않는다
            continue
        groups.setdefault(zone_of(p["비고"], expansion), []).extend(px(r) for r in p["rings"])

    # 금회를 나중에 그린다 — 겹치면 금회 선이 위로 올라와야 한다.
    order = [k for k in ("사업계획지구", "기허가", "금회") if k in groups]
    els = [{"type": "parcels", "polygons": groups[k], "color": z[k]["color"], "zone": k}
           for k in order]
    if legend and len(order) > 1:
        els.append({"type": "legend", "swatch": "outline", "title": "범 례",
                    "items": [[z[k]["color"], z[k]["label"]] for k in reversed(order)]})
    return els


# ── 자체 검증 — 골든셋 ──────────────────────────────────────────────────────
def _online_check(name, text, rows, limit=12):
    """조서 지번을 **현재 지적도와 맞춰 본다.** 어긋나면 그 자체가 정보다.

    ⚠️ 지적도는 살아 있는 자료다 — **사업이 시행되면 필지가 분할된다.** 이미 지어진
       사업의 조서 지번으로 지금 지적도를 찾으면 쪼개진 조각 하나만 잡힌다.
       신규 사업(시행 전)은 조서 지번이 그대로 살아 있어야 한다."""
    import map_fetch as M
    addr = survey_address(text)
    if not addr:
        return f"{name:<12} 주소를 못 만들었습니다"
    try:
        mx, my, _ = M.geocode(addr)
    except Exception as e:
        return f"{name:<12} 지오코딩 실패 ({addr}) {e}"
    lon, lat = M.merc_to_lonlat(mx, my)
    code, err = bjd_code(lon, lat)
    if not code:
        return f"{name:<12} {err}"
    ok = bad = miss = 0
    for r in rows[:limit]:
        fs, _ = _get(attrFilter=f"pnu:=:{pnu_of(code, r['지번'], r.get('산', False))}",
                     geometry="true")
        if not fs:
            miss += 1
            continue
        a = sum(area_m2(g) for x in fs for g in _rings(x["geometry"]))
        if r["지적면적"] and abs(a - r["지적면적"]) <= r["지적면적"] * 0.10:
            ok += 1
        else:
            bad += 1
    n = min(len(rows), limit)
    return (f"{name:<12} {addr[:30]:<30} 지적도 일치 {ok}/{n}"
            + (f" · 어긋남 {bad}" if bad else "") + (f" · 없음 {miss}" if miss else ""))


def self_test(root="cases/small-env", online=False):
    files = sorted(glob.glob(f"{root}/*/input/사업개요.txt"))
    if not files:
        print(f"[skip] 사업개요가 없습니다: {root}")
        return True
    ok = 0
    for f in files:
        name = f.split("/")[-3]
        rows, err, total = parse_survey(open(f, encoding="utf-8").read())
        if err:
            print(f"  [WARN] {name:<12} {err}")
            continue
        s = sum(r["소계"] for r in rows)
        mark = "OK  " if total and abs(s - total) < 2 else "WARN"
        if mark == "OK  ":
            ok += 1
        print(f"  [{mark}] {name:<12} 필지 {len(rows)}개 · 소계 합 {s:,.0f}㎡"
              f" · 조서 합계 {total and f'{total:,.0f}' or '없음'}")
        by = {}
        for r in rows:
            by.setdefault(r["비고"] or "(없음)", []).append(r["지번"])
        for k, v in by.items():
            print(f"          {k}: {' · '.join(v)}")
        if online:
            print(f"          ↳ {_online_check(name, open(f, encoding='utf-8').read(), rows)}")
    print(f"\n합계가 맞은 사업 {ok}/{len(files)}")
    return True


def main():
    ap = argparse.ArgumentParser(description="편입토지조서 → 사업지 경계 폴리곤")
    ap.add_argument("file", nargs="?", help="사업개요 텍스트")
    ap.add_argument("--lonlat", nargs=2, type=float, help="사업지 경위도 (법정동코드 확인용)")
    ap.add_argument("--center-px", nargs=2, type=float, help="map_fetch 의 center_px")
    ap.add_argument("--px-per-m", type=float, help="map_fetch 의 px_per_m")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--online", action="store_true", help="지적도까지 맞춰 본다 (느리다)")
    ap.add_argument("--expand", action="store_true",
                    help="지적이 갈라진 사업이면 본번 계열로 메운다 (근사)")
    ap.add_argument("--min-ratio", type=float, default=0.05,
                    help="편입률이 이보다 낮은 필지는 그리지 않는다 (기본 0.05)")
    ap.add_argument("-o", "--out", help="spec 조각(JSON)으로 저장")
    a = ap.parse_args()

    if a.self_test or not a.file:
        sys.exit(0 if self_test(online=a.online) else 1)

    rows, err, total = parse_survey(open(a.file, encoding="utf-8").read())
    if err:
        sys.exit(err)
    print(f"필지 {len(rows)}개 · 사업부지 합 {sum(r['소계'] for r in rows):,}㎡")
    if not a.lonlat:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return

    code, err = bjd_code(*a.lonlat)
    if err:
        sys.exit(err)
    print(f"법정동코드 {code}")
    parcels, warn = fetch(rows, code, a.expand)
    for p in parcels:
        flag = "" if p["편입률"] >= 0.6 else "  ⚠ 일부만 편입"
        print(f"  {p['지번']:<7} {p['지목']} {p['지적도면적']:>7,}㎡"
              f" · 편입 {p['편입률']*100:>5.1f}% · {p['비고']}{flag}")
    for w in warn:
        print(f"  ⚠ {w}", file=sys.stderr)

    if a.out and a.center_px and a.px_per_m:
        els = to_elements(parcels, a.lonlat, a.center_px, a.px_per_m, a.min_ratio)
        json.dump({"elements": els}, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"→ {a.out}  (덩어리 {len(els)}개 · 폴리곤 {sum(len(e['polygons']) for e in els)}개)")


if __name__ == "__main__":
    main()

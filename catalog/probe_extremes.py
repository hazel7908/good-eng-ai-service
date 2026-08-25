#!/usr/bin/env python3
"""
극점 좌표(2.1.1) — 시군 경계에서 계산할 수 있는가.

윈도우 세션 요청(2026-08-26)으로 천안에 실증했다. 새로 확보할 자료는 없다 —
`admin.py` 가 이미 쓰는 VWorld `LT_C_ADSIGG_INFO`(시군구) · `LT_C_ADRI_INFO`(리)면 된다.

    python catalog/probe_extremes.py --시군 천안시 --lonlat 127.15 36.81

## 실증 결과 — 계산은 된다. 다만 **측지계를 먼저 정해야 한다** ⚠️

정답 좌표를 그대로 대조하면 경도가 셋 다 **같은 방향으로 −9″** 치우친다.
정답을 **동경측지계**로 보고 WGS84 로 옮기면 오차가 사라진다.

    극점   변환 전    변환 후
    동단   −8.5″  →  +0.7″   (17m)
    서단   −9.9″  →  +2.3″   (57m)
    남단   −5.5″  →  −2.1″

동경측지계는 2010년 폐지됐다. 완성 보고서가 그걸 쓰는 것은 통계연보 **책자 본문**의
옛 문구를 그대로 옮겨서로 보인다. **어느 쪽으로 쓸지는 회사가 정할 일**이다 (G-6).

## 지명 역조회 — 3/4

    동단  동면 화덕리    ✅       남단  광덕면 원덕리  ✅
    서단  광덕면 광덕리  ✅       북단  성환읍 신가리  ❌ 정답 안궁리

북단은 우연이 아니다 — 신가리 최북단이 안궁리보다 **557m 북쪽**이다.

⚠️ **리 소속은 `full_nm` 으로 거른다.** 극점은 시 경계 위라 이웃 시군 리가 같이 잡힌다.
   처음에 안쪽으로 밀어 넣는 방식을 썼다가 남단이 세종시 전의면으로 빠졌다.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import admin as A
import parcels as P

# Bessel 1841(동경측지계) → WGS84, 한국 3-parameter
DX, DY, DZ = -146.43, 507.89, 681.46
A_B, F_B = 6377397.155, 1 / 299.1528128
A_W, F_W = 6378137.0, 1 / 298.257223563


def to_wgs84(lat, lon, h=0.0):
    """동경측지계 경위도를 세계측지계로. Molodensky."""
    la, lo = math.radians(lat), math.radians(lon)
    a, f, da, df = A_B, F_B, A_W - A_B, F_W - F_B
    e2 = 2 * f - f * f
    Rn = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    Rm = a * (1 - e2) / (1 - e2 * math.sin(la) ** 2) ** 1.5
    dlat = (-DX * math.sin(la) * math.cos(lo) - DY * math.sin(la) * math.sin(lo)
            + DZ * math.cos(la) + da * (Rn * e2 * math.sin(la) * math.cos(la)) / a
            + df * (Rm * (a / (a * (1 - f))) + Rn * ((a * (1 - f)) / a))
            * math.sin(la) * math.cos(la)) / (Rm + h)
    dlon = (-DX * math.sin(lo) + DY * math.cos(lo)) / ((Rn + h) * math.cos(la))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def dms(v):
    d = int(v)
    m = int((v - d) * 60)
    return f"{d}°{m:02d}'{(v - d - m / 60) * 3600:04.1f}\""


def extremes(시군, lon, lat, half_deg=0.35):
    """시군 폴리곤에서 동·서·남·북단 꼭짓점을 뽑는다. 시군은 `천안시` 처럼 구 없이."""
    regs, err = A.fetch("시군구", lon, lat, half_deg)
    if err:
        return None, err
    pts = [p for r in regs if r["name"].startswith(시군)
           for g in r["rings"] for p in g]          # 자치구가 여럿이면 합친다
    if not pts:
        return None, f"{시군} 경계를 못 찾았다"
    return {"동단": max(pts, key=lambda p: p[0]), "서단": min(pts, key=lambda p: p[0]),
            "남단": min(pts, key=lambda p: p[1]), "북단": max(pts, key=lambda p: p[1])}, None


def ri_of(lon, lat, 시군, half=0.02):
    """극점이 속한 리. **`full_nm` 으로 그 시군 것만 남긴다** — 극점은 시 경계 위다."""
    fs, err = P._get(data="LT_C_ADRI_INFO",
                     geomFilter=f"BOX({lon-half},{lat-half},{lon+half},{lat+half})",
                     geometry="true", size="200")
    best, name = 1e9, None
    for f in fs or []:
        full = f["properties"].get("full_nm", "")
        if 시군 not in full:
            continue
        for g in P._rings(f["geometry"]):
            for a in g:
                d = math.hypot((a[0] - lon) * 88.5, (a[1] - lat) * 111.0) * 1000
                if d < best:
                    best, name = d, " ".join(full.split()[-2:])
    return name, best


def span_km(ext):
    """연장거리 — ⚠️ 정의가 확정되지 않았다 (G-6). 검산용으로만 쓴다."""
    mlat = (ext["북단"][1] + ext["남단"][1]) / 2
    ew = (ext["동단"][0] - ext["서단"][0]) * 111.32 * math.cos(math.radians(mlat))
    ns = (ext["북단"][1] - ext["남단"][1]) * 110.95
    return ew, ns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--시군", required=True)
    ap.add_argument("--lonlat", nargs=2, type=float, required=True)
    a = ap.parse_args()
    ext, err = extremes(a.시군, *a.lonlat)
    if err:
        sys.exit(err)
    for nm in ("동단", "서단", "남단", "북단"):
        lon, lat = ext[nm][0], ext[nm][1]
        ri, d = ri_of(lon, lat, a.시군)
        blat, blon = lat, lon
        print(f"{nm}  세계측지계 동경 {dms(lon)} 북위 {dms(lat)}   {ri or '?'} ({d:.0f}m)")
    ew, ns = span_km(ext)
    print(f"\n연장거리(검산용) 동서 {ew:.1f}km · 남북 {ns:.1f}km   ⚠️ 정의 미확정 — 쓰지 말 것")


if __name__ == "__main__":
    main()

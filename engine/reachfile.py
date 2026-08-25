#!/usr/bin/env python3
"""
KRF(Korean Reach File) — **유하 경로와 거리**. 2.8.3 수계 서술·수계흐름모식도의 뼈대다.

정답 서술은 이렇게 쓴다.

    구거를 따라 약 1.93km 유하하여 **섬강(국가)** 에 합류되며, 약 32.61km 를 유하하여
    최종 수계 본류인 **한강(국가)** 으로 유입된다. 총 유하거리는 약 34.54km 이다.

하천 이름·등급은 하천일람에서 오지만 **거리는 물길을 따라 재야** 나온다.
`hydro.py` 가 쓰는 하천망(`LT_C_WKMSTRM`)은 지오메트리가 **면**(하천 구역)이라
중심선을 못 뽑는데, KRF 는 **선형 + 흐름 방향**을 준다.

    python engine/reachfile.py --download            # 전체본 취득 (87MB)
    python engine/reachfile.py --trace 천안_화덕리
    python engine/reachfile.py --self-test

## ⚠️ 자료가 답을 끝까지 주지 않는다

사업지에서 하천까지 **1.3km 가 구거**인데 구거는 국가하천망에 없다. 실무자는 지도에서
그 구거를 눈으로 따라가 *어느 하천에 처음 닿는가* 를 판단한다. 우리는 **직선 최근접**으로
대신할 수밖에 없어 갈린다 — 원주는 최근접이 원주천인데 정답은 **섬강**이다.

    최종 본류(금강·한강)   2/2 일치      ← 쓸 만하다
    중간 하천 체인         1/2           ← 원주에 원주천이 여분으로 낀다
    총 유하거리            0/2 (+10%·+58%)

**그래서 확정하지 않고 후보로 낸다.** 표본을 늘려도 이 구조는 안 바뀐다 —
구거가 자료에 없다는 사실이 그대로이기 때문이다.
"""
import argparse
import json
import math
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KRF_DIR = ROOT / "raw_data/nas/stats/_national/KRF"
LINE = KRF_DIR / "KRF_ver3_LINE.shp"
CHECK = "[확인 필요]"

BASE = "https://water.nier.go.kr"
PAGE = f"{BASE}/web/gisKrf?pMENU_NO=89"


def download(name="KRF_ver3_total.zip", path="total/"):
    """물환경정보시스템에서 KRF 를 받는다. POST 한 번이면 된다."""
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    s.get(PAGE, verify=False, timeout=60)
    r = s.post(f"{BASE}/web/krfFileDown", data={"strFileNm": name, "strFilePath": path},
               headers={"Referer": PAGE}, verify=False, timeout=600)
    r.raise_for_status()
    KRF_DIR.mkdir(parents=True, exist_ok=True)
    zp = KRF_DIR / name
    zp.write_bytes(r.content)
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():
            try:
                nm = n.encode("cp437").decode("cp949")
            except Exception:
                nm = n
            if nm.startswith("KRF_ver3_LINE."):     # 선형만 쓴다 (집수구역·절점 불필요)
                (KRF_DIR / nm).write_bytes(z.read(n))
    zp.unlink()
    return LINE


_CACHE = None


def load():
    """LINE 레이어 → (레코드, 도형, RCH_ID 색인). 한 번만 읽는다 (7,785구간)."""
    global _CACHE
    if _CACHE:
        return _CACHE
    if not LINE.exists():
        sys.exit(f"{LINE} 이 없다 — `python engine/reachfile.py --download` 먼저")
    import shapefile
    r = shapefile.Reader(str(LINE), encoding="cp949")
    fld = [f[0] for f in r.fields[1:]]
    srs = list(r.iterShapeRecords())
    recs = [dict(zip(fld, s.record)) for s in srs]
    _CACHE = (recs, [s.shape for s in srs], {x["RCH_ID"]: i for i, x in enumerate(recs)})
    return _CACHE


def _m(a, b):
    """경위도 두 점 사이 거리(m) — 위도 36~38도 근사."""
    return math.hypot((a[0] - b[0]) * 88800, (a[1] - b[1]) * 111000)


def trace(lon, lat, max_reach=200):
    """사업지 → 최종 본류. 반환 {체인, 구간별, 총거리_km, 후보, 최종본류}.

    ⚠️ **하류는 `DI_RCH_ID` 가 아니다.** 그 필드는 되짚어 와 순환을 만든다
    (병천천의 `DI` 가 용두천을 도로 가리킨다). 하류는 `LD_RCH_ID`/`RD_RCH_ID`
    (Left/Right Downstream) 다. 이걸 몰라 오래 2구간에서 멈췄다.
    """
    recs, shapes, byid = load()
    i0 = min(range(len(shapes)),
             key=lambda i: min(_m(p, (lon, lat)) for p in shapes[i].points))
    pts = shapes[i0].points
    gap = min(_m(p, (lon, lat)) for p in pts)

    # 합류 추정점부터 그 구간 끝까지만 센다. 좌표는 **상류→하류** 순이다
    # (끝점이 다음 구간에 더 가깝다 — 실측으로 확인)
    j = min(range(len(pts)), key=lambda k: _m(pts[k], (lon, lat)))
    seg = [_m(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
    first = float(recs[i0]["RCH_LEN"] or 0) * (sum(seg[j:]) / (sum(seg) or 1))

    cur, seen, chain = recs[i0], set(), []
    while cur and cur["RCH_ID"] not in seen and len(chain) < max_reach:
        seen.add(cur["RCH_ID"])
        chain.append((cur["DC_RIV_NM"],
                      first if not chain else float(cur["RCH_LEN"] or 0)))
        nxt = None
        for k in ("LD_RCH_ID", "RD_RCH_ID"):
            v = (cur.get(k) or "").strip()
            if v and v in byid and v not in seen:
                nxt = v
                break
        cur = recs[byid[nxt]] if nxt else None

    # 하천이 바뀌는 자리마다 묶는다 — 정답 서술이 그 단위다
    agg, acc = [], 0.0
    for i, (nm, ln) in enumerate(chain):
        acc += ln
        if i + 1 == len(chain) or chain[i + 1][0] != nm:
            agg.append({"하천": nm, "유하거리_km": round(acc, 2)})
            acc = 0.0

    # 첫 합류 하천 후보 — 사업지 둘레 하천을 거리순으로
    near = sorted({(round(min(_m(p, (lon, lat)) for p in shapes[i].points)),
                    recs[i]["DC_RIV_NM"]) for i in range(len(shapes))
                   if min(_m(p, (lon, lat)) for p in shapes[i].points) < 4000})[:5]
    return {
        "체인": [a["하천"] for a in agg],
        "구간별": agg,
        "총거리_km": round(sum(a["유하거리_km"] for a in agg), 2),
        "최종본류": agg[-1]["하천"] if agg else CHECK,
        "사업지_하천_직선거리_m": round(gap),
        "첫합류_후보": [{"하천": n, "직선거리_m": d} for d, n in near],
        "_경고": ("사업지~하천 구간이 **구거**라 자료에 없다. 첫 합류 하천을 "
                  "**직선 최근접으로 가정**했다 — 지도에서 구거를 따라가야 확정된다. "
                  "골든셋 2건 중 1건(원주)이 어긋났다"),
    }


GOLDEN = [
    # (사업, 정답 최종본류, 정답 총거리, 정답 체인)
    ("천안_화덕리", "금강", 45.12, ["용두천", "병천천", "미호천", "금강"]),
    ("원주_무장리", "한강", 34.54, ["섬강", "한강"]),
]


def self_test():
    ok = bad = 0
    for case, 본류, 거리, 체인 in GOLDEN:
        vp = ROOT / "cases/small-env" / case / "vars/regional-overview.json"
        if not vp.exists():
            print(f"⏭  {case}: vars 없음"); continue
        lo = json.loads(vp.read_text(encoding="utf-8")).get("공간", {}).get("_lonlat")
        if not lo:
            print(f"⏭  {case}: 좌표 없음"); continue
        r = trace(*lo)
        hit = r["최종본류"] == 본류
        ok, bad = (ok + 1, bad) if hit else (ok, bad + 1)
        print(f"\n== {case}")
        print(f"   {'✅' if hit else '❌'} 최종본류 {r['최종본류']} (정답 {본류})")
        print(f"   {'✅' if r['체인'] == 체인 else '⚠️'} 체인 {r['체인']}  (정답 {체인})")
        d = abs(r["총거리_km"] - 거리) / 거리
        print(f"   {'⚠️'} 총거리 {r['총거리_km']}km (정답 {거리}km · {d:+.0%})")
    print(f"\n=== 최종본류 {ok}/{ok + bad} 일치 ===")
    print("⚠️ 체인·거리는 확정하지 않는다 — 구거가 자료에 없다 (머리말)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--trace", metavar="사업")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.download:
        print(f"→ {download()}")
    elif a.self_test:
        return self_test()
    elif a.trace:
        vp = ROOT / "cases/small-env" / a.trace / "vars/regional-overview.json"
        lo = json.loads(vp.read_text(encoding="utf-8"))["공간"]["_lonlat"]
        print(json.dumps(trace(*lo), ensure_ascii=False, indent=1))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
정답 삽도 PSD → **좌표 맞춤값 자동 추출** (anchor_px · px_per_m).

수확 베이스에는 좌표가 없다. 실무자가 임의 창으로 잘라 쓴 것이라 도엽 격자와 안 맞는다.
지금까지는 축척바와 마커를 **눈으로 재서** `sheet_georef.json` 에 적었다 — 사업 하나에
삽도 넷이면 넷을 다 재야 해서, 골든셋 8건 전수 대조를 막는 병목이었다.

그런데 **PSD 레이어 이름에 답이 있었다.** 지역개황도에는

    사업지                     ← 표적 마커
    모양 1 사본 2 … 사본 7      ← 반경원 1km · 2km … 6km
    1.0km … 6.0km             ← 반경 라벨

이 그대로 들어 있다. 마커 bbox 중심이 anchor, 반경원 반지름을 회귀한 기울기가 축척이다.
평창에서 수동 실측과 맞춰 보면 anchor 2.5px · 축척 0.1% 차이다.

    python catalog/psd_georef.py                 # 전 사업 추출·대조
    python catalog/psd_georef.py --write         # sheet_georef.json 에 병합

⚠️ **수계도·위치도는 이 패턴이 없다** (반경원 대신 축척바를 쓴다). 지역개황도 계열만
   자동으로 잡힌다 — 나머지는 여전히 수동 실측이다.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEETS = os.path.join(ROOT, "raw_data/nas/sheets")
GEOREF = os.path.join(ROOT, "catalog/data/sheet_georef.json")

RING = re.compile(r"모양 1 사본 (\d+)$")
KM = re.compile(r"(\d)\.(\d)km$")


def _walk(layers):
    for l in layers:
        if l.is_group():
            yield from _walk(l)
        else:
            yield l


def _center(bbox):
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def extract(psd_path):
    """(anchor_px, px_per_m, 근거) — 못 잡으면 (None, None, 사유)."""
    from psd_tools import PSDImage
    psd = PSDImage.open(psd_path)
    W, H = psd.width, psd.height

    marker, rings = None, []
    for l in _walk(psd):
        name = (l.name or "").strip()
        if name == "사업지" and marker is None:
            marker = l.bbox
        m = RING.match(name or "")
        if m and l.is_visible():
            b = l.bbox
            w, h = b[2] - b[0], b[3] - b[1]
            # 반경원은 정원이다 — 가로세로가 크게 다르면 다른 도형이다
            if w > 40 and abs(w - h) <= max(4, w * 0.02):
                rings.append((w / 2, _center(b)))
    if len(rings) < 2:
        return None, None, f"반경원을 {len(rings)}개만 찾았습니다"

    # 반지름이 작은 것부터 1km, 2km … 로 매긴다. 정답 삽도는 6개가 보통인데
    # 45개까지 있는 판도 있다(청주) — 겹쳐 그린 것이라 **중복 반지름을 접는다**.
    rs = sorted(r for r, _ in rings)
    uniq = []
    for r in rs:
        if not uniq or r - uniq[-1] > uniq[-1] * 0.15:
            uniq.append(r)
    if len(uniq) < 2:
        return None, None, "반경원 반지름이 한 종류뿐입니다"
    # 이웃 간격의 중앙값 = 1km 당 픽셀. 평균보다 중앙값이 낫다 —
    # 맨 바깥 원이 화면 밖으로 잘려 bbox 가 작게 잡히는 판이 있다.
    gaps = sorted(uniq[i + 1] - uniq[i] for i in range(len(uniq) - 1))
    px_per_km = gaps[len(gaps) // 2]
    px_per_m = px_per_km / 1000

    if marker:
        anchor = _center(marker)
    else:
        # 마커가 없으면 반경원들의 중심 — 같은 점을 공유한다
        cs = [c for _, c in rings]
        anchor = (sorted(c[0] for c in cs)[len(cs) // 2],
                  sorted(c[1] for c in cs)[len(cs) // 2])
    why = (f"반경원 {len(uniq)}개 간격 중앙값 {px_per_km:.1f}px=1km · "
           f"{'마커' if marker else '반경원 중심'} 실측")
    return [round(anchor[0], 1), round(anchor[1], 1)], round(px_per_m, 5), why


# 지역개황도 계열만 이 패턴을 갖는다
KINDS = ("지역개황도", "대상지역설정도")


def main():
    ap = argparse.ArgumentParser(description="정답 PSD → 좌표 맞춤값")
    ap.add_argument("--write", action="store_true", help="sheet_georef.json 에 병합")
    a = ap.parse_args()

    georef = json.load(open(GEOREF, encoding="utf-8"))
    hits = 0
    for site in sorted(os.listdir(SHEETS)):
        d = os.path.join(SHEETS, site)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".psd") or not any(k in f for k in KINDS):
                continue
            try:
                anchor, ppm, why = extract(os.path.join(d, f))
            except Exception as e:
                print(f"  ✗ {site:<12} {f} — {type(e).__name__}")
                continue
            if anchor is None:
                print(f"  ✗ {site:<12} {f} — {why}")
                continue
            hits += 1
            old = georef.get(site, {}).get("지역개황도")
            mark = ""
            if old:
                da = max(abs(anchor[0] - old["anchor_px"][0]),
                         abs(anchor[1] - old["anchor_px"][1]))
                dp = abs(ppm - old["px_per_m"]) / old["px_per_m"] * 100
                mark = f"  ↔ 실측 대비 anchor {da:.1f}px · 축척 {dp:.1f}%"
            print(f"  ○ {site:<12} anchor {anchor} · {ppm} px/m   ({why}){mark}")
            if a.write:
                # ⚠️ **수동 실측을 덮어쓰지 않는다.** 눈으로 잰 값은 축척바·마커를 확대해
                #    맞춘 것이라 근거가 다르다. 자동값은 비어 있는 자리만 채운다.
                if old:
                    print(f"     (실측이 이미 있어 두었습니다)")
                else:
                    georef.setdefault(site, {})["지역개황도"] = {
                        "anchor_px": anchor, "px_per_m": ppm,
                        "근거": f"PSD 레이어 자동 추출 — {why}"}
    if a.write:
        json.dump(georef, open(GEOREF, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n→ {GEOREF}")
    print(f"\n{hits}건 추출")


if __name__ == "__main__":
    main()

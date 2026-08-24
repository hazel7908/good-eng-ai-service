#!/usr/bin/env python3
"""
수확한 베이스를 **종류 이름으로 정리**하고 목록을 만든다.

`harvest_sheets.py` 는 PSD 이름을 그대로 쓴다 — `지역개황도 틀 2023.png` ·
`생태자연도(최종).png` · `위치도 틀.png`. 실무자가 붙인 이름이라 사업마다 다르고,
실전에서 "이 사업의 지역개황도 베이스" 를 찾을 때 걸린다.

여기서 **종류로 정규화**한다 (`지역개황도.png`). 같은 종류가 둘이면 `_2` 를 붙인다.
원본 PSD 이름은 목록(`catalog/review/sheets_harvest.md`)에 남긴다 — 추적이 끊기면
NAS 에서 무엇을 받았는지 알 수 없다.

    python catalog/index_sheets.py            # 목록만
    python catalog/index_sheets.py --rename    # 실제로 이름을 바꾼다

⚠️ 이미지는 **커밋하지 않는다** (`raw_data/` 는 git 제외). NAS 에서 언제든 다시
   수확되고, 지금도 1.5GB 다. 커밋하는 것은 이 목록과 `sheet_georef.json` 의
   **실측 좌표** — 그것만이 다시 만들 수 없는 값이다.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEETS = os.path.join(ROOT, "raw_data/nas/sheets")
MD = os.path.join(ROOT, "catalog/review/sheets_harvest.md")
GEOREF = os.path.join(ROOT, "catalog/data/sheet_georef.json")

# ⚠️ **긴 이름이 먼저다.** `조망점위치도` 를 `위치도` 로 잡으면 서로 다른 삽도가 겹친다.
KINDS = ["국토환경성평가지도", "가설방음판넬 위치도", "조망점 위치도", "조망점위치도",
         "지역개황도", "생태자연도", "위성사진", "수계도", "지질도", "표고", "위치도"]


def kind_of(name):
    base = os.path.splitext(name)[0]
    for k in sorted(KINDS, key=len, reverse=True):
        if k.replace(" ", "") in base.replace(" ", ""):
            return k.replace(" ", "")
    return None


# 수확 실패(조각 0)면 흰 캔버스만 남아 몇 KB 다. 목록에서 성공으로 세면 안 된다.
MIN_OK = 20_000


def _rank(name, kind):
    """같은 종류가 여럿일 때 **어느 것이 본 파일인가**.

    ⚠️ 파일명 정렬로 정하면 안 된다 — `생태자연도 2` 가 `생태자연도(최종)` 보다 앞서
       실무자가 버린 판이 본 파일이 된다. 실측 좌표(`sheet_georef.json`)가 (최종) 기준이라
       조용히 어긋난다.

    `최종` 이 붙은 것이 1번, 그다음은 **군더더기가 적은 이름** 순이다
    (`수계도` < `수계도(작은)`)."""
    base = os.path.splitext(name)[0]
    if "최종" in base:
        return (0, 0)
    return (1, len(base.replace(kind, "").replace(" ", "")))


# 이름을 바꾸고 나면 PSD ↔ PNG 대응이 끊긴다. 사업 폴더에 매핑을 남긴다 —
# 없으면 "무엇을 받았는지" 도 "수확에 실패한 게 무엇인지" 도 알 수 없다.
SIDECAR = "_source.json"


def _map(site):
    f = os.path.join(SHEETS, site, SIDECAR)
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}


def scan():
    """(사업, 종류, 파일, 크기, 정규화이름, 상태) — 수확 못 한 PSD 는 실패로 센다."""
    rows = []
    for site in sorted(os.listdir(SHEETS)):
        d = os.path.join(SHEETS, site)
        if not os.path.isdir(d):
            continue
        seen = {}
        files = sorted(os.listdir(d))
        pngs = [f for f in files if f.endswith(".png")]
        pngs.sort(key=lambda f: (kind_of(f) or "?", _rank(f, kind_of(f) or "")))
        for f in pngs:
            size = os.path.getsize(os.path.join(d, f))
            k = kind_of(f) or "?"
            ok = size >= MIN_OK
            seen[k] = seen.get(k, 0) + 1
            target = (f"{k}.png" if seen[k] == 1 else f"{k}_{seen[k]}.png") if k != "?" else None
            rows.append((site, k, f, size, target, "○" if ok else "✗ 조각 0"))
        # PSD 는 받았는데 수확본이 없는 것 — 베이스를 못 골라냈다는 뜻이다.
        # ⚠️ 이름으로 맞추면 안 된다 (정규화로 달라졌다). 매핑을 본다.
        got = set(_map(site).values()) | {f for f in pngs}
        for f in files:
            if not f.endswith(".psd"):
                continue
            if f in got or os.path.splitext(f)[0] + ".png" in got:
                continue
            rows.append((site, kind_of(f) or "?", f, 0, None, "✗ 미수확"))
    return rows


def main():
    ap = argparse.ArgumentParser(description="수확 베이스 정리·목록")
    ap.add_argument("--rename", action="store_true", help="종류 이름으로 실제 변경")
    a = ap.parse_args()

    rows = scan()
    georef = json.load(open(GEOREF, encoding="utf-8")) if os.path.exists(GEOREF) else {}

    if a.rename:
        maps = {}
        for site, k, f, size, target, st in rows:
            if not f.endswith(".png"):
                continue
            m = maps.setdefault(site, _map(site))
            orig = m.get(f, f)                      # 두 번 돌려도 첫 이름을 잃지 않는다
            if not target or f == target:
                m[target or f] = orig
                continue
            src = os.path.join(SHEETS, site, f)
            dst = os.path.join(SHEETS, site, target)
            if os.path.exists(dst):
                print(f"  [건너뜀] {site}/{target} 가 이미 있습니다")
                continue
            os.rename(src, dst)
            m.pop(f, None)
            m[target] = orig
            print(f"  {site}/{f} → {target}")
        for site, m in maps.items():
            json.dump(m, open(os.path.join(SHEETS, site, SIDECAR), "w",
                              encoding="utf-8"), ensure_ascii=False, indent=1)
        rows = scan()

    lines = ["# NAS 도엽 베이스 수확\n",
             "삽도 PSD 의 배경 레이어만 합성한 깨끗한 지도 — 오버레이(사업계획지구·반경원·라벨) 없음.",
             "판별 기준은 `catalog/harvest_sheets.py` 의 `extract_base` 세 줄.\n",
             "⚠️ **이미지는 커밋하지 않는다** (`raw_data/` 는 git 제외, 현재 1.5GB).",
             "다시 만들 수 없는 값은 `catalog/data/sheet_georef.json` 의 **실측 좌표**뿐이라 그것만 커밋한다.\n",
             "| 사업 | 종류 | 파일 | 원래 이름 | 크기 | 좌표 | 상태 |",
             "|---|---|---|---|--:|:--:|:--:|"]
    for site, k, f, size, target, st in rows:
        cur = target or f
        has = "✅" if any(k in key for key in georef.get(site, {}) if key != "lonlat") else "—"
        src = _map(site).get(cur, "")
        orig = "" if src in ("", cur) else src
        sz = f"{size/1e6:.1f}MB" if size else "—"
        lines.append(f"| {site} | {k} | `{cur}` | {orig} | {sz} | {has} | {st} |")
    ok = [r for r in rows if r[5] == "○"]
    lines.append(f"\n수확 **{len(ok)}장** · {sum(r[3] for r in ok)/1e6:.0f}MB"
                 f" (실패 {len(rows)-len(ok)}건)\n")
    lines.append("실패는 PSD 구조가 제각각이라 그렇다 — 국토환경성평가지도는 ECVAM 캡처가"
                 " 레이어로 안 들어 있는 판이 있다. 반수동 처리 대상.\n")
    lines.append("원주·천안은 **NAS 경로가 바뀌어** 목록 조회부터 실패한다"
                 " (`0. 평가서/환경/환25-NN …`). 카탈로그 v2 재빌드 뒤에 다시 받는다.\n")
    open(MD, "w", encoding="utf-8").write("\n".join(lines))
    print(f"\n{len(rows)}장 → {MD}")


if __name__ == "__main__":
    main()

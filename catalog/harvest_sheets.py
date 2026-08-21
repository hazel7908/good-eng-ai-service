#!/usr/bin/env python3
"""
NAS 삽도 PSD → 깨끗한 도엽 베이스 수확.

도엽 파일은 API 가 없다(성과품 배포 정책). 그런데 **실무자가 매 사업 받아 쓴 도엽이
NAS 의 삽도 PSD 안에 쌓여 있다** — 배경 레이어로. 오버레이(사업계획지구·화살표·라벨)는
전부 별도 레이어라, 배경만 합성하면 원본 도엽이 나온다 (평창 수계도로 검증).

수확 기준: **보이는 큰(문서 25%↑) + 꽉 찬(불투명 60%↑) 래스터 레이어**만 합성한다.
작은 레이어 = 오버레이, 크지만 성긴 레이어(반경원 묶음 등)도 오버레이다 —
평창 위치도 틀에서 투명 레이어가 검은 사각형으로 얹히는 것으로 배웠다.

결과는 `raw_data/nas/sheets/{사업}/{PSD이름}.png` (git 제외) + 목록은
`catalog/review/sheets_harvest.md` (커밋).

⚠️ **수확본에는 좌표가 없다** — 실무자가 임의 창으로 잘라 쓴 것이라 도엽 격자와
   안 맞는다. 같은 지역 삽도의 베이스로 쓰려면 좌표 맞춤(georeferencing)이 필요하다.
   미해결 → docs/20260819_삽도_자동화.md 미해결 10번.

경로를 아는 사업만 SITES 에 있다. 나머지는 카탈로그 v2(/nas-survey 재실행) 후 채운다.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synology_filestation import connect, human

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "raw_data/nas/sheets")
MD = os.path.join(ROOT, "catalog/review/sheets_harvest.md")

# 지형도 계열만 — 위성사진·현장·계획도면류는 도엽이 아니다
WANT = ("위치도", "지역개황도", "수계도", "표고", "지질도", "생태자연도", "국토환경성평가지도")

SITES = {
    "평창_수청리": "/backupenv/2024/24-17 평창군 미탄면 수청리 73번지 일원 태양광시설 조성사업(완)/3. 삽도",
    "청주_호명리": "/backupenv/2024/24-1 청주 청원구 북이면 호명리 430 일원 태양광(솔랩) (완)/3. 삽도",
    "괴산_후평리": "/backupenv/0. 평가서/환경/환26-14 괴산 청천면 후평리 일원 근린생활(단독주택)단지 조성사업 소규모환경 및 소규모재해영향평가(태양측량)/3. 삽도",
}


def extract_base(psd_path, out_png, min_frac=0.25):
    """보이는 큰 래스터 레이어만 합성 → 깨끗한 베이스. (조각 수, 캔버스 크기) 반환."""
    from psd_tools import PSDImage
    from PIL import Image
    psd = PSDImage.open(psd_path)
    W, H = psd.width, psd.height
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    n = 0
    for layer in psd:
        if not layer.is_visible():
            continue
        if layer.width * layer.height < W * H * min_frac:
            continue
        im = layer.composite()
        if im is None:
            continue
        mask = im.getchannel("A") if "A" in im.getbands() else None
        if mask is not None:
            # 크지만 **성긴** 레이어(반경원·화살표 묶음)는 오버레이다.
            # 베이스 스캔은 불투명이 꽉 차 있다.
            small = mask.resize((64, 64))
            if sum(small.getdata()) / (64 * 64 * 255) < 0.6:
                continue
        canvas.paste(im.convert("RGB"), (layer.left, layer.top), mask)
        n += 1
    if n:
        canvas.save(out_png)
    return n, (W, H)


def main():
    fs = connect()
    rows = []
    for site, folder in SITES.items():
        try:
            items = fs.list_folder(folder)
        except Exception as e:
            print(f"[skip] {site} — 폴더 접근 실패 {e}")
            continue
        dest = os.path.join(OUT, site)
        os.makedirs(dest, exist_ok=True)
        for it in sorted(items, key=lambda x: x["name"]):
            name = it["name"]
            if not name.lower().endswith(".psd"):
                continue
            if not any(w in name for w in WANT):
                continue
            size = it.get("additional", {}).get("size", 0)
            local = os.path.join(dest, name)
            png = os.path.splitext(local)[0] + ".png"
            if os.path.exists(png):
                print(f"  [있음] {site}/{name}")
                continue
            t0 = time.time()
            try:
                if not os.path.exists(local):
                    fs.download(f"{folder}/{name}", dest)
                n, wh = extract_base(local, png)
                os.remove(local)                      # PSD 원본은 크다 — PNG 만 남긴다
                rows.append((site, name, human(size), n, wh))
                print(f"  [수확] {site}/{name} ({human(size)}) → 조각 {n} · "
                      f"{wh[0]}×{wh[1]} · {time.time()-t0:.0f}s")
            except Exception as e:
                print(f"  [실패] {site}/{name} — {e}")

    if rows:
        old = open(MD, encoding="utf-8").read() if os.path.exists(MD) else (
            "# NAS 도엽 베이스 수확\n\n삽도 PSD 의 배경 레이어만 합성한 깨끗한 지도. "
            "오버레이(사업계획지구 등)는 제거됨.\n좌표 없음 — georeferencing 은 미해결.\n\n"
            "| 사업 | PSD | 원본 크기 | 베이스 조각 | 캔버스 |\n|---|---|---|--:|---|\n")
        with open(MD, "w", encoding="utf-8") as f:
            f.write(old + "".join(
                f"| {s} | {n} | {sz} | {c} | {w}×{h} |\n"
                for s, n, sz, c, (w, h) in rows))
    print(f"\n수확 {len(rows)}건 → {OUT}")


if __name__ == "__main__":
    main()

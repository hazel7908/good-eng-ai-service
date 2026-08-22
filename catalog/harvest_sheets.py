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

골든셋 8개 사업 전부 등록 (경로는 2026-08-21 라이브 확인).
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
    "원주_무장리": "/backupenv/0. 평가서/환경/환25-09 원주시 호저면 무장리 578번지 일원 태양광발전시설 조성사업 소규모환경영향평가(㈜썬파워)/3. 삽도",
    "천안_화덕리": "/backupenv/0. 평가서/환경/환25-05 천안시 동남구 동면 화덕리 30번지 일원 태양광발전시설 조성사업 소규모환경영향평가(SolLab)/3. 삽도",
    "옥천_사양리": "/backupenv/2024/24-25 옥천군 군서면 사양리 산39-1번지 일원 야영장시설 부지조성사업(완)/3. 삽도",
    "충주_율능리": "/backupenv/0. 평가서/환경/환25-19 충주시 엄정면 율능리 91-2번지 일원 태양광발전시설 조성사업(㈜현화)/3. 삽도",
    "괴산_금신리": "/backupenv/0. 평가서/환경/환25-18 괴산군 청안면 금신리 155-1번지 일원 태양광발전시설 조성사업(동남이엔지)/3. 삽도",
}


def extract_base(psd_path, out_png, min_frac=0.25):
    """보이는 큰 래스터 레이어만 합성 → 깨끗한 베이스. (조각 수, 캔버스 크기) 반환."""
    from psd_tools import PSDImage
    from PIL import Image
    psd = PSDImage.open(psd_path)
    W, H = psd.width, psd.height
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    n = 0

    def walk(layers):
        """그룹 안까지 — 생태자연도 PSD 는 베이스가 그룹 폴더 안에 있었다."""
        for l in layers:
            if l.is_group():
                yield from walk(l)
            else:
                yield l

    for layer in walk(psd):
        if not layer.is_visible():
            continue
        # ⚠️ 모든 판정은 **문서 창 기준**이다. 베이스 스캔이 문서보다 훨씬 클 수 있는데
        #    (평창 생태자연도: 문서 1181² ↔ 레이어 6247×9478), 레이어 전체로 재면
        #    창 밖 빈 영역 때문에 불투명도가 낮게 나와 베이스가 걸러진다.
        l, t, r, b = layer.bbox
        ix = max(0, min(r, W) - max(l, 0))
        iy = max(0, min(b, H) - max(t, 0))
        if ix * iy < W * H * min_frac:
            continue
        im = layer.composite(viewport=(0, 0, W, H))
        if im is None:
            continue
        mask = im.getchannel("A") if "A" in im.getbands() else None
        if mask is not None:
            small = mask.resize((64, 64))
            # 문턱 30% — 베이스가 **띠 여러 장**일 수 있다 (괴산 위성: 캡처 4장이
            # 각각 문서의 ~48% 만 덮는다). 성긴 오버레이(반경원 묶음)는 10~20% 라
            # 여전히 걸러진다.
            if sum(small.getdata()) / (64 * 64 * 255) < 0.30:
                continue
        thumb = im.convert("RGB").resize((64, 64))
        gray = thumb.convert("L")
        vals = list(gray.getdata())
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        sat = thumb.convert("HSV").getchannel("S")
        sv = sum(sat.getdata()) / (64 * 64)
        # 균일색·무채색 = 오버레이(흰 패널·음영 링·딤).
        # ⚠️ **둘을 따로 쓰면 진짜 베이스가 걸린다** — 평창 위성은 어두운 숲 위주라
        #    명암 std 10.8 로 균일색 문턱(12)에 걸렸다. 채도가 있으면 지도다.
        if std < 12 and sv < 40:
            continue
        if sv < 18:
            continue
        canvas.paste(im.convert("RGB"), (0, 0), mask)
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
            # 받다 만 PSD(세션 끊김)는 크기가 다르다 — 지우고 다시 받는다
            if os.path.exists(local) and size and os.path.getsize(local) != size:
                print(f"  [부분] {site}/{name} {os.path.getsize(local)}≠{size} → 재다운로드")
                os.remove(local)
            # PNG 는 필터가 바뀌었을 수 있으니 PSD 가 있으면 다시 뽑는다
            if os.path.exists(png) and not os.path.exists(local):
                print(f"  [있음] {site}/{name}")
                continue
            t0 = time.time()
            try:
                if not os.path.exists(local):
                    fs.download(f"{folder}/{name}", dest)
                n, wh = extract_base(local, png)
                if False:                              # 필터를 다듬는 동안은 PSD 를 지우지 않는다 — 재다운로드 수업료가 크다
                    os.remove(local)
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

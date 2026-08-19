#!/usr/bin/env python3
"""
삽도 PSD 에서 **깨끗한 베이스 지도**를 뽑아낸다.

`figure_overlay.py` 는 "베이스 위에 그리는" 쪽이고, 이 모듈은 "베이스를 구하는" 쪽이다.

발견(2026-08-19): NAS 삽도 폴더의 PSD 는 **레이어가 분리돼 있다.**
실무자가 ①웹 지도를 캡처해 배경으로 깔고 ②그 위에 경계·라벨·범례·축척·방위를 얹는 식으로
만들었기 때문이다. 그래서 **배경 레이어만 꺼내면 오버레이가 없는 지도**가 나온다.

  NAS PSD 34,385개 (생태자연도 604 · 수계도 589 · 위성사진 923 · 지역개황도 253 · 정온시설 248 …)

사용:
    python engine/psd_base.py 삽도.psd --list          # 레이어 구조 보기
    python engine/psd_base.py 삽도.psd -o base.png     # 베이스 레이어 추출
    python engine/psd_base.py 삽도.psd --layer "레이어 2" -o base.png

⚠️ **웹 UI 가 같이 찍혀 있을 수 있다.** 실무자가 화면을 캡처한 것이라 축소/줌 버튼·
   레이어 창이 가장자리에 남는다. `--crop-ui` 로 가장자리를 잘라내되, **최종 확인은 눈으로** 한다.
"""
import argparse, sys
from pathlib import Path

try:
    from psd_tools import PSDImage
except ImportError:
    sys.exit("psd-tools 가 필요합니다: .venv/bin/pip install psd-tools")

# 오버레이 레이어 이름 — 골든셋 PSD 에서 실측한 표기. 베이스 후보에서 걸러내는 데 쓴다.
OVERLAY_HINT = ("경계", "사업계획지구", "범례", "축척", "방위", "화살표", "사각형",
                "텍스트", "지시", "마커", "라벨", "표적", "km", "m)", "복사", "사본")


def layers(psd):
    """(레이어, 픽셀수, 오버레이로 보이는가) 목록."""
    out = []
    for l in psd.descendants():
        if l.is_group():
            continue
        w, h = l.size
        looks_overlay = any(k in l.name for k in OVERLAY_HINT)
        out.append((l, w * h, looks_overlay))
    return out


def pick_base(psd):
    """베이스 레이어 추정 — **보이는 것 중 가장 큰 비(非)오버레이 래스터**.

    캡처한 지도는 문서보다 크게 깔리고(축소해 배치), 오버레이는 그보다 작다.
    실측: 국토환경성평가지도.psd 는 문서가 700×450 인데 배경 레이어가 1813×799 였다.

    ⚠️ **`visible` 을 먼저 본다.** 숨겨진 레이어는 대개 이전 버전이라 크기만 크고 비어 있다
    (같은 파일의 `레이어 1` 은 1822×810 인데 사실상 빈 이미지였다)."""
    cand = [(l, px) for l, px, ov in layers(psd) if not ov and px > 0]
    if not cand:
        return None
    vis = [t for t in cand if t[0].visible]
    return max(vis or cand, key=lambda t: t[1])[0]


def crop_ui(im, margin_ratio=0.06):
    """웹 캡처 가장자리의 UI 를 잘라낸다. 비율은 실측 기반의 기본값일 뿐이다."""
    w, h = im.size
    mx, my = int(w * margin_ratio), int(h * margin_ratio)
    return im.crop((mx, my, w - mx, h - my))


def main():
    ap = argparse.ArgumentParser(description="삽도 PSD → 베이스 지도 추출")
    ap.add_argument("psd")
    ap.add_argument("-o", "--out")
    ap.add_argument("--layer", help="레이어를 직접 지정")
    ap.add_argument("--list", action="store_true", help="레이어 구조만 출력")
    ap.add_argument("--crop-ui", action="store_true", help="가장자리 UI 잘라내기")
    a = ap.parse_args()

    psd = PSDImage.open(a.psd)
    ls = layers(psd)
    if a.list or not a.out:
        print(f"{Path(a.psd).name}  문서 {psd.width}×{psd.height}  레이어 {len(ls)}")
        base = pick_base(psd)
        for l, px, ov in sorted(ls, key=lambda t: -t[1]):
            mark = "베이스?" if l is base else ("오버레이" if ov else "")
            print(f"  {l.size[0]:>5}×{l.size[1]:<5} vis={str(l.visible):<5} {l.name[:30]:<32} {mark}")
        if not a.out:
            return

    if a.layer:
        tgt = next((l for l, _, _ in ls if l.name == a.layer), None)
        if tgt is None:
            sys.exit(f"레이어를 찾지 못했습니다: {a.layer}")
    else:
        tgt = pick_base(psd)
        if tgt is None:
            sys.exit("베이스 후보가 없습니다 — --list 로 확인 후 --layer 로 지정하세요")

    im = tgt.composite()
    if a.crop_ui:
        im = crop_ui(im)
    im.save(a.out)
    print(f"베이스 '{tgt.name}' {im.size} → {a.out}")


if __name__ == "__main__":
    main()

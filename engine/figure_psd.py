#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""삽도를 **레이어드 PSD** 로 떨어뜨린다 (클라이언트 요청, 계획 §9-2).

`figure_overlay.render()` 는 요소를 베이스 위에 **눌러 담아** JPG 한 장을 낸다.
그 그림은 고치려면 다시 그려야 한다. 여기서는 같은 spec 을 **층으로** 낸다 —
베이스 지도 한 층 + 요소마다 한 층. 실무자가 포토샵에서 층을 끄거나 옮겨 고친다.

    python engine/figure_psd.py spec.json -o 지역개황도.psd
    python engine/figure_psd.py --demo -o demo.psd

## 설계 — 그리는 코드는 한 벌이다

층 렌더가 `_draw_element()` 를 **그대로** 쓴다 (평면 렌더와 같은 분기). 층용으로
분기를 복사하면 두 벌이 조용히 갈라진다 — 이 저장소가 두 번 데인 자리다
(`hwpx.md` §검증 원칙).

## 검증 — 층을 합치면 평면과 같아야 한다

`verify()` 가 층을 순서대로 합성해 `render()` 결과와 픽셀 비교한다. **다른 근거**다:
평면은 한 캔버스에 누적해 그리고, 층은 각자 투명판에 그린 뒤 합친다. 둘이 맞으면
층 분리가 그림을 바꾸지 않았다는 뜻이다.

⚠️ **반투명 요소는 밑그림을 읽으면 안 된다.** 예전 `draw_parcels` 의 채색이
현재 화면과 섞는 방식이라 투명판에서는 검정과 섞여 색이 죽었다. 알파로 얹도록
고쳤고(수식 동일), 그래서 층 분리가 가능해졌다. 남는 차이는 반올림 1 LSB 뿐이다.

⚠️ **압축은 raw 만.** pytoshop 의 RLE 는 cython 모듈이 Python 3.13 에서 안 빌드된다.
   그래서 층을 **내용 bbox 로 잘라** 용량을 줄인다 (빈 투명 영역을 저장하지 않는다).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from figure_overlay import _draw_element, _helpers, canvas_for, render  # noqa: E402

try:
    import pytoshop
    # ⚠️ `pytoshop.nested_layers` 가 아니다 — 1.2.1 은 `pytoshop.user.nested_layers` 다.
    from pytoshop import image_data
    from pytoshop.enums import ColorMode, Compression
    from pytoshop.user import nested_layers
except ImportError:
    pytoshop = None

def _patch_layer_names():
    """층 이름 뒤에 붙는 **널 문자를 없앤다.**

    pytoshop 은 유니코드 문자열을 `길이 = 글자수+1` + 끝에 `\\0` 로 쓴다. NAS 실제
    포토샵 PSD 를 psd-tools 로 읽으면 이름이 `'배경'`, `'축척'` 처럼 깨끗한데
    우리 것은 `'반경 원\\x00'` 이 된다 — 층 이름은 **실무자가 보는 글자**라
    실물 관행에 맞춘다."""
    if pytoshop is None:
        return
    import struct

    from pytoshop import util
    if getattr(util, "_명칭_교정됨", False):
        return

    def encode(s):
        return struct.pack(">L", len(s)) + s.encode("utf_16_be")

    util.encode_unicode_string = encode
    # tagged_block 이 import 시점에 이름을 끌어다 쓴 경우까지 덮는다
    from pytoshop import tagged_block
    if hasattr(tagged_block, "encode_unicode_string"):
        tagged_block.encode_unicode_string = encode
    util._명칭_교정됨 = True


_patch_layer_names()

# 요소 종류 → 실무자가 읽을 층 이름. 포토샵 층 목록에 이대로 뜬다.
LAYER_NAME = {
    "target": "표적 마커", "label": "라벨", "boundary": "사업지 경계",
    "parcels": "사업지 필지", "zone": "지정구역 채색", "flow": "흐름 화살표",
    "rings": "반경 원", "polar": "정온시설 분포", "watercourse": "수계 모식도",
    "title": "제목", "admin": "행정구역명", "river": "하천명", "place": "지명",
    "scalebar": "축척", "north": "방위표", "legend": "범례",
}


def layer_label(el, seq):
    """층 이름 — 종류 + 그 요소의 글자(있으면). 같은 종류가 여럿이면 번호를 붙인다."""
    base = LAYER_NAME.get(el["type"], el["type"])
    text = el.get("text") or el.get("label")
    name = f"{base} · {text}" if text else base
    return f"{name} {seq}" if seq else name


def element_layer(size, el, k, F, pos, warn=None):
    """요소 하나를 **정확한 알파를 가진 투명 층**으로 뽑는다 (검정·흰색 두 판 기법).

    ⚠️ 투명판에 그냥 그리면 안 된다. Pillow 는 안티에일리어싱 글자를 그릴 때
    바탕색 쪽으로 **단순 보간**한다 — 투명판(0,0,0,0)에서는 RGB 가 `색×덮임` 이 되어
    사실상 프리멀티플라이 값이 남는다. 그것을 straight alpha 로 알고 합성하면
    가장자리가 한 번 더 곱해져 흐려진다. 실제로 반경 원 라벨에서 **최대 18** 차이가
    났다 (골든 지역개황도 3건). 데모는 라벨·범례가 불투명 상자를 먼저 깔아 안 걸렸다.

    같은 그리기를 **검정 판과 흰색 판**에 각각 하면 알파가 정확히 나온다:
        검정 위: Rb = C·a          흰색 위: Rw = C·a + 255·(1−a)
        ⇒ a = 1 − (Rw − Rb)/255,   C = Rb / a
    그리기 내부가 어떻게 굴든 성립한다 (source-over 이기만 하면).

    부수 효과 — **밑그림을 읽는 요소를 여기서 잡는다.** 밑그림에 의존하면 두 판의
    결과가 채널마다 어긋나 알파가 일치하지 않는다. 그럴 때 경고를 남긴다."""
    black = Image.new("RGBA", size, (0, 0, 0, 255))
    white = Image.new("RGBA", size, (255, 255, 255, 255))
    _draw_element(black, el, k, F, pos)
    _draw_element(white, el, k, F, pos)

    b = np.asarray(black.convert("RGB")).astype(np.float64)
    w = np.asarray(white.convert("RGB")).astype(np.float64)
    a_ch = 255.0 - (w - b)                       # 채널별 알파 추정
    spread = float(np.abs(a_ch.max(axis=2) - a_ch.min(axis=2)).max())
    if spread > 8 and warn is not None:
        warn.append(f"{el['type']}: 채널별 알파가 {spread:.0f} 어긋난다 — "
                    f"밑그림을 읽는 그리기일 수 있다")
    a = np.clip(a_ch.mean(axis=2), 0, 255)
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.where(a[..., None] > 0.5, b / np.maximum(a[..., None] / 255.0, 1e-6), 0.0)
    arr = np.dstack([np.clip(c, 0, 255), a]).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def render_layers(spec):
    """(문서 크기, [(이름, RGBA 이미지, (left, top))]) — 맨 앞이 베이스 층.

    각 요소를 따로 층으로 뽑은 뒤 내용 bbox 로 자른다. 자르는 이유는 용량이다
    (raw 압축뿐이라 빈 화면도 그대로 저장된다)."""
    canvas = canvas_for(spec)
    W, H = canvas.size
    k, F, pos = _helpers(canvas)          # ★ 배율은 문서 크기로 정한다 — 층마다 다르면 어긋난다

    out = [("베이스 지도", canvas.copy(), (0, 0))]
    seen, warn = {}, []
    for el in spec.get("elements", []):
        layer = element_layer((W, H), el, k, F, pos, warn)
        bbox = layer.getbbox()
        if bbox is None:
            print(f"  [빈 층] {el['type']} — 그려진 것이 없다 (건너뜀)")
            continue
        t = el["type"]
        seen[t] = seen.get(t, 0) + 1
        # 같은 종류가 하나뿐이면 번호를 안 붙인다 (`라벨` vs `라벨 2`)
        total = sum(1 for e in spec.get("elements", []) if e["type"] == t)
        out.append((layer_label(el, seen[t] if total > 1 else 0),
                    layer.crop(bbox), (bbox[0], bbox[1])))
    for m in dict.fromkeys(warn):
        print(f"  ⚠️ {m}")
    return (W, H), out


def flatten(size, layers):
    """층을 순서대로 합성 — `verify()` 가 평면 렌더와 대조할 때 쓴다."""
    W, H = size
    acc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for _, im, (l, t) in layers:
        pad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pad.paste(im, (l, t))
        acc.alpha_composite(pad)
    return acc


def verify(spec, tol=2):
    """층 합성 == 평면 렌더. 반올림 tol 이내면 통과.

    ⚠️ 통과가 '그림이 맞다'는 뜻은 아니다 — **층 분리가 그림을 바꾸지 않았다**는 뜻이다.
    삽도가 실제로 맞는지는 정답 대조(08-20 평창 5종)와 육안이 판정한다."""
    flat, _ = render(spec)
    size, layers = render_layers(spec)
    comp = flatten(size, layers)
    a = np.asarray(flat.convert("RGB")).astype(int)
    b = np.asarray(comp.convert("RGB")).astype(int)
    dmax = int(np.abs(a - b).max())
    npx = int((np.abs(a - b).sum(axis=2) > 0).sum())
    return dmax <= tol, dmax, npx, len(layers)


def write_psd(size, layers, out_path):
    """pytoshop 으로 PSD 쓰기 — raw 압축 (RLE 는 이 환경에서 안 빌드된다)."""
    if pytoshop is None:
        sys.exit("pytoshop 이 필요합니다: .venv/bin/pip install pytoshop")
    W, H = size
    items = []
    for name, im, (l, t) in layers:
        a = np.asarray(im.convert("RGBA"))
        h, w = a.shape[:2]
        items.append(nested_layers.Image(
            name=name, visible=True, opacity=255,
            top=t, left=l, bottom=t + h, right=l + w,
            channels={0: a[:, :, 0], 1: a[:, :, 1], 2: a[:, :, 2], -1: a[:, :, 3]},
            color_mode=ColorMode.rgb))
    # 포토샵 층 목록은 **위가 마지막에 그린 것**이다 — 그린 순서의 역순으로 넣는다.
    # ⚠️ `size` 는 **(폭, 높이)** 다. numpy 관행을 따라 (높이, 폭)으로 줬더니 문서가
    #    1600×1200 → 1200×1600 으로 뒤집혔다. 층 좌표는 맞은 채 캔버스만 돌아가
    #    포토샵에서 그림이 화면 밖으로 나간다 — 층 목록만 보면 멀쩡해 보인다.
    psd = nested_layers.nested_layers_to_psd(
        list(reversed(items)), color_mode=ColorMode.rgb, compression=Compression.raw,
        size=(W, H))

    # ⚠️ **병합 미리보기를 직접 채운다.** pytoshop 은 이 자리를 전부 0 으로 쓴다 —
    #    포토샵은 층에서 다시 합성하니 멀쩡하지만, Finder 썸네일·미리보기·
    #    이미지 뷰어는 이 미리보기를 그대로 보여준다 (= 새까만 그림).
    #    실무자가 파일 목록에서 삽도를 알아보려면 여기가 채워져 있어야 한다.
    merged = np.asarray(flatten((W, H), layers).convert("RGB"))
    psd.image_data = image_data.ImageData(
        channels=np.ascontiguousarray(merged.transpose(2, 0, 1)),
        compression=Compression.raw)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        psd.write(f)
    return out_path


def verify_written(path, spec, tol=2):
    """**쓴 파일을 다시 읽어** 평면 렌더와 대조 — `verify()` 와 다른 근거다.

    `verify()` 는 내가 만든 층 목록을 내 `flatten()` 으로 합친다. 둘이 같은 가정을
    공유하므로 **파일에 잘못 쓰는 실수는 못 잡는다.** 실제로 그랬다 —
    문서 크기를 (높이, 폭)으로 줘서 캔버스가 1600×1200 → 1200×1600 으로 돌아갔는데
    `verify()` 는 통과했고 층 목록도 멀쩡해 보였다. psd-tools 로 되읽어서야 드러났다.
    (`hwpx.md` §검증 원칙 — 검사는 수정과 다른 근거를 써야 한다.)"""
    try:
        from psd_tools import PSDImage
    except ImportError:
        print("  [건너뜀] psd-tools 없음 — 재판독 검사를 못 한다")
        return True, None, None
    psd = PSDImage.open(path)
    flat, _ = render(spec)
    if (psd.width, psd.height) != flat.size:
        return False, f"문서 크기 {psd.width}×{psd.height} ≠ 렌더 {flat.width}×{flat.height}", None

    # ★ `force=True` — **층에서 다시 합성**하게 한다. 이것을 빼면 psd-tools 가
    #   병합 미리보기를 그대로 돌려주는데, 그 미리보기는 우리가 방금 써 넣은 것이라
    #   **자기가 쓴 것을 자기가 읽고 통과**한다 (검사가 아니라 메아리다).
    comp = psd.composite(force=True).convert("RGB")
    a = np.asarray(flat.convert("RGB")).astype(int)
    b = np.asarray(comp).astype(int)
    dmax = int(np.abs(a - b).max())
    if dmax > tol:
        return False, None, dmax

    # 미리보기도 따로 본다 — 새까맣게 나가면 Finder 썸네일이 검정이 된다.
    prev = np.asarray(psd.numpy())
    if float(prev.max()) == 0.0:
        return False, "병합 미리보기가 비었다 (썸네일이 검정)", dmax
    return True, None, dmax


def build(spec, out_path, check=True):
    size, layers = render_layers(spec)
    for name, im, (l, t) in layers:
        print(f"  층 {name:28s} {im.width:>5}×{im.height:<5} @({l},{t})")
    p = write_psd(size, layers, out_path)
    mb = p.stat().st_size / 1e6
    print(f"→ {p}  {size[0]}×{size[1]} · 층 {len(layers)} · {mb:.1f}MB")
    if check:
        ok, dmax, npx, n = verify(spec)
        print(f"검증① 층 합성 vs 평면 렌더: {'일치' if ok else '⚠️ 불일치'} "
              f"(최대 차이 {dmax}, 차이 픽셀 {npx:,})")
        if not ok:
            sys.exit("층 분리가 그림을 바꿨다 — 요소 그리기가 밑그림을 읽고 있는지 확인할 것")
        ok2, why, dmax2 = verify_written(p, spec)
        print(f"검증② PSD 재판독 vs 평면 렌더: "
              f"{'일치' if ok2 else '⚠️ 불일치'}"
              + (f" (최대 차이 {dmax2})" if dmax2 is not None else "")
              + (f" — {why}" if why else ""))
        if not ok2:
            sys.exit("쓴 파일이 렌더와 다르다 — 문서 크기·층 좌표를 확인할 것")
    return p


def main():
    ap = argparse.ArgumentParser(description="삽도 spec → 레이어드 PSD")
    ap.add_argument("spec", nargs="?", help="figure_overlay spec JSON")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--demo", action="store_true", help="전 요소 시험판")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()

    if a.demo:
        from figure_overlay import demo_spec
        spec = demo_spec()
    else:
        if not a.spec:
            sys.exit("spec 파일이 필요합니다 (또는 --demo)")
        spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    build(spec, a.out, check=not a.no_check)


if __name__ == "__main__":
    main()

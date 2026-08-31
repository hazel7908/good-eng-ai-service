#!/usr/bin/env python3
"""
삽도 오버레이 — 베이스 지도 위에 라벨·마커·경계선·화살표를 얹는다.

지역개황 삽도는 3층이다 (docs/20260819_통계원자료_소싱실증.md §6):

    ① 베이스 지도   국토지리정보원 지형도 · 환경부 EGIS 자연환경현황도 · 식생도
                    → **사람이 캡처한다.** 이 모듈은 건드리지 않는다
    ② 오버레이      라벨 박스 · 표적 마커 · 경계선 · 구역 채색 · 흐름 화살표 · 지명
                    → **이 모듈이 그린다**
    ③ 장식          범례 · 축척 막대 · 방위표
                    → 이 모듈이 그린다 (고정 서식)

**좌표는 픽셀이다.** 실무자가 베이스 지도 위에서 점을 찍으면 그 좌표를 spec 에 적는 방식이
현실적인 시작점이다 (미팅 §5 "어디에 그릴지가 관건" 에 대한 답).

사용:
    python engine/figure_overlay.py spec.json -o 출력.jpg
    python engine/figure_overlay.py --demo            # 데모 spec 렌더 (자체 확인)

spec 예:
    {"base": "지형도.jpg",
     "elements": [
       {"type": "target",   "at": [980, 470]},
       {"type": "label",    "at": [1010, 540], "text": "사업계획지구", "from": [980, 470]},
       {"type": "boundary", "points": [[900,600],[1100,610],[1080,760],[890,740]], "color": "yellow"},
       {"type": "zone",     "points": [[1400,200],[1520,210],[1500,420],[1390,400]],
                            "color": "cyan", "label": "상수원보호구역"},
       {"type": "flow",     "path": [[300,900],[520,860],[760,700],[980,520]], "count": 6},
       {"type": "place",    "at": [600, 800], "text": "섬강"},
       {"type": "scalebar", "at": [1500, 2500], "length_px": 300, "label": "0.5km"},
       {"type": "north",    "at": [1850, 120]}
     ]}
"""
import argparse, json, math, sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow 가 필요합니다: .venv/bin/pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent

# ── 스타일 — 골든셋 삽도에서 실측한 값 (원주 지역개황 BinData) ─────────────────
# 색을 손으로 정하지 않았다. 유역도·생태자연도·식생보전등급도에서 픽셀을 뽑았다.
STYLE = {
    "label_bg":     (99, 99, 99),      # 라벨 박스 배경 — 회색
    "label_fg":     (255, 242, 0),     # 라벨 글자 — 노랑
    "label_edge":   (200, 30, 30),     # 라벨 테두리 — 빨강
    "target":       (206, 20, 30),     # 표적 마커 — 빨강 동심원
    # 경계선 색은 **삽도 종류마다 다르다** — 골든셋 실측:
    #   노랑=생태·자연도 · 빨강=식생보전등급도 · 파랑=국토환경성평가지도
    "boundary": {"yellow": (255, 242, 0), "red": (237, 28, 36), "blue": (1, 13, 255)},
    "zone":         (0, 255, 230),     # 구역 채색 — 청록 (상수원보호구역)
    "zone_alpha":   150,
    "flow":         (108, 190, 237),   # 하천 흐름 화살표 — 하늘색
    "place":        (31, 73, 177),     # 지명 — 파랑
    "deco":         (0, 0, 0),
    # 수계흐름모식도 — 괴산 골든셋 픽셀 실측
    "flow_site":    (28, 226, 255),    # 사업계획지구 박스 — 하늘색
    "flow_river":   (63, 106, 247),    # 하천 박스 — 파랑
}
# ── 기본 배치 — **골든셋 정답에서 실측한 위치**를 비율로 환산 ──────────────────
# 괴산 국토환경성평가지도(700×450) 기준: 범례 (508,11) · 등급띠 (5,416).
# 비율이라 삽도 크기가 달라져도 같은 자리에 놓인다. spec 에 `at` 을 주면 그쪽이 이긴다.
DEFAULT_POS = {
    "legend_v":  (0.708, 0.024),   # 세로 범례 — 오른쪽 위 (정답 508,11 · 박스가 커져 살짝 당김)
    "legend_h":  (0.007, 0.924),   # 가로 등급 띠 — 왼쪽 아래 (정답 5, 416)
    "north":     (0.927, 0.800),   # 방위표 중심 — 축척 **위쪽** 오른쪽
    "scalebar":  (0.530, 0.930),   # 축척 막대 시작 — 등급 띠 **오른쪽 옆**, 같은 줄
}
DEFAULT_SCALEBAR_RATIO = 0.200     # 축척 막대 길이 = 이미지 폭의 20% (정답 140/700)

# (경로, ttc 인덱스) — 골든셋 삽도의 라벨이 굵은 글씨라 **볼드를 기본**으로 쓴다.
FONT_CANDIDATES = [
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 6),        # Apple SD Gothic Neo Bold
    ("/System/Library/Fonts/Supplemental/NanumGothicBold.ttf", 0),
    ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", 0),  # 볼드가 없을 때
    ("C:/Windows/Fonts/malgun.ttf", 0),
]


def _font(size):
    for p, idx in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default()      # 한글이 깨진다 — 폰트를 설치할 것


def _scaled(im, base=1400):
    """요소 크기를 이미지 크기에 맞춘다. 삽도는 700~4,800px 로 폭이 제각각이다.

    기준 폭은 1,400 이다. 2,000 으로 잡으면 골든셋 최종본(700×450)에서 글자가 9px 까지
    작아져 읽히지 않는다.

    ⚠️ **위로도 막는다.** 정답 삽도는 커진다고 글자를 비례해 키우지 않는다 —
       지역개황도(4,449px)의 글자가 생태자연도(1,181px)와 절대 크기가 비슷하다.
       상한이 없으면 4,352px 짜리에서 배율 3.1 이 되어 반경 라벨이 서로 붙어 버렸다.

    상한 **1.2** 는 짐작이 아니라 실측이다 — 정답 지역개황도의 `1.0km` 텍스트 레이어가
    95×36px 이다 (평창·청주 PSD). 기준 폰트 30px 이니 36/30 = 1.2. 처음에 2.0 으로
    뒀더니 4,449px 판에서 글자가 60px 이 되어 반경 라벨 여섯이 서로 붙었다 —
    상한을 두고도 같은 증상이 남아 있었다."""
    return max(0.6, min(1.2, im.width / base))


# ── ② 오버레이 ──────────────────────────────────────────────────────────────
def draw_target(d, at, k=1.0):
    """표적 마커 — 동심원 3겹. 유역도에서 사업계획지구를 가리키는 그 표시다."""
    x, y = at
    for r, w in ((26 * k, 7 * k), (15 * k, 6 * k), (5 * k, 5 * k)):
        d.ellipse([x - r, y - r, x + r, y + r], outline=STYLE["target"], width=int(max(1, w)))


def draw_label(d, at, text, k=1.0, frm=None, font=None):
    """라벨 박스 + 지시선. `사업계획지구` 처럼 회색 바탕에 노란 글자."""
    font = font or _font(int(34 * k))
    pad = int(10 * k)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    w, h = r - l, b - t
    x, y = at
    box = [x - pad, y - pad, x + w + pad, y + h + pad * 1.4]
    if frm:                                   # 마커 → 라벨 지시선
        d.line([frm, (x + w / 2, y)], fill=STYLE["label_edge"], width=int(max(2, 4 * k)))
    d.rectangle(box, fill=STYLE["label_bg"], outline=STYLE["label_edge"], width=int(max(2, 3 * k)))
    d.text((x - l, y - t), text, font=font, fill=STYLE["label_fg"])
    return box


def draw_boundary(d, points, color="yellow", k=1.0):
    """사업계획지구 경계선. 설계도서 경계 좌표가 있으면 그대로 들어온다."""
    c = STYLE["boundary"].get(color, STYLE["boundary"]["yellow"])
    # 최소 굵기 5 — 삽도가 700px 급으로 작으면 비례 굵기가 1~3px 로 얇아진다.
    # 골든셋 실측(국토환경성평가지도)의 경계선이 4~5px 였다.
    d.line([tuple(p) for p in points] + [tuple(points[0])], fill=c, width=int(max(5, 9 * k)),
           joint="curve")


def draw_parcels(im, polygons, color="red", k=1.0, width=None, fill=0):
    """여러 필지를 **한 덩어리로 합쳐** 바깥 선만 그린다.

    정답 삽도는 필지 경계를 보여주지 않는다 — 사업지 외곽선 하나다. 필지별로 선을 그으면
    안쪽에 격자가 생겨 실제와 달라진다.

    합집합을 마스크로 낸다. 폴리곤을 마스크에 채우고, 안쪽을 깎아낸 것과의 차이가 곧
    테두리다 — 기하 라이브러리 없이 Pillow 만으로 된다.

    `fill` 을 주면 안쪽을 그 투명도로 칠한다 (정답의 노란 신규부지가 그렇다)."""
    from PIL import ImageChops, ImageFilter
    c = STYLE["boundary"].get(color, STYLE["boundary"]["yellow"])
    w = width or int(max(4, 6 * k))

    mask = Image.new("L", im.size, 0)
    md = ImageDraw.Draw(mask)
    for poly in polygons:
        if len(poly) >= 3:
            md.polygon([tuple(p) for p in poly], fill=255)

    if fill:
        # ⚠️ **밑그림과 섞지 않는다.** 예전에는 `blend(im, tint, fill)` 로 현재 화면과
        # 섞었는데, 그러면 이 요소를 **투명 레이어에 따로 그릴 수 없다** (빈 레이어의
        # RGB 는 검정이라 색이 죽는다). 같은 결과를 알파로 얹으면 밑그림을 안 읽는다 —
        # 베이스 위에 합성하면 base*(1-fill) + c*fill 로 수식이 같다 (PSD 층 분리 전제).
        if im.mode == "RGBA":
            wash = Image.new("RGBA", im.size, (0, 0, 0, 0))
            wash.paste(Image.new("RGBA", im.size, c + (int(round(255 * fill)),)), mask=mask)
            im.alpha_composite(wash)
        else:
            im.paste(Image.blend(im.convert("RGB"), Image.new("RGB", im.size, c), fill),
                     mask=mask)

    # 안쪽을 w 만큼 깎아 낸 것과의 차이 = 두께 w 의 테두리
    inner = mask
    for _ in range(max(1, w // 2)):
        inner = inner.filter(ImageFilter.MinFilter(3))
    edge = ImageChops.subtract(mask, inner)
    im.paste(Image.new("RGB", im.size, c), mask=edge)


def draw_zone(im, points, label=None, k=1.0, font=None):
    """구역 채색 — 반투명 폴리곤. 상수원보호구역·수변구역 같은 지정 구역."""
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.polygon([tuple(p) for p in points], fill=STYLE["zone"] + (STYLE["zone_alpha"],))
    im.alpha_composite(layer)
    if label:
        cx = sum(p[0] for p in points) / len(points)
        cy = min(p[1] for p in points)
        d = ImageDraw.Draw(im)
        f = font or _font(int(30 * k))
        d.text((cx, cy - 40 * k), label, font=f, fill=STYLE["place"], anchor="mb",
               stroke_width=int(max(2, 4 * k)), stroke_fill=(255, 255, 255))


def draw_flow(d, path, count=5, k=1.0):
    """하천 흐름 화살표 — 경로를 따라 등간격 배치.

    미팅 §5 의 "유수 방향 화살표". 경로만 찍어주면 방향·간격은 자동이라
    **반자동**으로 부를 만하다."""
    pts = [tuple(p) for p in path]
    seglen = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seglen)
    if total == 0:
        return
    size = 34 * k
    for n in range(count):
        target = total * (n + 0.5) / count
        acc = 0
        for i, sl in enumerate(seglen):
            if acc + sl >= target:
                t = (target - acc) / sl
                x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t
                y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t
                ang = math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
                tip = (x + size * math.cos(ang), y + size * math.sin(ang))
                left = (x + size * math.cos(ang + 2.5), y + size * math.sin(ang + 2.5))
                right = (x + size * math.cos(ang - 2.5), y + size * math.sin(ang - 2.5))
                d.polygon([tip, left, right], fill=STYLE["flow"])
                break
            acc += sl


def draw_title(im, at, text, width, height, k=1.0, size=None):
    """삽도 표제 — **리본 띠**. 정답 지역개황도가 상단 중앙에 두는 그 장식이다.

    골든셋 7건이 **완전히 일치한다** — 중심 (0.50, 0.055) · 폭 = 캔버스 폭의 16.7% ·
    높이 = 캔버스 높이의 5.8%. 사업이 달라도 같다.

    모양은 평창 PSD 에서 실측했다: 흰 바탕에 검은 테두리, 위아래 변이 중앙에서
    살짝 처지고(높이의 11%) 좌우 끝이 안으로 파인다(폭의 5.5%). 글자는 낱자를
    벌려 쓴다."""
    d = ImageDraw.Draw(im)
    cx, cy = at
    w, h = width, height
    x0, y0 = cx - w / 2, cy - h / 2
    sag = h * 0.11
    notch = w * 0.055

    def curve(top):
        pts = []
        for i in range(41):
            t = i / 40
            x = x0 + w * t
            off = sag * (1 - (2 * t - 1) ** 2)
            pts.append((x, y0 + off if top else y0 + h - off))
        return pts

    poly = curve(True) + [(x0 + w - notch, cy)] + curve(False)[::-1] + [(x0 + notch, cy)]
    d.polygon(poly, fill=(255, 255, 255))
    d.line(poly + [poly[0]], fill=(0, 0, 0), width=max(2, round(3 * k)))

    px = size or int(h * 0.45)
    f = _font(px)
    spaced = " ".join(text)
    d.text((cx, cy), spaced, font=f, fill=(0, 0, 0), anchor="mm",
           stroke_width=max(1, round(px * 0.06)), stroke_fill=(255, 255, 255))


def draw_admin(im, at, text, k=1.0, size=None):
    """행정구역명 — **낱자를 하나씩 박스에 담아** 벌려 놓는다.

    정답 지역개황도가 `평 창 군` 처럼 글자마다 회색 박스를 씌운다. 지도에 인쇄된
    지명과 구별되라고 그렇게 쓴다 — 붙여 쓰면 배경 글자에 묻힌다."""
    d = ImageDraw.Draw(im)
    px = size or int(52 * k)
    f = _font(px)
    pad = max(4, round(px * 0.12))
    box = px + pad * 2
    gap = round(px * 0.14)
    total = len(text) * box + (len(text) - 1) * gap
    x = at[0] - total / 2
    y = at[1] - box / 2
    for ch in text:
        d.rectangle([x, y, x + box, y + box], fill=(238, 238, 238),
                    outline=(90, 90, 90), width=max(2, round(px * 0.045)))
        d.text((x + box / 2, y + box / 2), ch, font=f, fill=(20, 20, 20), anchor="mm")
        x += box + gap


def draw_river(im, at, text, k=1.0, size=None, vertical=True):
    """하천명 — **낱자를 원 안에** 담아 늘어놓는다.

    정답 수계도가 `창` `리` `천` 을 하늘색 원에 하나씩 넣어 물길을 따라 세운다.
    행정구역명(네모 박스)과 모양을 달리해 **한눈에 구분되게** 하는 장치다."""
    d = ImageDraw.Draw(im)
    px = size or int(46 * k)
    f = _font(px)
    r = px * 0.72
    gap = r * 2 + max(3, px * 0.10)
    n = len(text)
    x, y = at
    if vertical:
        y -= gap * (n - 1) / 2
    else:
        x -= gap * (n - 1) / 2
    for ch in text:
        d.ellipse([x - r, y - r, x + r, y + r], fill=(176, 224, 245),
                  outline=(28, 78, 150), width=max(2, round(px * 0.06)))
        d.text((x, y), ch, font=f, fill=(20, 40, 90), anchor="mm")
        if vertical:
            y += gap
        else:
            x += gap


def draw_place(d, at, text, k=1.0, font=None):
    """지명 — 흰 테두리를 두른 파란 글자. 지도 위에서 읽히게 하는 표준 처리다."""
    f = font or _font(int(38 * k))
    d.text(at, text, font=f, fill=STYLE["place"], anchor="mm",
           stroke_width=int(max(2, 5 * k)), stroke_fill=(255, 255, 255))


# 방위 16방 — 보고서 PP 표가 쓰는 표기 그대로. 화면 기준 각도(0°=오른쪽, 시계방향).
BEARING = {"북": -90, "북북동": -67.5, "북동": -45, "동북동": -22.5, "동": 0,
           "동남동": 22.5, "남동": 45, "남남동": 67.5, "남": 90, "남남서": 112.5,
           "남서": 135, "서남서": 157.5, "서": 180, "서북서": 202.5,
           "북서": 225, "북북서": 247.5}


def _overlaps(a, b, pad=0):
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or
                a[3] + pad < b[1] or b[3] + pad < a[1])


def draw_rings(im, origin, radii_m, px_per_m, k=1.0, font=None,
               label_deg=213, color=(255, 255, 255), short=None, fill=None):
    """사업계획지구 중심 **반경 동심원** — 위성사진·지역개황도의 표준 구성이다.

    정답 삽도(괴산)는 0.25 · 0.5 · 0.75 · 1.0km 네 겹을 두르고 원마다 라벨을 단다.
    조사할 값이 하나도 없다 — **중심 좌표와 축척만 있으면 완전히 자동으로 나온다.**
    둘 다 `map_fetch` 가 돌려주는 값(`center_px` · `px_per_m`)이다.

    라벨은 원 위 `label_deg` 방향(기본 남서)에 놓는다. 정답이 그 자리를 쓴다.

    ⚠️ 원이 여럿이고 라벨을 한 방향에 몰면 글자가 겹친다. 정답 지역개황도는 반경 6개를
       동쪽 한 줄로 늘어놓는데 그때는 `반경 1km` 가 아니라 **`1.0km`** 로 줄여 쓴다.
       `short` 를 안 주면 원 4개를 넘을 때 자동으로 줄인다.

    ⚠️ **선 색이 삽도마다 다르다.** 위성사진은 어두운 배경이라 흰 선(기본값)인데,
       지역개황도는 밝은 지형도라 흰 선이 **보이지 않는다** — 정답은 회색
       `(127,127,125)` 을 쓴다 (청주 실측). 지역개황도에는 `fill` 도 준다:
       정답은 원마다 옅은 회색을 겹쳐 칠해 중심으로 갈수록 어두워진다
       (중심 −13/−22/−21, 바깥 0)."""
    if short is None:
        short = len(radii_m) > 4
    ox, oy = origin
    if fill:
        # ⚠️ **가장 바깥 원 안쪽을 한 번만** 칠한다. 원마다 겹쳐 칠하면 중심이 진해지는데
        #    정답은 그렇지 않다 — 원 영역이 고르게 덮여 있다 (청주 실측: 중심 −13/−22/−21,
        #    중간 −24/−25/−37 로 중심이 오히려 옅다).
        wash = Image.new("RGBA", im.size, (0, 0, 0, 0))
        r = max(radii_m) * px_per_m
        ImageDraw.Draw(wash).ellipse([ox - r, oy - r, ox + r, oy + r], fill=tuple(fill))
        im.alpha_composite(wash) if im.mode == "RGBA" else \
            im.paste(Image.alpha_composite(im.convert("RGBA"), wash).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(im)
    f = font or _font(int(30 * k))
    w = max(2, round(2.5 * k))
    rad = math.radians(label_deg)
    for m in radii_m:
        r = m * px_per_m
        d.ellipse([ox - r, oy - r, ox + r, oy + r], outline=tuple(color), width=w)
        txt = f"{m/1000:.1f}km" if short else f"반경 {m/1000:g}km"
        tx, ty = ox + r * math.cos(rad), oy - r * math.sin(rad)
        tw = d.textlength(txt, font=f)
        # 원 선 위에 글자가 겹치지 않게 살짝 띄운다
        d.text((tx - tw / 2, ty - 20 * k), txt, font=f, fill=tuple(color),
               stroke_width=max(1, round(3 * k)), stroke_fill=(60, 60, 60))


def draw_polar(im, origin, items, px_per_m, k=1.0, font=None, dot=None,
               adjacent_m=None):
    """**정온시설 표를 그대로 그림으로 옮긴다.**

    지역개황 「정온 및 개발시설 현황」 표(2.9.1)와 소음진동·대기질의 영향예측지점 표는
    `라벨 | 방향 | 이격거리(m)` 형태다. 사업계획지구 중심 좌표와 축척만 주면 **표에서 바로
    마커 위치가 나온다** — 지점마다 좌표를 찍을 필요가 없다.

    ⚠️ 방향이 16방위라 실제 방위각과 최대 ±11°차가 난다. **정확한 위치가 필요하면
    좌표를 받아야 한다** — 이 배치는 분포를 보여주는 용도다.

    **라벨은 겹치면 자리를 옮긴다** — 같은 방향에 지점이 몰리면(괴산 서쪽 258m·335m 처럼)
    글자가 포개져 읽을 수 없기 때문이다. 마커는 데이터라 옮기지 않고 라벨만 피한다."""
    d = ImageDraw.Draw(im)
    f = font or _font(int(26 * k))
    ox, oy = origin
    r = 9 * k
    color = dot or STYLE["target"]

    # ① 마커 좌표부터 다 계산한다 (라벨 배치가 서로를 알아야 하므로)
    pts = []
    for it in items:
        deg = BEARING.get(it["dir"])
        if deg is None:
            continue                       # 모르는 방위는 건너뛴다 (환각 금지)
        dist = it.get("dist_m")
        if not isinstance(dist, (int, float)):
            # `인접` 같은 비수치 값(평창 농막1) — **숫자를 지어내지 않는다.**
            # 대신 `adjacent_m`(사업지 등가반경 √(면적/π) — 조서에서 유도되는 값)을
            # 주면 그 거리에 놓는다: "경계에 붙어 있다"는 뜻을 그림으로 옮긴 것이다.
            # 없으면 건너뛴다 — 빠지는 것이 지어내는 것보다 낫다.
            if adjacent_m is None:
                continue
            dist = adjacent_m
        rad = math.radians(deg)
        pts.append((ox + dist * px_per_m * math.cos(rad),
                    oy + dist * px_per_m * math.sin(rad), it["label"]))

    # ② 마커를 먼저 그리고, 그 상자를 라벨 회피 대상에 넣는다
    boxes = []
    for x, y, _ in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(255, 255, 255),
                  width=int(max(1, 2 * k)))
        boxes.append((x - r, y - r, x + r, y + r))

    # ③ 라벨 — 오른쪽이 기본, 겹치면 시계 방향으로 자리를 옮긴다
    gap = 14 * k
    placed = []
    for x, y, label in pts:
        tw = d.textlength(label, font=f)
        th = 26 * k
        cands = [(x + gap, y, "lm"), (x - gap - tw, y, "lm"),
                 (x - tw / 2, y - gap - th / 2, "lm"), (x - tw / 2, y + gap + th / 2, "lm"),
                 (x + gap, y - gap, "lm"), (x + gap, y + gap, "lm"),
                 (x - gap - tw, y - gap, "lm"), (x - gap - tw, y + gap, "lm")]
        spot = None
        for push in range(4):              # 다 겹치면 조금씩 더 밀어 본다
            for lx, ly, anchor in cands:
                bx = (lx, ly - th / 2 - push * 2 * k, lx + tw, ly + th / 2 + push * 2 * k)
                shifted = (bx[0], bx[1] - push * th * 0.8, bx[2], bx[3] - push * th * 0.8)
                if not any(_overlaps(shifted, b, 2 * k) for b in boxes):
                    spot = (lx, ly - push * th * 0.8, shifted)
                    break
            if spot:
                break
        if spot is None:                   # 끝내 자리가 없으면 기본 위치에 그냥 둔다
            spot = (x + gap, y, (x + gap, y - th / 2, x + gap + tw, y + th / 2))
        lx, ly, box = spot
        d.text((lx, ly), label, font=f, fill=(0, 0, 0), anchor="lm",
               stroke_width=int(max(2, 3 * k)), stroke_fill=(255, 255, 255))
        boxes.append(box)
        placed.append(label)
    return placed


# ── ③ 장식 ─────────────────────────────────────────────────────────────────
def draw_scalebar(d, at, length_px, label, k=1.0, font=None):
    """축척 막대. 골든셋 형식은 **`200m ─ 0 ─ 200m`** — 가운데가 0이고 양쪽에 거리다 (실측).

    at 은 막대의 왼쪽 끝. 라벨은 막대 **위쪽**에 둔다 (아래는 등급 범례 띠와 겹친다)."""
    x, y = at
    h = int(14 * k)
    for i in range(4):                       # 흑백 교대 4칸
        x0 = x + length_px * i / 4
        x1 = x + length_px * (i + 1) / 4
        d.rectangle([x0, y, x1, y + h], fill=(0, 0, 0) if i % 2 == 0 else (255, 255, 255),
                    outline=(0, 0, 0), width=int(max(1, 2 * k)))
    f = font or _font(int(26 * k))
    st = dict(font=f, fill=STYLE["deco"], stroke_width=int(max(2, 3 * k)),
              stroke_fill=(255, 255, 255))
    ly = y - 4 * k
    d.text((x, ly), label, anchor="md", **st)                       # 왼쪽 끝
    d.text((x + length_px / 2, ly), "0", anchor="md", **st)         # 가운데
    d.text((x + length_px, ly), label, anchor="md", **st)           # 오른쪽 끝


def draw_north(d, at, k=1.0, font=None, style="compass"):
    """방위표. 골든셋은 **8방향 별 나침반 + N/S/E/W 글자**를 쓴다 (실측)."""
    x, y = at
    f = font or _font(int(26 * k))
    if style == "arrow":                       # 단순 화살표 — 작은 삽도용
        s_ = 30 * k
        d.polygon([(x, y - s_), (x - s_ * .45, y + s_ * .6), (x, y + s_ * .25)], fill=(0, 0, 0))
        d.polygon([(x, y - s_), (x + s_ * .45, y + s_ * .6), (x, y + s_ * .25)],
                  outline=(0, 0, 0), width=int(max(1, 2 * k)))
        d.text((x, y + s_ + 4 * k), "N", font=f, fill=STYLE["deco"], anchor="ma")
        return
    R_, r_ = 42 * k, 13 * k                    # 별 나침반: 긴 살 4 + 짧은 살 4
    for i in range(8):
        a0 = math.radians(-90 + i * 45)
        rr = R_ if i % 2 == 0 else R_ * 0.62
        tip = (x + rr * math.cos(a0), y + rr * math.sin(a0))
        l = (x + r_ * math.cos(a0 + math.pi / 8), y + r_ * math.sin(a0 + math.pi / 8))
        r = (x + r_ * math.cos(a0 - math.pi / 8), y + r_ * math.sin(a0 - math.pi / 8))
        d.polygon([tip, l, (x, y)], fill=(255, 255, 255), outline=(0, 0, 0))
        d.polygon([tip, r, (x, y)], fill=(0, 0, 0))
    off = R_ + 14 * k
    for lab, (dx, dy) in (("N", (0, -1)), ("S", (0, 1)), ("E", (1, 0)), ("W", (-1, 0))):
        d.text((x + off * dx, y + off * dy), lab, font=f, fill=(0, 0, 0), anchor="mm",
               stroke_width=int(max(2, 3 * k)), stroke_fill=(255, 255, 255))


def draw_legend(im, at, items, k=1.0, font=None, title=None, orient="v", swatch="fill"):
    """범례. 골든셋에 두 형태가 있다 (실측) —

    ① 세로형 + 제목 띠 : `범 례` 회색 띠 아래 [속 빈 파란 사각형] 사업계획지구
    ② 가로형 띠        : 지도 아래 [● 1등급] [● 2등급] … 원형 견본

    items 는 [(색, 설명)]. 색은 `STYLE["boundary"]` 의 이름이거나 RGB 튜플."""
    d = ImageDraw.Draw(im)
    # 세로 범례는 **가로 띠보다 크게** 그린다 — 정답 박스가 184×73(700px 기준)이라
    # 띠와 같은 치수로 그리면 120×32 로 절반밖에 안 된다.
    if orient == "h":
        f = font or _font(int(26 * k))
        pad, sw, lh = int(11 * k), int(46 * k), int(38 * k)
    else:
        f = _font(int(38 * k))
        pad, sw, lh = int(16 * k), int(88 * k), int(64 * k)

    def color_of(c):
        if isinstance(c, (list, tuple)):
            return tuple(c)
        return STYLE["boundary"].get(c, STYLE["zone"] if c == "cyan" else (150, 150, 150))

    x, y = at
    if orient == "h":                          # ── 가로 띠 (등급 범례)
        # 폭은 **실제 그리는 것과 같은 식**으로 계산한다. 마지막 항목 뒤 gap 은 빼야
        # 오른쪽에 빈 여백이 남지 않는다 (정답 띠는 폭 354/700 로 짧다).
        r = int(9 * k)
        gap = int(13 * k)
        tw = int(6 * k)                        # 원과 글자 사이
        unit = [2 * r + tw + d.textlength(t, font=f) for _, t in items]
        w = pad * 2 + sum(unit) + gap * (len(items) - 1)
        h = lh + pad
        d.rectangle([x, y, x + w, y + h], fill=(255, 255, 255), outline=(0, 0, 0),
                    width=int(max(1, 2 * k)))
        cx, cy = x + pad, y + h / 2
        for (c, text), u in zip(items, unit):
            d.ellipse([cx, cy - r, cx + 2 * r, cy + r], fill=color_of(c), outline=(80, 80, 80))
            d.text((cx + 2 * r + tw, cy), text, font=f, fill=(0, 0, 0), anchor="lm")
            cx += u + gap
        return

    # ── 세로형 (+ 선택적 제목 띠)
    body_w = sw + pad * 3 + max(d.textlength(t, font=f) for _, t in items)
    th = lh if title else 0
    w, h = body_w, th + lh * len(items) + pad * 2
    d.rectangle([x, y, x + w, y + h], fill=(255, 255, 255), outline=(0, 0, 0),
                width=int(max(1, 2 * k)))
    if title:
        d.rectangle([x, y, x + w, y + th], fill=(228, 228, 228), outline=(0, 0, 0),
                    width=int(max(1, 2 * k)))
        d.text((x + w / 2, y + th / 2), title, font=f, fill=(0, 0, 0), anchor="mm")
    for i, (c, text) in enumerate(items):
        cy = y + th + pad + lh * i
        col = color_of(c)
        box = [x + pad, cy + 6 * k, x + pad + sw, cy + lh - 8 * k]
        if swatch == "outline":                # 속 빈 사각형 — 경계선 범례에 쓴다
            d.rectangle(box, outline=col, width=int(max(3, 5 * k)))
        else:
            d.rectangle(box, fill=col, outline=(0, 0, 0))
        d.text((x + pad * 2 + sw, cy + lh / 2), text, font=f, fill=(0, 0, 0), anchor="lm")


# ── 수계흐름모식도 (지도가 아니라 도식) ─────────────────────────────────────
def watercourse_size(nodes, k=1.0):
    """모식도가 필요로 하는 캔버스 크기. `canvas` 를 안 주면 이 값으로 만든다."""
    f = _font(int(44 * k))
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    pad, arrow = int(26 * k), int(110 * k)
    w = sum(probe.textlength(n, font=f) + pad * 2 for n in nodes) + arrow * (len(nodes) - 1)
    return int(w + 120 * k), int(440 * k)


def draw_watercourse(im, nodes, links, total=None, k=1.0):
    """**수계흐름모식도** — 지역개황 그림 2.8-3.

    `사업계획지구 → 미호강(국가) → 금강(국가)` 처럼 물이 흘러가는 순서를 박스와 화살표로
    보인다. 지도가 아니라 **직접 작도하는 도식**이라 외부 지도가 필요 없다.

    입력은 본문 서술에 이미 있는 값 그대로다 —
    *"구거를 따라 약 1.93km 유하하여 섬강(국가)에 합류… 총 유하거리는 약 34.54km"*

      nodes = ["사업계획지구", "미 호 강 (국 가)", "금 강 (국 가)"]
      links = ["15.96km", "21.56km"]        # 노드 사이 구간 거리
      total = "총 유하거리 54.08km"

    색·모양은 괴산 골든셋에서 실측했다 (사업지 하늘색 · 하천 파랑 · 검은 굵은 테두리)."""
    d = ImageDraw.Draw(im)
    f = _font(int(44 * k))
    fs = _font(int(40 * k))
    W, H = im.size
    pad = int(26 * k)
    bw = [d.textlength(n, font=f) + pad * 2 for n in nodes]
    arrow = int(110 * k)
    total_w = sum(bw) + arrow * (len(nodes) - 1)
    x = (W - total_w) / 2
    bh = int(120 * k)
    y = int(H * 0.20)
    lw = int(max(3, 6 * k))

    centers = []
    for i, (n, w) in enumerate(zip(nodes, bw)):
        fill = STYLE["flow_site"] if i == 0 else STYLE["flow_river"]
        d.rounded_rectangle([x, y, x + w, y + bh], radius=int(18 * k),
                            fill=fill, outline=(0, 0, 0), width=lw)
        d.text((x + w / 2, y + bh / 2), n, font=f, fill=(0, 0, 0), anchor="mm")
        centers.append((x, x + w))
        if i < len(nodes) - 1:                      # → 화살표와 구간 거리
            ax0, ax1 = x + w + arrow * 0.18, x + w + arrow * 0.82
            ay = y + bh / 2
            th = int(14 * k)
            d.rectangle([ax0, ay - th / 2, ax1 - th, ay + th / 2], fill=(0, 0, 0))
            d.polygon([(ax1 + th, ay), (ax1 - th, ay - th * 1.7),
                       (ax1 - th, ay + th * 1.7)], fill=(0, 0, 0))
            if i < len(links):
                d.text(((ax0 + ax1) / 2, y - int(18 * k)), links[i], font=fs,
                       fill=(0, 0, 0), anchor="mb")
        x += w + arrow

    if total:                                        # ↔ 총 유하거리
        lx, rx = centers[0][0] + int(20 * k), centers[-1][1] - int(20 * k)
        ty = y + bh + int(70 * k)
        cap = int(52 * k)
        for px in (lx, rx):
            d.rectangle([px - lw, ty - cap / 2, px + lw, ty + cap / 2], fill=(0, 0, 0))
        th = int(12 * k)
        d.rectangle([lx + th * 2, ty - th / 2, rx - th * 2, ty + th / 2], fill=(0, 0, 0))
        for px, sgn in ((lx, 1), (rx, -1)):
            d.polygon([(px, ty), (px + sgn * th * 2.6, ty - th * 1.8),
                       (px + sgn * th * 2.6, ty + th * 1.8)], fill=(0, 0, 0))
        d.text(((lx + rx) / 2, ty + int(26 * k)), total, font=f, fill=(0, 0, 0), anchor="ma")


# ── 렌더 ────────────────────────────────────────────────────────────────────
DISPATCH_NEEDS_IMAGE = {"zone", "legend"}


def _draw_element(im, el, k, F, pos):
    """요소 하나를 `im` 에 그린다 — **평면 렌더와 PSD 층 렌더가 공유하는 유일한 분기.**

    ⚠️ 여기를 복사해 층 렌더를 따로 만들지 말 것. 두 벌이 되면 조용히 갈라진다
    (`hwpx.md` — "검사와 수정은 다른 근거를 써야 한다"의 반대편 짝: **그리는 코드는 한 벌**)."""
    d = ImageDraw.Draw(im)
    t = el["type"]
    if t == "target":
        draw_target(d, el["at"], k)
    elif t == "label":
        draw_label(d, el["at"], el["text"], k, el.get("from"), F(34))
    elif t == "boundary":
        draw_boundary(d, el["points"], el.get("color", "yellow"), k)
    elif t == "zone":
        draw_zone(im, el["points"], el.get("label"), k, F(30))
    elif t == "flow":
        draw_flow(d, el["path"], el.get("count", 5), k)
    elif t == "parcels":
        draw_parcels(im, el["polygons"], el.get("color", "red"), k,
                     el.get("width"), el.get("fill", 0))
    elif t == "rings":
        draw_rings(im, el["origin"], el["radii_m"], el["px_per_m"], k, F(30),
                   el.get("label_deg", 213), color=el.get("color", (255, 255, 255)),
                   short=el.get("short"), fill=el.get("fill"))
    elif t == "polar":
        # 정답 정온시설 분포도는 마커·라벨이 **초록**이다 (평창 실측).
        # 색을 안 주면 표적 빨강을 쓴다 — 삽도 종류마다 달라 spec 에서 정한다.
        draw_polar(im, el["origin"], el["items"], el["px_per_m"], k, F(26),
                   tuple(el["dot"]) if el.get("dot") else None,
                   el.get("adjacent_m"))
    elif t == "watercourse":
        # 모식도는 **자기 크기가 절대적**이라 배율을 고정한다.
        # 캔버스 크기를 내용에서 잡는데 그 크기로 다시 배율을 매기면 서로 물려 넘친다.
        draw_watercourse(im, el["nodes"], el.get("links", []), el.get("total"), 1.0)
    elif t == "title":
        # 크기를 안 주면 골든셋 7/7 비율을 쓴다 — 폭 16.7% · 높이 5.8%
        draw_title(im, el.get("at") or [im.width / 2, im.height * 0.055],
                   el["text"],
                   el.get("width", im.width * 0.167),
                   el.get("height", im.height * 0.058), k, el.get("size"))
    elif t == "admin":
        draw_admin(im, pos(el, "north") if not el.get("at") else el["at"],
                   el["text"], k, el.get("size"))
    elif t == "river":
        draw_river(im, el["at"], el["text"], k, el.get("size"),
                   el.get("vertical", True))
    elif t == "place":
        draw_place(d, el["at"], el["text"], k, F(el.get("size", 38)))
    elif t == "scalebar":
        length = el.get("length_px") or round(im.width * DEFAULT_SCALEBAR_RATIO)
        label = el.get("label")
        if not label and el.get("px_per_m"):
            # `px_per_m` 을 주면 라벨을 계산한다 — map_fetch 가 돌려주는 그 값이다.
            # 막대 길이에 해당하는 실제 거리를 **읽기 좋은 눈금**으로 내린다.
            raw = length / float(el["px_per_m"])
            nice = [10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000]
            pick = max([n for n in nice if n <= raw], default=nice[0])
            length = round(pick * float(el["px_per_m"]))       # 눈금에 맞춰 막대도 줄인다
            label = f"{pick}m" if pick < 1000 else f"{pick/1000:g}km"
        draw_scalebar(d, pos(el, "scalebar"), length, label or "", k, F(26))
    elif t == "north":
        draw_north(d, pos(el, "north"), k, F(26), el.get("style", "compass"))
    elif t == "legend":
        orient = el.get("orient", "v")
        draw_legend(im, pos(el, "legend_h" if orient == "h" else "legend_v"),
                    [(c, s) for c, s in el["items"]], k, F(26),
                    el.get("title"), orient, el.get("swatch", "fill"))
    else:
        raise ValueError(f"모르는 요소: {t}")
    return t


def canvas_for(spec):
    """spec 이 요구하는 캔버스 — 베이스 지도가 있으면 그것, 없으면 빈 판.

    `render()` 와 PSD 층 렌더가 **같은 크기**를 얻어야 층이 어긋나지 않는다."""
    if spec.get("base"):
        return Image.open(Path(spec["base"])).convert("RGBA")
    # 지도가 없는 도식(수계흐름모식도 등) — 빈 캔버스에 그린다.
    # `canvas` 를 안 주면 **내용에 맞춰 크기를 잡는다** (노드가 많으면 옆이 잘린다).
    if spec.get("canvas"):
        w, h = spec["canvas"]
    else:
        wc = next((e for e in spec.get("elements", []) if e["type"] == "watercourse"), None)
        w, h = watercourse_size(wc["nodes"]) if wc else (1600, 500)
    return Image.new("RGBA", (int(w), int(h)), (255, 255, 255, 255))


def _helpers(im):
    """배율·폰트 캐시·기본 위치 — 평면/층 렌더가 공유한다."""
    k = _scaled(im)
    font_cache = {}

    def F(sz):
        return font_cache.setdefault(sz, _font(int(sz * k)))

    def pos(el, key):
        """`at` 이 있으면 그대로, 없으면 정답 실측 비율로 계산한다.

        ⚠️ 0~1 값은 **비율**로 본다. 픽셀 좌표가 1 이하일 일은 없는데, 기본값이
           비율이라 그 형식으로 넣기 쉽다 — 픽셀로 읽으면 조용히 모서리에 붙는다."""
        at = el.get("at")
        if at:
            x, y = at
            if 0 <= x <= 1 and 0 <= y <= 1:
                return [round(im.width * x), round(im.height * y)]
            return at
        rx, ry = DEFAULT_POS[key]
        return [round(im.width * rx), round(im.height * ry)]

    return k, F, pos


def render(spec, out_path=None):
    im = canvas_for(spec)
    k, F, pos = _helpers(im)
    drawn = [_draw_element(im, el, k, F, pos) for el in spec.get("elements", [])]

    if out_path:
        im.convert("RGB").save(out_path, quality=92)
    return im, drawn


# ── 데모 / 자체 확인 ────────────────────────────────────────────────────────
def demo(base=None, out=None):
    """베이스 지도가 없으면 격자 캔버스를 만들어 요소를 전부 그려 본다.

    ⚠️ 실제 삽도의 베이스는 사람이 캡처한 지도다. 여기서 만드는 격자는
    **요소가 제대로 그려지는지 확인하기 위한 대체물**일 뿐이다."""
    out = Path(out or ROOT / "raw_data/figure_demo.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)

    base_path = Path(base) if base and Path(base).exists() \
        else demo_base(out.with_name("_demo_base.png"))
    spec = demo_spec(base_path)
    _, drawn = render(spec, out)
    print(f"요소 {len(drawn)}개 렌더 — {', '.join(drawn)}")
    print(f"→ {out}  ({out.stat().st_size/1024:.0f}KB)")
    return out


def demo_base(path):
    """격자 캔버스 — 실제 삽도 베이스(사람이 캡처한 지도)의 대체물."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1600, 1200), (238, 236, 226))
    g = ImageDraw.Draw(im)
    for x in range(0, 1600, 80):
        g.line([(x, 0), (x, 1200)], fill=(214, 212, 202))
    for y in range(0, 1200, 80):
        g.line([(0, y), (1600, y)], fill=(214, 212, 202))
    im.save(path)
    return path


def demo_spec(base_path):
    """전 요소 시험 spec — 평면 데모와 PSD 데모가 **같은 것**을 쓴다."""
    return {
        "base": str(base_path),
        "elements": [
            {"type": "zone", "points": [[1120, 120], [1420, 150], [1390, 430], [1100, 380]],
             "color": "cyan", "label": "상수원보호구역"},
            {"type": "flow", "path": [[120, 980], [420, 900], [700, 760], [980, 600], [1180, 470]],
             "count": 7},
            {"type": "boundary",
             "points": [[620, 640], [900, 660], [940, 830], [780, 900], [600, 820]],
             "color": "yellow"},
            {"type": "target", "at": [770, 560]},
            {"type": "label", "at": [820, 470], "text": "사업계획지구", "from": [770, 560]},
            {"type": "place", "at": [380, 700], "text": "섬강"},
            # 원주 무장리 골든셋 §2.9.1 정온시설 표를 그대로 넣었다 (표 → 그림)
            {"type": "polar", "origin": [770, 560], "px_per_m": 0.42, "items": [
                {"label": "민가1", "dir": "남동", "dist_m": 46},
                {"label": "축사1", "dir": "남", "dist_m": 314},
                {"label": "축사2", "dir": "남", "dist_m": 393},
                {"label": "축사3", "dir": "북", "dist_m": 593},
                {"label": "축사4", "dir": "북동", "dist_m": 698}]},
            {"type": "scalebar", "at": [1180, 1120], "length_px": 320, "label": "0.5km"},
            {"type": "north", "at": [1500, 90]},
            {"type": "legend", "at": [60, 60],
             "items": [["yellow", "사업계획지구"], ["cyan", "상수원보호구역"]]},
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="삽도 오버레이 (베이스 지도 위 라벨·마커·경계선)")
    ap.add_argument("spec", nargs="?", help="spec JSON 경로")
    ap.add_argument("-o", "--out", help="출력 이미지")
    ap.add_argument("--demo", action="store_true", help="데모 렌더")
    ap.add_argument("--base", help="데모에 쓸 베이스 지도")
    a = ap.parse_args()

    if a.demo or not a.spec:
        demo(a.base, a.out)
        return
    spec = json.load(open(a.spec, encoding="utf-8"))
    out = a.out or Path(a.spec).with_suffix(".jpg")
    _, drawn = render(spec, out)
    print(f"요소 {len(drawn)}개 → {out}")


if __name__ == "__main__":
    main()

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
}
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/Supplemental/NanumGothic.ttf",
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]


def _font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()      # 한글이 깨진다 — 폰트를 설치할 것


def _scaled(im, base=1400):
    """요소 크기를 이미지 크기에 맞춘다. 삽도는 700~4,800px 로 폭이 제각각이다.

    기준 폭을 1,400 으로 잡았다 — 골든셋 최종본이 700×450 인데 2,000 기준으로는
    글자가 9px 까지 작아져 읽히지 않았다 (실측 후 조정)."""
    return max(0.6, im.width / base)


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


def draw_polar(im, origin, items, px_per_m, k=1.0, font=None, dot=None):
    """**정온시설 표를 그대로 그림으로 옮긴다.**

    지역개황 §2.9.1 · 소음진동·대기질의 영향예측지점 표는 `라벨 | 방향 | 이격거리(m)` 형태다.
    사업계획지구 중심 좌표와 축척만 주면 **표에서 바로 마커 위치가 나온다** — 실무자가
    지점마다 좌표를 찍을 필요가 없다.

    ⚠️ 방향이 16방위라 실제 방위각과 최대 ±11°차가 난다. **정확한 위치가 필요하면
    좌표를 받아야 한다** — 이 배치는 분포를 보여주는 용도다."""
    d = ImageDraw.Draw(im)
    f = font or _font(int(26 * k))
    ox, oy = origin
    placed = []
    for it in items:
        deg = BEARING.get(it["dir"])
        if deg is None:
            continue                       # 모르는 방위는 건너뛴다 (환각 금지)
        dist = it.get("dist_m")
        if not isinstance(dist, (int, float)):
            continue                       # `인접` 같은 비수치 값 — 평창 사례
        rad = math.radians(deg)
        x = ox + dist * px_per_m * math.cos(rad)
        y = oy + dist * px_per_m * math.sin(rad)
        r = 9 * k
        color = dot or STYLE["target"]
        d.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(255, 255, 255),
                  width=int(max(1, 2 * k)))
        d.text((x + 14 * k, y), it["label"], font=f, fill=(0, 0, 0), anchor="lm",
               stroke_width=int(max(2, 3 * k)), stroke_fill=(255, 255, 255))
        placed.append(it["label"])
    return placed


# ── ③ 장식 ─────────────────────────────────────────────────────────────────
def draw_scalebar(d, at, length_px, label, k=1.0, font=None):
    x, y = at
    h = int(14 * k)
    for i in range(4):                       # 흑백 교대 4칸
        x0 = x + length_px * i / 4
        x1 = x + length_px * (i + 1) / 4
        d.rectangle([x0, y, x1, y + h], fill=(0, 0, 0) if i % 2 == 0 else (255, 255, 255),
                    outline=(0, 0, 0), width=int(max(1, 2 * k)))
    # 라벨은 막대 **위쪽**에 — 아래 두면 등급 범례 띠와 겹친다 (골든셋도 위쪽이다)
    f = font or _font(int(26 * k))
    d.text((x, y - 4 * k), "0", font=f, fill=STYLE["deco"], anchor="ld",
           stroke_width=int(max(2, 3 * k)), stroke_fill=(255, 255, 255))
    d.text((x + length_px, y - 4 * k), label, font=f, fill=STYLE["deco"], anchor="rd",
           stroke_width=int(max(2, 3 * k)), stroke_fill=(255, 255, 255))


def draw_north(d, at, k=1.0, font=None, style="compass"):
    """방위표. 골든셋은 **8방향 별 나침반 + N/S/E/W 글자**를 쓴다 (실측)."""
    x, y = at
    f = font or _font(int(26 * k))
    if style == "arrow":                       # 단순 화살표 (예전 기본형)
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
    f = font or _font(int(26 * k))
    pad, sw, lh = int(11 * k), int(46 * k), int(38 * k)

    def color_of(c):
        if isinstance(c, (list, tuple)):
            return tuple(c)
        return STYLE["boundary"].get(c, STYLE["zone"] if c == "cyan" else (150, 150, 150))

    x, y = at
    if orient == "h":                          # ── 가로 띠 (등급 범례)
        gap = int(18 * k)
        widths = [d.textlength(t, font=f) + sw + gap for _, t in items]
        w, h = sum(widths) + pad * 2, lh + pad
        d.rectangle([x, y, x + w, y + h], fill=(255, 255, 255), outline=(0, 0, 0),
                    width=int(max(1, 2 * k)))
        cx = x + pad
        for c, text in items:
            r = int(9 * k)
            cy = y + h / 2
            d.ellipse([cx, cy - r, cx + 2 * r, cy + r], fill=color_of(c), outline=(80, 80, 80))
            d.text((cx + 2 * r + 6 * k, cy), text, font=f, fill=(0, 0, 0), anchor="lm")
            cx += 2 * r + 6 * k + d.textlength(text, font=f) + gap
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


# ── 렌더 ────────────────────────────────────────────────────────────────────
DISPATCH_NEEDS_IMAGE = {"zone", "legend"}


def render(spec, out_path=None):
    base = Path(spec["base"])
    im = Image.open(base).convert("RGBA")
    k = _scaled(im)
    d = ImageDraw.Draw(im)
    font_cache = {}

    def F(sz):
        return font_cache.setdefault(sz, _font(int(sz * k)))

    drawn = []
    for el in spec.get("elements", []):
        t = el["type"]
        if t == "target":
            draw_target(d, el["at"], k)
        elif t == "label":
            draw_label(d, el["at"], el["text"], k, el.get("from"), F(34))
        elif t == "boundary":
            draw_boundary(d, el["points"], el.get("color", "yellow"), k)
        elif t == "zone":
            draw_zone(im, el["points"], el.get("label"), k, F(30))
            d = ImageDraw.Draw(im)          # alpha_composite 후 draw 재생성
        elif t == "flow":
            draw_flow(d, el["path"], el.get("count", 5), k)
        elif t == "polar":
            draw_polar(im, el["origin"], el["items"], el["px_per_m"], k, F(26))
            d = ImageDraw.Draw(im)
        elif t == "place":
            draw_place(d, el["at"], el["text"], k, F(38))
        elif t == "scalebar":
            draw_scalebar(d, el["at"], el["length_px"], el.get("label", ""), k, F(26))
        elif t == "north":
            draw_north(d, el["at"], k, F(26), el.get("style", "compass"))
        elif t == "legend":
            draw_legend(im, el["at"], [(c, s) for c, s in el["items"]], k, F(26),
                        el.get("title"), el.get("orient", "v"), el.get("swatch", "fill"))
            d = ImageDraw.Draw(im)
        else:
            raise ValueError(f"모르는 요소: {t}")
        drawn.append(t)

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

    if base and Path(base).exists():
        base_path = Path(base)
    else:
        base_path = out.with_name("_demo_base.png")
        im = Image.new("RGB", (1600, 1200), (238, 236, 226))
        g = ImageDraw.Draw(im)
        for x in range(0, 1600, 80):
            g.line([(x, 0), (x, 1200)], fill=(214, 212, 202))
        for y in range(0, 1200, 80):
            g.line([(0, y), (1600, y)], fill=(214, 212, 202))
        im.save(base_path)

    spec = {
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
    _, drawn = render(spec, out)
    print(f"요소 {len(drawn)}개 렌더 — {', '.join(drawn)}")
    print(f"→ {out}  ({out.stat().st_size/1024:.0f}KB)")
    return out


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

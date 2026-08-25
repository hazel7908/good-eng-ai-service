#!/usr/bin/env python3
"""
지역개황 삽도 생성 — **Mac 전용**. 결과 PNG 를 Windows 가 hwpx 에 넣는다.

한 대에서 다 못 한다. 갈리는 지점이 정확히 반대다.

    생성(여기)   API 키 4종(`~/.vworld.env` 등) — **Mac 에만 있다**
    삽입·검증    한글 프로그램 — **Windows 에만 있다**

명세는 `docs/20260825_삽도_명세_지역개황.md`. 거기 적힌 **액자 픽셀**이 이 파일의 근거다.

    python engine/build_figures_regional.py 천안_화덕리
    python engine/build_figures_regional.py 천안_화덕리 --only 지역개황도

## ⚠️ 비율이 핵심이다

갈아 끼운 그림은 **기존 액자 크기로 늘어난다.** 비율이 10% 넘게 어긋나면 찌그러진다.
그래서 정사각 베이스를 받아 **액자 비율로 잘라** 낸다 — 늘리지 않는다.
(정사각 그대로 냈다가 다섯 장이 전부 어긋난 적이 있다.)

## ⚠️ 늘리지 않는다 — 축척을 먼저 정한다

액자 높이 ÷ 담을 범위 = 필요한 `px_per_m`. NGII 레벨은 이산적이라
**그보다 상세한 레벨**을 받아 잘라 내고 줄인다. 반대로 하면 흐려진다.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

CHECK = "[확인 필요]"
TILE = 256

# 명세 §2 — 액자 픽셀(300dpi). 파일명이 곧 자리 지정이다 (§4).
# `반경_m` 은 그 삽도가 담아야 하는 **세로 반경** — 액자 높이가 이걸 덮어야 한다.
FRAME = {
    "지역개황도":     {"px": (4465, 2693), "bin": "image38", "반경_m": 6000,
                       "source": "ngii"},
    "수계도":         {"px": (1996, 2610), "bin": "image19", "반경_m": 4500,
                       "source": "ngii"},
    "생태자연도":     {"px": (1984, 2102), "bin": "image16", "반경_m": 900,
                       "source": "ngii"},
    "정온시설도":     {"px": (1996, 2705), "bin": "image37", "반경_m": 600,
                       "source": "ngii", "layer": "satellite_map+hybrid_map"},
    "수계흐름모식도": {"px": (1925,  543), "bin": "image18", "반경_m": None},
}

# 명세 §3 — 지역개황이 만들지 않는다
OTHER_PART = {"식생보전등급도": "동식물상(7.1.1) 산출물이다 — 인용만 한다 (rule §1)"}

def bottom_right(W, H, ppm, length_m, label):
    """축척 막대와 방위표를 **겹치지 않게** 우하단에 놓는다.

    ⚠️ 고정 오프셋(`W-560`)을 쓰면 액자마다 어긋난다 — 막대 길이가 `length_m × ppm`
    이라 축척이 바뀌면 길이가 통째로 달라지는데, 방위표 자리는 그대로여서 글자가
    겹쳐 뭉갰다 (`1.0km 0 1.0km` · `200m 0 S 200m`).
    막대 실제 폭에서 역산하고, 방위표는 그 **위쪽**에 세운다.
    """
    bar = max(60, int(length_m * ppm))
    pad = max(40, int(W * 0.03))
    bx, by = W - bar - pad - int(W * 0.06), H - pad - int(H * 0.02)
    return ([{"type": "scalebar", "at": [bx, by], "length_px": bar, "label": label},
             {"type": "north", "at": [W - pad - int(W * 0.03),
                                      by - max(120, int(H * 0.07))]}])


RING_COLOR = [127, 127, 125]
RING_FILL = [150, 140, 110, 58]
RADII = [1000, 2000, 3000, 4000, 5000, 6000]


def plan_base(kind):
    """액자와 담을 범위에서 **받을 축척과 타일 수**를 정한다.

    반환 (span, level_ppm, target_ppm). `level_ppm ≥ target_ppm` 을 보장한다 —
    모자란 레벨을 받아 늘리면 글자가 뭉개진다.
    """
    import map_fetch as M
    W, H = FRAME[kind]["px"]
    target_ppm = H / (2 * FRAME[kind]["반경_m"])          # 액자 높이가 지름을 덮는다
    ok = [(lv, 1 / r) for lv, r in M.NGII_LEVELS.items() if 1 / r >= target_ppm]
    if not ok:
        return None, None, target_ppm
    lv, level_ppm = min(ok, key=lambda t: t[1])           # 넘되 가장 가까운 레벨
    side = max(W, H) * level_ppm / target_ppm             # 잘라 내기 전 필요한 픽셀
    return math.ceil(side / TILE), level_ppm, target_ppm


def fetch_base(addr, kind, span, out_png):
    conf = FRAME[kind]
    # ⚠️ NGII(WMTS)는 `--size` 가 안 먹는다 — 출력 크기가 `span × 256` 이다.
    #    `--fit` 은 자동 축척용인데 우리는 레벨을 직접 정하므로 넉넉히 준다.
    cmd = [sys.executable, str(ROOT / "engine/map_fetch.py"), "--address", addr,
           "--source", conf["source"], "--span", str(span),
           "--fit", str(conf["반경_m"]), "-o", str(out_png)]
    if conf.get("layer"):
        cmd += ["--layer", conf["layer"]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return None, None, (r.stderr or r.stdout).strip()[:200]
    import re
    cx = ppm = None
    for line in r.stdout.split("\n"):
        # `px_per_m` 은 출력에 두 번 나온다 — 표 한 줄과 맨 아래 안내 문구
        if (m := re.match(r"\s+center_px\s+(\[.*\])\s*$", line)):
            cx = json.loads(m.group(1))
        elif (m := re.match(r"\s+px_per_m\s+([\d.]+)\s*$", line)):
            ppm = float(m.group(1))
    return (cx, ppm, None) if cx and ppm else (None, None, "map_fetch 출력 파싱 실패")


def crop_to_frame(base_png, kind, center_px, ppm):
    """액자 비율대로 **사업지를 가운데 두고** 잘라 낸다. 반환 (새 중심, 크기)."""
    from PIL import Image
    W, H = FRAME[kind]["px"]
    target_ppm = H / (2 * FRAME[kind]["반경_m"])
    cw, ch = round(W * ppm / target_ppm), round(H * ppm / target_ppm)
    im = Image.open(base_png)
    cx, cy = center_px
    left, top = round(cx - cw / 2), round(cy - ch / 2)
    # 가장자리를 넘으면 안쪽으로 민다 — 그만큼 사업지가 중심에서 벗어난다
    left = max(0, min(left, im.width - cw))
    top = max(0, min(top, im.height - ch))
    im.crop((left, top, left + cw, top + ch)).save(base_png)
    return [cx - left, cy - top], (cw, ch)


def render(base, els, out_path, frame_px=None):
    doc = {"elements": els}
    if base:
        doc["base"] = str(base)
    elif frame_px:
        doc["canvas"] = list(frame_px)      # 지도가 없는 도식 — 액자 크기로 그린다
    spec = Path(out_path).with_suffix(".spec.json")
    spec.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "engine/figure_overlay.py"),
                        str(spec), "-o", str(out_path)], capture_output=True, text=True)
    spec.unlink(missing_ok=True)
    return None if r.returncode == 0 else (r.stderr or r.stdout).strip()[:300]


# ── 삽도별 조립 ─────────────────────────────────────────────────────────────
def 지역개황도(ctx):
    """반경 동심원 + 표적 + 행정구역명. **주소 한 줄이면 그려진다.**"""
    import admin as A
    cx, ppm, (W, H) = ctx["cx"], ctx["ppm"], ctx["size"]
    els = [{"type": "rings", "origin": cx, "radii_m": RADII, "px_per_m": ppm,
            "label_deg": 0, "short": True, "color": RING_COLOR, "fill": RING_FILL},
           {"type": "target", "at": cx},
           {"type": "label", "at": [cx[0], cx[1] - max(150, int(H * 0.06))],
            "text": "사업계획지구", "from": cx}]
    ring_pts = [[cx[0] + r * ppm, cx[1]] for r in RADII]
    regs = []
    # ⚠️ 시도는 넣지 않는다 — 괴산 정답에 없다
    for lv in ("시군구", "읍면동"):
        r, err = A.fetch(lv, ctx["lon"], ctx["lat"], 0.35)
        if not err:
            regs += A.to_elements(r, (ctx["lon"], ctx["lat"]), cx, ppm, (W, H),
                                  protect_px=int(1200 * ppm),
                                  avoid=ring_pts, keep=int(900 * ppm))
    els += A._avoid(regs, int(700 * ppm))
    return els + [{"type": "title", "text": "지역개황도"}] \
        + bottom_right(W, H, ppm, 1000, "1.0km")


def 수계도(ctx):
    """흐름 화살표·하천명·보호구역 채색.

    ⚠️ 하천망 자료가 **면형**이라 물길을 못 뽑는다 — `hydro` 가 **베이스 그림의
    하천 색을 읽어** 화살표를 놓는다 (삽도 문서 3-3)."""
    import hydro as Hy
    from PIL import Image
    cx, ppm, (W, H) = ctx["cx"], ctx["ppm"], ctx["size"]
    im = Image.open(ctx["base"]).convert("RGB")
    els = [{"type": "target", "at": cx},
           {"type": "label", "at": [cx[0], cx[1] - 150], "text": "사업계획지구",
            "from": cx}]
    try:
        mask = Hy.river_mask(im)
        # ⚠️ 격자를 `220 × ppm/0.08` 로 잡으면 **NAS 도엽 축척(0.08)에 묶인다.**
        #    API 베이스는 ppm 이 3~4배라 격자가 800px 로 벌어져 화살표가 한 개만 남았다.
        #    화면 크기의 일정 비율로 잡아야 축척이 달라져도 고르게 놓인다.
        els += Hy.arrows_to_elements(
            Hy.flow_arrows(mask, cx, grid=max(80, int(min(W, H) / 12))))
        labels, err = Hy.river_labels(ctx["lon"], ctx["lat"], 0.05, cx, ppm, (W, H),
                                      avoid=[e.get("at") for e in els if e.get("at")],
                                      mask=mask)
        if err:
            ctx["warn"].append(f"하천명 — {err}")
        els += labels
    except Exception as e:
        ctx["warn"].append(f"하천 요소 — {type(e).__name__}: {e}")
    try:
        els += Hy.protected_zones(ctx["lon"], ctx["lat"], 0.05, cx, ppm)
    except Exception as e:
        ctx["warn"].append(f"보호구역 — {type(e).__name__}")
    return els + [{"type": "title", "text": "수계도"}] \
        + bottom_right(W, H, ppm, 1000, "1.0km")


def pp_points(ctx):
    """정온·개발시설 지점 목록 → `polar` 항목.

    ★ **자매 파트도 인풋이다** (`_category.md`). 한 사업의 보고서는 여러 파트가 같은
    PP 표를 쓴다 — 천안에서 소음진동↔대기질이 완전히 같음을 확인했다. 지역개황 vars 에
    표가 아직 없으면 **소음진동·대기질 vars 에서 가져온다.** 정답지 참조가 아니다 —
    금지 대상은 *생성하는 파트의* 골든셋뿐이다.

    ⚠️ `인접` 처럼 수치가 아닌 이격거리는 **건너뛴다** — 없는 위치를 지어내지 않는다.
    """
    rows = ctx["vars"].get("통계", {}).get("2.9.1 정온 및 개발시설 현황")
    src = "지역개황 vars"
    if not isinstance(rows, list) or not rows:
        for sib in ("noise-vib", "air-quality"):
            f = ctx["case_dir"] / f"vars/{sib}.json"
            if not f.exists():
                continue
            sv = json.loads(f.read_text(encoding="utf-8"))
            cand = (sv.get("예측", {}) or {}).get("지점")
            if isinstance(cand, list) and cand:
                rows, src = cand, f"{sib} vars"
                break
    out = []
    for r in (rows if isinstance(rows, list) else []):
        raw = r.get("이격거리_m", r.get("이격거리", r.get("이격거리(m)")))
        try:
            d = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            continue
        out.append({"label": r.get("이름") or r.get("라벨") or r.get("시설명", ""),
                    "dir": r.get("방향", ""), "dist_m": d})
    if out:
        ctx["warn"].append(f"PP {len(out)}지점 — {src} 에서 가져왔다")
    return out


def 정온시설도(ctx):
    """정온·개발시설 분포. **표를 그림으로 옮긴다** — PP 표(방향·이격거리)를
    `polar` 로 배치한다. 지점마다 좌표를 찍을 필요가 없다.

    ⚠️ 16방위라 실제 방위각과 최대 ±11° 차가 난다. `인접` 처럼 수치가 아닌
    이격거리는 **건너뛴다** — 없는 위치를 지어내지 않는다."""
    cx, ppm, (W, H) = ctx["cx"], ctx["ppm"], ctx["size"]
    items = pp_points(ctx)
    if not items:
        ctx["warn"].append("PP 표를 어디서도 못 찾았다 — 마커 없이 배경만 나온다")
    # ⚠️ PP 마커가 사업지 바로 옆(80m)에 오는 수가 있다 — 라벨을 표적 위에 두면
    #    `사업계농막구` 처럼 겹쳐 뭉갠다. 왼쪽 위로 빼고 지시선으로 잇는다.
    els = [{"type": "target", "at": cx},
           {"type": "label", "at": [cx[0] - int(W * 0.14), cx[1] - int(H * 0.06)],
            "text": "사업계획지구", "from": cx}]
    if items:
        els.append({"type": "polar", "origin": cx, "items": items, "px_per_m": ppm})
    return els + [{"type": "title", "text": "정온시설 및 개발시설 현황"}] \
        + bottom_right(W, H, ppm, 200, "200m")


def 생태자연도(ctx):
    """3층 조립 — 지형도 + 등급 채색 + 군락기호. `ecology.compose` 가 맡는다.

    ⚠️ `compose` 는 **(합성 이미지, 라벨 요소)** 를 돌려준다. 합성본을 베이스로
    삼아 다시 렌더해야 라벨이 얹힌다."""
    import ecology as E
    im, labels = E.compose(ctx["lon"], ctx["lat"], str(ctx["base"]),
                           ctx["ppm"], ctx["cx"])
    mid = Path(ctx["out"]).with_name("_ecology.png")
    im.save(mid)
    ctx["base"] = mid
    cx, (W, H) = ctx["cx"], im.size
    return list(labels) + [
        # 정답에는 **등급 범례가 있다** — 채색만 있으면 무슨 색인지 모른다
        {"type": "legend", "at": [60, 60], "items": E.legend_items()},
        {"type": "target", "at": cx},
        {"type": "label", "at": [cx[0], cx[1] - 110], "text": "사업계획지구",
         "from": cx},
        {"type": "title", "text": "생태·자연도"},
        {"type": "north", "at": [W - 160, H - 190]}]


def 수계흐름모식도(ctx):
    """지도가 없는 삽도 — 본문 수계 서술에서 사각형·화살표를 **직접 작도**한다.

    ⚠️ 서술은 사업개요가 아니라 **지역개황 본문(2.8.3)**에 있다."""
    import watercourse as W
    src = None
    for f in sorted((ctx["case_dir"] / "input").glob("*.txt")):
        t = f.read_text(encoding="utf-8", errors="replace")
        if "유하" in t and "합류" in t:
            src = t
            break
    if src is None:
        ctx["warn"].append("수계 유하 서술이 인풋에 없다 — 지역개황 본문(2.8.3)이 필요하다")
        return None
    el = W.parse(src)
    if len(el.get("nodes", [])) < 2:
        ctx["warn"].append("유하 경로를 못 읽었다 — 원문에 값이 없다")
        return None
    if el.get("_warn"):
        ctx["warn"] += list(el["_warn"])
    return [el]


BUILDERS = {"지역개황도": 지역개황도, "수계도": 수계도, "정온시설도": 정온시설도,
            "생태자연도": 생태자연도, "수계흐름모식도": 수계흐름모식도}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--only")
    a = ap.parse_args()

    case_dir = ROOT / "cases/small-env" / a.case
    vp = case_dir / "vars/regional-overview.json"
    if not vp.exists():
        sys.exit(f"ERROR: {vp} 없음 — build_vars_regional.py 를 먼저 돌린다")
    v = json.loads(vp.read_text(encoding="utf-8"))
    biz = v["사업"]
    addr = (v.get("공간", {}).get("지오코딩_주소")
            or f'{biz.get("시군","")} {biz.get("하위행정구역","")} {biz.get("리","")}')

    out_dir = case_dir / "regional-overview/figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"# {a.case} — {addr}\n")
    for k, why in OTHER_PART.items():
        print(f"  ▸ {k:16s} 만들지 않는다 — {why}")

    import map_fetch as M
    lon = lat = None
    made, skipped = [], []
    for kind in FRAME:
        if a.only and kind != a.only:
            continue
        W, H = FRAME[kind]["px"]
        out = out_dir / f"{kind}.png"
        ctx = {"vars": v, "case_dir": case_dir, "out": out, "warn": [], "size": (W, H)}

        if FRAME[kind]["반경_m"]:
            span, lppm, tppm = plan_base(kind)
            if span is None:
                skipped.append((kind, f"필요 축척 {tppm:.3f} px/m 를 NGII 레벨이 못 준다"))
                print(f"  ✗ {kind:16s} 축척 부족"); continue
            base = out_dir / f"_base_{kind}.png"
            print(f"    {kind}: {span}×{span} 타일 · {lppm:.3f}→{tppm:.3f} px/m …")
            cx, ppm, err = fetch_base(addr, kind, span, base)
            if err:
                skipped.append((kind, f"베이스 실패: {err}"))
                print(f"  ✗ {kind:16s} {err}"); continue
            cx, size = crop_to_frame(base, kind, cx, ppm)
            if lon is None:
                x, y, _ = M.geocode(addr)
                lon, lat = M.merc_to_lonlat(x, y)
            ctx.update(base=base, cx=cx, ppm=ppm, size=size, lon=lon, lat=lat)

        try:
            els = BUILDERS[kind](ctx)
        except Exception as e:
            skipped.append((kind, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {kind:16s} 조립 실패 — {type(e).__name__}: {e}"); continue
        if els is None:
            skipped.append((kind, " · ".join(ctx["warn"]) or "만들지 못했다"))
            print(f"  ✗ {kind:16s} {' · '.join(ctx['warn'])}"); continue

        err = render(ctx.get("base"), els, out, frame_px=(W, H))
        if err or not out.exists():
            skipped.append((kind, f"렌더 실패: {err}"))
            print(f"  ✗ {kind:16s} 렌더 실패 — {err}"); continue

        # 액자 픽셀로 정확히 맞춘다 — 비율은 이미 잘라 낼 때 맞췄다
        from PIL import Image
        im = Image.open(out)
        if im.size != (W, H):
            im.resize((W, H), Image.LANCZOS).save(out)
        for f in out_dir.glob("_*"):
            f.unlink()
        got = Image.open(out).size
        w = "  ⚠ " + " · ".join(ctx["warn"]) if ctx["warn"] else ""
        print(f"  ✓ {kind:16s} {got[0]}×{got[1]}  {out.stat().st_size//1024}KB{w}")
        made.append(kind)

    print(f"\n생성 {len(made)} · 못 만든 것 {len(skipped)}")
    for k, why in skipped:
        print(f"  [{CHECK}] {k} — {why}")
    print(f"→ {out_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

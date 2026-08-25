#!/usr/bin/env python3
"""
지역개황 vars 빌더 — 사업 인풋 + 통계 → `cases/{사업}/vars/regional-overview.json`.

**생성(`generate.py`)은 통계를 모른다.** 엔진은 vars 만 읽으므로, 표는 여기서
값으로 확정돼 있어야 한다. `calc.py`(소음진동)·`calc_air.py`(대기질)와 같은 자리다.

    python engine/build_vars_regional.py 원주_무장리
    python engine/build_vars_regional.py 원주_무장리 --dry-run

## 판을 여기서 **고정한다** ★

한 보고서 안에서 판이 섞이면 출처 주석이 거짓말이 된다 — 골든셋에서 실제로 네 건
나왔다 (천안은 출처 `2023` 인데 값은 2021판, 게다가 다른 열). 그래서

  · 최초 생성 때 **보유 최신으로 고정**하고 판·지문을 vars 에 박는다
  · 재생성은 vars 의 판을 그대로 쓴다 — 다시 고르지 않는다
  · 갱신은 `--refresh` 를 줄 때만

⚠️ **통계 확인 때문에 생성이 멈추면 안 된다.** 자료가 없으면 `[확인 필요]` 로 두고 넘어간다.
"""
import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

sys.path.insert(0, str(ROOT / "catalog"))
import build_stats_values as BSV                           # noqa: E402
import stats_extract as YB                                 # noqa: E402
import stats_irregular as IRR                              # noqa: E402
import stats_pdf as PDF                                    # noqa: E402
from stats_national import SOURCES, gun_key               # noqa: E402

CHECK = "[확인 필요]"
VALUES = ROOT / "catalog/data/stats_values"
MANIFEST = ROOT / "catalog/data/stats_values.manifest.json"
NAT = ROOT / "raw_data/nas/stats/_national"

# 절 → 어떤 경로로 오는가. `stats_values` 는 이미 뜬 값이라 **오프라인**이다.
FROM_VALUES = list(SOURCES)          # 전국 통계 — 값 저장소 조회
FROM_IRREGULAR = {
    "2.3.2 수변구역": ("수변구역", r"수변구역.*hwpx$"),
    "2.3.3 생태·경관보전지역": ("생태경관보전지역", r"생태경관보전지역.*hwpx$"),
    "2.3.3 야생생물 보호구역": ("야생생물보호구역", r"야생생물보호구역.*xlsx$"),
    "2.8.3 하천일람": ("하천일람", r"한국하천일람.*시도별.*xlsx$"),
}
FROM_PDF = {
    "2.3.3 자연공원": ("자연공원", r"국립공원기본통계\.pdf$"),
    "2.3.3 습지보호지역": ("습지보호지역", r"습지보호지역.*pdf$"),
    "2.3.3 백두대간": ("백두대간", r"산림청고시.*백두대간.*pdf$"),
}


def latest(pattern):
    """`raw_data` 에서 정규식에 맞는 **가장 새 판**을 고른다. 없으면 None."""
    cands = [p for p in NAT.rglob("*") if re.search(pattern, p.name)]
    if not cands:
        return None

    def key(p):
        m = re.search(r"(20\d\d)", p.name)
        return int(m.group(1)) if m else 0
    return max(cands, key=key)


def load_values():
    """값 저장소를 통째로 읽는다 — {(자료, 판): 문서}."""
    out = {}
    for f in sorted(VALUES.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[(d["자료"], d["판"])] = d
    return out


def pick_edition(store, 자료, frozen=None, refresh=False):
    """쓸 판을 고른다 — **고정이 기본이다.**

    한 보고서 안에서 판이 섞이면 출처 주석이 거짓말이 된다. 그래서 최초 생성 때 고른
    판을 vars 에 박아 두고, 재생성은 **그대로 쓴다.** 새 판으로 갈아타는 것은
    `--refresh` 를 줄 때만 — 눈에 보이는 행위여야 한다.

    ⚠️ 예전에는 늘 `max()` 를 골랐다. 문서에는 "재생성은 vars 의 판을 그대로 쓴다" 고
       적어 놓고 코드는 매번 최신으로 갈아탔다 — 설계와 구현이 어긋나 있었다.
    """
    yrs = [y for (s, y) in store if s == 자료]
    if not yrs:
        return None
    if not refresh and frozen and 자료 in frozen:
        keep = frozen[자료].get("판")
        if keep in yrs:
            return keep
    return max(yrs)


def 사업정보(case_dir):
    """사업개요에서 시군·면·리·사업명·면적을 읽는다. 못 읽으면 `[확인 필요]`."""
    txt = (case_dir / "input/사업개요.txt").read_text(encoding="utf-8", errors="replace")
    info = {k: CHECK for k in ("사업명", "시군", "구", "하위행정구역", "리", "지구_면적")}
    # ⚠️ **자치구가 끼는 사업이 있다** — `천안시 동남구 동면 화덕리`.
    #    rule §4-2 의 "면 ↔ 구 (7:1)" 변이다. 구를 선택항으로 두지 않으면 못 읽는다.
    m = re.search(r"([가-힣]+[시군])\s+(?:([가-힣]+구)\s+)?([가-힣]+[읍면동])\s+([가-힣]+리)"
                  r"\s*(\d[\d\-]*)?번지?\s*일원\s*(.+?조성사업)", txt)
    if m:
        info.update({"시군": m.group(1), "구": m.group(2) or "",
                     "하위행정구역": m.group(3), "리": m.group(4),
                     "사업명": m.group(0).strip()})
    if (a := re.search(r"사업계획지구의?\s*면적은\s*([\d,]+)\s*㎡", txt)):
        info["지구_면적"] = a.group(1)
    return info


# 시도 약칭 — 하천일람의 `시도` 열이 축약형이다 (`충남`·`강원`)
SIDO_SHORT = {"충청남도": "충남", "충청북도": "충북", "전라남도": "전남",
              "전라북도": "전북", "경상남도": "경남", "경상북도": "경북",
              "강원특별자치도": "강원", "강원도": "강원", "경기도": "경기",
              "제주특별자치도": "제주", "전북특별자치도": "전북"}


def 수계(path, info, out, 확인필요):
    """사업지 인근 하천 → 하천일람 계통.

    ⚠️ 예전에는 조회 키를 **`섬강`(원주 하천)으로 박아** 뒀다. 다른 사업에 원주 값이
    그대로 샜다 — 천안 vars 에 `섬강 · 경기 · 유로연장 100km` 가 들어가 있었다.
    지금은 좌표로 찾는다.

    ⚠️ **동명이천을 시도로 거른다.** `용두천` 은 천안 근처(충남 계통: 병천천→미호천→금강)와
    세종(대교천→금강)에 둘 다 있다. 시도를 안 주면 엉뚱한 수계가 나온다.
    """
    import hydro as Hy
    import stats_irregular as I
    lon, lat = out["공간"].get("_lonlat", (None, None))
    if lon is None:
        확인필요("통계.2.8.3 하천일람", "판단", "좌표가 없어 인근 하천을 못 찾았다")
        return CHECK
    streams, err = Hy.fetch_streams(lon, lat, 0.05)
    # 거리순으로 후보를 세운다 — 경위도 1도를 미터로 환산해 가장 가까운 절점을 본다
    cands = []
    for st in (streams or []):
        if not st.get("name") or not st.get("path"):
            continue
        d = min(math.hypot((px - lon) * 88800, (py - lat) * 111000)
                for px, py in st["path"])
        cands.append((round(d), st["name"], st.get("grade")))
    cands.sort()
    if not cands:
        확인필요("통계.2.8.3 하천일람", "판단",
                 f"인근 하천을 못 찾았다{' — ' + err if err else ''}")
        return CHECK

    시도 = SIDO_SHORT.get(str(info.get("시군_시도") or ""), None)
    if 시도 is None:
        m = re.match(r"([가-힣]+(?:도|시))\s", str(out["공간"].get("지오코딩_주소", "")))
        시도 = SIDO_SHORT.get(m.group(1)) if m else None

    r = None
    for _, nm, _g in cands:
        r = I.수계_체인(str(path), nm, 시도)
        if r and len(r["체인"]) > 1:
            break
    if not r:
        확인필요("통계.2.8.3 하천일람", "판단",
                 f"하천일람에서 {[c[1] for c in cands]} 를 못 찾았다")
        return CHECK
    r["후보"] = [{"하천": n, "거리_m": d, "등급": g} for d, n, g in cands[:5]]

    # ⚠️ **가장 가까운 하천이 정답이 아니다.** 사업지에서 구거가 *어디로 흘러드는지*는
    #    물길 방향 문제라 거리로 못 정한다 — 천안은 최근접(용두천)이 맞았지만
    #    원주는 최근접이 원주천(1,410m)인데 정답은 **섬강(1,612m)** 이다.
    #    관측 1:1 이라 규칙으로 굳히지 않는다. 최근접을 **기본값**으로 두고 표시한다.
    확인필요("통계.2.8.3 하천일람", "판단",
             f"유하 하천을 **최근접({r['기준하천']})으로 가정**했다 — 구거가 실제로 어디로 "
             f"흘러드는지는 물길을 따라가야 안다. 후보: "
             + " · ".join(f"{n}({d}m)" for d, n, _ in cands[:4]))
    # ── 유하 경로·거리 — KRF(Korean Reach File) ────────────────────────
    #    하천일람은 **계통**을, KRF 는 **경로와 거리**를 준다. 둘을 함께 낸다.
    try:
        import reachfile as RF
        t = RF.trace(lon, lat)
        r["유하"] = t
        확인필요("통계.2.8.3 하천일람", "판단",
                 f"유하 경로는 **KRF 추정**이다 — 최종본류 `{t['최종본류']}` "
                 f"(골든셋 2/2 일치), 총 {t['총거리_km']}km. "
                 "⚠️ **사업지~하천 구간이 구거라 자료에 없다** — 첫 합류 하천을 직선 "
                 "최근접으로 가정했고, 골든셋 2건 중 1건(원주)이 어긋났다. "
                 "구간별 거리도 +10~58% 벌어진다. 지도 확인 필요")
    except SystemExit:
        확인필요("통계.2.8.3 하천일람", "자료부재",
                 "KRF 가 없다 — `python engine/reachfile.py --download`")
    except Exception as e:
        확인필요("통계.2.8.3 하천일람", "판단", f"KRF 추적 실패: {e}")
    return r


def 최신확인(store_srcs, 확인필요, offline=False):
    """발행처에 새 판이 나왔는지 **보고서를 시작할 때 한 번** 본다.

    ⚠️ **막지 않는다.** 네트워크·사이트 개편 어느 것이 어긋나도 보유 판으로 진행하고
    사실만 적는다 — 통계 확인 때문에 보고서 생성이 멈추면 안 된다.

    ⚠️ **자동으로 받아 갈아타지 않는다.** 새 판이 있어도 알리기만 한다. 갈아타는 것은
    `--refresh` 를 줄 때만이다 — 한 보고서 안에서 판이 섞이면 출처 주석이 거짓말이 된다.

    반환 `{자료: 상태}`. 상태는 fill-report 에 그대로 실려 **실무자가 무엇을 직접
    확인해야 하는지** 보이게 한다.
    """
    if offline:
        return {s: "⏭ 확인 안 함 (--offline)" for s in store_srcs}
    sys.path.insert(0, str(ROOT / "catalog"))
    try:
        from build_stats_values import WATCH
    except Exception as e:
        확인필요("통계.최신판 확인", "판단", f"감시기를 못 불렀다 ({e})")
        return {}
    out, 미확인, 신판 = {}, [], []
    for src in sorted(store_srcs):
        fn = WATCH.get(src)
        if not fn:
            out[src] = "❓ 발행처 미확인 — **직접 확인 필요**"
            미확인.append(src)
            continue
        try:
            latest = fn()
        except Exception as e:
            out[src] = f"⚠️ 조회 실패 ({type(e).__name__}) — 보유 판으로 진행"
            continue
        out[src] = (f"✅ 발행처 최신 {latest} 확인" if latest else
                    "⚠️ 목록에서 연도를 못 읽었다")
        if latest:
            out[src] += f" ({latest})"
            신판.append((src, latest))
    if 미확인:
        확인필요("통계.최신판 확인", "판단",
                 f"**발행처를 몰라 최신인지 확인하지 못한 자료 {len(미확인)}종** — "
                 f"직접 확인해 주십시오: {' · '.join(미확인)}")
    return out, 신판


def build(case, refresh=False, land_source="통계연보", offline=False):
    case_dir = ROOT / "cases/small-env" / case
    if not (case_dir / "input/사업개요.txt").exists():
        sys.exit(f"ERROR: {case_dir}/input/사업개요.txt 없음")

    # 이미 만든 vars 가 있으면 **그때 고른 판**을 물려받는다 (`--refresh` 면 무시)
    vp = case_dir / "vars/regional-overview.json"
    frozen = {}
    if vp.exists() and not refresh:
        try:
            frozen = json.loads(vp.read_text(encoding="utf-8")).get("_통계판", {})
        except Exception:
            frozen = {}

    info = 사업정보(case_dir)
    시군 = info["시군"]
    if 시군 == CHECK:
        sys.exit("ERROR: 사업개요에서 시군을 못 읽었다 — 수동으로 vars 를 채울 것")

    store = load_values()
    man = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"판": []}
    지문 = {(e["자료"], e["판"]): e["원자료"]["sha256"][:12] for e in man["판"]}

    out = {
        "_meta": {
            "카테고리": "small-env", "파트": "regional-overview", "사업": case,
            "작성일": date.today().isoformat(),
            "출처": f"cases/small-env/{case}/input/ + 전국 통계 값 저장소. golden/ 미참조",
            "규칙": ".claude/rules/small-env/regional-overview.md",
            "주의": [
                "골든셋에서 값을 베끼지 않는다. 베끼면 검증이 부정이 된다.",
                "판(`_통계판`)은 **여기서 고정**된다 — 재생성해도 같은 값이 나온다.",
                "새 판으로 갈아타려면 `--refresh` 를 명시할 것.",
            ],
        },
        "사업": info,
        "_통계판": {},
        "통계": {},
        "_확인필요": [],
    }

    def 확인필요(항목, 분류, 사유):
        out["_확인필요"].append({"항목": 항목, "분류": 분류, "사유": 사유})

    srcs = sorted({s for (s, _y) in store})
    latest_state, 신판 = 최신확인(srcs, 확인필요, offline)

    # ── 새 판이 있으면 **받아서 값 저장소를 갱신한다** ─────────────────
    #    ⚠️ **최초 생성 때만** 갈아탄다. 이미 vars 가 있고 판이 고정돼 있으면
    #       그대로 쓴다 — 한 보고서 안에서 판이 섞이면 출처 주석이 거짓말이 된다.
    #       고정을 무시하려면 `--refresh`.
    #    ⚠️ **실패해도 막지 않는다.** 받다 어긋나면 보유 판으로 진행하고 사실만 적는다.
    for src, yr in 신판:
        if frozen and src in frozen and not refresh:
            확인필요("통계.최신판 확인", "판단",
                     f"🔴 **{src} {yr}판이 나와 있다** — 이 보고서는 "
                     f"{frozen[src].get('판')}판으로 **고정**돼 있어 그대로 쓴다. "
                     "갈아타려면 `--refresh` 를 줄 것")
            continue
        확인필요("통계.최신판 확인", "판단", f"🔽 {src} {yr}판을 받는 중…")
        path, err = BSV.download_latest(src, yr)
        if err:
            확인필요("통계.최신판 확인", "판단",
                     f"⚠️ **{src} {yr}판을 못 받았다** ({err}) — 보유 판으로 진행한다")
            continue
        try:
            BSV.rebuild_one(path)
            store.clear()
            store.update(load_values())
            확인필요("통계.최신판 확인", "판단",
                     f"✅ **{src} {yr}판으로 갱신했다** ({path.name})")
        except Exception as e:
            확인필요("통계.최신판 확인", "판단",
                     f"⚠️ {src} {yr}판 적재 실패 ({e}) — 보유 판으로 진행한다")

    # ── 좌표 먼저 ─────────────────────────────────────────────────────
    #    ⚠️ **수계 조회가 좌표를 쓴다.** 예전에는 지오코딩이 절 소싱보다 뒤에 있어
    #       하천을 못 찾고 원주 기본값(`섬강`)으로 떨어졌다.
    out["공간"] = {"도엽번호": CHECK, "생태자연도_등급": CHECK}
    # ⚠️ **지번까지 넣어야 한다.** 리까지만 주면 VWorld 가 `무장리 1` (리 대표점)로
    #    매칭해 **사업지와 다른 곳**을 짚는다 — 원주에서 생태자연도가 1등급으로 나왔다
    #    (정답 2,3등급). `지구_소재지` 는 사업명에서 뽑은 `…578번지` 다.
    m0 = re.search(r"^(.+?번지)\s*일원", str(info.get("사업명", "")))
    주소 = m0.group(1) if m0 else f'{info["시군"]} {info["하위행정구역"]} {info["리"]}'.strip()
    lon = lat = None
    try:
        import map_fetch
        x, y, matched = map_fetch.geocode(주소)      # EPSG:3857 + 매칭된 주소
        lon, lat = map_fetch.merc_to_lonlat(x, y)
        out["공간"]["지오코딩_주소"] = matched
        out["공간"]["_lonlat"] = [lon, lat]
        out["공간"]["좌표_3857"] = [x, y]
    except Exception as e:
        확인필요("공간.좌표", "판단", f"지오코딩 실패({주소}): {e}")


    # ── 전국 통계 (값 저장소 — 오프라인) ────────────────────────────────
    for sec in FROM_VALUES:
        자료 = SOURCES[sec]["자료"]
        yr = pick_edition(store, 자료, frozen, refresh)
        if yr is None:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "자료부재", f"{자료} 값 저장소에 없음 — build_stats_values 실행")
            continue
        blk = store[(자료, yr)]["절"].get(sec, {})
        rows = blk.get("값", {}).get(gun_key(시군), [])
        out["통계"][sec] = rows
        out["_통계판"][자료] = {"판": yr, "지문": 지문.get((자료, yr), CHECK),
                                "최신확인": latest_state.get(자료, CHECK)}
        if not rows:
            확인필요(f"통계.{sec}", "판단",
                     f"{시군} 해당 행 0 — 실제로 없는지(0개소) 표기 차이인지 확인")

    # ── 모양이 다른 것 (엑셀·한글) ──────────────────────────────────────
    for sec, (fn, pat) in FROM_IRREGULAR.items():
        p = latest(pat)
        if not p:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "자료부재", f"원자료 없음 (/{pat}/)")
            continue
        try:
            if fn == "하천일람":
                out["통계"][sec] = 수계(p, info, out, 확인필요)
            else:
                out["통계"][sec] = getattr(IRR, fn)(str(p), 시군)
        except Exception as e:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "판단", f"읽기 실패: {e}")
        out["_통계판"][sec] = {"파일": p.name}

    # ── PDF ────────────────────────────────────────────────────────────
    for sec, (fn, pat) in FROM_PDF.items():
        p = latest(pat)
        if not p:
            out["통계"][sec] = CHECK
            확인필요(f"통계.{sec}", "자료부재", f"원자료 없음 (/{pat}/)")
            continue
        try:
            r = getattr(PDF, fn)(str(p), 시군)
        except Exception as e:
            r, _ = CHECK, 확인필요(f"통계.{sec}", "판단", f"읽기 실패: {e}")
        out["통계"][sec] = r if r else []      # 빈 목록 = 지정현황 없음 (정상)
        out["_통계판"][sec] = {"파일": p.name}
        if isinstance(r, dict) and r.get("합계검산") == CHECK:
            확인필요(f"통계.{sec}", "판단", "시도 합계 검산 실패 — 표를 눈으로 확인할 것")

    # ── 통계연보 (지자체별 — 사업마다 원자료가 필요하다) ────────────────
    YB_SECS = ("2.2.1 지목별 토지이용", "2.2.2 용도지역", "2.5.1 도로",
               "2.5.2 환경오염물질 배출시설", "2.5.4 자동차", "2.6.3 문화재")
    yb = sorted((ROOT / "raw_data/nas/stats" / case).glob("*통계연보*")) or \
         sorted((ROOT / "raw_data/nas/stats" / case).glob("*.zip"))
    if not yb:
        for sec in YB_SECS:
            out["통계"][sec] = CHECK
        확인필요("통계.통계연보 6절", "자료부재",
                 f"{시군} 통계연보 원자료가 raw_data/nas/stats/{case}/ 에 없다 (확인요청 F-4)")
    elif yb[0].suffix.lower() == ".pdf":
        for sec in YB_SECS:
            out["통계"][sec] = CHECK
        확인필요("통계.통계연보 6절", "자료부재",
                 f"통계연보가 **스캔 PDF** ({yb[0].name}) — 값을 못 꺼낸다 (확인요청 F-4)")
    else:
        out["_통계판"]["지자체 통계연보"] = {
            "파일": yb[0].name,
            # ⚠️ 229개 지자체가 각자 발행해 감시가 구조적으로 안 된다.
            #    천안시 통계 누리집의 통계연보 페이지는 지금 "준비중" 이고 KOSIS 에도 없다
            "최신확인": "❓ 발행처가 지자체마다 달라 확인 불가 — **직접 확인 필요** (F-4)"}
        확인필요("통계.통계연보 최신판", "판단",
                 f"**{시군} 통계연보가 최신판인지 확인하지 못했다** — 지자체마다 발행처가 "
                 "달라 자동 확인이 안 된다. 지금 쓰는 것은 "
                 f"`{yb[0].name}` 이다. 더 새 판이 있는지 확인해 주십시오 (F-4 · G-7)")
        면 = info["하위행정구역"] if info["하위행정구역"] != CHECK else None
        try:
            book = YB.YearBook(str(yb[0]))
        except Exception as e:
            book = None
            for sec in YB_SECS:
                out["통계"][sec] = CHECK
            확인필요("통계.통계연보 6절", "판단", f"통계연보 열기 실패: {e}")
        if book:
            # ⚠️ **어느 연도 행을 쓸지는 회사 표준이 없다** (확인요청 F-1).
            #    지금 기본값은 "최신 행" — 정답지는 절마다 다른 행을 쓰고 있었다.
            calls = {
                "2.2.1 지목별 토지이용": lambda: {
                    "시군": YB.land_use(book), "면": YB.land_use(book, region=면) if 면 else CHECK},
                "2.2.2 용도지역": lambda: YB.zoning(book),
                "2.5.1 도로": lambda: YB.roads(book),
                "2.5.2 환경오염물질 배출시설": lambda: YB.emitters(book),
                "2.5.4 자동차": lambda: YB.vehicles(book),
                # ⚠️ 표에 **시군 전체와 면이 함께** 들어간다 (지목별과 같은 구성).
                #    면만 내면 "천안시 국가지정 14개소" 문장을 못 만든다
                "2.6.3 문화재": lambda: {
                    "시군": YB.heritage(book),
                    "면": YB.heritage(book, region=면) if 면 else CHECK},
            }
            for sec, fn in calls.items():
                try:
                    out["통계"][sec] = fn()
                except Exception as e:
                    out["통계"][sec] = CHECK
                    확인필요(f"통계.{sec}", "판단", f"통계연보에서 못 읽음: {e}")
            확인필요("통계.통계연보 6절", "판단",
                     "연도 행은 **최신 행**을 기본값으로 썼다 — 회사 표준 확인 필요 (F-1)")

    # ── 좌표에서 나오는 값 둘 ──────────────────────────────────────────
    #    ⚠️ **여기서 실패해도 생성을 막지 않는다.** 네트워크·키·조서 서식 어느 것이
    #       어긋나도 `[확인 필요]` 로 떨어뜨리고 넘어간다 (`common.md` 환각 금지).
    if lon is not None:
        # ① 도엽번호 — **순수 계산이다.** 네트워크도 폴리곤도 필요 없다 (골든셋 8쌍 일치)
        try:
            import map_fetch
            out["공간"]["도엽번호"] = map_fetch.sheet25k(lon, lat)
        except Exception as e:
            확인필요("공간.도엽번호", "판단", f"계산 실패: {e}")

        # ② 생태·자연도 등급 — **`ecology._site_rings()` 를 그대로 쓴다.**
        #    조서 읽기·법정동코드·필지 경계·좌표변환·**임야 조각 탐침**까지 그 안에 있고,
        #    골든셋 8/8 을 낸 것이 바로 그 경로다. 손으로 재구현하면 조각 탐침이 빠져
        #    원주가 정답 `2,3등급` 대신 `3` 으로 나온다 (실제로 그랬다).
        try:
            import ecology
            site, probes = ecology._site_rings(case, lon, lat)
            r = ecology.assess(lon, lat, site_rings=site, site_probes=probes)
            grades = r.get("등급들") or []
            out["공간"]["생태자연도_등급"] = ", ".join(grades) if grades else CHECK
            out["공간"]["_생태자연도_상세"] = r
            if not site:
                확인필요("공간.생태자연도_등급", "판단",
                         "**중심점으로 판정**했다 — 편입토지조서를 못 읽었거나 필지 경계를 "
                         "못 받았다. 두 등급에 걸릴 때 나열이 빠질 수 있다 (rule §2.8.1)")
        except Exception as e:
            확인필요("공간.생태자연도_등급", "판단", f"EcoBank 판정 실패: {e}")


    # ── 2.2.1 을 지적통계로 갈아탈 때 ──────────────────────────────────
    if land_source == "지적통계":
        cad = next((p for p in NAT.glob("지적기본통계집계*.csv")), None)
        if not cad:
            확인필요("통계.2.2.1 지목별 토지이용", "자료부재",
                     "지적통계 CSV 가 없다 — 공공데이터포털에서 받을 것")
        else:
            r = IRR.지적통계(str(cad), 시군)
            if r:
                out["통계"]["2.2.1 지목별 토지이용"] = {"시군": r["지목별"] | {"합계": r["합계"]},
                                                       "면": CHECK, "_출처": r["_출처"]}
                out["_통계판"]["지적통계"] = {"파일": cad.name}
                확인필요("통계.2.2.1 지목별 토지이용", "판단",
                         f"**지적통계로 갈아탔다** (`--land-source 지적통계`). 출처 주석이 "
                         f"`{r['_출처']}` 로 바뀐다 — 통계연보가 아니다 (확인요청 G-7). "
                         "⚠️ **면 단위는 이 자료에 없다** — 읍면동 지목은 통계연보라야 한다")
            else:
                확인필요("통계.2.2.1 지목별 토지이용", "판단",
                         f"지적통계에서 {시군} 을 못 찾았다")

    # ── 자료가 아예 없는 자리 ──────────────────────────────────────────
    out["통계"]["2.1.1 지리적 좌표"] = CHECK
    확인필요("통계.2.1.1 지리적 좌표(극점)", "자료부재",
             "통계연보 **엑셀 편에 없다** — 책자 본문에만 (확인요청 G-6)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--dry-run", action="store_true")
    # ⚠️ **기본은 통계연보다.** 지적통계로 바꾸면 값은 더 새로워지지만 **출처 주석이
    #    바뀐다**(`통계연보. 천안시` → `지적통계. 국토교통부`). 그건 실무자 판단이라
    #    자동으로 갈아타지 않는다 (확인요청 G-7).
    ap.add_argument("--land-source", choices=["통계연보", "지적통계"], default="통계연보",
                    help="2.2.1 지목별 토지이용의 출처 (기본: 통계연보)")
    ap.add_argument("--offline", action="store_true",
                    help="발행처 확인을 건너뛴다 (네트워크 없는 환경)")
    ap.add_argument("--refresh", action="store_true",
                    help="**고정된 판을 버리고 최신으로 갈아탄다** (기본은 고정)")
    a = ap.parse_args()

    _vp = ROOT / "cases/small-env" / a.case / "vars/regional-overview.json"
    frozen_before = (json.loads(_vp.read_text(encoding="utf-8")).get("_통계판")
                     if _vp.exists() else {})
    v = build(a.case, refresh=a.refresh, land_source=a.land_source,
              offline=a.offline)
    filled = sum(1 for x in v["통계"].values()
                 if x not in (CHECK,) and x != [] and x is not None)
    print(f"# {a.case} — 통계 {filled}/{len(v['통계'])} 절 채움 · "
          f"확인필요 {len(v['_확인필요'])}건")
    print("\n## 고정된 판" + ("  (--refresh — 최신으로 갈아탐)" if a.refresh else ""))
    for k, st in v["_통계판"].items():
        was = (frozen_before or {}).get(k, {}).get("판")
        mark = f"   ← {was}판에서 갈아탐" if was and st.get("판") and was != st["판"] else ""
        print(f"   {k}: {st}{mark}")
    print("\n## 확인 필요")
    for c in v["_확인필요"]:
        print(f"   [{c['분류']}] {c['항목']} — {c['사유']}")

    if a.dry_run:
        return 0
    out = ROOT / "cases/small-env" / a.case / "vars/regional-overview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {out.relative_to(ROOT)}  {out.stat().st_size/1024:.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

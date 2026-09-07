#!/usr/bin/env python3
"""자원순환(0726) vars 승계 빌더 — 지역개황(0200) 통계를 기초시설표로 옮긴다.

B 승급 재료 (2026-09-07). 전례 = `build_env_status_vars.py`(0500 측정 승계).
0726 기초시설 4표는 0200 §2.7 표와 같은 원천(전국 폐기물·하수도 통계)이라
**0200 vars 를 사실 대장으로 승계**한다 — 같은 사실이 두 파트에 두 번 조사되지 않게.

열 배치는 0726 베이스를 XML(cellAddr)로 실측했다:
  하수(8열·부머리행 수계/지류·데이터 4행) · 분뇨(6열) · 음식물(6열) · 매립(6열)
0200 에 없는 열(가동개시일·수계·지류·연계처리장명)은 None → 생성 시 [확인 필요].

⚠️ 하수 표 지역 열은 세로 병합 — 행 리스트에 넣되 병합 커서 왜곡은 Windows 실측 몫.
사용: python engine/build_waste_vars.py 천안_화덕리
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fmt(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return f"{v:,.1f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"
    return str(v).strip()


def build(case: str):
    vdir = ROOT / "cases" / "small-env" / case / "vars"
    ro = json.loads((vdir / "regional-overview.json").read_text(encoding="utf-8"))
    rc_path = vdir / "resource-cycle.json"
    rc = json.loads(rc_path.read_text(encoding="utf-8"))
    t = ro.get("통계", {})
    sigun = rc.get("사업", {}).get("시군") or ro.get("사업", {}).get("시군")

    def rows(key):
        return t.get(key) or []

    기초 = {}
    hs = rows("2.7.1 공공하수처리시설")
    if hs:
        기초["하수처리시설"] = {"앵커": "지류", "skip": 0, "베이스행": 4, "행": [
            [sigun if i == 0 else None, r.get("시설명"), fmt(r.get("소 재 지") or r.get("소재지")),
             fmt(r.get("시설용량(㎥/일)")), fmt(r.get("유입하수량(㎥/일)")), None, None, None]
            for i, r in enumerate(hs)]}
    bn = rows("2.7.2 분뇨처리시설")
    if bn:
        기초["분뇨처리시설"] = {"앵커": "연계처리장명", "skip": 0, "베이스행": 1, "행": [
            [r.get("시설명"), fmt(r.get("소재지")), fmt(r.get("시설용량(㎥/일)")),
             fmt(r.get("처리량(㎥/일)")), r.get("처리공법"), None] for r in bn]}
    um = rows("2.7.3 음식물류 폐기물 처리시설")
    if um:
        기초["음식물류"] = {"앵커": "공공/민간", "skip": 0, "베이스행": 1, "행": [
            [r.get("업체/시설명"), fmt(r.get("소재지")), r.get("공공/민간"),
             fmt(r.get("시설용량(톤/일)")), r.get("처리방법"), fmt(r.get("처리량(톤/년)"))]
            for r in um]}
    ml = rows("2.7.4 매립처리시설")
    if ml:
        기초["매립처리시설"] = {"앵커": "총매립면적", "skip": 0, "베이스행": 1, "행": [
            [r.get("시설명"), fmt(r.get("소재지")), fmt(r.get("총매립면적(㎡)")),
             fmt(r.get("총매립용량(㎥)")), fmt(r.get("기매립량(㎥)")),
             fmt(r.get("잔여매립가능량(㎥)"))] for r in ml]}

    rc.setdefault("현황", {})["기초시설표"] = 기초

    # ── 성상별 5표 — ④ 원자료 catalog/data/waste_2024_{시군}.json (Windows 추출)
    # 열 위치는 표마다 달라(지정은 -2, 사업장非는 +1) 머리 2행을 forward-fill 로 파싱한다.
    # 톤/년 → 톤/일 정수 반올림(원주 표시 정수 1/1), 0 은 "-".
    # ⚠️ (나)생활 = 가정계만 적용 — 사업장非배출시설계 포함 여부는 집계 정의 갈림(1/1 미확정).
    #    천안 골든 채점으로 확정한다(집계 정의 = 규칙이라 골든 검증이 적법한 distill).
    wj_path = ROOT / "catalog" / "data" / f"waste_2024_{(sigun or '').rstrip('시군')}.json"
    성상 = {}
    통계추가 = {}
    if wj_path.exists():
        wj = json.loads(wj_path.read_text(encoding="utf-8"))

        def cols(t):
            h0, h1 = t["머리"][0], t["머리"][1]
            ff, cur = [], ""
            for c in h0:
                cur = c if c else cur
                ff.append(cur)
            i_gen = next(i for i, c in enumerate(ff) if "발생량" in c)
            i_tot = next(i for i, c in enumerate(ff) if c == "총계")
            sub = {c: i_tot + j for j, c in enumerate(h1[i_tot:i_tot + 6]) if c}
            return i_gen, sub  # sub: {재활용, 소각, 매립, 기타?}

        def tpd(x):
            v = None
            try:
                v = float(str(x).replace(",", ""))
            except (TypeError, ValueError):
                return None
            d = round(v / 365)
            return "-" if d == 0 else f"{d:,}"

        BASE_MAP = [  # (json 성상, 앵커, skip, 기타열 유무)
            ("생활계", "처리방법별 발생량", 0, True),
            ("사업장배출시설계", "처리방법별 발생량", 1, True),
            ("건설", "처리방법별 발생량", 2, False),
            ("지정", "처리방법별 발생량", 3, True),
        ]
        for key, anchor, sk, has_etc in BASE_MAP:
            tabs = wj["값"].get(key)
            if not tabs:
                continue
            t = list(tabs.values())[0]
            i_gen, sub = cols(t)
            row = t["행"][0]
            vals = [sigun, tpd(row[i_gen]), tpd(row[sub["매립"]]), tpd(row[sub["소각"]]),
                    tpd(row[sub["재활용"]])] + ([tpd(row[sub["기타"]])] if has_etc else []) + ["-"]
            성상[key] = {"앵커": anchor, "skip": sk, "행": [vals]}
        # 관리구역 표 — 면적·인구·세대 (배출·처리량 열은 이 표에 없음 → [확인 필요])
        gwan = wj["값"].get("관리구역_인구세대")
        if gwan and gwan.get("행"):
            g = gwan["행"][0]
            면적 = f"{float(g[2]):,.0f}"
            인구 = f"{int(g[3]):,}"
            성상["관리구역"] = {"앵커": "행정구역(A)", "skip": 0,
                            "행": [[sigun, 면적, 인구, 면적, 인구, "100", None, None, None]]}
            통계추가["인구"] = int(g[3])
            통계추가["세대"] = int(g[5])
        # 생활폐 배출량(톤/일) — 통계연보 원천 관행(rule §31)의 대체 경로(전국폐기물 연간/365).
        # F-4(통계연보 입수) 해소 전 임시 — 경로 차이를 _확인필요에 남긴다.
        생활 = wj["값"].get("생활계")
        if 생활:
            t = list(생활.values())[0]
            i_gen, _ = cols(t)
            통계추가["생활폐_배출량_톤일"] = round(float(str(t["행"][0][i_gen]).replace(",", "")) / 365)
    rc["현황"]["성상별표"] = 성상
    rc.setdefault("통계", {}).update({k: v for k, v in 통계추가.items()
                                    if rc.get("통계", {}).get(k) in (None, "")})
    rc.setdefault("_meta", {})["기초시설표_승계"] = {
        "원천": "regional-overview.json §2.7 (전국 폐기물·하수도 통계)",
        "판": ro.get("_통계판", {}).get("전국 폐기물 발생 및 처리현황", {}).get("판"),
    }
    need = rc.setdefault("_확인필요", [])
    for item, why in [("성상별표 (나)생활 집계 정의", "가정계만 적용 — 사업장非배출 포함 여부 갈림(1/1), 천안 골든 채점으로 확정"),
                      ("생활폐_배출량_톤일 경로", "통계연보 원천(rule §31) 대신 전국폐기물 연간/365 환산 — F-4 해소 시 교체"),
                      ("관리구역 표 배출·처리량 열", "관리구역_인구세대 표에 없는 열 — 원자료 다른 표"),
                      ("(마)소각시설", "원주 베이스에 표 없음(원주 무보유) — 천안은 2기 존재, 표 삽입 부류(할 일 2·8·10)"),
                      ("하수 표 가동개시일·수계·지류 / 분뇨 연계처리장명", "0200 표에 없는 열 — 하수도통계 원자료 상세")]:
        if not any(isinstance(x, dict) and x.get("항목") == item for x in need):
            need.append({"항목": item, "분류": "X", "사유": why})

    rc_path.write_text(json.dumps(rc, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in 기초.items():
        print(f"  {k}: {len(v['행'])}행 (베이스 {v['베이스행']}행, 앵커 {v['앵커']})")
    print(f"✓ {rc_path.relative_to(ROOT)} — 기초시설표 {len(기초)}표 승계")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "천안_화덕리")

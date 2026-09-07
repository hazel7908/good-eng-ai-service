#!/usr/bin/env python3
"""0300 대상지역·0400 주변토지 vars 조립 빌더 — 형제 파트 vars 승계 (B 승급 2순위).

두 파트는 자체 조사값이 거의 없다 — 0300 은 기상·소음진동·수질·0100 값의 요약,
0400 은 0100 조서 + 지역개황 2.2 통계의 재배치다. **사실 대장 승계**로 조립한다
(같은 사실이 파트마다 두 번 조사되지 않게 — `build_env_status_vars`·`build_waste_vars` 전례).

없는 값은 만들지 않는다(환각 금지): 면적·일정·측정항목 표기 등은 None → [확인 필요].
사용: python engine/build_area_vars.py 천안_화덕리
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(vdir, name):
    p = vdir / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(vdir, name, data):
    (vdir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                       encoding="utf-8")


def build(case: str):
    vdir = ROOT / "cases" / "small-env" / case / "vars"
    pj = load(vdir, "project-overview")
    cl = load(vdir, "climate")
    nv = load(vdir, "noise-vib")
    ro = load(vdir, "regional-overview")
    sa = pj.get("사업", {})

    # ── 0300 대상지역 — 요약 조립
    gw = cl.get("기상연보", {})
    기간 = gw.get("기간") or []
    지점들 = (nv.get("예측", {}) or {}).get("지점") or []
    ta = {
        "_meta": {"빌더": "build_area_vars", "승계": "0100(사업·일정)·0721(관측소)·0727(예측지점)"},
        "사업": {"사업명": sa.get("사업명"), "위치": sa.get("위치"),
               "면적_㎡": sa.get("면적_㎡"), "시군": sa.get("시군") or "천안시"},
        "일정": pj.get("일정", {}),
        "기상": {"관측소": (gw.get("관측소") or {}).get("표기"),
               "연보기간": f"{기간[0]}~{기간[1]}년" if len(기간) == 2 else None},
        "지점": {"예측지점수": len(지점들) or None, "조망점수": None},
        "항목": {"대기": None, "수질": None},
        "_확인필요": [
            {"항목": "면적_㎡·착공일·준공일", "분류": "X", "사유": "신청서류 원천(0100 rule §0) — 0100 vars 확정 시 자동 승계"},
            {"항목": "항목.대기·수질", "분류": "판단", "사유": "측정 항목 나열 표기 관행 미확정 — 측정보고서 원문 표기로 나열할지 rule 확인"},
            {"항목": "조망점수", "분류": "X", "사유": "경관(0728) vars 미작성 — 그쪽 확정 시 승계"},
        ],
    }
    save(vdir, "target-area", ta)

    # ── 0400 주변토지 — 조서·지목 통계 조립
    # 시군지목표: 4행(시군 면적·구성비 / 읍면 면적·구성비) × 9칸 — **베이스 열 순서**
    # (계·임야·답·하천·전·도로·과수원·대지·기타 — 원주 면적순. ⚠️ F-3: 천안 골든은 코드순
    #  계열이라 열 순서가 갈린다 — 값 집합은 같고 순서는 [실무자 확인]).
    # `기타` 는 합계 잔차로 계산한다(지목 28종 중 표에 없는 것들의 합 — 환각 아님).
    JIMOK_COLS = ["임야", "답", "하천", "전", "도로", "과수원", "대"]

    def jimok_rows(d):
        if not d:
            return None
        tot = d.get("합계")
        vals = [d.get(k) for k in JIMOK_COLS]
        if tot is None or any(x is None for x in vals):
            return None
        etc = round(tot - sum(vals), 2)
        area = [tot] + vals + [etc]
        return ([f"{x:,.2f}" for x in area],
                [f"{x / tot * 100:.2f}" for x in area])

    def yongdo_rows(d):
        if not d or d.get("합계") is None:
            return None
        tot, dosi, bidosi = d["합계"], d.get("도시지역계"), d.get("비도시지역계")
        parts = [d.get(k) for k in ("주거", "상업", "공업", "녹지")]
        if None in (dosi, bidosi) or any(x is None for x in parts):
            return None
        미지정 = round(dosi - sum(parts), 2)
        area = [tot, dosi, *parts, 미지정, bidosi, d.get("관리"), d.get("농림"), d.get("보전")]
        if any(x is None for x in area):
            return None
        return ([f"{x:,.2f}" for x in area],
                [f"{x / tot * 100:.2f}" for x in area])

    t221 = (ro.get("통계") or {}).get("2.2.1 지목별 토지이용") or {}
    sj_rows = []
    for key in ("시군", "면"):
        pair = jimok_rows(t221.get(key))
        sj_rows += list(pair) if pair else [[None] * 9, [None] * 9]
    yd = yongdo_rows((ro.get("통계") or {}).get("2.2.2 용도지역"))
    지목표 = t221
    slu = {
        "_meta": {"빌더": "build_area_vars", "승계": "0100(조서·용도)·0200(지목 통계)"},
        "사업": {"사업명": sa.get("사업명"), "시군": sa.get("시군") or "천안시"},
        "조서": pj.get("조서", {}),
        "지구용도": pj.get("토지이용") or [],
        "서술": {},
        "시군지목표": {"행": sj_rows},
        "시군용도표": {"행": list(yd) if yd else []},
        "통계": {"통계연보연도": (ro.get("_통계판", {}).get("통계연보", {}) or {}).get("판"),
               "지목별": 지목표},
        "_확인필요": [
            {"항목": "조서·지구용도", "분류": "X", "사유": "0100 편입토지조서가 비어 있음(신청서류 대기) — 확정 시 재실행"},
            {"항목": "서술 8종", "분류": "판단", "사유": "지역개황 2.2 값 기반 문장 생성은 D2(정형 문장 조립) 이식 대상 — B 본작업"},
        ],
    }
    save(vdir, "surrounding-land-use", slu)

    # ── dry-검증 — 핸들러 build_slots 를 실제로 돌려 MISSING 수를 센다
    sys.path.insert(0, str(ROOT / "engine"))
    sys.path.insert(0, str(ROOT / "engine" / "parts" / "small-env"))
    import importlib.util
    for part, data in (("target-area", ta), ("surrounding-land-use", slu)):
        spec = importlib.util.spec_from_file_location(part.replace("-", "_"),
                                                      ROOT / "engine" / "parts" / "small-env" / f"{part}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        slots = m.build_slots(data)
        miss = [k for k, x in slots.items() if str(x) == "[확인 필요]"]
        filled = {k: str(x)[:30] for k, x in slots.items() if str(x) != "[확인 필요]"}
        print(f"✓ {part}: 슬롯 {len(slots)} — 채움 {len(filled)} · 확인필요 {len(miss)}")
        for k, x in filled.items():
            print(f"    {k} = {x}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "천안_화덕리")

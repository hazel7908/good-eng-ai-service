#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0840 수질오염총량검토서 파트 핸들러 — W3 (2026-09-03 Mac). compute 내장 (원주 역산 ✓ self-test).

규약: build_slots / build_tables. 지식: rules/small-env/water-total-load.md.
1장 토큰은 0100 과 같은 이름 — vars 도 0100 것을 승계한다(되먹임 vars 는 명시). 표 6종(할당부하량 /
조서 / 토지이용계획 / 시행 전 / 시행 후 / 총괄) — 앵커·오프셋은 **Windows 셀 주소 실측 전 추정**.
계산 규약(rule §3, 1/1): 발생부하량 = 면적e-6 × 원단위, BOD 3자리·T-P 4자리 표시, **합계는 표시값의 합**,
차감 = 후 − 전(문장), 총괄표 차감 셀은 음수면 0 (J-2 확인 전 기본값).
"""
from hwp_util import MISSING, fit_rows, write_at

# 토지계 지목별 연평균 발생부하원단위 (kg/㎢/일, BOD·T-P) — 수질오염총량관리 기술지침 (표 고정)
UNIT = {"전": (4.38, 1.400), "답": (4.24, 0.467), "과수원": (2.69, 0.630), "목장용지": (3.71, 0.295),
        "임야": (1.49, 0.056), "임": (1.49, 0.056), "잡종지": (0.96, 0.027), "잡": (0.96, 0.027),
        "하천": (0.96, 0.027), "구거": (0.96, 0.027), "대지": (10.28, 0.600), "대": (10.28, 0.600),
        "공장용지": (33.10, 0.885), "창고용지": (7.25, 0.447), "도로": (12.42, 0.391), "주차장": (12.42, 0.391),
        "주유소용지": (75.02, 1.385), "체육용지": (5.39, 0.738), "유원지": (14.87, 0.609)}


def _n(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _rows(area_by):
    """지목별 면적 → [지목, 면적, 원BOD, 원TP, 발BOD(3), 발TP(4)] + 표시값 합."""
    out, sb, st = [], 0.0, 0.0
    for jimok, area in (area_by or {}).items():
        a, u = _n(area), UNIT.get(jimok)
        if a is None or u is None:
            out.append([jimok, area, None, None, None, None])
            continue
        b, t = round(a / 1e6 * u[0], 3), round(a / 1e6 * u[1], 4)
        sb, st = sb + b, st + t
        out.append([jimok, f"{a:,.0f}", f"{u[0]:.2f}", f"{u[1]:.3f}", f"{b:.3f}", f"{t:.4f}"])
    tot = sum(_n(x[1]) or 0 for x in out)
    return out, f"{tot:,.0f}", f"{sb:.3f}", f"{st:.4f}"


def compute(v):
    p = v.get("부하", {})
    r = {}
    r["전표"], r["전_면적합"], r["전_BOD"], r["전_TP"] = _rows(p.get("시행전_지목"))
    r["후표"], r["후_면적합"], r["후_BOD"], r["후_TP"] = _rows(p.get("시행후_지목"))
    for k in ("BOD", "TP"):
        a, b = _n(r["전_" + k]), _n(r["후_" + k])
        nd = 3 if k == "BOD" else 4
        r["차감_" + k] = f"{b - a:.{nd}f}" if a is not None and b is not None else None
        # 총괄·할당부하량 표의 차감(신규 부하)은 음수면 0 (1/1 관측 — J-2)
        r["총괄차감_" + k] = (f"{max(b - a, 0):.{2 if k == 'BOD' else 3}f}" if a is not None and b is not None else None)
    return r


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    r = compute(v)
    s, gj, gw = v.get("사업", {}), v.get("실시근거", {}), v.get("경위", {})
    out = {k: g(s, k) for k in ("사업명", "위치", "시행자", "용도지역", "허가권자", "사업기간", "착공일", "준공일", "준공년도", "표지연월")}
    out["면적"] = (f"{_n(s.get('면적_㎡')):,.0f}" if _n(s.get("면적_㎡")) is not None else MISSING)
    out["배경_서술"] = g(v.get("배경", {}), "서술")
    out.update({"실시근거_서술": g(gj, "서술"), "대상사업_조항": g(gj, "대상사업_조항"),
                "대상사업_기준1": g(gj, "기준1"), "대상사업_기준2": g(gj, "기준2")})
    out.update({f"경위_{k}": g(gw, k) for k in ("조사", "작성", "요청", "알림")})
    out["단위유역"] = g(v.get("총량", {}), "단위유역")
    for k in ("전_BOD", "후_BOD", "차감_BOD", "전_TP", "후_TP", "차감_TP"):
        out[k] = r[k] or MISSING
    return out


def build_tables(hwp, v):
    r = compute(v)
    W = lambda *a, **k: write_at(hwp, *a, **k)
    jo = v.get("조서", {})

    print("  할당부하량 표 — 앵커 `신규`(A 데이터 행) · 당초 4 + 금회 4 (from_anchor, col_off 3) ⚠️ 실측")
    W("신규", 0, 3, ["0.00", "0.00", "0.000", "0.000", r["총괄차감_BOD"], "0.00", r["총괄차감_TP"], "0.000"], from_anchor=True)

    print("  편입토지조서 — 0100 과 동일: 앵커 `지적면적`(머리) · n행 · 행정구역 병합 셀 A · 합계는 계산 필드 자리")
    rows = jo.get("행") or []
    fit_rows(hwp, "지적면적", 7, max(len(rows), 1), start=1)
    for i, row in enumerate(rows or [[None] * 7]):
        W("지적면적", 1 + i, 1, list(row) + [None] * (7 - len(row)))
    W("지적면적", 1, 0, [jo.get("행정구역")])
    def tot(idx):
        vals = [_n(x[idx]) for x in rows if len(x) > idx and _n(x[idx]) is not None]
        return f"{sum(vals):,.0f}" if vals else None
    W("지적면적", 1 + max(len(rows), 1), 2, [tot(2), tot(3), tot(4), tot(5), "-"])

    print("  토지이용계획 표 — 앵커 `면 적(㎡)`(머리) · 4행 + 합계 ⚠️ 실측")
    lu = v.get("토지이용") or []
    tot_a = sum(_n(x[1]) or 0 for x in lu)
    fit_rows(hwp, "면 적(㎡)", 4, max(len(lu), 1), start=1)
    for i, (name, area) in enumerate(lu or [(None, None)]):
        a = _n(area)
        W("면 적(㎡)", 1 + i, 0, [name, (f"{a:,.2f}" if a is not None else None),
                                 (f"{a / tot_a * 100:.2f}" if a is not None and tot_a else None), "-"])
    W("면 적(㎡)", 1 + max(len(lu), 1), 1, [f"{tot_a:,.2f}" if tot_a else None, "100.00", "-"])

    print("  발생부하량 시행 전 표 — 앵커 `토지이용면적`(머리 2줄, 첫 출현) · 지목 n행 + 합계")
    er = r["전표"]
    fit_rows(hwp, "토지이용면적", 3, max(len(er), 1), start=2)
    for i, row in enumerate(er or [[None] * 6]):
        W("토지이용면적", 2 + i, 0, row)
    W("토지이용면적", 2 + max(len(er), 1), 0, ["합계", r["전_면적합"], "-", "-", r["전_BOD"], r["전_TP"]])

    print("  시행 후 표 — 같은 머리 2번째(skip=1) · 1행")
    hr = r["후표"] or [[None] * 6]
    W("토지이용면적", 2, 0, hr[0], skip=1)

    print("  최종 배출부하량 총괄표 — 앵커 `차감계`(머리) · BOD/T-P 2행 7칸 ⚠️ 실측")
    W("차감계", 2, 1, [r["전_BOD"], "0", r["전_BOD"], r["후_BOD"], "0", r["후_BOD"], r["총괄차감_BOD"]])
    W("차감계", 3, 1, [r["전_TP"], "0", r["전_TP"], r["후_TP"], "0", r["후_TP"], r["총괄차감_TP"]])


def self_test():
    v = {"부하": {"시행전_지목": {"전": 53, "답": 13858, "임야": 23}, "시행후_지목": {"잡": 13934}}}
    r = compute(v)
    got = (r["전_BOD"], r["전_TP"], r["후_BOD"], r["후_TP"], r["차감_BOD"], r["차감_TP"], r["총괄차감_BOD"], r["총괄차감_TP"])
    want = ("0.059", "0.0066", "0.013", "0.0004", "-0.046", "-0.0062", "0.00", "0.000")
    rows_ok = [x[4:] for x in r["전표"]] == [["0.000", "0.0001"], ["0.059", "0.0065"], ["0.000", "0.0000"]]
    print("self-test", "✓ 원주 역산 8/8 + 행 3/3" if got == want and rows_ok else f"✗ got {got} rows {r['전표']}")
    return got == want and rows_ok


if __name__ == "__main__":
    self_test()

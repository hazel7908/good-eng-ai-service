#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0728 경관 파트 핸들러 — W3 (2026-09-03 Mac).

규약: build_slots / build_tables. 지식: rules/small-env/landscape.md.
표 6종(자연공원 / 야생생물보호구역 / 산림유전자원 / 문화재 / 조망점 총괄 / 시뮬 조망점) — 앵커·오프셋은
**Windows 셀 주소 실측 전 추정**. ⚠️ 야생생물 표 소재지 셀은 spec 의 `원주시`→`{{시군}}` 치환에 걸려
뒤섞인 값이 되므로 **항상 다시 쓴다**. 조망점별 문장은 슬롯 6 고정(드론·①~⑤ — 러프).
"""
from hwp_util import MISSING, fit_rows, write_at


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, h = v.get("사업", {}), v.get("현황", {})
    b, k, m = h.get("보호지역", {}), v.get("경관자원", {}), v.get("조망점", {})
    out = {"사업명": g(s, "사업명"), "시군": g(s, "시군"), "시군은": g(s, "시군은"), "읍면": g(s, "읍면"),
           "용도지역": g(s, "용도지역"), "면적": g(s, "면적"),
           "조사시기": g(h, "조사시기"), "통계연보연도": g(h, "통계연보연도")}
    out.update({k_: g(b, k_) for k_ in ("생태경관보전_서술", "자연공원_서술", "백두대간_서술", "습지_서술", "야생생물_서술", "산림유전_서술")})
    out.update({k_: g(k, k_) for k_ in ("스카이라인_서술", "식생보전등급", "생태자연도", "하천경관_서술", "하천경로",
                                       "농촌경관_서술", "문화재_서술", "생태경관자원_서술", "분류표_생태경관")})
    out["조망점수"] = g(m, "수")
    sv = m.get("서술", {})
    out.update({f"조망_{k_}": g(sv, k_) for k_ in ("드론", "1", "2", "3", "5")})
    out["조망점5_위치"] = g(m, "조망점5_위치")
    sim = m.get("시뮬", {})
    out.update({f"시뮬_{k_}": g(sim, k_) for k_ in ("위치", "이격거리", "이용특성")})
    out["녹화계획_서술"] = g(v.get("저감", {}), "녹화계획_서술")
    return out


def build_tables(hwp, v):
    W = lambda *a, **k: write_at(hwp, *a, **k)
    b, k, m = v.get("현황", {}).get("보호지역", {}), v.get("경관자원", {}), v.get("조망점", {})

    print("  자연공원 표 — 앵커 `시·군·구별 면적(㎢)`(머리 2줄) · 1행 9칸 ⚠️ 실측")
    rows = b.get("자연공원표") or [[None] * 9]
    fit_rows(hwp, "시·군·구별 면적(㎢)", 1, len(rows), start=2)
    for i, row in enumerate(rows):
        W("시·군·구별 면적(㎢)", 2 + i, 0, list(row) + [None] * (9 - len(row)))

    # 🚨 앵커를 `면적(㎢)` 으로 두면 **자연공원 표**가 먼저 걸린다 — 그 표 머리가
    #    `시·군·구별 면적(㎢)` 이라 **부분문자열로 포함**한다(문서 순서상 자연공원이 앞).
    #    실제로 자연공원 표의 머리행까지 야생생물 값으로 덮였다 (09-03 되먹임 실측:
    #    `구분|도별|계` → `11|강원 원주 소초면…|0.059`). 이 표에만 있는 `연번` 을 쓴다.
    print("  야생생물 보호구역 표 — 앵커 `연번`(이 표 고유) · n행 · 소재지 셀은 항상 다시 쓴다")
    rows = b.get("야생생물표") or [[None, None, None, "-"]]
    fit_rows(hwp, "연번", 3, len(rows), start=1)
    for i, row in enumerate(rows):
        W("연번", 1 + i, 0, list(row) + [None] * (4 - len(row)))

    print("  산림유전자원보호구역 표 — 앵커 `보호구역 명칭` · n행 5칸")
    rows = b.get("산림유전표") or [[None] * 5]
    fit_rows(hwp, "보호구역 명칭", 2, len(rows), start=1)
    for i, row in enumerate(rows):
        W("보호구역 명칭", 1 + i, 0, list(row) + [None] * (5 - len(row)))

    print("  문화재 표 — 앵커 `총계`(머리 3줄 병합) · 시군행·읍면행 13칸 (라벨 열은 빈칸 치환) ⚠️ 실측")
    mt = k.get("문화재표", {})
    for i, key in enumerate(("시군행", "읍면행")):
        vals = mt.get(key) or [None] * 13
        W("총계", 3 + i, 1, vals)

    print("  조망점 총괄표 — 앵커 `고정 통제 조망점 선정사유`(머리 2줄) · 드론+n행 9칸 · TM 좌표는 셀 안 3줄")
    rows = m.get("표") or [[None] * 9]
    fit_rows(hwp, "고정 통제 조망점 선정사유", 6, len(rows), start=2)
    for i, row in enumerate(rows):
        W("고정 통제 조망점 선정사유", 2 + i, 0, list(row) + [None] * (9 - len(row)))

    print("  시뮬레이션 조망점 표 — 같은 머리 문자열 2번째(skip=1) · 1행")
    row = (m.get("시뮬") or {}).get("행") or [None] * 9
    W("고정 통제 조망점 선정사유", 2, 0, list(row) + [None] * (9 - len(row)), skip=1)

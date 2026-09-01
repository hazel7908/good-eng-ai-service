#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 2장 평가대상지역 설정 핸들러 (C 스텁).

지식: rules/small-disaster/target-area.md. 서술·사유 셀은 spec 토큰이 처리한다 —
표 편집은 ●/X 매트릭스뿐인데 **채움 미구현** (아래 참조).
"""
from hwp_util import MISSING


def build_slots(v):
    sa, sul, 사유 = v.get("사업", {}), v.get("서술", {}), v.get("사유", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        "협의대상항목": g(sa, "협의대상항목"),          # 1장과 같은 값 (승계 — 불일치 금지)
        "기초조사결과_서술": g(sul, "기초조사결과"),
        **{f"사유_{k}": g(사유, k) for k in
           ("홍수", "토사", "사면안정", "하천", "내수", "사면재해", "토사재해")},
    }


def build_tables(hwp, v):
    """●/X 매트릭스(평가대상지역 설정 표)와 사유 표의 설정/해당없음 열.

    ⚠️ **채움 미구현** — 러프 방침(rule ⑤): 기준 사업(천안) 판단 패턴을 유지하고
    vars `_확인필요` 로 [실무자 확인] 에 넘긴다. ●/X 를 [확인 필요] 로 비우면 표가
    읽히지 않아 비우기도 하지 않는다. 채움은 사업별 매트릭스 관행이 n≥3 쌓인 뒤.
    """
    if v.get("설정매트릭스"):
        print("  ⚠️ 2장 — 설정매트릭스 vars 가 있으나 채움 미구현 (베이스 패턴 유지)")
    else:
        print("  2장 — ●/X 매트릭스는 기준 사업 패턴 유지 ([실무자 확인])")

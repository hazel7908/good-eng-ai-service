#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 7장 결론 핸들러 (C 스텁) — 승계 파트 (1·4·5장 vars, 값 불일치 금지).

지식: rules/small-disaster/conclusion.md. 개요 표·요약 서술은 spec 토큰이 처리한다.
"""
from hwp_util import MISSING, blank_row


def build_slots(v):
    sa, yo = v.get("사업", {}), v.get("요약", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s = {
        "사업명": g(sa, "사업명"), "위치": g(sa, "위치"),
        "면적": (f"{sa['면적_㎡']:,}" if sa.get("면적_㎡") else MISSING),
        "시행자": g(sa, "시행자"), "사업기간": g(sa, "사업기간"), "승인기관": g(sa, "승인기관"),
        "저감요약_서술": g(yo, "저감요약"), "통수능판단_서술": g(yo, "통수능판단"),
    }
    조치 = v.get("조치") or []
    for i in range(4):
        s[f"조치{i+1}"] = 조치[i] if i < len(조치) else MISSING
    return s


def build_tables(hwp, v):
    """재해저감 총괄표 + 시설물제원 리스트 — 4·5장 vars 승계.

    ⚠️ **채움 미구현** — 총괄표는 유역별 수치·시설 규모가 중첩 병합된 대형 표라
    셀 주소 실측 없이 쓰면 안 된다 (CLAUDE.md 🚨 표 채우기 규약).
    - vars `총괄` 이 있으면: 채움 미구현 경고 + 베이스 유지 (되먹임은 이 경로로 통과)
    - 없으면: **수치 행을 비운다** — 기준 사업 첨두홍수량·토사유출량 잔존 금지.
      ⚠️ 비우기 앵커·행수도 실측 전 — 첫 다른-사업 생성 때 Windows 에서 확정할 것.
    """
    if v.get("총괄"):
        print("  ⚠️ 7장 — 총괄표 vars 가 있으나 채움 미구현 (베이스 유지 — 되먹임 전용)")
        return
    # 다른 사업 생성 경로 — 수치 잔존 방지 비우기
    # 🔬 2026-09-01 Windows 실측 (XML 셀 주소):
    #   · 앵커 `재해영향 예측 및 평가 결과` 는 문서에 **1회**, 총괄표 바깥 표의 C1 이다 → skip 불필요.
    #   · 데이터는 11행 이상까지 간다 (저감대책 A2~ · 저감방안 A6[6x1]~).
    #   · 🚨 **셀 안에 표가 또 있다** (첨두홍수량·규격 소표들). `blank_row` 는 바깥 셀만
    #     지우므로 **중첩표 안 기준 사업 값은 그대로 남는다** — 베이스에 `맹곡천` 2건이
    #     바로 그 자리다 (되먹임으로는 영원히 안 잡힌다). 첫 다른-사업 생성 때
    #     중첩표까지 도는 경로를 새로 짜야 한다.
    for 앵커, 행수 in (("재해영향 예측 및 평가 결과", 12),):
        for i in range(1, 행수 + 1):
            blank_row(hwp, 앵커, i, keep_first=1)
    print("  7장 — 총괄표 비움 (계산 인풋 대기) ⚠️ 앵커 실측 전")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0300 대상지역 파트 핸들러 — W1 (2026-08-31). 반고정 표 판 — 표 편집 없음.

규약: build_slots / build_tables. 지식: rules/small-env/target-area.md.
값은 전부 다른 파트 vars 공유 (기상·소음진동·대기질·수질·0100) — 불일치 금지.
평가 8·제외 9 표는 7/7 고정이라 손대지 않는다.
"""
from hwp_util import MISSING


def build_slots(v):
    sa, il, gi, jj, hm = (v.get("사업", {}), v.get("일정", {}), v.get("기상", {}),
                           v.get("지점", {}), v.get("항목", {}))
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    return {
        "사업명": g(sa, "사업명"),
        "위치": g(sa, "위치"),
        "면적": (f"{sa['면적_㎡']:,}" if sa.get("면적_㎡") else MISSING),
        "시군": g(sa, "시군"),                  # ⚠️ 괴산·충주 골든이 원주 잔재를 남긴 자리
        "착공일": g(il, "착공일"),              # 0100 공유
        "준공일": g(il, "준공일"),
        "관측소": g(gi, "관측소"),              # 기상(0721) vars 공유
        "연보기간": g(gi, "연보기간"),          # 예: "2014~2023년"
        "예측지점수": g(jj, "예측지점수"),      # 소음진동 vars 공유
        "조망점수": g(jj, "조망점수"),
        "대기항목": g(hm, "대기"),              # 대기질 vars 공유 (측정 항목 나열)
        "수질항목": g(hm, "수질"),              # 수질 vars 공유 (천안은 COD 계열)
    }


def build_tables(hwp, v):
    print("  0300 — 표 편집 없음 (평가·제외 표 7/7 고정)")

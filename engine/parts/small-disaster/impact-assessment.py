#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 4장 재해영향 예측·평가 핸들러 — C 베이스 (2026-09-03 Mac). **계산 재현 금지** (rule §②).

규약: build_slots / build_tables. 지식: rules/small-disaster/impact-assessment.md.
build_tables 는 **결과 표를 비운다** — 확률강우량·토지이용상태·CN·도달시간·저류상수·첨두홍수량·토사유출량
채택. 값이 vars `계산` 노드에 오면(rule §② 규약) 채우는 경로는 후속(B). 방법론 표(환산계수·Huff 회귀계수·
토양군 분류·최소 침투율·유출곡선번호 기준)는 지침 상수라 **손대지 않는다**.
앵커 = 각 표 머리 문자열(덮어쓰지 않는 라벨) · header_rows 는 **Windows 셀 주소 실측 전 추정**.
"""
from hwp_util import MISSING, blank_table_here, find_in_table, write_at

# (앵커, 머리행 수, 같은 머리를 가진 표 상한) — 비울 결과 표
RESULT_TABLES = [
    ("강  우   지  속   기  간(분)", 2, 6),   # 확률강우량 · 비교검토 · General형 재산정 (재현기간 × 지속기간)
    ("임계지속기간(min)", 2, 2),             # 첨두홍수량 (유역×단계 × 빈도)
    ("도달시간(min)", 2, 2),                 # 도달시간 (Kraven)
    ("A-TYPE", 2, 4),                        # 유역별 CN값 산정 (A/B/…)
    ("퇴적토단위중량", 3, 2),                # 토사유출량 채택
    ("구성비(%)", 1, 4),                     # 토지이용상태 개발전/중/후 (⚠️ 1장 투수/불투수와 같은 값)
]


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, ob, r = v.get("사업", {}), v.get("관측소", {}), v.get("강우자료", {})
    return {
        "위험지구_요약": g(s, "위험지구_요약"), "시군": g(s, "시군"), "방재성능목표_공고": g(s, "방재성능목표_공고"),
        "관측소": g(ob, "이름"), "관측소_주소": g(ob, "주소"), "관측소_경도": g(ob, "경도"), "관측소_위도": g(ob, "위도"),
        "관측소_표고": g(ob, "표고"), "관측소_개시일": g(ob, "개시일"),
        "강우자료_기간": g(r, "기간"), "강우자료_연수": g(r, "연수"),
    }


def build_tables(hwp, v):
    print("  관측소 표 — 관측소명 셀 1 (3장과 같은 표) ⚠️ 실측")
    write_at(hwp, "행  정  구  역", 1, 1, [v.get("관측소", {}).get("이름")])
    calc = v.get("계산") or {}
    if calc:
        print("  ⚠️ `계산` 노드가 있지만 채움 경로는 미구현(C) — 결과 표를 비우고 [확인 필요] 로 둔다")
    for anchor, hdr, limit in RESULT_TABLES:
        k = 0
        while k < limit and find_in_table(hwp, anchor, skip=k):
            n = blank_table_here(hwp, header_rows=hdr)
            print(f"  비움 `{anchor}` #{k + 1} — {n}셀")
            k += 1
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 표 비우기 스킵 (천안 값이 남는다!)")

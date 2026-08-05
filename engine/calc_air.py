#!/usr/bin/env python3
"""
대기질(7.2.2) 계산 — rules/small-env/air-quality.md §3 의 공식.

소음진동의 calc.py 와 같은 위치의 모듈이다. 파트 지식(공식)은 여기,
사업 값은 vars, 문서 조작은 generate.py — 엔진은 파트를 모른다.

⚠️ E_q2 · E_q3 계수는 **사업마다 다르고 환산 공식이 미해명**이다 (rule §3-3).
   상수로 두지 않는다 — vars 입력이다. 여기 있는 것은 검증용 관측값뿐이다.
⚠️ 예측결과의 `가중치` 는 AERMOD 모델링 출력이다. 계산 불가 (rule §2-5).

자체 검증:  python engine/calc_air.py   →  rule §3 의 검증값 대조
"""

import math

WORK_HOURS = 8              # 일 작업시간 (소음진동과 동일, 4/4)
DUMP_LOAD = 10.3            # 덤프트럭 1회 적재 토량 ㎥ (4/4)
DENSITY = 1.75              # 토사 비중 ton/㎥ (4/4)
K_PM10, K_PM25 = 0.36, 0.095          # 입경 계수 (EPA AP-42)
RATIO_PM10, RATIO_PM25 = 0.45, 0.12   # TSP → PM 배율 (= 0.36/0.80 · 0.095/0.80, 4/4)
E_Q4 = 0.00004              # q4 바람 흐트러짐 계수 (4/4 고정)


# ── §3-1 일 작업량 ────────────────────────────────────────────
def daily_volume(total_m3, days):
    return total_m3 / days


def trips_per_day(daily_m3):
    """운반횟수(회/일) = ⌈일 작업량 ÷ 10.3⌉ (4/4)"""
    return math.ceil(daily_m3 / DUMP_LOAD)


def vkt_per_day(trips, dist_km, n_trucks=1):
    """VKT/일 = 운반횟수 × 이동거리 × 투입대수 × 2(왕복)"""
    return trips * dist_km * n_trucks * 2


# ── §3-2 q1 — 덤프트럭 이동 (EPA AP-42 비포장도로) ─────────────
def e_q1(P, k):
    """E(kg/VKT). 사업 변수는 강수일수 P 뿐 — 나머지 인자는 4/4 고정."""
    return (1.7 * (12 / 12) * (7.5 / 48) * (15 / 2.7) ** 0.7
            * (10 / 4) ** 0.5 * k * (365 - P) / 365)


def q1_kg_day(P, vkt, k):
    """⚠️ 실무는 E 를 표에 적은 4자리 값으로 곱한다 (표시값 연쇄).
    평창: 0.3605 × 2.4 = 0.8652 — 원값(0.36046…)이면 0.8651 로 어긋난다."""
    return round(e_q1(P, k), 4) * vkt


# ── §3-3 q2 · q3 · q4 — 기타 비산먼지 ─────────────────────────
def q2_kg_day(E_q2, daily_m3):
    """기타 장비 운행. E_q2 는 vars (사업별 — 공식 미해명). TSP 기준."""
    return E_q2 * daily_m3 * DENSITY


def q3_kg_day(E_q3, daily_m3):
    """토량 상·하적 (상적+하적 = ×2). E_q3 는 vars (PM-10/PM-2.5 별도)."""
    return E_q3 * daily_m3 * DENSITY * 2


def q4_kg_day(daily_m3):
    """바람에 의한 흐트러짐. TSP 기준."""
    return E_Q4 * daily_m3 * DENSITY


def tsp_to_pm(tsp):
    return tsp * RATIO_PM10, tsp * RATIO_PM25


def g_per_sec(kg_day):
    return kg_day * 1000 / (WORK_HOURS * 3600)


# ── §3-5 저감 후 재예측 ───────────────────────────────────────
def mitigated_weight(weight):
    """저감 후 가중치 = 저감 전 × 0.5 (최저 저감효율 50%, 4/4)"""
    return weight * 0.5


# ── 자체 검증 — rule §3 의 역산 검증값 대조 ────────────────────
def self_test():
    rows = []

    def chk(label, got, want, nd=4):
        ok = round(got, nd) == want
        rows.append(ok)
        print(f"  {'OK ' if ok else 'NG '} {label:34s} {round(got, nd)}  (기대 {want})")

    print("일 작업량 (§3-1)")
    chk("천안 2,204.85/50", daily_volume(2204.85, 50), 44.1, 2)
    chk("청주 758.90/50", daily_volume(758.90, 50), 15.18, 2)
    chk("청주 운반횟수", trips_per_day(15.18), 2, 0)
    chk("천안 운반횟수", trips_per_day(44.10), 5, 0)

    print("q1 — E(kg/VKT) (§3-2)")
    chk("P=105 PM-10 (천안·옥천)", e_q1(105, K_PM10), 0.3577)
    chk("P=100 PM-10 (청주)", e_q1(100, K_PM10), 0.3646)
    chk("P=103 PM-10 (평창)", e_q1(103, K_PM10), 0.3605)
    chk("천안 q1 = 0.3577×2.60", q1_kg_day(105, 2.60, K_PM10), 0.93, 2)

    print("q2·q4 (§3-3)")
    chk("천안 q2 PM-10", tsp_to_pm(q2_kg_day(0.0401, 44.10))[0], 1.3926)
    chk("천안 q2 PM-2.5", tsp_to_pm(q2_kg_day(0.0401, 44.10))[1], 0.3714)
    chk("청주 q2 PM-10", tsp_to_pm(q2_kg_day(0.0409, 15.18))[0], 0.4889)
    chk("천안 q3 PM-10 (E=0.00009)", q3_kg_day(0.00009, 44.10), 0.0139)
    chk("천안 q4 PM-10", tsp_to_pm(q4_kg_day(44.10))[0], 0.0014)
    chk("청주 q4 TSP", q4_kg_day(15.18), 0.0011)

    print("저감 후 (§3-5)")
    chk("천안 3.75 → 1.88", round(mitigated_weight(3.75), 2), 1.88, 2)
    chk("천안 1.30 → 0.65", mitigated_weight(1.30), 0.65, 2)

    n_ok = sum(rows)
    print(f"\n{n_ok}/{len(rows)} " + ("전부 통과 ✅" if n_ok == len(rows) else "실패 있음 ❌"))
    return n_ok == len(rows)


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

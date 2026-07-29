#!/usr/bin/env python3
"""
소음·진동 계산 — 순수 함수 (플랫폼 무관, 한글 API 불필요)

generate.py 에서 분리한 이유:
  1. Mac 에서 검증 가능해야 한다. 한글 API 는 Windows 전용이라
     엔진에 계산이 섞여 있으면 공식을 확인하려면 Windows 가 필요했다.
  2. 공식이 틀려도 조용히 지나간다. self_test() 가 골든셋 실측값과
     대조한다 — 실제로 2026-07-29 재검증에서 저감량 공식이 틀린 것이
     발견됐다 (rules/small-env/noise-vib.md §6-1 R3).

지식의 출처는 .claude/rules/small-env/noise-vib.md §3 이다.
이 파일은 그 공식을 코드로 옮긴 것일 뿐 — 값을 여기서 바꾸지 말고
rule 을 먼저 고친 뒤 반영한다.

사용:
    python engine/calc.py          # 골든셋 대조 자체 검증
"""

import math

# ============================================================
# 상수 — rules/small-env/noise-vib.md §3-4 구조화 블록과 일치
# 출처: 건설기계류 소음특성, 국립환경과학원 2003
# ============================================================
EQUIP = {
    "excavator_75_140":  {"noise": 71.7, "vib": 33.5},   # 굴삭기 75~140HP
    "excavator_under75": {"noise": 67.5, "vib": None},    # 저소음 대체용
    "dump_truck":        {"noise": 74.9, "vib": 33.3},
}

ATTEN = {
    "noise": {"r0": 15.0, "coef": 20.0},
    # 진동 계수 = 20 × n = 20 × 0.81 = 16.2
    #   ⚠️ 16.17 이 아니다. 골든셋 5개 사업 36개 행으로 확인 (R4, 2026-07-29)
    "vib":   {"r0": 7.5,  "coef": 16.2},
}

# 정온시설 종류별 목표기준 (rule §2-5)
#   주거 진동 65 는 골든셋 4/5. 괴산만 70 이고 자체 불일치까지 있다.
TARGET = {
    "R": {"noise": 65, "vib": 65},   # 민가·마을 (주거)
    "L": {"noise": 60, "vib": 57},   # 축사
}

# 분산투입 감산량 (rule §3-3 ②) — 공식이 아니라 작성자 판단.
#   골든셋: 원주 1.7 / 괴산 3.3 / 청양 4.9
#   1.7 = 76.6 - 74.9(덤프 단독), 4.9 = 76.6 - 71.7(굴삭기 단독)
DISPERSION_RANGE = (1.7, 4.9)
DISPERSION_DEFAULT = 1.7   # 가장 보수적 (저감을 적게 주장)


def composite(levels):
    """합성 레벨 = 10·log10(Σ 10^(L/10))"""
    return 10 * math.log10(sum(10 ** (x / 10) for x in levels))


def attenuate(level, dist, kind):
    """거리 감쇠. kind: 'noise' | 'vib'"""
    a = ATTEN[kind]
    return level - a["coef"] * math.log10(dist / a["r0"])


def composite_noise(equipment):
    """투입장비 목록 → 합성소음도. equipment: EQUIP 의 키 목록"""
    return composite([EQUIP[e]["noise"] for e in equipment])


def composite_vib(equipment):
    """투입장비 목록 → 합성진동레벨. 진동값이 없는 장비는 제외"""
    return composite([EQUIP[e]["vib"] for e in equipment if EQUIP[e]["vib"] is not None])


def composite_low_noise(equipment):
    """① 저소음 건설장비 투입 후 합성소음도 (rule §3-3 ①)

    굴삭기를 75HP 미만 등급(67.5)으로 **교체하고 합성을 다시 계산**한다.
    ⚠️ 저감효과 표의 값(1.7 등)을 예측치에서 빼는 것이 아니다 —
       그 열은 '한 등급 위 동력과의 차이'다. 이 오해가 R3 오류였다.
    """
    swapped = ["excavator_under75" if e.startswith("excavator") else e
               for e in equipment]
    return composite_noise(swapped)


def target(kind_code, metric):
    """정온시설 종류('R'/'L') → 목표기준"""
    return TARGET[kind_code][metric]


def verdict(predicted, limit):
    """판정. 보고서 표기는 '만족' / '상회' (‘초과’ 아님 — _category.md §3)"""
    return "만족" if predicted <= limit else "상회"


def mitigation_series(dist, equipment, dispersion=DISPERSION_DEFAULT):
    """저감 단계별 예측소음도 (rule §3-3)

    반환: (예측치, 저소음장비 후, 분산투입 후)
    ⚠️ 중간값을 반올림하지 않는다. 끝까지 실수로 계산하고
       표시할 때만 반올림한다 — 괴산 P-1 은 56.04 → 55.07 → 51.77
       로 가야 55.1 / 51.8 이 나온다.
    """
    c0 = composite_noise(equipment)
    c1 = composite_low_noise(equipment)
    base = attenuate(c0, dist, "noise")
    low  = attenuate(c1, dist, "noise")
    disp = low - dispersion          # ② 는 단순 감산이 맞다
    return base, low, disp


def sound_panel_reduction(after_dispersion, limit):
    """③ 가설방음판넬 감쇠량 — 목표기준에서 역산 (rule §3-3 ③)

    ②까지 해도 목표를 못 맞추는 지점에만 적용한다.
    청양 P-1: 72.6 - 12.64 = 59.96 ≤ 60
    """
    if after_dispersion <= limit:
        return None                   # 불필요 → 표에서 '-'
    return round(after_dispersion - limit, 2)


def distance_for_level(level, composite_level, kind="noise"):
    """목표 레벨에 도달하는 거리. 이격거리별 표(21)의 첫 칸에 쓴다."""
    a = ATTEN[kind]
    return a["r0"] * 10 ** ((composite_level - level) / a["coef"])


# ============================================================
# 자체 검증 — 골든셋 실측값 대조
# ============================================================
def self_test():
    """rules/small-env/noise-vib.md 의 공식이 골든셋과 맞는지 확인.

    ⚠️ 이것은 '검증'이지 '생성'이 아니다. 골든셋을 여는 유일한 예외이며,
       사람이 공식을 고칠 때 돌리는 개발용 도구다. 생성 경로에서는
       절대 호출하지 않는다.
    """
    EX_DUMP = ["excavator_75_140", "dump_truck"]
    EX_ONLY = ["excavator_75_140"]
    ok = True

    def check(label, got, want, tol=0.05):
        nonlocal ok
        hit = abs(got - want) <= tol
        ok &= hit
        print(f"  {'OK ' if hit else 'X  '} {label:38s} {got:8.2f}  (기대 {want})")

    print("합성 레벨 — rule §3-1 조회표")
    check("굴삭기+덤프 합성소음도", composite_noise(EX_DUMP), 76.6)
    check("굴삭기+덤프 합성진동레벨", composite_vib(EX_DUMP), 36.4)
    check("굴삭기만 합성소음도", composite_noise(EX_ONLY), 71.7)
    check("굴삭기만 합성진동레벨", composite_vib(EX_ONLY), 33.5)
    check("저소음 교체 후 합성소음도", composite_low_noise(EX_DUMP), 75.63)

    print("\n저감 단계별 예측치 — 골든셋 실측 5행")
    #  (사업, 이격거리, 감산량, 예측, 저소음후, 분산후)
    rows = [
        ("원주 P-1",  46, 1.7, 66.9, 65.9, 64.2),
        ("원주 P-2", 314, 1.7, 50.2, 49.2, 47.5),
        ("괴산 P-1", 160, 3.3, 56.0, 55.1, 51.8),
        ("괴산 P-4", 151, 3.3, 56.5, 55.6, 52.3),
        ("청양 P-2", 293, 4.9, 50.8, 49.8, 44.9),
    ]
    for name, d, sub, e0, e1, e2 in rows:
        g0, g1, g2 = mitigation_series(d, EX_DUMP, sub)
        for lbl, got, want in [("예측", g0, e0), ("저소음후", g1, e1), ("분산후", g2, e2)]:
            check(f"{name} {lbl}", round(got, 1), want, tol=0.001)

    print("\n진동 거리감쇠 — 표 24 (원주·괴산 동일, 5/5 사업 36행 검증됨)")
    cv = composite_vib(EX_DUMP)
    for d, want in zip([50, 100, 150, 200, 300, 500, 1000],
                       [23.1, 18.2, 15.3, 13.3, 10.5, 6.9, 2.0]):
        check(f"{d}m 진동레벨", round(attenuate(cv, d, "vib"), 1), want, tol=0.001)
    # 굴삭기만 쓰는 사업(여주)도 같은 계수로 맞는지 — 계수 오판을 거른다
    cv1 = composite_vib(EX_ONLY)
    for d, want in [(140, 12.9), (260, 8.6), (530, 3.5)]:
        check(f"여주 {d}m (굴삭기만)", round(attenuate(cv1, d, "vib"), 1), want, tol=0.001)

    print("\n가설방음판넬 역산 — 청양 P-1 (축사, 목표 60)")
    check("감쇠량", sound_panel_reduction(72.6, 60), 12.6, tol=0.05)

    print("\n이격거리별 표 첫 칸 — 목표 도달거리")
    check("괴산 65dB(A) 도달거리", distance_for_level(65.0, composite_noise(EX_DUMP)), 57, tol=0.6)

    print("\n" + ("전부 통과 ✅" if ok else "실패 있음 ❌ — rule §3 과 대조할 것"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

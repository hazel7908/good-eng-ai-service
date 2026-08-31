#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자원순환(7.2.6) 계산 — rules/small-env/resource-cycle.md §3.

인부·분뇨는 수질과 공유(calc_water.workers·sewage_unit_Lpd) — 여기는 이 파트 고유분만.
원칙: 끝까지 원값, 표시만 반올림 (water-quality rule §3-0 준용).

자체 검증:  python engine/calc_waste.py
"""

def waste_oil_lpd(fuel_lph, n_units, misc_pct, hours=8):
    """폐유 발생량 (ℓ/일) = 연료사용량(ℓ/hr·대) × 대수 × 잡품비(%) × 시간."""
    return fuel_lph * n_units * (misc_pct / 100) * hours


def household_unit_kgpd(gen_tpd, population):
    """생활폐기물 원단위 (kg/인·일) = 발생량(톤/일) ÷ 인구 × 1,000. 적용은 2자리."""
    return gen_tpd / population * 1000


def self_test():
    ok = 0

    def chk(name, got, want, nd=2):
        nonlocal ok
        if round(got, nd) == want:
            ok += 1
            print(f"  ✓ {name}: {round(got, nd)}")
        else:
            print(f"  ✗ {name}: 계산 {got} ≠ 골든 {want}")

    print("[폐유 — 7/7 동일값 (굴삭기 1.0㎥ + 덤프 15ton)]")
    chk("굴삭기", waste_oil_lpd(19.5, 1, 22), 34.32)
    chk("덤프트럭", waste_oil_lpd(15.9, 1, 38), 48.34)
    chk("합계", waste_oil_lpd(19.5, 1, 22) + waste_oil_lpd(15.9, 1, 38), 82.66)

    print("[생활폐 원단위]")
    chk("원주 원단위", household_unit_kgpd(191, 366306), 0.52)
    chk("원주 일량 (0.52×6)", 0.52 * 6, 3.12)
    chk("천안 원단위", household_unit_kgpd(652, 687575), 0.95)
    chk("천안 일량 (0.95×6)", 0.95 * 6, 5.70)
    chk("옥천 원단위", household_unit_kgpd(38.5, 49262), 0.78)
    # ⚠️ 괴산 골든(0.52)은 원주 값 복사 결함 — 검증 대상 아님 (rule §6-1)

    print(f"\n{ok}건 일치")
    return ok


if __name__ == "__main__":
    self_test()

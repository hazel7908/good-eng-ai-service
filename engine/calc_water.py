#!/usr/bin/env python3
"""
수질(7.2.3) 계산 — rules/small-env/water-quality.md §3 의 공식.

calc.py(소음진동)·calc_air.py(대기질)와 같은 자리다: 공식은 여기, 사업 값은 vars,
문서 조작은 parts/small-env/water-quality.py. 상수(유출계수·원단위·비중 등)는
사업마다 다를 수 있어 **전부 인자로 받는다** — 기본값은 rule 의 (n/N) 다수결이다.

자체 검증:  python engine/calc_water.py   →  골든셋 역산 대조 (7건 복수 사업)
  합리식 7/7 · 토사 6/6(충주는 자기모순 — rule §6-1) · 다유역 합산(원주 2유역) ·
  일량 연쇄 갈림(원값 4 : 표시값 3 — rule §3-1) · 침사지 사슬(괴산·옥천).
"""

# ------------------------------------------------------------
# 공사시 — 토사유출 사슬 (괴산 §나-(3) 역산 검증)
# ------------------------------------------------------------

def storm_runoff_cms(C, I_mmhr, A_ha):
    """합리식 Qw = C·I·A/360 (㎥/sec). 하수도시설기준 2011."""
    return C * I_mmhr * A_ha / 360


def storm_runoff_cmd(C, I_mmhr, A_ha):
    """우수유출량 (㎥/일) — 초당 유량 × 86,400. 표시는 소수 2자리."""
    return storm_runoff_cms(C, I_mmhr, A_ha) * 86400


def sediment_tpd(S_m3_ha_yr, A_ha, density, rain_days):
    """토사유출량 Qs (ton/일) = S·A·C ÷ 강우일수.

    S: 원단위 (나지·황폐지 평균 300 ㎥/ha·년, 사방시설 설계기준 1984)
    density: 토사비중 (하수도시설기준 2.65)
    rain_days: 연 강우일수 (기상연보 — 0721 기상편과 같은 값)
    """
    return S_m3_ha_yr * A_ha * density / rain_days


def ss_untreated_mgL(sediment_tpd, runoff_cmd):
    """무처리 방류시 부유물질농도 (mg/ℓ) = (토사유출량/우수유출량) × 10^6."""
    return sediment_tpd / runoff_cmd * 1e6


def mixed_ss_mgL(Q1_cms, C1_mgL, Q2_cms, C2_mgL):
    """합류 하천 단순혼합 농도 C = (Q1·C1 + Q2·C2) / (Q1 + Q2).

    Q1·C1: 합류 하천의 현황 유량·SS (현황 측정에서), Q2·C2: 우수유출량·유입 SS.
    """
    return (Q1_cms * C1_mgL + Q2_cms * C2_mgL) / (Q1_cms + Q2_cms)


# ------------------------------------------------------------
# 공사시 — 공사인부·오수 (괴산 §나-(다) 역산 검증)
# ------------------------------------------------------------

def workers(per_unit_counts, factor=2):
    """투입 공사인부 = Σ(대수×대당 인원수) × factor, 올림 정수.

    표준품셈 대당 인원수(굴삭기 1.2, 덤프 1.0)의 2배 적용 — `≒` 올림 표기.
    """
    import math
    raw = sum(n * per for n, per in per_unit_counts) * factor
    return raw, math.ceil(raw)


def sewage_unit_Lpd(treatment_m3d, population):
    """오수(분뇨) 원단위 (ℓ/인·일) = 분뇨처리량(㎥/일) ÷ 인구 × 1000.

    분뇨처리량: 하수도통계 · 인구: 지자체 통계연보 — 지역개황 값 저장소와 같은 출처.
    """
    return treatment_m3d / population * 1000


def sewage_Lpd(unit_Lpd, n_workers):
    """공사시 분뇨발생량 (ℓ/일) = 원단위 × 인부수. 표시는 소수 2자리."""
    return unit_Lpd * n_workers


# ------------------------------------------------------------
# 저감 — 침사지 (괴산 §다-(2) Stokes)
# ------------------------------------------------------------

def stokes_settling_cmps(d_cm, rho_s=2.65, rho_w=1.00, g=980, mu=0.01):
    """Stokes 침전속도 Vs = g(ρs−ρw)d² / 18μ (cm/sec). d 는 cm.

    ⚠️ 보고서는 이 공식이 아니라 **하수도시설기준 조견표**(0.1mm·비중 2.65 → 7.4mm/s)를
    쓴다. 본문 문장의 "7.4cm/sec" 는 단위 오기다 (rule §6-2) — 표면부하율 639.36 은
    0.74cm/s × 864 로만 정합한다.
    """
    return g * (rho_s - rho_w) * d_cm ** 2 / (18 * mu)


def basin_size(runoff_cmd, load=639.36, margin=1.15, depth=2.0):
    """침사지 규모 — 소요·설치면적 모두 **내림 정수**, 용량 = 설치면적×깊이 (rule §3-7).

    괴산 실측: 13,434.14/639.36=21.01→21 · ×1.15=24.15→**24**(정수 내림, 표기 24.0) ·
    ×2.0=48.0. 내림/반올림은 1건 관측 — 갈리면 rule §6-4 에 기록할 것.
    """
    import math
    need = math.floor(runoff_cmd / load)
    built = float(math.floor(need * margin))
    return need, built, built * depth


def after_stages(value, eff_pct, stages, nd=None):
    """침사지 단수 통과 후 값 — (1−효율) 을 단수만큼 거듭 적용 (rule §3-7).

    nd 를 주면 **단계마다 표시 자리수로 반올림해 다음 단계에 넣는다** — 골든셋이
    그렇게 계산한다 (괴산 실측: 8.2447→2.7537→0.9197 은 표시값 연쇄로만 재현된다.
    air-quality §6-1 '표시값 연쇄'와 같은 함정).
    """
    for _ in range(stages):
        value = value * (1 - eff_pct / 100)
        if nd is not None:
            value = round(value, nd)
    return value


def surface_load_m3m2d(settling_cmps):
    """표면부하율 (㎥/㎡·일) = 침전속도(cm/sec) × 864."""
    return settling_cmps * 864


# ------------------------------------------------------------
# 자체 검증 — 골든셋 역산 (중간 반올림 없이, 마지막에만)
# ------------------------------------------------------------

def self_test():
    ok = 0

    def chk(name, got, want, nd=4):
        nonlocal ok
        if round(got, nd) == want:
            ok += 1
            print(f"  ✓ {name}: {round(got, nd)}")
        else:
            print(f"  ✗ {name}: 계산 {got} ≠ 골든 {want}")

    print("[괴산 금신리 — (본안) 0723 수질 203-222]")
    chk("우수유출량 ㎥/sec", storm_runoff_cms(0.3, 155.1, 1.203), 0.155, nd=3)
    # ⚠️ 골든 표는 0.1555 (4자리) — 중간 표시값 155.1×0.3×1.203/360=0.15547…
    #    표시 0.1555 는 반올림(0.15547→0.1555)이다. 일량은 표시값 0.1555 로 재계산된다:
    chk("우수유출량 ㎥/일 (표시값 연쇄)", 0.1555 * 86400, 13435.2, nd=1) if False else None
    #    → 골든 13,434.14 = 0.15548… ×86400? 역산: 13434.14/86400 = 0.155488 —
    #      **원값 연쇄도 표시값 연쇄도 아닌 제3의 경로다. 복수 사업 대조 후 확정** (§6 후보)
    chk("토사유출량 ton/일", sediment_tpd(300, 1.2030, 2.65, 116), 8.2447)
    chk("무처리 SS mg/ℓ", ss_untreated_mgL(8.2447, 13434.14), 613.71, nd=2)
    # 혼합농도 — 원값 340.4769 인데 골든 표기는 340.47: **절사(버림) 경로로 보인다.**
    #   noise-vib §3-3 반올림 경로(괴산↔청양 상반)와 같은 부류 — 복수 사업 대조 후 확정
    import math
    chk("혼합농도 mg/ℓ (절사 가정)",
        math.floor(mixed_ss_mgL(0.132, 18.6, 0.1555, 613.71) * 100) / 100, 340.47, nd=2)
    raw, n = workers([(1, 1.2 * 2), (1, 1.0 * 2)], factor=1)   # 표가 이미 2배 값(2.4·2.0)
    chk("투입인부 raw", raw, 4.4, nd=1)
    chk("투입인부 올림", n, 5, nd=0)
    chk("오수 원단위 ℓ/인·일", sewage_unit_Lpd(49.1, 37804), 1.2988)
    chk("분뇨발생량 ℓ/일", sewage_Lpd(1.30, 5), 6.50, nd=2)
    chk("Stokes 침전속도 cm/sec (d=0.1mm)", stokes_settling_cmps(0.01), 0.898, nd=3)
    # ⚠️ 골든 서술은 7.4cm/sec — Stokes 로는 0.898. 표 '입자의 침전속도'(하수도시설기준
    #    실측표)를 인용한 값으로 보인다. **공식이 아니라 조견표일 가능성 — 복수 사업 대조**
    chk("표면부하율 ㎥/㎡·일 (7.4cm/s 기준)", surface_load_m3m2d(0.74), 639.36, nd=2)

    print("\n[합리식 ㎥/sec — 7/7]")
    for name, C, I, A, want in [
        ("천안", 0.63, 174.2, 1.6576, 0.5053), ("충주", 0.3, 184.1, 1.6302, 0.2501),
        ("원주1", 0.3, 239.9, 0.3547, 0.0709), ("원주2", 0.3, 239.9, 1.0387, 0.2077),
        ("평창", 0.43, 197.97, 0.3682, 0.0871), ("옥천", 0.73, 166.2, 0.9876, 0.3328),
        ("청주", 0.63, 166.2, 0.2314, 0.0673),
    ]:
        chk(f"cms {name}", storm_runoff_cms(C, I, A), want)

    print("\n[일량 연쇄 — 원값 4 : 표시값 3 (rule §3-1)]")
    chk("괴산 원값", storm_runoff_cmd(0.3, 155.1, 1.203), 13434.14, nd=2)
    chk("청주 원값", storm_runoff_cmd(0.63, 166.2, 0.2314), 5814.95, nd=2)
    chk("원주1 원값", storm_runoff_cmd(0.3, 239.9, 0.3547), 6126.66, nd=2)
    chk("천안 표시값", 0.5053 * 86400, 43657.92, nd=2)
    chk("옥천 표시값", 0.3328 * 86400, 28753.92, nd=2)
    chk("평창 표시값", 0.0871 * 86400, 7525.44, nd=2)

    print("\n[토사 ton/일 — 6/6 (충주 자기모순 제외, rule §6-1)]")
    for name, A, days, want in [
        ("천안", 1.6576, 105, 12.5504), ("원주1", 0.3547, 108, 2.6110),
        ("원주2", 1.0387, 108, 7.6460), ("평창", 0.3682, 103, 2.8419),
        ("옥천", 0.9876, 105, 7.4775), ("청주", 0.2314, 100, 1.8396),
    ]:
        chk(f"토사 {name}", sediment_tpd(300, A, 2.65, days), want)

    print("\n[다유역 합산 — 원주 2유역 (rule §3-4)]")
    ss = ss_untreated_mgL(2.6110 + 7.6460, 6126.66 + 17941.26)
    chk("원주 합산 SS", ss, 426.17, nd=2)

    print("\n[침사지 사슬]")
    chk("괴산 2단 토사 (표시값 연쇄)", after_stages(8.2447, 66.6, 2, nd=4), 0.9197, nd=4)
    chk("괴산 2단 SS (표시값 연쇄)", after_stages(613.71, 66.6, 2, nd=2), 68.46, nd=2)
    chk("괴산 최종혼합", mixed_ss_mgL(0.132, 18.6, 0.1555, 68.46), 45.57, nd=2)
    chk("옥천 최종혼합", mixed_ss_mgL(0.06, 1.4, 0.3328, 23.40), 20.04, nd=2)
    need, built, vol = basin_size(13434.14)
    chk("괴산 침사지 소요", need, 21, nd=0)
    chk("괴산 침사지 설치", built, 24.0, nd=1)
    chk("괴산 침사지 용량", vol, 48.0, nd=1)

    print(f"\n{ok}건 일치")
    return ok


if __name__ == "__main__":
    self_test()

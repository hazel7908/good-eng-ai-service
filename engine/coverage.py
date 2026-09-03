#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6유형 커버리지 측정 — "지금 몇 %인가"를 한 숫자로 (2026-09-01 신설).

정의 (전환계획 §5-1 완성도 사다리를 단계 점수로):
    0.00 미착수 · 0.10 재료(골든·구조 훑기) · 0.30 rule(distill) ·
    0.50 spec+핸들러(Mac 체인) · 0.70 베이스+되먹임(C+) ·
    0.85 B(러프 생성·채점 WRONG 0) · 1.00 A

  파트(장) 단위로 점수를 매겨 유형 평균 → 두 가지 총계:
    ① 유형 균등 (6유형 각 1/6)  ② 실무 건수 가중 (NAS 보유 건수 — naming.md 카테고리 표)

⚠️ 점수는 **마일스톤마다 손으로 갱신**한다 (자동 추정 금지 — 상태는 판단이다).
   갱신 이력은 git log 로 남는다. 아래 STATUS 의 근거는 CLAUDE.md ★ 행·validation.md.

    python engine/coverage.py            # 표 + 총계
"""

LADDER = {0.0: "미착수", 0.1: "재료", 0.25: "rule스텁", 0.3: "rule", 0.5: "spec", 0.7: "베이스C+",
          0.85: "B", 1.0: "A"}

# {유형: (NAS 건수, {파트: 점수})} — 2026-09-01 실측 기준
STATUS = {
    "소환 small-env": (76, {
        "0722 대기질": 1.0, "0727 소음진동": 1.0,
        "0200 지역개황": 0.85, "0721 기상": 0.85, "0723 수질": 0.85,
        "0500 환경현황": 0.8,          # 5.3 통계 자동 + 측정 승계 — B 문턱
        "0100 사업개요": 0.7, "0300 대상지역": 0.7, "0400 주변토지": 0.7,
        "0724 토지이용": 0.7, "0726 자원순환": 0.7,
        "0600 입지타당성": 0.7, "0711 동식물상": 0.7, "0725 지형지질": 0.7,   # W3 6파트 베이스+되먹임 ✅ 09-03 (⑮)
        "0728 경관": 0.7, "0800 부록": 0.7, "0840 총량검토서": 0.7,           # (n=1 원주 — 종목록·조서 셀은 핸들러 몫)
    }),
    "소재평 small-disaster": (55, {
        "1장 개요": 0.7, "2장 대상지역": 0.7, "7장 결론": 0.7,     # 베이스+되먹임 ✅ 09-01
        "3장 기초현황": 0.5, "4장 예측평가": 0.5, "5장 저감대책": 0.5,   # C spec+핸들러 09-03 (4·5장 결과 표 비우기)
        "6장 유지관리": 0.7, "8장 부록": 0.7,      # 6·8장 베이스+되먹임 09-03 (⑫-2·⑫-3)
    }),
    "재평 disaster-impact": (16, {
        f"{i}장": 0.5 for i in range(1, 9)      # 소재평 spec+핸들러 준용 층 09-03 (골격 일치 60% — 소재평 베이스 파생 C 프레임)
    }),
    "검토서 disaster-review": (4, {
        "1장 개요": 0.5, "2장 대상지역": 0.7, "3장 기초현황": 0.5,      # 2장 베이스+되먹임 100% (⑬) · 1·3·4장 C spec+핸들러 09-03
        "4장 위험요인": 0.5, "5장 부록": 0.1,
    }),
    "본환 env-impact": (10, {   # 30파트 실측(⑭) — rule 스텁 0.25 · 요약장 5+8장 spec+핸들러 0.5 (09-03)
        "summary": 0.25, "project-overview": 0.25, "target-area": 0.5, "regional-overview": 0.25, "scoping": 0.25, "public-opinion": 0.25, "alternatives": 0.25, "conservation-goal": 0.5, "flora-fauna": 0.25, "natural-assets": 0.25, "climate": 0.5, "air-quality": 0.25, "greenhouse-gas": 0.25, "water-quality": 0.25, "land-use": 0.25, "soil": 0.25, "topo-geology": 0.25, "resource-cycle": 0.25, "noise-vib": 0.25, "landscape": 0.25, "population-housing": 0.5, "strategic-reflection": 0.5, "mitigation-postmonitoring": 0.5, "unavoidable-impact": 0.5, "resident-damage": 0.5, "conclusion": 0.5, "appendix-1": 0.25, "appendix-2": 0.25, "appendix-3": 0.25, "water-total-load": 0.25
    }),
    "전략 strategic-env": (2, {   # 22파트 실측(⑭, 하천기본계획 표본) — rule 스텁 0.25 · 09-03
        "summary": 0.5, "plan-overview": 0.25, "alternatives": 0.25, "target-area": 0.5, "regional-overview": 0.25, "scoping": 0.25, "public-opinion": 0.25, "plan-adequacy": 0.25, "flora-fauna": 0.25, "natural-assets": 0.25, "topo-geology": 0.25, "landscape": 0.25, "water-quality": 0.25, "hydrology": 0.25, "climate": 0.5, "air-quality": 0.25, "noise-vib": 0.25, "resource-cycle": 0.5, "socioeconomic": 0.25, "conclusion": 0.25, "appendix": 0.25, "load-allocation-deferral": 0.25
    }),
}


def main():
    rows, tot_eq, tot_w, wsum = [], 0.0, 0.0, 0
    for name, (w, parts) in STATUS.items():
        avg = sum(parts.values()) / len(parts)
        rows.append((name, len(parts), avg, w))
        tot_eq += avg
        tot_w += avg * w
        wsum += w
    print(f"{'유형':<28}{'파트':>4}{'커버리지':>9}{'건수':>5}")
    for name, n, avg, w in rows:
        print(f"{name:<28}{n:>4}{avg*100:>8.1f}%{w:>5}")
    print(f"\n총계 ① 유형 균등        : {tot_eq/len(STATUS)*100:.1f}%")
    print(f"총계 ② 실무 건수 가중   : {tot_w/wsum*100:.1f}%  (소환>소재≫나머지 — 계획 §2-3)")
    print("\n사다리: " + " · ".join(f"{k}={v}" for k, v in LADDER.items()))


if __name__ == "__main__":
    main()

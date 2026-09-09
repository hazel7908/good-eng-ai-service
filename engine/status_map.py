#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전 영역 현황 지도 생성 — coverage(단계) × naming(장명↔슬러그) × cases(실물) 조인.

미팅 '아무 파트나 지목' 시연의 원판 (2026-09-09 신설 — 세 번 손으로 재생성하다 도구화).
    python engine/status_map.py     # → docs/20260909_전영역_현황지도.md 갱신
"""
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import coverage

ICON = {1.0: "🟢A", 0.85: "🔵B", 0.7: "🟡C", 0.5: "spec", 0.3: "rule", 0.25: "rule", 0.1: "재료", 0.0: "—"}
BASE_CASE = {"small-env": "원주_무장리", "small-disaster": "천안_삼성리", "disaster-impact": "천안_삼성리",
             "disaster-review": "원주_태장동", "env-impact": "횡성_벨라스톤CC", "strategic-env": "충북_수산천고명천"}

SE = {"0722 대기질": "air-quality", "0727 소음진동": "noise-vib", "0200 지역개황": "regional-overview",
      "0721 기상": "climate", "0723 수질": "water-quality", "0500 환경현황": "env-status",
      "0300 대상지역": "target-area", "0726 자원순환": "resource-cycle", "0600 입지타당성": "site-suitability",
      "0400 주변토지": "surrounding-land-use", "0724 토지이용": "land-use", "0100 사업개요": "project-overview",
      "0840 총량검토서": "water-total-load", "0725 지형지질": "topo-geology", "0711 동식물상": "flora-fauna",
      "0728 경관": "landscape", "0800 부록": "appendix"}
DIS = {"1": ("1장 사업 개요", "project-overview"), "2": ("2장 대상지역 설정", "target-area"),
       "3": ("3장 기초현황 조사", "baseline-survey"), "4": ("4장 재해영향 예측·평가", "impact-assessment"),
       "5": ("5장 재해영향 저감대책", "mitigation"), "6": ("6장 유지관리계획", "maintenance"),
       "7": ("7장 결론", "conclusion"), "8": ("8장 부록", "appendix")}
REV = {"1": ("1장 계획의 개요", "project-overview"), "2": ("2장 검토 대상지역 설정", "target-area"),
       "3": ("3장 기초현황 조사", "baseline-survey"), "4": ("4장 위험요인 분석·저감방향", "risk-analysis"),
       "5": ("5장 부록", "appendix")}
EI = {"summary": "1장 요약문", "project-overview": "2장 사업의 개요", "target-area": "3장 평가 대상지역",
      "regional-overview": "4장 지역개황", "scoping": "5장 평가항목·범위 심의", "public-opinion": "6장 주민의견 수렴",
      "alternatives": "7장 대안설정·평가", "conservation-goal": "8장 환경보전목표", "flora-fauna": "9.1 동식물상",
      "natural-assets": "9.1 자연환경자산", "climate": "9.2 기상", "air-quality": "9.2 대기질",
      "greenhouse-gas": "9.2 온실가스", "water-quality": "9.3 수질(수리수문)", "land-use": "9.4 토지이용",
      "soil": "9.4 토양", "topo-geology": "9.4 지형지질", "resource-cycle": "9.5 자원순환",
      "noise-vib": "9.5 소음진동", "landscape": "9.5 위락경관", "population-housing": "9.6 인구주거",
      "strategic-reflection": "10장 전략평가 협의내용 반영", "mitigation-postmonitoring": "11장 저감방안·사후조사",
      "unavoidable-impact": "12장 불가피한 환경영향", "resident-damage": "13장 주민 피해",
      "conclusion": "14장 종합평가·결론", "appendix-1": "15장 부록1(인적사항)", "appendix-2": "15장 부록2(조사목록)",
      "appendix-3": "15장 부록3(측정·모델링)", "water-total-load": "별첨 수질오염총량검토서"}
ST = {"summary": "1 요약문", "plan-overview": "2 개발기본계획 개요", "alternatives": "3 계획의 대안",
      "target-area": "4 대상지역 설정", "regional-overview": "5 지역개황", "scoping": "6 협의회 심의",
      "public-opinion": "7 주민·관계기관 의견", "plan-adequacy": "8 계획의 적정성", "flora-fauna": "9 동식물상",
      "natural-assets": "9 자연환경자산", "topo-geology": "9 지형지질", "landscape": "9 경관",
      "water-quality": "9 수질", "hydrology": "9 수리수문", "climate": "9 기상", "air-quality": "9 대기질",
      "noise-vib": "9 소음진동", "resource-cycle": "9 자원순환", "socioeconomic": "9 사회경제",
      "conclusion": "10 종합평가·결론", "appendix": "11 부록", "load-allocation-deferral": "별첨 오염총량 할당유보"}

RATIONALE = """## 왜 본환·전략은 C인가 (예상 질문 대비)

C는 미달이 아니라 **설계된 배분**이다 — 목표(82.9) 자체가 "실무 80% 두 유형은 B,
나머지는 C"의 산술값. 싸게 올릴 수 있으면 계획보다 올렸다(재평: 소재평 라인 재사용으로
계획 밖 B · 검토서: 실사업 인풋 확보 즉시 승급 — 09-09 B 도달, "인풋만 오면 이 속도"의 증거).

| 유형 | C의 이유 | 상태 |
|---|---|---|
| 본환 | 표본 1건(규칙 굳히기 금지 원칙) + 30파트 최대 물량 + 소환 재사용 불가(골격 일치 19%) | 표 배치 마무리 — 실사용 사업 생기는 순서로 승급 |
| 전략 | 표본 1건, 그마저 하천기본계획(**태양광 전략 표본이 NAS에 없다** = 실무 희소) | 〃 |

→ 미팅 답: **"어떤 유형을 먼저 쓰실지 정해주시면 그게 승급 순서가 됩니다."**
"""


def artifacts(cat, slug):
    out = []
    for p in sorted((ROOT / "cases").glob(f"{cat}/*/{slug}/output.hwpx")):
        case = p.parts[-3]
        kind = "되먹임" if case == BASE_CASE[cat] else "러프"
        pdf = "+PDF" if p.with_name("output.pdf").exists() else ""
        out.append((kind, f"{case}{pdf}"))
    out.sort(key=lambda x: x[0] != "러프")
    return out


def main():
    cats = [("소환 small-env", "small-env", [(k, k, SE[k]) for k in coverage.STATUS["소환 small-env"][1]]),
            ("소재평 small-disaster", "small-disaster", [(k,) + DIS[k[0]] for k in coverage.STATUS["소재평 small-disaster"][1]]),
            ("재평 disaster-impact", "disaster-impact", [(k,) + DIS[k[0]] for k in coverage.STATUS["재평 disaster-impact"][1]]),
            ("검토서 disaster-review", "disaster-review", [(k,) + REV[k[0]] for k in coverage.STATUS["검토서 disaster-review"][1]]),
            ("본환 env-impact", "env-impact", [(k, EI[k], k) for k in coverage.STATUS["본환 env-impact"][1]]),
            ("전략 strategic-env", "strategic-env", [(k, ST[k], k) for k in coverage.STATUS["전략 strategic-env"][1]])]
    lines = ["# 전 영역 현황 지도 — 6유형 90파트 한 장 (미팅용, `engine/status_map.py` 자동 생성)", "",
             "> 원천: `engine/coverage.py`(단계) + `docs/naming.md`(장명↔폴더) + cases/ 실물 스캔.",
             "> **모든 유형·모든 파트가 처음으로 '틀 이상'에 도달한 상태** — 이제부터는 실사용",
             "> 피드백이 각 파트의 `[확인 필요]`(채움 내역서)를 메워가는 단계다.",
             ">",
             "> **지목 시연**: 지목받은 장을 아래 표에서 찾아 `cases/{유형}/{사업}/{폴더}/output.hwpx`",
             "> 를 연다(맥 한글 뷰어 검증 ✅ / 윈도우 한글). **러프 판 우선**. `되먹임` 만 있는 파트",
             "> (본환·전략 전체)는 설명 필수: *\"기준 사업을 자기 틀에 다시 부어 배치를 검증한 판 —",
             "> 신규 사업 값이 아니라 틀의 실물\"*. 같은 폴더 `fill-report.md` 가 사람 몫 명세.", ""]
    tot, missing = collections.Counter(), []
    for title, cat, rows in cats:
        n, parts = coverage.STATUS[title]
        dist = collections.Counter(ICON[parts[k]] for k, _, _ in rows)
        tot.update(dist)
        lines += [f"## {title} — {len(rows)}파트 (실무 {n}건) · " + " · ".join(f"{a} {b}" for a, b in sorted(dist.items(), reverse=True)),
                  "", "| 장 | 폴더(슬러그) | 단계 | 열어볼 실물 |", "|---|---|:-:|---|"]
        for key, kor, slug in rows:
            arts = artifacts(cat, slug)
            if not arts:
                cell = "— (생성물 없음)"
                missing.append(f"{title.split()[0]} {kor}")
            else:
                cell = " · ".join(f"**{c}**({k})" if k == "러프" else f"{c}({k})" for k, c in arts[:3])
            lines.append(f"| {kor} | `{slug}` | {ICON[parts[key]]} | {cell} |")
        lines.append("")
    lines.insert(11, "**전체 분포: " + " · ".join(f"{k} {c}" for k, c in sorted(tot.items(), reverse=True))
                 + f" — 90파트 전부 재료 이상, 미착수 0 · 지목 즉시 열람 {90 - len(missing)}/90**")
    lines.insert(12, "")
    if missing:
        lines += [f"## ⚠️ 생성물이 아직 없는 파트 {len(missing)}", ""] + [f"- {m}" for m in missing] + [""]
    lines.append(RATIONALE)
    dst = ROOT / "docs" / "20260909_전영역_현황지도.md"
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"지도 갱신 → {dst.name} · 분포 " + " ".join(f"{k}{c}" for k, c in sorted(tot.items(), reverse=True))
          + f" · 지목 가능 {90 - len(missing)}/90" + (f" · 없음 {missing}" if missing else ""))


if __name__ == "__main__":
    main()

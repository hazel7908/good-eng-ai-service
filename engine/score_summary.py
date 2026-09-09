#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""채점 결과 일람 — 흩어진 validation.md 54개를 한 표로 (2026-09-09 신설).

배경: 파트별 채점은 `cases/{카테고리}/{사업}/{파트}/validation.md` 에 기록되는데
비교·보고용 일람이 없었다(커버리지 사다리는 단계만 본다). 이 스크립트가 전수를 긁어
`catalog/review/score_summary.md` 를 생성한다 — 커밋해 두면 미팅·보고에서 바로 쓴다.

⚠️ validation.md 는 `score_part --write` 가 덮어쓰는 **마지막 채점 시점**의 기록이다.
   재생성 후 재채점 전이면 낡을 수 있어 파일 날짜를 함께 싣는다.

    python engine/score_summary.py          # 표 출력 + catalog/review/score_summary.md 갱신
"""
import datetime
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAT_LABEL = {"small-env": "소환", "small-disaster": "소재평", "disaster-impact": "재평",
             "disaster-review": "검토서", "env-impact": "본환", "strategic-env": "전략"}
# 기준 사업 = 되먹임(자기 검증 — 점수가 채점이 아니라 엔진 검증) 구분용
BASE_CASE = {"small-env": "원주_무장리", "small-disaster": "천안_삼성리",
             "disaster-impact": "천안_삼성리", "disaster-review": "원주_태장동",
             "env-impact": "횡성_벨라스톤CC", "strategic-env": "충북_수산천고명천"}


def main():
    rows = []
    for f in sorted(ROOT.glob("cases/*/*/*/validation.md")):
        cat, case, part = f.parts[-4], f.parts[-3], f.parts[-2]
        t = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"OK\+문형\s+(\d+)/(\d+)\s*=\s*([\d.]+)%", t)
        if not m:
            continue
        wrong = re.search(r"WRONG\s+(\d+)건", t)
        w = wrong.group(1) if wrong else ("0" if "WRONG 0" in t or "✅" in t else "?")
        day = datetime.date.fromtimestamp(f.stat().st_mtime).isoformat()
        kind = "되먹임" if case == BASE_CASE.get(cat) else "채점"
        rows.append((CAT_LABEL.get(cat, cat), case, part, kind, f"{m.group(3)}%",
                     f"{m.group(1)}/{m.group(2)}", w, day))
    rows.sort(key=lambda r: (r[3], r[0], r[1], -float(r[4].rstrip("%"))))

    lines = ["# 채점 결과 일람 (자동 생성 — `engine/score_summary.py`)", "",
             f"> 갱신 {datetime.date.today().isoformat()} · validation.md {len(rows)}건 집계.",
             "> 채점 = 정답 보고서와 항목 대조(OK+문형/전체). WRONG 은 **코드로 고칠 결함** 기준이",
             "> 아니라 채점기 표시 그대로다 — 정답지 부류(G-1·문형 갈림 등) 분류는 각 validation.md 참조.",
             "> **구분**: '채점' = 다른-사업 생성 대조(진짜 성능) · '되먹임' = 기준 사업 자기 검증(엔진 배치 확인 — 점수 비교 무의미).", "",
             "| 유형 | 사업 | 파트 | 구분 | 채점 | 항목 | WRONG | 채점일 |", "|---|---|---|:-:|--:|--:|:-:|---|"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    dst = ROOT / "catalog" / "review" / "score_summary.md"
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))
    print(f"… 총 {len(rows)}건 → {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

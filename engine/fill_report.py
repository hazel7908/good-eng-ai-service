#!/usr/bin/env python3
"""
채움 내역서(fill-report) 생성 — vars JSON → cases/{카테고리}/{사업}/{파트}/fill-report.md

왜 있나:
  output.hwpx 는 완성본과 똑같이 생겨서, 검토하는 실무자가 문서만 봐서는
  "뭐가 자동으로 채워졌고, 뭘 의심하고, 뭘 직접 채워야 하는지" 알 수 없다.
  그 지도가 이 문서다. output.hwpx 옆에 두고 위에서 아래로 훑으면 검토 동선이 된다.

validation.md 와의 역할 구분:
  - fill-report.md : 생성 시점, 인풋+rule 만으로. "이렇게 채웠고 근거는 이것" (자기 신고)
  - validation.md  : 검증 단계, 골든셋 필요. "정답과 대조하니 무엇이 틀렸나" (채점표)
  실무에는 정답이 없으므로 실무자 손에 가는 것은 fill-report 뿐이다.

원천은 vars JSON 하나다. 이 스크립트는 판단하지 않는다:
  - `_확인필요` 배열 {항목, 분류, 사유}      → ❓ / ⚠️ 절
  - PART_HANDLERS 의 slots 핸들러 반환값     → ✅ 채움 값 목록
  "왜"를 여기서 새로 쓰지 않는다 — vars 작성(생성 3단계) 때 `_확인필요` 에 적는다.
  설명이 길면 사유에는 요지 한 줄 + rule 절 번호만 적는다 (rule 을 고치면
  낡은 복사본이 남는 사고 방지 — generate-report SKILL.md 머리글 참조).

플랫폼 무관 (한글 API 불필요). Mac 에서도 돈다:
    python engine/fill_report.py small-env noise-vib 천안_화덕리
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate import MISSING, load_part_handlers

ROOT = Path(__file__).parent.parent

# ❓ = 값이 없어 실무자가 채워야 함 / ⚠️ = 채웠지만 확인 필요
ASK_KINDS = ("X",)                    # 나머지(삽도△·판단 등)는 전부 ⚠️


def _cell(v):
    """마크다운 표 셀용 문자열."""
    if v is None:
        return "—"
    return str(v).replace("|", "\\|").replace("\n", " ")


def build(category, part, case):
    vars_path = ROOT / "cases" / category / case / "vars" / f"{part}.json"
    v = json.loads(vars_path.read_text(encoding="utf-8"))

    build_slots, _ = load_part_handlers(category, part)
    slots = build_slots(v)

    checks = v.get("_확인필요", [])
    ask = [c for c in checks if c.get("분류") in ASK_KINDS]
    warn = [c for c in checks if c.get("분류") not in ASK_KINDS]
    meta = v.get("_meta", {})
    rule = meta.get("규칙", f".claude/rules/{category}/{part}.md")

    L = []
    L.append(f"# 채움 내역 — {case} / {part}")
    L.append("")
    L.append(f"> 생성 데이터: `cases/{category}/{case}/vars/{part}.json` "
             f"(작성일 {meta.get('작성일', '?')}) · 근거 규칙: `{rule}`")
    L.append("> 이 문서는 vars 에서 기계적으로 생성된다 (`engine/fill_report.py`). "
             "내용을 고치려면 vars 를 고치고 다시 뽑을 것.")
    L.append("")
    L.append(f"검토 요약: **직접 채울 것 {len(ask)}건 · 확인할 것 {len(warn)}건 · "
             f"자동 채움 {len(slots)}칸**")
    L.append("")

    L.append(f"## ❓ 실무자가 채워야 하는 것 ({len(ask)}건)")
    L.append("")
    L.append("문서에는 `[확인 필요]` 또는 `-` 로 나간 자리다. 값을 지어내지 않았다.")
    L.append("건수는 **사실(vars 항목) 기준**이라 아래 ✅ 빈칸 수와 1:1이 아니다 — "
             "본문 빈칸으로 가는 항목은 ✅ 목록에 `← ❓` 로 표시되고, "
             "**표 안 자리로 가는 항목은 ✅ 목록에 나타나지 않는다.**")
    L.append("")
    L.append("| 항목 | 왜 비웠나 |")
    L.append("|---|---|")
    for c in ask:
        L.append(f"| {_cell(c.get('항목'))} | {_cell(c.get('사유'))} |")
    L.append("")

    L.append(f"## ⚠️ 채웠지만 확인이 필요한 것 ({len(warn)}건)")
    L.append("")
    L.append("삽도 판독(정밀도 낮음)이거나, 회사 표준이 없어 기본값을 쓴 항목이다.")
    L.append("")
    L.append("| 항목 | 분류 | 근거와 한계 |")
    L.append("|---|:--:|---|")
    for c in warn:
        L.append(f"| {_cell(c.get('항목'))} | {_cell(c.get('분류'))} "
                 f"| {_cell(c.get('사유'))} |")
    L.append("")

    L.append(f"## ✅ 자동으로 채운 빈칸 ({len(slots)}칸)")
    L.append("")
    L.append("베이스 문서의 `{{토큰}}` 자리에 들어간 값. 빈칸 위치는 "
             f"`templates/{category}/{part}.slots.md` 참조.")
    L.append("")
    L.append("| 빈칸(토큰) | 들어간 값 |")
    L.append("|---|---|")
    for k, val in slots.items():
        mark = " ← ❓" if str(val) == MISSING else ""
        L.append(f"| `{k}` | {_cell(val)}{mark} |")
    L.append("")
    L.append("> 표 안의 계산값과 표 편집(행 수 조절·서식)은 이 목록에 없다 — 계산은 "
             "`engine/calc.py` · `calc_air.py` 가 하며 골든셋 대조 자체검증을 내장한다. "
             "골든셋이 있는 사업의 항목별 채점은 같은 폴더 `validation.md`.")
    L.append("")

    out = ROOT / "cases" / category / case / part / "fill-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    return out, len(ask), len(warn), len(slots)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category")
    ap.add_argument("part")
    ap.add_argument("case")
    a = ap.parse_args()
    out, ask, warn, filled = build(a.category, a.part, a.case)
    print(f"{out}\n  ❓ 직접 채울 것 {ask} · ⚠️ 확인 {warn} · ✅ 자동 {filled}")


if __name__ == "__main__":
    main()

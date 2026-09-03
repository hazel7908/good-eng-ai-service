#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 6장 유지관리계획 핸들러 (C+ — 2026-09-03 Mac).

지식: rules/small-disaster/maintenance.md. 본체는 2/2 내용 고정(실측) — 손대지 않는다.
사업 고유는 **유지관리대장 작성 항목 표** 한 개: Ⅰ 시설물제원 / Ⅱ 일반 유지관리 × 개발중 /
개발후 = 셀 4개에 번호 목록(5장 시설 제원 승계). 셀 하나가 여러 문단이라 `\\n` 으로 잇는다
(set_cell 줄바꿈은 Windows 가 09-01 고침). 시설 목록이 없으면 `[확인 필요]` 한 줄로 **비운다**
— 천안의 `플륨관 D300, 104.8m` 같은 규격은 텍스트라 표유출검사 ③이 못 잡는 부류다.
⚠️ 앵커 `Ⅰ. 시설물제원`·`Ⅱ. 일반 유지관리`(A열 라벨 셀, 문단 첫 줄)는 Windows 실측 전.
"""
from hwp_util import MISSING, write_at

# 고정 라벨 (2/2 실측 — 천안·충주 동일)
_L = {"I_first": "시설물제원 유지관리 대상 항목", "I_last": "저감방안 관련",
      "II_first": "일반 유지관리 대상 항목", "II_mid_last": "저감방안 관련",
      "II_mid_extra": "현장관리 관련", "II_after_last": "일반관리 관련"}


def _list(first, items, *tails):
    """`1. 첫 라벨` + 시설 n줄 + 꼬리 라벨들 → 번호 붙여 한 셀 텍스트."""
    body = list(items) if items else [MISSING]
    lines = [first] + body + list(tails)
    return "\n".join(f"{i}. {t}" for i, t in enumerate(lines, 1))


def build_slots(v):
    sa = v.get("사업", {})
    return {"사업명": sa.get("사업명") or MISSING}


def build_tables(hwp, v):
    f = v.get("시설", {})            # {"개발중": [..제원 포함..], "개발후": [...]} — 5장 vars 승계
    중, 후 = f.get("개발중"), f.get("개발후")
    # Ⅱ(일반 유지관리)는 같은 시설의 **이름만** 쓴다 (천안 실측: 가배수로 / 침사지). 없으면 [확인 필요].
    중_이름 = f.get("개발중_이름") or ([MISSING] if not 중 else 중)
    후_이름 = f.get("개발후_이름") or ([MISSING] if not 후 else 후)
    write_at(hwp, "Ⅰ. 시설물제원", 0, 1, [
        _list(_L["I_first"], 중, _L["I_last"]),
        _list(_L["I_first"], 후, _L["I_last"])], from_anchor=True)
    write_at(hwp, "Ⅱ. 일반 유지관리", 0, 1, [
        _list(_L["II_first"], 중_이름, _L["II_mid_last"], _L["II_mid_extra"]),
        _list(_L["II_first"], 후_이름, _L["II_after_last"])], from_anchor=True)
    print("  6장 — 유지관리대장 작성 항목 표 4셀 " + ("채움" if (중 or 후) else "비움([확인 필요])")
          + " ⚠️ 앵커 실측 전")

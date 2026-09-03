#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 7장 결론 핸들러 (C 스텁) — 승계 파트 (1·4·5장 vars, 값 불일치 금지).

지식: rules/small-disaster/conclusion.md. 개요 표·요약 서술은 spec 토큰이 처리한다.
"""
from hwp_util import (MISSING, blank_row, blank_table_here, cell_addr,
                      clear_cell_paras, down, enter_table, find_in_table,
                      right, table_ctrls)


def build_slots(v):
    sa, yo = v.get("사업", {}), v.get("요약", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s = {
        "사업명": g(sa, "사업명"), "위치": g(sa, "위치"),
        "면적": (f"{sa['면적_㎡']:,}" if sa.get("면적_㎡") else MISSING),
        "시행자": g(sa, "시행자"), "사업기간": g(sa, "사업기간"), "승인기관": g(sa, "승인기관"),
        "저감요약_서술": g(yo, "저감요약"), "통수능판단_서술": g(yo, "통수능판단"),
    }
    조치 = v.get("조치") or []
    for i in range(4):
        s[f"조치{i+1}"] = 조치[i] if i < len(조치) else MISSING
    return s


def build_tables(hwp, v):
    """재해저감 총괄표 + 시설물제원 리스트 — 4·5장 vars 승계.

    ⚠️ **채움 미구현** — 총괄표는 유역별 수치·시설 규모가 중첩 병합된 대형 표라
    셀 주소 실측 없이 쓰면 안 된다 (CLAUDE.md 🚨 표 채우기 규약).
    - vars `총괄` 이 있으면: 채움 미구현 경고 + 베이스 유지 (되먹임은 이 경로로 통과)
    - 없으면: **수치 행을 비운다** — 기준 사업 첨두홍수량·토사유출량 잔존 금지.
      ⚠️ 비우기 앵커·행수도 실측 전 — 첫 다른-사업 생성 때 Windows 에서 확정할 것.
    """
    if v.get("총괄"):
        print("  ⚠️ 7장 — 총괄표 vars 가 있으나 채움 미구현 (베이스 유지 — 되먹임 전용)")
        return
    # ── 다른 사업 생성 경로 — 기준 사업 값 잔존 금지
    # 🔬 2026-09-03 실측 (충주 첫 다른-사업 생성 · HWPX XML 셀 주소 · 컨트롤 앵커):
    #   · 외곽 표는 **11행**, A·B 는 재해유형 라벨(서식 고정) · C·D 가 내용이다.
    #   · 🚨 **C·D 칸 7곳에 표가 또 들어 있다** (부모 칸 → 머리행 수 = NEST).
    #     `blank_row` 는 바깥 칸만 지워 중첩표 안 천안 값(`43.51`·`1.596`·`3.77`·
    #     `D400`·`씨드스프레이`)이 **전부 살아남았다.** 표유출검사도 못 잡는다 —
    #     ②는 최상위 표만 보고 ①은 지명만 본다(`맹곡천` 1건만 걸렸다).
    #   · 중첩표는 **캐럿으로 못 들어간다** → `table_ctrls()` 앵커로 `enter_table()`.
    #   · 칸을 `set_cell` 로 비우면 **칸 안 표가 지워진다** → `clear_cell_paras`,
    #     표가 앵커된 문단은 건너뛴다.
    OUTER, ROWS = "재해영향 예측 및 평가 결과", 11
    NEST = {("C", 3): 2, ("D", 3): 2, ("C", 5): 2, ("D", 5): 1,
            ("C", 7): 1, ("C", 9): 1, ("C", 11): 1}      # 부모칸 → 머리행 수
    ctrls = table_ctrls(hwp)
    비움, 중첩 = 0, 0
    for col_off, cname in ((0, "C"), (1, "D")):
        for r in range(2, ROWS + 1):
            if not find_in_table(hwp, OUTER):            # 행마다 앵커에서 다시 찾는다
                print(f"    WARNING: 앵커 '{OUTER}' 못 찾음")
                break
            right(hwp, col_off)
            down(hwp, r - 1)
            a = cell_addr(hwp)
            if not a or a[0] != cname or a[1] != r:
                continue                                 # 어긋나면 건드리지 않는다
            lst = hwp.GetPos()[0]                         # 이 칸의 목록 id
            inner = [c for c in ctrls if c[0] == lst]
            비움 += clear_cell_paras(hwp, {c[1] for c in inner})
            hdr = NEST.get((cname, r))
            for _l, _p, ctrl in inner:
                if hdr and enter_table(hwp, ctrl):
                    중첩 += blank_table_here(hwp, hdr)
    print(f"  7장 — 총괄표 비움 {비움}문단 + 중첩표 {중첩}칸 (계산 인풋 대기)")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `socioeconomic` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 사회경제 — 지목·용도·인구·산업 서술 수확(소환 0724 문형) + 하천명 · 통계 표 비움(B: 통계 소싱). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables, blank_value_cells

BLANK = [("구성비", 2, 4), ("수립연장", 2, 2), ("세대", 2, 3), ("행정구역", 1, 2),
         # ⚠️ 09-08 anchor_suggest — 되먹임 사각 25표 중 사업 고유 8개. 머리행 셀을
         #    베이스에서 실측했고(표 안 · 한 문단 · 문서 내 1~2회) anchor_check 통과분만.
         #    평가기준·보상규정·제방표준단면도(TYPE-A/D/H/L)는 고정이라 뺐다.
         ("건조지역", 2, 1), ("공사시작", 1, 1), ("제방정비 완료구간", 2, 1),
         ("미수립 구간", 2, 1), ("구조물명칭", 1, 1), ("경간장", 1, 1),
         ("고호", 1, 1), ("소류력", 2, 2)]
# 🚨 지구별 축제·보축계획 14표는 **라벨-값 격자**라 blank_tables 로 못 비운다 —
#    머리행이 따로 없고 한 행 안에 `계획홍수위 | El. | 150.27~156.39 | m` 처럼 섞여 있다.
#    header_rows 로 자르면 값이 살아남고, 다 지우면 라벨까지 사라진다. 셀 단위 도구 필요.


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")

    # 🚨 지구별 축제·보축계획 14표는 **라벨-값 격자**다 — 머리행이 따로 없고 한 행에
    #    `계획홍수위 | El. | 150.27~156.39 | m` 처럼 라벨과 값이 섞여 있다.
    #    blank_tables 로 자르면 값이 살아남고 다 지우면 라벨이 사라진다 → 칸 단위로 간다.
    rep = ([], [])          # (비운 칸, 남긴 칸) — 첫 적용 캘리브레이션용
    k = blank_value_cells(hwp, "계획홍수위", hdr=1, limit=16, report=rep)
    if k == 0:
        print("    WARNING: 앵커 '계획홍수위' 못 찾음 — 지구별 계획 표 유출 위험")
    else:
        print(f"    [값비움 내역] 비움 {len(rep[0])} · 유지 {len(rep[1])}")
        print(f"      비움: {sorted(set(rep[0]))[:24]}")
        print(f"      유지: {sorted(set(rep[1]))[:24]}")


EXPECT = ['법정리_서술', '서술_19', '서술_527', '서술_18', '서술_268', '서술_961', '서술_656', '계획명', '시군', '읍면', '하천1_명', '하천2_명']

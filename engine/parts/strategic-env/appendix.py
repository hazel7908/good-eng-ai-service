#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategic-env `appendix` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 부록 — 인용문헌 사업 고유 줄 + 계획명·하천명·기상연보 · 참여자 명단 회사 고정 · 조사목록 캡션은 하천명 토큰이 처리. BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables

BLANK = [("성명", 1, 2)]
# 🚨 09-08 — 측정사진 표 14개(되먹임 사각 21표의 대부분)는 `blank_tables` 로 못 비운다.
#    머리행이 없고 `측정항목|W-1(1차)` / `측정지점|{{시군}} {{읍면}} 고명리` 가 3행마다
#    되풀이되는 **라벨-값 격자**다. header_rows 로 자르면 값이 남고, 다 지우면 라벨까지
#    사라진다. 게다가 칸마다 기준 사업 **사진**이 박혀 있어 텍스트로는 손도 못 댄다.
#    (지정현황·기술인력 표는 회사 상시라 고정 — 비우면 안 된다.)


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['부록문헌1_줄', '부록문헌2_줄', '기상_기간', '관측소', '계획명', '시군', '읍면', '하천1_명', '하천2_명']

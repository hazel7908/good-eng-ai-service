# -*- coding: utf-8 -*-
"""본환 `strategic-reflection` 베이스 명세 — C (2026-09-03 Mac). 기준 = 횡성_벨라스톤CC (골든 줄에서 프로그램 생성 — 손 타이핑 0).

지식: rules/env-impact/strategic-reflection.md · _category.md. 협의내용↔반영 표 2개는 협의의견 문서 인풋 — 핸들러가 비운다(머리행만 남김).
순서: 긴 통문장 → 값 → 사업명·시군(맨 뒤). 본환은 소환 서식과 계보가 달라 소환 spec 을 준용하지 않는다(_category §2).
"""

REPLACE = [
    ("본 사업의 경우 전략환경영향평가 시 협의내용을 반영하여 사업을 시행하고자 하며, 전략환경영향평가시와 토지이용계획을 동일하게 수립하였다",
     "{{반영_도입}}"),
    ("벨라스톤C.C 증설사업", "{{사업명}}"),
]

SPEC = {
    "source": "횡성_벨라스톤CC",
    "src": "raw_data/nas/env-impact/횡성_벨라스톤CC/strategic-reflection.hwpx",   # 원본 파일명은 Windows 확정 (⑭ 수확 폴더)
    "replace": REPLACE,
    "paras": [],
    "cells": [],
    "expect": ["반영_도입", "사업명"],
}

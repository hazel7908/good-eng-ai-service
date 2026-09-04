# -*- coding: utf-8 -*-
"""env-impact `appendix-3` 베이스 명세 — C+ (2026-09-04 Mac). 기준 = 횡성_벨라스톤CC.

지식: rules/env-impact/appendix-3.md. 측정사진·시험성적서·모델링 입력자료 — AERMOD 제목(TITLEONE + 페이지 머리 ×9)만 토큰 · 입력 전문은 `[모델링 필요]` 부류(할 일 3) · 측정사진·성적서 스캔은 걷어내기(측정 파트 vars 승계 자리).

"""

REPLACE = [
    ("CO TITLEONE 벨라스톤C.C 증설사업 aermod", "CO TITLEONE {{사업명}} aermod"),
    ("벨라스톤C.C 증설사업 aermod", "{{사업명}} aermod"),
    ("벨라스톤C.C 증설사업", "{{사업명}}"),
]

SPEC = {
    "source": "횡성_벨라스톤CC",
    "src": "raw_data/nas/env-impact/횡성_벨라스톤CC/appendix-3.hwpx",   # 원본 파일명은 Windows 확정
    "replace": REPLACE,
    "paras": [],
    "cells": [],
    "expect": ["사업명"],
}

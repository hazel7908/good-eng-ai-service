#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-impact `land-use` 핸들러 — C 틀 (2026-09-04 Mac). 규약: vars `slots`. 토지이용 — 현황 서술 6·개발방향/시설구상/토지이용계획 9·생태면적률 서술 3·값 3 = 25토큰 · 지목/소유/편입 표 6과 생태면적률 산정 표는 비움(설계 인풋) · 환경종합/상위계획 검토(700~1,450 — 국가·도·군 계획 요약)는 반고정 문서 발췌(검토서 3장 관련계획 부류 — 부합성 표 셀만 판단). BLANK 앵커는 Windows 실측 전 추정."""
from hwp_util import MISSING, blank_tables, delete_range

BLOCK_MARK = "[확인 필요] 도·군 환경/종합/기본계획 발췌는 사업 시군의 문서 인풋 — 기준 사업(횡성) 본문은 걷어냈다"

BLANK = [("지목별 토지이용현황", 2, 4), ("편입토지면적", 1, 1), ("소유자별 토지이용현황", 2, 2), ("가중치", 1, 3)]


def build_slots(v):
    s = v.get("slots") or {}
    return {k: (s.get(k) if s.get(k) not in (None, "") else MISSING) for k in EXPECT}


def build_tables(hwp, v):
    print("  도·군 계획 발췌 2블록 — delete_range (검토서 3장 관련계획 방식 · 국가계획은 반고정 유지) ⚠️ 실측")
    if not (v.get("slots") or {}).get("계획본문유지"):
        delete_range(hwp, "제3차 강원도 환경보전계획", "환경종합계획과의 부합성")
        delete_range(hwp, "강원도 종합계획", "상위계획과의 연계성")
    for anchor, hdr, limit in BLANK:
        k = blank_tables(hwp, anchor, hdr, limit)
        if k == 0:
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 기준 사업 값 잔존 위험")


EXPECT = ['도환경계획명', '도종합계획명', '군기본계획명', '개발행위지목_서술', '용도지역_서술', '증설지목_서술', '생태면적률_본안서술', '시설구상_1', '생태면적률_초안서술', '생태면적률_현황서술', '지목_서술', '시설구상_3', '영향예측_도입', '시설구상_2', '토지이용계획_1', '개발방향_3', '환경종합_부합', '증설소유_서술', '소유_서술', '개발방향_2', '개발방향_4', '토지이용계획_2', '개발방향_1', '생태면적률_목표', '사업명', '생태면적률_개발전', '생태면적률', '시군']

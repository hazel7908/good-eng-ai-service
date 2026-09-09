#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""베이스 기준 사업 고유값 잔존 검사 — templates 전수 (2026-09-09 신설, Mac 가동).

배경: 검토서 3장에서 `지구명` 표 8개 중 핸들러가 엉뚱한 3개를 잡고 있던 결함이
**옥계리 첫 실사업 생성에서야** 드러났다 — 되먹임은 값이 자기 것이라 영원히 못 본다.
그날 쓴 진단(hwpx XML 평문 추출 → 기준 사업 고유값 세기)을 상설화한 것.
`docs/20260907_베이스_지명잔존.md`(수동 목록)의 기계화이기도 하다.

⚠️ 잔존 ≠ 결함. 세 부류로 갈린다 — 사람이 분류한다:
  ① spec 토큰 미달 (서술 문장)          → spec 추가
  ② 핸들러 미커버 표                     → BLANK/채움 추가 (생성 때 해소 예정이면 통과)
  ③ 의도 잔존 (인풋 장 본문·delete_range 안·의도된 반고정)
검사는 그대로, 판정 근거는 각 rule·spec 주석에 적는다 (검사-수정 근거 분리).

    python engine/base_residue.py                 # 전 카테고리
    python engine/base_residue.py disaster-review # 한 카테고리
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 카테고리별 기준 사업 고유값 (베이스에 남아 있으면 후보). 짧은 지명은 오탐이 많아
# **사업 문서에 실제로 나온 형태**로 적는다 — 부분문자열 덫(`지정면적`⊂`지정면`) 주의.
KEYS = {
    "small-env": ["원주시", "무장리", "호저면", "섬강", "원주천", "치악", "무장저수지", "만대산"],
    "small-disaster": ["천안시", "삼성리", "목천읍", "산방천", "승천천", "124-7"],
    "disaster-impact": ["천안시", "삼성리", "목천읍", "산방천", "조항리", "둔내면", "썬룩스"],
    "disaster-review": ["원주시", "태장동", "원주천", "섬강", "2332-1", "문막", "단구로",
                        "가현", "씨엔피", "부론", "호저면", "소초면", "잠양", "한배미", "법천", "청룡"],
    "env-impact": ["횡성", "벨라스톤", "둔내", "섬강", "월현리", "진원"],
    "strategic-env": ["수산천", "고명천", "제천시", "수산면", "고명리", "청풍", "성내리"],
}


def flat_text(hwpx: Path):
    z = zipfile.ZipFile(hwpx)
    chunks = []
    for zi in sorted(z.namelist()):
        if not re.search(r"Contents/section\d+\.xml$", zi):
            continue
        xml = z.read(zi).decode("utf-8", errors="ignore")
        chunks += [m.group(1) for m in re.finditer(r"<hp:t[^>]*>([^<]*)</hp:t>", xml) if m.group(1)]
    return chunks


def main():
    cats = sys.argv[1:] or sorted(KEYS)
    grand = 0
    for cat in cats:
        keys = KEYS[cat]
        for hp in sorted((ROOT / "templates" / cat).glob("*.hwpx")):
            lines = flat_text(hp)
            hits, seen = [], set()
            for i, l in enumerate(lines):
                s = l.strip()
                for k in keys:
                    if k in s and s[:60] not in seen:
                        seen.add(s[:60])
                        hits.append((i, k, s[:70]))
                        break
            grand += len(hits)
            mark = "  ✅" if not hits else f"  ⚠️ {len(hits):3}건"
            print(f"{mark}  {cat}/{hp.stem}")
            for i, k, s in hits[:12]:
                print(f"        L{i}|[{k}] {s}")
            if len(hits) > 12:
                print(f"        … 외 {len(hits) - 12}건")
    print(f"\n총 잔존 후보 {grand}건 (분류는 사람 몫 — 모듈 docstring ①②③)")


if __name__ == "__main__":
    main()

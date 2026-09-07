#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""법령 인용 자동 최신화 — 생성 마무리 단계 훅 (2026-09-07 신설, 지시서 ㉙).

클라이언트 요구가 "항상 최신 법령 정보 자동"이다. 베이스는 **판 고정**을 유지하고
산출물만 생성 시점 최신이 된다 — map 만 갱신하면 베이스 재빌드 없이 신규 생성물
전부에 반영된다.

  map: catalog/review/law_update_map.json   (Mac 이 법제처 API 대조로 기계 생성)
    치환[]        {old, new, 근거, 현행명, parts}   — old 는 번호까지 든 전체 표기
    인용오류의심[] {인용, 인용번호, 그 번호의 현행}  — **치환하지 않는다**. 경고만.

⚠️ **되먹임에는 걸지 않는다.** 되먹임은 기준 사업을 자기 베이스로 되돌려 배치를
   대조하는 검증이라, 법령 문자열이 바뀌면 diff 가 나는 것이 당연해 배치 결함과
   구분이 안 된다. 기준 사업이면 자동으로 건너뛰고 그 사실을 찍는다.

🚨 **`fr()` 은 몇 건을 바꿨는지 알려주지 않는다.** 그래서 적용 여부는 산출물
   텍스트로 **사후 검산**한다 — 구번호가 남아 있으면 치환이 조용히 실패한 것이다.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "catalog" / "review" / "law_update_map.json"
NUM = re.compile(r"제\s?20\d\d-\d+\s?호")


def load():
    if not MAP.exists():
        return None
    return json.loads(MAP.read_text(encoding="utf-8"))


def apply(hwp, fr, category=None, part=None):
    """map 의 `치환` 을 **파일 순서대로** AllReplace. 적용 시도 건수를 돌려준다.

    파일 순서 = Mac 이 길이 내림차순으로 정렬해 둔 것이다. 짧은 문자열을 먼저
    바꾸면 긴 표기의 일부만 바뀌어 **뒤섞인 인용**이 된다 — 순서를 바꾸지 말 것.
    """
    m = load()
    if not m:
        print("  [법령] map 이 없다 — 최신화 건너뜀")
        return 0, []
    쌍 = m.get("치환", [])
    key = f"{category}/{part}" if category and part else None
    쓸것 = [e for e in 쌍 if not key or not e.get("parts") or key in e["parts"]]
    for e in 쓸것:
        fr(hwp, e["old"], e["new"])
    의심 = [e for e in m.get("인용오류의심", [])
            if not key or not e.get("parts") or key in e["parts"]]
    print(f"  [법령] 인용 최신화 {len(쓸것)}건 시도"
          + (f" · 인용오류 의심 {len(의심)}건은 치환하지 않음" if 의심 else ""))
    return len(쓸것), 의심


def verify(text, category=None, part=None):
    """산출물 텍스트로 사후 검산 — (적용, 실패, 미등록번호).

    실패 = map 의 `old` 가 그대로 남은 것. 조용한 치환 실패를 이걸로만 잡는다.
    """
    m = load()
    if not m:
        return 0, [], []
    key = f"{category}/{part}" if category and part else None
    쓸것 = [e for e in m.get("치환", [])
            if not key or not e.get("parts") or key in e["parts"]]
    적용 = [e for e in 쓸것 if e["new"] in text]
    실패 = [e for e in 쓸것 if e["old"] in text]
    신번호 = {n for e in m.get("치환", []) for n in NUM.findall(e["new"])}
    미등록 = sorted({n for n in NUM.findall(text) if n not in 신번호})
    return len(적용), 실패, 미등록

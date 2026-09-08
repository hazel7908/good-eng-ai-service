#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미처리 표에 붙일 앵커를 **캡션으로 분류해** 제안한다 (사람 검토용 초안).

맥이 정한 판정 원칙 (2026-09-08):
  법령 · 전국 상수 · 표준 문안 · 회사 상시  → **고정**(건드리지 않는다)
  지명 · 측정 · 계획값 · 판 있는 통계        → **사업 고유**(비운다)
  애매하면 **비우는 쪽** — 남의 값이 남는 것이 최악이다. 단 앵커 라벨은 살린다.

⚠️ 이 도구는 **초안만** 낸다. 캡션 낱말로 가르는 것이라 반드시 사람이 훑어야 한다 —
   `계획홍수량에 따른 여유고`(전국 기준표)와 `계획여유고 결정`(사업 고유)이
   낱말로는 거의 같아 보인다.

  python engine/anchor_propose.py <카테고리> <파트>
"""
import importlib.util
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwp_util import console_utf8  # noqa: E402
import anchor_check as AC          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 전국 상수·표준 — 캡션에 이 말이 있으면 고정으로 본다
FIXED = ("공식", "분류", "기준(", "적용한계", "일반적 적용", "특징", "필요 여부",
         "환산계수", "회귀상수", "누가곡선", "누가우량", "함수조건", "유출곡선지수(AMC",
         "조도계수 범위", "하천의 조도계수", "Richardson", "Manning 공식", "Bligh",
         "에 따른 둑마루폭", "에 따른 여유고", "표준단면", "표준경사", "위계에 따른",
         "지정현황 기준", "산정 성과 비교",
         # 09-08 hydrology 실측 보강 — 전국 상수·문헌 상수표
         "보정계수", "와류계", "허용 소류력", "소류력 계산식", "Schiechtl", "저항성",
         "일시적 세굴깊이", "평형하상 산정방법", "유효수면폭비", "전국의",
         "권역별 평균 강수량", "Bligh 계수", "Isbash", "국부세굴심 예측",
         "가뭄대책", "가뭄 대응", "하도분류별", "분류기호",
         "산정모형 비교", "대리어종", "서식처 수리조건", "흐름의 느낌",
         "평가기준 및 필요유량")

# 캡션이 표지·번호·토큰이라 표를 못 가리키는 것 — 손대지 않는다(앵커가 캡션 자체가 된다)
SKIP_CAP = ("9.1.6", "{{계획명}}", "제9장", "-")
# 사업 고유 — 우선한다 (FIXED 와 겹치면 이쪽이 이긴다)
OWN = ("현황", "결과", "관측소", "홍수위", "수리량", "사행특성", "하상경사", "CN값",
       "도달시간", "결정", "집계", "사용량", "달성도", "계획 수립", "계획수립",
       "지배면적비", "매개변수 비교", "기점홍수위", "산정 결과", "측정결과", "입도분포",
       # 09-08 hydrology 실측 보강 — 관측소·계산 결과·계획값
       "관측기록", "곡선식", "능력 검토", "능력검토", "설치규모", "입력변수",
       "평강우량", "강우강도식 계수", "위치 및 범위", "하상변동", "연최대강우",
       "n 값 산정", "마루폭 및 하단폭 산정", "제방능력")


def classify(cap: str) -> str:
    c = cap.strip()
    if c in SKIP_CAP or len(c) < 3 or c.replace(",", "").replace(".", "").isdigit():
        return "판단보류"
    if any(k in cap for k in OWN):
        return "사업고유"
    if any(k in cap for k in FIXED):
        return "고정"
    return "애매→비움"          # 원칙상 비우는 쪽


def main():
    console_utf8()
    cat, part = sys.argv[1], sys.argv[2]
    base = ROOT / "templates" / cat / f"{part}.hwpx"
    z = zipfile.ZipFile(base)
    xml = "".join(z.read(n).decode("utf-8", "replace")
                  for n in sorted(z.namelist()) if AC.SEC.match(n))
    paras = AC.paragraphs(base)
    freq = {}
    for t, intbl in paras:
        if intbl:
            freq[t.strip()] = freq.get(t.strip(), 0) + 1

    hf = ROOT / "engine" / "parts" / cat / f"{part}.py"
    hs = importlib.util.spec_from_file_location("h", hf)
    hm = importlib.util.module_from_spec(hs)
    hs.loader.exec_module(hm)
    have = [a for a, *_ in (getattr(hm, "BLANK", None) or [])]

    caps = [(m.start(), AC._unesc("".join(re.findall(r"<hp:t>(.*?)</hp:t>", m.group(0), re.S))))
            for m in re.finditer(r"<hp:p\b(?:(?!<hp:p\b).)*?</hp:p>", xml, re.S)]

    for tm in re.finditer(r"<hp:tbl\b.*?</hp:tbl>", xml, re.S):
        blk, start = tm.group(0), tm.start()
        cells = {}
        for c in re.finditer(r"<hp:tc\b.*?</hp:tc>", blk, re.S):
            b = c.group(0)
            a = re.search(r'colAddr="(\d+)"[^>]*rowAddr="(\d+)"', b)
            if not a:
                continue
            ps = [AC._unesc("".join(re.findall(r"<hp:t>(.*?)</hp:t>", pm.group(0), re.S)))
                  for pm in re.finditer(r"<hp:p\b(?:(?!<hp:p\b).)*?</hp:p>", b, re.S)]
            cells.setdefault(int(a.group(2)), []).append(
                (int(a.group(1)), [x.strip() for x in ps if x.strip()]))
        if not cells:
            continue
        flat = " ".join(t for r in cells.values() for _, ps in r for t in ps)
        if any(a in flat for a in have) or not re.search(r"\d", flat):
            continue
        cap = next((t.strip() for p, t in reversed(caps) if p < start and t.strip()), "")
        verdict = classify(cap)
        rows = sorted(cells)
        cand = []
        for r in rows[:2]:
            for _, ps in sorted(cells[r]):
                for t in ps:
                    if (2 <= len(t) <= 26 and freq.get(t, 9) <= 2
                            and not re.fullmatch(r"[\d.,~\-()%㎜㎥㎡\s]+", t)):
                        cand.append((freq.get(t, 9), r, t))
        pick = sorted(cand)[0] if cand else None
        a = f"({pick[2]!r}, {max(1, pick[1] + 1)}, {freq.get(pick[2], 1)})" if pick else "(앵커 후보 없음)"
        print(f"{verdict:8s} | {cap[:44]:46s} | 행{len(rows):3d} | {a}")


if __name__ == "__main__":
    main()

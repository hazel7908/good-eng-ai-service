#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""베이스 무결성 전수 검사 — 생성이 베이스를 되쓴 오염을 잡는다 (2026-09-08 신설·같은 날 재설계).

배경: generate 가 베이스를 직접 열어 한글이 되써서 **재해 3장 베이스에 충주 값**, 소환
대기질 베이스는 08-06(f3e3205)부터 **한 달간 토큰 0 + 평창 값** 상태였다 (Windows caef5f7
발견·복원 — 수정은 .work.hwpx 사본 방식). 어떤 게이트도 못 잡았다 — 토큰이 없으면
`빈칸 잔여 0` 이 항상 초록이다.

⚠️ 첫 판 오탐 24건의 진짜 원인은 **추출 축소**였다 (09-08 Windows 교차 검증으로 확정):
hp:t 만 이어붙이면 계산 필드 안 토큰(hp:t 밖 텍스트 노드)을 못 세서 expect 와 어긋났다.
태그 전체 제거 방식으로 고쳐 Windows template_audit 과 같은 수를 센다. 단 expect 0 인
파트(6장 maintenance — 본체 고정)는 대조 자체가 무의미하니 이력 대조가 여전히 주 검사다.

주 검사 = **자기 이력 대조** (규약 차이에 면역 — 자기가 자기 과거와 다른가만 본다):
  ① 이력상 토큰 수 감소 — 어떤 커밋에서 토큰이 줄었으면 그 커밋이 오염을 실었다.
     (대기질 f3e3205 18→0 이 정확히 이 무늬 — 유일 실측 사례, 복원 확인됨)
  ② 워킹트리 vs HEAD — 커밋 안 된 되쓰기 (재해 3장 부류, git checkout 으로 복원).
  ③ 케이스 지명 잔존 — 기준 사업이 아닌 생성 사업 리·동 지명이 베이스 텍스트에 남음.

    python engine/base_integrity.py                  # 전수 (이력 포함 — 수 분)
    python engine/base_integrity.py --worktree-only  # 워킹트리만 (게이트용 — 빠름)
"""
import argparse
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"\{\{([^}]+)\}\}")

# 카테고리별 기준 사업 (table_leak.CATEGORY_BASE 와 같은 사실 — 독립 기재)
BASE_CASE = {"small-env": "원주_무장리", "small-disaster": "천안_삼성리",
             "disaster-impact": "천안_삼성리", "disaster-review": "원주_태장동",
             "env-impact": "횡성_벨라스톤CC", "strategic-env": "충북_수산천고명천"}


def _text_tokens(blob):
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except Exception:
        return None, None
    txt = ""
    for n in sorted(x for x in z.namelist()
                    if re.match(r"Contents/(section\d+|header\d*)\.xml$", x)):
        # ⚠️ hp:t 만 이어붙이면 **계산 필드 안 토큰을 못 센다** (hp:t 밖 텍스트 노드 —
        #    수질 30 을 25 로 세서 오탐 5건, 09-08 실측. Windows 방식과 대조로 확정).
        #    태그 전체 제거로 모든 텍스트 노드를 본다.
        txt += re.sub(r"<[^>]+>", "", z.read(n).decode("utf-8", "ignore"))
    return txt, set(TOKEN.findall(txt))


def case_names():
    out = {}
    for cat_dir in (ROOT / "cases").iterdir():
        if not cat_dir.is_dir():
            continue
        names = set()
        for case in cat_dir.iterdir():
            if case.is_dir() and case.name != BASE_CASE.get(cat_dir.name):
                tail = case.name.split("_")[-1]
                if len(tail) >= 2:
                    names.add(tail)
        out[cat_dir.name] = names
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category")
    ap.add_argument("--worktree-only", action="store_true",
                    help="이력 스캔 생략 — 워킹트리 vs HEAD + 지명 잔존만 (게이트용)")
    a = ap.parse_args()
    cnames = case_names()
    bad = 0
    for hwpx in sorted((ROOT / "templates").glob("*/*.hwpx")):
        cat = hwpx.parent.name
        if a.category and cat != a.category:
            continue
        rel = str(hwpx.relative_to(ROOT))
        txt, toks = _text_tokens(hwpx.read_bytes())
        probs = []
        # ② 워킹트리 vs HEAD
        head = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=ROOT).stdout
        if head:
            _, htoks = _text_tokens(head)
            if htoks is not None and toks is not None and len(toks) < len(htoks):
                probs.append(f"🚨 워킹트리 토큰 감소 {len(htoks)}→{len(toks)} — 커밋 안 된 되쓰기, git checkout 으로 복원")
        # ① 이력 감소
        if not a.worktree_only:
            hist = subprocess.run(["git", "log", "--format=%h", "--", rel],
                                  capture_output=True, text=True, cwd=ROOT).stdout.split()
            seq = []
            for h in reversed(hist):
                blob = subprocess.run(["git", "show", f"{h}:{rel}"], capture_output=True, cwd=ROOT).stdout
                _, t = _text_tokens(blob)
                if t is not None:
                    seq.append((h, len(t)))
            drops = [f"{seq[i-1][0]}:{seq[i-1][1]}→{seq[i][0]}:{seq[i][1]}"
                     for i in range(1, len(seq)) if seq[i][1] < seq[i-1][1]]
            # 복원 커밋으로 회복됐으면(마지막 판 ≥ 최대치) 이력 감소는 '과거 사고 기록'으로 알림만
            if drops:
                recovered = seq and seq[-1][1] >= max(n for _, n in seq)
                (probs if not recovered else probs).append(
                    ("ℹ️ 과거 감소·복원됨: " if recovered else "🚨 이력 토큰 감소: ") + " · ".join(drops))
        # ③ 케이스 지명 잔존
        hits = sorted({nm for nm in cnames.get(cat, ()) if txt and nm in txt})
        if hits:
            probs.append(f"🚨 케이스 지명 잔존: {hits}")
        real = [p for p in probs if p.startswith("🚨")]
        if probs:
            print(f"{'✗' if real else 'ℹ️'} {rel} (토큰 {len(toks or ())})")
            for p in probs:
                print("   " + p)
        if real:
            bad += 1
    print(f"\n{'🚨 오염 ' + str(bad) + '건' if bad else '✅ 전수 무결 (과거 사고는 복원 확인)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""사업 vars 골격 생성기 — 핸들러 계약(build_slots 소스)에서 빈 vars 를 뽑는다.

새 검증 사업을 열 때 파트마다 vars 노드·키를 손으로 베끼던 것을 자동화한다
(소재평 B 트랙 시동, 2026-09-08). 값은 전부 None — **인풋에서 채우기 전까지
[확인 필요]** 가 정직한 상태다(환각 금지). 식별자(사업명·시군)만 인자로 받는다.

사용: python engine/build_case_skeleton.py small-disaster 충주_지방정원 \
        --사업명 "충주 지방정원 조성사업" --시군 충주시
이미 있는 vars 파일은 건드리지 않는다(스킵).
검증: 각 골격으로 핸들러 build_slots 를 실제 호출 — 식별자 외 전부 MISSING 확인.
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VGET = re.compile(r'v\.get\("([^"]+)"')
GKEY = re.compile(r'g\((\w+),\s*"([^"]+)"\)')
SAGET = re.compile(r'(\w+)\.get\("([^"]+)"\)')


def contract(src: str):
    """build_slots 소스에서 {노드: [키…]} 를 뽑는다."""
    m = re.search(r"def build_slots\(v\):(.*?)(?:\ndef |\Z)", src, re.S)
    if not m:
        return {}
    body = m.group(1)
    # 좌변 변수 ↔ v.get("노드") 짝 — 튜플 대입 포함 (순서 대응)
    var2node = {}
    for line in body.splitlines():
        if "v.get(" not in line or "=" not in line:
            continue
        lhs = line.split("=", 1)[0]
        names = [x.strip() for x in lhs.split(",") if x.strip().isidentifier()]
        nodes = VGET.findall(line)
        if names and len(names) == len(nodes):
            var2node.update(zip(names, nodes))
    keys = {}
    for var, key in GKEY.findall(body) + SAGET.findall(body):
        node = var2node.get(var)
        if node:
            keys.setdefault(node, [])
            if key not in keys[node]:
                keys[node].append(key)
    return keys


def build(category: str, case: str, 사업명: str, 시군: str):
    hdir = ROOT / "engine" / "parts" / category
    vdir = ROOT / "cases" / category / case / "vars"
    vdir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "engine"))
    for hp in sorted(hdir.glob("*.py")):
        part = hp.stem
        vp = vdir / f"{part}.json"
        if vp.exists():
            print(f"  = {part}: 이미 있음 — 스킵")
            continue
        keys = contract(hp.read_text(encoding="utf-8"))
        d = {"_meta": {"빌더": "build_case_skeleton", "상태": "골격 — 인풋 대기",
                     "식별자출처": "NAS 카탈로그·골든 표제(인풋 확보 시 재확인)"},
             "_확인필요": [{"항목": "전 노드", "분류": "X",
                       "사유": "검증 사업 인풋 수확 대기(사업개요·설계도서) — 값 채우기 전 생성 금지 아님, [확인 필요] 러프는 가능"}]}
        for node, ks in keys.items():
            d[node] = {k: None for k in ks}
        d.setdefault("사업", {}).update({"사업명": 사업명, "시군": 시군})
        vp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        # dry-run — 핸들러가 골격을 소화하는지 + 식별자 외 전부 MISSING 인지
        spec = importlib.util.spec_from_file_location(part.replace("-", "_"), hp)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
            slots = m.build_slots(d)
            filled = [k for k, x in slots.items() if str(x) != "[확인 필요]"]
            print(f"  ✓ {part}: 노드 {list(keys)} · 슬롯 {len(slots)} (채움 {len(filled)}: {filled[:4]})")
        except Exception as e:
            print(f"  ⚠️ {part}: 골격 dry-run 실패 — {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("category"); ap.add_argument("case")
    ap.add_argument("--사업명", required=True); ap.add_argument("--시군", required=True)
    a = ap.parse_args()
    build(a.category, a.case, a.사업명, a.시군)

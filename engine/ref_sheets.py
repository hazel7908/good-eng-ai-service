#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""문헌 도엽 후보 조립 — 0800 문헌목록·0711 문헌조사의 「전국자연환경조사 {도엽명}」 자리.

규칙 (골든 7건 distill — rules/small-env/appendix.md §문헌목록):
  · 문헌 도엽 ⊆ 사업지 도엽의 3×3 이웃 (5/5 이름 단위 검증, 09-08).
  · 반경 ~5km 걸침이 후보 상한을 주지만 **결정 규칙은 아니다** — 천안에서 남쪽 3km
    청주 도엽이 걸치는데 골든 문헌엔 없다(실무자 선택 잡음 1건). → 후보로 내고
    `[실무자 확인]` 을 붙인다 (환각 금지 — 확정하지 않는다).
  · 조사 차수·연도(제5차 2019 등)는 국립생태원 도엽별 조사연도 원천이 따로 필요 —
    EcoBank 소싱 과제(미구현). 그 전까지 연도는 [확인 필요].

도엽명 DB: catalog/review/sheet_names_25k.json (공공데이터 15067685 · 시드 5/5 검증).

    python engine/ref_sheets.py 127.41144 36.76700   # 천안 화덕리
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
from map_fetch import sheet25k, sheets25k  # noqa: E402

DB = ROOT / "catalog" / "review" / "sheet_names_25k.json"


def _name(db, no):
    return (db.get(no) or {}).get("명") or f"[도엽명 미상 {no}]"


def candidates(lon, lat, half_m=5000):
    """→ {"사업지": (번호, 명), "후보": [(번호, 명)…], "문헌후보": [문자열…]}."""
    db = json.loads(DB.read_text(encoding="utf-8"))["도엽"]
    own = sheet25k(lon, lat)
    cand = sheets25k(lon, lat, half_m=half_m)
    if own not in cand:
        cand.append(own)
    out = [(no, _name(db, no)) for no in sorted(cand)]
    lit = [f"「제[확인 필요]차 전국자연환경조사 {nm} [확인 필요]」" for _no, nm in out]
    return {"사업지": (own, _name(db, own)), "후보": out, "문헌후보": lit,
            "_주의": "후보 상한 — 골든에서 반경 걸침 도엽이 문헌에 다 실리진 않았다(청주 배제 1건). 실무자 확인"}


def self_test():
    r = candidates(127.41144232874953, 36.76700235065794)   # 천안 화덕리
    names = {nm for _no, nm in r["후보"]}
    ok = r["사업지"][1] == "진천" and {"병천", "전동", "진천"} <= names
    print("self-test", "✓ 천안 — 사업지 진천 · 골든 문헌 3도엽 ⊆ 후보" if ok else f"✗ {r}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 3:
        r = candidates(float(sys.argv[1]), float(sys.argv[2]))
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        self_test()

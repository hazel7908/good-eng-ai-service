#!/usr/bin/env python3
"""자원순환(0726) vars 승계 빌더 — 지역개황(0200) 통계를 기초시설표로 옮긴다.

B 승급 재료 (2026-09-07). 전례 = `build_env_status_vars.py`(0500 측정 승계).
0726 기초시설 4표는 0200 §2.7 표와 같은 원천(전국 폐기물·하수도 통계)이라
**0200 vars 를 사실 대장으로 승계**한다 — 같은 사실이 두 파트에 두 번 조사되지 않게.

열 배치는 0726 베이스를 XML(cellAddr)로 실측했다:
  하수(8열·부머리행 수계/지류·데이터 4행) · 분뇨(6열) · 음식물(6열) · 매립(6열)
0200 에 없는 열(가동개시일·수계·지류·연계처리장명)은 None → 생성 시 [확인 필요].

⚠️ 하수 표 지역 열은 세로 병합 — 행 리스트에 넣되 병합 커서 왜곡은 Windows 실측 몫.
사용: python engine/build_waste_vars.py 천안_화덕리
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fmt(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return f"{v:,.1f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"
    return str(v).strip()


def build(case: str):
    vdir = ROOT / "cases" / "small-env" / case / "vars"
    ro = json.loads((vdir / "regional-overview.json").read_text(encoding="utf-8"))
    rc_path = vdir / "resource-cycle.json"
    rc = json.loads(rc_path.read_text(encoding="utf-8"))
    t = ro.get("통계", {})
    sigun = rc.get("사업", {}).get("시군") or ro.get("사업", {}).get("시군")

    def rows(key):
        return t.get(key) or []

    기초 = {}
    hs = rows("2.7.1 공공하수처리시설")
    if hs:
        기초["하수처리시설"] = {"앵커": "지류", "skip": 0, "베이스행": 4, "행": [
            [sigun if i == 0 else None, r.get("시설명"), fmt(r.get("소 재 지") or r.get("소재지")),
             fmt(r.get("시설용량(㎥/일)")), fmt(r.get("유입하수량(㎥/일)")), None, None, None]
            for i, r in enumerate(hs)]}
    bn = rows("2.7.2 분뇨처리시설")
    if bn:
        기초["분뇨처리시설"] = {"앵커": "연계처리장명", "skip": 0, "베이스행": 1, "행": [
            [r.get("시설명"), fmt(r.get("소재지")), fmt(r.get("시설용량(㎥/일)")),
             fmt(r.get("처리량(㎥/일)")), r.get("처리공법"), None] for r in bn]}
    um = rows("2.7.3 음식물류 폐기물 처리시설")
    if um:
        기초["음식물류"] = {"앵커": "공공/민간", "skip": 0, "베이스행": 1, "행": [
            [r.get("업체/시설명"), fmt(r.get("소재지")), r.get("공공/민간"),
             fmt(r.get("시설용량(톤/일)")), r.get("처리방법"), fmt(r.get("처리량(톤/년)"))]
            for r in um]}
    ml = rows("2.7.4 매립처리시설")
    if ml:
        기초["매립처리시설"] = {"앵커": "총매립면적", "skip": 0, "베이스행": 1, "행": [
            [r.get("시설명"), fmt(r.get("소재지")), fmt(r.get("총매립면적(㎡)")),
             fmt(r.get("총매립용량(㎥)")), fmt(r.get("기매립량(㎥)")),
             fmt(r.get("잔여매립가능량(㎥)"))] for r in ml]}

    rc.setdefault("현황", {})["기초시설표"] = 기초
    rc.setdefault("_meta", {})["기초시설표_승계"] = {
        "원천": "regional-overview.json §2.7 (전국 폐기물·하수도 통계)",
        "판": ro.get("_통계판", {}).get("전국 폐기물 발생 및 처리현황", {}).get("판"),
    }
    need = rc.setdefault("_확인필요", [])
    for item, why in [("성상별표", "전국 폐기물 발생 및 처리현황 원자료 필요(성상·처리방법별 시군 행) — 대여 맥북에 원자료 유실, Windows 재확보"),
                      ("통계.인구·생활폐_배출량_톤일", "위와 같은 원자료 — 생활폐 원단위 계산 인풋"),
                      ("하수 표 가동개시일·수계·지류 / 분뇨 연계처리장명", "0200 표에 없는 열 — 하수도통계 원자료 상세")]:
        if not any(isinstance(x, dict) and x.get("항목") == item for x in need):
            need.append({"항목": item, "분류": "X", "사유": why})

    rc_path.write_text(json.dumps(rc, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in 기초.items():
        print(f"  {k}: {len(v['행'])}행 (베이스 {v['베이스행']}행, 앵커 {v['앵커']})")
    print(f"✓ {rc_path.relative_to(ROOT)} — 기초시설표 {len(기초)}표 승계")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "천안_화덕리")

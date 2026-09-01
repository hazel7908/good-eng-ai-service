#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0500 환경현황 vars 빌더 — **손으로 만들지 않는다** (rule env-status.md §승계, 08-31 확정).

같은 사업의 측정 3파트 vars(소음진동·대기질·수질) + 0100 + 지역개황 vars 에서 키를
**복사**해 `vars/env-status.json` 을 만든다. "값 불일치 금지"(rule ⑥)의 구현 =
복사 원천 단일화. 원천 파일이 없으면 그 절 값은 None(→ `[확인 필요]`)으로 두고
`_확인필요` 에 남긴다 — 러프 원칙 그대로, 값을 지어내지 않는다.

    python engine/build_env_status_vars.py 원주_무장리
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _load(case, part):
    p = ROOT / "cases/small-env" / case / "vars" / f"{part}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def build(case):
    nv = _load(case, "noise-vib")
    aq = _load(case, "air-quality")
    wq = _load(case, "water-quality")
    po = _load(case, "project-overview")
    ro = _load(case, "regional-overview")

    need = []                                   # _확인필요 누적

    def miss(item, why):
        need.append({"항목": item, "분류": "X", "사유": why})

    def g(src, *keys):
        d = src
        for k in keys:
            if not isinstance(d, dict) or d.get(k) in (None, ""):
                return None
            d = d[k]
        return d

    # ── 사업 (0100 → 지역개황 → 측정 파트 순으로 첫 값)
    사업명 = g(po, "사업", "사업명") or g(ro, "사업", "사업명") or g(wq, "사업", "사업명")
    시군 = g(ro, "사업", "시군") or g(wq, "사업", "시군")
    읍면 = g(ro, "사업", "하위행정구역")
    if not 사업명:
        miss("사업명", "0100·지역개황·수질 vars 모두 없음")
    if not 읍면:
        miss("읍면", "지역개황 vars 의 하위행정구역 부재")

    # ── 5.2 가. 조사일시 3줄 + 조사지점 표 3행 (§승계가 정한 정확히 그 셋)
    조사 = {
        "대기_측정일시": g(aq, "현황", "측정일시"),
        "수질_측정일시": g(wq, "현황", "측정일시"),
        "소음_측정일시": g(nv, "현황", "측정일시"),
        "대기_지점명": None,                    # 지점명 표기 4종 변이 — [실무자 확인]
        "대기_지점주소": g(aq, "현황", "측정지점", "주소"),
        "수질_지점명": None,
        "수질_지점주소": g(wq, "현황", "측정지점_위치"),
        "소음진동_지점명": g(nv, "현황", "측정지점", "지점명"),
        "소음_지점주소": g(nv, "현황", "측정지점", "주소"),
    }
    for k, v in 조사.items():
        if v is None:
            src = {"대기": "air-quality", "수질": "water-quality"}.get(k[:2], "noise-vib")
            miss(k, f"{src} vars 에 값 없음 (지점명은 표기 변이로 실무자 확인)")

    # ── 5.2 나. 측정결과 표 3종 — **원 파트와 같은 vars 에서 뽑는다** (rule ⑥)
    측정 = {
        "대기": g(aq, "현황", "측정결과"),
        "수질_값": g(wq, "현황", "측정값"),
        "수질_등급": g(wq, "현황", "측정등급"),
        "수질_측정서술": g(wq, "현황", "측정결과_서술"),
        "소음": g(nv, "현황", "소음"),
        "진동": g(nv, "현황", "진동"),
        "소음기준_지역": g(nv, "기준", "소음환경기준_지역"),
        "소음기준_주간": g(nv, "기준", "소음환경기준_주간"),
        "소음기준_야간": g(nv, "기준", "소음환경기준_야간"),
        "진동기준_지역": g(nv, "기준", "생활진동규제_지역"),
        "진동기준_주간": g(nv, "기준", "생활진동규제_주간"),
        "진동기준_심야": g(nv, "기준", "생활진동규제_심야"),
    }
    for k, v in 측정.items():
        if v is None:
            miss(f"측정.{k}", "원천 파트 vars 부재 — 값 불일치 금지 원칙상 여기서 새로 쓰지 않는다")

    # ── 5.1 자연생태 — 생태자연도만 지역개황 인프라 재사용, 나머지는 동식물상/신규 소스
    생태 = {
        "생태자연도_등급들": g(ro, "공간", "_생태자연도_상세", "등급들"),
        "도엽번호": g(ro, "공간", "도엽번호"),
        "사업지_1등급": g(ro, "공간", "_생태자연도_상세", "사업지_1등급"),
        "사업지_별도관리": g(ro, "공간", "_생태자연도_상세", "사업지_별도관리"),
        "등급분포_표": None,        # 사업지 등급별 면적·구성비 — ecology.py 산출에 아직 없음
    }
    miss("생태.등급분포_표", "사업지 등급별 면적(㎡)·구성비(%) — ecology.py 미산출")
    miss("식생_서술·식생보전등급·식생 표", "동식물상(0711) 산출 인용 — 인풋 관행 미확정 (계획 §7-②)")
    miss("국토환경성_서술", "EGIS 등급 조회 — 신규 소스 미구축 (rule ②)")
    miss("생태계 현황 표", "동식물상(0711) 현지조사 결과 인용")
    miss("산줄기_서술", "산경표 서술 — 자동 소스 없음 (rule ②)")

    # ── 5.3 사회·경제 — 지역개황 2.9 원천인데 지역개황 vars 가 2.9 를 아직 안 담는다
    사회 = {"통계연보연도": None, "인구_시군서술": None, "인구_읍면서술": None,
          "인구동태_서술": None, "주거_서술": None, "산단_서술": None, "산업_서술": None}
    miss("사회.* (5.3 전체)", "지역개황 vars 에 2.9 인구·주거·산업 값 없음 — 통계연보 소싱 확장 대기")

    out = {
        "_meta": {"카테고리": "small-env", "파트": "env-status", "사업": case,
                  "작성일": str(date.today()),
                  "출처": "build_env_status_vars.py — 측정 3파트·0100·지역개황 vars 복사 (rule §승계)",
                  "원천": {"noise-vib": bool(nv), "air-quality": bool(aq),
                           "water-quality": bool(wq), "project-overview": bool(po),
                           "regional-overview": bool(ro)}},
        "사업": {"사업명": 사업명, "시군": 시군, "읍면": 읍면},
        "조사": 조사,
        "측정": 측정,
        "생태": 생태,
        "사회": 사회,
        "_확인필요": need,
    }
    p = ROOT / "cases/small-env" / case / "vars" / "env-status.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {p.relative_to(ROOT)}  (확인필요 {len(need)}건, "
          f"원천: {', '.join(k for k, v in out['_meta']['원천'].items() if v) or '없음'})")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용: python engine/build_env_status_vars.py {사업}")
    build(sys.argv[1])

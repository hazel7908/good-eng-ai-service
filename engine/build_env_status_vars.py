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
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _load(case, part):
    p = ROOT / "cases/small-env" / case / "vars" / f"{part}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _find_yearbook(시군):
    """통계연보 엑셀판(zip/폴더) 자동 탐색 → (경로, 판연도).

    규약: `raw_data/web/stats_yearbook/{시군에서 시·군 뗀 이름}/` 아래 —
    폴더명·파일명의 `20NN` 이 판연도다 (원주 2024 웹 재배포판으로 확립, 2026-09-01).
    NAS 관행 위치(`raw_data/nas/stats/…`)도 본다. 여럿이면 최신판."""
    if not 시군:
        return None, None
    best = (None, None)
    for base in (ROOT / "raw_data/web/stats_yearbook" / 시군[:-1],
                 *(ROOT / "raw_data/nas/stats").glob(f"*{시군[:-1]}*")):
        if not base.exists():
            continue
        for p in sorted(base.iterdir()):
            m = re.search(r"(20\d{2})", p.name)
            if not m:
                continue
            if p.is_dir() or p.suffix.lower() == ".zip":
                has_xlsx = any(True for _ in p.glob("*.xls*")) if p.is_dir() else True
                if has_xlsx and (best[1] is None or int(m.group(1)) > best[1]):
                    best = (p, int(m.group(1)))
    return best


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

    # ── 5.3 사회·경제 — 통계연보 원천 (⚠️ 지역개황에는 인구 절이 없다 — 0200 재사용이
    #    아니라 같은 원자료를 stats_extract.extract_0500 으로 직접 뽑는다)
    사회 = {"통계연보연도": None, "인구추이": None, "읍면인구": None,
          "인구동태": None, "주택": None, "사업체": None}
    yb_path, yb_year = _find_yearbook(시군)
    if yb_path:
        try:
            sys.path.insert(0, str(ROOT / "engine"))
            from stats_extract import extract_0500
            got = extract_0500(yb_path, 읍면=읍면)
            사회.update({"통계연보연도": yb_year, "인구추이": got["인구추이"],
                       "읍면인구": got["읍면"], "인구동태": got["인구동태"],
                       "주택": got["주택"], "사업체": got["사업체"]})
            print(f"  통계연보 {yb_year}판 ← {Path(yb_path).name}")
        except Exception as e:                      # openpyxl 부재 등 — 러프 원칙: 비운 채 감
            miss("사회.* (5.3)", f"통계연보 추출 실패: {e}")
    else:
        miss("사회.* (5.3 전체)", f"통계연보 원자료 없음 — raw_data/web/stats_yearbook/{(시군 or '')[:-1]}/ "
                              "에 엑셀판(zip/폴더)을 두면 자동 추출된다 (확인요청 F-4)")
    miss("산단_서술·산단 표", "지역개황 2.5.3 재사용은 표 서식 변이(원주 6열↔천안 4열) 판단 뒤 — 확인요청 참조")
    if 사회["주택"]:
        miss("주거_서술 '총가구수'", "골든 갈림 — 원주는 주택수 합계를, 천안은 일반가구수를 '총가구수'로 서술 (1:1). 원주 문형 채택")

    out = {
        "_meta": {"카테고리": "small-env", "파트": "env-status", "사업": case,
                  "작성일": str(date.today()),
                  "출처": "build_env_status_vars.py — 측정 3파트·0100·지역개황 vars 복사 (rule §승계)",
                  "원천": {"noise-vib": bool(nv), "air-quality": bool(aq),
                           "water-quality": bool(wq), "project-overview": bool(po),
                           "regional-overview": bool(ro)}},
        "사업": {"사업명": 사업명, "시군": 시군, "읍면": 읍면, "리": g(ro, "사업", "리")},
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

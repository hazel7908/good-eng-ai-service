#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소재평 1장 사업개요 핸들러 — 재해 첫 핸들러 (2026-09-01 Mac, C 스텁).

규약: build_slots(v) / build_tables(hwp, v). 지식: rules/small-disaster/project-overview.md.
표 채움은 소환 0100 조서 경로 이식 — ⚠️ **앵커·오프셋 전부 Windows 실측 전** (평면 추출
추정, 셀 주소 `KeyIndicator` 로 확정할 것). 되먹임(천안 삼성리 자기 생성)이 첫 검증이다.
"""
from hwp_util import MISSING, blank_row, fit_rows, write_at


def _c(x):
    return None if x in (None, "") else f"{x:,}" if isinstance(x, (int, float)) else str(x)


def build_slots(v):
    sa, sul = v.get("사업", {}), v.get("서술", {})
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s = {
        "사업명": g(sa, "사업명"), "위치": g(sa, "위치"), "주소_일원": g(sa, "주소_일원"),
        "용도지역": g(sa, "용도지역"), "사업유형": g(sa, "사업유형"),
        "면적": (f"{sa['면적_㎡']:,}" if sa.get("면적_㎡") else MISSING),
        "시행자": g(sa, "시행자"), "사업기간": g(sa, "사업기간"),
        "승인기관": g(sa, "승인기관"), "협의권자": g(sa, "협의권자"),
        "사업서술": g(sa, "사업서술"), "협의대상항목": g(sa, "협의대상항목"),
        "사업목적_서술": g(sul, "목적"), "협의사유_서술": g(sul, "협의사유"),
    }
    경위, 향후 = v.get("경위") or [], v.get("향후") or []
    for i in range(3):
        s[f"경위{i+1}"] = 경위[i] if i < len(경위) else MISSING
    for i in range(5):
        s[f"향후{i+1}"] = 향후[i] if i < len(향후) else MISSING
    return s


def build_tables(hwp, v):
    """신청면적 조서 + 토지이용 3표. ⚠️ 앵커 추정 — Windows 실측으로 확정."""
    tj = v.get("토지이용", {})

    # ── 신청면적 조서 — 소환 0100 조서와 동일 부류 (행 수 가변, 합계는 계산 필드 대체)
    #    앵커 "신청면적(㎡)"(머리행 라벨). 위치 열(시군/읍면리)은 세로 병합 라벨 ⚠️.
    조서 = v.get("조서") or []
    if 조서:
        fit_rows(hwp, "신청면적(㎡)", 5, len(조서))          # 베이스 데이터 행 5 (천안 실측)
        for i, row in enumerate(조서):                       # [지번, 지목, 지적, 신청면적, 비고]
            write_at(hwp, "신청면적(㎡)", i + 1, 2,
                     [row[0], row[1], _c(row[2]), _c(row[3]), row[4] or ""])
        합계 = [sum(r[2] for r in 조서), sum(r[3] for r in 조서)]
        write_at(hwp, "합                      계", 0, 3, [_c(합계[0]), _c(합계[1])],
                 from_anchor=True)                           # 합계 행 (계산 필드 자리) ⚠️
    else:
        for i in range(1, 6):
            blank_row(hwp, "신청면적(㎡)", i, keep_first=0)   # 지번까지 사업 고유 — 전부 비움

    # ── 토지이용 총괄 (투수/불투수 2행 × 현황·계획 면적/구성비 4값)
    총괄 = tj.get("총괄") or {}
    for i, key in ((1, "투수"), (2, "불투수")):
        r = 총괄.get(key) or [None] * 4
        write_at(hwp, "토지이용계획", i, 1, [_c(x) for x in r])   # 앵커=머리행 '토지이용계획' ⚠️skip 확인

    # ── 토지이용현황 / 토지이용계획 표 (지목·용도별 n행 — 라벨까지 사업 고유)
    for 앵커, rows, base in (("토지이용현황", tj.get("현황"), 2), ("토지이용계획", tj.get("계획"), 5)):
        # ⚠️ 같은 문자열이 총괄 표 머리에도 있다 — skip 실측 필수 (find_in_table 충돌 부류)
        if rows:
            fit_rows(hwp, 앵커, base, len(rows))
            for i, row in enumerate(rows):
                write_at(hwp, 앵커, i + 1, 0, [row[0], _c(row[1]), _c(row[2]),
                                               (row[3] if len(row) > 3 else "") or ""], skip=1)
        else:
            for i in range(1, base + 1):
                blank_row(hwp, 앵커, i, keep_first=0, skip=1)

    print("  1장 — 조서·토지이용 4표 처리 ⚠️ 앵커 실측 전 (되먹임으로 확정)")

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


def _sum(xs):
    """면적 합계. ⚠️ 정수로 떨어지면 정수로 — `3133.0` 이 `3,133.0` 으로 찍힌다."""
    t = sum(x or 0 for x in xs)
    return int(t) if float(t).is_integer() else round(t, 1)


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
        # ⚠️ **col_off=1** — 실측: 앵커 `신청면적(㎡)`=E1(머리행) · A=위치(세로 병합) ·
        #    B=지번 · C=지목 · D=지적 · E=신청면적 · F=비고. 2 로 두면 지번이 지목 칸에
        #    들어가 한 칸씩 밀린다.
        # 🚨 A열(위치)은 **세로 병합 한 칸**이라 값 열만 쓰면 기준 사업이 남는다 —
        #    베이스에 `천안시 동남구/목천읍 삼성리` 가 그대로 있다 (소환 0100 과 같은 자리).
        write_at(hwp, "신청면적(㎡)", 1, 0, [(v.get("사업") or {}).get("조서_위치")])
        for i, row in enumerate(조서):                       # [지번, 지목, 지적, 신청면적, 비고]
            write_at(hwp, "신청면적(㎡)", i + 1, 1,
                     [row[0], row[1], _c(row[2]), _c(row[3]), row[4] or ""])
        합계 = [sum(r[2] for r in 조서), sum(r[3] for r in 조서)]
        # ⚠️ 합계 칸은 **A:C 3칸 병합** — `from_anchor` 에서 오른쪽 한 번이면 벌써 D열이다.
        #    3 을 주면 F열(비고)까지 넘어가고, 마지막 칸이라 되돌아가지 못해 **덮어쓴다**
        #    (되먹임에서 비고에 `3,133` 이 찍혔다). 실측: A7[1x3]=합계 · D7=지적 · E7=신청면적.
        write_at(hwp, "합                      계", 0, 1, [_c(합계[0]), _c(합계[1])],
                 from_anchor=True)                           # 합계 행 (계산 필드 자리) ⚠️
    else:
        for i in range(1, 6):
            blank_row(hwp, "신청면적(㎡)", i, keep_first=0)   # 지번까지 사업 고유 — 전부 비움

    # ── 토지이용 3표 — 앵커 실측 확정 (2026-09-01 KeyIndicator)
    #    `토지이용현황`=B1 · `토지이용계획`=D1 은 **총괄 표 머리행에만** 있다(각 1회).
    #    개별 현황·계획 표는 머리가 `구 분` 이고, 그 문자열은 표 5곳에 있다:
    #      skip0=총괄 · skip1=토지이용현황 · skip2=토지이용계획 · skip3=협의대상 · skip4=사업개요
    #    → 개별 표는 `구 분` + skip 으로 잡는다. 앞선 코드가 `토지이용현황/계획` 을 개별 표
    #      앵커로 써서 **7건 전부 '못 찾음'** 이었다 (되먹임 실측).
    총괄 = tj.get("총괄") or {}
    # 총괄 데이터: +1 계 · +2 투수지역 · +3 불투수지역 (실측)
    for off, key in ((2, "투수"), (3, "불투수")):
        r = 총괄.get(key) or [None] * 4
        write_at(hwp, "구 분", off, 1, [_c(x) for x in r], skip=0)

    # ⚠️ **두 표의 열 기준이 다르다** (XML 셀 주소 실측):
    #    현황 = `A1[1x2]='구 분'` 병합 머리 → 데이터 행에 **빈 A열 여백**이 있어 지목이 B열.
    #    계획 = 병합 없음 → 지목이 A열.
    #    현황을 col 0 으로 쓰면 한 칸씩 왼쪽으로 밀려 **구성비 칸의 기준 사업 값이 살아남는다**
    #    (되먹임에서 `98.37`·`1.63` 이 한 번 더 나왔다). 합계 행은 둘 다 `계` 가 병합/단독
    #    첫 칸이라 col 1 로 같다.
    for sk, rows, base, dcol in ((1, tj.get("현황"), 2, 1),
                                 (2, tj.get("계획"), 5, 0)):
        # ⚠️ **데이터는 +2행부터다** — `+1` 은 `계`(합계) 행이다 (실측). +1 로 시작하면
        #    합계 행이 첫 지목으로 덮이고 뒤가 한 행씩 밀린다 (되먹임에서 `계 3,133 100.00`
        #    이 사라지고 값이 어긋났다).
        if rows:
            fit_rows(hwp, "구 분", base, len(rows), start=2, skip=sk)
            for i, row in enumerate(rows):
                write_at(hwp, "구 분", i + 2, dcol,
                         [row[0], _c(row[1]), _c(row[2]),
                          (row[3] if len(row) > 3 else "") or ""], skip=sk)
            # 합계 행 — 안 쓰면 기준 사업 값이 남는다 (다른 사업에서 유출)
            write_at(hwp, "구 분", 1, 1,
                     [_c(_sum(x[1] for x in rows)), "100.00", ""], skip=sk)
        else:
            for i in range(1, base + 2):          # 계 행 포함
                blank_row(hwp, "구 분", i, keep_first=0, skip=sk)

    print("  1장 — 조서·토지이용 4표 처리 (앵커 실측 확정 2026-09-01)")

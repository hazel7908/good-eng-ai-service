#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토서 1장 계획의 개요 핸들러 — C 베이스 (2026-09-03 Mac). 지식: rules/disaster-review/project-overview.md.

표: 결정 조서 블록(~15표) **비움**(행정계획 문서 인풋) · 지목별/소유별 토지이용현황(전치 표 — 행 라벨 앵커) 채움 ·
토지이용계획(안) 비움(골든이 남의 값). 앵커·오프셋은 Windows 실측 전 추정.
"""
from hwp_util import (blank_row, blank_tables, blank_value_cells, fit_cols, MISSING, write_at)


def _n(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def compute(v):
    """지목별·소유별 표: 필지수 합·면적 합·구성비 (계산 필드 자리)."""
    r = {}
    for key in ("지목별", "소유별"):
        rows = (v.get("토지이용") or {}).get(key) or []       # [[구분, 필지수, 면적], ...]
        np_, na = sum(int(_n(x[1]) or 0) for x in rows), sum(_n(x[2]) or 0 for x in rows)
        # 면적 소수 보존 — 옥계리 체육용지 667,850.2 가 정수 절사로 훼손되던 것 정정 (09-09)
        fmt = lambda x: f"{x:,.1f}".rstrip("0").rstrip(".") if x is not None else None
        r[key] = {"필지": [str(np_)] + [x[1] for x in rows], "면적": [fmt(na)] + [fmt(_n(x[2])) for x in rows],
                  # 구성비 소수 1자리 — 골든 표기 실측(임 94.2 = 60,469/64,223). .2f 는 규약 위반이었다(09-09 Windows 적발 94.15↔94.2)
                  "구성비": ["100.0"] + [f"{_n(x[2]) / na * 100:.1f}" if na and _n(x[2]) is not None else None for x in rows]}
    return r


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    s, n = v.get("계획", {}), v.get("서술", {})
    out = {k: g(s, k) for k in ("계획명", "위치", "조서_위치1", "조서_위치2", "시행자", "사업기간", "시군", "도시관리계획명")}
    out["국공유_주체"] = g(v.get("토지이용", {}), "국공유_주체")
    # 면적 소수 보존 — 옥계리 1,239,132.2㎡ 가 정수 절사(,.0f)로 훼손되던 것 정정 (09-09)
    n_ = _n(s.get("면적_㎡"))
    out["면적"] = f"{n_:,.1f}".rstrip("0").rstrip(".") if n_ is not None else MISSING
    out.update({k: g(n, k) for k in ("배경_서술", "목적_서술", "실시근거_서술")})
    gw = v.get("경위") or []
    out.update({f"경위_{i}": (gw[i - 1] if i <= len(gw) else MISSING) for i in range(1, 17)})
    lb = v.get("위치도_라벨") or []
    out.update({f"위치도_라벨{i}": (lb[i - 1] if i <= len(lb) else MISSING) for i in range(1, 4)})
    return out


def _blank_all(hwp, anchor, header_rows, limit, skip=0):
    """공용 위임 — skip 인자는 폐기(앵커 생존 자동 판정). 시그니처는 호출부 호환용.

    ⚠️ `max_rows` 기본 24 는 이 장에서 모자란다 — 가구·획지 조서가 16행인데 세로 병합 칸을
    행마다 다시 밟아 예산을 두 배로 쓴다. 09-09 옥계리에서 **13행부터 원주 값이 남았다**.
    """
    k = blank_tables(hwp, anchor, header_rows, limit, max_rows=80)
    print(f"  비움 `{anchor}` ×{k}" if k else f"    WARNING: 앵커 '{anchor}' 못 찾음")
    return k


def build_tables(hwp, v):
    """🚨 **비우기를 먼저, 채우기를 나중에.** 09-09 옥계리에서 순서가 거꾸로라
    `blank_value_cells("면  적(㎡)")` 가 **방금 채운 지목별 표를 도로 지웠다.**
    같은 앵커가 비우는 표와 채우는 표에 함께 걸리면 순서가 결과를 바꾼다.
    """
    r = compute(v)
    W = lambda *a, **k: write_at(hwp, *a, **k)

    # ── 1. 결정 조서 블록 비우기 (행정계획 문서 인풋 — 사업마다 통째로 다르다) ──
    # 🔬 09-09 XML 실측: 조서 표는 **머리행이 1줄인 것과 2줄인 것이 섞여 있다.**
    #    2줄(기정|변경|변경후 · 명칭|면적|명칭|위치|면적): 지구단위계획구역·자동차정류장·
    #      완충녹지·유수지·가구획지·용도지역  → `도면표시`/`구     분` 를 hdr=2 로
    #    1줄(변경내용|변경사유): 구역 사유서·도로 결정(변경)·시설 사유서 3종 → `변경사유` hdr=1
    #    ⚠️ 옛 `("도면표시", 3, 12)` 는 **한 행이 아니라 두 행을 건너뛰어** 조서 9표 중
    #       데이터가 2~3행뿐인 표들을 통째로 놓쳤다(로그는 `비움 ×N` 정상).
    print("  결정 조서 블록 — 머리 2줄(도면표시·구     분) / 머리 1줄(변경사유) 두 갈래로 비움")
    _blank_all(hwp, "도면표시", 2, 12)
    _blank_all(hwp, "변경사유", 1, 6)
    _blank_all(hwp, "구     분", 2, 1)          # 용도지역 결정조서 (문단 `용도지역 결정(대상지)` 는 앵커 불가)
    _blank_all(hwp, "계획내용", 1, 3)            # 건축물 용도·건폐율/용적률·차량출입 계획 3표
    # 도로 결정(변경) 조서는 **중첩표**라 바깥 표 앵커(`변경사유`)로는 안 닿는다. 자기 머리
    # 라벨을 쓴다 — `종점` 은 문서에 단 하나다(등급|류별|번호|폭원 부머리가 있어 hdr=2).
    _blank_all(hwp, "종점", 2, 1)
    _blank_all(hwp, "근생", 1, 1)               # 토지이용계획(안) — `합계` 는 런 분할이라 못 쓴다(⑰)

    # 현장 사진 캡션 — 그림은 빌더가 걷어냈지만 **캡션은 남는다**(`NO.01 남서측` = 원주 촬영 방향).
    # 사진 칸을 건드리면 그림 틀이 깨지므로 **캡션 행만** 비운다. 앵커가 값이라 지우며 소멸 →
    # 못 찾을 때까지 돈다.
    n = 0
    while n < 14 and blank_row(hwp, "NO.0", 0):
        n += 1
    print(f"  현장 사진 캡션 {n}행 비움 (촬영 방향은 사업 고유)")

    # 소유별 토지이용현황 — 머리가 2단(국공유지 소계/{{시군}} · 사유지 소계/확보/미확보)이라
    # vars 의 `[[구분, 필지수, 면적]]` 평면 구조로는 칸을 못 맞춘다. **값만 비우고 계열만 채운다.**
    # ⚠️ 맥에게: 옥계리 국공유는 **기획재정부** 소유인데 머리 칸은 `{{시군}}`(→횡성군)이다 —
    #    토큰 뜻이 "국공유지 소유 지자체"라 사업에 따라 층이 어긋난다.
    rep = ([], [])
    blank_value_cells(hwp, "사유지동의율", hdr=2, limit=1, report=rep)
    print(f"  소유별 토지이용현황 — 값 {len(rep[0])}칸 비움 · 라벨 {len(rep[1])} 유지")

    # ── 2. 채우기 ──
    # 🚨 **전치 표는 열을 맞추지 않으면 값이 다음 행으로 넘쳐 행 라벨을 덮는다.**
    #    원주는 지목 2종(임·전)인데 옥계리는 9종이라, 열을 안 늘리면 `면  적(㎡)`·`구성비(%)`
    #    라벨 자리에 숫자가 박히고 표가 통째로 뒤섞였다 (09-09 실측 — 남의 값이 남는 것보다
    #    나쁜 부류). `fit_cols` 로 칸 수를 맞추고 **머리행(지목명)까지 함께 쓴다.**
    rows = (v.get("토지이용") or {}).get("지목별") or []
    d = r["지목별"]
    print(f"  지목별 토지이용현황 — 지목 {len(rows)}종에 맞춰 열 조정 후 머리행·3행 채움")
    if fit_cols(hwp, "필 지 수", len(rows) + 1):
        W("필 지 수", -1, 1, ["계"] + [x[0] for x in rows], from_anchor=True)
        W("필 지 수", 0, 1, d["필지"], from_anchor=True)
        W("필 지 수", 1, 1, d["면적"], from_anchor=True)
        W("필 지 수", 2, 1, d["구성비"], from_anchor=True)

    # 소유별은 계열 한 칸씩만 확실하다 (분류 층이 인풋과 다르다 — 위 주석)
    s = r["소유별"]
    W("사유지동의율", -3, 1, [s["필지"][0]], from_anchor=True)
    W("사유지동의율", -2, 1, [s["면적"][0]], from_anchor=True)
    W("사유지동의율", -1, 1, [s["구성비"][0]], from_anchor=True)

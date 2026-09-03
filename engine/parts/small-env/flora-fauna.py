#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0711 동·식물상 파트 핸들러 — W3 (2026-09-03 Mac). 틀(C) — 요약 문장·집계 토큰 56 + 전후 식생 표.

규약: build_slots / build_tables. 지식: rules/small-env/flora-fauna.md.
계산: 귀화율 PN = 귀화/현지 관속식물 ×100 · 도시화지수 UI = 귀화/321 ×100 (원주 15.44·7.17 역산 ✓).
⚠️ 종목록 표 6종(≈9,000줄)은 여기서 안 다룬다 — 빌더 단계 과제(rule §6). 그 전까지 표유출검사 ②에
   반드시 걸린다(의도된 실패 — 베이스가 원주 종목록을 그대로 담고 있다는 뜻).
"""
from hwp_util import MISSING, write_at

UI_DENOM = 321          # 남한 귀화식물 총 분류군 (한국식물분류학회지 2011) — 문장에 명시된 상수


def _n(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def 문헌목록(items):
    return ", ".join(f"「{x}」" for x in items) if items else None


def compute(v):
    """귀화율·도시화지수 · 전후 식생 비율 · 요약표 값 (현지 집계와 같은 값)."""
    c, r = v.get("현지", {}), {}
    gw, tot = _n(c.get("귀화_n")), _n(c.get("식물_n"))
    r["귀화율"] = f"{gw / tot * 100:.2f}" if gw and tot else None
    r["도시화지수"] = f"{gw / UI_DENOM * 100:.2f}" if gw else None
    rows = (v.get("전후식생") or {}).get("표") or []
    before = sum(_n(x[2]) or 0 for x in rows)
    after = sum(_n(x[3]) or 0 for x in rows if len(x) > 3)
    r["전후표"] = [[x[0], x[1],
                  x[2], (f"{_n(x[2]) / before * 100:.2f}" if before and _n(x[2]) is not None else ("-" if x[2] in (None, "-") else None)),
                  (x[3] if len(x) > 3 else "-"), (f"{_n(x[3]) / after * 100:.2f}" if len(x) > 3 and after and _n(x[3]) is not None else "-"),
                  "-"] for x in rows]
    r["전_합"], r["후_합"] = (f"{before:,.0f}" if before else None), (f"{after:,.0f}" if after else None)
    return r


def build_slots(v):
    g = lambda d, k: (d.get(k) if d.get(k) not in (None, "") else MISSING)
    r = compute(v)
    s, j, m, c = v.get("조사", {}), v.get("문헌", {}), v.get("문헌", {}).get("결과", {}), v.get("현지", {})
    out = {"사업명": g(v.get("사업", {}), "사업명")}
    out.update({k: g(s, k) for k in ("조사기간", "면적", "도엽명", "도엽번호", "격자", "조사지역_주소", "생태자연도")})
    out["문헌목록"] = 문헌목록(j.get("목록")) or MISSING
    for i, x in enumerate((j.get("주석") or []) + [None] * 6, 1):
        if i <= 6:
            out[f"문헌주석_{i}"] = x or MISSING
    out["문헌표머리_5"], out["문헌표머리_6"] = g(j, "표머리_5"), g(j, "표머리_6")
    out.update({f"문헌결과_{k}": g(m, k) for k in
                ("식물", "포유류", "포유류_보호종", "양서파충류", "조류", "조류_보호종", "곤충", "특정동물")})
    out.update({k: g(c, k) for k in (
        "식물_집계", "식물_과순위", "식물_생활형서술", "고유종", "특산식물", "귀화_집계", "교란종", "교란종명",
        "식생유형_지구", "식생유형_광역", "면적분포_지구", "면적분포_광역", "등급분포_지구", "등급분포_광역",
        "등급구성", "포유류_현지", "양서류_현지", "파충류_현지", "조류_현지", "조류_생활형서술", "조류_목별서술",
        "조류_군집서술", "곤충_현지")})
    out["귀화율"], out["도시화지수"] = r["귀화율"] or MISSING, r["도시화지수"] or MISSING
    yo = c.get("요약", {})
    out.update({f"요약_{k}": g(yo, k) for k in ("식물", "포유류", "양서파충류", "조류", "곤충")})
    out["전후식생_서술"] = g(v.get("전후식생", {}), "서술")
    return out


def build_tables(hwp, v):
    r = compute(v)
    print("  사업 전·후 식생보전등급 변화 표 — 앵커 `해 당 식 생 형`(머리 2줄) · 데이터 7행 고정 · 열 C~G ⚠️ Windows 실측")
    rows = r["전후표"]
    for i in range(7):
        row = rows[i] if i < len(rows) else [None, None, "-", "-", "-", "-", "-"]
        write_at(hwp, "해 당 식 생 형", 2 + i, 2, row[2:])          # 등급·식생형 라벨 2열은 고정
    write_at(hwp, "해 당 식 생 형", 9, 2, [r["전_합"], "100.00", r["후_합"], "100.00", "-"])   # 계산 필드 자리
    print("  요약표(식생보전등급 면적·분류군 종수)는 빈칸 치환 · 종목록 표 6종은 빌더 과제 (rule §6)")


def self_test():
    v = {"현지": {"귀화_n": 23, "식물_n": 149}, "전후식생": {"표": [["Ⅴ(5)", "도로 및 나지", "1,134", "13,934"], ["Ⅴ(4)", "경작지", "8,412"], ["Ⅴ(2)", "이차초원", "4,388"]]}}
    r = compute(v)
    want = {"귀화율": "15.44", "도시화지수": "7.17"}
    ok = all(r[k] == w for k, w in want.items()) and [x[3] for x in r["전후표"]] == ["8.14", "60.37", "31.49"] and r["전후표"][0][5] == "100.00"
    print("self-test", "✓" if ok else f"✗ {r}")
    return ok


if __name__ == "__main__":
    self_test()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기상 자료 소싱 — 기상연보 값을 ASOS 일자료에서 만든다 (climate rule §2).

기상 파트(0721)는 **전부 기상연보 소싱**이라 측정도 판단도 없다. 그동안 vars 를
손으로 채워 왔는데(기준 사업 원주만), 그러면 다른 사업은 영원히 `[확인 필요]` 다.

    python engine/kma.py --self-test                  # 원주 2023 으로 파이프라인 검증
    python engine/kma.py --stn 232 --year 2023        # 천안 월별
    python engine/kma.py --stn 232 --years 2014 2023 --vars cases/.../climate.json

## 출처

공공데이터포털 `기상청_지상(종관, ASOS) 일자료 조회서비스`
(`apis.data.go.kr/1360000/AsosDalyInfoService`). 인증키는 `~/.ecobank.env` 를 그대로
쓴다 — **공공데이터포털은 계정당 인증키가 하나**다 (`ecgy.py` 와 같은 규약).

⚠️ **API 마다 `활용신청`이 따로 필요하다.** 키가 맞아도 신청 안 한 API 는 **403** 이
   온다 (에러 본문도 없다). 생태·경관보전지역은 되는데 ASOS 는 403 이면 키 문제가
   아니라 신청 문제다 — 아래 `KEY_HINT` 를 그대로 안내한다.

## 기상연보 정의 (self_test 로 확인한다)

| 항목 | 만드는 법 |
|---|---|
| 평균기온 | 일평균기온(`avgTa`)의 평균 |
| 평균최고·최저 | 일최고(`maxTa`)·일최저(`minTa`)의 평균 |
| 강수량 | 일강수량(`sumRn`) 합 (결측·무강수는 0) |
| **강수일** | **일강수량 ≥ 0.1mm 인 날 수** ★ 정의가 갈리는 자리 |
| 습도 | 일평균상대습도(`avgRhm`) 평균 |
| 일조 | 일조시간(`sumSsHr`) 합 |
| 풍속 | 일평균풍속(`avgWs`) 평균 |

★ 강수일은 **수질 파트의 `강우일수`와 같은 값이어야 한다** (파트 공유 값 — rule §2).
  원주 2023 = 108 일이 두 파트에서 같은 수다.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
CACHE = ROOT / "raw_data/cache/kma"

KEY_HINT = """
ASOS 일자료 API 가 403 이다 — 인증키는 맞는데 **이 API 를 활용신청하지 않았다.**

  1. https://www.data.go.kr/data/15059093/openapi.do 접속 (로그인)
  2. [활용신청] — 일반 인증키는 보통 **즉시 승인**된다
  3. 승인 뒤 이 명령을 다시 돌린다 (키는 이미 ~/.ecobank.env 에 있다)

같은 계정의 다른 API(생태·경관보전지역)는 정상 동작한다 — 계정·키 문제가 아니다.
"""

# 기상연보 지점 — 필요한 것만 적는다 (환각 금지: 모르는 지점은 넣지 않는다)
STATIONS = {"114": "원주", "232": "천안", "131": "청주", "133": "대전",
            "127": "충주", "216": "태백", "100": "대관령", "121": "영월"}


def _key():
    p = os.path.expanduser("~/.ecobank.env")
    if not os.path.exists(p):
        sys.exit("~/.ecobank.env 가 없습니다 — 공공데이터포털 인증키")
    for line in open(p):
        if line.strip().startswith("ECOBANK_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("~/.ecobank.env 에 ECOBANK_API_KEY 가 없습니다")


def fetch_daily(stn, start, end, use_cache=True):
    """일자료를 받는다. 하루 한 행 — 1년이면 365행이라 `numOfRows` 를 크게 준다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"asos_{stn}_{start}_{end}.json"
    if use_cache and cf.exists():
        return json.loads(cf.read_text(encoding="utf-8"))

    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode(
            {"serviceKey": _key(), "pageNo": page, "numOfRows": 999,
             "dataType": "JSON", "dataCd": "ASOS", "dateCd": "DAY",
             "startDt": start, "endDt": end, "stnIds": stn}, safe="")
        try:
            raw = urllib.request.urlopen(
                urllib.request.Request(BASE + "?" + q,
                                       headers={"User-Agent": "Mozilla/5.0"}),
                timeout=60).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                sys.exit(KEY_HINT)
            raise
        d = json.loads(raw)
        body = d.get("response", {}).get("body", {})
        items = (body.get("items") or {}).get("item") or []
        rows += items
        if page * 999 >= int(body.get("totalCount", 0)):
            break
        page += 1
    cf.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def _f(v):
    """빈 문자열·결측을 None 으로. **0 과 결측을 구분한다** — 무강수일은 0 이다."""
    try:
        return float(v) if str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _avg(xs, nd):
    xs = [x for x in xs if x is not None]
    return f"{sum(xs) / len(xs):.{nd}f}" if xs else None


def _sum(xs, nd, comma=False):
    xs = [x for x in xs if x is not None]
    s = sum(xs)
    return f"{s:,.{nd}f}" if comma else f"{s:.{nd}f}"


def monthly(rows, year):
    """월별 8종. 기상연보 표 순서와 같다 (climate rule §1)."""
    by = defaultdict(list)
    for r in rows:
        d = r.get("tm", "")
        if d.startswith(str(year)):
            by[int(d[5:7])].append(r)
    out = {k: [] for k in ("평균최고", "평균", "평균최저", "강수량", "습도",
                           "일조", "강수일", "풍속")}
    for m in range(1, 13):
        rs = by.get(m, [])
        out["평균최고"].append(_avg([_f(r.get("maxTa")) for r in rs], 2))
        out["평균"].append(_avg([_f(r.get("avgTa")) for r in rs], 2))
        out["평균최저"].append(_avg([_f(r.get("minTa")) for r in rs], 2))
        out["강수량"].append(_sum([_f(r.get("sumRn")) for r in rs], 1))
        out["습도"].append(_avg([_f(r.get("avgRhm")) for r in rs], 2))
        out["일조"].append(_sum([_f(r.get("sumSsHr")) for r in rs], 1))
        # ★ 강수일 = 0.1mm 이상인 날. `sumRn` 이 비면 무강수다
        out["강수일"].append(str(sum(1 for r in rs if (_f(r.get("sumRn")) or 0) >= 0.1)))
        out["풍속"].append(_avg([_f(r.get("avgWs")) for r in rs], 2))
    return out


def yearly(rows, y0, y1):
    out = []
    for y in range(int(y0), int(y1) + 1):
        rs = [r for r in rows if r.get("tm", "").startswith(str(y))]
        if not rs:
            continue
        out.append({
            "연도": str(y),
            "평균": _avg([_f(r.get("avgTa")) for r in rs], 2),
            "최고": _avg([_f(r.get("maxTa")) for r in rs], 2),
            "최저": _avg([_f(r.get("minTa")) for r in rs], 2),
            "강수량": _sum([_f(r.get("sumRn")) for r in rs], 1, comma=True),
            "강수일": str(sum(1 for r in rs if (_f(r.get("sumRn")) or 0) >= 0.1)),
            "습도": _avg([_f(r.get("avgRhm")) for r in rs], 2),
            "풍속": _avg([_f(r.get("avgWs")) for r in rs], 2),
            "일조": _sum([_f(r.get("sumSsHr")) for r in rs], 2, comma=True),
        })
    return out


# ── 자체 검증 ───────────────────────────────────────────────────────────────
# 원주(114) 2023 월별 — `cases/small-env/원주_무장리/vars/climate.json` 의 값이다.
# 기준 사업 vars 라 **정답지가 아니다**(베이스 원본에서 왔다). 파이프라인이 기상연보
# 정의를 제대로 재현하는지 재는 잣대로 쓴다 — distill 4단계의 역산 검증과 같은 방법.
SELF = {
    "강수일": ["7", "0", "2", "10", "8", "11", "18", "14", "12", "6", "11", "9"],
    "강수량": ["28.0", "0.0", "13.8", "39.1", "130.7", "140.0", "463.3", "233.0",
               "158.6", "37.8", "66.7", "80.7"],
    "일조": ["195.6", "189.0", "249.9", "189.9", "239.9", "232.0", "157.7", "152.9",
             "160.7", "201.9", "175.8", "152.3"],
}


def self_test():
    rows = fetch_daily("114", "20230101", "20231231")
    got = monthly(rows, 2023)
    ok = True
    for k, want in SELF.items():
        hit = sum(1 for a, b in zip(got[k], want) if a == b)
        print(f"  {k:5s} {hit}/12 " + ("✅" if hit == 12 else "❌"))
        if hit != 12:
            ok = False
            print(f"    받은 값 {got[k]}")
            print(f"    기대값 {want}")
    print("자체 검증", "통과 ✅ — 기상연보 정의를 재현한다" if ok else "실패 ❌ — 정의를 다시 볼 것")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="ASOS 일자료 → 기상연보 값")
    ap.add_argument("--stn", help=f"지점번호 {STATIONS}")
    ap.add_argument("--year", type=int, help="월별 표를 만들 연도")
    ap.add_argument("--years", nargs=2, metavar=("Y0", "Y1"), help="연도별 표 구간")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", help="결과 JSON 저장 경로")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if not a.stn:
        ap.error("--stn 이 필요하다")

    y0, y1 = (a.years if a.years else (a.year, a.year))
    rows = fetch_daily(a.stn, f"{y0}0101", f"{y1}1231")
    print(f"{STATIONS.get(a.stn, a.stn)}({a.stn}) {y0}~{y1} · 일자료 {len(rows)}행")
    res = {"관측소": {"지점": a.stn, "이름": STATIONS.get(a.stn, "")},
           "기간": [str(y0), str(y1)],
           "연도별": yearly(rows, y0, y1)}
    if a.year:
        res["월별"] = monthly(rows, a.year)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:1200])
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                               encoding="utf-8")
        print(f"→ {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

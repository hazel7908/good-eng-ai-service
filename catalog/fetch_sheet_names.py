#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전국 도엽명 DB 수집 — 공공데이터포털 15067685 (국토지리정보원 수치지도 지도정보).

385,451행(전 축척)을 페이징으로 받아 **1:25,000(도엽번호 6자리)** 만 추려
`catalog/review/sheet_names_25k.json` 에 저장한다: {번호: {"명", "조사연도", "제작연도"}}.
같은 도엽이 판마다 여러 행이면 최신 조사연도를 남긴다.

키: ~/.ecobank.env (공공데이터포털 계정 키 — ⚠️ `/` 가 들어 있어 percent-encode 필수,
    quote(key, safe="") — safe 기본값이 '/' 라 그대로 쓰면 401 이 난다. 09-08 실측).
용도: 0800 문헌목록·0711 문헌조사 자동 조립 (rules/small-env/appendix.md §문헌목록).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "catalog" / "review" / "sheet_names_25k.json"
UDDI = "uddi:95200468-4f15-4f7a-bf5c-c0bea1070572"


def main():
    key = next(ln.split("=", 1)[1].strip()
               for ln in open(os.path.expanduser("~/.ecobank.env")) if "ECOBANK_API_KEY" in ln)
    qk = urllib.parse.quote(key, safe="")
    base = f"https://api.odcloud.kr/api/15067685/v1/{UDDI}?serviceKey={qk}&perPage=5000"
    out = {}
    page, total = 1, None
    while total is None or (page - 1) * 5000 < total:
        for attempt in range(3):
            try:
                d = json.load(urllib.request.urlopen(f"{base}&page={page}", timeout=90))
                break
            except Exception as e:
                print(f"  p{page} 재시도 {attempt+1}: {e}", flush=True)
                time.sleep(5)
        else:
            sys.exit(f"p{page} 3회 실패 — 중단")
        total = d["totalCount"]
        for r in d["data"]:
            no = str(r.get("도엽_번호", "")).strip()
            if len(no) != 6 or not no.isdigit():
                continue
            name = str(r.get("도엽_명", "")).strip()
            yr = r.get("조사_연도")
            old = out.get(no)
            if old is None or (yr or 0) > (old.get("조사연도") or 0):
                out[no] = {"명": name, "조사연도": yr, "제작연도": r.get("제작_연도")}
        if page % 10 == 0:
            print(f"  p{page}/{-(-total // 5000)} — 25k 도엽 {len(out)}", flush=True)
        page += 1
    DST.write_text(json.dumps({"_출처": "공공데이터포털 15067685 (수치지도 지도정보)",
                               "_수집일": time.strftime("%Y-%m-%d"), "도엽": out},
                              ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"완료 — 1:25,000 도엽 {len(out)}종 → {DST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

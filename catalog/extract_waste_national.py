"""2024 전국 폐기물 결과표 → 천안시 값 추출 (성상별 발생량 + 인구)."""
import json, pathlib, openpyxl, sys
sys.path.insert(0, "engine")
from hwp_util import console_utf8
console_utf8()
D = pathlib.Path("raw_data/nas/stats/_national/2024_전국폐기물")
REGION = "천안시"
SPEC = [
    ("생활계", "02_01_*", "2-나-1). (시군구) 생활(가정)폐기물 발생량"),
    ("사업장비배출시설계", "02_01_*", "2-나-2). (시군구) 사업장비(非)배출시설계폐기물"),
    ("사업장배출시설계", "02_02_*", None),
    ("건설", "02_03_*", None),
    ("지정", "02_04_*", None),
]
out = {"자료": "전국 폐기물 발생 및 처리현황", "판": 2024, "시군": REGION,
       "출처": "https://www.recycling-info.or.kr/rrs/stat/envStatDetail.do?nttId=1597",
       "원자료": "2024년 전국 폐기물 발생 및 처리현황 결과표.zip", "값": {}}

def rows_for(ws, region, hdr_max=8):
    heads, res = [], []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        cells = ["" if c is None else str(c).strip() for c in row]
        if i <= hdr_max:
            heads.append(cells); continue
        if len(cells) > 1 and region in cells[1]:
            res.append(cells)
    return heads, res

for name, pat, sheet in SPEC:
    fs = sorted(D.glob(pat))
    if not fs:
        print(f"  ❌ {name}: 파일 없음 {pat}"); continue
    wb = openpyxl.load_workbook(fs[0], read_only=True, data_only=True)
    sheets = [sheet] if sheet else [s for s in wb.sheetnames if "시군구" in s and "발생" in s]
    for s in sheets:
        if s not in wb.sheetnames:
            print(f"  ❌ {name}: 시트 없음 {s}"); continue
        heads, rs = rows_for(wb[s], REGION)
        if not rs:
            print(f"  ⚠️ {name}/{s}: {REGION} 행 없음"); continue
        out["값"].setdefault(name, {})[s] = {"머리": heads[3:7], "행": rs}
        print(f"  ✅ {name:16} {s[:40]:42} {len(rs)}행 · {len(rs[0])}열")

# 인구·세대수
wb = openpyxl.load_workbook(sorted(D.glob("02_01_*"))[0], read_only=True, data_only=True)
heads, rs = rows_for(wb["1-나. (시군구) 생활폐기물관리구역현황"], REGION)
out["값"]["관리구역_인구세대"] = {"머리": heads[3:6], "행": rs}
print(f"  ✅ {'인구·세대':16} {len(rs)}행")
p = pathlib.Path("catalog/data/waste_2024_천안.json")
p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("  →", p, f"{p.stat().st_size/1024:.0f}KB")

#!/usr/bin/env python3
"""
지자체 통계연보(엑셀) → 지역개황(0200) 표 값 추출.

`calc.py`(소음진동) · `calc_air.py`(대기질)와 같은 자리의 파트 모듈이다. 다만 성질이 다르다 —
**계산이 아니라 소싱**이다. 지역개황 값의 대부분은 공식으로 유도되지 않고 통계연보에서 옮겨진다
(rule `small-env/regional-overview.md` §2).

  통계연보 zip/폴더  →  편(xlsx)  →  시트  →  연도 행/지역 행  →  단위 변환  →  표 값

검증: `python engine/stats_extract.py --self-test`
      천안 화덕리 골든셋(§2.2.1 지목별 · §2.5.4 자동차)과 대조한다.

⚠️ 이 모듈은 **엑셀 배포판만** 다룬다. 스캔 PDF 판(평창 등)은 OCR 없이는 값을 꺼낼 수 없다.
   배포 형식별 현황은 `catalog/review/stats_catalog.md` §2.
"""
import argparse, io, re, sys, zipfile
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl 이 필요합니다: .venv/bin/pip install openpyxl")

ROOT = Path(__file__).resolve().parent.parent

# ── 절 → (편 패턴, 시트 패턴) 매핑 ────────────────────────────────────────────
# 통계연보 편 구성은 통계청 표준이라 지자체가 달라도 같다 (소싱실증 §3-1).
# ✅ = 골든셋으로 검증됨 / ⬜ = 매핑만 확인, 파서 미구현
SHEET_MAP = {
    "2.2.1 지목별 토지이용":      ("02.토지", r"토지\s*지목별",          "✅"),
    "2.5.4 자동차":               ("11.교통", r"자동차\s*등록$|1-자동차등록", "✅"),
    "2.2.2 용도지역":             ("10.주택", r"용도지역",               "⬜"),
    "2.5.1 도로":                 ("10.주택", r"^\d+-도로|도\s*로$",      "⬜"),
    "2.5.2 환경오염물질 배출시설": ("13. 환",  r"환경오염물질\s*배출사업장", "⬜"),
    "2.6.3 문화재":               ("14-02",   r"문화재",                 "⬜"),
}

# 지목 이름 — 통계연보 헤더 표기에는 균등분할 공백이 들어간다 (`과 수 원`).
JIMOK = ["합계", "전", "답", "과수원", "목장용지", "임야", "광천지", "대", "공장용지",
         "학교용지", "주차장", "주유소용지", "창고용지", "도로", "철도용지", "제방",
         "하천", "구거", "유지", "양어장", "수도용지", "공원", "체육용지", "유원지",
         "종교용지", "사적지", "묘지", "잡종지"]


def _norm(s):
    """균등분할 공백·개행·괄호주석을 지운 비교용 문자열."""
    if s is None:
        return ""
    return re.sub(r"[\s ]+", "", str(s)).replace("·", "")


class YearBook:
    """통계연보 한 판(版). zip 이든 풀린 폴더든 같게 다룬다."""

    def __init__(self, path):
        self.path = Path(path)
        self._books = {}                      # 편 파일명 → bytes
        if self.path.is_dir():
            for p in sorted(self.path.glob("*.xls*")):
                self._books[p.name] = p.read_bytes()
        elif self.path.suffix.lower() == ".zip":
            z = zipfile.ZipFile(self.path)
            for i in z.infolist():
                if i.is_dir():
                    continue
                # ⚠️ 지자체 배포 zip 은 파일명이 CP949 다. unzip 은 여기서 실패한다.
                try:
                    name = i.filename.encode("cp437").decode("cp949")
                except Exception:
                    name = i.filename
                if name.lower().endswith((".xlsx", ".xls")):
                    self._books[Path(name).name] = z.read(i)
        else:
            self._books[self.path.name] = self.path.read_bytes()
        if not self._books:
            raise ValueError(f"엑셀 편을 찾지 못했습니다: {path}")

    @property
    def volumes(self):
        return sorted(self._books)

    def sheet(self, vol_pat, sheet_pat):
        """편 패턴·시트 패턴으로 워크시트를 찾는다. 이름이 지자체마다 조금씩 다르므로 정규식."""
        for name, blob in self._books.items():
            if not re.search(vol_pat, name):
                continue
            wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
            for sn in wb.sheetnames:
                if re.search(sheet_pat, sn):
                    return wb[sn]
        return None


# ── 표 읽기 공통 ────────────────────────────────────────────────────────────
def _header_row(ws, must_have="합계", limit=12):
    """헤더 행 번호를 찾는다. 통계연보는 제목·단위 줄이 앞에 붙어 행 번호가 판마다 다르다."""
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=limit, values_only=True), 1):
        # 헤더 셀에 영문이 붙어 있는 판이 많다 (`합계Total`) — 앞부분만 본다.
        if any(_norm(c).startswith(must_have) for c in row):
            return i
    return None


def _year_rows(ws, label_col=1, max_row=80):
    """라벨 열에서 `2022` 꼴 연도 행을 모은다 → {연도: 행번호}.

    ⚠️ 엑셀이 연도를 숫자로 들고 있어 `2,018` 처럼 보이는 판도 있다.
    ⚠️ 연도 블록 사이에 **빈 행**이 끼는 판이 있다 — 마지막 행을 놓치기 쉬운 구조이고,
       실제로 정답지가 이 함정에 빠져 있었다 (소싱실증 §4-3)."""
    out = {}
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row, values_only=True), 1):
        v = row[label_col - 1]
        if v is None:
            continue
        m = re.fullmatch(r"(19|20)\d{2}", _norm(v).replace(",", ""))
        if m:
            out[int(m.group(0))] = i
    return out


def _region_row(ws, region, label_col=1, max_row=400):
    """읍면동 블록에서 지역 행을 찾는다. `동    면` 처럼 균등분할 공백이 들어간다."""
    tgt = _norm(region)
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row, values_only=True), 1):
        if _norm(row[label_col - 1]) == tgt:
            return i
    return None


# ── 2.2.1 지목별 토지이용 ───────────────────────────────────────────────────
def land_use(yb, region=None, year=None):
    """지목별 면적을 ㎢ 로 돌려준다.

    region=None 이면 연도 행(시군 전체), region 을 주면 읍면동 블록의 그 행.
    year=None 이면 **가장 최근 연도 행** — 어느 해를 쓸지는 회사 표준 확인 대상
    (`docs/실무자_확인요청.md` F-1)."""
    ws = yb.sheet(*SHEET_MAP["2.2.1 지목별 토지이용"][:2])
    if ws is None:
        raise LookupError("토지 지목별 현황 시트를 찾지 못했습니다")

    hr = _header_row(ws)
    if hr is None:
        raise LookupError("지목 헤더 행을 찾지 못했습니다")
    header = list(ws.iter_rows(min_row=hr, max_row=hr, values_only=True))[0]
    col = {}
    for ci, cell in enumerate(header, 1):
        n = _norm(cell)
        if n in JIMOK and n not in col:          # 블록이 반복되므로 처음 것만
            col[n] = ci

    if region:
        r = _region_row(ws, region)
        if r is None:
            raise LookupError(f"'{region}' 행을 찾지 못했습니다")
        used = f"{region} 행"
    else:
        yrs = _year_rows(ws)
        if not yrs:
            raise LookupError("연도 행을 찾지 못했습니다")
        y = year or max(yrs)
        r = yrs[y]
        used = f"{y}년 행"

    vals = list(ws.iter_rows(min_row=r, max_row=r, values_only=True))[0]
    out = {}
    for k, ci in col.items():
        v = vals[ci - 1]
        if isinstance(v, (int, float)):
            out[k] = round(v / 1_000_000, 2)      # ㎡ → ㎢, 소수 2자리 (실증 §4-1)
    out["_출처행"] = used
    return out


def land_use_ratio(area: dict):
    """구성비(%) — rule §3-1. 면적÷합계×100, 소수 2자리."""
    tot = area.get("합계")
    if not tot:
        return {}
    return {k: round(v / tot * 100, 2) for k, v in area.items()
            if isinstance(v, (int, float))}


# ── 2.5.4 자동차 ────────────────────────────────────────────────────────────
def vehicles(yb, year=None):
    """자동차 등록대수. 보고서 표는 계·승용차·승합차·화물차·특수차·이륜자동차 6칸이다."""
    ws = yb.sheet(*SHEET_MAP["2.5.4 자동차"][:2])
    if ws is None:
        raise LookupError("자동차 등록 시트를 찾지 못했습니다")
    hr = _header_row(ws)
    header = list(ws.iter_rows(min_row=hr, max_row=hr, values_only=True))[0] if hr else ()
    col = {}
    for ci, cell in enumerate(header, 1):
        n = _norm(cell)
        for k in ("합계", "승용차", "승합차", "화물차", "특수차", "이륜자동차"):
            if n.startswith(k) and k not in col:
                col[k] = ci
    yrs = _year_rows(ws)
    y = year or max(yrs)
    vals = list(ws.iter_rows(min_row=yrs[y], max_row=yrs[y], values_only=True))[0]
    out = {k: vals[ci - 1] for k, ci in col.items() if isinstance(vals[ci - 1], (int, float))}
    out["_출처행"] = f"{y}년 행"
    return out


# ── 자체 검증 ───────────────────────────────────────────────────────────────
# 천안 화덕리 골든셋 §2.2.1 · §2.5.4 실측값 (golden/small-env/천안_화덕리/regional-overview.txt)
GOLDEN_CHEONAN = {
    "시군_2021": {"합계": 636.15, "전": 51.88, "답": 92.85, "임야": 309.02,
                  "대": 39.69, "과수원": 15.68},
    "동면":      {"합계": 43.27, "전": 4.57, "답": 6.23, "임야": 26.18,
                  "대": 0.86, "과수원": 0.09},
    "자동차":     {"합계": 351796, "승용차": 294246, "승합차": 10499,
                  "화물차": 45382, "특수차": 1669, "이륜자동차": 22622},
}


def self_test(path=None):
    path = path or ROOT / "raw_data/nas/stats/천안_화덕리/천안_2023"
    if not Path(path).exists():
        print(f"[skip] 통계연보가 없습니다: {path}")
        print("       NAS 에서 내려받으세요 — catalog/review/stats_catalog.md 참조")
        return True
    yb = YearBook(path)
    print(f"편 {len(yb.volumes)}개 — {', '.join(v[:14] for v in yb.volumes[:4])} …\n")

    ok = True
    # 시군 전체 — 정답지는 2021년 행을 썼다 (최신 2022 가 아니다). 실증 §4-3
    got = land_use(yb, year=2021)
    for k, want in GOLDEN_CHEONAN["시군_2021"].items():
        hit = got.get(k)
        flag = "OK " if hit == want else "MISS"
        ok &= hit == want
        print(f"  [{flag}] 천안시 {k:<4} 기대 {want:>8,.2f} / 추출 {hit if hit is None else f'{hit:>8,.2f}'}")

    got = land_use(yb, region="동면")
    for k, want in GOLDEN_CHEONAN["동면"].items():
        hit = got.get(k)
        flag = "OK " if hit == want else "MISS"
        ok &= hit == want
        print(f"  [{flag}] 동면   {k:<4} 기대 {want:>8,.2f} / 추출 {hit if hit is None else f'{hit:>8,.2f}'}")

    got = vehicles(yb, year=2022)
    for k, want in GOLDEN_CHEONAN["자동차"].items():
        hit = got.get(k)
        flag = "OK " if hit == want else "MISS"
        ok &= hit == want
        print(f"  [{flag}] 자동차 {k:<5} 기대 {want:>8,} / 추출 {hit if hit is None else f'{hit:>8,}'}")

    # 구성비 역산 — rule §3-1
    ratio = land_use_ratio(land_use(yb, year=2021))
    for k, want in (("임야", 48.58), ("전", 8.16), ("답", 14.60)):
        hit = ratio.get(k)
        flag = "OK " if hit == want else "MISS"
        ok &= hit == want
        print(f"  [{flag}] 구성비 {k:<4} 기대 {want:>8.2f}% / 계산 {hit:>8.2f}%")

    print("\n" + ("✅ 전 항목 일치" if ok else "❌ 불일치 있음"))
    return ok


def main():
    ap = argparse.ArgumentParser(description="통계연보 → 지역개황 표 값")
    ap.add_argument("path", nargs="?", help="통계연보 zip 또는 폴더")
    ap.add_argument("--region", help="읍면동 이름 (없으면 시군 전체)")
    ap.add_argument("--year", type=int, help="연도 행 (없으면 최신)")
    ap.add_argument("--what", default="land", choices=["land", "vehicle", "sheets"])
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test or not a.path:
        sys.exit(0 if self_test(a.path) else 1)

    yb = YearBook(a.path)
    if a.what == "sheets":
        for k, (vol, sh, mark) in SHEET_MAP.items():
            ws = yb.sheet(vol, sh)
            print(f"  {mark} {k:<26} → {ws.title if ws else '(못 찾음)'}")
    elif a.what == "land":
        area = land_use(yb, a.region, a.year)
        ratio = land_use_ratio(area)
        print(f"[{area.pop('_출처행')}]  단위 ㎢ / %")
        for k, v in area.items():
            print(f"  {k:<8} {v:>10,.2f}  {ratio.get(k, 0):>6.2f}%")
    else:
        for k, v in vehicles(yb, a.year).items():
            print(f"  {k:<8} {v}")


if __name__ == "__main__":
    main()

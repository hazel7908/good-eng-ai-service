#!/usr/bin/env python3
"""
전국 통계 **값 저장소** 빌드 — 원자료에서 값을 떠서 우리 쪽에 남긴다.

**좌표만 갖고 있으면 안 되는 이유가 실측으로 나왔다.**
괴산 금신리 골든셋의 유입하수량 `5,822.3` 은 우리가 확보한 하수도통계 **2021·2022·2023
어느 판에도 없다.** 같은 "2023 하수도통계" 라도 배포본이 여럿이고 값이 다르기 때문이다.
원자료를 가리키기만 하면 **그 보고서가 어느 값을 썼는지 영영 되짚을 수 없다.**

그래서 판마다 **값 + 판 지문(sha256)** 을 남긴다.
`sheet_georef.json` 을 커밋하는 것과 같은 논리다 — **다시 만들 수 없는 값**이라서.

    python catalog/build_stats_values.py                  # 로컬 원자료 전부
    python catalog/build_stats_values.py --list           # 무엇이 있고 무엇이 없나
    python catalog/build_stats_values.py --show 괴산군     # 판을 가로질러 본다
    python catalog/build_stats_values.py --check-new      # 발행처에 새 판이 나왔나

출력이 **둘로 갈린다** — 기준은 *다시 만들 수 있는가* 다 (`CLAUDE.md` 삽도 대목과 같은 규약).

    catalog/data/stats_values.manifest.json   ← **커밋**. 판 지문·출처·좌표·행수
    catalog/data/stats_values/{자료}_{판}.json ← **커밋 안 함**. 값 본체 (NAS 로 공유)

값 본체는 원자료 + 이 코드로 **재생성된다.** 반면 *"그 보고서가 어느 판을 썼나"* 는
원자료가 교체되면 **영영 못 만든다** — 그래서 매니페스트만 남긴다.
자료가 12종으로 늘면 값 본체는 10~20MB 가 되고, 재빌드마다 통째로 바뀐다.
git 히스토리는 되돌릴 수 없으므로 **처음부터 나눈다.**
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
from stats_national import SOURCES, extract_all           # noqa: E402

RAW = ROOT / "raw_data/nas/stats/_national"
OUT = ROOT / "catalog/data/stats_values"
MANIFEST = ROOT / "catalog/data/stats_values.manifest.json"

# 발행처 — 새 판을 어디서 받는지. 목록 URL 은 규칙적이라 신판 감시에도 쓴다.
PUBLISHER = {
    "전국 폐기물 발생 및 처리현황": {
        "기관": "기후에너지환경부·한국환경공단 / 자원순환정보시스템",
        "목록": "https://www.recycling-info.or.kr/rrs/stat/envStatList.do"
                "?bbsId=BBSMSTR_000000000002&s_nttSj=KEC006",
        "상세": "https://www.recycling-info.or.kr/rrs/stat/envStatDetail.do?nttId={id}",
    },
    "전국산업단지현황통계": {
        "기관": "한국산업단지공단 (국가승인통계 399003호)",
        "목록": "https://www.data.go.kr/data/3041272/fileData.do",
        "받기": "POST /tcs/dss/selectFileDataDownload.do → "
                "GET /cmm/cmm/fileDownload.do?atchFileId=..&fileDetailSn=..",
    },
    "산림유전자원보호구역 지정 현황": {
        "기관": "산림청",
        "목록": None,          # ❓ 발행처 경로 미확인 — NAS 창고 사본으로 쓴다
    },
    "상수원보호구역 지정현황": {
        "기관": "기후에너지환경부",
        "목록": None,          # ❓ 발행처 경로 미확인 — NAS 창고 사본으로 쓴다
    },
    "음식물류 폐기물 처리시설 현황": {
        "기관": "기후에너지환경부",
        "목록": None,          # ❓ 발행처 경로 미확인 — NAS 창고 사본으로 쓴다
    },
    "상수도통계": {
        "기관": "환경부(기후에너지환경부) / 국가상수도정보시스템",
        "목록": "https://www.waternow.go.kr/web/board/STAT?pMENUID=9",
        "상세": "https://www.waternow.go.kr/web/board/STAT/{id}/?pMENUID=9",
    },
    "하수도통계": {
        "기관": "환경부(기후에너지환경부) / 하수도정보시스템",
        "목록": "https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/list.do",
        "상세": "https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/{id}/view.do",
    },
}


# 파일명 → 자료. 폐기물은 **결과표 zip 안의 특정 엑셀**이라 파일명이 길다.
NAME_TO_SRC = [
    (r"상수도통계", "상수도통계"),
    (r"하수도통계", "하수도통계"),
    (r"처리업체현황_Ⅰ", "전국 폐기물 발생 및 처리현황"),
    (r"음식물류", "음식물류 폐기물 처리시설 현황"),
    (r"상수원보호구역", "상수원보호구역 지정현황"),
    (r"산업단지현황조사", "전국산업단지현황통계"),
    (r"산림유전자원보호구역", "산림유전자원보호구역 지정 현황"),
]



# ── 신판 감시 ───────────────────────────────────────────────────────────────
# 발행처 목록에서 **최신 판 연도**를 읽는다. 파일은 안 받는다 — 확인만 한다.
#
# ⚠️ **발행처를 아는 자료가 전부가 아니다.** 아래 넷만 확인된 경로가 있고 나머지는
#    `stats_registry.py` 에서 `❓ 미확인` 이다. 확인 못 한 것을 "최신" 이라고 말하면
#    안 되므로 **모른다고 보고**한다 (`common.md` 환각 금지).
def _get(url):
    """⚠️ 하수도정보시스템은 **TLS 협상이 까다롭다** — 기본 어댑터로는 `SSLError` 가 난다.
    보안 수준을 낮춘 컨텍스트를 붙인다 (사내에서 `curl -sk` 를 쓰는 것과 같은 이유)."""
    import ssl
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return type("R", (), {"text": r.read().decode("utf-8", "replace")})()


def _latest_waternow():
    """국가상수도정보시스템 발간자료 — `2024년 기후에너지환경부 통계자료`."""
    h = _get("https://www.waternow.go.kr/web/board/STAT?pMENUID=9").text
    ys = [int(m) for m in re.findall(r"(20\d\d)년\s*[가-힣]*\s*통계\s*자료", h)]
    return max(ys) if ys else None


def _latest_hasudo():
    """하수도정보시스템 자료실 — `2025년 하수도통계`.

    ⚠️ 같은 해에 `작성방법`·`교육자료` 게시물도 올라온다. 제목이 **통계로 끝나는 것**만 센다."""
    h = _get("https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/list.do").text
    ys = [int(m) for m in re.findall(r"(20\d\d)년\s*하수도통계\s*<", h)]
    return max(ys) if ys else None


def _latest_recycling():
    """자원순환정보시스템 — `전국 폐기물 발생 및 처리현황(2024년)`."""
    h = _get("https://www.recycling-info.or.kr/rrs/stat/envStatList.do"
             "?bbsId=BBSMSTR_000000000002&s_nttSj=KEC006").text
    ys = [int(m) for m in re.findall(r"처리현황\((20\d\d)년\)", h)]
    return max(ys) if ys else None


def _latest_kicox():
    """공공데이터포털 전국산업단지현황통계 — 파일명에 `_20250930` 꼴로 박힌다."""
    h = _get("https://www.data.go.kr/data/3041272/fileData.do").text
    ys = [int(m[:4]) for m in re.findall(r"현황통계_(20\d\d)\d{4}", h)]
    return max(ys) if ys else None


WATCH = {
    "상수도통계": _latest_waternow,
    "하수도통계": _latest_hasudo,
    "전국 폐기물 발생 및 처리현황": _latest_recycling,
    "전국산업단지현황통계": _latest_kicox,
}


# ── 자동 취득 ───────────────────────────────────────────────────────────────
# 확인만으로는 부족하다 — **새 판이 있으면 받아 와야** 생성이 최신으로 돈다.
# 아래 넷은 경로를 실측으로 뚫었다 (2026-08-24~25). 나머지는 발행처를 모른다.
def _sess():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    s.verify = False
    return s


def _fetch_waternow(year):
    """국가상수도정보시스템 — 목록에서 그 해 게시물 → 첨부 xlsx."""
    s = _sess()
    h = s.get("https://www.waternow.go.kr/web/board/STAT?pMENUID=9", timeout=60).text
    m = re.search(rf'href="(/web/board/STAT/(\d+)/[^"]*)"[^>]*>\s*{year}년', h)
    if not m:
        return None, f"{year}년 게시물을 목록에서 못 찾았다"
    d = s.get("https://www.waternow.go.kr" + m.group(1), timeout=60).text
    # ⚠️ 파일명이 판마다 다르다 — `2023년 상수도통계.xlsx` ↔ `2024년 상수도통계_공표.xlsx`.
    #    이름을 고정하지 말고 **`.xlsx` 첨부**를 고른다 (개요는 `.hwpx` 다).
    f = None
    for m in re.finditer(r'<a[^>]*href="(/jfile/readDownloadFile\.do[^"]*)"[^>]*>(.{0,120}?)</a>',
                         d, re.S):
        if re.sub(r"<[^>]+>", "", m.group(2)).strip().lower().endswith(".xlsx"):
            f = m
            break
    if not f:
        return None, "첨부 xlsx 를 못 찾았다"
    url = "https://www.waternow.go.kr" + f.group(1).replace("&amp;", "&")
    return s.get(url, timeout=600).content, None


def _fetch_hasudo(year):
    """하수도정보시스템 — 상세가 **POST** 이고 `bbsId` 가 빠지면 '파라미터 변조' 가 난다."""
    import ssl
    import urllib.parse
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor())
    op.addheaders = [("User-Agent", "Mozilla/5.0"),
                     ("Referer", "https://www.hasudoinfo.or.kr/bbs/lay1/WS10000015/list.do")]
    base = "https://www.hasudoinfo.or.kr"
    h = op.open(base + "/bbs/lay1/WS10000015/list.do", timeout=60).read().decode(
        "utf-8", "replace")
    ids = re.findall(rf"getDetail\('(\d+)'\)[^>]*>[^<]*{year}년\s*하수도통계\s*<", h)
    if not ids:
        # 목록은 `onclick` 과 제목이 떨어져 있을 수 있다 — 순서로 짝짓는다
        pairs = list(zip(re.findall(r"getDetail\('(\d+)'\)", h),
                         re.findall(r"getDetail\('\d+'\)[\s\S]{0,300}?>([^<]{4,40})<", h)))
        ids = [i for i, t in pairs if f"{year}년 하수도통계" in t]
    if not ids:
        return None, f"{year}년 하수도통계 게시물을 못 찾았다"
    data = urllib.parse.urlencode({"cntnsSn": ids[0], "pageIndex": 1,
                                   "bbsId": "BBS_000007", "pageUnit": 10,
                                   "searchKeyword": ""}).encode()
    d = op.open(base + f"/bbs/lay1/WS10000015/{ids[0]}/view.do", data=data,
                timeout=60).read().decode("utf-8", "replace")
    f = re.search(r"fileDownload\('([^']+)',\s*'(\d+)'\)", d)
    if not f:
        return None, "첨부를 못 찾았다"
    url = (f"{base}/bbs/fileDownload.do?atcmtFileId={f.group(1)}&fileSn={f.group(2)}")
    return op.open(url, timeout=900).read(), None


def _fetch_recycling(year):
    """자원순환정보시스템 — 다운로드가 **form POST** 다 (GET 이면 '잘못된 접근')."""
    s = _sess()
    lst = ("https://www.recycling-info.or.kr/rrs/stat/envStatList.do"
           "?bbsId=BBSMSTR_000000000002&s_nttSj=KEC006")
    h = s.get(lst, timeout=60).text
    m = re.search(rf"nttId=(\d+)[^>]*>[^<]*처리현황\({year}년\)", h)
    if not m:
        return None, f"{year}년 게시물을 못 찾았다"
    d = s.get("https://www.recycling-info.or.kr/rrs/stat/envStatDetail.do"
              f"?bbsId=BBSMSTR_000000000002&nttId={m.group(1)}&s_nttSj=KEC006",
              timeout=60).text
    fid = re.search(r'name="atchFileId" value="([^"]+)"', d)
    sn = re.search(r"fnDownload\('[^']+','(\d+)'\)[^>]*>[^<]*결과표\.zip", d)
    if not (fid and sn):
        return None, "결과표 zip 을 못 찾았다"
    r = s.post("https://www.recycling-info.or.kr/cmm/fms/FileDownload.do",
               data={"bbsId": "BBSMSTR_000000000002", "nttId": m.group(1),
                     "s_nttSj": "KEC006", "atchFileId": fid.group(1),
                     "fileSn": sn.group(1)},
               headers={"Referer": lst}, timeout=900)
    return r.content, None


def _fetch_kicox(_year=None):
    """공공데이터포털 — 3단계. ⚠️ 응답의 `dataSetFileDetailInfo.atchFileId` 는 `None` 이다,
    쓸 값은 **최상위** `atchFileId` 다."""
    s = _sess()
    page = "https://www.data.go.kr/data/3041272/fileData.do"
    h = s.get(page, timeout=60).text
    pk = re.search(r"fn_fileDataDown\('(\d+)',\s*'(uddi:[0-9a-f-]+)'", h)
    if not pk:
        return None, "publicDataDetailPk 를 못 찾았다"
    j = s.post("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do",
               data={"publicDataPk": pk.group(1), "publicDataDetailPk": pk.group(2),
                     "atchFileId": "", "fileDetailSn": "1",
                     "publicDataTyCode": "PR0051"},
               headers={"Referer": page, "X-Requested-With": "XMLHttpRequest"},
               timeout=60).json()
    fid, sn = j.get("atchFileId"), j.get("fileDetailSn")
    if not fid:
        return None, "atchFileId 가 비어 있다"
    r = s.get("https://www.data.go.kr/cmm/cmm/fileDownload.do",
              params={"atchFileId": fid, "fileDetailSn": sn},
              headers={"Referer": page}, timeout=900)
    return r.content, None


FETCH = {
    "상수도통계": (_fetch_waternow, "{y}년 상수도통계_공표.xlsx"),
    "하수도통계": (_fetch_hasudo, "{y} 하수도통계.xlsx"),
    "전국 폐기물 발생 및 처리현황": (_fetch_recycling, "폐기물{y}.zip"),
    "전국산업단지현황통계": (_fetch_kicox, "산업단지현황조사_{y}.xlsx"),
}


def download_latest(src, year):
    """새 판을 받아 `raw_data/` 에 놓는다. 반환 (경로, 오류)."""
    fn, pat = FETCH.get(src, (None, None))
    if not fn:
        return None, "취득 경로를 모른다"
    try:
        blob, err = fn(year)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if err or not blob or len(blob) < 10000:
        return None, err or "받은 것이 너무 작다 (오류 페이지일 수 있다)"
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / pat.format(y=year)
    out.write_bytes(blob)
    if out.suffix == ".zip":                      # 폐기물은 결과표 zip 안의 엑셀을 쓴다
        import zipfile
        d = RAW / f"폐기물{year}"
        d.mkdir(exist_ok=True)
        with zipfile.ZipFile(out) as z:
            for n in z.namelist():
                try:
                    nm = n.encode("cp437").decode("cp949")
                except Exception:
                    nm = n
                if "처리업체현황_Ⅰ" in nm:
                    (d / nm).write_bytes(z.read(n))
        out.unlink()
        out = d
    return out, None


def rebuild_one(path):
    """받은 원자료 한 벌만 값 저장소에 반영한다 (전체 재빌드는 비싸다)."""
    paths = sorted(path.glob("*.xlsx")) if path.is_dir() else [path]
    for p in paths:
        ed = edition_of(p)
        if not ed:
            continue
        src, yr = ed
        doc = build(p, src, yr)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{src}_{yr}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def check_new():
    """보유 판 ↔ 발행처 최신 판. **파일은 받지 않는다.**"""
    man = (json.loads(MANIFEST.read_text(encoding="utf-8"))
           if MANIFEST.exists() else {"판": []})
    have = {}
    for e in man["판"]:
        have[e["자료"]] = max(have.get(e["자료"], 0), e["판"])

    print("# 신판 감시 — 보유 ↔ 발행처\n")
    print("| 자료 | 보유 | 발행처 최신 | |")
    print("|---|:--:|:--:|:--:|")
    todo, unknown = [], []
    for src, yr in sorted(have.items()):
        fn = WATCH.get(src)
        if not fn:
            print(f"| {src} | {yr} | ❓ | **발행처 미확인** |")
            unknown.append(src)
            continue
        try:
            latest = fn()
        except Exception as e:
            print(f"| {src} | {yr} | ⚠️ | 조회 실패 ({type(e).__name__}) |")
            continue
        if latest is None:
            print(f"| {src} | {yr} | ⚠️ | 목록에서 연도를 못 읽었다 |")
        elif latest > yr:
            print(f"| {src} | {yr} | **{latest}** | 🔴 **새 판** |")
            todo.append((src, latest))
        else:
            print(f"| {src} | {yr} | {latest} | ✅ 최신 |")

    print(f"\n감시 {len(have) - len(unknown)} / 보유 {len(have)}종")
    if unknown:
        print(f"⚠️ **발행처 미확인 {len(unknown)}종** — 확인 전까지 '최신' 이라 말할 수 없다: "
              + " · ".join(unknown))
    print("\n🔴 받아야 할 것: " + (" · ".join(f"{s} {y}판" for s, y in todo)
                                  if todo else "없음"))
    return todo


def edition_of(path):
    """파일명에서 (자료, 판) 을 읽는다. 판은 **기준연도**다 (공표연도가 아니다)."""
    name = path.name
    m = re.search(r"(20\d\d)", name)
    if not m:
        m2 = re.search(r"[\'\(](\d{2})[\.\-]\d{1,2}월", name)
        if not m2:
            return None
        m = m2
        m = type("M", (), {"group": lambda self, i: str(2000 + int(m2.group(1)))})()
    for pat, src in NAME_TO_SRC:
        if re.search(pat, name.replace(" ", "")):
            return src, int(m.group(1))
    return None


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while (b := f.read(chunk)):
            h.update(b)
    return h.hexdigest()


def build(path, src, year):
    secs = {s: spec for s, spec in SOURCES.items() if spec["자료"] == src}
    doc = {
        "자료": src,
        "판": year,
        "발행처": PUBLISHER.get(src, {}),
        "원자료": {
            "파일명": path.name,
            "크기": path.stat().st_size,
            # ⚠️ 판 지문 — 같은 연도라도 배포본이 갈린다. 이것이 판을 가르는 유일한 근거다
            "sha256": sha256(path),
        },
        "추출": {"일자": date.today().isoformat(), "도구": "engine/stats_national.py"},
        "절": {},
    }
    for sec in secs:
        try:
            values, sheet, missing = extract_all(path, sec)
        except KeyError as e:
            doc["절"][sec] = {"오류": str(e)}
            print(f"    ⚠️ {sec}: {e}")
            continue
        doc["절"][sec] = {
            "시트": sheet,
            "원자료에_없는_열": missing,
            "시군수": len(values),
            "행수": sum(len(v) for v in values.values()),
            "값": dict(sorted(values.items())),
        }
        print(f"    {sec}: 시군 {len(values)} · 행 {sum(len(v) for v in values.values())}"
              + (f"  ⚠️ 없는 열 {missing}" if missing else ""))
    return doc


def show(gun):
    """한 시군을 **판마다 나란히** 펼친다.

    값 저장소를 두는 이유가 여기 있다 — 원자료 8벌(90MB)을 열지 않고
    *"어느 판에서 값이 어떻게 바뀌었나"* 를 바로 본다.
    """
    docs = sorted((json.loads(f.read_text(encoding="utf-8")) for f in OUT.glob("*.json")),
                  key=lambda d: (d["자료"], d["판"]))
    if not docs:
        print("값 저장소가 비었다 — 먼저 인자 없이 실행할 것"); return 1
    for sec in SOURCES:
        lines = []
        for d in docs:
            blk = d["절"].get(sec)
            if not blk or "값" not in blk:
                continue
            for row in blk["값"].get(gun, []):
                vals = " | ".join(f"{v:,}" if isinstance(v, (int, float)) else str(v)
                                  for v in row.values())
                lines.append(f"  {d['판']}판  {vals}")
        if lines:
            print(f"\n## {sec} — {gun}")
            print("        " + " | ".join(SOURCES[sec]["열"]))
            print("\n".join(lines))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="원자료 보유 현황만 본다")
    ap.add_argument("--show", metavar="시군", help="한 시군을 판마다 나란히 본다")
    ap.add_argument("--check-new", action="store_true", help="발행처에 새 판이 나왔나")
    a = ap.parse_args()

    if a.check_new:
        check_new()
        return 0
    if a.show:
        return show(a.show)

    found = {}
    for p in sorted(list(RAW.glob("*.xlsx")) + list(RAW.glob("*/*.xlsx"))):
        ed = edition_of(p)
        if ed:
            found[ed] = p

    if a.list:
        print("## 로컬 원자료 (raw_data, 커밋 제외)")
        for (src, yr), p in sorted(found.items()):
            print(f"  {src} {yr}판  {p.name}  {p.stat().st_size/1e6:.1f}MB")
        print("\n## 값 저장소 (커밋 대상)")
        for f in sorted(OUT.glob("*.json")) if OUT.exists() else []:
            print(f"  {f.name}  {f.stat().st_size/1024:.0f}KB")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "설명": "전국 통계 값 저장소의 판 목록. 값 본체는 커밋하지 않는다 — "
                "`python catalog/build_stats_values.py` 로 재생성하거나 NAS 에서 받는다.",
        "갱신": date.today().isoformat(),
        "판": [],
    }
    for (src, yr), p in sorted(found.items()):
        print(f"\n== {src} {yr}판 — {p.name}")
        doc = build(p, src, yr)
        out = OUT / f"{src}_{yr}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"    → {out.relative_to(ROOT)}  {out.stat().st_size/1024:.0f}KB")
        manifest["판"].append({
            "자료": src, "판": yr,
            "발행처": doc["발행처"].get("목록"),
            "원자료": doc["원자료"],                       # 파일명·크기·sha256
            "값파일": {"이름": out.name,
                       "크기": out.stat().st_size,
                       "sha256": sha256(out)},            # NAS 사본이 같은지 대조용
            "절": {sec: {k: v for k, v in blk.items() if k != "값"}
                   for sec, blk in doc["절"].items()},
            "추출일": doc["추출"]["일자"],
        })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {MANIFEST.relative_to(ROOT)}  {MANIFEST.stat().st_size/1024:.0f}KB  (커밋 대상)")
    print(f"  값 본체 {len(manifest['판'])}개는 커밋하지 않는다 — NAS 로 공유")
    return 0


if __name__ == "__main__":
    sys.exit(main())

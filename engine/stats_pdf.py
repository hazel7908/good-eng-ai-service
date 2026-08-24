#!/usr/bin/env python3
"""
PDF 로 배포되는 전국 통계 — **셋 다 텍스트 PDF 다** (스캔 아님, OCR 불필요).

| 자료 | 쪽 | 절 |
|---|--:|---|
| 국립공원기본통계 | 256 | 2.3.3 나. 자연공원 |
| 백두대간보호지역 고시 | 192 | 2.3.3 다. 백두대간 |
| 습지보호지역·람사르 현황 | 4 | 2.3.3 라. 습지 |

⚠️ **세로 병합 셀이 위로 샌다.** `pdftotext -layout` 은 병합된 공원명 칸을 세로 가운데에
놓기 때문에, 그 공원의 **첫 시군이 공원명 줄보다 위에** 찍힌다.

    다도해해상  전라남도  2,276.21  완도군  582.164
                                    진도군  604.369
                                    신안군  528.006
                                    원주시  106.46      ← **치악산 것인데 위에 있다**
    치 악 산  강원특별자치도  176.567  횡성군  69.372

줄 위치로는 가를 수 없다. **시도 합계로 검산해 가른다** — `parcels.py` 가 편입토지조서를
합계로 검산하는 것과 같은 수법이다.

    python engine/stats_pdf.py 자연공원 <pdf> --region 원주시
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

CHECK = "[확인 필요]"
NUM = r"[\d,]+\.?\d*"


def text(pdf, cache=True):
    """pdftotext -layout. 같은 폴더에 `.txt` 로 캐시한다 (256쪽은 몇 초 걸린다)."""
    out = Path(pdf).with_suffix(".layout.txt")
    if cache and out.exists():
        return out.read_text(encoding="utf-8", errors="replace")
    subprocess.run(["pdftotext", "-layout", str(pdf), str(out)], check=True)
    return out.read_text(encoding="utf-8", errors="replace")


def _f(s):
    return float(str(s).replace(",", ""))


def 자연공원(pdf, region):
    """`시·군·구별 면적 현황` 에서 그 시군이 속한 국립공원을 찾는다.

    반환 {공원명, 시도, 시도면적, 시군별:[(시군, 면적)…]} 또는 None.
    """
    body = text(pdf)
    # ⚠️ **목차에도 같은 제목이 있다.** 점선(`······`)이 붙은 쪽은 목차다 — 본문을 고른다.
    hits = [m for m in re.finditer(r"사\.\s*시[·․]군[·․]구별 면적 현황(.{0,20})", body)
            if "·····" not in m.group(1) and "…" not in m.group(1)]
    if not hits:
        return None
    m = hits[-1]
    seg = body[m.end():]
    end = re.search(r"\n\s*[가-힣]\.\s", seg)
    seg = seg[:end.start()] if end else seg[:40000]

    # ⚠️ 시도 이름은 `only` 로 새기 쉽다 (`서울특별시  37.517`) — 먼저 걸러 낸다
    SIDO = re.compile(r"(특별시|광역시|특별자치시|특별자치도|남도|북도|^경기도$|^강원도$|^제주도$)")

    # 줄이 **네 갈래**다 — 공원명·시도 칸이 세로 병합이라 줄마다 빠지는 게 다르다
    #   ① 공원명 + 시도 + 시도면적 + 시군 + 면적
    #   ② 공원명 +               시군 + 면적      ← `지 리 산   산청군 113.924`
    #   ③        시도 + 시도면적 + 시군 + 면적    ← 공원이 여러 시도에 걸칠 때
    #   ④                        시군 + 면적
    # ② 를 빠뜨리면 그 줄의 시군이 **통째로 사라져** 합계가 영영 안 맞는다
    head = re.compile(rf"^\s*([가-힣][가-힣\s]*?)\s{{2,}}([가-힣]+(?:특별자치도|특별시|광역시|도))"
                      rf"\s+({NUM})\s+(\S+?[시군구])\s+({NUM})\s*$")
    park_only = re.compile(rf"^\s*([가-힣][가-힣\s]*?)\s{{2,}}(\S+?[시군구])\s+({NUM})\s*$")
    cont = re.compile(rf"^\s*([가-힣]+(?:특별자치도|특별시|광역시|도))\s+({NUM})"
                      rf"\s+(\S+?[시군구])\s+({NUM})\s*$")
    only = re.compile(rf"^\s*(\S+?[시군구])\s+({NUM})\s*$")

    # 줄 순서를 그대로 살려 **두 목록**을 만든다.
    #   flat   — (시군, 면적) 을 나온 순서대로
    #   blocks — (공원, 시도, 시도면적) 을 나온 순서대로
    # 병합이 위로 새도 **순서 자체는 어긋나지 않는다** — 그래서 순서대로 소비하면 갈린다.
    flat, blocks, park = [], [], None
    for ln, line in enumerate(seg.split("\n")):
        if not line.strip():
            continue
        if (h := head.match(line)):
            park = re.sub(r"\s+", "", h.group(1))
            blocks.append({"공원명": park, "시도": h.group(2),
                           "시도면적": _f(h.group(3)), "시군별": [], "줄": ln})
            flat.append((ln, h.group(4), _f(h.group(5))))
        # ⚠️ `and blocks` 로 막으면 안 된다 — 첫 공원(지리산)은 **시도 줄이 공원명 줄보다 먼저**
        #    나와서, 막으면 그 블록이 통째로 버려지고 뒤 블록이 전부 밀린다
        elif (c := cont.match(line)):
            blocks.append({"공원명": park, "시도": c.group(1),
                           "시도면적": _f(c.group(2)), "시군별": [], "줄": ln})
            flat.append((ln, c.group(3), _f(c.group(4))))
        elif (po := park_only.match(line)) and not SIDO.search(po.group(1)):
            park = re.sub(r"\s+", "", po.group(1))          # ② 공원명 + 시군 + 면적
            flat.append((ln, po.group(2), _f(po.group(3))))
        elif (o := only.match(line)) and not SIDO.search(o.group(1)):
            flat.append((ln, o.group(1), _f(o.group(2))))

    # ⚠️ **공원명이 블록보다 뒤에 나오는 수가 있다** (지리산은 전북·전남 줄이 먼저다).
    #    `None` 인 앞 블록들을 **뒤에서 찾은 이름으로** 채운다.
    for i in range(len(blocks) - 1, -1, -1):
        if blocks[i]["공원명"] is None:
            nxt = next((b["공원명"] for b in blocks[i:] if b["공원명"]), None)
            blocks[i]["공원명"] = nxt or CHECK

    # ⚠️ **합계로 가르되, 블록마다 국소적으로 찾는다.**
    #    앞에서부터 순서대로 소비하면 **한 블록이 어긋난 순간 뒤가 전부 밀린다.**
    #    블록의 줄 위치 둘레에서만 연속 구간을 찾으면 실패가 전파되지 않는다.
    for bi, b in enumerate(blocks):
        lo = blocks[bi - 1]["줄"] + 1 if bi else 0
        hi = blocks[bi + 1]["줄"] if bi + 1 < len(blocks) else 10 ** 9
        # 병합 셀이 위로 새므로 앞 블록 줄까지 조금 넘겨 본다
        cand = [x for x in flat if lo - 6 <= x[0] < hi]
        best = None
        for a in range(len(cand)):
            tot = 0.0
            for z in range(a, len(cand)):
                tot += cand[z][2]
                if abs(tot - b["시도면적"]) < 0.01:
                    best = cand[a:z + 1]
                    break
            if best:
                break
        b["시군별"] = [(g, v) for _, g, v in (best or
                       [x for x in flat if b["줄"] - 6 <= x[0] < hi])]
        b["합계검산"] = "OK" if best else CHECK

    for b in blocks:
        for gun, area in b["시군별"]:
            if gun == region:
                return {"공원명": b["공원명"], "시도": b["시도"],
                        "시도면적(㎢)": b["시도면적"], "시군별": b["시군별"],
                        "합계검산": b["합계검산"], "해당시군면적(㎢)": area}
    return None


def 습지보호지역(pdf, region):
    """`습지보호지역 지정 및 람사르습지 등록 현황` — 4쪽짜리 목록."""
    body = text(pdf)
    key = region.rstrip("시군구")
    out = []
    for line in body.split("\n"):
        if key in line and re.search(NUM, line):
            out.append(re.sub(r"\s{2,}", " | ", line.strip()))
    return out


def 백두대간(pdf, region):
    """`백두대간보호지역 고시` — 시군별 필지 목록. 있으면 그 줄들을 돌려준다."""
    body = text(pdf)
    key = region.rstrip("시군구")
    return [re.sub(r"\s{2,}", " | ", l.strip())
            for l in body.split("\n") if key in l][:20]


NAT = Path("raw_data/nas/stats/_national")

GOLDEN = [
    # ⚠️ **"없음" 만으로는 검증이 안 된다.** 항상 0 을 내는 버그도 통과한다
    #    (생태·경관보전지역에서 8건 중 7건이 "없음" 이라 7/8 을 통과했다).
    #    **있는 시군**으로 증명한다.
    ("자연공원 원주(치악산)", "자연공원", NAT / "2025 국립공원기본통계.pdf", "원주시",
     {"공원명": "치악산", "해당시군면적(㎢)": 106.46, "합계검산": "OK"}),
    ("자연공원 평창(오대산)", "자연공원", NAT / "2025 국립공원기본통계.pdf", "평창군",
     {"공원명": "오대산", "해당시군면적(㎢)": 142.03, "합계검산": "OK"}),
]


def self_test():
    ok = bad = 0
    for label, fn, path, region, expect in GOLDEN:
        if not path.exists():
            print(f"⏭  {label}: 원자료 없음"); continue
        got = globals()[fn](str(path), region)
        print(f"\n== {label}")
        if not got:
            print("   ❌ 값 없음"); bad += 1; continue
        for k, e in expect.items():
            g = got.get(k)
            hit = abs(g - e) < 0.01 if isinstance(e, float) else str(g) == str(e)
            print(f"   {'✅' if hit else '❌'} {k}: {g!r}" + ("" if hit else f" ≠ {e!r}"))
            ok, bad = (ok + 1, bad) if hit else (ok, bad + 1)
    print(f"\n=== 자체검증: {ok} OK · {bad} 불일치 ===")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("절", nargs="?", choices=["자연공원", "습지보호지역", "백두대간"])
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--region")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    r = globals()[a.절](a.pdf, a.region)
    if not r:
        print(f"{a.region}: 해당 없음 (지정현황 없음)"); return 0
    print(r if not isinstance(r, list) else "\n".join(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""표 유출 검사 — 산출물 vs 베이스. **`smoke_check` 가 못 잡는 자리**를 잡는다.

증거 인계: docs/20260901_표유출검사_증거인계.md (Windows → Mac). 0100·0500·0726 이
게이트 "통과"인데 기준 사업(원주) 값·지명·캡션이 실려 나갔다 — leak_check 는 서술
문장만 보기 때문이다. 어려운 것은 탐지가 아니라 **오탐 제어**다 (같은 문서 §3).

두 갈래 (§4 제안 그대로):
  ① 지명 유출  — 기준 사업의 시군·읍면·리·하천·시설명이 산출물에 남았는가.
               + **뒤섞인 값**: 기준 사업 상위 행정구역(강원)과 새 시군이 한 줄에
               동시 출현 (`강원도 천안시 가현동 156` — 값 비교로는 못 잡는 최악 유형).
  ② 표 동일   — 산출물 표의 숫자 시퀀스가 베이스와 **완전히 같다** (지정폐 `11|3|1|7`
               처럼 작은 수 유출은 값 목록 대조가 놓친다 — 표 단위 동일성만 잡는다).
               법령·참조표는 같아야 정상이라 FAIL 이 아니라 **사람 훑기 목록**으로 낸다.

⚠️ **되먹임(기준 사업 자기 생성)에는 무의미하다** — 전부 "유출"이라 거부한다 (§4 ⚠️).
⚠️ 검사는 수정과 다른 근거를 쓴다 (hwpx.md 🚨) — 핸들러의 앵커·spec 을 일절 참조하지
   않고 **문서 바이트에서 직접** 읽는다.

    python engine/table_leak.py small-env resource-cycle 천안_화덕리
    python engine/table_leak.py small-env env-status 천안_화덕리 --detail
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hwp_util import console_utf8   # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import score_regional as S  # noqa: E402  — 표 파서 한 벌 (score_part 와 같은 규약)

ROOT = S.ROOT
NUM = re.compile(r"\d[\d,]*\.?\d*")

# ── 카테고리별 기준 사업 지명·시설명 (2026-09-01 분리 — 재해 베이스는 원주가 아니다)
# ⚠️ 같은 카테고리라도 베이스가 갈리는 파트가 생기면 (소환 대기질=청주) 파트별로 또 가른다.
CATEGORY_BASE = {
    "small-env": {          # 기준: 원주 무장리 — 증거 문서 §1 실측 + 골든 지명
        "기준사업": "원주_무장리",
        "시군": "원주시",
        "이름들": {"원주시", "호저면", "무장리", "호저로", "생담길", "태장동", "가현동",
                 "흥업면", "사제리", "지정면", "가곡리", "문막", "섬강", "귀둔천",
                 "원주기업도시", "원주분뇨처리장", "원주공공하수처리장", "강원바이오에너지",
                 "원주기상", "원주(114)"},
        "상위": ("강원특별자치도", "강원도"),
    },
    "small-disaster": {     # 기준: 천안 삼성리 서식 세트 (_variants §0-1)
        "기준사업": "천안_삼성리",
        "시군": "천안시",
        "이름들": {"천안시", "목천읍", "삼성리", "동남구", "맹곡천", "이상용"},
        "상위": ("충청남도", "충남"),
    },
    "disaster-impact": {    # 기준: 천안 삼성리 — 재평 베이스는 소재평 베이스 파생 (rules/disaster-impact/_category §3)
        "기준사업": "천안_삼성리",
        "시군": "천안시",
        "이름들": {"천안시", "목천읍", "삼성리", "동남구", "맹곡천", "이상용"},
        "상위": ("충청남도", "충남"),
    },
    "env-impact": {         # 기준: 횡성 벨라스톤CC 골프장 (⑭ 수확 — rules/env-impact/_category)
        "기준사업": "횡성_벨라스톤CC",
        "시군": "횡성군",
        "이름들": {"횡성군", "서원면", "옥계리", "벨라스톤", "이리천", "섬강"},
        "상위": ("강원특별자치도", "강원도"),
    },
    "disaster-review": {    # 기준: 원주 태장동 (실사업 최종본 — rules/disaster-review)
        "기준사업": "원주_태장동",
        "시군": "원주시",
        "이름들": {"원주시", "태장동", "가현동"},
        "상위": ("강원특별자치도", "강원도"),
    },
    # disaster-impact: 베이스 미정 (소재평 파생 예정) — 정해지면 등록. 미등록 카테고리는
    # 검사를 건너뛰며 그 사실을 출력한다 (조용한 무의미 검사 방지).
}

# 오탐 예외 (§3) — 줄에 이 패턴이 있으면 '유출'이 아니라 '문맥 확인'으로 낮춘다.
CONTEXT_OK = [
    re.compile(r"춘천시.*강릉시|강릉시.*춘천시"),      # 저황유 별표10의2 법령 지역 목록
    re.compile(r"동쪽|서쪽|남쪽|북쪽|인접|접하|경계"),   # 접경 설명 (지형지질 0725 실측)
]

# 부분문자열 덫 (§3) — 기준 지명이 **다른 낱말 안**에 들어가 걸리는 자리.
# 지명 뒤에 이 글자가 붙으면 그 지명 히트는 버린다. 줄 전체를 낮추는 CONTEXT_OK 와 달리
# **그 히트만** 떨어뜨리므로 같은 줄의 진짜 유출은 살아남는다.
#   실측: `지정면적(천㎡)` ⊃ `지정면` (지역개황 산업단지 표, 2026-09-01 Windows).
SUBSTRING_TRAP = {
    "지정면": "적",       # 지정면적
    "문막": "장",         # (문막장… 방어용, 미관측)
}

# 표 동일이 **정상**인 캡션 (법령·참조표·수식 상수표 — 실측한 것만, 늘려 간다)
ALLOW_IDENTICAL = [
    "환경기준", "규제기준", "배출허용기준", "기초유출계수", "토사유출량 원단위",
    "침전속도", "지역별 보정", "소음도", "원단위", "법칙", "산정식",
    "실시근거",                       # 0100 — 시행령 별표 면적 기준 (법령 인용표)
    "행정사항",                       # 재해 7장 — 자연재해대책법 조문·서식 인용표
                                     #   (숫자열 `6 4 1 3 2 30 …` 은 조문 번호다.
                                     #    충주 첫 다른-사업 생성에서 확인, 09-03)
]


def _tables(hwpx):
    """(캡션, 숫자 시퀀스) 목록 — score_regional 파서로 최상위 표만."""
    z = zipfile.ZipFile(hwpx)
    out = []
    for n in sorted(x for x in z.namelist()
                    if re.match(r"Contents/section\d+\.xml$", x)):
        xml = z.read(n).decode("utf-8")
        xml = re.sub(r"<hp:(header|footer)[ >].*?</hp:\1>", " ", xml, flags=re.S)
        pos = 0
        for a, b in S._top_tables(xml):
            cells = [c for c in S._text(xml[a:b]) if c]
            caps = [c for c in S._text(xml[pos:a]) if c]
            pos = b
            if not cells:
                continue
            cap = next((c for c in reversed(caps) if len(c) >= 4
                        and not c.startswith(("자)", "주)"))), "")
            out.append((cap, tuple(NUM.findall(" ".join(cells)))))
    return out


def _cells(hwpx):
    """표마다 **모든 셀 텍스트 집합** — 중첩표 안까지 (최상위 span 안의 <hp:t> 전부).
    ②(숫자 시퀀스 동일)가 못 보는 두 자리를 위해 (Windows ⑪ 실측, 2026-09-03):
      · 중첩표 — 바깥 셀은 비웠는데 안쪽 표의 `43.51`·`1.596`·`3.77` 이 남아 통과
      · 부분 변경 — 조서처럼 데이터는 비우고 **합계만** 남은 표는 시퀀스가 달라져 통과"""
    z = zipfile.ZipFile(hwpx)
    out = []
    for n in sorted(x for x in z.namelist() if re.match(r"Contents/section\d+\.xml$", x)):
        xml = re.sub(r"<hp:(header|footer)[ >].*?</hp:\1>", " ",
                     z.read(n).decode("utf-8"), flags=re.S)
        pos = 0
        for a, b in S._top_tables(xml):
            cells = {c for c in S._text(xml[a:b]) if c}
            caps = [c for c in S._text(xml[pos:a]) if c]
            pos = b
            if not cells:
                continue
            cap = next((c for c in reversed(caps) if len(c) >= 4
                        and not c.startswith(("자)", "주)"))), "")
            out.append((cap, cells))
    return out


# 구조 상수 — 표의 **고정 열**에 늘 같은 값이 놓이는 것들. 잔존이 아니라 서식이다.
#   IDF 표 지속시간(분): 천안 수질에서 ③이 1080·1440·2880 을 잔존으로 오탐 (2026-09-03).
GENERIC_NUMS = {"120", "180", "240", "360", "540", "720", "900", "1080", "1440", "2880", "4320"}


def _specific(cell):
    """기준 사업 **고유값**으로 볼 만한 숫자 셀인가 — 유효 숫자 3자리 이상.
    `43.51`·`3.77`·`8,527` ✓ · `50`·`30`(빈도)·`2023`(연도)·`100.00`(구성비 합)·`0.05` ✗.
    ⚠️ 두 자리 소수(첨두홍수량 0.05)는 놓친다 — 골든 대조(채점)가 잡는 층으로 남긴다."""
    v = cell.strip()
    if not re.fullmatch(r"[\d,]+(?:\.\d+)?", v):
        return False
    d = v.replace(",", "")
    if d in ("100", "100.0", "100.00") or d in GENERIC_NUMS:
        return False
    if "." not in d and 1900 <= int(d) <= 2099:
        return False
    return len(d.replace(".", "").lstrip("0")) >= 3


def numeric_residue(base_p, out_p, allow=()):
    """③ 숫자 잔존 — 베이스와 산출물의 **같은 표**(순서 짝)에서 고유 숫자 셀이 그대로면 유출.
    반환 [(캡션, [잔존 셀…])]. 법령·참조표(allow 캡션)는 같아야 정상이라 제외."""
    bt, ot = _cells(base_p), _cells(out_p)
    pairs = list(zip(bt, ot)) if len(bt) == len(ot) else [
        ((bc, bs), (oc, os_)) for oc, os_ in ot for bc, bs in bt if bc and bc == oc]
    found = []
    for (bcap, bcells), (ocap, ocells) in pairs:
        cap = ocap or bcap
        if any(k in cap for k in allow):
            continue
        if bcells == ocells:
            continue        # 표 전체가 그대로 = ②(표동일)의 영역 — 정당 동일이 많아 경고로 둔다
                            # (폐유 표: 같은 표준 품셈 장비면 값이 같다 — 천안 실측 오탐 방지)
        shared = sorted(c for c in (bcells & ocells) if _specific(c))
        if shared:
            found.append((cap[:30] or "(캡션 없음)", shared))
    return found


def _lines(hwpx):
    """전체 텍스트 줄 — 머리글 **포함** (사업명 유출 전례, _category.md 5-1 ②)."""
    z = zipfile.ZipFile(hwpx)
    out = []
    for n in sorted(x for x in z.namelist()
                    if re.match(r"Contents/(section\d+|header\d*)\.xml$", x)):
        out += [t for t in re.findall(r"<hp:t[^>]*>([^<]*)</hp:t>",
                                      z.read(n).decode("utf-8")) if t.strip()]
    return out


def check(category, part, case, detail=False):
    out_p = ROOT / "cases" / category / case / part / "output.hwpx"
    base_p = ROOT / "templates" / category / f"{part}.hwpx"
    if not out_p.exists():
        sys.exit(f"산출물 없음 — {out_p}")
    if not base_p.exists():
        sys.exit(f"베이스 없음 — {base_p}")

    base_cfg = CATEGORY_BASE.get(category)
    if base_cfg is None:
        print(f"'{category}' 는 기준 사업 지명이 미등록 — 표 유출 검사를 건너뜀 "
              f"(CATEGORY_BASE 에 등록할 것. 조용한 무의미 검사보다 낫다)")
        return True

    # 대상 사업 시군 — vars 에서. 되먹임이면 검사 자체가 무의미하다 (§4 ⚠️).
    # ⚠️ **`시군` 키가 없는 카테고리가 있다** — 재해 vars 는 `위치` 한 줄만 갖는다.
    #    그러면 되먹임인데도 스킵이 안 걸려 **자기 지명이 전부 유출로 뜬다**
    #    (재해 첫 베이스 3장에서 14건. 2026-09-01 Windows 실측).
    #    `시군` 이 없으면 `위치`·`주소_일원` 에서 기준 시군을 찾아 되먹임을 판정한다.
    시군 = None
    for vp in sorted((ROOT / "cases" / category / case / "vars").glob("*.json")):
        사업 = json.loads(vp.read_text(encoding="utf-8")).get("사업", {})
        시군 = 사업.get("시군")
        if 시군:
            break
        for k in ("위치", "주소_일원"):
            if base_cfg["시군"] in str(사업.get(k) or ""):
                시군 = base_cfg["시군"]
                break
        if 시군:
            break
    # 되먹임 판정은 **사업 이름**으로 한다 — 시군으로 하면 같은 시군의 다른 사업(예: 소환
    # 기준이 원주인데 원주 태장동 신규 사업)을 되먹임으로 오인해 검사를 건너뛴다.
    # 위에서 구한 `시군` 은 뒤섞인 값 탐지(상위 행정구역 × 새 시군)에만 쓴다.
    if case == base_cfg["기준사업"]:
        print("되먹임(기준 사업 자기 생성) — 표 유출 검사는 무의미하다. 건너뜀 (증거 문서 §4)")
        return True

    fail, warn = [], []

    # ── ① 지명 유출 + 뒤섞인 값
    names, upper = base_cfg["이름들"], base_cfg["상위"]
    for ln in _lines(out_p):
        hits = [w for w in names if w in ln
                and not all(ln[i + len(w):i + len(w) + 1] == SUBSTRING_TRAP.get(w)
                            for i in range(len(ln)) if ln.startswith(w, i))]
        mixed = 시군 and any(u in ln for u in upper) and 시군 in ln
        if not hits and not mixed:
            continue
        soft = any(p.search(ln) for p in CONTEXT_OK)
        row = (("뒤섞임" if mixed else "지명"), ", ".join(hits) or f"{upper[-1]}+{시군}",
               ln.strip()[:70])
        (warn if soft else fail).append(row)

    # ── ② 표 동일 — 숫자 시퀀스 완전 일치 (빈 시퀀스 제외)
    bt, ot = _tables(base_p), _tables(out_p)
    base_seqs = {seq: cap for cap, seq in bt if seq}
    for cap, seq in ot:
        if not seq or seq not in base_seqs:
            continue
        if any(k in cap for k in ALLOW_IDENTICAL):
            continue                        # 법령·참조표·수식 상수 — 같아야 정상
        # 숫자 3개 미만이거나 전부 한 자리(지점 번호 `1 1 1`·연도 조각)면 신호가 아니다
        if len(seq) < 3 or all(len(x.replace(",", "").replace(".", "")) < 2 for x in seq):
            continue
        warn.append(("표동일", cap[:30] or "(캡션 없음)",
                     " ".join(seq[:8]) + (" …" if len(seq) > 8 else "")))

    # ── ③ 숫자 잔존 — 셀 단위, 중첩표 포함 (②가 못 보는 두 자리 — Windows ⑪ 인계)
    for cap, shared in numeric_residue(base_p, out_p, ALLOW_IDENTICAL):
        fail.append(("숫자잔존", cap, ", ".join(shared[:6]) + (" …" if len(shared) > 6 else "")))

    for kind, what, ctx in fail:
        print(f"  🚨 {kind:<4} {what:<20} | {ctx}")
    shown = warn if detail else warn[:15]
    for kind, what, ctx in shown:
        print(f"  ⚠️ {kind:<4} {what:<20} | {ctx}")
    if len(warn) > len(shown):
        print(f"  … 경고 {len(warn) - len(shown)}건 더 (--detail)")
    print(f"\n{'🚨 유출 ' + str(len(fail)) + '건 — 내보내면 안 된다' if fail else '✅ 유출 0'}"
          f" · 훑어볼 경고 {len(warn)}건")
    return not fail


def main():
    console_utf8()   # ⚠️ cp949 에는 ✅·⚠️ 가 없다 — 파이프로 돌면 죽는다
    ap = argparse.ArgumentParser(description="표 유출 검사 — 산출물 vs 베이스")
    ap.add_argument("category")
    ap.add_argument("part")
    ap.add_argument("case")
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if check(a.category, a.part, a.case, a.detail) else 1)


if __name__ == "__main__":
    main()

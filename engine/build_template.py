#!/usr/bin/env python3
"""
베이스 문서 빌더 — 골든셋에 빈칸을 뚫어 templates/{카테고리}/{파트}.hwpx 를 만든다.

  golden/{카테고리}/{기준사업}/원본.hwpx  →  templates/{카테고리}/{파트}.hwpx

6단계(`docs/windows_session.md` §1)를 **재현 가능하게** 만든 것이다.
안내서는 한글 수작업을 전제하지만, 손으로 치면 가운뎃점 3종(`·` `ㆍ` `․`)과
스마트따옴표(`‘’` `“”`)에서 매칭이 깨진다(`_category.md` §4). 문자열을 코드에
박아 두면 다시 만들 때 같은 결과가 나온다.

⚠️ Windows + 한글 프로그램 전용.
⚠️ 여기 적힌 `찾을 문자열` 은 **원주 무장리 골든셋 실측**이다.
   기준 사업을 바꾸면 SPECS 를 다시 실측해야 한다.

명세: templates/small-env/noise-vib.slots.md
사용:
    python engine/build_template.py small-env noise-vib
    python engine/build_template.py small-env noise-vib --dry-run   # 매칭 검사만
"""

import argparse
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ============================================================
# 파트별 빈칸 명세
# ============================================================
# (찾을 문자열, 바꿀 문자열) — 한글 AllReplace 는 표 안쪽도 포함한다.
NOISE_VIB_REPLACE = [
    # --- A절 1~5 ---
    ("원주시 호저면 무장리 578번지 일원 태양광발전시설 조성사업", "{{사업명}}"),
    ("2025. 06. 30. ~ 2025. 07. 04.", "{{조사시기}}"),
    ("강원특별자치도 원주시 호저면 생담길 120", "{{측정지점_주소}}"),
    ("2025년 06월 24일 ~ 06월 25일", "{{측정일시}}"),
    ("사업계획지구 주변 1개 지점의 소음 측정 결과", "{{측정결과_도입}}"),

    # --- A절 6~9 · 숫자만 바꾸고 단위는 남긴다 ---
    ("주간 평균 45.0dB(A), 야간 평균 39.0dB(A)",
     "주간 평균 {{소음_주간평균}}dB(A), 야간 평균 {{소음_야간평균}}dB(A)"),
    ("주간 평균 10.0dB(V), 야간 9.0dB(V)",
     "주간 평균 {{진동_주간평균}}dB(V), 야간 {{진동_심야평균}}dB(V)"),

    # --- A절 10 · 가운뎃점 U+2024 ---
    ("소음․진동 측정지점도", "{{측정지점도_캡션}}"),

    # --- A절 11~12 · 같은 토큰, 문맥이 다르다 ---
    ("반경 1.0km 이내(5개 지점)", "반경 1.0km 이내({{예측지점_수}}개 지점)"),
    ("대표 시설 5개 지점을", "대표 시설 {{예측지점_수}}개 지점을"),

    # --- A절 13~16 · 최인접 거리는 소음·진동 두 곳 (AllReplace 로 동시 처리) ---
    ("가장 인접한 정온시설은 46m 이격",
     "가장 인접한 정온시설은 {{최인접_이격거리}}m 이격"),
    ("정온시설의 영향이 있을 것으로", "정온시설의 영향이 {{소음영향_서술}} 것으로"),
    ("정온시설의 진동 영향이 없을 것으로",
     "정온시설의 진동 영향이 {{진동영향_서술}} 것으로"),

    # --- A절 17~18 · 스마트따옴표 U+2018/U+2019. 목표 수치도 함께 토큰화 ---
    ("대상지역 ‘가’ 지역의 공사장 낮 기준 65dB(A)",
     "대상지역 ‘{{목표기준_지역문자}}’ 지역의 공사장 낮 기준 {{목표소음_주거}}dB(A)"),
    ("상 ‘가’ 지역 의 주간 기준 65dB(V)",
     "상 ‘{{목표기준_지역문자}}’ 지역 의 주간 기준 {{목표진동_주거}}dB(V)"),

    # --- 6단계에서 추가로 발견한 자리 (slots.md §D 지시) ---
    # 축사 목표기준 — 원주와 괴산이 같지만 사업마다 갈릴 수 있어 토큰화
    ("가축피해 강화기준 60dB(A)", "가축피해 강화기준 {{목표소음_축사}}dB(A)"),
    ("가축피해 강화기준 57dB(V)", "가축피해 강화기준 {{목표진동_축사}}dB(V)"),
    # 표 5 측정지점 — 엔진이 셀 편집하지 않는다. 원주 값이 남으면 MISSING 오류
    ("250", "{{측정지점_이격거리}}"),
    ("축사 인근", "{{측정지점_비고}}"),
    # 표 19 투입장비 일 작업량
    ("201.22", "{{일작업량}}"),
    # 표 6 소음환경기준 행 — 지역 문자. 숫자 2칸은 아래 CELL 에서 처리
    ("소음환경기준(일반지역 “나” 지역)",
     "소음환경기준(일반지역 “{{소음환경기준_지역}}” 지역)"),

    # --- 2026-07-31 천안 검증에서 드러난 자리 (rule §4-3 · §5-2) ---
    # 인용(문헌자료) 케이스에서 함께 바뀌는 6곳 중 4곳. 나머지 2곳은 위에 이미 있다
    ("소음․진동 현황 : 측정자료", "소음․진동 현황 : {{현황_자료유형}}"),
    ("(2) 소음ㆍ진동 현황", "(2) 소음ㆍ진동 현황{{현황_소제목_접미}}"),
    ("본 사업시행으로 인하여 직·간접적인 영향이 예상되는 지역 중 사업계획지구와 "
     "가장 인접한 1개 지점을 선정하여 소음·진동 측정을 실시하였다.", "{{측정지점_도입}}"),
    ("사업계획지구 주변 1개 지점의 진동 측정 결과", "{{진동측정결과_도입}}"),
    # 예측소음도 결과 서술 — 상회 지점이 있으면 '~를 제외한' 이 붙는다
    ("P-1 지점을 제외한 전 지점에서 기준치를 만족하는 것으로 예측되었다",
     "{{예측소음도_결과서술}}"),
    # 표 7 생활진동 규제기준 행 — 천안은 '가. 주거지역' 65/60 이라 원주와 다르다
    ("생활진동 규제기준(나. 그밖의 지역)", "생활진동 규제기준({{생활진동규제_지역}})"),
    # 표 19 시간당 작업량 — 일 작업량 ÷ 8 (`주) 일 작업시간 : 8시간 기준`, 천안에서 확인)
    ("25.15", "{{시간당작업량}}"),
    # 저감 1)절 — 상회 0건이면 `필요시` 가 붙는다 (rule §4-1)
    ("1) 저소음 건설장비 사용", "1) {{저감1_접두}}저소음 건설장비 사용"),
]

# (앵커 문자열, skip, [(오른쪽으로 n칸, 넣을 값), ...])
# 숫자 셀은 문서 전체에서 유일하지 않아 찾기/바꾸기로 못 잡는다. 셀을 짚어 넣는다.
NOISE_VIB_CELLS = [
    ("소음환경기준(일반지역", 0,
     [(1, "{{소음환경기준_주간}}"), (1, "{{소음환경기준_야간}}")]),
    ("생활진동 규제기준(", 0,
     [(1, "{{생활진동규제_주간}}"), (1, "{{생활진동규제_심야}}")]),
]

# ============================================================
# 대기질 — 명세: templates/small-env/air-quality.slots.md
# 기준 사업 청주 호명리 (전 축에서 다수 쪽 — slots.md 서두)
# ============================================================
AIR_QUALITY_REPLACE = [
    # --- A절 1~5 ---
    # 사업명이 운영시 문단의 `태양광발전소 조성사업` 을 포함한다 — 긴 것 먼저 (16번보다 앞)
    ("청주시 청원구 북이면 호명리 430번지 외 2필지 태양광발전소 조성사업", "{{사업명}}"),
    ("2024. 01. 08 ~ 2024. 01. 26", "{{조사시기}}"),
    ("충북 청주시 청원구 북이면 호명리 235", "{{측정지점_주소}}"),
    # ⚠️ 원본 연도 오타(2023 ← 2024)를 그대로 찾아야 매칭된다 (slots.md A-4)
    ("2023년 01월 09일 ~ 01월 10일", "{{측정일시}}"),
    ("전 항목이 대기환경 기준치 이내를 만족하는 것으로 나타났다", "{{측정결과_서술}}"),

    # --- A절 6~7 · 같은 토큰 두 곳 ---
    ("이내(5개 지점)", "이내({{예측지점_수}}개 지점)"),
    ("대표 시설 5개 지점을", "대표 시설 {{예측지점_수}}개 지점을"),

    # --- A절 8~9 · 기상 ---
    ("청주기상대", "{{부지기상_기상대}}"),        # 본문 1 + 표 안 2 — AllReplace 로 3곳
    ("오산고층기상관측망", "{{상층기상}}"),

    # --- A절 10 · 숫자 3개만 토큰 ---
    ("공사시 총 토공량은 758.90㎥로 토공사 기간 50일 감안하여 일 작업량을 산정한 결과, "
     "약 15.18㎥/일로 산정되었다.",
     "공사시 총 토공량은 {{총토공량}}㎥로 토공사 기간 {{토공기간}}일 감안하여 "
     "일 작업량을 산정한 결과, 약 {{일작업량}}㎥/일로 산정되었다."),

    # --- A절 11 ---
    ("공사시 주변 정온시설의 대기질 영향을 예측한 결과 전지점에서 대기환경 기준을 "
     "만족하는 것으로 조사되었다.", "{{예측결과_서술}}"),

    # --- A절 12 · 두 곳의 표기가 다르다 (쉼표) ---
    ("(기상연보 2022년, 기상청)", "(기상연보 {{기상연보_연도}}년, 기상청)"),
    ("(기상연보, 2022년, 기상청)", "(기상연보, {{기상연보_연도}}년, 기상청)"),

    # --- A절 13 · 표기 2종 (`품셈 2023` ×2 · `품셈.2023` ×1) ---
    ("품셈 2023", "품셈 {{품셈_연도}}"),
    ("품셈.2023", "품셈.{{품셈_연도}}"),

    # --- A절 14~15 · 주석 숫자 ---
    ("= 15.18 / 10.3 ≒ 2", "= {{일작업량}} / 10.3 ≒ {{운반횟수}}"),
    ("0.15km로 제시", "{{이동거리}}km로 제시"),

    # --- A절 16~18 ---
    ("본 사업은 태양광발전소 조성사업으로", "{{사업종류_운영시}}"),
    ("공사시 주변지역 대기질의 영향이 미미할 것으로 예상되나, 비산먼지 저감을 위해 "
     "각종 방안 (살수, 차속제한 등)을 필요시 실시할 계획이며,", "{{저감효과_도입}}"),
    ("각종 저감방안의 실시 후 전 항목이 전 지점에서 대기환경기준(24시간 기준)을 "
     "만족하는 것으로 나타났다.", "{{저감후_서술}}"),

    # --- 청주 고유 문장 삭제 (1/4 — slots.md A 하단) ---
    ("기허가지는 부지 및 태양광패널 설치가 완료되어, 금회 사업부지에 한하여 "
     "작업량을 산정하였다.", ""),
]

SPECS = {
    "air-quality": {
        "source": "청주_호명리",
        # 대기질 원본은 golden/ 이 아니라 raw_data 에 있다 (hwp → hwpx 변환본)
        "src": "raw_data/청주_호명리/0722_대기질.hwpx",
        "replace": AIR_QUALITY_REPLACE,
        "cells": [],        # B절 표는 전부 엔진(generate.py)이 셀 편집 — 빈칸을 뚫지 않는다
        "expect": [
            "사업명", "조사시기", "측정지점_주소", "측정일시", "측정결과_서술",
            "예측지점_수", "부지기상_기상대", "상층기상",
            "총토공량", "토공기간", "일작업량",
            "예측결과_서술", "기상연보_연도", "품셈_연도",
            "운반횟수", "이동거리",
            "사업종류_운영시", "저감효과_도입", "저감후_서술",
        ],
    },
    "noise-vib": {
        "source": "원주_무장리",
        "replace": NOISE_VIB_REPLACE,
        "cells": NOISE_VIB_CELLS,
        # 만들어져야 하는 토큰 (slots.md D절) — 저장 후 대조한다
        "expect": [
            "사업명", "조사시기", "측정일시", "측정지점_주소", "측정지점_이격거리",
            "측정지점_비고", "소음_주간평균", "소음_야간평균", "진동_주간평균",
            "진동_심야평균", "소음환경기준_지역", "소음환경기준_주간",
            "소음환경기준_야간", "측정결과_도입", "측정지점도_캡션", "예측지점_수",
            "최인접_이격거리", "일작업량", "소음영향_서술", "진동영향_서술",
            "목표기준_지역문자", "목표소음_주거", "목표소음_축사",
            "목표진동_주거", "목표진동_축사",
            # 2026-07-31 추가 (천안 검증)
            "현황_자료유형", "현황_소제목_접미", "측정지점_도입",
            "진동측정결과_도입", "예측소음도_결과서술",
            "생활진동규제_지역", "생활진동규제_주간", "생활진동규제_심야",
            "시간당작업량", "저감1_접두",
        ],
    },
}


# ============================================================
def check(spec, golden_txt, src_hwpx=None):
    """찾을 문자열이 실재하는지 — 한글 없이도 돌아간다.

    골든 txt 와 원본 hwpx XML **둘 다** 본다. 두 검사는 서로 반대로 깨진다:
    형광펜(markpen)에 걸친 문자열은 XML 에서 쪼개지고(소음진동 실증),
    텍스트 노드가 갈라진 문자열은 추출 txt 에서 줄이 나뉜다(청주 조사시기 실증).
    **둘 중 하나에서 찾으면 한글 찾기/바꾸기는 매칭한다** — 런 경계를 무시하기 때문.
    """
    text = golden_txt.read_text(encoding="utf-8")
    xml = ""
    if src_hwpx and src_hwpx.exists():
        with zipfile.ZipFile(src_hwpx) as z:
            xml = z.read("Contents/section0.xml").decode("utf-8")

    bad = 0
    for old, new in spec["replace"]:
        n_txt, n_xml = text.count(old), xml.count(old)
        ok = n_txt or n_xml
        if not ok:
            bad += 1
        where = f"txt {n_txt}·xml {n_xml}"
        print(f"  {'OK  ' if ok else 'MISS'} {where:12s}  {old[:50]}")
    for anchor, _, _ in spec["cells"]:
        ok = text.count(anchor) or xml.count(anchor)
        if not ok:
            bad += 1
        print(f"  {'OK  ' if ok else 'MISS'} {'':12s}  [셀] {anchor[:46]}")
    return bad


def normalize(hwp, tokens):
    """토큰을 단일 런으로 만든다.

    원본에 글자 서식 경계(형광펜 끝 표시 등)가 걸쳐 있으면 바꾼 결과가
    `{{진동</hp:t>...<hp:t>_주간평균}}` 처럼 XML 상에서 쪼개진다. 한글 찾기/바꾸기는
    이래도 매칭되지만 `generate.py` 의 잔여 토큰 검사(raw XML 비교)가 무력해진다.
    찾은 자리는 선택 상태이므로 같은 문자열을 다시 넣으면 서식이 하나로 합쳐진다.
    """
    from generate import find_fwd
    for t in tokens:
        tok = "{{%s}}" % t
        hwp.MovePos(2)
        for _ in range(10):
            if not find_fwd(hwp, tok):
                break
            hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
            hwp.HParameterSet.HInsertText.Text = tok
            hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)


def caption_paras(hwpx):
    """표 바로 앞 문단(= 표 캡션)의 문단 번호를 돌려준다.

    `hp:caption` 이 0개다 — 캡션은 표에 붙은 개체가 아니라 **별도 문단**이라
    표가 다음 쪽으로 밀릴 때 캡션만 앞 장에 남는다 (`docs/layout_review.md` §1-1).
    XML 은 **읽기만** 한다. 고치는 것은 한글 API 다 (`rules/hwpx.md`).
    """
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(hwpx) as z:
        root = ET.fromstring(z.read("Contents/section0.xml"))

    tops = [c for c in root if c.tag.endswith("}p")]
    out = []
    for i, p in enumerate(tops):
        has_tbl = any(e.tag.endswith("}tbl") for e in p.iter())
        if has_tbl and i > 0:
            out.append(i - 1)
    return out, tops


def keep_captions_with_table(dst):
    """캡션 문단에 '다음 문단과 함께' 를 건다. 저장이 끝난 파일을 다시 열어 처리한다."""
    import win32com.client

    idxs, tops = caption_paras(dst)
    print(f"  캡션 문단 {len(idxs)}개에 KeepWithNext 적용")

    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False
    hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
    hwp.Open(str(dst))

    for i in idxs:
        hwp.SetPos(0, i, 0)
        # GetDefault 는 커서가 놓인 문단의 현재 모양을 읽는다 —
        # 이것을 건너뛰면 정렬·들여쓰기가 기본값으로 덮인다.
        hwp.HAction.GetDefault("ParagraphShape", hwp.HParameterSet.HParaShape.HSet)
        hwp.HParameterSet.HParaShape.KeepWithNext = 1
        hwp.HAction.Execute("ParagraphShape", hwp.HParameterSet.HParaShape.HSet)

    hwp.SaveAs(str(dst), "HWPX")
    hwp.Quit()
    time.sleep(2)
    return len(idxs)


def build(spec, src, dst):
    import win32com.client
    from generate import fr, find_in_table, set_cell, right

    shutil.copy(src, dst)
    print(f"[1/4] 복사: {dst.name}")

    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False
    hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
    hwp.Open(str(dst))
    print("[2/4] 한글 열기 완료")

    print(f"[3/4] 찾기/바꾸기 {len(spec['replace'])}건...")
    for old, new in spec["replace"]:
        fr(hwp, old, new)
        print(f"  {old[:46]:48s} -> {new[:40]}")

    for anchor, skip, steps in spec["cells"]:
        print(f"  [셀] {anchor}")
        if not find_in_table(hwp, anchor, skip=skip):
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 스킵")
            continue
        for n, value in steps:
            right(hwp, n)
            set_cell(hwp, value)
            print(f"    +{n}칸 = {value}")

    print(f"  [정리] 토큰 {len(spec['expect'])}종 단일 런으로 병합")
    normalize(hwp, spec["expect"])

    print("[4/4] 저장...")
    hwp.SaveAs(str(dst), "HWPX")
    hwp.Quit()
    time.sleep(2)


def verify(spec, dst):
    """저장된 베이스 문서의 토큰을 명세와 대조."""
    import re
    import zipfile
    with zipfile.ZipFile(dst) as zf:
        xml = zf.read("Contents/section0.xml").decode("utf-8")
    found = set(re.findall(r"\{\{([^}]+)\}\}", xml))
    want = set(spec["expect"])
    print(f"\n토큰 {len(found)}종 발견")
    for k in sorted(want & found):
        print(f"  OK      {{{{{k}}}}}")
    for k in sorted(want - found):
        print(f"  MISSING {{{{{k}}}}}")
    for k in sorted(found - want):
        print(f"  EXTRA   {{{{{k}}}}}  <- 명세에 없다")
    return not (want - found) and not (found - want)


def main():
    ap = argparse.ArgumentParser(description="베이스 문서(빈칸) 생성")
    ap.add_argument("category")
    ap.add_argument("part")
    ap.add_argument("--dry-run", action="store_true", help="매칭 검사만 (한글 불필요)")
    a = ap.parse_args()

    if a.part not in SPECS:
        sys.exit(f"ERROR: '{a.part}' 명세 없음. 지원: {list(SPECS)}")
    spec = SPECS[a.part]

    gold = ROOT / "golden" / a.category / spec["source"]
    # 원본이 golden/ 밖(raw_data)에 있는 파트는 `src` 로 지정한다 (대기질 — hwp 변환본)
    src = ROOT / spec["src"] if "src" in spec else gold / "원본.hwpx"
    if not src.exists():
        sys.exit(f"ERROR: 원본 없음 — {src}\n  (raw_data 원본은 git 에 없다 — NAS 에서 받을 것)")

    print(f"기준 사업: {spec['source']}\n찾을 문자열 검사:")
    bad = check(spec, gold / f"{a.part}.txt", src)
    if bad:
        sys.exit(f"\nERROR: 매칭 실패 {bad}건 — 문자열을 골든셋에서 다시 실측할 것")
    print("\n전부 매칭 ✅")

    if a.dry_run:
        return

    dst = ROOT / "templates" / a.category / f"{a.part}.hwpx"
    dst.parent.mkdir(parents=True, exist_ok=True)
    build(spec, src, dst)

    print("\n[5/5] 캡션 쪽 분리 방지...")
    keep_captions_with_table(dst)

    ok = verify(spec, dst)
    print(f"\n완료: {dst} ({dst.stat().st_size:,} bytes)")
    print("베이스 문서 준비 완료 ✅" if ok else "\n⚠️ 명세와 어긋난다 — 위 목록 확인")


if __name__ == "__main__":
    main()

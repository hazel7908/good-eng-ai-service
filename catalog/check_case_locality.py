#!/usr/bin/env python3
"""골든 수확물 지자체 검증 — 파일명·번호 매칭만 믿지 않는다.

두 번 데었다: ①청양 0200 이 내용은 강릉시였다(파일명 `(완)` 함정) ②천안 폴더(환25-05)에
여주 광대리 사업 복사본이 섞여 재추출을 오염시켰다(09-07 Windows 보류 사유).
→ **본문 지자체명 빈도 검사**로 수확물이 그 사업 것인지 판정한다.

사용: python catalog/check_case_locality.py 천안 golden/small-env/천안_화덕리/*.txt
  기대 지자체(첫 인자)가 본문 최빈 시군과 다르면 ✗. 시군명 목록은 본문에서 직접 뽑는다
  (X시/X군/X구 패턴) — 사전이 필요 없어 어느 사업에든 쓸 수 있다.

판정 규칙: 최빈 시군 == 기대 → ✓ · 기대가 상위 3위 밖이거나 최빈이 다른 시군(2배 이상) → ✗
(인접 지자체 언급은 정상이라 단순 존재로는 판정하지 않는다 — 빈도 비교만).
"""
import re
import sys
from collections import Counter
from pathlib import Path

SIGUN = re.compile(r"([가-힣]{1,4}[시군])(?=[은는이가의에와과로를\s,.)〕〉」』]|$)")
# `공사시`·`운영시` 같은 때 시(時) 어미가 시군으로 잡힌다 — 블랙리스트는 끝이 없어서,
# **같은 문서에서 도명 뒤에 등장한 적 있는 이름만** 시군으로 인정한다
# (`충청남도 천안시`는 있어도 `충청남도 공사시`는 없다).
DO = (r"(?:서울|인천|대전|대구|부산|울산|광주|세종|경기도|강원도|강원특별자치도|충청북도|충청남도|"
      r"전라북도|전북특별자치도|전라남도|경상북도|경상남도|제주|충북|충남|전북|전남|경북|경남|강원)")


def top_sigun(txt: str):
    valid = set(re.findall(DO + r"\s*([가-힣]{1,4}[시군])", txt))
    # 행정구역 연쇄 — `천안시 동남구`·`원주시 호저면`처럼 시군 뒤에 구·읍·면·동·리가
    # 따라오면 지명이다 (`공사시` 뒤엔 읍면이 오지 않는다)
    valid |= set(re.findall(r"([가-힣]{1,4}[시군])\s+[가-힣]{1,5}[구읍면동리]\b", txt))
    # 연쇄 규칙의 동형어 구멍(`공사시 진동`·`운영시 관리`)은 이 도메인의 時-명사 블랙리스트로 막는다
    valid -= {"시군", "공사시", "운영시", "발파시", "굴착시", "운행시", "산정시", "측정시",
              "조성시", "가동시", "강우시", "비강우시", "작업시", "작업실시", "설치시", "해석시",
              "평가시", "협의시", "검토시", "계획시", "시행시", "완료시", "착공시", "준공시"}
    cnt = Counter(m for m in SIGUN.findall(txt) if m in valid and len(m) >= 3)
    return cnt.most_common(6)


def check(expect: str, path: Path) -> bool:
    txt = path.read_text(encoding="utf-8", errors="replace")
    top = top_sigun(txt)
    if not top:
        print(f"  ? {path.name}: 시군명 없음 (표지·서식 파일일 수 있음)")
        return True
    best, best_n = top[0]
    exp_n = dict(top).get(expect) or dict(top).get(expect + "시") or dict(top).get(expect + "군") or 0
    ok = best.startswith(expect) or (exp_n and best_n < exp_n * 2)
    if not ok and best_n <= 3:
        # 저신호 — 부록(대행업체 주소뿐)·경관(인접 지자체 언급뿐) 같은 문서는 판정 보류
        print(f"  ? {path.name}: 신호 약함 — 최빈 {best}({best_n}) · 기대 {expect} {exp_n}회 (사람 확인)")
        return True
    mark = "✓" if ok else "✗"
    print(f"  {mark} {path.name}: 최빈 {best}({best_n})" +
          (f" · 기대 {expect} {exp_n}회" if not best.startswith(expect) else "") +
          ("" if ok else f"  ← 다른 사업 의심! 상위: {top[:3]}"))
    return ok


def main():
    if len(sys.argv) < 3:
        sys.exit("사용: check_case_locality.py <기대 지자체(예: 천안)> <txt...>")
    expect, files = sys.argv[1], sys.argv[2:]
    bad = sum(not check(expect, Path(f)) for f in files)
    print(f"\n{len(files)}건 중 의심 {bad}건" + (" — 수확물을 갈아끼우지 말 것" if bad else " ✓"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

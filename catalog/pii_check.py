#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""인풋 개인정보 검사·가리기 — 신청서류·조서에는 실명·주민번호·연락처·자택주소가 산다.

세 번 데었다 (2026-09-08, 전부 천안 개발행위허가신청서):
  ① 주민번호·연락처만 정규식으로 지웠더니 **인적사항 라벨 다음 줄의 이름·주소가 남았다**
  ② 동호수를 먼저 가리자 그 줄에 `[개인정보]` 가 생겼고, 라벨 규칙이 "이미 가려졌다"고
     보고 건너뛰어 **도로명 주소가 그대로 남았다** — 부분 마스킹이 전체 마스킹을 막았다
  ③ **편입토지조서 소유자 열의 실명**은 라벨도 정규식도 안 걸렸다 (Mac 적발)

→ 규칙 셋:
  · 개인정보가 **한 조각이라도** 든 줄은 통째로 가린다 (그런 줄에 사업 정보는 없다)
  · 인적사항 라벨 다음 줄은 **무조건** 통째로
  · 조서형 줄(지번·면적과 사람 이름이 같이 있는 줄)의 이름은 **자동으로 못 지운다** —
    지명과 구분이 안 되기 때문이다. **후보로 찍어 사람이 확인**한다.

사용:
    python catalog/pii_check.py <txt…>              # 검사만 (후보 보고)
    python catalog/pii_check.py --fix <txt…>        # 가리기 + 검사
"""
import re
import sys
from pathlib import Path

RRN = re.compile(r"\d{6}\s?-\s?[1-4]\d{6}")
TEL = re.compile(r"01[016-9][-\s]?\d{3,4}[-\s]?\d{4}")
DONG = re.compile(r"\d{3,4}\s?동\s?\d{1,4}\s?호")
ROAD = re.compile(r"[가-힣]+(?:로|길)\s?\d+(?:[-길]\d+)?")
LAB = ("성명(법인명 및 대표자 성명)", "생년월일(법인등록번호)", "주소", "전화번호",
       "성명", "생년월일", "소유자", "신청인")
# 조서 줄: 지번(숫자-숫자)과 면적(쉼표 숫자)이 같이 있는 줄
JOSEO = re.compile(r"\d+-\d+.*?\d{1,3}(?:,\d{3})+|\d{1,3}(?:,\d{3})+.*?\d+-\d+")
# 🚨 **칸마다 한 줄로 추출되는 문서가 있다** (2026-09-09 — 옥계리 입안신청서 hwp).
#    그러면 위 한 줄 규칙이 통째로 헛돈다: `787-1` `2,927.0` `조형범` 이 **세 줄**로 나뉜다.
#    실명 `조형범` 8회가 그렇게 빠져나갔다 — 조서 구역을 잡아 **홀로 선 이름 줄**도 본다.
JOSEO_HEAD = re.compile(r"(편입\s*)?토지\s*조서|소유자별|소유\s*자")
BARE_NAME = re.compile(r"^[가-힣]{2,4}$")
# 조서 구역에 흔한 낱말 — 이름이 아니다
NOTNAME = set(
    "옥계리 서원면 횡성군 합계 소유자 지번 지목 비고 번호 소재지 기정 변경 증감 구성비 "
    "필지수 면적 공부 편입 추가부지 관련도면 임야 도로 하천 구거 대지 잡종지 과수원 "
    "목장용지 학교용지 주차장 창고용지 종교용지 유원지 광천지 염전 공장용지 철도용지 "
    "제방 수도용지 공원 사적지 묘지 유지 체육용지 용적률 건폐율 생활권 업무용 시가화 "
    "변경후 변경전 국유지 사유지 공유지 소계 총계".split())
# 사람 이름 후보: 2~4자 한글이 홀로 선 칸. 지명 접미사는 뺀다.
NAME = re.compile(r"(?<![가-힣])[가-힣]{2,4}(?![가-힣])")
지명끝 = ("시", "군", "구", "읍", "면", "리", "동", "로", "길", "천", "산", "km", "㎡")


def mask(lines, names=()):
    """개인정보를 가린다. `names` 는 **사람이 확인한** 실명 목록 (조서 칸 단독)."""
    out, n = [], 0
    confirmed = set(names)
    for i, l in enumerate(lines):
        if l.strip() in confirmed:
            out.append("[개인정보]"); n += 1; continue
        if i and lines[i - 1].strip() in LAB and l.strip():
            out.append("[개인정보]"); n += 1; continue
        new = DONG.sub("[개인정보]", RRN.sub("[개인정보]", TEL.sub("[개인정보]", l)))
        if new != l:
            out.append("[개인정보]"); n += 1; continue   # 조각이 들어간 줄은 통째로
        out.append(l)
    return out, n


def scan(text, label):
    bad = {"주민번호": RRN.findall(text), "연락처": TEL.findall(text),
           "동호수": DONG.findall(text)}
    hard = sum(len(v) for v in bad.values())
    names = []
    lines = text.splitlines()
    for l in lines:
        if not JOSEO.search(l):
            continue
        for w in NAME.findall(l):
            if not w.endswith(지명끝) and w not in ("소유자", "지목", "면적", "구분", "비고"):
                names.append((w, l.strip()[:60]))
    # 칸마다 한 줄인 문서 — **이웃 줄에 지번·면적이 있는** 홀로 선 이름만 본다.
    # 구역 전체를 훑으면 목차의 `토지조서` 부터 걸려 오탐이 수백 건이 된다(실측 344).
    JIBUN = re.compile(r"^\d+(-\d+)?$")
    AREA = re.compile(r"^\d{1,3}(,\d{3})*(\.\d+)?")
    for i, l in enumerate(lines):
        w = l.strip()
        if not BARE_NAME.match(w) or w in NOTNAME or w.endswith(지명끝):
            continue
        near = [x.strip() for x in lines[max(0, i - 6):i + 7]]
        if any(JIBUN.match(x) for x in near) and any(AREA.match(x) for x in near):
            names.append((w, f"(조서 칸 단독 — {i}행)"))
    print(f"  {label[:44]:46} 확정 {hard} · 조서 이름 후보 {len(names)}")
    for k, v in bad.items():
        if v:
            print(f"     🚨 {k} {len(v)}건")
    for w, l in names[:6]:
        print(f"     ⚠️ 이름 후보 `{w}` — {l}")
    return hard, len(names)


def main():
    args = sys.argv[1:]
    fix = "--fix" in args
    files = [a for a in args if a != "--fix"]
    tot = 0
    for f in files:
        p = Path(f)
        t = p.read_text(encoding="utf-8")
        if fix:
            lines, n = mask(t.splitlines())
            t = "\n".join(lines) + "\n"
            p.write_text(t, encoding="utf-8")
            print(f"  가림 {n}줄 — {p.name[:40]}")
        hard, _ = scan(t, p.name)
        tot += hard
    print(f"\n확정 개인정보 잔존 {tot}건" + ("" if tot == 0 else "  🚨 커밋 금지"))
    return 1 if tot else 0


if __name__ == "__main__":
    sys.exit(main())

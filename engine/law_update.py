#!/usr/bin/env python3
"""법령 인용 자동 최신화 — 치환 매핑 생성 (할 일 7 ④단계).

클라이언트 요구 = **항상 최신 법령 정보를 자동으로**. 층별 자동화:
  ① 인용 표기(법령명·고시번호) — 이 도구가 만든 매핑으로 완전 자동 치환
  ② 기준표 값 — law_annex 대조(현재 8종 전부 현행 일치 → 갱신 대상 없음)
  ③ 별표 구조 개정 — 자동 감지까지, 채움은 [확인 필요]

이 도구는 law_check_result.json(② 대조 결과)에서 **구인용 → 현행 표기** 치환 쌍을
기계 생성한다. 원칙:
  - STALE 행정규칙: 인용 문자열 안의 `제NNNN-NN호` → 현행 발령번호. 부처명이 함께
    인용된 경우(환경부고시 등) 현행 소관부처명으로 함께 교체
  - 구명칭 법령: 옛 법령명 → 현행 법령명 (낫표 안 문자열 통째)
  - 지자체 고시·확인필요·명칭미상은 제외 (사업 고유값이거나 근거 부족)

출력: catalog/review/law_update_map.json — Windows generate/build 단계가 이 매핑을
읽어 치환한다(적용 훅은 지시서 참조). 갱신 주기: law_check --fresh 재실행 → 이 도구
재실행이면 매핑이 항상 현행을 따라간다.

⚠️ 치환은 **표기가 유일하게 특정되는 쌍만** 만든다 — `제2023-63호` 같은 번호 문자열은
문서 전체에서 유일하므로 안전하고, 법령명은 낫표 포함 전체 문자열로만 바꾼다(부분
문자열 뒤섞임 금지 — 주소 오염 사고의 교훈).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTICE_NO = re.compile(r"제(\d{4}-\d+)호")

# 부처명 교체 — 인용 문자열 안에서 번호와 함께 바꾼다 (2025 정부조직 개편)
MINISTRY = {"환경부": "기후에너지환경부"}
# 구명칭 → 현행 법령명 (law_check 명칭불일치 중 실제 개명·폐지 확정분만.
#  약칭(세계유산법)·오탈 추정(다중이용업소·한강수계)은 제외 — 근거: 20260907_법령인용목록.md)
RENAMED = {
    "야생동·식물보호법": "야생생물 보호 및 관리에 관한 법률",
    "문화재보호법": "문화유산의 보존 및 활용에 관한 법률",
    "문화재보호법 시행령": "문화유산의 보존 및 활용에 관한 법률 시행령",
    "댐건설 및 주변지역지원 등에 관한 법률": "댐건설·관리 및 주변지역지원 등에 관한 법률",
    "에너지기본법 시행규칙": "에너지법 시행규칙",
    "수목원 조성 및 진흥에 관한 법률 시행규칙": "수목원·정원의 조성 및 진흥에 관한 법률 시행규칙",
}


def main():
    res = json.loads((ROOT / "catalog" / "review" / "law_check_result.json").read_text(encoding="utf-8"))
    cites = json.loads((ROOT / "catalog" / "review" / "law_citations.json").read_text(encoding="utf-8"))["법령"]
    pairs = []

    # ── STALE 행정규칙: 그 번호를 인용한 모든 표기 변형에 대해 번호(+부처명+날짜) 교체쌍 생성
    def norm(s):
        for d in "ㆍ‧∙･⸳․":
            s = s.replace(d, "·")
        return re.sub(r"[\s·]", "", s)

    suspects = []
    DATE = re.compile(r"(19|20)\d{2}\s*\.\s*\d{1,2}\s*\.(?:\s*\d{1,2}\s*\.?)?")
    for r in res["행정규칙"]:
        if r["판정"] != "STALE" or not r.get("현행발령번호"):
            continue
        old_no, new_no = r["인용고시번호"], r["현행발령번호"]
        agency = r.get("소관부처") or ""
        cur_name = r.get("현행명", "")
        d = r.get("현행발령일", "")
        new_date = f"{d[:4]}.{int(d[4:6])}.{int(d[6:8])}." if len(d) == 8 else ""
        for name, v in cites.items():
            if v.get("고시번호") != old_no:
                continue
            # 이름-번호 불일치 가드 — 인용문에 든 규칙명이 현행명과 안 겹치면 골든의 인용 오기 의심.
            # (실례: `자연재해위험개선지구 관리지침(제2023-63호)` — 2023-63 은 실무지침 번호)
            bare = re.sub(r"[(\[（].*", "", name).strip()
            bare = re.sub(r"[가-힣]+(부|처|청|위원회)?\s?고시.*", "", bare).strip(" ,.·")
            if len(bare) >= 6 and cur_name and norm(bare)[:6] not in norm(cur_name):
                suspects.append({"인용": name, "인용번호": old_no, "그 번호의 현행": cur_name,
                                 "parts": v["parts"]})
                continue
            new = name.replace(f"제{old_no}호", f"제{new_no}호")
            for old_min, new_min in MINISTRY.items():
                # 현행 소관부처가 개편명일 때만 부처명 교체 (행안부 고시 등은 건드리지 않는다)
                if new_min in agency:
                    new = new.replace(f"{old_min}고시", f"{new_min}고시").replace(f"{old_min} 고시", f"{new_min} 고시")
            if new_date:
                new = DATE.sub(new_date, new)                 # 병기된 발령일도 현행으로
            if new != name:
                pairs.append({"old": name, "new": new, "근거": f"STALE {old_no}→{new_no}",
                              "현행명": cur_name, "parts": v["parts"]})

    # ── 구명칭 법령: 낫표 전체 교체 (인용이 「명칭」 꼴이므로 낫표째 치환해 부분 일치를 막는다)
    for old, new in RENAMED.items():
        hit = cites.get(old) or cites.get(old.replace("·", "·"))
        if hit:
            pairs.append({"old": f"「{old}」", "new": f"「{new}」", "근거": "법령 개명",
                          "현행명": new, "parts": hit["parts"]})

    # 안전 검사 — old 가 다른 old 의 부분 문자열이면 순서 함정 → 길이 내림차순 정렬로 봉인
    pairs.sort(key=lambda p: -len(p["old"]))
    dst = ROOT / "catalog" / "review" / "law_update_map.json"
    dst.write_text(json.dumps({"생성일": res["생성일"], "원칙": "길이 내림차순 적용·전체 문자열만",
                               "치환": pairs, "인용오류의심": suspects},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    parts = {p for e in pairs for p in e["parts"]}
    print(f"치환쌍 {len(pairs)}건 · 대상 파트 {len(parts)}곳 · 인용오류 의심 {len(suspects)}건 → {dst.relative_to(ROOT)}")
    for s in suspects:
        print(f"  ⚠️ 인용오류 의심: {s['인용'][:50]} — 그 번호의 현행은 [{s['그 번호의 현행'][:30]}]")
    for e in pairs[:40]:
        print(f"  [{e['근거']}] {e['old'][:44]} → {e['new'][:44]}")


if __name__ == "__main__":
    main()

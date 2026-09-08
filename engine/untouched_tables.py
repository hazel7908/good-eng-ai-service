"""되먹임 산출물의 **손대지 않은 표** — 비우기 앵커 누락 후보 (캡션으로 분류).

되먹임은 표 유출 검사를 건너뛴다. 앵커가 없어 기준 사업 값이 통째로 남은 표는
게이트 어디에도 안 걸린다 — 다른 사업 생성에서만 드러난다.
"""
import re, sys, glob, os, zipfile
sys.path.insert(0, "engine")
from hwp_util import console_utf8
import score_regional as S
console_utf8()
NUM = re.compile(r"\d")
고정 = ("법", "기준", "규정", "별표", "고시", "산정식", "공식", "분류", "지침", "등급표",
        "가중치", "원단위표", "환산", "계수표", "예시")
고유 = ("현황", "조사", "측정", "발생", "계획", "예측", "결과", "일람", "내역", "명세",
        "지점", "저감", "투입", "산정", "분포", "목록", "이용")
CASES = {"env-impact": "횡성_벨라스톤CC", "strategic-env": "충북_수산천고명천"}
PARTS = {"env-impact": ("landscape regional-overview resource-cycle greenhouse-gas flora-fauna "
                        "water-quality scoping strategic-reflection appendix-1 appendix-2 "
                        "topo-geology soil").split(),
         "strategic-env": "topo-geology appendix flora-fauna scoping socioeconomic landscape "
                          "regional-overview".split()}
print("# 되먹임에서 손대지 않은 표 — 비우기 앵커 누락 후보 (2026-09-07)\n")
print("`[확인 필요]` 가 한 칸도 없고 숫자를 든 표. 되먹임은 표 유출 검사를 건너뛰므로")
print("**게이트 어디에도 안 걸린다** — 다른 사업 생성에서만 드러난다.\n")
print("⚠️ = 캡션이 사업 고유(현황·조사·측정·발생·계획…) → 앵커 필요 후보")
print("🔒 = 법령·기준·규정·산정식 → 고정이 정상 · ? = 캡션으로 판단 불가\n")
tot = {"⚠️": 0, "🔒": 0, "?": 0}
lines = []
for cat, parts in PARTS.items():
    for part in parts:
        f = f"cases/{cat}/{CASES[cat]}/{part}/output.hwpx"
        if not os.path.exists(f):
            continue
        z = zipfile.ZipFile(f)
        rows = []
        for n in sorted(x for x in z.namelist() if re.match(r"Contents/section\d+\.xml$", x)):
            xml = re.sub(r"<hp:(header|footer)[ >].*?</hp:\1>", " ",
                         z.read(n).decode("utf-8"), flags=re.S)
            pos = 0
            for a, b in S._top_tables(xml):
                cells = [c for c in S._text(xml[a:b]) if c]
                caps = [c for c in S._text(xml[pos:a]) if c]
                pos = b
                if not cells:
                    continue
                blob = " ".join(cells)
                if "[확인 필요]" in blob or not NUM.search(blob):
                    continue
                cap = next((c for c in reversed(caps) if len(c) >= 4
                            and not c.startswith(("자)", "주)"))), "")
                mark = "🔒" if any(k in cap for k in 고정) else (
                       "⚠️" if any(k in cap for k in 고유) else "?")
                tot[mark] += 1
                rows.append((mark, cap[:70] or blob[:70]))
        if rows:
            w = sum(1 for m, _ in rows if m == "⚠️")
            lines.append(f"\n## {cat}/{part} — {len(rows)}표 (⚠️ {w})")
            LIM = 10 ** 6 if "--all" in sys.argv else 12
            for m, c in [r for r in rows if r[0] == "⚠️"][:LIM]:
                lines.append(f"- {m} {c}")
             # 나머지는 수만 적는다
            etc = len(rows) - min(w, LIM)
            if etc:
                lines.append(f"- (그 외 {etc}표 — 🔒/? 포함)")
print("\n".join(lines))
print(f"\n합계 {sum(tot.values())}표 — ⚠️ {tot['⚠️']} · 🔒 {tot['🔒']} · ? {tot['?']}")

"""손대지 않은 사업 고유 표 → 앵커 후보. 캡션과 머리 셀을 **같은 표 범위**에서 읽는다.

⚠️ 색인으로 베이스 표와 짝지으면 안 된다 — 중첩표 때문에 산출물 145 : 베이스 191 로
   개수가 달라 엉뚱한 표의 머리가 붙는다 (실측 2026-09-08).
"""
import re, sys, zipfile
sys.path.insert(0, "engine")
from hwp_util import console_utf8
import score_regional as S
console_utf8()
NUM = re.compile(r"\d")
고정 = ("법", "기준", "규정", "별표", "고시", "산정식", "공식", "분류", "지침", "등급표",
        "가중치", "원단위표", "환산", "계수표", "예시")
고유 = ("현황", "조사", "측정", "발생", "계획", "예측", "결과", "일람", "내역", "명세",
        "지점", "저감", "투입", "산정", "분포", "목록", "이용")
cat, part = sys.argv[1], sys.argv[2]
case = {"env-impact": "횡성_벨라스톤CC", "strategic-env": "충북_수산천고명천"}[cat]
z = zipfile.ZipFile(f"cases/{cat}/{case}/{part}/output.hwpx")
n_all = n_hit = 0
for n in sorted(x for x in z.namelist() if re.match(r"Contents/section\d+\.xml$", x)):
    xml = re.sub(r"<hp:(header|footer)[ >].*?</hp:\1>", " ", z.read(n).decode("utf-8"), flags=re.S)
    pos = 0
    for a, b in S._top_tables(xml):
        cells = [c for c in S._text(xml[a:b]) if c]
        caps = [c for c in S._text(xml[pos:a]) if c]
        pos = b
        if not cells:
            continue
        n_all += 1
        blob = " ".join(cells)
        cap = next((c for c in reversed(caps) if len(c) >= 4
                    and not c.startswith(("자)", "주)"))), "")
        if "[확인 필요]" in blob or not NUM.search(blob):
            continue
        if any(k in cap for k in 고정) or not any(k in cap for k in 고유):
            continue
        n_hit += 1
        print(f"[{n_hit:2}] {cap[:44]}")
        print(f"     머리: {' | '.join(cells[:10])[:88]}")
print(f"\n표 {n_all} · 사업 고유 미처리 {n_hit}")

"""베이스에 남은 기준 사업 지명·수치를 표 안/밖으로 갈라 센다.

표 안 = 핸들러 비우기 앵커 몫 · 표 밖 = spec 토큰화 몫.
"""
import re, sys, zipfile, glob, os, pathlib
sys.path.insert(0, "engine")
from hwp_util import console_utf8
import score_regional as S
console_utf8()
CFG = {"env-impact": ("횡성", ("횡성", "벨라스톤", "서원면", "옥계", "우천면", "공근면", "둔내")),
       "strategic-env": ("제천", ("제천", "청풍", "수산면", "덕산면", "금성면", "한수면",
                                 "수산천", "고명천"))}
out = []
for cat, (label, KEYS) in CFG.items():
    for f in sorted(glob.glob(f"templates/{cat}/*.hwpx")):
        part = os.path.basename(f)[:-5]
        z = zipfile.ZipFile(f)
        for n in sorted(x for x in z.namelist()
                        if re.match(r"Contents/section\d+\.xml$", x)):
            xml = re.sub(r"<hp:(header|footer)[ >].*?</hp:\1>", " ",
                         z.read(n).decode("utf-8"), flags=re.S)
            spans = list(S._top_tables(xml))
            pos, outside = 0, []
            for a, b in spans:
                outside.append(xml[pos:a]); pos = b
            outside.append(xml[pos:])
            texts = [t for chunk in outside for t in S._text(chunk) if t]
            for t in texts:
                if any(k in t for k in KEYS) and "{{" not in t:
                    out.append((cat, part, t.strip()[:88]))
print("# 베이스 표 **밖** 기준 사업 지명 잔존 — spec 토큰화 몫\n")
cur = None
for cat, part, t in out:
    if (cat, part) != cur:
        cur = (cat, part); print(f"\n## {cat}/{part}")
    print(f"- {t}")
print(f"\n합계 {len(out)}줄")

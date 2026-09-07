"""⑤ 골든 재수확 — 번호 매칭 + **지명 검사** 통과분만 쓴다."""
import sys, os, glob, pathlib, subprocess
sys.path.insert(0, "catalog"); sys.path.insert(0, "engine")
from synology_filestation import connect
from hwp_util import console_utf8
from extract import extract
console_utf8()
SHARE = "/backupenv"
CODE = "환25-05"; CASE = "천안_화덕리"; 시군 = "천안"
# 우선순위: W3 6파트 + 0840 (B 승급 채점 기준)
WANT = {"site-suitability": "0600", "flora-fauna": "0711", "topo-geology": "0725",
        "landscape": "0728", "appendix": "0800", "water-total-load": "0840"}
fs = connect()
roots = [f"/0. 평가서/환경/{y}" for y in ("2024", "2025", "2026")]
root = None
for r in roots:
    try:
        for it in fs.list_folder(SHARE + r):
            if it["isdir"] and it["name"].startswith(CODE):
                root = it["path"]
    except Exception:
        pass
print("  사업 폴더:", root)

def walk(p, d=0, out=None):
    if out is None: out = []
    if d > 3: return out
    try: items = fs.list_folder(p)
    except Exception: return out
    for it in items:
        if it["isdir"]: walk(it["path"], d + 1, out)
        else: out.append((it["name"], (it.get("additional") or {}).get("size") or 0, it["path"]))
    return out

files = walk(root)
print("  파일 %d개" % len(files))
D = pathlib.Path("raw_data/nas/small-env") / CASE
D.mkdir(parents=True, exist_ok=True)
got = []
for slug, num in WANT.items():
    cand = [f for f in files if f[0].lower().endswith(".hwp") and "(본안)" in f[0]
            and (f" {num} " in f[0] or f" {num}" in f[0])]
    # ⚠️ 같은 파트가 여러 판으로 있다 — `(마킹)`(검토 표시본)은 버리고 `(완)` 을 고른다.
    #    둘 다 아니면 이름이 긴 쪽(쪽수 표기가 붙은 최종본)을 쓴다.
    cand = [c for c in cand if "(마킹)" not in c[0]] or cand
    완 = [c for c in cand if "(완)" in c[0]]
    if 완: cand = 완
    if len(cand) > 1: cand = [sorted(cand, key=lambda c: -len(c[0]))[0]]
    if not cand:
        print("  ❌ %-18s 후보 없음" % slug); continue
    name, size, path = cand[0]
    local = D / name
    if not local.exists() or (size and local.stat().st_size != size):
        fs.download(path, str(D))
    got.append((slug, local, name))
    print("  ⬇ %-18s %s" % (slug, name[:52]))
# 인풋 xlsx (0840 계산)
xl = [f for f in files if f[0].endswith(".xlsx") and "총량계산" in f[0]]
if xl:
    inp = pathlib.Path("cases/small-env") / CASE / "input"
    inp.mkdir(parents=True, exist_ok=True)
    fs.download(xl[0][2], str(inp))
    print("  ⬇ 인풋 %s → %s" % (xl[0][0][:40], inp))
else:
    print("  ⚠️ 총량계산.xlsx 못 찾음")
# 추출 → 지명 검사 → 통과분만 기록
outdir = pathlib.Path("golden/small-env") / CASE
tmp = pathlib.Path("raw_data/_harvest_tmp"); tmp.mkdir(exist_ok=True)
for slug, local, name in got:
    try: t = extract(str(local))
    except Exception as e:
        print("  ❌ 추출 실패 %s: %s" % (slug, type(e).__name__)); continue
    f = tmp / f"{slug}.txt"; f.write_text(t, encoding="utf-8")
    r = subprocess.run([sys.executable, "catalog/check_case_locality.py", 시군, str(f)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = "✗" not in (r.stdout or "")
    print("  %s %-18s %5d줄  %s" % ("✅" if ok else "⛔", slug, t.count(chr(10)),
                                    (r.stdout or "").strip().splitlines()[-1][:60] if r.stdout else ""))
    if ok:
        (outdir / f"{slug}.txt").write_text(t, encoding="utf-8")

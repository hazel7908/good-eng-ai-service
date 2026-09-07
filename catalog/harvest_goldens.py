#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소환 골든 재수확 — NAS 원본 → txt. **세 겹 검사를 통과한 것만** 덮어쓴다.

두 번 데었다:
  ① 청양 0200 은 파일명이 `(완)` 인데 내용이 강릉시였다
  ② 천안 폴더(환25-05) 안에 **여주 광대리 사업 복사본**이 섞여 재추출을 오염시켰다.
     줄 유사도 57%로 가드를 통과했다 — 이 부류 문서는 골격이 같아 유사도만으로는 못 막는다.

그래서 세 겹이다:
  1. **파트 번호** — 파일명의 `(본안) NNNN` (수리수문 0724 가 끼면 뒤가 밀리므로 대체 번호도 본다)
  2. **판 선택** — `(마킹)` 제외 → `(완)` 우선 → 남으면 이름이 긴 쪽(쪽수 표기가 붙은 최종본)
  3. **지명 검사** — `check_case_locality.py` 로 본문 최빈 시군이 그 사업 것인지
  4. 옛 골든이 있으면 **파트 동일성** — 첫 절 제목이 같은지 (다른 파트로 갈아치우는 사고 방지)

사용: python catalog/harvest_goldens.py [사업명 …]   (생략하면 전부)
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from synology_filestation import connect          # noqa: E402
from hwp_util import console_utf8                 # noqa: E402
from extract import extract                       # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHARE = "/backupenv"
# 사업 → (NAS 환번호, 지명 검사에 쓸 시군)
CASES = {
    "괴산_금신리": ("환25-18", "괴산"), "괴산_후평리": ("환26-14", "괴산"),
    "옥천_사양리": ("환24-25", "옥천"), "천안_화덕리": ("환25-05", "천안"),
    "청주_호명리": ("환24-01", "청주"), "충주_율능리": ("환25-19", "충주"),
    "평창_수청리": ("환24-17", "평창"),
}
# 슬러그 → 파트 번호. ⚠️ 수리수문(0724)이 끼는 사업은 뒤가 한 칸씩 밀린다 → 대체 번호를 뒤에 둔다.
NUM = {
    "project-overview": ["0100"], "regional-overview": ["0200"], "target-area": ["0300"],
    "surrounding-land-use": ["0400"], "env-status": ["0500"], "site-suitability": ["0600"],
    "flora-fauna": ["0711"], "climate": ["0721"], "air-quality": ["0722"],
    "water-quality": ["0723"], "land-use": ["0724", "0725"],
    "topo-geology": ["0725", "0726"], "resource-cycle": ["0726", "0727"],
    "noise-vib": ["0727", "0728"], "landscape": ["0728", "0729"],
    "appendix": ["0800"], "water-total-load": ["0840"],
}


def rank(cands):
    """판 우선순위 — `(마킹)` 제외 → `(완)` 우선 → 이름이 긴 쪽.

    ⚠️ **하나만 골라선 안 된다.** 충주 0726 은 이 규칙이 고른 `…255-262.hwp` 가
    내용상 **괴산 사업 복사본**이었고, 밀린 `(지장물)` 이 진짜 충주였다.
    → 순위대로 시도하고 **지명 검사를 통과하는 첫 후보**를 쓴다.
    """
    c = [x for x in cands if "(마킹)" not in x[0]] or cands
    완 = [x for x in c if "(완)" in x[0]]
    나머지 = [x for x in c if x not in 완]
    return (sorted(완, key=lambda x: -len(x[0]))
            + sorted(나머지, key=lambda x: -len(x[0])))


def overlap(old, new):
    """옛 골든의 줄이 새 텍스트에 얼마나 남아 있나 — 파트 동일성 판정.

    ⚠️ **첫 줄 제목 비교는 오탐투성이다.** 옛 골든은 장 제목 없이 시작한 것이 많고
    (`의개요` ↔ `제1장 사업의 개요`), 추출기 수정으로 앞 글자가 되살아난 것도 있다.
    괴산 17파트 중 8건이 그렇게 잘못 걸렸다 — 전부 같은 파트였다.
    ⚠️ 반대로 겹침만으로도 안 된다 — 여주 복사본이 57%로 통과했다. **지명 검사와 함께** 쓴다.
    """
    o = [l.strip() for l in old.splitlines() if len(l.strip()) > 12]
    if not o:
        return 1.0
    n = set(l.strip() for l in new.splitlines())
    return sum(1 for l in o if l in n) / len(o)


def walk(fs, p, d=0, out=None):
    if out is None:
        out = []
    if d > 3:
        return out
    try:
        items = fs.list_folder(p)
    except Exception:                                        # noqa: BLE001
        return out
    for it in items:
        if it["isdir"]:
            walk(fs, it["path"], d + 1, out)
        else:
            out.append((it["name"], (it.get("additional") or {}).get("size") or 0, it["path"]))
    return out


def main():
    console_utf8()
    want = sys.argv[1:] or list(CASES)
    fs = connect()
    folders = {}
    for y in ("2023", "2024", "2025", "2026"):
        try:
            for it in fs.list_folder(f"{SHARE}/0. 평가서/환경/{y}"):
                if it["isdir"]:
                    folders[it["name"]] = it["path"]
        except Exception:                                    # noqa: BLE001
            pass
    ok = skip = fail = 0
    for case in want:
        code, 시군 = CASES[case]
        root = next((v for k, v in folders.items() if k.startswith(code)), None)
        if not root:
            print(f"❌ {case}: NAS 폴더 없음 ({code})")
            continue
        files = [f for f in walk(fs, root)
                 if f[0].lower().endswith(".hwp") and "(본안)" in f[0]]
        gdir = ROOT / "golden" / "small-env" / case
        rdir = ROOT / "raw_data" / "nas" / "small-env" / case
        rdir.mkdir(parents=True, exist_ok=True)
        tmp = ROOT / "raw_data" / "_harvest_tmp"
        tmp.mkdir(exist_ok=True)
        print(f"\n=== {case}  (파일 {len(files)})")
        for slug, nums in NUM.items():
            cands = []
            for n in nums:
                cands = [f for f in files if f" {n} " in f[0] or f" {n}" in f[0]]
                if cands:
                    break
            t = name = None
            거른것 = []
            for cand in rank(cands):
                cname, size, path = cand
                local = rdir / cname
                if not local.exists() or (size and local.stat().st_size != size):
                    fs.download(path, str(rdir))
                try:
                    cand_t = extract(str(local))
                except Exception as e:                       # noqa: BLE001
                    거른것.append(f"{cname[:30]}(추출실패 {type(e).__name__})")
                    continue
                f = tmp / f"{case}_{slug}.txt"
                f.write_text(cand_t, encoding="utf-8")
                r = subprocess.run([sys.executable, str(ROOT / "catalog" / "check_case_locality.py"),
                                    시군, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
                if "✗" in (r.stdout or ""):
                    거른것.append(f"{cname[:30]}(지명✗)")
                    continue
                t, name = cand_t, cname
                break
            if t is None:
                print(f"  ⛔ {slug:20} 지명 검사 통과 후보 없음 — {' · '.join(거른것)[:70]}")
                skip += 1
                continue
            if 거른것:
                print(f"     (앞 후보 거름: {' · '.join(거른것)[:64]})")
            dst = gdir / f"{slug}.txt"
            ov = None
            if dst.exists():
                ov = overlap(dst.read_text(encoding="utf-8"), t)
                if ov < 0.40:
                    print(f"  ⛔ {slug:20} 파트 불일치 의심 — 옛 줄 겹침 {ov:.0%}  {name[:36]}")
                    skip += 1
                    continue
            gdir.mkdir(parents=True, exist_ok=True)
            before = dst.read_text(encoding="utf-8").count("\n") if dst.exists() else 0
            dst.write_text(t, encoding="utf-8")
            ok += 1
            겹침 = f" 겹침 {ov:.0%}" if ov is not None else " 신규"
            print(f"  ✅ {slug:20} {before:>6,} → {t.count(chr(10)):>6,}줄{겹침}  {name[:34]}")
    print(f"\n갱신 {ok} · 건너뜀 {skip} · 실패 {fail}")


if __name__ == "__main__":
    main()

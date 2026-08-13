#!/usr/bin/env python3
"""
NAS 전수 크롤 드라이버 — 최상위 폴더별 분할 + 병렬 + 재개 가능.

왜 분할하나 (2026-08-13 실측):
  전수는 폴더 7.4만+(기타자료 심층 6.7만+ 별도)라 통짜 크롤은 끝나기 전엔
  아무것도 저장되지 않고 진행도 안 보인다. 최상위 폴더별로 쪼개면
  ① 폴더 하나 끝날 때마다 part JSON 이 떨어지고 (중단돼도 보존)
  ② 이미 받은 폴더는 건너뛰어 재개 가능하며
  ③ 진행 로그가 실시간으로 보인다.

사용 (재조사 절차 전체는 .claude/skills/nas-survey):
    python3 catalog/crawl_full.py                      # 전수 → catalog/data/nas_index_new.json.gz
    python3 catalog/crawl_full.py --exclude "0. 기타자료"   # 특정 최상위 폴더 제외
    python3 catalog/crawl_full.py --shallow "0. 기타자료=2" # 특정 폴더만 깊이 제한(요약)

part JSON 은 raw_data/nas_crawl/{날짜}/ (git 제외)에 쌓인다. 같은 날 재실행하면 이어받는다.
⚠️ 스냅샷끼리 비교(nas_diff)할 때 깊이 조건이 다르면 diff 가 왜곡된다 — --shallow 를 쓴
스냅샷은 그 폴더 안 diff 를 믿지 말 것.
"""

import argparse
import datetime
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from synology_filestation import connect, walk_tree_parallel

ROOT = Path(__file__).resolve().parent.parent
SHARE = "/backupenv"
SKIP_ALWAYS = {"#recycle", "#snapshot"}


def main():
    ap = argparse.ArgumentParser(description="NAS 전수 크롤 (분할·병렬·재개)")
    ap.add_argument("--out", default=str(ROOT / "catalog/data/nas_index_new.json.gz"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--exclude", action="append", default=[], help="제외할 최상위 폴더")
    ap.add_argument("--shallow", action="append", default=[],
                    help="'폴더명=깊이' — 해당 최상위 폴더만 요약 크롤")
    a = ap.parse_args()
    shallow = dict(s.split("=", 1) for s in a.shallow)

    date = datetime.date.today().isoformat()
    parts_dir = ROOT / "raw_data/nas_crawl" / date
    parts_dir.mkdir(parents=True, exist_ok=True)

    fs = connect()
    try:
        top = walk_tree_parallel(fs, SHARE, depth=1, workers=4)
        names = [n for n in top["dirs"] if n not in SKIP_ALWAYS and n not in a.exclude]
        print(f"[*] 최상위 {len(names)}개 폴더 (제외: {sorted(SKIP_ALWAYS | set(a.exclude))})")

        root = {"path": SHARE, "files": top.get("files", []), "dirs": {}}
        for i, name in enumerate(names, 1):
            part = parts_dir / f"{name.replace('/', '_')}.json"
            if part.exists():
                print(f"[{i}/{len(names)}] {name} — 저장본 재사용")
                root["dirs"][name] = json.load(open(part, encoding="utf-8"))
                continue
            depth = int(shallow.get(name, 99))
            print(f"[{i}/{len(names)}] {name} 크롤 중 (depth={depth})...")
            node = walk_tree_parallel(fs, f"{SHARE}/{name}", depth=depth, workers=a.workers)
            json.dump(node, open(part, "w", encoding="utf-8"), ensure_ascii=False)
            root["dirs"][name] = node
    finally:
        fs.logout()

    root["_meta"] = {"crawled": date, "workers": a.workers,
                     "exclude": a.exclude, "shallow": shallow}
    with gzip.open(a.out, "wt", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False)
    print(f"[✓] 스냅샷 저장: {a.out}")
    print(f"    다음: python3 catalog/nas_diff.py {a.out}   (검토 후 --promote)")


if __name__ == "__main__":
    main()

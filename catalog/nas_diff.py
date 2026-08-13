#!/usr/bin/env python3
"""
NAS 스냅샷 diff — 두 인덱스(JSON)를 비교해 추가/삭제/변경 파일을 보고한다.

왜 있나:
  NAS 가 지속 업데이트되는 동안(2026-08 말까지 예고) 우리 자산 —
  catalog/data/nas_catalog.json(정본 카탈로그) · docs/naming.md(파트 번호 규칙) ·
  CLAUDE.md 자료 소재 표 — 이 낡는 것을 감지하기 위한 도구.
  스냅샷은 `synology_filestation.py tree "/backupenv" --depth 99 --json ...` 으로 뜬다.

운영 방침 (2026-08-13 갱신): NAS 는 8월 말까지 지속 업데이트 예정. 재조사 요청이 오면
  **전체 트리를 다시 크롤**한다 (부분 크롤로 줄이지 않는다 — diff 가 전체에서 일어난다).
  QuickConnect 릴레이 경유뿐이라(직결 포트 닫힘 확인) 느린 것은 감수하되,
  병렬 크롤(--workers 8, 기본값)로 왕복 지연을 숨긴다.

  ⚠️ 두 스냅샷의 **크롤 깊이가 다르면 diff 가 왜곡된다** — 7/21 인덱스가 depth 3 제한이라
  "전부 신규"로 잘못 잡힌 전례 (2026-08-13 발견, truncated 4,631 노드). 항상 전수(depth 99)
  로 뜨고, 부분 크롤 스냅샷과는 비교하지 말 것. 규모 참고: 전수 = 폴더 7.4만+(기타자료 심층
  6.7만+ 별도) · 파일 73만+, 병렬 8 로 30분~1시간대. 스냅샷은 70MB+ 라 .gz 로 보관한다.
  크롤이 길면 최상위 폴더별 분할(재개 가능)이 안전하다 — scratchpad/crawl_parts.sh 패턴.

사용:
    # 1) 새 스냅샷 크롤링 (병렬이 기본. --workers 1 로 순차 강제 가능)
    python3 catalog/synology_filestation.py tree "/backupenv" --depth 99 \
        --json catalog/data/nas_index_new.json
    # 2) 비교 (구스냅샷은 기본값 catalog/data/nas_index.json)
    python3 catalog/nas_diff.py catalog/data/nas_index_new.json
    # 3) 검토 후 새 스냅샷으로 교체(--promote)하면 다음 비교의 기준이 된다
    python3 catalog/nas_diff.py catalog/data/nas_index_new.json --promote

출력: 콘솔 요약 + catalog/review/nas_diff_{날짜}.md (전체 목록)
보고서류(.hwp/.hwpx) 변경은 ★ 로 표시한다 — 카탈로그·golden 영향 후보.
"""

import argparse
import datetime
import gzip
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD_DEFAULT = ROOT / "catalog/data/nas_index.json.gz"
REPORT_EXT = (".hwp", ".hwpx")


def load_index(path):
    """스냅샷 로드 — .gz 투명 지원 (전수 스냅샷이 70MB+ 라 압축 보관한다)."""
    p = str(path)
    opener = gzip.open if p.endswith(".gz") else open
    with opener(p, "rt", encoding="utf-8") as f:
        return json.load(f)

# 파트별 보고서 파일명 패턴 — naming.md 의 번호 체계와 연동 (0722 대기질, 0727 소음진동 등)
PART_HINTS = ("0722", "0727", "0728", "0724", "0200", "본안")


def flatten(node, path=""):
    """인덱스 트리 → {파일경로: (size, mtime)}"""
    out = {}
    p = path or node.get("path", "")
    for f in node.get("files", []):
        out[f"{p}/{f['name']}"] = (f.get("size"), f.get("mtime"))
    for name, ch in node.get("dirs", {}).items():
        out.update(flatten(ch, f"{p}/{name}"))
    return out


def fmt_ts(ts):
    if not ts:
        return "?"
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def mark(path):
    star = "★" if path.lower().endswith(REPORT_EXT) else ""
    hint = "†" if any(h in path for h in PART_HINTS) else ""
    return star + hint


def main():
    ap = argparse.ArgumentParser(description="NAS 스냅샷 비교")
    ap.add_argument("new", help="새 스냅샷 JSON")
    ap.add_argument("--old", default=str(OLD_DEFAULT), help="기준 스냅샷 (기본: 현행 인덱스)")
    ap.add_argument("--promote", action="store_true",
                    help="비교 후 새 스냅샷을 현행 인덱스로 교체")
    a = ap.parse_args()

    old = flatten(load_index(a.old))
    new = flatten(load_index(a.new))

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(p for p in set(old) & set(new) if old[p] != new[p])

    today = datetime.date.today().isoformat()
    lines = [f"# NAS 변경 감지 — {today}", "",
             f"기준: `{a.old}` → 신규: `{a.new}`",
             f"**추가 {len(added)} · 삭제 {len(removed)} · 변경 {len(changed)}** "
             f"(★=보고서 hwp/hwpx · †=파트 번호 파일명)", ""]
    for title, items, detail in (("추가", added, new), ("삭제", removed, old),
                                 ("변경", changed, new)):
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        for p in items:
            sz, mt = detail[p]
            lines.append(f"- {mark(p)} `{p}` ({fmt_ts(mt)})")
        lines.append("")

    out = ROOT / f"catalog/review/nas_diff_{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    stars = [p for p in added + changed if p.lower().endswith(REPORT_EXT)]
    print(f"추가 {len(added)} · 삭제 {len(removed)} · 변경 {len(changed)}"
          f" — 보고서류(★) {len(stars)}건")
    for p in stars[:20]:
        print(f"  ★ {p}")
    if len(stars) > 20:
        print(f"  ... 외 {len(stars) - 20}건 (전체: {out.name})")
    print(f"[✓] 상세: {out}")

    if a.promote:
        shutil.copy(a.new, a.old)
        print(f"[✓] 현행 인덱스 교체: {a.old}")


if __name__ == "__main__":
    main()

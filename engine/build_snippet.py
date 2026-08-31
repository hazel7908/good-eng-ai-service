#!/usr/bin/env python3
"""
절 조각(snippet) 빌더 — 완성 보고서에서 **한 절만** 오려내 조각 HWPX 로 만든다.

  완성 보고서.hwp  →  templates/{카테고리}/{파트}.snippets/{조건}.hwpx

베이스 문서(빈칸)로는 표현할 수 없는 것이 있다. 사업 조건에 따라 **절이 통째로
더 들어가는** 경우다 — 예: ②까지 해도 목표를 못 맞추면 `전파경로 차단대책(가설방음판넬)`
절이 붙는다 (rule §3-3-③). 수식 개체·표·삽도가 들어 있어 코드로 만들 수 없다.

**조각 이름은 사업이 아니라 조건으로 붙인다.** 같은 조건이면 어느 사업에서 뽑아도 되고,
다른 사업에 그대로 재사용된다.

⚠️ Windows + 한글 프로그램 전용.
⚠️ 원본을 직접 열지 않는다 — 복사본을 열어 바깥을 지우고 저장한다.

사용:
    python engine/build_snippet.py small-env noise-vib 저감3_방음판넬 \
        --src "raw_data/snippet_src/(본안) 0727 소음진동(완) 257-276.hwp"
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hwp_util import console_utf8, open_hwp, quit_hwp   # noqa: E402  (경로 삽입 뒤라야 한다)

ROOT = Path(__file__).parent.parent

# 조건 → (시작 앵커, 끝 앵커). 끝 앵커 **직전**까지 남는다.
SPECS = {
    "저감3_방음판넬": {
        "start": "3) 지형에 의한 감쇠효과",
        "end": "5) 최종 저감대책 수립 후, 예측소음도",
        "설명": "rule §3-3-③ — ②까지 해도 목표를 못 맞추는 지점이 있을 때 붙는 절. "
                "지형 감쇠 + 회절감쇠치·투과손실치·삽입손실치 산정 + 설치 제원·위치도",
    },
}


def keep_only(hwp, start_anchor, end_anchor):
    """start_anchor 문단부터 end_anchor 문단 직전까지만 남기고 나머지를 지운다."""
    from hwp_util import find_fwd

    # ── 뒤쪽 먼저 ── 앞을 먼저 지우면 문단 번호가 밀린다
    hwp.MovePos(2)
    if not find_fwd(hwp, end_anchor):
        sys.exit(f"ERROR: 끝 앵커 '{end_anchor}' 못 찾음")
    hwp.HAction.Run("MoveParaBegin")
    s = hwp.GetPos()
    hwp.MovePos(3)                      # 문서 끝
    e = hwp.GetPos()
    hwp.SelectText(s[1], s[2], e[1], e[2])
    hwp.HAction.Run("Delete")

    # ── 앞쪽 ──
    hwp.MovePos(2)
    a = hwp.GetPos()
    if not find_fwd(hwp, start_anchor):
        sys.exit(f"ERROR: 시작 앵커 '{start_anchor}' 못 찾음")
    hwp.HAction.Run("MoveParaBegin")
    b = hwp.GetPos()
    hwp.SelectText(a[1], a[2], b[1], b[2])
    hwp.HAction.Run("Delete")


def main():
    console_utf8()
    ap = argparse.ArgumentParser(description="절 조각 빌더")
    ap.add_argument("category")
    ap.add_argument("part")
    ap.add_argument("name", help="조건 이름 (SPECS 의 키)")
    ap.add_argument("--src", required=True, help="원본 완성 보고서 (.hwp/.hwpx)")
    a = ap.parse_args()

    if a.name not in SPECS:
        sys.exit(f"ERROR: 조건 '{a.name}' 명세 없음. 지원: {list(SPECS)}")
    spec = SPECS[a.name]

    src = Path(a.src)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        sys.exit(f"ERROR: {src} 없음")

    dst = ROOT / "templates" / a.category / f"{a.part}.snippets" / f"{a.name}.hwpx"
    dst.parent.mkdir(parents=True, exist_ok=True)
    work = dst.with_suffix(".work" + src.suffix)
    shutil.copy(src, work)

    print(f"조건 : {a.name}\n설명 : {spec['설명']}")
    print(f"범위 : '{spec['start']}'  ~  '{spec['end']}' 직전")

    import win32com.client
    hwp = open_hwp(work)

    print("[1/2] 절 바깥 삭제...")
    keep_only(hwp, spec["start"], spec["end"])

    print("[2/2] 저장...")
    if dst.exists():
        dst.unlink()
    hwp.SaveAs(str(dst), "HWPX")
    quit_hwp(hwp)          # 프로세스가 실제로 죽을 때까지 대기
    work.unlink(missing_ok=True)

    print(f"\n완료: {dst} ({dst.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

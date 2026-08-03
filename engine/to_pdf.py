#!/usr/bin/env python3
"""
HWPX → PDF 변환. **육안 확인을 자동화하기 위한 것**이다.

지금까지 검증은 전부 텍스트 추출로만 했다. 그래서 표 행 수를 늘리거나(5→10행)
절을 통째로 지운 뒤(`delete_range`) **페이지 나눔·표 잘림이 깨졌는지 볼 방법이 없었다.**
PDF 로 바꿔 두면 페이지 단위로 눈으로 확인할 수 있다 (`/validate-report` 6단계).

⚠️ Windows + 한글 프로그램 전용.

사용:
    python engine/to_pdf.py cases/small-env/천안_화덕리/noise-vib/output.hwpx
    python engine/to_pdf.py <hwpx> --out review/천안.pdf
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent


def to_pdf(src: Path, dst: Path):
    import win32com.client

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()

    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False
    hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
    hwp.Open(str(src))

    # 한글의 PDF 저장. 포맷 문자열이 버전마다 다를 수 있어 순서대로 시도한다.
    ok = False
    for fmt in ("PDF", "pdf"):
        try:
            hwp.SaveAs(str(dst), fmt)
            ok = True
            break
        except Exception as e:      # noqa: BLE001 — 어떤 예외든 다음 포맷으로 넘어간다
            print(f"  SaveAs('{fmt}') 실패: {e}")

    hwp.Quit()
    time.sleep(2)

    if not ok or not dst.exists():
        sys.exit("ERROR: PDF 저장 실패. 한글 버전이 PDF 내보내기를 지원하는지 확인할 것")
    return dst


def main():
    ap = argparse.ArgumentParser(description="HWPX → PDF (육안 확인용)")
    ap.add_argument("hwpx")
    ap.add_argument("--out", help="출력 PDF 경로 (기본: 같은 폴더 output.pdf)")
    a = ap.parse_args()

    src = Path(a.hwpx)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        sys.exit(f"ERROR: {src} 없음")

    dst = Path(a.out) if a.out else src.with_suffix(".pdf")
    if not dst.is_absolute():
        dst = ROOT / dst

    print(f"[1/2] 변환: {src.name}")
    to_pdf(src, dst)
    print(f"[2/2] 완료: {dst} ({dst.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

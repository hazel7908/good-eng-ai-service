#!/usr/bin/env python3
"""
HWP/HWPX 텍스트 추출 스크립트

소규모 환경영향평가 보고서(HWP/HWPX)에서 텍스트를 추출합니다.

사용법:
    # 단일 파일 추출
    python engine/extract.py input.hwp
    python engine/extract.py input.hwpx

    # 폴더 내 모든 HWP/HWPX 일괄 추출
    python engine/extract.py ./raw_data/ --output ./extracted_texts/

    # 특정 파일을 지정 경로에 저장
    python engine/extract.py input.hwp --output result.txt

의존성:
    pip install olefile
"""

import argparse
import os
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

try:
    import olefile
except ImportError:
    print("olefile 패키지가 필요합니다: pip install olefile", file=sys.stderr)
    sys.exit(1)


def _sanitize(text: str) -> str:
    """UTF-8 로 못 쓰는 문자를 걷어낸다.

    ⚠️ HWP 본문에 **짝 없는 서로게이트**가 섞여 있는 문서가 있다 — 원주 동식물상(0711,
    73MB)이 그랬다. 그대로 `write_text` 하면 `UnicodeEncodeError` 로 **추출이 통째로
    실패한다** (2026-09-01 실측). 파일 하나가 아니라 그 문서 전체를 잃는다.
    """
    return text.encode("utf-8", "replace").decode("utf-8")


def extract_hwp(filepath: str) -> str:
    """
    HWP (바이너리) 파일에서 텍스트를 추출합니다.

    - olefile로 OLE 스트림 열기
    - FileHeader에서 압축 여부 확인 (offset 36, bit 0)
    - BodyText/Section0~N 스트림을 순회하며 레코드 파싱
    - tag_id 67 (HWPTAG_PARA_TEXT) 레코드에서 UTF-16LE 텍스트 추출
    - 제어문자(0x0000~0x001F) 필터링
    """
    ole = olefile.OleFileIO(filepath)

    # 압축 여부 확인
    header = ole.openstream("FileHeader").read()
    flags = struct.unpack_from("<I", header, 36)[0]
    is_compressed = bool(flags & 1)

    paragraphs = []

    # BodyText/Section0, Section1, ... 순회
    section_idx = 0
    while True:
        stream_name = f"BodyText/Section{section_idx}"
        if not ole.exists(stream_name):
            break

        raw = ole.openstream(stream_name).read()

        if is_compressed:
            try:
                raw = zlib.decompress(raw, -15)
            except zlib.error:
                section_idx += 1
                continue

        # 레코드 단위 파싱
        offset = 0
        while offset < len(raw) - 4:
            header_val = struct.unpack_from("<I", raw, offset)[0]
            tag_id = header_val & 0x3FF
            # level = (header_val >> 10) & 0x3FF
            size = (header_val >> 20) & 0xFFF

            offset += 4

            if size == 0xFFF:
                if offset + 4 > len(raw):
                    break
                size = struct.unpack_from("<I", raw, offset)[0]
                offset += 4

            if offset + size > len(raw):
                break

            # tag_id 67 = HWPTAG_PARA_TEXT
            if tag_id == 67 and size > 0:
                data = raw[offset : offset + size]
                text = _decode_para_text(data)
                if text.strip():
                    paragraphs.append(text.strip())

            offset += size

        section_idx += 1

    ole.close()
    return "\n".join(paragraphs)


def _decode_para_text(data: bytes) -> str:
    """
    HWPTAG_PARA_TEXT 레코드에서 텍스트를 디코딩합니다.
    UTF-16LE 인코딩이며, HWP 제어문자를 필터링합니다.
    """
    chars = []
    i = 0
    while i < len(data) - 1:
        code = struct.unpack_from("<H", data, i)[0]
        i += 2

        # HWP 인라인 제어문자: 확장 제어 (가변 길이)
        if code in (1, 2, 3, 11, 12, 13, 14, 15, 16, 17, 18, 21, 22, 23):
            # 확장 제어문자는 추가 12바이트(6 wchar)를 건너뜀
            i += 12
            continue

        # 일반 제어문자
        if code < 0x0020:
            if code == 0x000A or code == 0x000D:  # 줄바꿈
                chars.append("\n")
            elif code == 0x0009:  # 탭
                chars.append("\t")
            # 나머지 제어문자는 무시
            continue

        chars.append(chr(code))

    return "".join(chars)


def extract_hwpx(filepath: str) -> str:
    """
    HWPX (XML 기반) 파일에서 텍스트를 추출합니다.

    - ZIP으로 해제
    - Contents/section*.xml 파일들을 찾아서 파싱
    - 모든 텍스트 노드를 추출
    """
    paragraphs = []

    with zipfile.ZipFile(filepath, "r") as z:
        # section 파일 찾기
        section_files = sorted(
            [
                name
                for name in z.namelist()
                if "section" in name.lower() and name.endswith(".xml")
            ]
        )

        if not section_files:
            # fallback: Contents/ 아래 모든 xml
            section_files = sorted(
                [
                    name
                    for name in z.namelist()
                    if name.startswith("Contents/") and name.endswith(".xml")
                ]
            )

        for section_file in section_files:
            xml_content = z.read(section_file)
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError:
                continue

            # 🚨 **문단 단위로 잇는다** (2026-09-04). 예전 코드는 모든 요소의 text/tail 을
            #    각각 strip 해 **별도 줄**로 넣었다 — `<hp:t>1차  :  2025.<hp:fwSpace/>06.…</hp:t>`
            #    한 셀이 골든에 세 줄로 갈라졌고, spec 생성기가 이어붙이다 앞자리를 잃었다
            #    (soil 조사시기 `025.06.25` — Windows ㉑ 실측). fwSpace·형광펜 낀 셀 전부가
            #    같은 부류라 근본을 고친다. 아래 규칙:
            #    · 한 `<hp:p>` = 한 줄 (셀 안 문단 포함 — 기존 줄 모양과 동일)
            #    · `fwSpace` → U+2007(고정폭 공백) — 눈에는 공백, **코드로는 구별**된다.
            #      spec 생성기는 이 문자가 든 줄을 replace 로 뚫으면 안 된다(한글 찾기가
            #      일반 공백과 다르게 취급) — **paras 로 라우팅**하는 신호다.
            #    · `tab` → \t · 서식 요소(markpen 등)는 문자 없음 — text/tail 만 잇는다.
            #    · `<hp:p>` 밖 텍스트(수식 `hp:script` 등)는 예전처럼 별도 줄로 보존한다.
            def _local(tag):
                return tag.rsplit("}", 1)[-1]

            in_p = set()

            def _collect(node, parts):
                """문단 안 텍스트를 문서 순서로 잇는다 — **중첩 문단(글상자·셀 안 p)에는
                내려가지 않는다**(자기 차례에 별도 줄). 안 막으면 바깥 p 가 안쪽 p 들을
                통째로 삼켜 같은 문장이 두 번 나온다 (전략 자원순환 폐유저장소 실측)."""
                for ch in node:
                    in_p.add(id(ch))
                    ln = _local(ch.tag)
                    if ln == "p":
                        if ch.tail and ch.tail.strip():
                            parts.append(ch.tail)
                        continue
                    if ln == "fwSpace":
                        parts.append("\u2007")
                    elif ln == "tab":
                        parts.append("\t")
                    if ch.text:
                        parts.append(ch.text)
                    _collect(ch, parts)
                    if ch.tail:
                        parts.append(ch.tail)

            for para in root.iter():
                if _local(para.tag) != "p":
                    continue
                in_p.add(id(para))
                parts = []
                if para.text:
                    parts.append(para.text)
                _collect(para, parts)
                line = "".join(parts).strip()
                if line:
                    paragraphs.append(line)
            # p 에 안 담긴 텍스트 (머리글 밖 수식·개체 설명 등) — 예전 동작 보존
            for elem in root.iter():
                if id(elem) in in_p or _local(elem.tag) == "p":
                    continue
                if elem.text and elem.text.strip():
                    paragraphs.append(elem.text.strip())
                if elem.tail and elem.tail.strip():
                    paragraphs.append(elem.tail.strip())

    return "\n".join(paragraphs)


def extract(filepath: str) -> str:
    """파일 확장자에 따라 적절한 추출 함수를 호출합니다.

    🚨 **`_sanitize` 는 여기서 건다.** 예전엔 CLI 쓰기 지점 두 곳에만 걸려 있어
    `extract()` 를 직접 부르는 코드는 **짝 없는 서로게이트에 그대로 죽었다**
    (수확기가 전략 `08 계획의 적정성` 에서 UnicodeEncodeError — 09-03).
    깨진 문서는 드물지 않으니 **추출 자체가 안전한 문자열을 돌려주게** 한다.
    """
    ext = Path(filepath).suffix.lower()
    if ext == ".hwp":
        return _sanitize(extract_hwp(filepath))
    elif ext == ".hwpx":
        return _sanitize(extract_hwpx(filepath))
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext} (HWP 또는 HWPX만 지원)")


def process_directory(input_dir: str, output_dir: str) -> list[dict]:
    """디렉토리 내 모든 HWP/HWPX 파일을 재귀 탐색하여 추출합니다."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    results = []

    for filepath in sorted(input_path.rglob("*")):
        if filepath.suffix.lower() not in (".hwp", ".hwpx"):
            continue

        # 원본 디렉토리 구조를 유지하며 출력
        rel = filepath.relative_to(input_path)
        out_file = output_path / rel.with_suffix(".txt")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            text = extract(str(filepath))
            out_file.write_text(_sanitize(text), encoding="utf-8")
            results.append(
                {"file": str(rel), "status": "success", "chars": len(text)}
            )
            print(f"  [OK] {rel} → {len(text)}자")
        except Exception as e:
            results.append({"file": str(rel), "status": "error", "error": str(e)})
            print(f"  [ERR] {rel} → {e}", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="HWP/HWPX 파일에서 텍스트를 추출합니다."
    )
    parser.add_argument("input", help="HWP/HWPX 파일 또는 디렉토리 경로")
    parser.add_argument(
        "--output", "-o", help="출력 파일 또는 디렉토리 경로 (미지정 시 stdout)"
    )
    args = parser.parse_args()

    if not args.input.strip():
        # 빈 문자열이면 Path("") == '.' 이 되어 **레포 전체를 배치 추출**해 버린다
        # (2026-08-31 실사고 — golden/ 안에 쓰레기 출력 디렉토리 생성). 명시적으로 거부한다.
        sys.exit("ERROR: 입력 경로가 비어 있음 — 파일/디렉토리를 지정할 것")
    input_path = Path(args.input)

    if input_path.is_dir():
        # 디렉토리 모드: 일괄 추출
        output_dir = args.output or str(input_path.parent / "extracted_texts")
        print(f"입력 디렉토리: {input_path}")
        print(f"출력 디렉토리: {output_dir}")
        print()

        results = process_directory(str(input_path), output_dir)

        success = sum(1 for r in results if r["status"] == "success")
        errors = sum(1 for r in results if r["status"] == "error")
        print(f"\n완료: {success}개 성공, {errors}개 실패 (총 {len(results)}개)")

    elif input_path.is_file():
        # 단일 파일 모드
        text = extract(str(input_path))

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(_sanitize(text), encoding="utf-8")
            print(f"저장 완료: {args.output} ({len(text)}자)")
        else:
            print(text)

    else:
        print(f"파일/디렉토리를 찾을 수 없습니다: {args.input}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

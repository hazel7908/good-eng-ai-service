#!/usr/bin/env python3
"""
HWPX 보고서 생성 스크립트

템플릿 HWPX 파일의 텍스트를 새로운 사업 데이터로 치환하여
새 HWPX 파일을 생성합니다.

사용법:
    python generate_hwpx.py

현재는 원주 무장리 템플릿 → 괴산 금신리 변환 하드코딩.
향후 범용화 시 config 파일로 분리 예정.
"""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# XML 네임스페이스 등록 (출력 시 ns0, ns1 방지)
NAMESPACES = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf/",
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)

NS = {"hp": NAMESPACES["hp"]}


def get_cell_text(table, row, col):
    """테이블의 특정 셀 텍스트를 가져옵니다."""
    rows = table.findall("hp:tr", NS)
    if row >= len(rows):
        return None
    cells = rows[row].findall("hp:tc", NS)
    if col >= len(cells):
        return None
    texts = []
    for t in cells[col].findall(".//hp:t", NS):
        if t.text:
            texts.append(t.text)
    return "".join(texts)


def set_cell_text(table, row, col, new_value):
    """테이블의 특정 셀의 첫 번째 hp:t 텍스트를 설정합니다."""
    rows = table.findall("hp:tr", NS)
    if row >= len(rows):
        return False
    cells = rows[row].findall("hp:tc", NS)
    if col >= len(cells):
        return False
    t_elem = cells[col].find(".//hp:t", NS)
    if t_elem is not None:
        t_elem.text = new_value
        return True
    return False


def replace_text_in_xml(root, replacements):
    """
    XML 트리의 모든 hp:t 노드에서 텍스트 치환을 수행합니다.
    테이블 내부는 건드리지 않고, 일반 문단의 텍스트만 치환합니다.
    """
    # 테이블 내부의 hp:t 노드를 먼저 수집 (제외용)
    table_t_nodes = set()
    for tbl in root.findall(".//hp:tbl", NS):
        for t in tbl.findall(".//hp:t", NS):
            table_t_nodes.add(t)

    all_t = root.findall(".//hp:t", NS)
    count = 0

    for t_elem in all_t:
        if t_elem in table_t_nodes:
            continue  # 테이블 내부는 스킵
        if t_elem.text is None:
            continue
        original = t_elem.text
        modified = original
        for old_val, new_val in replacements:
            if old_val in modified:
                modified = modified.replace(old_val, new_val)
        if modified != original:
            t_elem.text = modified
            count += 1

    return count


def generate_goesan_from_wonju(template_path, output_path):
    """
    원주 무장리 템플릿에서 괴산 금신리 보고서를 생성합니다.

    테이블 매핑 (원주 무장리 기준):
      Table  0~1: 머리글/바닥글
      Table  2: 사업명
      Table  3: 장 제목
      Table  4: 현황조사내용 표
      Table  5: 소음·진동 측정지점 표
      Table  6: 소음측정결과 표
      Table  7: 진동측정결과 표
      Table  8: 측정지점도 (삽도)
      Table  9: 소음환경기준 표 (법령 고정)
      Table 10: 생활소음 규제기준 표 (법령 고정)
      Table 11: 생활진동 규제기준 표 (법령 고정)
      Table 12: 환경분쟁 피해배상액 (고정)
      Table 13: 영향예측내용 표
      Table 14: 영향예측지점 표
      Table 15: 예측지점도 (삽도)
      Table 16: 건설기계류 소음도 표 (고정)
      Table 17: 합성소음도 공식 (고정)
      Table 18: 진동 감쇠 공식 (고정)
      Table 19: 투입장비대수 표
      Table 20: 공종별 합성소음도 표
      Table 21: 이격거리별 소음도 표
      Table 22: 정온시설 예측소음도 표
      Table 23: 공종별 합성진동레벨 표
      Table 24: 이격거리별 진동도 표
      Table 25: 정온시설 예측진동도 표
      Table 26: 환경보전목표 표
      Table 27: 저소음 건설장비 표 (고정)
      Table 28: 분산투입 효과 표 (고정)
      Table 29: 최종 저감대책 후 예측소음도 표
    """

    # === HWPX 읽기 ===
    with zipfile.ZipFile(template_path, "r") as z_in:
        all_files = {}
        for name in z_in.namelist():
            all_files[name] = z_in.read(name)
    xml_content = all_files["Contents/section0.xml"]
    root = ET.fromstring(xml_content)
    tables = root.findall(".//hp:tbl", NS)

    print("  [1/5] 일반 문단 텍스트 치환...")

    # === 1. 일반 문단 (테이블 외부) 텍스트 치환 ===
    paragraph_replacements = [
        # 사업명/위치 (문단 내 등장)
        (
            "원주시 호저면 무장리 578번지 일원 태양광발전시설 조성사업",
            "괴산군 청안면 금신리 153번지 일원 태양광발전시설 조성사업",
        ),
        (
            "원주시 호저면 무장리 578번지",
            "괴산군 청안면 금신리 153번지",
        ),
        # 소음 측정 서술문
        (
            "주간 평균 45.0dB(A), 야간 평균 39.0dB(A)",
            "주간 평균 49.0dB(A), 야간 평균 44.0dB(A)",
        ),
        # 측정일시 서술
        (
            "2025년 06월 30일 ~ 07월 01일",
            "2025년 09월 18일 ~ 09월 19일",
        ),
        # 소음 목표기준 서술
        (
            "대상지역 \u2018가\u2019 지역의 공사장 낮 기준 65dB(A)",
            "대상지역 \u2018다\u2019 지역의 공사장 낮 기준 65dB(A)",
        ),
        # 진동 기준 서술
        (
            "생활진동 규제기준 상 \u2018가\u2019 지역 의 주간 기준 65dB(V)",
            "생활진동 규제기준 상 \u2018나\u2019 지역 의 주간 기준 70dB(V)",
        ),
        # 정온시설 예측소음도 결과 서술 (원주는 P-1 초과, 괴산은 전 지점 만족)
        (
            "P-1 지점을 제외한 전 지점에서 기준치를 만족하는 것으로 예측되었다.",
            "전 지점에서 기준치를 만족하는 것으로 예측되었다.",
        ),
    ]
    count = replace_text_in_xml(root, paragraph_replacements)
    print(f"    → {count}개 노드 치환")

    # === 2. 테이블 셀 단위 치환 ===
    print("  [2/5] 테이블 셀 치환...")

    # Table 2: 사업명
    set_cell_text(tables[2], 0, 0,
                  "괴산군 청안면 금신리 153번지 일원 태양광발전시설 조성사업")
    print("    Table 2 (사업명): 치환 완료")

    # Table 4: 현황조사내용 - 조사시기
    set_cell_text(tables[4], 1, 1, "2025. 09. 22. ~ 2025. 09. 26. ")
    print("    Table 4 (조사시기): 치환 완료")

    # Table 5: 측정지점 표
    set_cell_text(tables[5], 1, 1, "충청북도 괴산군 청안면 질마로불당재길 48-56")
    set_cell_text(tables[5], 1, 2, "[확인 필요]")  # 이격거리
    set_cell_text(tables[5], 1, 3, "[확인 필요]")  # 비고
    print("    Table 5 (측정지점): 치환 완료")

    # Table 6: 소음측정결과 표
    # Row 2: N-1 데이터행 (col 1~8: 주간1회~4회, 평균, 야간1회~2회, 평균)
    noise_values = ["46.9", "48.4", "51.3", "48.1", "49", "43.6", "43.5", "44"]
    for i, val in enumerate(noise_values):
        set_cell_text(tables[6], 2, i + 1, val)
    # Row 3: 기준행 - "나"→"다" 지역, 55/45 → 65/55
    set_cell_text(tables[6], 3, 0, '소음환경기준(일반지역 "다" 지역)')
    set_cell_text(tables[6], 3, 1, "65")  # 주간 기준
    set_cell_text(tables[6], 3, 2, "55")  # 야간 기준
    print("    Table 6 (소음측정결과): 치환 완료")

    # Table 7: 진동측정결과 표
    # Row 2: V-1 데이터행 (col 1~5: 주간1회, 2회, 평균, 야간1회, 평균)
    vib_values = ["18.7", "11.6", "15", "9.9", "10"]
    for i, val in enumerate(vib_values):
        set_cell_text(tables[7], 2, i + 1, val)
    print("    Table 7 (진동측정결과): 치환 완료")

    # Table 13: 영향예측내용 표
    set_cell_text(tables[13], 0, 0, "구 분")  # 구조 유지
    # 예측항목은 동일, 예측범위의 사업명만 변경
    print("    Table 13 (영향예측내용): 구조 유지")

    # Table 14: 영향예측지점 표 - 현장조사 데이터 필요
    # 원주는 5개 지점, 괴산은 [현장조사 필요]
    for row_idx in range(2, 7):  # P-1 ~ P-5 행
        set_cell_text(tables[14], row_idx, 1, "[현장조사 필요]")  # 지점명
        set_cell_text(tables[14], row_idx, 2, "[확인 필요]")  # 방향
        set_cell_text(tables[14], row_idx, 3, "[확인 필요]")  # 이격거리
        set_cell_text(tables[14], row_idx, 4, "[확인 필요]")  # XTM
        set_cell_text(tables[14], row_idx, 5, "[확인 필요]")  # YTM
    print("    Table 14 (영향예측지점): [현장조사 필요]로 표시")

    # Table 19: 투입장비대수 표
    # 괴산 인풋에 일작업량/시간당 작업량 정보 없음
    set_cell_text(tables[19], 1, 3, "[확인 필요]")  # 일 작업량
    set_cell_text(tables[19], 1, 4, "[확인 필요]")  # 시간당 작업량
    print("    Table 19 (투입장비대수): [확인 필요]로 표시")

    # Table 21: 이격거리별 소음도 표
    # 원주: 57, 101, 150, 200, 300, 500, 1000 / 괴산: 57, 100, 150, 200, 300, 500, 1000
    set_cell_text(tables[21], 0, 2, "100")  # 101 → 100
    set_cell_text(tables[21], 1, 2, "60.1")  # 60.0 → 60.1 (100m에서의 값)
    print("    Table 21 (이격거리별 소음도): 치환 완료")

    # Table 22: 정온시설 예측소음도 - 현장조사 데이터 필요
    for row_idx in range(1, 6):  # P-1 ~ P-5
        set_cell_text(tables[22], row_idx, 1, "[현장조사 필요]")
        set_cell_text(tables[22], row_idx, 2, "[확인 필요]")
        set_cell_text(tables[22], row_idx, 3, "[확인 필요]")
        set_cell_text(tables[22], row_idx, 4, "[확인 필요]")
        # col 5 (소음기준): 주거시설 65, 축사 60
        # col 6 (기준만족여부): [확인 필요]
        set_cell_text(tables[22], row_idx, 6, "[확인 필요]")
    print("    Table 22 (정온시설 예측소음도): [현장조사 필요]로 표시")

    # Table 25: 정온시설 예측진동도 - 현장조사 데이터 필요
    for row_idx in range(1, 6):
        set_cell_text(tables[25], row_idx, 1, "[현장조사 필요]")
        set_cell_text(tables[25], row_idx, 2, "[확인 필요]")
        set_cell_text(tables[25], row_idx, 3, "[확인 필요]")
        set_cell_text(tables[25], row_idx, 4, "[확인 필요]")
        set_cell_text(tables[25], row_idx, 6, "[확인 필요]")
    print("    Table 25 (정온시설 예측진동도): [현장조사 필요]로 표시")

    # Table 26: 환경보전목표 표
    # 원주: 주거 65/65, 축사 60/57 → 괴산: 동일 (구조 유지)
    print("    Table 26 (환경보전목표): 동일 → 유지")

    # Table 29: 최종 저감대책 후 예측소음도 - 현장조사 데이터 필요
    for row_idx in range(1, 6):
        set_cell_text(tables[29], row_idx, 1, "[현장조사 필요]")
        set_cell_text(tables[29], row_idx, 2, "[확인 필요]")
        set_cell_text(tables[29], row_idx, 3, "[확인 필요]")
        set_cell_text(tables[29], row_idx, 4, "[확인 필요]")
        set_cell_text(tables[29], row_idx, 5, "[확인 필요]")
        set_cell_text(tables[29], row_idx, 6, "[확인 필요]")
        set_cell_text(tables[29], row_idx, 7, "[확인 필요]")
    print("    Table 29 (최종 예측소음도): [현장조사 필요]로 표시")

    # === 3. 머리글/바닥글 사업명 치환 ===
    print("  [3/5] 머리글/바닥글 치환...")
    # header.xml에서도 사업명 치환
    if "Contents/header.xml" in all_files:
        header_xml = all_files["Contents/header.xml"].decode("utf-8")
        header_xml = header_xml.replace(
            "원주시 호저면 무장리 578번지 일원 태양광발전시설 조성사업",
            "괴산군 청안면 금신리 153번지 일원 태양광발전시설 조성사업",
        )
        header_xml = header_xml.replace(
            "원주시 호저면 무장리 578번지",
            "괴산군 청안면 금신리 153번지",
        )
        all_files["Contents/header.xml"] = header_xml.encode("utf-8")
        print("    header.xml 치환 완료")

    # === 4. 진동 서술문의 측정값 (테이블 외부) ===
    print("  [4/5] 진동 서술문 치환...")
    # 진동 측정결과 서술은 hp:t가 분리되어 있음: "주간 평균" + "10.0" + "dB(V), 야간" + "9.0" + "dB(V)으로..."
    # 테이블 외부 hp:t에서 정확한 값만 치환
    table_t_nodes = set()
    for tbl in tables:
        for t in tbl.findall(".//hp:t", NS):
            table_t_nodes.add(t)

    all_t = root.findall(".//hp:t", NS)
    for t_elem in all_t:
        if t_elem in table_t_nodes:
            continue
        if t_elem.text is None:
            continue
        # 진동 서술문의 개별 값들
        if t_elem.text == "10.0":
            t_elem.text = "15.0"
            print("    진동 주간 평균: 10.0 → 15.0")
        elif t_elem.text == "9.0":
            t_elem.text = "10.0"
            print("    진동 야간 평균: 9.0 → 10.0")

    # === 5. 저장 ===
    print("  [5/5] HWPX 파일 저장...")
    modified_xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
    modified_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>' + modified_xml
    )

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z_out:
        for name, data in all_files.items():
            if name == "Contents/section0.xml":
                z_out.writestr(name, modified_xml.encode("utf-8"))
            else:
                z_out.writestr(name, data)

    print(f"\n  생성 완료: {output_path}")


def main():
    base = Path(__file__).parent.parent
    template = base / "templates" / "원주_무장리_소음진동_템플릿.hwpx"
    output = base / "tests" / "소음진동" / "output" / "괴산_금신리_소음진동_AI생성.hwpx"

    output.parent.mkdir(parents=True, exist_ok=True)

    print("=== HWPX 보고서 생성 ===")
    print(f"  템플릿: {template.name}")
    print(f"  출력: {output.name}")
    print()

    generate_goesan_from_wonju(str(template), str(output))


if __name__ == "__main__":
    main()

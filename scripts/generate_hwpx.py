#!/usr/bin/env python3
"""
HWPX 템플릿 기반 소음진동 보고서 생성 스크립트.

원주 무장리 HWPX를 템플릿으로, 괴산 금신리 데이터로 텍스트/테이블을 교체하여
표/서식/레이아웃이 보존된 보고서를 생성합니다.

HWPX = ZIP 파일. 내부 Contents/section0.xml에 모든 본문 포함.

사용법:
    python3 scripts/generate_hwpx.py

출력:
    tests/소음진동/output/괴산_금신리_소음진동_AI생성.hwpx
"""

import copy
import math
import os
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


# ============================================================
# 1. 괴산 금신리 데이터 (generate_from_template.py에서 재사용)
# ============================================================
@dataclass
class PredictionPoint:
    p_num: int
    name: str
    direction: str
    distance_m: int
    facility_type: str  # 'residential' or 'livestock'
    xtm: str = ""
    ytm: str = ""
    note: str = "-"

    @property
    def noise_standard(self) -> int:
        return 60 if self.facility_type == 'livestock' else 65

    @property
    def vibration_standard(self) -> int:
        return 57 if self.facility_type == 'livestock' else 70


PREDICTION_POINTS = [
    PredictionPoint(1, "민가1", "북서", 150, 'residential'),
    PredictionPoint(2, "축사2", "서",   200, 'livestock'),
    PredictionPoint(3, "민가3", "남",   250, 'residential'),
    PredictionPoint(4, "축사3", "동",   350, 'livestock'),
    PredictionPoint(5, "민가2", "북서", 350, 'residential'),
    PredictionPoint(6, "축사4", "남서", 550, 'livestock'),
    PredictionPoint(7, "민가4", "동남", 600, 'residential'),
    PredictionPoint(8, "마을",  "북",   850, 'residential'),
]

EQUIP_NOISE = [71.7, 74.9]   # 15m 기준
EQUIP_VIB = [33.5, 33.3]     # 7.5m 기준
LOW_NOISE_REDUCTION = 1.7    # 저소음 굴삭기 저감 dB(A)
VIBRATION_COEFF = 16.17       # 진동 거리감쇠 계수

# XML 네임스페이스
NS = {
    'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hs': 'http://www.hancom.co.kr/hwpml/2011/section',
    'hc': 'http://www.hancom.co.kr/hwpml/2011/core',
}

# ElementTree 네임스페이스 등록 (출력 시 ns0, ns1 대신 원래 prefix 사용)
ET.register_namespace('hp', 'http://www.hancom.co.kr/hwpml/2011/paragraph')
ET.register_namespace('hs', 'http://www.hancom.co.kr/hwpml/2011/section')
ET.register_namespace('hc', 'http://www.hancom.co.kr/hwpml/2011/core')
ET.register_namespace('ha', 'http://www.hancom.co.kr/hwpml/2011/app')
ET.register_namespace('hp10', 'http://www.hancom.co.kr/hwpml/2016/paragraph')
ET.register_namespace('hh', 'http://www.hancom.co.kr/hwpml/2011/head')
ET.register_namespace('hhs', 'http://www.hancom.co.kr/hwpml/2011/history')
ET.register_namespace('hm', 'http://www.hancom.co.kr/hwpml/2011/master-page')
ET.register_namespace('hpf', 'http://www.hancom.co.kr/schema/2011/hpf')
ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
ET.register_namespace('opf', 'http://www.idpf.org/2007/opf/')
ET.register_namespace('ooxmlchart', 'http://www.hancom.co.kr/hwpml/2016/ooxmlchart')
ET.register_namespace('hwpunitchar', 'http://www.hancom.co.kr/hwpml/2016/HwpUnitChar')
ET.register_namespace('epub', 'http://www.idpf.org/2007/ops')
ET.register_namespace('config', 'urn:oasis:names:tc:opendocument:xmlns:config:1.0')


# ============================================================
# 2. 계산 함수
# ============================================================
def combined_level(levels):
    return 10 * math.log10(sum(10 ** (l / 10) for l in levels))


def noise_at_distance(combined_15m, dist_m):
    return combined_15m - 20 * math.log10(dist_m / 15)


def vibration_at_distance(combined_7_5m, dist_m):
    return combined_7_5m - VIBRATION_COEFF * math.log10(dist_m / 7.5)


# ============================================================
# 3. XML 유틸리티
# ============================================================
def get_cell_text(cell):
    """셀의 모든 <hp:t> 텍스트를 결합하여 반환"""
    texts = []
    for t_elem in cell.iter('{http://www.hancom.co.kr/hwpml/2011/paragraph}t'):
        if t_elem.text:
            texts.append(t_elem.text)
    return ''.join(texts)


def set_cell_text(cell, new_text):
    """셀의 첫 번째 <hp:t> 요소 텍스트를 교체"""
    t_elems = list(cell.iter('{http://www.hancom.co.kr/hwpml/2011/paragraph}t'))
    if t_elems:
        t_elems[0].text = new_text
        # 나머지 <hp:t> 요소들은 비우기
        for t in t_elems[1:]:
            t.text = ''


def get_table_rows(tbl):
    """테이블의 직접 자식 <hp:tr> 요소들 반환"""
    return tbl.findall('hp:tr', NS)


def get_row_cells(row):
    """행의 직접 자식 <hp:tc> 요소들 반환"""
    return row.findall('hp:tc', NS)


# ============================================================
# 4. Step 1: 단순 텍스트 교체 (XML 문자열 치환)
# ============================================================
def build_text_replacements():
    """원주 → 괴산 단순 텍스트 교체 목록"""
    combined_noise = combined_level(EQUIP_NOISE)
    min_dist = min(p.distance_m for p in PREDICTION_POINTS)

    return [
        # 프로젝트명
        ("원주시 호저면 무장리 578번지 일원 태양광발전시설 조성사업",
         "괴산군 청안면 금신리 153번지 일원 태양광발전시설 조성사업"),
        # 측정지점 주소
        ("강원특별자치도 원주시 호저면 생담길 120",
         "충청북도 괴산군 청안면 질마로불당재길 48-56"),
        # 조사시기
        ("2025. 06. 30. ~ 2025. 07. 04.",
         "2025. 09. 18. ~ 2025. 09. 19."),
        # 측정일시
        ("2025년 06월 24일 ~ 06월 25일",
         "2025년 09월 18일 ~ 19일"),
        # 소음 측정결과 텍스트
        ("주간 평균 45.0dB(A), 야간 평균 39.0dB(A)",
         "주간 평균 49.0dB(A), 야간 평균 44.0dB(A)"),
        # 예측지점 수
        ("5개 지점을 영향예측지점으로 선정",
         "8개 지점을 영향예측지점으로 선정"),
    ]


def apply_text_replacements(xml_str):
    """XML 문자열에서 단순 텍스트 치환 수행"""
    replacements = build_text_replacements()
    count = 0
    for old, new in replacements:
        if old in xml_str:
            xml_str = xml_str.replace(old, new)
            count += 1
    print(f"  텍스트 교체: {count}건")
    return xml_str


# ============================================================
# 5. Step 2: 테이블 행 교체 + 추가 (XML DOM 조작)
# ============================================================
def replace_table15_prediction(tbl):
    """TABLE#15 (영향예측지점): 5개 데이터행 → 8개 데이터행"""
    rows = get_table_rows(tbl)
    # rows[0], rows[1] = 헤더 (2행)
    # rows[2]~rows[6] = P-1~P-5 데이터

    # 기존 5개 데이터행 교체
    for i in range(5):
        p = PREDICTION_POINTS[i]
        row = rows[2 + i]
        cells = get_row_cells(row)
        # cells: [구분, 지점명, 방향, 이격거리, XTM, YTM, 비고]
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], p.direction)
        set_cell_text(cells[3], str(p.distance_m))
        set_cell_text(cells[4], p.xtm if p.xtm else "-")
        set_cell_text(cells[5], p.ytm if p.ytm else "-")
        set_cell_text(cells[6], p.note)

    # P-6, P-7, P-8: 마지막 데이터행(P-5) 복제
    last_data_row = rows[6]  # P-5 row
    for i in range(5, 8):
        p = PREDICTION_POINTS[i]
        new_row = copy.deepcopy(last_data_row)
        cells = get_row_cells(new_row)
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], p.direction)
        set_cell_text(cells[3], str(p.distance_m))
        set_cell_text(cells[4], p.xtm if p.xtm else "-")
        set_cell_text(cells[5], p.ytm if p.ytm else "-")
        set_cell_text(cells[6], p.note)
        tbl.append(new_row)

    # rowCnt 업데이트
    tbl.set('rowCnt', '10')
    print("  TABLE#15 (영향예측지점): 7행 → 10행")


def replace_table23_noise(tbl):
    """TABLE#23 (예측소음도): 6행(1 header + 5 data) → 9행(1 header + 8 data)"""
    combined_noise = combined_level(EQUIP_NOISE)
    rows = get_table_rows(tbl)
    # rows[0] = 헤더
    # rows[1]~rows[5] = P-1~P-5

    # 기존 5개 데이터행 교체
    for i in range(5):
        p = PREDICTION_POINTS[i]
        pred = round(noise_at_distance(combined_noise, p.distance_m), 1)
        row = rows[1 + i]
        cells = get_row_cells(row)
        # cells: [구분, 지점명, 방향, 이격거리, 예측소음도, 소음기준, 기준만족여부]
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], p.direction)
        set_cell_text(cells[3], str(p.distance_m))
        set_cell_text(cells[4], str(pred))
        set_cell_text(cells[5], str(p.noise_standard))
        satisfied = pred <= p.noise_standard
        set_cell_text(cells[6], "만족" if satisfied else "상회")

    # P-6, P-7, P-8 추가
    last_data_row = rows[5]
    for i in range(5, 8):
        p = PREDICTION_POINTS[i]
        pred = round(noise_at_distance(combined_noise, p.distance_m), 1)
        new_row = copy.deepcopy(last_data_row)
        cells = get_row_cells(new_row)
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], p.direction)
        set_cell_text(cells[3], str(p.distance_m))
        set_cell_text(cells[4], str(pred))
        set_cell_text(cells[5], str(p.noise_standard))
        satisfied = pred <= p.noise_standard
        set_cell_text(cells[6], "만족" if satisfied else "상회")
        tbl.append(new_row)

    tbl.set('rowCnt', '9')
    print("  TABLE#23 (예측소음도): 6행 → 9행")


def replace_table26_vibration(tbl):
    """TABLE#26 (예측진동도): 6행 → 9행"""
    combined_vib = combined_level(EQUIP_VIB)
    rows = get_table_rows(tbl)

    for i in range(5):
        p = PREDICTION_POINTS[i]
        pred = round(vibration_at_distance(combined_vib, p.distance_m), 1)
        row = rows[1 + i]
        cells = get_row_cells(row)
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], p.direction)
        set_cell_text(cells[3], str(p.distance_m))
        set_cell_text(cells[4], str(pred))
        set_cell_text(cells[5], str(p.vibration_standard))
        satisfied = pred <= p.vibration_standard
        set_cell_text(cells[6], "만족" if satisfied else "상회")

    last_data_row = rows[5]
    for i in range(5, 8):
        p = PREDICTION_POINTS[i]
        pred = round(vibration_at_distance(combined_vib, p.distance_m), 1)
        new_row = copy.deepcopy(last_data_row)
        cells = get_row_cells(new_row)
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], p.direction)
        set_cell_text(cells[3], str(p.distance_m))
        set_cell_text(cells[4], str(pred))
        set_cell_text(cells[5], str(p.vibration_standard))
        satisfied = pred <= p.vibration_standard
        set_cell_text(cells[6], "만족" if satisfied else "상회")
        tbl.append(new_row)

    tbl.set('rowCnt', '9')
    print("  TABLE#26 (예측진동도): 6행 → 9행")


def replace_table30_summary(tbl):
    """TABLE#30 (종합 - 최종 저감대책 후 예측소음도): 6행 → 9행
    cols: [구분, 지점명, 이격거리, 예측치, 저소음장비후, 분산투입후, 최종예측치, 환경보전목표, 비고]
    """
    combined_noise = combined_level(EQUIP_NOISE)
    rows = get_table_rows(tbl)
    # rows[0] = 헤더, rows[1]~rows[5] = P-1~P-5

    for i in range(5):
        p = PREDICTION_POINTS[i]
        pred = round(noise_at_distance(combined_noise, p.distance_m), 1)
        after_low = round(pred - LOW_NOISE_REDUCTION, 1)
        # 분산투입: 장비 1대씩 운영 → max(71.7, 74.9) = 74.9
        single_max = max(EQUIP_NOISE)
        pred_dispersed = round(noise_at_distance(single_max, p.distance_m), 1)
        final = pred_dispersed
        env_target = float(p.noise_standard)

        row = rows[1 + i]
        cells = get_row_cells(row)
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], str(p.distance_m))
        set_cell_text(cells[3], str(pred))
        set_cell_text(cells[4], str(after_low))
        set_cell_text(cells[5], str(pred_dispersed))
        set_cell_text(cells[6], str(final))
        set_cell_text(cells[7], str(env_target))
        satisfied = final <= env_target
        set_cell_text(cells[8], "만족" if satisfied else "상회")

    last_data_row = rows[5]
    for i in range(5, 8):
        p = PREDICTION_POINTS[i]
        pred = round(noise_at_distance(combined_noise, p.distance_m), 1)
        after_low = round(pred - LOW_NOISE_REDUCTION, 1)
        single_max = max(EQUIP_NOISE)
        pred_dispersed = round(noise_at_distance(single_max, p.distance_m), 1)
        final = pred_dispersed
        env_target = float(p.noise_standard)

        new_row = copy.deepcopy(last_data_row)
        cells = get_row_cells(new_row)
        set_cell_text(cells[0], f"P - {p.p_num}")
        set_cell_text(cells[1], p.name)
        set_cell_text(cells[2], str(p.distance_m))
        set_cell_text(cells[3], str(pred))
        set_cell_text(cells[4], str(after_low))
        set_cell_text(cells[5], str(pred_dispersed))
        set_cell_text(cells[6], str(final))
        set_cell_text(cells[7], str(env_target))
        satisfied = final <= env_target
        set_cell_text(cells[8], "만족" if satisfied else "상회")
        tbl.append(new_row)

    tbl.set('rowCnt', '9')
    print("  TABLE#30 (종합): 6행 → 9행")


# ============================================================
# 6. Step 3: 측정값 + 기타 테이블 교체
# ============================================================
def replace_table7_noise_measurement(tbl):
    """TABLE#7 (소음측정결과): 측정값 교체
    Row 2: [N-1, 주간1회, 2회, 3회, 4회, 평균, 야간1회, 2회, 평균]
    Row 3: [소음환경기준(일반지역 "나" 지역), 55, 45]
    """
    rows = get_table_rows(tbl)
    # 데이터행 (Row 2)
    data_row = rows[2]
    cells = get_row_cells(data_row)
    new_values = ["N - 1", "46.9", "48.4", "51.3", "48.1", "49.0", "43.6", "43.5", "44.0"]
    for j, val in enumerate(new_values):
        set_cell_text(cells[j], val)

    # 기준행 (Row 3): "나" 지역 → "다" 지역
    std_row = rows[3]
    std_cells = get_row_cells(std_row)
    set_cell_text(std_cells[0], '소음환경기준(일반지역 "다" 지역)')
    set_cell_text(std_cells[1], "65")
    set_cell_text(std_cells[2], "55")
    print("  TABLE#7 (소음측정결과): 값 교체 완료")


def replace_table8_vibration_measurement(tbl):
    """TABLE#8 (진동측정결과): 측정값 교체
    Row 2: [V-1, 주간1회, 2회, 평균, 심야1회, 평균]
    Row 3: [생활진동 규제기준(나. 그밖의 지역), 70, 65]
    """
    rows = get_table_rows(tbl)
    data_row = rows[2]
    cells = get_row_cells(data_row)
    new_values = ["V - 1", "18.7", "11.6", "15.0", "9.9", "10.0"]
    for j, val in enumerate(new_values):
        set_cell_text(cells[j], val)

    # 기준행: 괴산은 "나. 그밖의 지역" / 70 / 65 (원주 템플릿과 동일)
    std_row = rows[3]
    std_cells = get_row_cells(std_row)
    set_cell_text(std_cells[0], "생활진동 규제기준(나. 그밖의 지역)")
    set_cell_text(std_cells[1], "70")
    set_cell_text(std_cells[2], "65")
    print("  TABLE#8 (진동측정결과): 값 교체 완료")


def replace_table6_measurement_point(tbl):
    """TABLE#6 (측정지점): 이격거리 250 → 150, 비고 축사 인근 → 주택
    구조: 2행 (Row 0=헤더, Row 1=데이터)
    Row 1: [N·V-1, 주소, 이격거리, 비고]
    """
    rows = get_table_rows(tbl)
    data_row = rows[1]  # 데이터행은 Row 1
    cells = get_row_cells(data_row)
    # cells[1] = 주소 (이미 텍스트 교체로 변경됨)
    set_cell_text(cells[2], "150")
    set_cell_text(cells[3], "주택")
    print("  TABLE#6 (측정지점): 이격거리/비고 교체")


def replace_table22_distance_noise(tbl):
    """TABLE#22 (이격거리별 소음도): 거리 57→50, 101→100 + 소음도 값 교체"""
    combined_noise = combined_level(EQUIP_NOISE)
    rows = get_table_rows(tbl)

    # Row 0: [구분(m), 57, 101, 150, 200, 300, 500, 1000]
    dist_row = rows[0]
    dist_cells = get_row_cells(dist_row)
    new_dists = ["구분(m)", "50", "100", "150", "200", "300", "500", "1000"]
    for j, val in enumerate(new_dists):
        set_cell_text(dist_cells[j], val)

    # Row 1: 소음도 값 재계산
    val_row = rows[1]
    val_cells = get_row_cells(val_row)
    dists = [50, 100, 150, 200, 300, 500, 1000]
    vals = [str(round(noise_at_distance(combined_noise, d), 1)) for d in dists]
    set_cell_text(val_cells[0], "소음도(dB(A))")
    for j, val in enumerate(vals):
        set_cell_text(val_cells[j + 1], val)
    print("  TABLE#22 (이격거리별 소음도): 교체 완료")


def replace_table25_distance_vibration(tbl):
    """TABLE#25 (이격거리별 진동도): 같은 합성진동레벨이므로 값 동일, 하지만 확인차 재계산"""
    combined_vib = combined_level(EQUIP_VIB)
    rows = get_table_rows(tbl)

    # Row 1: 진동도 값 재계산
    val_row = rows[1]
    val_cells = get_row_cells(val_row)
    dists = [50, 100, 150, 200, 300, 500, 1000]
    vals = [str(round(vibration_at_distance(combined_vib, d), 1)) for d in dists]
    set_cell_text(val_cells[0], "진동레벨(dB(V))")
    for j, val in enumerate(vals):
        set_cell_text(val_cells[j + 1], val)
    print("  TABLE#25 (이격거리별 진동도): 확인/재계산 완료")


def replace_table20_equipment(tbl):
    """TABLE#20 (투입장비대수): 작업량 교체
    Row 1: [토공사, 굴삭기, 1.0㎥, 201.22, 25.15, 138.9, 1, -]
    Row 2: [덤프트럭, 15ton, 57.2, 1, -]
    """
    rows = get_table_rows(tbl)

    # 굴삭기 행 (Row 1)
    exc_row = rows[1]
    exc_cells = get_row_cells(exc_row)
    # 일 작업량, 시간당 작업량, 장비별 작업량 교체
    set_cell_text(exc_cells[3], "345.37")  # 일 작업량
    set_cell_text(exc_cells[4], "43.17")   # 시간당 작업량
    set_cell_text(exc_cells[5], "138.9")   # 장비별 작업량 (동일)

    # 덤프트럭 행 (Row 2) - 작업량은 덤프트럭의 시간당 작업량
    dump_row = rows[2]
    dump_cells = get_row_cells(dump_row)
    # 덤프트럭은 셀 구조가 다를 수 있음 (토공사 셀과 병합)
    # Row 2: [덤프트럭, 15ton, 57.2, 1, -]
    # 57.2는 시간당 작업량 → 유지 (or 교체 필요 시 변경)
    print("  TABLE#20 (투입장비대수): 작업량 교체 완료")


# ============================================================
# 7. 진동 측정결과 본문 텍스트 교체
# ============================================================
def replace_vibration_text(xml_str):
    """진동 측정결과 본문 텍스트 교체 (여러 <hp:run>/<hp:t> 요소에 걸쳐있음)
    원주 XML 구조:
      <hp:t>주간 평균 </hp:t>...<hp:t>10.0</hp:t>...<hp:t>dB(V), 야간 </hp:t>...<hp:t>9.0</hp:t>
    → 괴산: 15.0, 10.0
    """
    import re

    # 패턴: "주간 평균 " 뒤에 오는 "10.0" (hp:run/hp:t 태그 사이에)
    # 그리고 "dB(V), 야간 " 뒤에 오는 "9.0"
    pattern = (r'(주간 평균 </hp:t></hp:run><hp:run[^>]*><hp:t>)'
               r'10\.0'
               r'(</hp:t></hp:run><hp:run[^>]*><hp:t>dB\(V\), 야간 </hp:t></hp:run><hp:run[^>]*><hp:t>)'
               r'9\.0')
    replacement = r'\g<1>15.0\g<2>10.0'
    xml_str, n = re.subn(pattern, replacement, xml_str, count=1)
    if n:
        print("  진동 측정결과 본문 텍스트: 교체 완료")
    else:
        print("  경고: 진동 측정결과 본문 텍스트 패턴 미발견")

    return xml_str


def replace_noise_prediction_text(xml_str):
    """소음 예측결과 본문: P-1 지점 관련 텍스트 교체"""
    # 원주: "P-1 지점을 제외한 전 지점에서"
    # 괴산: 모든 지점 만족 여부 확인
    combined_noise = combined_level(EQUIP_NOISE)
    exceeding = []
    for p in PREDICTION_POINTS:
        pred = round(noise_at_distance(combined_noise, p.distance_m), 1)
        if pred > p.noise_standard:
            exceeding.append(f"P-{p.p_num}")

    if exceeding:
        old_text = "P-1 지점을 제외한 전 지점에서 기준치를 만족하는 것으로 예측되었다."
        new_text = f"{', '.join(exceeding)} 지점을 제외한 전 지점에서 기준치를 만족하는 것으로 예측되었다."
    else:
        old_text = "P-1 지점을 제외한 전 지점에서 기준치를 만족하는 것으로 예측되었다."
        new_text = "전 지점에서 기준치를 만족하는 것으로 예측되었다."

    if old_text in xml_str:
        xml_str = xml_str.replace(old_text, new_text)
        print(f"  소음 예측결과 본문: '{old_text[:30]}...' → '{new_text[:30]}...'")

    return xml_str


def replace_noise_target_text(xml_str):
    """소음 목표기준 텍스트 교체: '가' 지역 → 적절한 지역"""
    return xml_str


def replace_min_distance_text(xml_str):
    """최소 이격거리 관련 본문 텍스트 교체"""
    min_dist = min(p.distance_m for p in PREDICTION_POINTS)

    # 소음 관련
    old = "가장 인접한 정온시설은 46m 이격되어 있어"
    new = f"가장 인접한 정온시설은 {min_dist}m 이격되어 있어"
    if old in xml_str:
        xml_str = xml_str.replace(old, new)
        print(f"  최소 이격거리(소음): 46m → {min_dist}m")

    return xml_str


# ============================================================
# 8. 메인 실행
# ============================================================
def main():
    project_root = Path(__file__).parent.parent

    template_path = project_root / "templates" / "원주_무장리_소음진동_템플릿.hwpx"
    output_path = project_root / "tests" / "소음진동" / "output" / "괴산_금신리_소음진동_AI생성.hwpx"

    if not template_path.exists():
        print(f"템플릿 없음: {template_path}")
        return

    print(f"템플릿: {template_path.name}")
    print(f"출력:   {output_path.name}")

    # Step 0: 임시 디렉토리에 ZIP 해제
    with tempfile.TemporaryDirectory() as tmpdir:
        print("\n[1/5] HWPX ZIP 해제...")
        with zipfile.ZipFile(str(template_path), 'r') as zf:
            zf.extractall(tmpdir)

        section_path = os.path.join(tmpdir, 'Contents', 'section0.xml')
        with open(section_path, 'r', encoding='utf-8') as f:
            xml_str = f.read()
        print(f"  section0.xml: {len(xml_str):,} bytes")

        # Step 1: 단순 텍스트 교체 (문자열 레벨)
        print("\n[2/5] 단순 텍스트 교체...")
        xml_str = apply_text_replacements(xml_str)
        xml_str = replace_vibration_text(xml_str)
        xml_str = replace_noise_prediction_text(xml_str)
        xml_str = replace_min_distance_text(xml_str)

        # Step 2+3: XML DOM 조작
        print("\n[3/5] 테이블 DOM 조작...")
        root = ET.fromstring(xml_str)

        tables = root.findall('.//hp:tbl', NS)
        print(f"  총 {len(tables)}개 테이블 발견")

        # TABLE#6 (측정지점)
        replace_table6_measurement_point(tables[5])
        # TABLE#7 (소음측정결과)
        replace_table7_noise_measurement(tables[6])
        # TABLE#8 (진동측정결과)
        replace_table8_vibration_measurement(tables[7])
        # TABLE#15 (영향예측지점) - 행 추가
        replace_table15_prediction(tables[14])
        # TABLE#20 (투입장비대수)
        replace_table20_equipment(tables[19])
        # TABLE#22 (이격거리별 소음도)
        replace_table22_distance_noise(tables[21])
        # TABLE#23 (예측소음도) - 행 추가
        replace_table23_noise(tables[22])
        # TABLE#25 (이격거리별 진동도)
        replace_table25_distance_vibration(tables[24])
        # TABLE#26 (예측진동도) - 행 추가
        replace_table26_vibration(tables[25])
        # TABLE#30 (종합) - 행 추가
        replace_table30_summary(tables[29])

        # Step 4: XML 직렬화 + 저장
        print("\n[4/5] XML 직렬화...")
        xml_output = ET.tostring(root, encoding='unicode', xml_declaration=False)

        # ElementTree가 실제 사용되지 않는 네임스페이스를 제거하므로,
        # 원본 템플릿의 루트 태그에 있던 모든 네임스페이스 선언을 복원해야 함.
        # 한글 프로그램은 이 선언이 없으면 파일을 열지 못함.
        REQUIRED_NAMESPACES = (
            'xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"',
            'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"',
            'xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph"',
            'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"',
            'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"',
            'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"',
            'xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history"',
            'xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page"',
            'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"',
            'xmlns:dc="http://purl.org/dc/elements/1.1/"',
            'xmlns:opf="http://www.idpf.org/2007/opf/"',
            'xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart"',
            'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"',
            'xmlns:epub="http://www.idpf.org/2007/ops"',
            'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"',
        )

        # 루트 태그 <hs:sec ...> 에 누락된 네임스페이스 삽입
        import re
        def restore_namespaces(xml_str):
            match = re.match(r'(<hs:sec\s)', xml_str)
            if not match:
                return xml_str
            # 현재 루트 태그에 있는 네임스페이스 확인
            root_tag_end = xml_str.index('>')
            root_tag = xml_str[:root_tag_end + 1]
            missing = [ns for ns in REQUIRED_NAMESPACES if ns not in root_tag]
            if missing:
                insert_pos = len('<hs:sec')
                ns_str = ' ' + ' '.join(missing)
                xml_str = xml_str[:insert_pos] + ns_str + xml_str[insert_pos:]
            return xml_str

        xml_output = restore_namespaces(xml_output)

        # ElementTree가 self-closing 태그에 공백을 추가하는 문제 수정
        # ' />' → '/>'  (한글 프로그램이 공백 있는 형태를 거부할 수 있음)
        xml_output = xml_output.replace(' />', '/>')

        # XML 선언 추가
        xml_output = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>' + xml_output

        with open(section_path, 'w', encoding='utf-8') as f:
            f.write(xml_output)
        print(f"  section0.xml: {len(xml_output):,} bytes")

        # Step 5: ZIP 재포장 (원본과 동일한 압축방식 유지)
        print("\n[5/5] HWPX ZIP 재포장...")
        os.makedirs(output_path.parent, exist_ok=True)

        # 원본 ZIP에서 각 파일의 압축방식 기록
        compress_types = {}
        with zipfile.ZipFile(str(template_path), 'r') as orig_zf:
            for info in orig_zf.infolist():
                compress_types[info.filename] = info.compress_type

        with zipfile.ZipFile(str(output_path), 'w') as zf:
            # mimetype은 반드시 ZIP의 첫 번째 엔트리여야 함 (HWPX/ODF 스펙)
            mimetype_path = os.path.join(tmpdir, 'mimetype')
            if os.path.exists(mimetype_path):
                zf.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)

            for dirpath, dirnames, filenames in os.walk(tmpdir):
                for fn in filenames:
                    abs_path = os.path.join(dirpath, fn)
                    arc_name = os.path.relpath(abs_path, tmpdir)
                    if arc_name == 'mimetype':
                        continue  # 이미 첫 번째로 추가됨
                    # 원본과 동일한 압축방식 사용
                    comp = compress_types.get(arc_name, zipfile.ZIP_DEFLATED)
                    zf.write(abs_path, arc_name, compress_type=comp)

    print(f"\n완료!")
    print(f"출력 파일: {output_path}")
    print(f"파일 크기: {output_path.stat().st_size:,} bytes")

    # 검증
    verify_output(output_path)


def verify_output(output_path):
    """생성된 HWPX 검증"""
    print("\n" + "=" * 60)
    print("검증")
    print("=" * 60)

    import re

    with zipfile.ZipFile(str(output_path), 'r') as zf:
        xml_bytes = zf.read('Contents/section0.xml')
    xml_str = xml_bytes.decode('utf-8')

    root = ET.fromstring(xml_str)
    tables = root.findall('.//hp:tbl', NS)

    # 1. 프로젝트명 확인
    if "괴산군 청안면 금신리" in xml_str:
        print("[PASS] 프로젝트명: 괴산군 청안면 금신리")
    else:
        print("[FAIL] 프로젝트명 교체 실패")

    # 2. 측정지점 주소
    if "질마로불당재길 48-56" in xml_str:
        print("[PASS] 측정지점 주소: 질마로불당재길 48-56")
    else:
        print("[FAIL] 측정지점 주소 교체 실패")

    # 3. TABLE#15 행 수
    tbl15 = tables[14]
    rows15 = get_table_rows(tbl15)
    if len(rows15) == 10:
        print(f"[PASS] TABLE#15 행 수: {len(rows15)} (2 header + 8 data)")
    else:
        print(f"[FAIL] TABLE#15 행 수: {len(rows15)} (expected 10)")

    # 4. TABLE#23 행 수
    tbl23 = tables[22]
    rows23 = get_table_rows(tbl23)
    if len(rows23) == 9:
        print(f"[PASS] TABLE#23 행 수: {len(rows23)} (1 header + 8 data)")
    else:
        print(f"[FAIL] TABLE#23 행 수: {len(rows23)} (expected 9)")

    # 5. P-1~P-8 확인
    combined_noise = combined_level(EQUIP_NOISE)
    combined_vib = combined_level(EQUIP_VIB)

    print("\n예측소음도 검증:")
    for i, p in enumerate(PREDICTION_POINTS):
        pred = round(noise_at_distance(combined_noise, p.distance_m), 1)
        row = rows23[1 + i]
        cells = get_row_cells(row)
        actual = get_cell_text(cells[4])
        status = "PASS" if actual == str(pred) else "FAIL"
        print(f"  [{status}] P-{p.p_num} ({p.name}, {p.distance_m}m): "
              f"예측={pred}, 실제={actual}, 기준={p.noise_standard}")

    # 6. TABLE#26 행 수
    tbl26 = tables[25]
    rows26 = get_table_rows(tbl26)
    print(f"\n예측진동도 검증:")
    for i, p in enumerate(PREDICTION_POINTS):
        pred = round(vibration_at_distance(combined_vib, p.distance_m), 1)
        row = rows26[1 + i]
        cells = get_row_cells(row)
        actual = get_cell_text(cells[4])
        status = "PASS" if actual == str(pred) else "FAIL"
        print(f"  [{status}] P-{p.p_num} ({p.name}, {p.distance_m}m): "
              f"예측={pred}, 실제={actual}, 기준={p.vibration_standard}")

    # 7. 소음 측정결과
    tbl7 = tables[6]
    rows7 = get_table_rows(tbl7)
    data_row = rows7[2]
    cells = get_row_cells(data_row)
    avg_noise = get_cell_text(cells[5])  # 주간 평균
    if avg_noise == "49.0":
        print(f"\n[PASS] 소음 주간 평균: {avg_noise}")
    else:
        print(f"\n[FAIL] 소음 주간 평균: {avg_noise} (expected 49.0)")

    # 8. 원주 흔적 확인
    wonju_traces = ["무장리", "원주시", "호저면"]
    for trace in wonju_traces:
        if trace in xml_str:
            print(f"[WARN] 원주 흔적 발견: '{trace}'")
        else:
            print(f"[PASS] 원주 흔적 없음: '{trace}'")


if __name__ == "__main__":
    main()

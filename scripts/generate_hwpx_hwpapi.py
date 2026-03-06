#!/usr/bin/env python3
"""
한글 API(win32com) 기반 HWPX 보고서 생성 스크립트.
원주 무장리 템플릿 → 괴산 금신리 데이터로 교체 후 저장.
"""

import io
import math
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

try:
    import win32com.client
except ImportError:
    print("ERROR: pywin32 미설치. pip install pywin32")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    Image = None
    print("WARNING: Pillow 미설치. 이미지 교체 스킵됨.")


# ============================================================
# 데이터 + 계산
# ============================================================
EQUIP_NOISE = [71.7, 74.9]
EQUIP_VIB = [33.5, 33.3]
LOW_NOISE_REDUCTION = 1.7
VIB_COEFF = 16.17

PP = [  # (번호, 이름, 방향, 거리, 종류 R/L) — 삽도 이미지 기반 추출
    (1, "민가1", "북서", 160, "R"), (2, "축사2", "서", 220, "L"),
    (3, "민가3", "남", 175, "R"),   (4, "축사3", "동", 150, "L"),
    (5, "축사1", "북서", 450, "L"), (6, "축사4", "남서", 500, "L"),
    (7, "축사5", "동남", 600, "L"), (8, "마을1", "북", 690, "R"),
]

def n_std(t): return 60 if t == "L" else 65
def v_std(t): return 57 if t == "L" else 70
def comb(levels): return 10 * math.log10(sum(10 ** (l / 10) for l in levels))
def noise_at(d): return comb(EQUIP_NOISE) - 20 * math.log10(d / 15)
def vib_at(d): return comb(EQUIP_VIB) - VIB_COEFF * math.log10(d / 7.5)


# ============================================================
# 한글 API 유틸리티 (안전 체크 포함)
# ============================================================
def fr(hwp, old, new):
    """전체 문서 찾기/바꾸기"""
    hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
    p = hwp.HParameterSet.HFindReplace
    p.FindString = old
    p.ReplaceString = new
    p.IgnoreMessage = 1
    p.Direction = hwp.FindDir("AllDoc")
    p.FindType = 0
    hwp.HAction.Execute("AllReplace", p.HSet)


def find_fwd(hwp, text):
    """현재 위치에서 앞으로 검색. 찾으면 True."""
    hwp.HAction.GetDefault("RepeatFind", hwp.HParameterSet.HFindReplace.HSet)
    p = hwp.HParameterSet.HFindReplace
    p.FindString = text
    p.Direction = hwp.FindDir("Forward")
    p.FindType = 0
    p.IgnoreMessage = 1
    return hwp.HAction.Execute("RepeatFind", p.HSet)


def in_table(hwp):
    """현재 커서가 테이블 셀 안에 있는지 확인"""
    return hwp.GetPos()[0] > 0


def find_in_table(hwp, text, skip=0):
    """테이블 셀 안에서 텍스트를 찾을 때까지 반복 검색.
    skip: 테이블 안에서 발견해도 skip번 만큼 건너뜀 (부분매칭 회피용)
    """
    hwp.MovePos(2)
    table_found = 0
    for _ in range(30):  # 최대 30번 시도
        if not find_fwd(hwp, text):
            return False
        if in_table(hwp):
            if table_found < skip:
                table_found += 1
                continue
            return True
    return False


def safe_replace_cell(hwp, text):
    """안전하게 현재 셀 내용 교체. 테이블 밖이면 스킵."""
    if not in_table(hwp):
        print(f"    WARNING: 커서가 테이블 밖! '{text[:20]}' 스킵")
        return False
    hwp.HAction.Run("SelectAll")
    hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
    hwp.HParameterSet.HInsertText.Text = text
    hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
    return True


def right(hwp, n=1):
    for _ in range(n): hwp.HAction.Run("TableRightCell")

def down(hwp, n=1):
    for _ in range(n): hwp.HAction.Run("TableLowerCell")

def col_begin(hwp):
    hwp.HAction.Run("TableColBegin")

def fill_row(hwp, values):
    """현재 셀부터 오른쪽으로 값 채우기"""
    for i, v in enumerate(values):
        if i > 0: right(hwp)
        safe_replace_cell(hwp, v)


# ============================================================
# 삽도 이미지 교체 (HWPX ZIP 후처리)
# ============================================================
def jpg_to_png_bytes(jpg_path):
    """JPG 파일을 PNG 바이트로 변환 (Pillow 사용)"""
    if Image is None:
        return None
    img = Image.open(jpg_path)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def replace_images_in_hwpx(hwpx_path, img_map):
    """HWPX(ZIP) 내 BinData 이미지를 교체.
    img_map: {"BinData/image1.png": "/path/to/new.jpg", ...}
    """
    if Image is None:
        print("  Pillow 없음 — 이미지 교체 스킵")
        return

    tmp_path = hwpx_path + ".tmp"
    replaced = 0

    # 이전 실행의 임시파일 정리
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # 대소문자 무시 매핑 (한글 API가 .png → .PNG로 변경할 수 있음)
    img_map_lower = {k.lower(): v for k, v in img_map.items()}

    with zipfile.ZipFile(hwpx_path, "r") as zin, \
         zipfile.ZipFile(tmp_path, "w") as zout:
        for item in zin.infolist():
            if item.filename.lower() in img_map_lower:
                # JPG → PNG 변환 후 교체
                new_jpg = img_map_lower[item.filename.lower()]
                if not os.path.exists(new_jpg):
                    print(f"  WARNING: {new_jpg} 없음, 스킵")
                    zout.writestr(item, zin.read(item.filename))
                    continue
                png_data = jpg_to_png_bytes(new_jpg)
                # 원본과 동일한 압축 설정 (STORED) 유지
                new_info = zipfile.ZipInfo(item.filename)
                new_info.compress_type = item.compress_type  # 보통 ZIP_STORED(0)
                zout.writestr(new_info, png_data)
                print(f"  {item.filename}: 교체 완료 ({len(png_data):,} bytes)")
                replaced += 1
            else:
                # 그대로 복사 (압축 설정 보존)
                zout.writestr(item, zin.read(item.filename))

    # 원본을 교체 (os.replace는 Windows에서 atomic)
    os.replace(tmp_path, hwpx_path)
    print(f"  이미지 {replaced}건 교체 완료")


# ============================================================
# 메인
# ============================================================
def main():
    root = Path(__file__).parent.parent
    template = str(root / "templates" / "원주_무장리_소음진동_템플릿.hwpx")
    output = str(root / "tests" / "소음진동" / "output" / "괴산_금신리_소음진동_AI생성_hwpapi.hwpx")
    os.makedirs(os.path.dirname(output), exist_ok=True)

    print("[1/4] 한글 시작...")
    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = False
    hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
    hwp.Open(template)
    print("  템플릿 열기 완료")

    # ==========================================
    # [2/4] Find/Replace (고유 문자열)
    # ==========================================
    print("\n[2/4] 텍스트 교체...")
    replacements = [
        ("원주시 호저면 무장리 578번지 일원 태양광발전시설 조성사업",
         "괴산군 청안면 금신리 153번지 일원 태양광발전시설 조성사업"),
        ("강원특별자치도 원주시 호저면 생담길 120",
         "충청북도 괴산군 청안면 질마로불당재길 48-56"),
        ("2025. 06. 30. ~ 2025. 07. 04.",
         "2025. 09. 18. ~ 2025. 09. 19."),
        ("2025년 06월 24일 ~ 06월 25일",
         "2025년 09월 18일 ~ 19일"),
        ("주간 평균 45.0dB(A), 야간 평균 39.0dB(A)",
         "주간 평균 49.0dB(A), 야간 평균 44.0dB(A)"),
        ("주간 평균 10.0dB(V), 야간 9.0dB(V)",
         "주간 평균 15.0dB(V), 야간 10.0dB(V)"),
        ("5개 지점을 영향예측지점으로 선정",
         "8개 지점을 영향예측지점으로 선정"),
        ("가장 인접한 정온시설은 46m 이격",
         "가장 인접한 정온시설은 150m 이격"),
        ("P-1 지점을 제외한 전 지점에서 기준치를 만족하는 것으로 예측되었다.",
         "전 지점에서 기준치를 만족하는 것으로 예측되었다."),
        ("축사 인근", "이서건설"),
        # 소음기준 지역 서술: '가' 65dB(A) → '나' 70dB(A)
        ("대상지역 \u2018가\u2019 지역의 공사장 낮 기준 65dB(A)",
         "대상지역 \u2018나\u2019 지역의 공사장 낮 기준 70dB(A)"),
        # 진동기준 지역 서술: '가' 65dB(V) → '나' 70dB(V) (2단계)
        ("\u2018가\u2019 지역 의", "\u2018나\u2019 지역의"),
        ("주간 기준 65dB(V) 적용", "주간 기준 70dB(V) 적용"),
        # 발생원 현황 서술 (환경질측정_보고서 L917~922, L739~743 기반)
        ("농경지, 개발시설, 민가 등이 위치하고 있으며 소음·진동 발생원으로는 사업계획지구 인근 개발시설로 조사되었다.",
         "나대지 및 경작지가 대부분 형성되어 있으며 남측으로 건설자재 제조업체 및 폐기물 처리업체가 인접하여 있고, 소음·진동 발생원으로는 인접 도로의 차량 통행 소음과 건설자재 공장소음 등으로 조사되었다."),
    ]
    for old, new in replacements:
        fr(hwp, old, new)
    print(f"  {len(replacements)}건 교체 완료")

    # ==========================================
    # [3/4] 테이블 셀 편집
    # ==========================================
    print("\n[3/4] 테이블 편집...")

    # --- 측정지점 이격거리 ---
    print("  측정지점 이격거리...")
    if find_in_table(hwp, "N·V - 1"):
        right(hwp, 2)
        safe_replace_cell(hwp, "25")

    # --- 소음측정결과 ---
    print("  소음측정결과...")
    if find_in_table(hwp, "N - 1"):
        for v in ["46.9", "48.4", "51.3", "48.1", "49", "43.6", "43.5", "44"]:
            right(hwp)
            safe_replace_cell(hwp, v)
        down(hwp)
        col_begin(hwp)
        safe_replace_cell(hwp, '소음환경기준(일반지역 "다" 지역)')
        right(hwp)
        safe_replace_cell(hwp, "65")
        right(hwp)
        safe_replace_cell(hwp, "55")

    # --- 진동측정결과 ---
    print("  진동측정결과...")
    # skip=1: "N·V - 1"(Table 5) 안의 "V - 1" 부분매칭을 건너뜀
    if find_in_table(hwp, "V - 1", skip=1):
        for v in ["18.7", "11.6", "15", "9.9", "10"]:
            right(hwp)
            safe_replace_cell(hwp, v)

    # --- 영향예측지점 (Table 14): 행 추가 + 데이터 ---
    print("  영향예측지점...")
    if find_in_table(hwp, "XTM"):
        down(hwp, 5)  # P-5 행
        hwp.HAction.Run("TableRowEnd")
        hwp.HAction.Run("TableColEnd")
        for _ in range(3): hwp.HAction.Run("TableAppendRow")
        find_in_table(hwp, "XTM")
        down(hwp)
        col_begin(hwp)
        for i, (n, nm, d, dist, t) in enumerate(PP):
            if i > 0: down(hwp); col_begin(hwp)
            fill_row(hwp, [f"P - {n}", nm, d, str(dist), "-", "-", "-"])

    # --- 이격거리별 소음도 (Table 21) ---
    print("  이격거리별 소음도...")
    if find_in_table(hwp, "구분(m)"):
        # 첫 번째 값: 65dB 도달거리 = round(15 * 10^((76.6-65)/20)) = 57m
        dists = [57, 100, 150, 200, 300, 500, 1000]
        for d in dists:
            right(hwp)
            safe_replace_cell(hwp, str(d))
        down(hwp)
        col_begin(hwp)
        safe_replace_cell(hwp, "소음도(dB(A))")
        for d in dists:
            right(hwp)
            safe_replace_cell(hwp, str(round(noise_at(d), 1)))

    # --- 예측소음도 (Table 22): 행 추가 + 데이터 ---
    print("  예측소음도...")
    if find_in_table(hwp, "예측소음도"):
        down(hwp, 5)
        hwp.HAction.Run("TableRowEnd")
        hwp.HAction.Run("TableColEnd")
        for _ in range(3): hwp.HAction.Run("TableAppendRow")
        find_in_table(hwp, "예측소음도")
        down(hwp)
        col_begin(hwp)
        for i, (n, nm, d, dist, t) in enumerate(PP):
            if i > 0: down(hwp); col_begin(hwp)
            pred = round(noise_at(dist), 1)
            sat = "만족" if pred <= n_std(t) else "상회"
            fill_row(hwp, [f"P - {n}", nm, d, str(dist), str(pred), str(n_std(t)), sat])

    # --- 이격거리별 진동도 (Table 24) ---
    print("  이격거리별 진동도...")
    if find_in_table(hwp, "진동레벨(dB(V))"):
        dists = [50, 100, 150, 200, 300, 500, 1000]
        for d in dists:
            right(hwp)
            safe_replace_cell(hwp, str(round(vib_at(d), 1)))

    # --- 예측진동도 (Table 25): 행 추가 + 데이터 ---
    print("  예측진동도...")
    if find_in_table(hwp, "예측진동도"):
        down(hwp, 5)
        hwp.HAction.Run("TableRowEnd")
        hwp.HAction.Run("TableColEnd")
        for _ in range(3): hwp.HAction.Run("TableAppendRow")
        find_in_table(hwp, "예측진동도")
        down(hwp)
        col_begin(hwp)
        for i, (n, nm, d, dist, t) in enumerate(PP):
            if i > 0: down(hwp); col_begin(hwp)
            pred = round(vib_at(dist), 1)
            sat = "만족" if pred <= v_std(t) else "상회"
            fill_row(hwp, [f"P - {n}", nm, d, str(dist), str(pred), str(v_std(t)), sat])

    # --- 최종 저감대책 (Table 29): 행 추가 + 데이터 ---
    print("  최종 저감대책...")
    if find_in_table(hwp, "최종예측치"):
        down(hwp, 5)
        hwp.HAction.Run("TableRowEnd")
        hwp.HAction.Run("TableColEnd")
        for _ in range(3): hwp.HAction.Run("TableAppendRow")
        find_in_table(hwp, "최종예측치")
        down(hwp)
        col_begin(hwp)
        smax = max(EQUIP_NOISE)
        for i, (n, nm, d, dist, t) in enumerate(PP):
            if i > 0: down(hwp); col_begin(hwp)
            pred = round(noise_at(dist), 1)
            alow = round(pred - LOW_NOISE_REDUCTION, 1)
            disp = round(smax - 20 * math.log10(dist / 15), 1)
            tgt = float(n_std(t))
            sat = "만족" if disp <= tgt else "상회"
            fill_row(hwp, [f"P - {n}", nm, str(dist), str(pred),
                           str(alow), str(disp), str(disp), str(tgt), sat])

    # ==========================================
    # [4/5] 저장
    # ==========================================
    print("\n[4/5] 저장...")
    hwp.SaveAs(output, "HWPX")
    hwp.Quit()
    time.sleep(2)  # 한글 프로세스 완전 종료 대기

    size = os.path.getsize(output)
    print(f"  한글 API 저장 완료: {size:,} bytes")

    # ==========================================
    # [5/5] 삽도 이미지 교체 (ZIP 후처리)
    # ==========================================
    print("\n[5/5] 삽도 이미지 교체...")
    raw_base = root / "소규모환경 태양광사업 관련 자료_260219" / "소규모환경 태양광사업 관련 자료_260219" / "4. 괴산군 청안면 금신리 태양광" / "삽도"
    img_map = {
        "BinData/image1.png": str(raw_base / "소음진동 측정지점.jpg"),
        "BinData/image2.png": str(raw_base / "대기, 소음진동 영향예측지점.jpg"),
    }
    replace_images_in_hwpx(output, img_map)

    # 간단 검증
    size = os.path.getsize(output)
    print(f"\n완료! {size:,} bytes")
    print(f"출력: {output}")

    with zipfile.ZipFile(output, "r") as zf:
        xml = zf.read("Contents/section0.xml").decode("utf-8")
    print(f"\n검증: section0.xml = {len(xml):,} chars")
    for kw in ["괴산", "P - 8", "이서건설", "46.9", "마을1", "축사1", "축사5",
               "나대지 및 경작지"]:
        print(f"  '{kw}': {'OK' if kw in xml else 'MISSING'}")
    # 이미지 교체 확인
    with zipfile.ZipFile(output, "r") as zf:
        for item in zf.infolist():
            if "image" in item.filename.lower():
                print(f"  {item.filename}: {item.file_size:,} bytes")


if __name__ == "__main__":
    main()

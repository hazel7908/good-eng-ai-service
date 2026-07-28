#!/usr/bin/env python3
"""출력 HWPX 상세 검증 스크립트"""
import zipfile
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

output = r'C:\Users\user00\Documents\GitHub\good-eng-ai-service\tests\소음진동\output\괴산_금신리_소음진동_AI생성_hwpapi.hwpx'

with zipfile.ZipFile(output, 'r') as zf:
    xml = zf.read('Contents/section0.xml').decode('utf-8')

print(f"section0.xml: {len(xml):,} chars\n")

# 1. EN DASH 버전 P-point
print("=== P-point (EN DASH \u2013) ===")
for i in range(1, 9):
    tag = f'P \u2013 {i}'
    cnt = xml.count(tag)
    status = "OK" if cnt >= 4 else "MISSING" if cnt == 0 else f"LOW({cnt})"
    print(f"  {tag}: {cnt}회 {status}")

# 2. 새 PP 시설명
print("\n=== PP 시설명 (이미지 기반) ===")
for nm in ["민가1", "축사2", "민가3", "축사3", "축사1", "축사4", "축사5", "마을1"]:
    cnt = xml.count(nm)
    print(f"  '{nm}': {cnt}회 {'OK' if cnt > 0 else 'MISSING'}")

# 3. 이전 PP 이름 (제거 확인)
print("\n=== 이전 PP 이름 (제거 확인) ===")
for nm in ["민가2", "민가4"]:
    cnt = xml.count(nm)
    print(f"  '{nm}': {cnt}회 {'REMOVED OK' if cnt == 0 else 'STILL EXISTS!'}")

# "마을" 단독 (마을1이 아닌)은 원주 템플릿에 있을 수 있으므로 스킵

# 4. NV-1 이격거리 (25m)
print("\n=== NV-1 이격거리 ===")
# 25가 포함되어 있는지 확인 (다른 숫자에 포함되지 않게 주의)
idx = xml.find('>25<')
print(f"  '>25<' 존재: {'YES' if idx >= 0 else 'NO'}")

# 5. PP 이격거리
print("\n=== PP 이격거리 ===")
for d in [160, 220, 175, 150, 450, 500, 600, 690]:
    cnt = xml.count(f'>{d}<')
    print(f"  {d}m: >{d}< {cnt}회 {'OK' if cnt > 0 else 'CHECK'}")

# 6. 기본 키워드
print("\n=== 기본 키워드 ===")
for kw in ["괴산", "이서건설", "46.9", "70dB(V)", "49.0dB(A)", "15.0dB(V)"]:
    cnt = xml.count(kw)
    print(f"  '{kw}': {cnt}회 {'OK' if cnt > 0 else 'MISSING'}")

# 7. 제거 확인 (원주 데이터)
print("\n=== 원주 데이터 제거 확인 ===")
for kw in ["원주시 호저면", "무장리 578번지", "생담길 120", "45.0dB(A)", "65dB(V) 적용"]:
    cnt = xml.count(kw)
    print(f"  '{kw}': {cnt}회 {'REMOVED OK' if cnt == 0 else 'STILL EXISTS!'}")

# 8. 예측소음도 계산 확인 (P-4가 가장 가까워서 소음도 가장 높음)
import math
def noise_at(d):
    cn = 10 * math.log10(10**(71.7/10) + 10**(74.9/10))
    return cn - 20 * math.log10(d / 15)

print("\n=== 예측소음도 확인 ===")
pp_data = [
    (1, "민가1", 160, "R"), (2, "축사2", 220, "L"),
    (3, "민가3", 175, "R"), (4, "축사3", 150, "L"),
    (5, "축사1", 450, "L"), (6, "축사4", 500, "L"),
    (7, "축사5", 600, "L"), (8, "마을1", 690, "R"),
]
for n, nm, dist, t in pp_data:
    pred = round(noise_at(dist), 1)
    std = 60 if t == "L" else 65
    sat = "만족" if pred <= std else "상회"
    in_xml = str(pred) in xml
    print(f"  P-{n} {nm} {dist}m: {pred}dB vs {std} → {sat} {'(XML OK)' if in_xml else '(XML MISSING)'}")

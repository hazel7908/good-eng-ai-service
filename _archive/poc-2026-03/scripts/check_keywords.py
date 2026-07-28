#!/usr/bin/env python3
"""출력 HWPX에서 '나' 지역, '주거지역' 관련 텍스트 검색"""
import zipfile, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

output = r'C:\Users\user00\Documents\GitHub\good-eng-ai-service\tests\소음진동\output\괴산_금신리_소음진동_AI생성_hwpapi.hwpx'
with zipfile.ZipFile(output, 'r') as zf:
    xml = zf.read('Contents/section0.xml').decode('utf-8')

# <hp:t> 태그 내용만 추출
texts = re.findall(r'<hp:t[^>]*>(.*?)</hp:t>', xml)

print("=== '나' 지역 / '가' 지역 포함 텍스트 ===")
for t in texts:
    if ('나' in t and '지역' in t) or ('가' in t and '지역' in t):
        if len(t) > 5:  # 너무 짧은건 제외
            print(f"  [{t}]")

print("\n=== '주거지역' 또는 '주거시설' 포함 텍스트 ===")
for t in texts:
    if '주거지역' in t or '주거시설' in t:
        print(f"  [{t}]")

print("\n=== dB(V) 관련 텍스트 ===")
for t in texts:
    if 'dB(V)' in t and ('65' in t or '70' in t or '기준' in t or '적용' in t):
        print(f"  [{t}]")

print("\n=== 생활소음 / 생활진동 + 규제기준 텍스트 ===")
for t in texts:
    if ('생활소음' in t or '생활진동' in t) and '규제기준' in t:
        print(f"  [{t}]")

print("\n=== dB(A) + 적용 텍스트 ===")
for t in texts:
    if 'dB(A)' in t and '적용' in t:
        print(f"  [{t}]")

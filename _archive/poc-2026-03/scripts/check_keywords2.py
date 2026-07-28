#!/usr/bin/env python3
"""출력 HWPX에서 소음/진동 목표기준 관련 텍스트 검색 - 파일 출력"""
import zipfile, re

output = r'C:\Users\user00\Documents\GitHub\good-eng-ai-service\tests\소음진동\output\괴산_금신리_소음진동_AI생성_hwpapi.hwpx'
with zipfile.ZipFile(output, 'r') as zf:
    xml = zf.read('Contents/section0.xml').decode('utf-8')

# <hp:t> 태그 내용만 추출
texts = re.findall(r'<hp:t[^>]*>(.*?)</hp:t>', xml)

lines = []

lines.append("=== 목표기준 + 적용 관련 ===")
for t in texts:
    if '적용' in t and ('기준' in t or 'dB' in t):
        lines.append(f"  [{t}]")

lines.append("")
lines.append("=== 주거 관련 (길이>3) ===")
for t in texts:
    if ('주거지역' in t or '주거시설' in t) and len(t) > 3:
        lines.append(f"  [{t}]")

lines.append("")
lines.append("=== 소음환경기준 + 지역 ===")
for t in texts:
    if '소음환경기준' in t:
        lines.append(f"  [{t}]")

lines.append("")
lines.append("=== 환경보전목표 테이블 관련 ===")
for i, t in enumerate(texts):
    if '환경보전목표' in t or ('주거시설' in t and len(t) < 10):
        # 주변 텍스트도 보기
        ctx = texts[max(0,i-2):min(len(texts),i+5)]
        lines.append(f"  idx={i}: [{t}]")
        for j, c in enumerate(ctx):
            if c != t:
                lines.append(f"    ctx[{i-2+j}]: [{c}]")

with open(r'C:\Users\user00\Documents\GitHub\good-eng-ai-service\scripts\check_result2.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("Done - check_result2.txt")

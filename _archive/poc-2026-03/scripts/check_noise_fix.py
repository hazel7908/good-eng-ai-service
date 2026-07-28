#!/usr/bin/env python3
"""소음 목표기준 교체 확인"""
import zipfile, re

output = r'C:\Users\user00\Documents\GitHub\good-eng-ai-service\tests\소음진동\output\괴산_금신리_소음진동_AI생성_hwpapi.hwpx'
with zipfile.ZipFile(output, 'r') as zf:
    xml = zf.read('Contents/section0.xml').decode('utf-8')

texts = re.findall(r'<hp:t[^>]*>(.*?)</hp:t>', xml)

lines = []
lines.append("=== 소음/진동 목표기준 텍스트 ===")
for t in texts:
    if '규제기준' in t and '적용' in t:
        lines.append(f"  [{t}]")

lines.append("")
lines.append("=== P-8 EN DASH 확인 ===")
en_dash = '\u2013'
p8 = f'P {en_dash} 8'
cnt = xml.count(p8)
lines.append(f"  'P \\u2013 8' (EN DASH): {cnt}회 {'OK' if cnt > 0 else 'MISSING'}")

p8_hyp = 'P - 8'
cnt2 = xml.count(p8_hyp)
lines.append(f"  'P - 8' (hyphen): {cnt2}회")

with open(r'C:\Users\user00\Documents\GitHub\good-eng-ai-service\scripts\check_noise_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("Done")

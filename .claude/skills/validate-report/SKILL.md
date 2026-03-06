---
name: validate-report
description: 생성된 HWPX 보고서를 정답지와 비교 검증
argument-hint: "[섹션명] (예: 소음진동)"
---

# 보고서 검증 워크플로우

## 전제 조건
- 생성 결과물: `tests/{섹션}/output/` 에 HWPX 파일
- 정답지 텍스트: `tests/{섹션}/expected/` 에 추출된 텍스트

## 실행 절차

### 1단계: 생성 결과물 텍스트 추출
```python
# HWPX에서 텍스트 추출 (zipfile + XML 파싱)
import zipfile, xml.etree.ElementTree as ET
with zipfile.ZipFile(hwpx_path) as z:
    xml = z.read("Contents/section0.xml")
    root = ET.fromstring(xml)
    texts = [e.text for e in root.iter() if e.text and e.text.strip()]
```

### 2단계: 정답지와 라인별 비교
- 섹션별로 대응되는 부분 매칭
- 차이점을 WRONG / MISSING / EXTRA / MINOR / UNAVAIL 로 분류

### 3단계: 오류 분류 기준

| 판정 | 의미 |
|:----:|------|
| WRONG | 변경했으나 값이 틀림 |
| MISSING | 변경해야 하나 누락 |
| EXTRA | 불필요한 변경 |
| MINOR | 표기 차이 (의미 동일) |
| UNAVAIL | 인풋 자료 한계 |

### 4단계: 결과 문서화
- `docs/poc_hwpx_comparison.md` 에 비교 결과 작성
- 오류 원인 분석 + 개선 방안 제시
- 해당 섹션의 rules 오류 레지스트리에 새로운 오류 추가

### 5단계: 법령표 서식 확인 (수동)
- Table 9 (소음환경기준): 적용 지역 볼드/음영 확인
- Table 10 (생활소음 규제기준): 적용 지역 음영 확인
- Table 11 (생활진동 규제기준): 적용 지역 음영 확인

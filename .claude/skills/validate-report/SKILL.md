---
name: validate-report
description: 생성된 HWPX 보고서를 정답지와 비교 검증
argument-hint: "[카테고리] [파트] [사업] (예: small-env noise-vib 괴산_금신리)"
---

# 보고서 검증 워크플로우

## 전제 조건
- 생성 결과물: `cases/{카테고리}/{사업}/{파트}/` 에 HWPX 파일
- 정답지: `golden/{카테고리}/{사업}/{파트}.txt` — **`golden/` 에 짝이 있는 사업에서만 자동 비교가 성립한다.**
  짝이 없으면(신규 납품 사업) 자동 검증 불가 → 사람이 검토한다

> **`golden/` 을 여는 것은 이 스킬뿐이다.** 생성 절차(1~4단계)에서는 한 번도 열리지 않는다

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
- `cases/{카테고리}/{사업}/{파트}/validation.md` 에 비교 결과 작성
- 오류 원인 분석 + 개선 방안 제시
- `.claude/rules/{카테고리}/{파트}.md` 오류 레지스트리에 새로운 오류 추가

### 5단계: 법령표 서식 확인 (수동)
- Table 9 (소음환경기준): 적용 지역 볼드/음영 확인
- Table 10 (생활소음 규제기준): 적용 지역 음영 확인
- Table 11 (생활진동 규제기준): 적용 지역 음영 확인

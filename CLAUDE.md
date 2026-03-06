# 환경영향평가 보고서 AI 자동화 프로젝트

## 프로젝트 개요

소규모 환경영향평가 보고서(태양광 발전시설)의 특정 파트를 AI로 자동 생성하는 시스템.
**접근 방식**: HWPX 템플릿(원주 무장리) + 변수 치환 → 새 사업 보고서 생성.
**기술 스택**: Windows + 한글 프로그램 API (win32com) + Python 3.10+

## 현재 상태

- **Phase 1 (소음·진동)**: PoC 완료, 결과 비교 분석 완료
  - 한글 API 기반 HWPX 자동 생성 성공 (14건 텍스트 교체 + 9개 표 편집 + 2건 이미지 교체)
  - 정답지 대비 정확도: OK 44%, WRONG 31%, MISSING 12% → 개선 필요 항목 식별 완료
  - 상세 비교: `docs/poc_hwpx_comparison.md`
- Python XML 직접 조작 방식은 **파일 무결성 문제로 중단** (한글 API만 사용)

## 프로젝트 구조

```
├── CLAUDE.md                     # 이 파일 (프로젝트 개요)
├── .claude/
│   ├── rules/
│   │   ├── common.md             # 공통 규칙 (기준 체계 매핑, 품질 기준)
│   │   ├── hwpx.md               # HWPX 기술 규칙 (한글 API 패턴)
│   │   └── 소음진동.md            # 소음진동 변수 매핑, 공식, 분기, 오류 패턴
│   └── skills/
│       ├── generate-report/      # /generate-report — 보고서 생성 워크플로우
│       └── validate-report/      # /validate-report — 결과 검증 워크플로우
│
├── scripts/                      # 생성/추출 스크립트
│   ├── generate_hwpx_hwpapi.py   # 한글 API 기반 HWPX 생성 (메인)
│   └── extract_hwp.py            # HWPX 텍스트 추출
│
├── templates/                    # HWPX 템플릿 + 정답지 (검증용만!)
├── tests/소음진동/                # 인풋(input/), 정답(expected/), 출력(output/)
├── references/                   # 레퍼런스 보고서 4개 (추출 텍스트)
├── docs/                         # PoC 문서
│   ├── poc_hwpx_comparison.md    # 생성 vs 정답 비교 분석
│   ├── poc_result_report.md      # PoC 결과 보고서
│   └── poc_plan.md               # PoC 실행 계획서
└── raw_data/                     # 원본 자료 (git 제외)
```

## 핵심 원칙

1. **정답지 참조 금지**: 생성 과정에서 정답지 사용 금지. 검증 단계에서만 사용
2. **원본 텍스트 우선**: 삽도 추출 데이터보다 텍스트 파일에서 직접 확인. 추출 불가 시 `[확인 필요]`
3. **기준 체계 혼동 주의**: 소음환경기준("가"~"라")과 생활소음규제기준("가.주거"/"나.그밖") 구분 필수 → `.claude/rules/common.md` 참조

## 코드 작성 시 주의사항

- Python 3.10+, 가상환경 `.venv/`
- 원본 HWP/PDF는 `raw_data/`에 보관, git 제외
- 한글 API 사용 시 반드시 `.claude/rules/hwpx.md` 참조

## 현재 TODO

| Phase | 내용 | 상태 |
|-------|------|:----:|
| 1-2c | 한글 API HWPX 자동 생성 PoC | ✅ 완료 |
| 1-3 | PoC 비교 분석 + 지식 구조화 | 🔄 진행 중 |
| 2 | 대기질 파트 확장 | 대기 |
| 3 | 전체 보고서 통합 | 미착수 |
| 4 | 웹 기반 운영 시스템 | 미착수 |

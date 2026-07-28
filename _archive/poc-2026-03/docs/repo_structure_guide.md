# 레포 구조 및 작업 방식 가이드

> 작성일: 2026-03-06
> 목적: 이 레포에서 Claude Code가 어떻게 동작하는지, 새 세션에서 작업할 때 무엇이 어떻게 참조되는지 설명

---

## 1. 배경

### PoC 당시의 작업 방식 (Phase 1)

소음·진동 PoC는 **CLAUDE.md 한 파일(524줄)에 모든 지식을 담고** 작업했다.
변수 매핑, 계산 공식, 한글 API 패턴, 분기 로직, 레퍼런스 비교 — 전부 한 곳에 있었고, Claude Code는 매 세션마다 이 전체를 읽었다.

문제:
- 파일이 커지면 지시 준수율이 떨어짐 (토큰 과다)
- 대기질 등 섹션 추가 시 감당 불가
- 소음진동 작업할 때 불필요한 지식까지 로딩됨

### 현재 구조 (Phase 1-3 이후)

PoC 결과 비교 분석 후, Claude Code 표준 체계에 맞게 지식을 분리했다.

---

## 2. 현재 레포 구조

```
good-eng-ai-service/
│
├── CLAUDE.md                              # 프로젝트 개요 (64줄)
│                                          # → 매 세션 시작 시 자동 로딩
│
├── .claude/
│   ├── rules/                             # 주제별 규칙 (조건부 로딩)
│   │   ├── common.md                      #   공통: 기준 체계 매핑, 품질 기준
│   │   ├── hwpx.md                        #   기술: 한글 API 패턴, HWPX 구조
│   │   └── 소음진동.md                     #   섹션: 변수 매핑, 공식, 오류 패턴
│   │
│   ├── skills/                            # 워크플로우 (명시적 호출)
│   │   ├── generate-report/SKILL.md       #   /generate-report — 보고서 생성
│   │   └── validate-report/SKILL.md       #   /validate-report — 결과 검증
│   │
│   └── settings.local.json                # 로컬 설정 (git 제외)
│
├── scripts/
│   ├── generate_hwpx_hwpapi.py            # 한글 API 기반 HWPX 생성 (Windows 전용)
│   └── extract_hwp.py                     # HWPX 텍스트 추출
│
├── templates/
│   ├── 원주_무장리_소음진동_템플릿.hwpx     # 생성 기반 템플릿
│   └── 괴산_금신리_소음진동_정답.hwpx       # 검증용만 (생성 시 참조 금지!)
│
├── tests/소음진동/
│   ├── input/                             # 인풋 (사업개요.txt, 환경질측정_보고서.txt)
│   ├── expected/                          # 정답 텍스트 (검증용)
│   └── output/                            # 생성 결과물
│
├── references/                            # 레퍼런스 보고서 4개 (추출 텍스트)
│
├── docs/
│   ├── repo_structure_guide.md            # 이 파일
│   ├── poc_hwpx_comparison.md             # 생성 vs 정답 비교 분석
│   ├── poc_result_report.md               # PoC 결과 보고서
│   └── poc_plan.md                        # PoC 실행 계획서
│
└── raw_data/                              # 원본 자료 (git 제외)
```

---

## 3. 각 파일의 역할과 로딩 시점

### CLAUDE.md — 항상 로딩

Claude Code가 이 레포에서 열리면 **무조건 첫 번째로 읽는 파일**.
프로젝트가 뭔지, 지금 어디까지 왔는지, 핵심 원칙 3개만 담고 있다.
상세 지식은 여기에 넣지 않는다.

### .claude/rules/ — 조건부 로딩

Claude Code가 특정 파일을 읽거나 수정할 때, 해당 경로에 매칭되는 rule만 로딩된다.

| rule 파일 | 로딩 조건 (paths) | 내용 |
|----------|-----------------|------|
| `common.md` | 경로 스코핑 없음 (항상) | 기준 체계 매핑, 품질 기준, 변수 분류 체계 |
| `hwpx.md` | `scripts/**`, `templates/**` | 한글 API 사용법, HWPX 구조, 기술적 함정 |
| `소음진동.md` | `tests/소음진동/**`, `scripts/generate_hwpx*` | 소음진동 전용: 테이블 인덱스, 변수 매핑, 계산 공식, 분기 로직, 오류 패턴 |

예시:
- `tests/소음진동/input/환경질측정_보고서.txt`를 읽으면 → `common.md` + `소음진동.md` 로딩
- `scripts/generate_hwpx_hwpapi.py`를 수정하면 → `common.md` + `hwpx.md` + `소음진동.md` 로딩
- `docs/poc_plan.md`만 읽으면 → `common.md`만 로딩 (나머지 불필요)

### .claude/skills/ — 명시적 호출

사용자가 `/generate-report` 또는 `/validate-report`를 입력하면 해당 SKILL.md가 로딩되고, 그 안에 정의된 워크플로우를 따라 작업한다.

---

## 4. 실제 작업 시나리오

### 시나리오 A: 소음진동 개선 작업

사용자가 "소음 목표기준 오류를 수정해줘"라고 요청한 경우:

```
1. Claude Code 시작
   → CLAUDE.md 로딩 (프로젝트 개요, 현재 상태)

2. scripts/generate_hwpx_hwpapi.py 열기
   → .claude/rules/hwpx.md 로딩 (한글 API 패턴)
   → .claude/rules/소음진동.md 로딩 (오류 레지스트리에서 해당 오류 확인)
   → .claude/rules/common.md 로딩 (기준 체계 매핑으로 올바른 값 확인)

3. 코드 수정
   → 소음진동.md의 "PoC 오류 레지스트리"에서 원인과 교훈 참조
   → common.md의 "용도지역별 매핑표"에서 올바른 기준값 확인

4. 검증 (/validate-report 소음진동)
   → validate-report SKILL.md 로딩
   → 정답지와 비교하여 수정 결과 확인
```

### 시나리오 B: 대기질 섹션 신규 확장

사용자가 "대기질 파트도 자동 생성하자"라고 요청한 경우:

```
1. 새 파일 생성
   → .claude/rules/대기질.md (대기질 전용 변수 매핑, 공식, 분기 로직)
   → tests/대기질/input/ (인풋 파일)
   → tests/대기질/expected/ (정답 텍스트)

2. 대기질.md에 path 스코핑 설정
   ---
   paths:
     - "tests/대기질/**"
     - "scripts/*대기*"
   ---

3. 작업 시
   → tests/대기질/ 파일 작업하면 대기질.md만 로딩 (소음진동.md는 로딩 안 됨)
   → common.md는 공통이므로 항상 로딩
   → hwpx.md는 스크립트 작업 시 로딩

4. 공통 지식 추가 발견 시
   → common.md에 추가 (기준 체계 매핑 등)
   → 소음진동과 대기질 모두 자동으로 참조
```

### 시나리오 C: 새로운 사업 보고서 생성

사용자가 "새 사업(예: 홍성 갈산리) 소음진동 보고서 생성해줘"라고 요청한 경우:

```
1. /generate-report 소음진동
   → generate-report SKILL.md의 절차에 따라 진행

2. 인풋 읽기
   → 소음진동.md의 변수 매핑 참조하여 추출

3. 기준 분류 결정
   → common.md의 용도지역별 매핑표로 자동 결정

4. 계산 + 스크립트 실행
   → 소음진동.md의 공식 참조
   → 소음진동.md의 오류 레지스트리 확인 → 동일 실수 방지

5. 검증
   → /validate-report 소음진동
```

---

## 5. 지식이 쌓이는 구조

```
작업 수행 → 오류 발견 → 오류 레지스트리에 추가 → 다음 작업에서 자동 참조
                ↓
         공통 오류면 → common.md에 추가
         섹션 오류면 → 소음진동.md / 대기질.md에 추가
         기술 오류면 → hwpx.md에 추가
```

새 사업을 생성할 때마다 오류 레지스트리가 누적되므로, 같은 실수를 반복하지 않게 된다.
이것이 PoC에서 발견한 19건의 WRONG 항목을 기록해둔 이유다.

---

## 6. 실행 환경

| 환경 | 용도 | 실행 가능한 것 |
|------|------|-------------|
| **Windows** (한글 프로그램 설치) | HWPX 생성 | `generate_hwpx_hwpapi.py` (win32com) |
| **Mac/Linux** | 코드 작성, 분석, 문서화 | 텍스트 추출, 비교 분석, 지식 정리 |

`generate_hwpx_hwpapi.py`는 **Windows 전용**. 한글 프로그램의 COM API를 호출하므로 Mac/Linux에서는 실행 불가.
텍스트 추출(`extract_hwp.py`)이나 비교 분석은 어디서든 가능.

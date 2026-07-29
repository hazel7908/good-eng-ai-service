# 환경영향평가 보고서 AI 자동화

소규모 환경영향평가 보고서(태양광 발전시설)의 파트별 초안을 AI로 자동 생성하는 프로젝트.

**접근 방식**: 완성된 보고서(골든셋)에서 **베이스 문서 + 변수 명세**를 도출하고, 신규 사업의 인풋으로 채워 생성한다.
**기술 스택**: Windows + 한글 프로그램 API (win32com) + Python 3.10+

---

## 현재 상태

**Phase 1 (소음·진동) PoC 완료 → 지식·구조 정비 중.**

레포는 2026-07-27~28에 **PoC 구조에서 전 영역 서비스 구조로 개편**됐다. 옛 구조(`scripts/` `tests/` `references/` `prompts/`)는 `_archive/poc-2026-03/` 에 그대로 보존돼 있다.

| 단계 | 내용 | 상태 |
|:--:|---|:--:|
| 0~3.5 | 레포 구조 개편 + 경로 스코핑 검증 | ✅ 완료 |
| 4 | 파트 지식 7장르 재편집 · 카테고리층 · 이름 대응표 | 🔄 진행 중 |
| 5 | 사업 데이터를 `vars/` 로 분리 | ⬜ |
| 6 | **원주 골든셋 → 베이스 문서 도출 (빈칸 뚫기)** | ⬜ **Windows 필요** |
| 7 | `skills/distill-golden` 신설 | ⬜ |
| 8 | 문서 동기화 | 🔄 |

상세 계획: [`docs/repo_restructure_plan.md`](docs/repo_restructure_plan.md) §9

> ⚠️ **`templates/` 가 아직 비어 있다.** 베이스 문서는 단계 6(Windows·한글 프로그램)에서 만든다. 그때까지 생성 파이프라인은 끝까지 돌지 않는다.

---

## PoC 결과 — 두 번의 측정, 범위가 다르다

두 수치가 함께 돌아다니는데 **잰 대상이 다르다.** 섞어 읽으면 안 된다.

### 1차 (2026-02) — 텍스트 수준 생성

| 항목 | 결과 |
|---|---|
| 문서 구조 일치도 | 100% |
| 변수 치환 정확도 | 100% (변수 16개) |
| 환각 | **0건** |
| 판단 | **GO** |

→ [`docs/poc_result_report.md`](docs/poc_result_report.md) (클라이언트용)

### 2차 (2026-03) — 실제 HWPX 생성 · 정답지 대조

한글 API로 파일을 실제로 만들어 **항목 61개**를 정답지와 1:1 비교했다.

| 판정 | 건수 | 비율 |
|---|--:|--:|
| OK | 27 | 44.3% |
| WRONG | 19 | 31.1% |
| MISSING | 7 | 11.5% |
| UNAVAIL (인풋 한계) | 4 | 6.6% |
| MINOR (표기 차이) | 3 | 4.9% |
| EXTRA | 1 | 1.6% |

→ [`docs/poc_hwpx_comparison.md`](docs/poc_hwpx_comparison.md)

**두 수치가 모순인 게 아니다.** 1차는 *"구조와 변수를 옳게 채우는가"*, 2차는 *"완성 파일이 정답과 같은가"* 를 쟀다. 2차에서 드러난 오류(기준 체계 혼동, 저감량 계산, 삽도 추출 정밀도)가 지금 정비 중인 지식의 재료다.

> 오류 원인의 **10/61 건이 삽도 이미지 추출 부정확**이다. 텍스트로 안 나오는 값(이격거리·방향·좌표)은 **실무자 입력 또는 GIS 데이터**가 필요하다 — 자동화 범위의 실질적 상한.

---

## 구조

```
├── CLAUDE.md                    항상 로드 — 원칙·현황·포인터
│
├── .claude/
│   ├── rules/                   ▓ 지식 (경로 조건부 로드)
│   │   ├── common.md              공통 — 항상 로드
│   │   ├── hwpx.md                한글 API 기술
│   │   └── small-env/             카테고리층
│   │       ├── _category.md         전 파트 공유 (구조·문체·표기)
│   │       └── noise-vib.md         파트 지식 (변수·공식·분기·오류)
│   └── skills/                  ▓ 절차
│       ├── generate-report/       생성 워크플로우
│       └── validate-report/       검증 워크플로우
│
├── templates/small-env/         ▓ 베이스 문서 (빈칸 뚫린 시작 파일) ⚠️ 단계 6에서 생성
│
├── golden/small-env/            ▓ 골든셋 — 생성 중 접근 금지, 검증 전용
│   ├── {사업}/원본.hwpx · noise-vib.txt      완성 보고서 5건
│   └── _variants.md                         사업 간 변이표
│
├── cases/small-env/{사업}/      ▓ 사업별 작업공간
│   ├── input/                     사업개요.txt · 환경질측정_보고서.txt (전 파트 공유)
│   ├── vars/                      엔진에서 분리한 사업 데이터
│   └── noise-vib/                 생성 결과 · 검증 리포트
│
├── engine/                      ▓ 생성 엔진 (파트 무관)
│   ├── generate.py                한글 API 기반 HWPX 생성 (Windows)
│   └── extract.py                 HWPX 텍스트 추출
│
├── catalog/                     ▓ NAS 카탈로그 (독립 하위시스템)
├── docs/                        ▓ 사람이 읽는 문서
└── _archive/poc-2026-03/        ▓ 옛 PoC 통째 (스코핑·검색 제외)
```

### 폴더 3분할이 핵심이다

| 폴더 | 정체 | 생성 중 접근 |
|---|---|:--:|
| `templates/` | 베이스 문서 (빈칸 뚫린 시작 파일) | ✅ |
| `golden/` | 골든셋 (완성된 정답 보고서) | ❌ **금지** |
| `cases/` | 사업별 입력 + 생성물 | ✅ |

**`golden/` 은 검증 단계에서만 연다.** 실무에는 정답이 없으므로, 생성 과정이 정답을 참조하면 평가가 무의미해진다.

`cases/` 와 `golden/` 에 같은 사업이 나오는 건 중복이 아니다 — 짝이 있으면 **검증 대상**, 없으면 **납품 작업**이다.

---

## 지식이 로드되는 방식

rule 파일은 **경로로 스코핑**된다. 파일을 여는 행위 자체가 트리거이고, Claude의 판단이 개입하지 않는다.

```
golden/small-env/괴산_금신리/noise-vib.txt 를 연다
   → 경로가 noise-vib.md 의 paths: 와 매칭
   → 그 rule 본문이 컨텍스트에 자동 주입
```

| rule | 로드 시점 |
|---|---|
| `common.md` | 항상 (`paths:` 없음) |
| `_category.md` | `cases/`·`templates/`·`golden/` 의 `small-env/` 를 건드릴 때 |
| `noise-vib.md` | 그중 소음진동 파트만 |
| `hwpx.md` | `engine/`·`templates/` 를 건드릴 때 |

파트가 수십 개로 늘어도 컨텍스트엔 **공통 + 카테고리 + 해당 파트 1개**만 들어온다. 안 쓰는 기준표가 같이 떠 있으면 서로 혼동을 부르기 때문이다 (2차 PoC의 Critical 오류 1번이 정확히 기준 분류 혼동이었다).

> **동작은 실측으로 확인됐다** (2026-07-28). 검증 절차와 함정: [`docs/repo_restructure_plan.md`](docs/repo_restructure_plan.md) §1
> `paths:` 가 틀리면 **에러 없이 조용히 로드가 안 된다.** 폴더 이름을 바꿀 때는 반드시 재검증할 것.

---

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/knowledge_architecture.md`](docs/knowledge_architecture.md) | 지식 체계 설계 — 왜 이 구조인가 (7장르·3층·유사 서비스 조사) |
| [`docs/repo_restructure_plan.md`](docs/repo_restructure_plan.md) | 구조 개편 계획·실행 순서·경로 스코핑 설계 |
| [`docs/naming.md`](docs/naming.md) | 한글 ↔ 영문 이름 대응표 |
| [`docs/poc_hwpx_comparison.md`](docs/poc_hwpx_comparison.md) | 2차 PoC 정답지 대조 (개선 목표의 기준선) |
| [`docs/poc_result_report.md`](docs/poc_result_report.md) | 1차 PoC 결과 (클라이언트용) |
| [`docs/nas_structure_overview.md`](docs/nas_structure_overview.md) · [`reorg_strategy.md`](docs/reorg_strategy.md) | NAS 자료 파악·정리 전략 |
| [`golden/small-env/_variants.md`](golden/small-env/_variants.md) | 골든셋 5건 변이 비교 |

---

## 확장 로드맵

| Phase | 내용 | 상태 |
|:--:|---|---|
| 1 | 소음·진동 파트 자동화 | PoC 완료 · 지식 정비 중 |
| 2 | 대기질 파트 확장 (7.2.2) | 대기 |
| 3 | 전체 보고서 통합 | 미착수 |
| 4 | 웹 기반 운영 시스템 | 미착수 |

카테고리 확장(재해영향평가 등)은 구조상 준비돼 있다 — `rules/{카테고리}/` 를 추가하면 된다. 다만 **내용은 그 카테고리 골든셋을 분석해야 나온다.**

---

## 개발 환경

- Python 3.10+, 가상환경 `.venv/`
- 생성(`engine/generate.py`)은 **Windows + 한글 프로그램** 필요. 추출(`extract.py`)은 플랫폼 무관
- 원본 HWP/PDF/JPG는 `raw_data/` (git 제외)
- Python XML 직접 조작 방식은 **파일 무결성 문제로 중단** — 한글 API만 사용

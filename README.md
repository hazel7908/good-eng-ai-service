# 환경영향평가 보고서 AI 자동화

소규모 환경영향평가 보고서(태양광 발전시설)의 파트별 초안을 AI로 자동 생성하는 프로젝트.

**접근 방식**: 완성된 보고서(골든셋)에서 **베이스 문서(빈칸 뚫린 HWPX) + 변수 명세 + 파트 규칙**을 도출하고, 신규 사업의 인풋으로 채워 생성한다.
**기술 스택**: Windows + 한글 프로그램 API (win32com) + Python 3.10+ (계산·검증·문서화는 Mac 겸용)

---

## 현재 상태 (2026-08-24)

**두 파트(소음·진동, 대기질)의 생성→검증 파이프라인 완주. 두 파트 모두 "코드로 고칠 수 있는 오류 0" 도달.**

| 사업 | 파트 | 정확도 (정답 보고서와 항목 대조) |
|---|---|---|
| 천안 화덕리 | 소음·진동 | **94.8%** (73/77) — 문장·수치 오류 0, 잔여는 인풋 원천 부재 |
| 괴산 금신리 | 소음·진동 | 59.0% — 골든셋 중 예외 사업 (규칙 검증용) |
| 청양 매곡리 | 소음·진동 | 50.0% — 구조 이질 사업 (빈칸 치환의 한계 측정) |
| 평창 수청리 | 대기질 | **61.6%** (85/138) — 계산 체인 오차 0, 잔여는 인풋·구조·표준 영역 |

세 숫자가 다른 것은 성능 분산이 아니라 **서로 다른 조건의 측정**이다 — 텍스트 인풋 + 통상 구조면 90%대, 삽도 인풋이면 70%대, 구조 이질 사업은 50%대. 상세와 캘리브레이션: [`docs/20260813_결과보고_소음진동_대기질.md`](docs/20260813_결과보고_소음진동_대기질.md)

**진행 중 — 세 번째 파트 「지역개황」** (2026-08-24 갱신)

앞 두 파트는 *측정값을 계산*했다. 지역개황은 **외부 통계를 옮겨 적는다** — 값의 90%가 계산이 아니라 **소싱**이다.

| 층 | 내용 | 상태 |
|:--:|---|---|
| A 본문 토큰 | 사업 고유값 | 명세 완료 · 베이스 문서는 Windows 대기 |
| **B 통계 표** | **자료 19종 → 절 19개** | **절 18/19 · 자료 15/19종** |
| C 법령표 | 2.4 전체 | 고정 |
| D 삽도 6종 | 지역개황도·수계도 등 | 5종 정답 근접 |

통계는 네 층으로 나눠 다룬다 — ①어느 파일이 어디 있나(`stats_catalog`) ②파일 안 어디에 뭐가 있나(`SOURCES` 선언) ③꺼내는 방법(엔진) ④**꺼낸 값 + 판 지문**(`stats_values`). 생성은 ④만 본다.

**다음 단계**: 나머지 파트로 확대 (10월 말 전체 주제 영역 구현 목표). NAS 전수 조사(08-13)로 파트별 완성 보고서 165~234건 확보 확인 — 자료 허들 없음. 진행 현황·할 일은 [`CLAUDE.md`](CLAUDE.md).

---

## 파이프라인

```
[신규 사업 인풋]                [지식·규칙]                  [생성 엔진]
사업개요·측정보고서       +   골든셋에서 도출한        →   한글(HWP) 자동 조작       →   초안 HWPX
(+ 자매 파트 텍스트)          파트별 규칙(.claude/rules)     빈칸 치환·표 계산·행 조절      + fill-report.md
                                                                                          (실무자용 채움 내역서)
```

1. **`/distill-golden`** — 골든셋 분석 → 파트 규칙 + 베이스 문서 빈칸 명세 도출
2. **`engine/build_template.py`** — 골든셋에 빈칸을 뚫어 베이스 문서 생성 (재현 가능)
3. **`/generate-report`** — 인풋 → vars JSON(사실 대장) → 엔진 생성 → fill-report
4. **`/validate-report`** — 골든셋과 항목 대조 채점 → 규칙에 되먹임 (골든셋은 이 단계에서만 연다)

vars JSON 은 값의 나열이 아니라 **"사업에 대해 확정한 사실들의 대장"**이다 — 사실이 어떤
문장·표가 되는지는 엔진의 파트 핸들러가 결정한다 (사실 1개 → 문서 여러 곳, 자기모순 원천 차단).

---

## 구조

```
├── CLAUDE.md                    항상 로드 — 원칙·현황·다음 할 일
│
├── .claude/
│   ├── rules/                   ▓ 지식 (경로 조건부 로드)
│   │   ├── common.md              공통 — 항상 로드 (기준 체계·변수 분류·vars 규약)
│   │   ├── hwpx.md                한글 API 기술
│   │   └── small-env/             카테고리층
│   │       ├── _category.md         전 파트 공유 (구조·문체·표기·파트 간 인풋 공유)
│   │       ├── noise-vib.md         소음·진동 파트 지식
│   │       ├── air-quality.md       대기질 파트 지식
│   │       └── regional-overview.md 지역개황 파트 지식 (외부 통계 소싱)
│   └── skills/                  ▓ 절차
│       ├── distill-golden/        골든셋 → 규칙·빈칸 명세 도출
│       ├── generate-report/       생성 워크플로우 (fill-report 포함)
│       ├── validate-report/       검증 워크플로우 (PDF 육안 확인 포함)
│       └── nas-survey/            NAS 재조사 — 전수 크롤 → diff (주기 운영)
│
├── templates/small-env/         ▓ 베이스 문서
│   ├── noise-vib.hwpx (+.slots.md)   토큰 36종 · 빈칸 명세
│   ├── air-quality.hwpx (+.slots.md) 토큰 19종
│   ├── regional-overview.slots.md    빈칸 명세만 (베이스 hwpx 는 Windows 작업 대기)
│   └── noise-vib.snippets/           조건부 절 조각 (절 삽입은 보류 중)
│
├── golden/small-env/            ▓ 골든셋 — 생성 중 접근 금지, 검증 전용
│   ├── {사업 10}/                    소음진동 7 + 대기질 4 + 지역개황 8 (겹침 있음)
│   └── _variants.md                  사업 간 변이표(§8 소음진동·§9 대기질·§10 지역개황) + 정답지 자기모순
│
├── cases/small-env/{사업 6}/    ▓ 사업별 작업공간
│   ├── input/                     인풋 (전 파트 공유)
│   ├── vars/                      사업 데이터 JSON (사실 대장)
│   └── {파트}/                    output.hwpx · fill-report.md · validation.md
│
├── engine/                      ▓ 생성 엔진 (파트 무관 본체 + 파트 핸들러)
│   ├── generate.py                한글 API 생성 (Windows) — PART_HANDLERS 레지스트리
│   ├── calc.py · calc_air.py      계산 (플랫폼 무관, 골든셋 자체검증 내장)
│   │  ▸ 지역개황 통계 소싱 — 자료 19종을 네 층으로 나눠 읽는다
│   ├── xlsx_grid.py              공용 격자 — 머리글 인식·병합 끌어채우기·**이름으로 열 찾기**
│   ├── stats_extract.py          지자체 통계연보 엑셀 → 6절 (자체검증 내장)
│   ├── stats_national.py         전국 통계 엑셀 → 9절 · 좌표는 `SOURCES` 선언 (자체검증 82)
│   ├── stats_irregular.py        선언으로 안 되는 모양 — 수변구역·생태경관·하천일람·야생생물
│   ├── hwpx_table.py             HWPX 표 읽기 (**읽기 전용** — `rules/hwpx.md` 금지는 쓰기)
│   ├── stats_pdf.py              텍스트 PDF → 자연공원·습지·백두대간 (합계 검산으로 표 복원)
│   │  ▸ 삽도 — 실행 경로
│   ├── map_fetch.py              주소·좌표 → 베이스 지도 (NGII 지형도·위성 · ECVAM · EGIS)
│   ├── parcels.py                편입토지조서 → 사업지 경계 폴리곤 (연속지적도)
│   ├── ecology.py                생태·자연도 베이스 + 등급 판정 (EcoBank)
│   ├── admin.py                  행정구역명 라벨 (VWorld 행정경계)
│   ├── watercourse.py            수계 서술 → 수계흐름모식도 입력
│   ├── figure_overlay.py         삽도 오버레이 15종 (마커·경계·반경원·행정구역명·정온시설)
│   ├── ecgy.py                   생태·경관보전지역 판정·이격거리·채색 (해수부 WFS)
│   ├── hydro.py                  수계도 — 흐름 화살표·하천명·보호구역 채색
│   ├── psd_base.py               ⚙ 검증 전용 — 정답 PSD 레이어 추출 (파이프라인 아님)
│   ├── build_template.py          베이스 문서 빌더 · build_snippet.py 절 조각
│   ├── fill_report.py             실무자용 채움 내역서 (플랫폼 무관)
│   ├── extract.py                 HWP/HWPX 텍스트 추출 · to_pdf.py 육안 검증용
│
├── catalog/                     ▓ NAS 카탈로그 (독립 하위시스템)
│   ├── synology_filestation.py    NAS API 클라이언트 (병렬 크롤)
│   ├── build_catalog.py           정본 카탈로그 빌더 (290 유니크 사업, v2 예정)
│   ├── build_stats_catalog.py     통계 원자료 카탈로그 (236건 — 지자체 통계연보·전국 통계)
│   ├── stats_registry.py          **통계 자료 전수 목록** — 필요·보유·발행처 (19종)
│   ├── build_stats_values.py      원자료 → **값 저장소** + 판 지문(sha256)
│   ├── trace_stats.py             ⚙ 역추적기 — 값을 넣으면 원자료 어느 시트·열인지 알려준다
│   ├── nas_diff.py                스냅샷 변경 감지
│   ├── harvest_sheets.py          삽도 PSD → 깨끗한 도엽 베이스 수확
│   ├── index_sheets.py            수확본 종류 정규화 + 목록 (이미지는 git 제외)
│   ├── data/nas_index.json.gz     전수 스냅샷 (08-13)
│   ├── data/sheet_georef.json     수확 베이스 실측 좌표 — **다시 만들 수 없는 값**
│   ├── data/stats_values.manifest.json  판 목록·지문·좌표 — **다시 만들 수 없는 값**
│   ├── data/stats_holdings.json   자료별 최신 보유 현황 (창고 + 로컬)
│   ├── data/stats_values/         값 본체 (git 제외 — 재생성 가능, NAS 로 공유)
│   └── review/                    검수용 트리·워크리스트·조사 리포트
│
├── docs/                        ▓ 사람이 읽는 문서 (신규는 YYYYMMDD_제목.md)
│   └── img/                       문서에 넣는 이미지 (비교·예시)
└── _archive/poc-2026-03/        ▓ 옛 PoC 보존 (참조 금지)
```

### 폴더 3분할이 핵심이다

| 폴더 | 정체 | 생성 중 접근 |
|---|---|:--:|
| `templates/` | 베이스 문서 (빈칸 뚫린 시작 파일) | ✅ |
| `golden/` | 골든셋 (완성된 정답 보고서) | ❌ **금지** |
| `cases/` | 사업별 입력 + 생성물 | ✅ |

**`golden/` 은 검증 단계에서만 연다.** 실무에는 정답이 없으므로, 생성 과정이 정답을 참조하면 평가가 무의미해진다.

---

## 지식이 로드되는 방식

rule 파일은 **경로로 스코핑**된다. 파일을 여는 행위 자체가 트리거이고, Claude의 판단이 개입하지 않는다.

| rule | 로드 시점 |
|---|---|
| `common.md` | 항상 (`paths:` 없음) |
| `_category.md` | `cases/`·`templates/`·`golden/` 의 `small-env/` 를 건드릴 때 |
| `noise-vib.md` / `air-quality.md` | 그중 해당 파트만 |
| `hwpx.md` | `engine/`·`templates/` 를 건드릴 때 |

파트가 수십 개로 늘어도 컨텍스트엔 **공통 + 카테고리 + 해당 파트 1개**만 들어온다.
`paths:` 가 틀리면 에러 없이 조용히 로드가 안 되므로, 폴더 이름 변경 시 재검증 필수.

---

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/20260813_결과보고_소음진동_대기질.md`](docs/20260813_결과보고_소음진동_대기질.md) | **1차 결과 보고** (상대 회사 공유용) — 방법·정확도·논의사항 |
| [`docs/실무자_확인요청.md`](docs/실무자_확인요청.md) | 실무자 질문지 — 회사 표준이 없어 갈리는 항목 (10월 배치 회신) |
| [`docs/knowledge_architecture.md`](docs/knowledge_architecture.md) | 지식 체계 설계 — 7장르·3층·skills/rules 분리 원칙 |
| [`docs/naming.md`](docs/naming.md) | 파트 목록·번호 체계(장·절 코드) · 한글↔영문 대응 |
| [`golden/small-env/_variants.md`](golden/small-env/_variants.md) | 골든셋 변이 비교 (n/7 근거) + 정답지 자기모순 목록 |
| [`catalog/review/nas_survey_2026-08-13.md`](catalog/review/nas_survey_2026-08-13.md) | NAS 전수 조사 — 실규모·파트별 자료 집계·신규 사업 |
| [`catalog/review/stats_catalog.md`](catalog/review/stats_catalog.md) | **통계 원자료 지도** — 지자체 통계연보 59·전국 통계 177, 배포 형식별 자동화 가능성 |
| [`docs/20260824_지역개황_작업계획.md`](docs/20260824_지역개황_작업계획.md) | **지역개황 4층 구조·통계 19종 전수·값 저장소 설계** — 이 파트의 정본 |
| [`docs/20260825_윈도우_지역개황_베이스.md`](docs/20260825_윈도우_지역개황_베이스.md) | **⏳ 다음 Windows 세션 지시서** — 베이스 문서 + §B 표 17개 |
| [`docs/20260824_통계자동화_결과보고.md`](docs/20260824_통계자동화_결과보고.md) | 미팅용 — 통계 자동화 결과 (요청 ①② 에 대한 답) |
| [`catalog/review/sheets_harvest.md`](catalog/review/sheets_harvest.md) | 도엽 베이스 수확 목록 — 사업·종류·좌표 유무 (이미지 자체는 git 제외) |
| [`docs/20260819_지역개황_골든셋선별.md`](docs/20260819_지역개황_골든셋선별.md) | 지역개황 골든셋 선별 — 선별 근거·통계 출처 지도 |
| [`docs/20260819_통계원자료_소싱실증.md`](docs/20260819_통계원자료_소싱실증.md) | **통계 원자료 소재 + 매핑 실증** — NAS 통계연보 91건·배포 형식 |
| [`docs/20260819_삽도_자동화.md`](docs/20260819_삽도_자동화.md) | **삽도 자동화** — 베이스 출처 4곳·취득 실증·오버레이 자동화 등급 |
| [`docs/repo_restructure_plan.md`](docs/repo_restructure_plan.md) · [`docs/poc_hwpx_comparison.md`](docs/poc_hwpx_comparison.md) | 구조 개편 이력 · 2차 PoC 기준선 (44.3% — 현재 대비의 출발점) |

---

## 로드맵

| Phase | 내용 | 상태 |
|:--:|---|---|
| 1 | 소음·진동 파트 (7.2.7) | ✅ 3사업 측정, 최고 94.8% |
| 2 | 대기질 파트 (7.2.2) — 파이프라인 이식성 검증 | ✅ 1사업 측정 61.6% (파트 추가 비용: 규칙+베이스+핸들러) |
| 3 | **나머지 파트 확대** — 진행 중: **지역개황(`regional-overview`)** 골든셋 8건 확보(08-19) → 규칙 도출. 이후 수질 등 | 🔄 진행 중 (10월 말 전체 구현 목표) |
| 4 | NAS 정본 카탈로그 v2 + 전체 카테고리 지도 | ⬜ 8월 말 (NAS 업로드 완료 후) |
| 5 | 실전 시범 (정답 없는 신규 사업 — **환26-09 청주 대덕리, 정답지 봉인**) | ⬜ 10월 실무자 미팅 이후 |
| 6 | 전체 보고서 통합 · 웹 기반 운영 | ⬜ 미착수 |

카테고리 확장(재해영향평가 등)은 구조상 준비돼 있다 — `rules/{카테고리}/` 를 추가하면 된다. 내용은 그 카테고리 골든셋 분석에서 나온다.

---

## 개발 환경

- Python 3.10+, 가상환경 `.venv/`
- **Windows + 한글 프로그램 필요**: `generate.py`(생성) · `build_template.py`(베이스 문서) · `to_pdf.py`(육안 검증)
- **플랫폼 무관**: `calc*.py`(계산·자체검증) · `stats_*.py`·`xlsx_grid.py`·`hwpx_table.py`(통계 소싱) · `figure_overlay.py`(삽도) · `fill_report.py` · `extract.py` · `catalog/*`(NAS 조사)
- 원본 HWP/PDF/JPG는 `raw_data/` (git 제외)
- Python XML 직접 조작은 파일 무결성 문제로 금지 — 한글 API만 사용 (`rules/hwpx.md`)

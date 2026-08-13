---
name: nas-survey
description: NAS 재조사 — 전수 크롤 → 스냅샷 diff → 변경 리포트 (8월 말까지 주기 운영)
---

# NAS 재조사 워크플로우

> NAS 는 2026-08 말까지 지속 업로드 중이다. 재조사 요청이 오면 **전체 트리를 전수로**
> 다시 크롤한다 (부분 크롤 금지 — diff 가 전체에서 일어난다). 도구 상세는 각 스크립트
> docstring, 조사 이력은 `catalog/review/nas_survey_*.md`.

## 절차

### 1단계 — 전수 크롤 (30분~1시간, 백그라운드 권장)

```
python3 catalog/crawl_full.py
```

- 최상위 폴더별 분할 + 병렬 8 + **재개 가능** (part 저장: `raw_data/nas_crawl/{날짜}/`)
- 진행은 stdout 에 실시간 표시. 중단돼도 재실행하면 이어받는다
- QuickConnect 릴레이 경유뿐이다 (직결 포트 닫힘 확인, 08-13) — 느린 것은 감수

### 2단계 — diff

```
python3 catalog/nas_diff.py catalog/data/nas_index_new.json.gz
```

- 기준(현행 `catalog/data/nas_index.json.gz`) 대비 추가/삭제/변경 목록 →
  `catalog/review/nas_diff_{날짜}.md`
- **★ = 보고서류(hwp/hwpx), † = 파트 번호 파일명** — 이것부터 본다

### 3단계 — 해석·반영

- ★ 신규 보고서류 → 골든셋 후보·신규 사업 여부 판단, 필요 시 CLAUDE.md 자료 소재 갱신
- **환26 계열 사업 폴더에 인풋(성적서·지역개황·엑셀) 도착 여부 확인** — 실전 시범 추적 (CLAUDE.md 할 일 6)
- 큰 구조 변화(폴더 대량 이동·신규 최상위)면 조사 리포트(`nas_survey_{날짜}.md`)를 남긴다

### 4단계 — 기준 교체

```
python3 catalog/nas_diff.py catalog/data/nas_index_new.json.gz --promote
```

검토가 끝났을 때만. promote 하면 이 스냅샷이 다음 diff 의 기준이 된다.

## 주의

- ⚠️ **깊이 조건이 다른 스냅샷끼리 비교 금지** — depth 제한 스냅샷과 전수를 비교하면
  "전부 신규"로 왜곡된다 (7/21 인덱스가 depth-3 이라 실제로 겪었다)
- 카탈로그 재빌드(`build_catalog.py`)는 이 절차와 별개 — v2 는 업로드 완료(8월 말) 후 (CLAUDE.md 할 일 5)
- 스냅샷은 .gz 로만 커밋한다 (전수 70MB+ → 압축 ~10MB)

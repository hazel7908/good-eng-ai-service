# Windows 세션 안내 — 옛 기록 (6단계·소음진동)

> ## ⚠️ 2026-08-25 — **이 문서는 지나간 작업이다**
>
> 여기 적힌 6단계(소음진동 베이스)와 청양 재측정은 **모두 끝났다.**
>
> **지금 Windows 세션의 할 일은 지역개황 베이스 + 표 편집**이다.
> → **[`20260825_윈도우_지역개황_베이스.md`](20260825_윈도우_지역개황_베이스.md)**
> 그 문서 하나만 따라가면 된다 (환경 준비 포함).
>
> 아래는 소음진동 때의 기록이라 **참고용으로만** 남긴다.

# Windows 세션 안내 — 6단계(베이스 문서) + 재측정

> ## ⚠️ 2026-08-03 — 이 문서의 6단계는 **완료됐다**
>
> **다음 Windows 세션의 할 일은 청양 매곡리 생성·검증**이다.
> → **[`cases/small-env/청양_매곡리/noise-vib/pre-generation.md`](../cases/small-env/청양_매곡리/noise-vib/pre-generation.md)**
> 실행 명령·예상 출력표·미리 특정해 둔 문제 3가지가 거기 있다.
> 아래 §0(환경 준비)만 이 문서에서 쓰고, 나머지는 위 지시서를 따를 것.

---

> **목표**: 원주 골든셋에 빈칸을 뚫어 베이스 문서를 만들고, 괴산을 재생성해 **2차 PoC 44.3% 대비 얼마나 올랐는지 측정**한다.
> **작성**: 2026-07-29 · Mac에서 준비를 끝낸 상태 · **6단계 완료 2026-07-31**

---

## 0. 준비 — 5분

```powershell
git clone https://github.com/hazel7908/good-eng-ai-service.git
cd good-eng-ai-service
git checkout develop
git pull

python -m venv .venv
.venv\Scripts\activate
pip install pywin32 Pillow
```

**환경 확인** (한글 프로그램 없이도 돌아간다):

```powershell
python engine\calc.py
python engine\generate.py small-env noise-vib 괴산_금신리 --dry-run
```

- `calc.py` → `전부 통과 ✅` 가 나와야 한다. 안 나오면 여기서 멈추고 알릴 것
- `--dry-run` → 치환값 29개 + 확인 필요 8건이 출력된다

**필요한 것**:
- 한글 프로그램 (HWP)
- 삽도 JPG 2개 — `소음진동 측정지점.jpg`, `대기, 소음진동 영향예측지점.jpg`
  (`raw_data/` 는 git 제외라 따로 준비해야 한다. **없어도 이미지 교체만 건너뛰고 진행 가능**)

---

## 1. 빈칸 뚫기 — 이번 세션의 핵심 ★

**작업 지시서**: `templates/small-env/noise-vib.slots.md`

```powershell
copy golden\small-env\원주_무장리\원본.hwpx templates\small-env\noise-vib.hwpx
```

한글로 `templates\small-env\noise-vib.hwpx` 를 열고, 지시서 **A절 표의 18개 항목**을 찾기/바꾸기 한다.

| 꼭 지킬 것 | 이유 |
|---|---|
| **골든셋에서 문자열을 복사**해 붙여넣기 | 가운뎃점이 3종(`·` `ㆍ` `․`)이라 손으로 치면 매칭 실패 |
| **B절 표는 건드리지 않는다** | 엔진이 앵커 문자열로 셀을 찾는다. 지우면 실패 |
| `45.0dB(A)` 는 **숫자만** 토큰으로 | 단위까지 넣으면 출력에 단위가 빠진다 |
| **이미지를 지우지 않는다** | 자리를 유지해야 ZIP 후처리로 교체된다 |

저장 후 확인 (Mac/Windows 무관):

```powershell
python engine\extract.py templates\small-env\noise-vib.hwpx | findstr /R "{{"
```

토큰 15종이 나와야 한다 (지시서 D절 목록과 대조).

> **이 산출물만 만들어두면 이번 세션의 절반은 성공이다.** 이후 엔진이 몇 번 실패해도 다시 돌리면 되지만, 이 파일은 수작업이라 다시 만들기 번거롭다. **만들자마자 커밋할 것.**

```powershell
git add templates\small-env\noise-vib.hwpx
git commit -m "6단계 — 원주 골든셋에서 베이스 문서 도출"
git push
```

---

## 2. 생성

```powershell
taskkill /f /im Hwp.exe
python engine\generate.py small-env noise-vib 괴산_금신리 --raw-dir "<삽도 폴더 경로>"
```

삽도가 없으면 `--raw-dir` 를 빼고 실행한다.

**⚠️ 이 스크립트는 win32com 으로 한 번도 실행된 적이 없다.** Mac에서 리팩터링만 했고 문법·계산은 검증했으나 한글 API 호출은 미검증이다. **1~2회 오류가 날 것으로 예상**하고, 나면 그대로 알려주면 된다.

성공하면 마지막에 이렇게 나온다:
```
빈칸 잔여 없음 ✅
⚠️ '[확인 필요]' 가 문서에 남아 있다 — 실무자 입력 필요
```
두 번째 줄은 정상이다 (조사시기·시설명 등 인풋에 없는 값).

출력: `cases\small-env\괴산_금신리\noise-vib\output.hwpx`

---

## 3. 검증 — 진짜 목표

```
/validate-report small-env noise-vib 괴산_금신리
```

`golden/small-env/괴산_금신리/noise-vib.txt` 와 대조해 **판정별 집계**를 낸다.

**비교 기준선** (2차 PoC, `docs/poc_hwpx_comparison.md`):

| 판정 | 건수 | 비율 |
|---|--:|--:|
| OK | 27 | **44.3%** |
| WRONG | 19 | 31.1% |
| MISSING | 7 | 11.5% |
| UNAVAIL | 4 | 6.6% |
| MINOR | 3 | 4.9% |
| EXTRA | 1 | 1.6% |

### 이번에 오를 것으로 기대하는 것

규칙 수정으로 **약 12건**이 잡힐 것으로 본다:

| 고친 것 | 관련 오류 |
|---|--:|
| R1 주거 진동 기준 70 → 65 | 예측진동도 전 행 |
| R2 목표기준 지역 문자 | Critical 1건 |
| R3 저감량 계산 (①재계산 / ②단순감산) | Critical 4건 |
| R4 진동 감쇠계수 16.17 → 16.2 | 표 24 + 예측진동도 |
| 표 24 검색 앵커 교정 | Critical 1건 |
| 표기 규칙 (`25m`, `09월 19일`, `미미할`) | Minor 3건 |
| 표 안 텍스트 치환 | Major 1건 |

### 안 오를 것 — 미리 알고 있어야 실망하지 않는다

| 원인 | 건수 | 왜 |
|---|--:|---|
| **삽도 추출 부정확** | **10** | 지식·코드로 해결 불가. GIS/실무자 입력 필요 |
| 인풋 자료 부재 | 3 | 조사시기·작업량은 원천적으로 인풋에 없다 |
| 셀 서식 미구현 | 3 | 법령표 볼드/음영은 아직 코드가 없다 |

**PP 이격거리를 일부러 PoC 추출값 그대로 뒀다** (`220/150/500/600`, 정답은 `225/151/505/595`). 정답으로 고치면 점수는 오르지만 **개선을 측정할 수 없게 된다.**

> 그래서 현실적 기대치는 **44% → 60% 안팎**이다. 80%대는 삽도 문제를 풀어야 나온다.

---

## 4. 검증 후 — 되먹임

`/validate-report` 5단계가 지시하는 대로:

1. 새 오류 → `rules/small-env/noise-vib.md` §6 오류 레지스트리
2. 규칙 자체가 틀렸으면 → `golden/small-env/_variants.md` 로 5건 대조 후 수정, **`(n/5)` 표기**
3. 규칙을 고쳤으면 **스킬도 점검** (값이 스킬에 박혀 있으면 잘못된 자리)

결과는 `cases/small-env/괴산_금신리/noise-vib/validation.md` 에 남긴다.

---

## 막히면

| 증상 | 확인 |
|---|---|
| `calc.py` 실패 | 규칙과 코드가 어긋난 것. **여기서 멈추고 보고** |
| `빈칸 잔여` 경고 | 토큰 이름 오타. `slots.md` D절 목록과 대조 |
| `커서가 테이블 밖` 경고 | 앵커 문자열을 실수로 지웠다. 1단계 B절 참조 |
| 표 데이터 침범 | 검색 앵커 충돌. `구분(m)` 은 표 21·24 둘 다 있어 `skip` 에 의존 |
| 한글이 안 뜸 | `taskkill /f /im Hwp.exe` 후 재시도 |

**세션 시작할 때 Claude Code에 이렇게 말하면 된다:**

```
docs/windows_session.md 읽고 6단계부터 진행해줘
```

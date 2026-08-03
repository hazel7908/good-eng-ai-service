---
name: validate-report
description: 생성된 HWPX 보고서를 정답지와 비교 검증
argument-hint: "[카테고리] [파트] [사업] (예: small-env noise-vib 괴산_금신리)"
---

# 보고서 검증 워크플로우

> **이 문서는 절차만 담는다.** 판정 기준값·표 번호·계산 방식은 파트 rule에 있다 (`knowledge_architecture.md` §5).

## 전제 조건

- 생성 결과: `cases/{카테고리}/{사업}/{파트}/output.hwpx`
- 정답지: `golden/{카테고리}/{사업}/{파트}.txt`

**`golden/` 에 짝이 있는 사업에서만 자동 비교가 성립한다.** 없으면(신규 납품) 사람이 검토한다.

> **`golden/` 을 여는 것은 이 스킬뿐이다.** 생성 절차에서는 한 번도 열리지 않는다.

## 실행 절차

### 1단계 — 결과물 텍스트 추출

```python
import zipfile, re, xml.etree.ElementTree as ET
z = zipfile.ZipFile(hwpx_path)
secs = sorted(n for n in z.namelist() if re.match(r'Contents/section\d+\.xml$', n))
lines = []
for s in secs:
    root = ET.fromstring(z.read(s))
    for p in root.iter():
        if not p.tag.endswith('}p'): continue
        if any(c.tag.endswith('}p') for c in p.iter() if c is not p): continue  # 표를 품은 바깥 문단
        t = ''.join(''.join(e.itertext()) for e in p.iter() if e.tag.endswith('}t'))
        if t.strip(): lines.append(t.strip())
```

> 문단(`}p`) 단위로 모아야 표 셀이 한 줄씩 떨어진다. `e.text` 만 훑으면 순서가 섞인다.

⚠️ **두 줄을 빠뜨리면 오판한다** (2026-07-31 실제 발생):
> - `itertext()` — `e.text` 만 읽으면 `<hp:markpenBegin/>`(형광펜) 같은 **인라인 개체 뒤 글자(`.tail`)를 통째로 잃는다.**
>   `이내(8개 지점)` 이 `이내` 로 보여 **정상 출력을 MISSING 으로 오판**했다.
> - 중첩 문단 제외 — 표를 품은 바깥 문단까지 세면 **표 전체가 한 줄로 뭉쳐** diff가 노이즈로 덮인다.

### 2단계 — 정답지와 대조

섹션별로 매칭해 차이를 분류한다.

| 판정 | 의미 |
|:--:|---|
| **OK** | 정확히 일치 |
| **WRONG** | 변경했으나 값이 틀림 |
| **MISSING** | 변경해야 하나 누락 (**베이스 문서 값이 그대로 남음**) |
| **EXTRA** | 불필요한 변경 |
| **MINOR** | 표기 차이 (의미 동일) |
| **UNAVAIL** | 인풋 자료 한계로 채울 수 없었음 |

**MISSING과 WRONG을 구분해야 한다** — MISSING은 원본 사업(원주 등)의 값이 그대로 남은 것이라 그럴듯해 보여서 놓치기 쉽다. 베이스 문서 원본과도 대조할 것.

### 3단계 — ⚠️ 검색어 함정

문자열로 집계할 때 다음을 확인한다. 놓치면 **오류가 0건으로 잘못 나온다.**

| 함정 | 내용 |
|---|---|
| **판정 낱말** | 보고서는 기준 초과를 **`상회`** 로 쓴다. `초과` 로 검색하면 전부 놓친다 (실제로 5건 모두 0으로 잘못 집계된 적 있음) |
| **가운뎃점 3종** | `·` U+00B7 / `ㆍ` U+318D / `․` U+2024 가 자리별로 다르다. 검색어는 골든셋에서 **복사**할 것 |
| **표 안 텍스트** | 본문에 없고 표 셀에만 있는 문구가 있다 (예: 예측범위 지점 수) |

→ 상세: `rules/{카테고리}/_category.md`

### 4단계 — 결과 문서화

`cases/{카테고리}/{사업}/{파트}/validation.md` 에 작성한다.

- 판정별 집계 + 비율
- **오류 원인 분류** — 무엇이 지식 문제이고 무엇이 데이터/코드 문제인지 나눈다
  (지식으로 못 고치는 것: 삽도 추출 정밀도, 인풋 부재, 서식 미구현)
- 심각도 분류 (Critical / Major / Minor)

### 5단계 — 규칙에 되먹임 ★

검증의 산출물은 리포트가 아니라 **고쳐진 규칙**이다.

1. 새 오류 → 파트 rule의 **오류 레지스트리**에 추가
2. **규칙 자체가 틀린 경우** → `golden/{카테고리}/_variants.md` 로 골든셋 전체를 대조하고 규칙을 고친다
3. 규칙을 고칠 때 **관측 건수 `(n/5)` 를 반드시 적는다**
   - `(1/5)` 는 법칙이 아니라 그 사업의 우연일 수 있다
   - 실제로 괴산 1건에서 일반화된 규칙 3개가 틀린 적 있다
4. **파트 rule을 고쳤으면 스킬도 점검한다**
   - 스킬에 값·계산 방식이 적혀 있으면 그건 **잘못된 자리**다 → rule로 옮기고 스킬은 가리키게만
   - 이 점검이 빠져 스킬이 낡은 규칙을 지시한 전례가 있다

### 6단계 — 육안 확인 (PDF 로 변환해서 본다) ★

**텍스트 대조로는 절대 안 잡히는 결함이 있다.** 2026-08-03 에 처음 눈으로 보고
표 캡션이 표와 쪽 분리되는 Critical 결함을 찾았다 → `docs/layout_review.md`

```powershell
python engine\to_pdf.py cases\{카테고리}\{사업}\{파트}\output.hwpx --out raw_data\review\{사업}.pdf
```

그 다음 페이지를 이미지로 렌더링해 확인한다 (`pypdfium2`. `pymupdf` 는 DLL 로드 실패):

```python
import pypdfium2 as pdfium
pdf = pdfium.PdfDocument(path)
for i in range(len(pdf)):
    pdf[i].render(scale=1.7).to_pil().save(f"p{i+1:02d}.png")
```

**볼 것**:

| 항목 | 놓치기 쉬운 이유 |
|---|---|
| **표 캡션과 표가 같은 쪽에 있는가** | 텍스트 추출에서는 둘 다 있으므로 통과한다 |
| **셀 안 글자가 두 줄로 접혔는가** (`P - 10` 등) | 추출값은 정상이다 |
| 표 행 수 · 잘림 · 겹침 | |
| **법령표의 볼드/음영** — 표 9 는 “가”~“라”, 표 10·11 은 `가/나` (서로 다른 체계) | 서식은 텍스트에 안 남는다 |
| 삽도가 올바른 위치에 들어갔는지 · 왜곡 | |
| 절을 지운 자리(`delete_range`)에 잘린 흔적이 없는지 | |

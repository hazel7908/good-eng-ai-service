---
paths:
  - "engine/**"
  - "templates/**"
---

# HWPX 기술 규칙

## HWPX 파일 구조

HWPX = ZIP 파일. 내부 구조:
```
├── mimetype                    # "application/hwp+zip" (반드시 ZIP_STORED!)
├── META-INF/container.xml
├── Contents/
│   ├── section0.xml            # 본문 (모든 텍스트와 테이블)
│   ├── header.xml              # 머리글
│   └── ...
├── BinData/                    # 이미지 (image1.png, image2.png 등)
└── PrvImage.png                # 미리보기 이미지 (ZIP_STORED!)
```

## XML 구조 (section0.xml)

```xml
<hp:tbl>          <!-- 테이블 -->
  <hp:tr>           <!-- 행 -->
    <hp:tc>           <!-- 셀 -->
      <hp:subList>
        <hp:p>          <!-- 단락 -->
          <hp:run>        <!-- 런 -->
            <hp:t>텍스트</hp:t>
          </hp:run>
        </hp:p>
      </hp:subList>
    </hp:tc>
  </hp:tr>
</hp:tbl>
```

## ❌ Python XML 직접 조작 금지

**이 방식은 중단됨.** Python `ElementTree`로 HWPX의 section0.xml을 파싱→수정→재직렬화하면:
1. 미사용 네임스페이스 선언 제거 (15개 → 3개) → 한글이 파일 거부
2. Self-closing 태그 공백 변환 (`/>` → ` />`)
3. 줄바꿈 정규화 (`\r\n` → `\n`)
4. ZIP 엔트리 순서 변경

개별 패치 가능하나 근본적으로 불안정. **한글 API 방식만 사용할 것.**

## ✅ 한글 API (win32com) 패턴

### 기본 사용법

```python
import win32com.client
hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.XHwpWindows.Item(0).Visible = False
hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
hwp.Open(template_path)
```

### 찾기/바꾸기

```python
hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
p = hwp.HParameterSet.HFindReplace
p.FindString = "원주시 호저면"
p.ReplaceString = "괴산군 청안면"
p.IgnoreMessage = 1
p.Direction = hwp.FindDir("AllDoc")
hwp.HAction.Execute("AllReplace", p.HSet)
```

### 테이블 셀 이동

```python
hwp.HAction.Run("TableRightCell")   # 오른쪽 셀
hwp.HAction.Run("TableLowerCell")   # 아래 셀
hwp.HAction.Run("TableColBegin")    # 열 시작
hwp.HAction.Run("TableRowEnd")      # 행 끝
hwp.HAction.Run("TableAppendRow")   # 행 추가
```

### 셀 내용 교체

```python
hwp.HAction.Run("SelectAll")
hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
hwp.HParameterSet.HInsertText.Text = "새 텍스트"
hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
```

### 저장 후 반드시 대기

```python
hwp.SaveAs(output_path, "HWPX")
hwp.Quit()
time.sleep(2)  # 한글 프로세스 완전 종료 대기 (없으면 PermissionError)
```

### 이미지 교체 (ZIP 후처리)

한글 API로 저장한 뒤, HWPX(ZIP)를 열어 BinData 내 이미지를 교체.
- JPG → PNG 변환 필요 (Pillow 사용)
- 원본 압축 설정(ZIP_STORED) 보존
- 대소문자 무시 매핑 필요 (한글 API가 .png → .PNG로 변경할 수 있음)

## 🚨 검증 원칙 — 검사와 수정은 **다른 근거**를 써야 한다 (2026-08-24)

### 무슨 일이 있었나

천안 지역개황에 **원주 삽도 14장**(수계모식도·현장사진 등)이 실려 나갔다.
고치려고 `blank_figures()` 와 `check_stale_figures()` 를 같이 만들었는데,
**둘이 같은 pic→이름 매핑을 썼다.** 그 매핑이 틀렸다:

```python
ids   = re.findall(r'binaryItemIDRef="(image\d+)"', sec)   # 30개
names = re.findall(r'원본 그림의 이름: (...)', sec)           # 16개  ← 이름 없는 그림이 섞여 있다
zip(ids, names)        # ❌ 순서로 짝지으면 통째로 밀린다
```

결과 — **엉뚱한 그림 13장을 지우고 진짜 원주 삽도는 그대로 뒀는데,**
검사는 같은 매핑을 쓰므로 `삽도 잔존 없음 ✅` 을 냈다. **PDF 를 눈으로 보고서야 잡혔다.**

### 규칙

1. **검사는 수정과 다른 근거로 판정한다.** 같은 가정을 공유하면 둘이 같이 틀린다.
   `check_stale_figures()` 는 이제 매핑을 안 쓰고 **바이트 비교 + 크기**만 본다.
2. **두 근거가 어긋나면 그것이 경보다.** 매핑 기준과 크기 기준이 다르면 경고를 낸다.
3. **그림·레이아웃을 건드렸으면 PDF 육안 확인 전에는 통과시키지 않는다.**
   삽도는 텍스트 대조·빈칸 검사·정확도 측정에 **전부 안 걸린다.**
4. `hp:pic` 안의 값은 **블록 단위로 함께 읽는다.** 문서 전체에서 각각 뽑아 순서로 짝짓지 않는다.
5. **전제가 바뀌면 검사도 다시 쓴다.** 같은 날 두 번 데였다 —
   ① 매핑을 고쳤는데 검사가 옛 매핑을 써서 **거짓 통과**
   ② 템플릿을 비웠는데 검사가 "베이스와 동일 = 다른 사업 그림" 전제를 유지해
      플레이스홀더 16장을 **거짓 경보**했다 (`0.00MB` 를 "300KB 이상"이라고 찍었다).
   거짓 경보가 일상이 되면 **진짜 경보를 놓친다.** 고칠 때 검사도 같이 연다.

### 삽도는 베이스 단계에서 걷어낸다

기준 사업 그림을 지우는 자리는 **생성(`generate.py`)이 아니라 베이스 빌더**다
(`build_template.strip_figures()` · `slots.md` §D). 증상이 보이는 자리(생성물)에서
막았다가 저장소에 원주 축사 사진이 계속 남았다.

| | 잘못된 자리 | 맞는 자리 |
|---|--:|--:|
| 지역개황 베이스 | 51.8MB | **1.3MB** |
| 저장소의 기준 사업 사진 | 남는다 | 없다 |
| 매 생성 | 20장 지움 | 불필요 |

생성 쪽에는 **회귀 감시만** 남긴다 (`check_figures()`) — 베이스에 큰 그림이 살아 있으면
빌더가 놓친 것이므로 경고한다. 작은 플레이스홀더가 남은 것은 정상(아직 안 채운 삽도)이다.

> 이미 같은 함정을 다른 형태로 겪었다 — *"골든셋이 전부 같은 답이면 검증이 통과해도 약하다"*
> (`regional-overview.md` 생태자연도 8/8). **통과했다는 것이 맞다는 뜻이 아니다.**

---

## PoC에서 발견된 기술적 함정

### ★ 찾기/바꾸기는 **런 경계를 넘지 못한다** (2026-08-25 실증)

한 문단이라도 글자모양이 다르면 XML 이 `<hp:run>` 여럿으로 갈린다. **찾을 문자열이
두 런에 걸치면 치환이 조용히 실패한다** — 예외도 경고도 없다.

```
원본 문단 (런 3개)
  [0] '원주시는 고속도로 86,011m, … 총 도로연장 1,219,327m로 포장율은 '
  [1] '98.25'                      ← 숫자만 다른 글자모양
  [2] '%인 것으로 조사되었다.'
```

`포장율은 98.25%인` 으로 찾으면 **안 바뀐다.** 런 [0] 안에서 끝나게 자르고,
`98.25` 는 따로 바꾼다.

> **숫자·날짜가 별도 런인 경우가 많다.** 문서를 만든 사람이 그 부분만 다시 입력했거나
> 서식을 손봤기 때문이다. 긴 문장을 통째로 잡을수록 걸릴 확률이 올라간다.

**검사도 런 단위로 해야 한다.** `build_template.check()` 는 `<hp:t>` 를 **줄바꿈으로
이어** 붙인다 — 런을 넘는 문자열은 찾지 못하게 해서 실패를 미리 잡는다.
문단 텍스트로 이어 붙이면 **한글이 못 바꾸는 것을 통과시킨다.**

### ★ 치환 목록은 **순서가 의미를 바꾼다** (2026-08-25 실증)

`REPLACE` 는 위에서 아래로 돈다. 앞선 치환이 만든 결과 위에서 다음 치환이 돈다.

```
… ("무장리", "{{리}}"),                                  ← 먼저 돌면
  ("… 본 사업계획지구가 위치한 호저면 무장리는 …", "…"),   ← 이건 이미 못 찾는다
```

지명처럼 **짧고 널리 퍼진 치환은 맨 뒤**에 두고, 그 지명을 포함하는 **긴 문장 치환은
반드시 앞**에 둔다.

⚠️ **`check()` 는 이것을 못 잡는다.** 원본을 보고 판정하므로 OK 를 낸다.
치환 시점의 텍스트는 이미 달라져 있다. **빌더 끝의 토큰 대조가 마지막 방어선이다.**

### find_in_table 검색어 충돌

"진동레벨(dB(V))"로 검색하면 Table 24(이격거리별 진동도)가 아닌 Table 23(합성진동레벨)의 "합성진동레벨(dB(V))" 헤더가 먼저 매칭됨.
→ 검색어를 더 구체적으로 지정하거나, 테이블 순서를 고려한 skip 파라미터 사용

**2026-08-24 재발 — 이번엔 조용히 다른 표를 망쳤다.**
지역개황 2.7.1 하수처리표를 고치려고 소재지 `가곡리` 를 앵커로 썼는데,
`가곡리` 가 **2.3.2 배출시설 설치제한지역 표의 대상지역 목록**에도 있었다
(`지정면,(보통리, 가곡리, 안창리)`). 거기가 먼저 걸려 값이 엉뚱한 표에 박혔고,
**로그는 정상으로 찍혔다** — 결과 문서를 열어보기 전까지 알 수 없다.

→ **앵커를 쓰기 전에 원본에서 출현 횟수를 센다.**

```python
txt.count(anchor)   # 1 이 아니면 더 길게 잡거나 skip= 을 준다
```

지번까지 붙이면 대개 유일해진다 (`가곡리` 2회 → `가곡리 711-8` 1회).
→ **셀을 고친 뒤에는 반드시 결과 문서에서 값의 위치를 검산할 것.**

**앵커는 셀이 아니라 문단 단위로 고른다.** 표 머리 셀은 줄을 나눠 쓰는 일이 흔한데,
XML 에서는 **문단이 갈린다.** `정수처리적용방식` 은 눈에 그렇게 보여도 실제로는
`정수처리` / `적용방식` 두 문단이라 찾기가 실패한다 (에러 없이 `못 찾음` 경고만 뜬다).

```python
# 표 셀 문단을 뽑아 후보의 유일성을 센다
paras = [문단텍스트 for tc in root.iter(tc) for p in tc.iter(p)]
sum(1 for x in paras if anchor in x)   # 1 이어야 한다
```
### ★ 병합 표는 `KeyIndicator()` 로 셀 주소를 읽어 채운다 (2026-08-24 해결)

세로 병합이 있으면 **행마다 칸 수가 다르다.** 지역개황 산업단지 표는 `구분`(일반/농공)이
그룹마다 병합돼 행1·행10 만 6칸이고 나머지는 5칸이다. 왼쪽부터 채우면 한 칸씩 밀리고,
`TableRowEnd` 기준 오른쪽 정렬은 **이전 행 머리까지 덮었다.** 둘 다 실측으로 실패했다.

**해법은 칸을 세지 않는 것이다.** `KeyIndicator()` 의 마지막 항목이 셀 주소를 준다:

```python
hwp.KeyIndicator()      # (True, 3, 1, 28, 1, 1, 9, 0, '(E1): 문자 입력')

def cell_addr(hwp):
    m = re.match(r'\(([A-Z]+)(\d+)\)', str(hwp.KeyIndicator()[-1]))
    return (m.group(1), int(m.group(2))) if m else None
```

오른쪽으로 걸으며 주소를 찍어 보면 병합 동작이 그대로 보인다:

```
행2:  A2 B2 C2 D2 E2 F2
행3:  A2 ← 병합 칸을 다시 지난다   B3 C3 D3 E3 F3
행4:  A2                          B4 C4 D4 E4 F4
```

**병합 칸은 자기 원래 행 번호를 알려준다.** 그래서 행을 왼쪽부터 걸으며
`row == 목표행` 인 칸에만 쓰면 병합과 무관하게 정확히 맞는다 — 칸 수를 알 필요가 없다.
목표 행 번호도 `down(n)` 뒤에 주소를 읽어 얻으면 되므로 짐작이 들어가지 않는다.

→ `generate.py` 의 `fill_by_col(hwp, anchor, row_off, {'C': 값, 'D': 값})`
### 스마트 따옴표 (Unicode)

한글 프로그램 내부에서 '가'의 따옴표는 일반 따옴표(')가 아닌 유니코드 스마트 따옴표(\u2018, \u2019).
FindReplace에서 반드시 유니코드 문자를 사용해야 매칭됨.

### HWP 프로세스 재사용 불가

이전 실행에서 한글 프로세스가 남아있으면 `gencache.EnsureDispatch` 실패.
실행 전 `taskkill /f /im Hwp.exe` 권장.

### ⚠️ 강제 종료가 `gen_py` 캐시를 깨뜨린다 (2026-08-24 실증)

`taskkill /F` 로 한글을 죽이면 win32com 의 타입 라이브러리 캐시가 **반쯤 생성된 상태로 남는다.**
다음 실행은 에러 없이 **`hwp.Open()` 에서 멎는다** — 프로세스는 `Responding=True` 이고
CPU 는 분당 1초씩만 오른다. 대화상자로 오해하기 쉽다.

진짜 예외는 한참 뒤에야 뜬다:

```
FileNotFoundError: ...\Temp\gen_py\3.12\{CLSID}x0x1x0\HAction.py.NNNNN.temp
```

**해법 — 캐시를 통째로 지우면 재생성된다:**

```bash
taskkill //F //IM Hwp.exe
rm -rf "$LOCALAPPDATA/Temp/gen_py"
```

지운 뒤 `EnsureDispatch` 1.7초 · `Open` 152초로 정상 복귀했다 (52MB 지역개황 베이스 기준).

> 💡 **진단 요령**: 오래 걸리는 것과 막힌 것을 CPU 로 가른다.
> `Get-Process Hwp | Select CPU` 가 **분당 1초 수준이면 막힌 것**이고, 실제 작업 중이면 훨씬 빨리 오른다.

### ⚠️ 로그를 파이프로 넘기지 말 것

`python build_template.py ... | tail -40` 은 **진행 로그를 버퍼에 가둔다.** 멎었을 때
어디서 멎었는지 알 수 없다. 긴 작업은 `python -u ... > 로그파일` 로 흘리고 파일을 본다.

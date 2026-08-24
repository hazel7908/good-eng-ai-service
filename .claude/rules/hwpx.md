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

## PoC에서 발견된 기술적 함정

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

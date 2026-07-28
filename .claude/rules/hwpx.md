---
paths:
  - "scripts/**"
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

### 스마트 따옴표 (Unicode)

한글 프로그램 내부에서 '가'의 따옴표는 일반 따옴표(')가 아닌 유니코드 스마트 따옴표(\u2018, \u2019).
FindReplace에서 반드시 유니코드 문자를 사용해야 매칭됨.

### HWP 프로세스 재사용 불가

이전 실행에서 한글 프로세스가 남아있으면 `gencache.EnsureDispatch` 실패.
실행 전 `taskkill /f /im Hwp.exe` 권장.

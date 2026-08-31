#!/usr/bin/env python3
"""한글 API 공용 유틸 — generate.py 와 engine/parts/*/*.py 가 함께 쓴다.

2026-08-31 R1 리팩터로 generate.py 에서 분리했다 (로직 변경 없음 — 위치만).
hwp 인자를 받는 함수는 Windows + 한글 전용이지만, 모듈 import 자체는 어디서나 된다.
기술 규칙: .claude/rules/hwpx.md
"""
import io
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLACEHOLDER = "{{%s}}"          # 베이스 문서의 빈칸 표기
MISSING = "[확인 필요]"          # 값이 없을 때 출력할 문자열
MODELING = "[모델링 필요]"       # AERMOD 출력이 없을 때 (대기질 rule §2-5)


# ============================================================
# 세션 열기·닫기 — 2026-08-31 회귀에서 얻은 방어 3종
# ============================================================
def console_utf8():
    """표준 출력을 UTF-8 로 고정한다.

    ⚠️ **cp949 에는 em-dash(—, U+2014) 가 없다.** 파이프로 실행하면 콘솔 인코딩이
    cp949 가 되고, 진행 로그 한 줄(`표 6 — 소음측정결과`)이 UnicodeEncodeError 를
    던져 **생성이 표 편집 도중에 죽는다.** 로그 한 글자가 산출물을 날리는 셈이라
    출력 인코딩을 아예 고정한다 (2026-08-31 실측 — 아래 open_hwp 주석과 한 사건).
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _hwp_running():
    """한글 프로세스가 아직 살아 있는가 (tasklist — 추가 의존성 없이)."""
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Hwp.exe", "/NH"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
    except Exception:
        return False                      # 셀 수 없으면 기다리지 않는다
    return "Hwp.exe" in (r.stdout or "")


def quit_hwp(hwp, timeout=40):
    """한글을 닫고 **프로세스가 실제로 사라질 때까지** 기다린다.

    🚨 `Quit()` 은 곧바로 돌아오지만 프로세스는 몇 초 더 살아 있다. 그 사이에 다음
    단계가 같은 파일을 열면 **`Open()` 이 영영 안 끝난다** (2026-08-31 실측 —
    build_template 의 keep_captions_with_table 이 10분 넘게 멈춰 있었다. to_pdf 도
    같은 자리에서 한 번 걸렸다). 예전 `time.sleep(2)` 로는 모자란다.

    ⚠️ 사람이 한글을 따로 띄워 두었으면 여기서 timeout 만큼 기다렸다가 그냥 넘어간다
    (판별할 방법이 없다). 자동화 중에는 한글을 열어 두지 말 것.
    """
    try:
        hwp.Quit()
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _hwp_running():
            time.sleep(1.0)               # 파일 핸들 반환 여유
            return True
        time.sleep(0.5)
    print(f"  ⚠️ 한글 프로세스가 {timeout}초 안에 안 닫혔다 — 다음 열기가 막힐 수 있다")
    return False


def open_hwp(path, visible=False):
    """한글을 띄우고 문서를 연다 — **편집 가능 상태임을 확인하고** 넘긴다.

    🚨 **읽기 전용이면 표 편집이 조용히 전부 무시된다** (2026-08-31 실측).
    `EditMode == 0` 일 때 `InsertText`·`AllReplace` 는 **정상 동작하는데**
    `Table*` 액션(`TableRightCell`·`TableLowerCell`·`TableColBegin`·`TableAppendRow`)
    만 `False` 를 돌려주고 아무 일도 안 한다. 그 결과가 최악이다 —
    빈칸은 다 채워지고 표만 **기준 사업(원주) 값 그대로** 남는다. 경고도 없고
    `빈칸 잔여 0` 도 통과한다. 실제로 천안 소음진동 표 6·7·14·21·22·24·25 가
    전부 원주 값으로 나갔다 (앵커 셀에는 마지막 값이 덮여 `21.2`·`[확인 필요]`).

    원인은 **앞선 실행이 남긴 한글 프로세스**다. 생성이 도중에 죽으면 `Quit()` 이
    안 불려 한글이 템플릿을 붙든 채 살아남고, 다음 실행은 같은 파일을 **읽기 전용**
    으로 연다. 그래서 여기서 EditMode 를 확인하고 되돌린다.
    """
    import win32com.client
    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = visible
    hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
    hwp.Open(str(path))
    try:
        mode = hwp.EditMode
    except Exception:
        return hwp                      # 속성이 없는 버전이면 확인을 건너뛴다
    if mode != 1:
        print("  ⚠️ 문서가 읽기 전용으로 열렸다 (EditMode=0) — 표 편집이 통째로 무시된다.")
        print("     앞선 실행이 남긴 한글 프로세스가 이 파일을 붙들고 있을 때 그렇다.")
        print("     되돌리는 중… (근본 해결: taskkill /F /IM Hwp.exe)")
        try:
            hwp.EditMode = 1
        except Exception as e:
            print(f"     EditMode 설정 실패: {e}")
        if getattr(hwp, "EditMode", 0) != 1:
            hwp.Quit()
            sys.exit("ERROR: 편집 불가 상태다. 한글을 모두 닫고 다시 실행할 것 "
                     "— 이대로 두면 표가 기준 사업 값으로 나간다")
        print("     ✅ 편집 가능 상태로 되돌렸다")
    return hwp


# ============================================================
# 한글 API 유틸리티
# ============================================================
def fr(hwp, old, new):
    """전체 문서 찾기/바꾸기"""
    hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
    p = hwp.HParameterSet.HFindReplace
    p.FindString, p.ReplaceString = old, new
    p.IgnoreMessage = 1
    p.Direction = hwp.FindDir("AllDoc")
    p.FindType = 0
    hwp.HAction.Execute("AllReplace", p.HSet)


def find_fwd(hwp, text):
    hwp.HAction.GetDefault("RepeatFind", hwp.HParameterSet.HFindReplace.HSet)
    p = hwp.HParameterSet.HFindReplace
    p.FindString = text
    p.Direction = hwp.FindDir("Forward")
    p.FindType = 0
    p.IgnoreMessage = 1
    return hwp.HAction.Execute("RepeatFind", p.HSet)


def in_table(hwp):
    return hwp.GetPos()[0] > 0


def find_in_table(hwp, text, skip=0):
    """테이블 셀 안에서 텍스트를 찾을 때까지 반복 검색.
    skip: 부분매칭 회피용 (예: 'V - 1' 이 'N·V - 1' 에 먼저 걸린다)
    """
    hwp.MovePos(2)
    hit = 0
    for _ in range(30):
        if not find_fwd(hwp, text):
            return False
        if in_table(hwp):
            if hit < skip:
                hit += 1
                continue
            return True
    return False


def set_cell(hwp, text):
    if not in_table(hwp):
        print(f"    WARNING: 커서가 테이블 밖 — '{str(text)[:20]}' 스킵")
        return False
    hwp.HAction.Run("SelectAll")
    hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
    hwp.HParameterSet.HInsertText.Text = str(text)
    hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
    return True


def right(hwp, n=1):
    for _ in range(n): hwp.HAction.Run("TableRightCell")


def down(hwp, n=1):
    for _ in range(n): hwp.HAction.Run("TableLowerCell")


def col_begin(hwp):
    hwp.HAction.Run("TableColBegin")


def fill_row(hwp, values):
    for i, v in enumerate(values):
        if i > 0: right(hwp)
        set_cell(hwp, v)


def delete_range(hwp, start_anchor, end_anchor):
    """start_anchor 가 있는 문단 처음부터 end_anchor 문단 직전까지 통째로 지운다.

    표를 품은 구간도 함께 지워진다. 사업마다 절이 통째로 빠지는 경우가 있어 필요하다
    (rule §4-1 — 상회 0건이면 저감 2)·3)·4) 절이 없다).
    """
    hwp.MovePos(2)
    if not find_fwd(hwp, start_anchor):
        print(f"    WARNING: 시작 앵커 '{start_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    s = hwp.GetPos()
    if not find_fwd(hwp, end_anchor):
        print(f"    WARNING: 끝 앵커 '{end_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    e = hwp.GetPos()
    if s[0] != e[0]:
        print(f"    WARNING: 두 앵커가 서로 다른 리스트에 있다 {s[0]}≠{e[0]}")
        return False
    hwp.SelectText(s[1], s[2], e[1], e[2])
    hwp.HAction.Run("Delete")
    return True


def set_bold(hwp, on):
    hwp.HAction.GetDefault("CharShape", hwp.HParameterSet.HCharShape.HSet)
    hwp.HParameterSet.HCharShape.Bold = 1 if on else 0
    hwp.HAction.Execute("CharShape", hwp.HParameterSet.HCharShape.HSet)


def set_text_color(hwp, color):
    """현재 선택 영역의 글자 색. 선택이 없으면 커서 위치의 기본값만 바뀐다."""
    hwp.HAction.GetDefault("CharShape", hwp.HParameterSet.HCharShape.HSet)
    hwp.HParameterSet.HCharShape.TextColor = color
    hwp.HAction.Execute("CharShape", hwp.HParameterSet.HCharShape.HSet)


def color_markers(hwp, texts, color=None, limit=2000):
    """`[확인 필요]`·`[모델링 필요]` 를 빨간 글자로 바꾼다 (미팅 요청 4, 08-13).

    찾기(`RepeatFind`)는 일치 구간을 **선택 상태로** 남기므로 그 위에 CharShape 를
    적용하면 글꼴·크기는 그대로 두고 색만 바뀐다. 찾기/바꾸기의 `ReplaceCharShape`
    를 쓰지 않는 이유가 이것이다 — 그쪽은 기본 글자모양을 통째로 덮어쓴다.
    """
    if color is None:
        color = hwp.RGBColor(255, 0, 0)
    total = 0
    for t in texts:
        hwp.HAction.Run("MoveDocBegin")
        n, last = 0, None
        while n < limit and find_fwd(hwp, t):
            pos = hwp.GetPos()
            if pos == last:                 # 커서가 안 움직이면 순환이다
                break
            last = pos
            set_text_color(hwp, color)
            n += 1
        if n:
            print(f"  '{t}' {n}건 빨강 처리")
        total += n
    return total


def bold_row(hwp, anchor, ncells, on, skip=0):
    """앵커 셀부터 오른쪽으로 ncells 칸의 글자를 굵게/보통으로 바꾼다."""
    if not find_in_table(hwp, anchor, skip=skip):
        print(f"    WARNING: 법령표 앵커 '{anchor}' 못 찾음")
        return False
    for i in range(ncells):
        if i:
            right(hwp)
        hwp.HAction.Run("SelectAll")
        set_bold(hwp, on)
    return True


SHADE = 0xE5E5E5        # 베이스 문서 법령표의 음영 색 (header.xml winBrush faceColor)


def cell_fill(hwp, color):
    """현재 셀의 면 색. color=None 이면 채우기 없음.

    셀 블록(`TableCellBlock`)이 잡혀 있어야 적용된다 — 커서만 있으면 무시된다.
    """
    hwp.HAction.GetDefault("CellBorderFill", hwp.HParameterSet.HCellBorderFill.HSet)
    p = hwp.HParameterSet.HCellBorderFill
    fa = p.FillAttr
    if color is None:
        fa.type = hwp.BrushType("NullBrush")
        fa.WindowsBrush = 0
    else:
        fa.type = hwp.BrushType("NullBrush|WinBrush")
        fa.WindowsBrush = 1
        fa.WinBrushFaceColor = color
        fa.WinBrushHatchColor = 0
        fa.WinBrushFaceStyle = -1
    p.FillAttr = fa
    hwp.HAction.Execute("CellBorderFill", p.HSet)


def shade_row(hwp, anchor, ncells, color, skip=0, offset=0):
    """앵커 셀에서 offset 칸 오른쪽부터 ncells 칸에 면 색을 넣는다.

    셀마다 앵커에서 다시 찾아간다 — 셀 블록을 잡으면 커서 이동이 달라져
    한 번에 훑으면 어긋난다.
    """
    for i in range(ncells):
        if not find_in_table(hwp, anchor, skip=skip):
            print(f"    WARNING: 법령표 앵커 '{anchor}' 못 찾음")
            return False
        right(hwp, offset + i)
        hwp.HAction.Run("TableCellBlock")
        cell_fill(hwp, color)
        hwp.HAction.Run("Cancel")
    return True


def clone_para(hwp, src_anchor, dst_anchor, text):
    """`src_anchor` 문단을 통째로 복사해 `dst_anchor` 문단 **앞**에 넣고 내용을 text 로 바꾼다.

    베이스 문서에 없는 문단을 새로 넣어야 할 때 쓴다 (인용 케이스의 출처 주석 등).
    빈 문단을 만들어 쓰면 **글자·문단 모양이 대상 문단의 것을 물려받아** 제목 서식으로 나온다.
    같은 종류의 기존 문단을 복사하는 편이 안전하다.
    """
    hwp.MovePos(2)
    if not find_fwd(hwp, src_anchor):
        print(f"    WARNING: 복사 원본 '{src_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("MoveSelParaEnd")
    hwp.HAction.Run("Copy")

    hwp.MovePos(2)
    if not find_fwd(hwp, dst_anchor):
        print(f"    WARNING: 대상 '{dst_anchor}' 못 찾음")
        return False
    hwp.HAction.Run("MoveParaBegin")
    # ⚠️ 순서가 중요하다. 붙여넣기를 먼저 하고 나누면 **대상 문단이 복사본 서식을 물려받아**
    #    소제목이 작은 글씨로 바뀐다. 빈 문단을 먼저 만들고 거기에 붙인다.
    hwp.HAction.Run("BreakPara")
    hwp.HAction.Run("MoveUp")
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("Paste")
    # 붙여넣은 내용을 원하는 문장으로 바꾼다
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("MoveSelParaEnd")
    hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
    hwp.HParameterSet.HInsertText.Text = text
    hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
    return True


def append_rows(hwp, anchor, base_rows, need):
    """표의 행 수를 need 에 맞춘다. 커서는 anchor 다음 행 첫 칸에 둔다."""
    if need > base_rows:
        down(hwp, base_rows)
        hwp.HAction.Run("TableRowEnd")
        hwp.HAction.Run("TableColEnd")
        for _ in range(need - base_rows):
            hwp.HAction.Run("TableAppendRow")
        find_in_table(hwp, anchor)
    down(hwp)
    col_begin(hwp)


# ============================================================
# 삽도 이미지 교체 (HWPX ZIP 후처리)
# ============================================================
def replace_images(hwpx_path, img_map):
    try:
        from PIL import Image
    except ImportError:
        print("  Pillow 미설치 — 이미지 교체 스킵")
        return

    tmp = hwpx_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    lower = {k.lower(): v for k, v in img_map.items()}
    n = 0

    with zipfile.ZipFile(hwpx_path) as zin, zipfile.ZipFile(tmp, "w") as zout:
        for item in zin.infolist():
            src = lower.get(item.filename.lower())
            if src and os.path.exists(src):
                buf = io.BytesIO()
                Image.open(src).save(buf, format="PNG")
                info = zipfile.ZipInfo(item.filename)
                info.compress_type = item.compress_type   # 보통 STORED — 유지해야 함
                zout.writestr(info, buf.getvalue())
                print(f"  {item.filename}: 교체 ({buf.tell():,} bytes)")
                n += 1
            else:
                if src:
                    print(f"  WARNING: {src} 없음 — 원본 유지")
                zout.writestr(item, zin.read(item.filename))

    os.replace(tmp, hwpx_path)
    print(f"  이미지 {n}건 교체")


def figure_names(hwpx_path):
    """문서의 그림 → `{"image3": "수계도.jpg", …}`.

    `<hc:img binaryItemIDRef="imageN">` 과 `원본 그림의 이름: X` 가 같은 순서로 나온다.
    `CLP…` 는 한글이 붙여넣기에 붙이는 이름이라 **베이스 원본 파일이 아니다** — 구분한다.
    """
    with zipfile.ZipFile(hwpx_path) as z:
        sec = "".join(z.read(n).decode("utf-8") for n in z.namelist()
                      if re.match(r"Contents/section\d+\.xml$", n))
    # 🚨 `binaryItemIDRef` 목록과 이름 목록을 **순서로 짝지으면 안 된다.**
    #    이름이 없는 그림이 섞여 있다 (수식·기호 등 14장). 그렇게 짝지었다가
    #    엉뚱한 그림을 지웠다 (2026-08-24). **`hp:pic` 블록 안에서 함께 읽는다.**
    out = {}
    for m in re.finditer(r"<hp:pic\b.*?</hp:pic>", sec, re.S):
        blk = m.group(0)
        i = re.search(r'binaryItemIDRef="(image\d+)"', blk)
        nm = re.search(r"원본 그림의 이름: ([^\r<&]+)", blk)
        if i and nm:                      # 이름이 있는 것만 = 원본 파일에서 온 그림
            out.setdefault(i.group(1), nm.group(1).strip())
    return out


# ⚠️ **바이트가 아니라 가로 픽셀로 가른다** (2026-08-25 정정).
#    `300KB` 로 쟀더니 원주 현장사진 4장(429×287 · 220~285KB)이 검사를 통과해
#    천안 보고서에 실려 나갔다. 압축률이 그림마다 달라 바이트는 크기를 대변하지 못한다.
#    실측 분포: 사업 고유 그림 361~6,960px · 일반 아이콘 44~157px.
FIGURE_MIN_PX = 300


def check_figures(hwpx_path, template_path):
    """삽도 상태를 센다 — **아직 안 채운 것**과 **기준 사업 그림이 샌 것**을 가른다.

    기준 사업 그림은 이제 베이스 단계에서 걷어낸다
    (`build_template.strip_figures()` — `slots.md` §D). 그래서 여기서 "베이스와 동일"은
    **아직 안 채웠다**는 뜻이지 다른 사업 그림이라는 뜻이 아니다.

    ⚠️ **검사의 전제가 바뀌면 검사도 다시 써야 한다.** 템플릿을 비운 뒤에도 옛 검사를
    그대로 뒀더니 플레이스홀더 16장을 "다른 사업 삽도가 실린다"고 **거짓 경보**했다
    (2026-08-24). 남는 위험은 하나뿐이다 — **베이스에 큰 그림이 살아남는 것**.
    그건 빌더 회귀이므로 크기로 잡는다.

    🚨 검사는 수정과 **다른 근거**를 쓴다 (`rules/hwpx.md` 검증 원칙).
    """
    with zipfile.ZipFile(template_path) as zt:
        base = {i.filename: zt.read(i.filename) for i in zt.infolist()
                if i.filename.startswith("BinData")}
    unfilled, leaked = [], []
    with zipfile.ZipFile(hwpx_path) as z:
        for fn, data in base.items():
            try:
                if z.read(fn) != data:
                    continue                      # 갈아 끼웠다 = 채워졌다
            except KeyError:
                continue
            # 베이스에 큰 그림이 남아 있다 = strip_figures 가 놓쳤다 = 회귀
            # ⚠️ `[삽도 필요]` 자리표시도 900px 다 — **바이트로 먼저 걸러낸다.**
            #    자리표시는 흰 바탕이라 3KB 남짓이고, 실제 그림은 그보다 훨씬 크다.
            try:
                from PIL import Image
                w = Image.open(io.BytesIO(data)).width
            except Exception:
                w = 0
            big = w >= FIGURE_MIN_PX and len(data) > 20 * 1024
            (leaked if big else unfilled).append((fn, len(data), w))

    if leaked:
        print(f"⚠️ 베이스에 큰 그림이 살아 있다 {len(leaked)}장 "
              f"— **기준 사업 삽도가 실린다.** build_template.strip_figures() 를 의심할 것")
        for fn, sz, w in sorted(leaked, key=lambda x: -x[2])[:6]:
            print(f"     {fn}  가로 {w}px  {sz/1024:.0f}KB")
    elif unfilled:
        print(f"삽도 {len(unfilled)}장이 아직 [삽도 필요] 상태 "
              f"— 기준 사업 그림 유출은 없다 ✅")
    else:
        print("삽도 전부 교체됨 ✅")
    return leaked




def left(hwp, n=1):
    for _ in range(n):
        hwp.HAction.Run("TableLeftCell")


# ============================================================
# 표 유틸 — 지역개황에서 출발했지만 파트 무관 (병합 표는 hwpx.md 'KeyIndicator' 절)
# ============================================================
def _num(x):
    """표 셀 숫자 표기 — 천단위 쉼표, 불필요한 소수 0 제거."""
    if x is None:
        return MISSING
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return f"{x:,}"
    if isinstance(x, float):
        if x == int(x):
            return f"{int(x):,}"
        # ⚠️ `f"{x:,}"` 는 부동소수점 오차를 그대로 찍는다 —
        #    `12,026.700000000012` 가 실제로 문서에 나갔다 (2026-08-24).
        #    통계 표의 소수는 한 자리를 넘지 않으므로 반올림 후 뒤 0 을 턴다.
        return f"{round(x, 2):,.2f}".rstrip("0").rstrip(".")
    return str(x)


def fit_rows(hwp, anchor, base_rows, need, start=1):
    """앵커 행 아래 **데이터 행 수**를 need 로 맞춘다.

    끝나면 커서는 **첫 데이터 행 첫 칸**에 있다.
    `append_rows()` 는 늘리기만 한다 — 줄이는 쪽은 여기서 처리한다.
    시군마다 시설 개수가 달라 양방향이 다 필요하다.
    """
    # start: 앵커 행에서 **첫 데이터 행까지의 거리**. 머리행이 두 줄인 표(하수)는 2다.
    cur = base_rows
    while cur > need:
        if not find_in_table(hwp, anchor):
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 행 조정 스킵")
            return False
        down(hwp, start - 1 + cur)          # 마지막 데이터 행
        hwp.HAction.Run("TableDeleteRow")
        cur -= 1
    if need > cur:
        if not find_in_table(hwp, anchor):
            print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 행 조정 스킵")
            return False
        append_rows(hwp, anchor, cur, need)
        return True
    if not find_in_table(hwp, anchor):
        print(f"    WARNING: 앵커 '{anchor}' 못 찾음 — 행 조정 스킵")
        return False
    down(hwp, start)
    col_begin(hwp)
    return True


def cell_addr(hwp):
    """현재 셀 주소 → `("B", 3)`. 표 밖이면 None.

    `KeyIndicator()` 의 마지막 항목이 `'(B3): 문자 입력'` 꼴이다.
    **병합 칸을 지날 때 그 칸의 원래 행 번호가 나온다** — 이것이 병합 표를 다루는 열쇠다.
    행마다 칸 수를 세지 않고도 "지금 몇 열 몇 행인가"를 알 수 있다 (2026-08-24 실측).
    """
    try:
        ki = hwp.KeyIndicator()
    except Exception:
        return None
    m = re.match(r"\(([A-Z]+)(\d+)\)", str(ki[-1]))
    return (m.group(1), int(m.group(2))) if m else None


def fill_by_col(hwp, anchor, row_off, values, max_steps=40, skip=0):
    """머리행 앵커에서 `row_off` 만큼 내려간 행의 **지정 열**에만 값을 쓴다.

    values: `{"C": "...", "D": "..."}` — 표 열 문자로 지정한다.
    행을 왼쪽부터 걸으며 **주소를 읽어** 목표 행의 칸에만 쓰므로,
    세로 병합으로 다른 행 주소가 섞여 나와도 안전하다. 칸 수를 알 필요가 없다.
    """
    if not find_in_table(hwp, anchor, skip=skip):
        print(f"    WARNING: 앵커 '{anchor}' 못 찾음")
        return False
    down(hwp, row_off)
    here = cell_addr(hwp)
    if not here:
        print(f"    WARNING: '{anchor}' +{row_off}행 — 셀 주소를 못 읽었다")
        return False
    target = here[1]
    col_begin(hwp)
    left_to_write = dict(values)
    for _ in range(max_steps):
        a = cell_addr(hwp)
        if not a:
            break
        col, row = a
        if row > target:                       # 다음 행으로 넘어갔다
            break
        if row == target and col in left_to_write:
            set_cell(hwp, left_to_write.pop(col))
            if not left_to_write:
                break
        right(hwp)
    if left_to_write:
        print(f"    WARNING: '{anchor}' {target}행 — 못 쓴 열 {sorted(left_to_write)}")
    return True


def blank_row(hwp, anchor, row_off, keep_first=0, max_steps=40):
    """목표 행의 칸을 전부 `[확인 필요]` 로 비운다.

    자료가 없어 채우지 못하는 표에 쓴다. **원주 값을 남기면 안 되기 때문**이다 —
    다른 사업 이름 아래 남의 통계가 실린다 (rule §6-3, 청양 골든셋).
    keep_first: 왼쪽에서 이만큼의 칸은 건드리지 않는다 (항목명·라벨 열).
    """
    if not find_in_table(hwp, anchor):
        return False
    down(hwp, row_off)
    here = cell_addr(hwp)
    if not here:
        return False
    target = here[1]
    col_begin(hwp)
    seen = 0
    for _ in range(max_steps):
        a = cell_addr(hwp)
        if not a:
            break
        if a[1] > target:
            break
        if a[1] == target:
            if seen >= keep_first:
                set_cell(hwp, MISSING)
            seen += 1
        right(hwp)
    return True


def fill_after(hwp, anchor, row_off, keep_first, values, max_steps=40):
    """목표 행에서 **앞 keep_first 칸을 건너뛰고** 값을 순서대로 쓴다.

    종합표(2.10)처럼 그룹 첫 행만 라벨이 하나 더 있어 5칸·6칸이 섞이는 표에 쓴다.
    칸 수를 세는 방식(`뒤에서 N번째`)은 실패했다 — 세는 걸음과 쓰는 걸음이
    같은 칸 집합을 보지 않아 그룹 첫 행에서 라벨이 덮였다 (2026-08-24 실측).
    건너뛸 칸 수를 **호출자가 명시**하면 걸음이 한 번으로 끝나 어긋날 여지가 없다.
    """
    if not find_in_table(hwp, anchor):
        return False
    down(hwp, row_off)
    a0 = cell_addr(hwp)
    if not a0:
        return False
    target = a0[1]
    col_begin(hwp)
    seen = 0
    vi = 0
    for _ in range(max_steps):
        a = cell_addr(hwp)
        if not a or a[1] > target:
            break
        if a[1] == target:
            if seen >= keep_first:
                if vi >= len(values):
                    break
                set_cell(hwp, values[vi])
                vi += 1
            seen += 1
        right(hwp)
    return vi == len(values)

def fill_list_table(hwp, label, anchor, base_rows, rows, cols):
    """목록형 표 하나를 채운다.

    cols: 표 열 순서대로의 vars 키 목록. **`None` 은 vars 에 없는 열**이라
          `[확인 필요]` 로 비운다 — 원주 값을 남겨두면 다른 사업 이름 아래
          남의 통계가 남는다 (청양 골든셋이 그렇게 망가졌다).
    """
    n = len(rows)
    if n == 0:
        print(f"  {label}: 0행 — 지정 없음 (표 처리는 §C 삭제 대상)")
        return 0
    if not fit_rows(hwp, anchor, base_rows, n):
        return 0
    for i, item in enumerate(rows):
        if i:
            down(hwp)
            col_begin(hwp)
        fill_row(hwp, [MISSING if c is None else _num(item.get(c)) for c in cols])
    print(f"  {label}: {n}행 (기본 {base_rows}행)")
    return n


# 목록형 표 — (라벨, 앵커, 기본 데이터행수, vars 키, 표 열 순서의 vars 키)
# ⚠️ 앵커는 **표 안에서 유일**해야 한다. `find_in_table` 은 본문 매치를 건너뛰지만
#    다른 표에 같은 문자열이 있으면 거기가 먼저 걸린다 (rules/hwpx.md).
#    전부 베이스 문서에서 실측 확인했다 (2026-08-24).


# ------------------------------------------------------------
# 값 포맷 헬퍼 — 파트 공용 (소음진동·대기질이 같이 쓴다)
# ------------------------------------------------------------
def _fmt(v):
    return MISSING if v is None else str(v)


def _pp_label(ye, kind):
    """PP 라벨 형식. **같은 사업 안에서도 표마다 다르다** (noise-vib rule §4-4).

    kind: '지점표'(표 14) | '예측표'(표 22·25·29)
    청양은 표 14 만 `P - 1` 이고 나머지는 `P-1` 이다. 다른 3건은 전부 `P - 1`.
    """
    return (ye.get(f"PP라벨_{kind}") or ye.get("PP라벨") or "P - {n}")

#!/usr/bin/env python3
"""
편입토지조서 → 사업지 경계 폴리곤.

사업개요에는 **편입토지조서**가 있다. 어느 필지가 얼마나 사업에 들어가는지 적은 표다.

    구분  지번   지목  지적면적  사업부지  진출입로  소계   비고
    금신리 153   전    3,157     670      -       670   기허가
          155-1 답    1,246     903      -       903   금회증설

이 표의 **지번만 있으면 필지 경계를 국가 자료에서 받아올 수 있다** — VWorld 연속지적도다.
그림에 폴리곤을 그리려고 설계도서(dwg)를 기다릴 필요가 없다.

    주소 → 지오코딩 → 좌표 → 필지 1건 조회 → **법정동코드** → 조서 지번과 붙여 PNU → 폴리곤

`비고` 열이 정답 삽도의 **구역 구분**이다. 증설 사업은 기허가지와 금회 부지를 다른 색으로
그린다 (증설·변경 7건 중 6건).

⚠️ **색과 이름은 회사 표준이 없다 — 사업마다 다르다.** 증설·변경 14건 전수에서
   금회 빨강 7 : 노랑 2 · 기허가 파랑 6 : 빨강 1 · 문구는 `금회 증축부지`·`증설부지`·
   `공장증설부지`·`변경협의시` 처럼 제각각이다. 그래서 여기서 정하지 않고 **`vars` 에서
   받는다.** 아래 기본값은 그 다수값이다. → `docs/20260819_삽도_자동화.md` §4-3 표

   ⚠️ **구역이 둘이라는 보장도 없다** — 완오리 `1·2·3공장부지` 셋, 천안 백자리 넷.
      여기서는 조서 `비고` 로 **둘만** 낸다. 셋 이상은 표현 못 한다 (만나면 수작업).

   구분을 유지해야 하는 진짜 이유는 색이 아니라 **계산**이다. 증설 3건 모두 이격거리와
   작업량을 **금회 부지 기준**으로 낸다 (3/3). 두 폴리곤은 따로 나와야 한다.

⚠️ **필지 경계는 사업지 경계와 같지 않다.** 조서의 `사업부지` 면적이 `지적면적` 보다 작으면
   필지 일부만 들어간다는 뜻이라, 필지 전체를 그리면 **실제보다 넓게** 그려진다.
   편입률을 함께 계산해 낮은 필지에는 경고를 단다. 정확한 경계는 설계도서라야 한다.

검증: `python engine/parcels.py --self-test`
"""
import argparse, glob, itertools, json, os, re, sys, urllib.parse, urllib.request
from pathlib import Path

VWORLD_DATA = "https://api.vworld.kr/req/data"
CADASTRE = "LP_PA_CBND_BUBUN"          # 연속지적도
DOMAIN = "http://localhost"

# 지번은 `산` 이 붙을 수 있다 — 임야다 (원주 산59-1). PNU 의 산여부 자리가 달라진다.
JIBUN = re.compile(r"(산)?(\d{1,5})(?:-(\d{1,4}))?")
# HWP 표를 텍스트로 뽑으면 ㎡ 가 깨져 숫자에 들러붙는다 — `2,737浵ࡦ` (청양)
NUM = re.compile(r"^-$|^[\d,]+(?:\.\d+)?")


def _n(s):
    s = s.strip()
    if s == "-":
        return 0
    m = NUM.match(s)
    return float(m.group(0).replace(",", "")) if m and m.group(0) != "-" else None


def _cols(lines):
    """헤더에서 **숫자 열이 몇 개인지** 읽는다 — 첫 짐작일 뿐이다.

    조서 서식이 사업마다 다르다. 4열(지적면적·사업부지·진출입로·소계)이 흔하고
    여주는 2열(지적면적·편입면적)이다. 열 수를 모르면 비고의 `-` 를 숫자로 먹는다.
    **마지막 숫자 열이 언제나 사업에 편입되는 면적**이라 그것만 쓰면 된다.

    ⚠️ 헤더가 다층이면 이 계산이 어긋난다 — 평창은 공동 사업이라 편입면적 아래에
       **사업자별 열 3개 + 계**가 더 붙는데, 헤더 줄에서는 `편입면적` 다음이 바로
       `비고` 라 2열로 보인다. 그래서 `parse_survey` 가 **합계 행과 맞는 열 수를
       골라** 이 짐작을 바로잡는다."""
    try:
        i, j = lines.index("지목"), lines.index("비고")
    except ValueError:
        return 4
    return max(2, j - i - 1)


def _scan(lines, n):
    """숫자 열이 n 개라고 보고 필지를 훑는다."""
    rows, k = [], 0
    while k < len(lines):
        m = JIBUN.fullmatch(lines[k])
        # 지번 → 지목(한 글자) → 숫자 n 개 → 비고
        if m and k + n + 2 < len(lines) and JIMOK.fullmatch(lines[k + 1]):
            nums = [_n(lines[k + 2 + t]) for t in range(n)]
            if all(v is not None for v in nums):
                rows.append({
                    "지번": lines[k], "지목": lines[k + 1],
                    "산": bool(m.group(1)),
                    "지적면적": nums[0], "소계": nums[-1],
                    "비고": lines[k + 2 + n],
                })
                k += n + 3
                continue
        k += 1
    return rows


# ── 헤더 기반 파서 — 조서 서식이 회사 안에서도 여러 갈래다 ────────────────────
#
# 낯선 서식 4건을 뜯어 보니 **구역이 적히는 자리가 셋**이었다.
#
#   ① `비고` 열          괴산·여주·청주 — `기허가` / `금회증설`
#   ② **하위 열 이름**    예산 구례리 — 신청면적 아래 `남산·양지·금광1·금광2·도로부지`
#                       용인 석천리 — 편입면적 아래 `사전환경성검토·기정·변경·금회`
#   ③ **`구분` 열 행 그룹** 충주 완오리 — `기존 공장 부지` / `2공장 증설 부지` / `3공장 신설 부지`
#
# 그래서 열 수를 짐작하는 대신 **헤더를 읽는다.**

_소재지 = re.compile(r"(시|군|구|읍|면|리|동)$")
# ⚠️ **지목을 "한글 한 글자" 로 잡으면 안 된다.** 예산 조서는 합계 행을 `계` 로 여는데,
#    앞 칸이 `977` 이라 `977 계` 가 지번+지목으로 읽혔다.
# ⚠️ **한 글자로만 잡아도 안 된다.** 골든셋이 전부 약자(`전`·`답`·`임`)를 써서 몰랐는데,
#    천안 백자리는 정식 명칭을 쓴다 — `종교`·`임야`·`창고`·`유지`·`도로`.
JIMOK = re.compile(
    r"[전답과목장임광염대공창종철제천구유양수도로사묘잡원학차체분]"
    r"|전|답|과수원|목장용지|임야|광천지|염전|대|공장용지|학교용지|주차장|주유소용지"
    r"|창고용지|창고|도로|철도용지|제방|하천|구거|유지|양어장|수도용지|공원|체육용지"
    r"|유원지|종교용지|종교|사적지|묘지|잡종지")
_계 = re.compile(r"\s*(소\s*계|합\s*계|계)\s*$")


def _is_place(tok):
    """`괴산군`·`평창군 미탄면 수청리` 처럼 소재지 칸인가."""
    return bool(_소재지.search(tok.split()[-1])) if tok.split() else False


def _cell(s):
    """셀 → 숫자. `-` 는 0. **지번을 숫자로 먹지 않는다** (`704-2` → None).

    ⚠️ 깨진 ㎡(`9,785浵ࡦ`)가 붙어 오므로 앞부분만 본다. 그래서 `704-2` 를
       그냥 두면 `704` 로 읽힌다 — 하이픈+숫자가 이어지면 지번으로 본다."""
    s = s.strip()
    if s in ("-", "–", "—", ""):
        return 0.0
    if re.match(r"^산?\d[\d,]*-\d", s):
        return None
    m = re.match(r"[\d,]+(?:\.\d+)?", s)
    return float(m.group(0).replace(",", "")) if m else None


def _looks_row(lines, q, n):
    """`lines[q]` 에서 **한 필지 행이 시작되는가** — 지번 · 지목 · 숫자 n 칸.

    ⚠️ 지번+지목만 보면 안 된다. `도로`·`창고`·`유지` 는 지목이면서 비고에도 흔히 쓰인다
       (안성 `374-2 답 2,774 526 도로` 에서 `526 도로` 가 지번+지목으로 읽혔다).
       **뒤에 숫자가 n 칸 따라오는지**까지 봐야 자리로 갈린다."""
    if not (JIBUN.fullmatch(lines[q]) and q + 1 < len(lines)
            and JIMOK.fullmatch(lines[q + 1])):
        return False
    for t in range(n):
        v = lines[q + 2 + t] if q + 2 + t < len(lines) else None
        # 숫자가 **들어 있기만** 하면 된다 — 값에 접두어가 붙는 조서가 있다
        # (용인 석천리 `증) 405`). 대신 `구`·`도로` 처럼 숫자 없는 칸은 걸러진다.
        if v is None or not (v.strip() in ("-", "–", "—") or re.search(r"\d", v)):
            return False
    return True


def _num_at(lines, q, n=1):
    """`lines[q]` 를 숫자 칸으로 읽는다. 다음 필지의 지번이면 `None` (= 행 끝).

    ⚠️ **`264` 는 숫자이면서 지번이다.** 무엇인지는 뒤 칸이 정한다 — 지목이 따라오면
       다음 행의 지번이다. 이 문맥 판정이 없으면 `산84` 를 84 로 먹는다.
    ⚠️ 값에 접두어가 붙는 조서가 있다 — 용인 석천리는 증가분을 `증) 405` 로 적는다."""
    if q >= len(lines):
        return None
    t = lines[q].strip()
    if _looks_row(lines, q, n):
        return None
    if t in ("-", "–", "—", ""):
        return 0.0
    if re.match(r"^산?\d[\d,]*-\d", t):
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", t)
    return float(m.group(0).replace(",", "")) if m else None


def _header(lines):
    """헤더를 읽어 **숫자 열 이름**과 그룹 라벨을 낸다.

    반환 `(열이름[], 데이터시작, 그룹라벨)` — 못 읽으면 `None`."""
    start = next((k for k in range(len(lines) - 1)
                  if JIBUN.fullmatch(lines[k])
                  and JIMOK.fullmatch(lines[k + 1])), None)
    if start is None:
        return None
    # `(㎡)` 나 `(2010.04)` 처럼 **괄호만 있는 칸**은 윗 칸의 꼬리다 — 열로 세면 부푼다.
    head = [l for l in lines[1:start] if not re.fullmatch(r"\(?㎡\)?|\([^()]*\)", l)]
    # `지목` 뒤부터가 숫자 열이다.
    j = next((k for k, t in enumerate(head) if t.replace(" ", "") == "지목"), None)
    if j is None:
        return None
    cols = head[j + 1:]
    # `비고`(또는 `소유자`)가 숫자 열과 그 **하위 행**을 가른다.
    cut = next((k for k, t in enumerate(cols)
                if t.replace(" ", "") in ("비고", "소유자")), None)
    if cut is None:
        # `비고` 도 `소유자` 도 없으면 숫자 열과 그룹 라벨의 경계가 헤더에 없다.
        # **첫 데이터 행이 숫자를 몇 개 물고 있는지** 세어 가른다 (완오리 = 2).
        cnt = 0
        while _cell(lines[start + 2 + cnt] if start + 2 + cnt < len(lines) else "x") is not None:
            cnt += 1
        keep = [t for t in cols if not _is_place(t)]
        front, back = keep[:cnt], []
        cols = cols[:len(front)] + [t for t in keep[cnt:]]   # 나머지는 그룹 라벨로
        cut = len(front) - 1
    else:
        front, back = cols[:cut], [t for t in cols[cut + 1:] if not _is_place(t)]
    # 첫 데이터 행이 숫자를 몇 개 물었는지 — 헤더 해석의 심판이다.
    cnt = 0
    while _num_at(lines, start + 2 + cnt, 1) is not None:
        cnt += 1
    # ⚠️ `비고` 뒤에 오는 것이 **늘 하위 열은 아니다.** 천안 백자리는 `구분` 칸
    #    (`백자리 종교시설`·`소규모환경영향평가시`)이 거기 온다. 둘 중 행과 맞는 쪽을 쓴다.
    # ⚠️ `<=` 다. 행 끝의 `-` 는 비고인데 숫자 0 으로도 읽혀 `cnt` 를 하나 부풀린다
    #    (용인 석천리 — 실제 5열인데 6으로 세어진다).
    if back and 2 <= len(front) - 1 + len(back) <= cnt:
        names, group_extra = front[:-1] + back, []
    else:
        names, group_extra = front[:cnt] if cnt else front, back
        back = []
    names = [t.replace(" ", "") for t in names]
    if len(names) < 2:
        return None
    # 하위 열도 소재지도 아닌 나머지가 행 그룹 라벨이다 (완오리 `기존 공장 부지`).
    tail = [t for t in (cols[cut + 1:] if cut is not None else [])
            if not _is_place(t) and t not in back] + list(group_extra)
    return names, start, " ".join(dict.fromkeys(tail)), bool(back)


# 표 밖 것들이 마지막 필지의 비고로 딸려 온다 — 주석(`주) …`)·증감 표기(`증) 960`)·
# 그림 캡션. 용인 석천리 마지막 행이 이것들을 통째로 삼켰다.
_잡음 = re.compile(r"^[가-힣]\)|<그림|구적도|편입용지도|위성사진|위치도")


def _note(tail):
    """행 꼬리 → 비고. 표 밖 것을 걷어내고 앞의 두 칸만 쓴다."""
    out = []
    for t in tail:
        t = t.strip()
        if _잡음.search(t):
            break
        if t and not _계.fullmatch(t) and _cell(t) is None:
            out.append(t)
    return out[:2]


def _pick(names):
    """어느 숫자 열이 **편입 면적**인가. `("열", i)` 또는 `("합", None)`."""
    for k, t in enumerate(names):
        if "금회" in t:                       # 용인 — 이력 열이 앞에 늘어선다
            return "열", k
    for k, t in enumerate(names[1:], 1):
        if _계.fullmatch(t):                  # 괴산·평창 — `소계`/`계` 가 곧 편입
            return "열", k
    if len(names) > 2:                        # 예산 — 하위 열이 곧 구역이라 전부 더한다
        return "합", None
    return "열", len(names) - 1


def _structured(lines):
    """헤더가 읽히면 그것으로 훑는다. 실패하면 `None` 을 내고 옛 경로로 넘어간다."""
    h = _header(lines)
    if not h:
        return None
    names, k, group, has_sub = h
    n = len(names)
    kind, idx = _pick(names)
    has비고 = any(l.replace(" ", "") == "비고" for l in lines[1:k])
    rows = []
    while k < len(lines):
        if not _looks_row(lines, k, n):
            k += 1
            continue
        m = JIBUN.fullmatch(lines[k])
        nums = [_num_at(lines, k + 2 + t, n) for t in range(n)]
        if any(v is None for v in nums):
            return None                       # 헤더와 안 맞는다 — 옛 경로에 맡긴다
        j = k + 2 + n
        tail = []
        while j < len(lines):
            if _looks_row(lines, j, n):
                break
            tail.append(lines[j])
            j += 1
        소계 = sum(nums[1:]) if kind == "합" else nums[idx]
        # 구역 — ①하위 열이 구역이면 가장 많이 편입된 열 ②아니면 행 그룹 ③아니면 비고
        if kind == "합":
            구역 = names[1 + max(range(n - 1), key=lambda t: nums[1 + t])]
        elif group:
            구역 = group
        else:
            구역 = " ".join(_note(tail)) if has비고 else "-"
            구역 = 구역 or "-"
        rows.append({"지번": lines[k], "지목": lines[k + 1], "산": bool(m.group(1)),
                     "지적면적": nums[0], "소계": 소계, "비고": 구역,
                     "구역출처": "열" if kind == "합" else ("그룹" if group else "비고")})
        # 다음 그룹 라벨 — 소계 행과 숫자를 걷어낸 나머지 (완오리 `2공장 증설 부지`)
        if not has비고:
            lab = [t for t in tail if not _계.fullmatch(t) and not _is_place(t)
                   and re.search(r"[가-힣]", t)]
            if lab:
                group = " ".join(lab)
        k = j
    return rows or None


def parse_survey(text):
    """편입토지조서 → 필지 목록. HWP 표라 셀이 한 줄씩 떨어져 나온다."""
    i = text.find("편입토지조서")
    if i < 0:
        return [], "편입토지조서를 찾지 못했습니다", None
    seg = text[i:]
    end = seg.find("합계")     # ⚠️ `소계` 는 열 이름으로도 쓰여 끝 표시어가 못 된다
    body, tail = (seg[:end], seg[end:end + 260]) if end > 0 else (seg, "")
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    guess = _cols(lines)
    tail_nums = [_n(x) for x in tail.split("\n")[1:12]] if tail else []
    tail_nums = [v for v in tail_nums if v is not None]

    # 헤더를 읽는 쪽을 먼저 시도한다. 합계 행의 **어느 칸과든** 맞으면 확정 —
    # 다열 조서는 합계 행에도 숫자가 여럿이라 자리를 짚어 맞출 수 없다
    # (예산 계 행: 남산 9,838 · 양지 6,562 · … · 총 34,177).
    st = _structured(lines)
    if st:
        got = sum(r["소계"] for r in st)
        hit = next((v for v in tail_nums if abs(v - got) < 2), None)
        if hit is not None:
            return st, None, hit

    def total_for(n):
        return tail_nums[n - 1] if len(tail_nums) >= n else (
            tail_nums[-1] if tail_nums else None)

    # 짐작한 열 수부터 넓혀 가며 **합계 행과 맞는 것**을 고른다.
    # 서식 변이를 일일이 따라가는 대신 조서가 스스로 검산하게 한다.
    best = cand = None
    for n in [guess] + [c for c in range(2, 8) if c != guess]:
        rows = _scan(lines, n)
        if not rows:
            continue
        t = total_for(n)
        if t is not None and abs(sum(r["소계"] for r in rows) - t) < 2:
            return rows, None, t              # 합계 행과 맞으면 그것으로 확정
        if best is None:
            best = (rows, t)
        # 합계 행이 없는 조서도 있다 (평창은 `소계` 로 끝내고 진출입로 블록이 또 붙는다).
        # 그럴 때는 **편입면적이 0 인 필지가 없는** 쪽을 고른다 —
        # 편입되지 않는 필지를 조서에 올릴 이유가 없기 때문이다.
        if cand is None and all(r["소계"] > 0 for r in rows) and len(rows) > 1:
            cand = (rows, t)
    if st:                       # 헤더를 읽은 쪽이 짐작보다 낫다
        return _guard(st, None)
    if cand:
        return _guard(cand[0], cand[1])
    if best is None:
        return ([], "조서에서 필지를 읽지 못했습니다", None) if not st \
            else _guard(st, None)
    # 옛 경로가 합계를 못 맞췄으면 헤더를 읽은 쪽을 우선한다.
    return _guard(st, None) if st else _guard(best[0], best[1])


# ⚠️ **여기까지 왔다는 것은 합계 검산에 실패했다는 뜻이다.** 예전에는 그대로 돌려줬다 —
#    부르는 쪽이 검증된 값인지 알 방법이 없었다. 낯선 서식 5건을 먹여 보니 **4건이
#    거부 없이 쓰레기를 냈다** (예산 구례리·용인 석천리는 필지 2건, 충주 완오리는
#    비고 자리에 지번이 들어왔다). 조서 구조가 회사 안에서도 여러 갈래라서다 —
#    구역이 `비고` 가 아니라 **열**로 오거나(예산: 남산·양지·금광1·금광2·도로부지)
#    **`구분` 열의 행 그룹**으로 온다(완오리: 기존 공장 부지).
def _guard(rows, total):
    """합계로 검산 못 한 결과를 내보내기 전 마지막 관문.

    ⚠️ **합계 숫자를 믿고 거를 수 없다.** 평창은 합계 행이 없어 엉뚱한 수(2,024)를
       읽는데 실제 소계 합은 17,615 다. 그래서 **구조 신호**로 거른다 — 열이 밀리면
       `비고` 자리에 지목·지번·`소계` 가 들어온다. 골든셋 6건의 비고는 `-`·`기허가`·
       `금회증설`·`공유수면` 뿐이라 이 신호와 겹치지 않는다.

    합계는 **조서가 우리보다 클 때만** 쓴다 — 필지를 빠뜨렸다는 뜻이라서다.
    작을 때는 평창처럼 합계를 잘못 읽은 경우가 있어 근거가 못 된다."""
    got = sum(r["소계"] for r in rows)
    지목 = "전답과장임잡대구천도묘유원학교사철차수제양광염"
    for r in rows:
        b = (r["비고"] or "").strip()
        if re.fullmatch(r"소\s*계|합\s*계", b):
            return [], "열이 밀렸습니다 — 비고 자리에 `소계`가 들어왔습니다", total
        if len(b) == 1 and b in 지목:
            return [], f"열이 밀렸습니다 — 비고 자리에 지목 `{b}` 가 들어왔습니다", total
        if re.fullmatch(r"산?\d+(-\d+)?", b):
            return [], f"열이 밀렸습니다 — 비고 자리에 지번 `{b}` 가 들어왔습니다", total
    if total is not None and total > got + 1:
        return [], (f"조서 합계보다 적게 읽었습니다 — 읽은 소계 합 {got:,.0f} "
                    f"↔ 조서 {total:,.0f} (필지를 빠뜨렸습니다)"), total
    return rows, None, total


def survey_address(text):
    """조서 머리에 적힌 **지역명 + 첫 지번** → 지오코딩용 주소.

    조서는 `구분` 열에 시군·읍면·리를 한 줄씩 적는다. 본문 첫 줄의 사업명에서
    뽑는 것보다 이쪽이 견고하다 — 사업명 표기가 제각각이다."""
    rows, err, _ = parse_survey(text)
    if err:
        return None
    i = text.find("편입토지조서")
    lines = [l.strip() for l in text[i:].split("\n") if l.strip()]
    try:
        start = lines.index("비고") + 1
    except ValueError:
        return None
    area = []
    for l in lines[start:start + 6]:
        if re.fullmatch(r"[가-힣]+(?:시|군|구|읍|면|동|리)", l):
            area.append(l)
        elif area:
            break
    return " ".join(area + [rows[0]["지번"]]) if area else None


def _get(**kw):
    key = _key()
    p = {"service": "data", "request": "GetFeature", "data": CADASTRE, "key": key,
         "domain": DOMAIN, "format": "json", "size": "100", "crs": "EPSG:4326"}
    p.update(kw)
    r = json.loads(urllib.request.urlopen(
        f"{VWORLD_DATA}?{urllib.parse.urlencode(p)}", timeout=25).read())
    res = r.get("response", {})
    if res.get("status") != "OK":
        return [], res.get("error", {}).get("text", res.get("status"))
    return res.get("result", {}).get("featureCollection", {}).get("features", []), None


def _key():
    path = os.path.expanduser("~/.vworld.env")
    if not os.path.exists(path):
        sys.exit("~/.vworld.env 가 없습니다 (VWORLD_API_KEY)")
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("VWORLD_API_KEY"):
            return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("~/.vworld.env 에 VWORLD_API_KEY 가 없습니다")


def bjd_code(lon, lat):
    """좌표 → 법정동코드. 그 자리 필지를 하나 집어 PNU 앞 10자리를 뗀다."""
    fs, err = _get(geomFilter=f"POINT({lon} {lat})", size="1")
    if err or not fs:
        return None, err or "그 좌표에 필지가 없습니다"
    return fs[0]["properties"]["pnu"][:10], None


def pnu_of(code, jibun, san=False):
    """법정동코드 + 지번 → PNU 19자리 (코드10 + 산여부1 + 본번4 + 부번4)."""
    m = JIBUN.fullmatch(jibun.strip())
    if not m:
        return None
    san = san or bool(m.group(1))
    return f"{code}{2 if san else 1}{int(m.group(2)):04d}{int(m.group(3) or 0):04d}"


def _rings(geom):
    """폴리곤 하나든 여럿이든 바깥 링을 전부 모은다 — 필지가 조각나 있을 수 있다."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def area_m2(ring):
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True)
    p = [tr.transform(x, y) for x, y in ring]
    return abs(sum(p[i][0] * p[i - 1][1] - p[i - 1][0] * p[i][1]
                   for i in range(len(p)))) / 2


def fetch_bonbun(code, jibun):
    """본번 계열을 통째로 받는다 — `155` 를 넣으면 155·155-1·155-2… 가 다 온다.

    **이미 시행된 사업**은 지적이 갈라져 조서 지번이 그대로 없다. 그럴 때 본번 계열을 다
    합치면 조서의 지적면적과 다시 맞는다 (괴산 4개 본번 모두 ±1%)."""
    m = JIBUN.fullmatch(jibun.strip())
    if not m:
        return []
    pre = f"{code}{2 if m.group(1) else 1}{int(m.group(2)):04d}"
    fs, _ = _get(attrFilter=f"pnu:like:{pre}", geometry="true")
    return fs


def fetch(rows, code, expand=False):
    """조서 필지들의 경계를 받아 온다. 지적면적과 대조해 **스스로 검증**한다."""
    out, warn = [], []
    seen = set()
    for r in rows:
        pnu = pnu_of(code, r["지번"], r.get("산", False))
        fs, err = _get(attrFilter=f"pnu:=:{pnu}", geometry="true")
        if err or not fs:
            warn.append(f"{r['지번']} — 필지를 찾지 못했습니다 ({err or 'PNU ' + pnu})")
            continue
        rings = [g for f in fs for g in _rings(f["geometry"])]
        got = sum(area_m2(g) for g in rings)
        off = r["지적면적"] and abs(got - r["지적면적"]) > r["지적면적"] * 0.10
        if off and expand:
            # 갈라진 사업 — 본번 계열을 통째로 받아 메운다. 중복은 PNU 로 막는다.
            fs2 = [f for f in fetch_bonbun(code, r["지번"])
                   if f["properties"]["pnu"] not in seen]
            if fs2:
                seen.update(f["properties"]["pnu"] for f in fs2)
                rings = [g for f in fs2 for g in _rings(f["geometry"])]
                got = sum(area_m2(g) for g in rings)
                off = abs(got - r["지적면적"]) > r["지적면적"] * 0.10
                warn.append(f"{r['지번']} — 지적이 갈라져 본번 계열 {len(fs2)}필지로 대신했습니다"
                            f" ({got:,.0f}㎡ ↔ 조서 {r['지적면적']:,.0f}㎡)")
        elif off:
            warn.append(f"{r['지번']} — 지적도 {got:,.0f}㎡ ↔ 조서 {r['지적면적']:,.0f}㎡ "
                        "(10% 넘게 어긋납니다)")
        seen.add(pnu)
        ratio = r["소계"] / r["지적면적"] if r["지적면적"] else 1.0
        out.append(dict(r, pnu=pnu, rings=rings, 지적도면적=round(got), 편입률=round(ratio, 3)))
    return out, warn


# 증설 사업의 두 구역 — 기본 색·이름. **회사 표준이 아니라 다수값이다.**
# 기허가지 파랑 3 : 빨강 1, 범례 문구는 7건이 전부 달랐다. 사업별로 vars 가 덮어쓴다.
# → docs/20260819_삽도_자동화.md §4-3
ZONE_DEFAULT = {
    "사업계획지구": {"color": "red",  "label": "사업계획지구"},
    "금회":        {"color": "red",  "label": "금회사업부지"},
    "기허가":      {"color": "blue", "label": "기허가지"},
}


# 구역이 셋 이상일 때 쓰는 색 순서. 정답에서 실제로 본 순서다 —
# 빨강·파랑이 압도적이고(7:2 · 6:1) 그다음이 노랑·청록이다 (완오리 1·2·3공장부지).
ZONE_PALETTE = ["red", "blue", "yellow", "cyan"]


def is_expansion(parcels):
    """증설 사업인가 — 조서가 **모든 필지에** 금회/기허가를 적었으면 그렇다.

    ⚠️ `금회` 가 어딘가 한 번 나오는 것만으로는 부족하다. 용인 석천리는 필지 16개 중
       둘에만 `금회 증설부지` 라고 적어 두었는데, 나머지가 `-` 다 — 구역 구분이 아니라
       그 두 필지에 붙인 주석이다. 실제 정답 삽도도 **빨강 하나**로 그렸다."""
    vals = [(p.get("비고") or "-").strip() for p in parcels]
    return bool(vals) and all(v and v != "-" for v in vals) \
        and any("금회" in v for v in vals)


def zones_in(parcels):
    """조서에 적힌 **구역 목록**. 나눌 것이 없으면 빈 리스트.

    구역이 적히는 자리가 셋이라 (`_structured` 머리말 참고) 파서가 어느 자리에서
    읽었든 여기 `비고` 로 들어온다 — `금회증설`(비고 열) · `2공장 증설 부지`(행 그룹) ·
    `금광1`(하위 열 이름).

    ⚠️ **비증설 사업을 나누면 안 된다.** 정답이 `사업계획지구` 한 덩어리 빨강이다 (2/2).
       `-`·`공유수면`·`도로점용` 같은 비고는 구역이 아니라 주석이다."""
    if is_expansion(parcels):                 # ① 금회/기허가 — 가장 흔하다
        return ["금회", "기허가"]
    # ② **비고 칸은 원래 주석 자리다.** 거기 적힌 것을 구역으로 쓰는 건 `기허가`/
    #    `금회증설` 관례뿐이고, 그건 위에서 이미 걸렀다. 나머지 비고는 구역이 아니다 —
    #    천안 백자리 `소규모환경영향평가시 : 9,900㎡` · 안성 `황태성(사용승낙)` ·
    #    천안 화덕리 `공유수면` 이 전부 그렇다.
    #    구역으로 인정하는 것은 **하위 열 이름**(예산)과 **행 그룹**(완오리)뿐이다.
    if not any(p.get("구역출처") in ("열", "그룹") for p in parcels):
        return []
    uniq = [v for v in dict.fromkeys((p.get("비고") or "-").strip() for p in parcels)
            if v != "-"]
    return uniq if len(uniq) > 1 else []


def zone_of(비고, zones):
    """조서 `비고` → 구역 키. `zones` 가 비면 전부 `사업계획지구` 한 덩어리."""
    if not zones:
        return "사업계획지구"
    b = (비고 or "").strip()
    if zones == ["금회", "기허가"]:
        return "금회" if "금회" in b else "기허가"
    return b if b in zones else zones[0]


# 계산마다 **기준이 되는 부지가 다르다.** 증설 사업에서 이걸 섞으면 값이 조용히 틀린다.
#
#   PP 이격거리 (정온시설까지)   → 금회 부지만        (괴산·여주·청주 3/3)
#   생태·경관보전지역 이격거리    → 사업계획지구 전체   (평창 "사업계획지구로부터 1.04km")
#   생태자연도 등급 판정         → 사업계획지구 전체
#
# ⚠️ PP 이격거리는 **우리가 계산하지 않는다** — 정온시설 좌표(XTM/YTM)가 자료 부재라
#    잴 대상이 없다. 값은 지역개황편 정온시설 표에서 온다 (텍스트 9/10 정확 · 삽도 판독은
#    최후 수단). 여기 기준을 적어 두는 것은 **나중에 계산을 붙일 때 틀리지 않기 위해서**다.
BASIS = ("사업계획지구", "금회")


def site_rings(parcels, basis="사업계획지구", min_ratio=0.5):
    """사업지 폴리곤 링(경위도) — **기준을 명시해서** 꺼낸다.

    `basis="금회"` 는 증설 사업의 금회 부지만 낸다. 비증설 사업에 쓰면 조서에 금회가
    없으므로 **빈 리스트**가 나온다 — 조용히 전체로 넘어가지 않는다. 부르는 쪽이
    증설 여부를 `is_expansion()` 으로 먼저 판정해야 한다.

    ⚠️ `min_ratio` 기본값이 그리기(0.05)보다 높은 0.5 인 이유 — 편입률이 낮은 필지를
       넣으면 **사업지가 통째로 부풀어 거리가 0 에 가까워진다.** 원주 산59-1 은 임야
       184,166㎡ 중 23㎡(0.01%)만 편입이다 (`ecology._site_rings` 의 같은 판단)."""
    zs = zones_in(parcels)
    if basis not in BASIS and basis not in zs:
        raise ValueError(f"기준은 {BASIS} 이거나 이 조서의 구역 {zs} 여야 한다: {basis!r}")
    out = []
    for p in parcels:
        if p.get("편입률", 1.0) < min_ratio:
            continue
        if basis != "사업계획지구" and zone_of(p.get("비고"), zs) != basis:
            continue
        out.extend(p["rings"])
    return out


def to_elements(parcels, origin_lonlat, center_px, px_per_m, min_ratio=0.05,
                crs="EPSG:3857", zones=None, legend=False):
    """필지 폴리곤 → figure_overlay 요소들.

    구역은 조서의 `비고` 로 나눈다 — 증설 사업은 기허가지와 금회 부지를 다른 색으로
    그린다 (증설·변경 7건 중 6건).

    ⚠️ **색과 이름은 여기서 정하지 않는다.** 회사 표준이 없어 사업마다 다르다.
       `zones` 로 덮어쓴다 — `{"금회": {"color": "yellow", "label": "금회 신규부지"}}`.
       기본값은 다수를 따른다 (`ZONE_DEFAULT`).

    `legend=True` 면 범례 요소를 함께 낸다. **구역이 둘일 때만** 붙는다 —
    비증설 사업은 정답도 `사업계획지구` 한 항목이라 여기서 만들지 않는다 (2/2).

    지도 위 지시선 라벨(`금회 신규부지` → 화살표)은 **만들지 않는다.** 괴산 1건뿐이고
    (1/7) 나머지는 전부 범례에 넣는다."""
    z = {k: dict(v) for k, v in ZONE_DEFAULT.items()}
    for i, k in enumerate(zones_in(parcels)):          # 조서에서 읽은 구역 (셋 이상 가능)
        z.setdefault(k, {"color": ZONE_PALETTE[i % len(ZONE_PALETTE)], "label": k})
    for k, v in (zones or {}).items():
        z.setdefault(k, {}).update(v)
    import math
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    cx_m, cy_m = tr.transform(*origin_lonlat)
    ox, oy = center_px
    # Web Mercator 는 위도가 올라갈수록 늘어난다 — 그 배율을 빼야 실제 거리와 맞는다.
    # EPSG:5186 같은 **평면 직각좌표계는 이미 미터**라 보정하지 않는다.
    k = (px_per_m / math.cos(math.radians(origin_lonlat[1]))
         if crs == "EPSG:3857" else px_per_m)

    def px(ring):
        out = []
        for lon, lat in ring:
            x, y = tr.transform(lon, lat)
            out.append([round(ox + (x - cx_m) * k, 1), round(oy - (y - cy_m) * k, 1)])
        return out

    # 구역끼리 **한 덩어리로 합친다.** 필지마다 선을 그으면 안쪽에 격자가 생긴다 —
    # 정답에는 외곽선 하나뿐이다.
    zs = zones_in(parcels)
    groups = {}
    for p in parcels:
        if p["편입률"] < min_ratio:          # 스치듯 지나가는 필지는 그리지 않는다
            continue
        groups.setdefault(zone_of(p["비고"], zs), []).extend(px(r) for r in p["rings"])

    # 금회를 나중에 그린다 — 겹치면 금회 선이 위로 올라와야 한다.
    order = [k for k in ("사업계획지구", "기허가", "금회") if k in groups] \
        or [k for k in zs if k in groups]
    els = [{"type": "parcels", "polygons": groups[k], "color": z[k]["color"], "zone": k}
           for k in order]
    if legend and len(order) > 1:
        els.append({"type": "legend", "swatch": "outline", "title": "범 례",
                    # 금회/기허가는 **금회를 위에** 둔다 (정답 5건 전부). 조서에서 읽은
                    # 다구역은 조서 순서 그대로다 (완오리 1공장 → 2공장 → 3공장).
                    "items": [[z[k]["color"], z[k]["label"]]
                              for k in (reversed(order) if "금회" in order else order)]})
    return els


# ── 자체 검증 — 골든셋 ──────────────────────────────────────────────────────
def _online_check(name, text, rows, limit=12):
    """조서 지번을 **현재 지적도와 맞춰 본다.** 어긋나면 그 자체가 정보다.

    ⚠️ 지적도는 살아 있는 자료다 — **사업이 시행되면 필지가 분할된다.** 이미 지어진
       사업의 조서 지번으로 지금 지적도를 찾으면 쪼개진 조각 하나만 잡힌다.
       신규 사업(시행 전)은 조서 지번이 그대로 살아 있어야 한다."""
    import map_fetch as M
    addr = survey_address(text)
    if not addr:
        return f"{name:<12} 주소를 못 만들었습니다"
    try:
        mx, my, _ = M.geocode(addr)
    except Exception as e:
        return f"{name:<12} 지오코딩 실패 ({addr}) {e}"
    lon, lat = M.merc_to_lonlat(mx, my)
    code, err = bjd_code(lon, lat)
    if not code:
        return f"{name:<12} {err}"
    ok = bad = miss = 0
    for r in rows[:limit]:
        fs, _ = _get(attrFilter=f"pnu:=:{pnu_of(code, r['지번'], r.get('산', False))}",
                     geometry="true")
        if not fs:
            miss += 1
            continue
        a = sum(area_m2(g) for x in fs for g in _rings(x["geometry"]))
        if r["지적면적"] and abs(a - r["지적면적"]) <= r["지적면적"] * 0.10:
            ok += 1
        else:
            bad += 1
    n = min(len(rows), limit)
    return (f"{name:<12} {addr[:30]:<30} 지적도 일치 {ok}/{n}"
            + (f" · 어긋남 {bad}" if bad else "") + (f" · 없음 {miss}" if miss else ""))


def self_test(root="cases/small-env", online=False):
    files = sorted(glob.glob(f"{root}/*/input/사업개요.txt"))
    if not files:
        print(f"[skip] 사업개요가 없습니다: {root}")
        return True
    ok = 0
    for f in files:
        name = f.split("/")[-3]
        rows, err, total = parse_survey(open(f, encoding="utf-8").read())
        if err:
            print(f"  [WARN] {name:<12} {err}")
            continue
        s = sum(r["소계"] for r in rows)
        mark = "OK  " if total and abs(s - total) < 2 else "WARN"
        if mark == "OK  ":
            ok += 1
        print(f"  [{mark}] {name:<12} 필지 {len(rows)}개 · 소계 합 {s:,.0f}㎡"
              f" · 조서 합계 {total and f'{total:,.0f}' or '없음'}")
        by = {}
        for r in rows:
            by.setdefault(r["비고"] or "(없음)", []).append(r["지번"])
        for k, v in by.items():
            print(f"          {k}: {' · '.join(v)}")
        if online:
            print(f"          ↳ {_online_check(name, open(f, encoding='utf-8').read(), rows)}")
    print(f"\n합계가 맞은 사업 {ok}/{len(files)}")
    return _ext_test() and True


# ⚠️ **통과만 세면 파서가 조용히 틀리는 것을 못 잡는다.** 낯선 서식 4건을 먹여 보니
#    거부 없이 쓰레기를 냈다 (2026-08-24). 그 4건을 표본으로 박아 두고 **조서에 적힌
#    합계와 맞는지**까지 본다 — 필지 수만 세면 열이 밀린 것을 놓친다.
def _ext_test(root="engine/testdata/조서_확장표본"):
    spec = Path(root) / "기대값.json"
    if not spec.exists():
        return True
    want = json.loads(spec.read_text(encoding="utf-8"))
    print("\n낯선 서식 — 조서 구조가 회사 안에서도 여러 갈래다")
    bad = 0
    for name, exp in want.items():
        if name.startswith("_"):
            continue
        f = Path(root) / f"{name}.txt"
        rows, err, _ = parse_survey(f.read_text(encoding="utf-8"))
        got = sum(r["소계"] for r in rows)
        zs = zones_in(rows)
        why = (err or
               (f"필지 {len(rows)} ≠ {exp['필지']}" if len(rows) != exp["필지"] else "") or
               (f"합계 {got:,.0f} ≠ {exp['합계']:,}" if abs(got - exp["합계"]) >= 2 else "") or
               (f"구역 {zs} ≠ {exp['구역']}" if zs != exp["구역"] else ""))
        bad += bool(why)
        print(f"  [{'FAIL' if why else 'OK  '}] {name:<14} {exp['구조']}")
        print(f"          {why or f'필지 {len(rows)} · 합계 {got:,.0f}㎡'}"
              + (f" · 구역 {zs}" if zs and not why else ""))
    print(f"\n낯선 서식 {len(want) - 1 - bad}/{len(want) - 1}")
    return bad == 0


def main():
    ap = argparse.ArgumentParser(description="편입토지조서 → 사업지 경계 폴리곤")
    ap.add_argument("file", nargs="?", help="사업개요 텍스트")
    ap.add_argument("--lonlat", nargs=2, type=float, help="사업지 경위도 (법정동코드 확인용)")
    ap.add_argument("--center-px", nargs=2, type=float, help="map_fetch 의 center_px")
    ap.add_argument("--px-per-m", type=float, help="map_fetch 의 px_per_m")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--online", action="store_true", help="지적도까지 맞춰 본다 (느리다)")
    ap.add_argument("--expand", action="store_true",
                    help="지적이 갈라진 사업이면 본번 계열로 메운다 (근사)")
    ap.add_argument("--min-ratio", type=float, default=0.05,
                    help="편입률이 이보다 낮은 필지는 그리지 않는다 (기본 0.05)")
    ap.add_argument("-o", "--out", help="spec 조각(JSON)으로 저장")
    a = ap.parse_args()

    if a.self_test or not a.file:
        sys.exit(0 if self_test(online=a.online) else 1)

    rows, err, total = parse_survey(open(a.file, encoding="utf-8").read())
    if err:
        sys.exit(err)
    print(f"필지 {len(rows)}개 · 사업부지 합 {sum(r['소계'] for r in rows):,}㎡")
    if not a.lonlat:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return

    code, err = bjd_code(*a.lonlat)
    if err:
        sys.exit(err)
    print(f"법정동코드 {code}")
    parcels, warn = fetch(rows, code, a.expand)
    for p in parcels:
        flag = "" if p["편입률"] >= 0.6 else "  ⚠ 일부만 편입"
        print(f"  {p['지번']:<7} {p['지목']} {p['지적도면적']:>7,}㎡"
              f" · 편입 {p['편입률']*100:>5.1f}% · {p['비고']}{flag}")
    for w in warn:
        print(f"  ⚠ {w}", file=sys.stderr)

    if a.out and a.center_px and a.px_per_m:
        els = to_elements(parcels, a.lonlat, a.center_px, a.px_per_m, a.min_ratio)
        json.dump({"elements": els}, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"→ {a.out}  (덩어리 {len(els)}개 · 폴리곤 {sum(len(e['polygons']) for e in els)}개)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""지역개황(0200) 파트 핸들러 — 2026-08-31 R1 리팩터로 generate.py 에서 분리 (로직 불변).

규약: build_slots(v) / build_tables(hwp, v). 지식 출처: rules/small-env/regional-overview.md
"""
import re
from pathlib import Path

from hwp_util import (MISSING, blank_row, col_begin, delete_range, down, fill_after,
                      fill_by_col, fill_list_table, fill_row, fit_rows, fr, right,
                      _num)

LIST_TABLES = [
    ("2.3.2 상수원보호구역", "보호구역명", 1, "2.3.2 상수원보호구역",
     ["보호구역명", "지정일자", "지정면적(㎢)", "소재지"]),
    ("2.3.3 산림유전자원", "보호구역 명칭", 2, "2.3.3 산림유전자원보호구역",
     ["지정일자", None, "지정유형", "위치", "면적(㎡)"]),
    ("2.3.3 야생생물", "연번", 3, "2.3.3 야생생물 보호구역",
     ["연번", "소재지", "면적(㎢)", "비고"]),
    # ⛔ 2.5.3 산업·농공단지는 **아직 못 넣는다.** `구분` 열이 그룹(일반/농공)마다
    #    세로 병합이라 행마다 셀 수가 5·6 으로 갈린다. 왼쪽 정렬은 한 칸씩 밀리고,
    #    오른쪽 정렬(TableRowEnd 기준)은 이전 행을 침범했다 — 2026-08-24 실측.
    #    행별 칸 수를 런타임에 알아내는 방법이 필요하다.
    ("2.6.1 취수장", "취수원정보", 3, "2.6.1 취수장",
     ["시설명", "소재지 주소", "설계시설용량(㎥/일)", "취수원정보",
      "일평균취수량(㎥/일)", "공급정수장"]),
    # 앵커 `정수처리적용방식` 은 못 쓴다 — 셀이 `정수처리`/`적용방식` 두 문단이다
    ("2.6.2 정수장", "급수지역", 3, "2.6.2 정수장",
     ["시설명", "소재지 주소", "설계시설용량(㎥/일)", "일평균생산량(㎥/일)",
      "정수처리 적용방식", "급수지역"]),
    ("2.7.2 분뇨처리시설", "연계처리장명", 1, "2.7.2 분뇨처리시설",
     ["시설명", "소재지", "시설용량(㎥/일)", "처리량(㎥/일)", "처리공법", None]),
    ("2.7.3 음식물류", "업체/시설명", 1, "2.7.3 음식물류 폐기물 처리시설",
     ["업체/시설명", "소재지", "공공/민간", "시설용량(톤/일)", "처리방법", "처리량(톤/년)"]),
    ("2.7.4 매립처리시설", "기매립량", 1, "2.7.4 매립처리시설",
     ["시설명", "소재지", "총매립면적(㎡)", "총매립용량(㎥)",
      "기매립량(㎥)", "잔여매립가능량(㎥)"]),
]


CHECK = "[확인 필요]"


def _pct(part, total):
    """구성비(%) — 소수 2자리. rule §3-1 (골든셋 16행 중 15행 역산 일치)."""
    if not total:
        return CHECK
    return f"{part / total * 100:.2f}"


def slots_regional_overview(v):
    """vars → 베이스 문서 빈칸 (토큰 28종). 키는 `regional-overview.slots.md` A절과 일치.

    ⚠️ 이 파트는 **채워지지 않는 자리가 많은 것이 정상**이다 — 개황 문단·지구 지목 구성처럼
    인풋에 없는 값이 여럿이라 `[확인 필요]` 로 남는다. `fill_report.py` 가 그것을 모아
    실무자에게 넘긴다. **지어내지 않는다** (`common.md` 환각 금지).
    """
    biz, st = v["사업"], v.get("통계", {})
    ybk = v.get("_통계판", {}).get("지자체 통계연보", {})

    out = {
        "사업명": biz.get("사업명", CHECK),
        "시군": biz.get("시군", CHECK),
        "하위행정구역": biz.get("하위행정구역", CHECK),
        "리": biz.get("리", CHECK),
        "지구_면적": biz.get("지구_면적", CHECK),
        # 인풋에 없다 — 실무자 입력 (slots.md A절 5·6·7·9·13·15·17·18·19)
        "시군_개황": CHECK,
        # 2.8.3 수계 서술 — 유하 하천·거리는 사업마다 다르다. vars 에 없으면 [확인 필요].
        "수계_서술": biz.get("수계_서술", CHECK),
        "하위행정구역_개황": CHECK,
        "시군청_주소": CHECK,
        "지구_지목구성": CHECK,
        "지구_지목_서술": CHECK,
        "지구_용도지역": CHECK,
        "폐수_지역등급": CHECK,
    }

    # ── 좌표에서 나오는 값 둘 (vars 빌더가 `공간` 에 채워 둔다) ──────────
    sp = v.get("공간", {})
    # ⚠️ 도엽은 **이름‧번호** 형태로 쓴다 (`횡성‧377122`, 이음표 U+2027).
    #    번호는 계산되지만 **도엽 이름은 도엽 색인에서 와야** 한다 → 없으면 번호만
    번호 = sp.get("도엽번호", CHECK)
    이름 = sp.get("도엽명")
    out["도엽명_번호"] = f"{이름}‧{번호}" if 이름 and 번호 != CHECK else (
        번호 if 번호 != CHECK else CHECK)
    # `2, 3` 처럼 나열될 수 있다 — 부지가 두 등급에 걸치면 둘 다 적는다 (rule 3/8)
    # ⚠️ 베이스 문구가 `생태·자연도 {{토큰}}으로` 라 **`등급` 을 값에 붙여야** 한다.
    #    안 붙이면 `생태·자연도 3으로` 가 나간다 (2026-08-25 실측).
    _eg = sp.get("생태자연도_등급")
    out["생태자연도_등급"] = f"{_eg}등급" if _eg else CHECK

    # 지구 소재지 — 사업명에서 조립한다 (`{시군} {면} {리} {지번}`)
    m = re.search(r"^(.+?번지)\s*일원", str(biz.get("사업명", "")))
    out["지구_소재지"] = m.group(1) if m else CHECK

    # 출처 주석 — 그 지자체 통계연보의 **실제 제목**을 따른다 (rule §2-1, 통일하지 않는다)
    out["통계연보_표기"] = ybk.get("표기") or (
        Path(ybk["파일"]).stem if ybk.get("파일") else CHECK)

    # ── 2.2.1 지목별 — 구성비를 계산한다 (rule §3-1) ────────────────────
    land = st.get("2.2.1 지목별 토지이용")
    for scope, pre in (("시군", "시군"), ("면", "면")):
        d = land.get(scope) if isinstance(land, dict) else None
        if not isinstance(d, dict):
            for k in ("전체면적", "임야_구성비", "임야_면적", "경작지_구성비", "경작지_면적"):
                out[f"{pre}_{k}"] = CHECK
            continue
        tot = d.get("합계")
        임야 = d.get("임야")
        경작 = (d.get("전") or 0) + (d.get("답") or 0)
        out[f"{pre}_전체면적"] = f"{tot:,.2f}" if tot else CHECK
        out[f"{pre}_임야_면적"] = f"{임야:,.2f}" if 임야 else CHECK
        out[f"{pre}_임야_구성비"] = _pct(임야, tot) if 임야 else CHECK
        out[f"{pre}_경작지_면적"] = f"{경작:,.2f}" if 경작 else CHECK
        out[f"{pre}_경작지_구성비"] = _pct(경작, tot) if 경작 else CHECK

    # rule §5-1 — A형 문장의 `비교적 높은/낮은` 은 **경작지 비율에 따라 갈린다**
    #   (평창 9.40% → `낮은`). 문턱이 골든셋에 명시돼 있지 않아 10% 를 기준으로 둔다
    try:
        out["높낮"] = "높은" if float(out["시군_경작지_구성비"]) >= 10 else "낮은"
    except (TypeError, ValueError):
        out["높낮"] = CHECK

    # ── 2.6 · 2.7 서술 문장 ★ ─────────────────────────────────────────
    # 표를 채워도 그 위 문장은 기준 사업(원주) 수치를 그대로 안고 있었다 —
    # `BCS공법으로 일 430㎥ … 원주공공하수처리시설과 연계` 가 천안 보고서에 실렸다.
    # **표와 문장은 같은 vars 에서 나와야 한다** (2026-08-24).
    def n_of(key):
        r = st.get(key)
        return str(len(r)) if isinstance(r, list) and r else CHECK

    out["취수장_개소"] = n_of("2.6.1 취수장")
    out["정수장_개소"] = n_of("2.6.2 정수장")
    out["하수처리_개소"] = n_of("2.7.1 공공하수처리시설")
    # 방류 수계는 통계에 없다 — 하천일람(2.8.3)이나 인풋 수계 서술에서 와야 한다
    out["하수_방류수계"] = biz.get("방류수계", CHECK)
    out["음식물류_개소"] = n_of("2.7.3 음식물류 폐기물 처리시설")

    분뇨 = st.get("2.7.2 분뇨처리시설")
    out["분뇨_개소"] = n_of("2.7.2 분뇨처리시설")
    if isinstance(분뇨, list) and 분뇨:
        # 문장은 공법·처리량을 합산하지 않는다 — 시설이 둘 이상이면 지어내게 된다
        one = 분뇨[0] if len(분뇨) == 1 else {}
        out["분뇨_처리공법"] = one.get("처리공법", CHECK)
        out["분뇨_처리량"] = _num(one.get("처리량(㎥/일)")) if one.get("처리량(㎥/일)") else CHECK
    else:
        out["분뇨_처리공법"] = out["분뇨_처리량"] = CHECK

    매립 = st.get("2.7.4 매립처리시설")
    out["매립_개소"] = n_of("2.7.4 매립처리시설")
    if isinstance(매립, list) and 매립:
        # 사용가능기간 `1999-2032` 의 뒤쪽이 종료년이다. 시설이 여럿이면 가장 늦은 해.
        yrs = [str(x.get("사용가능기간", "")).split("-")[-1] for x in 매립]
        yrs = [y for y in yrs if y.isdigit()]
        out["매립_종료년"] = max(yrs) if yrs else CHECK
        cum = sum(x.get("기매립량(㎥)") or 0 for x in 매립)
        out["매립_누적량"] = _num(cum) if cum else CHECK
    else:
        out["매립_종료년"] = out["매립_누적량"] = CHECK
    # 누적 기준년 — 폐기물 통계는 **전년도 실적을 이듬해 발행**한다.
    # 출처 주석도 `전국 폐기물 발생 및 처리현황(2023년도) 2024` 로 두 해를 함께 적는다.
    판 = v.get("_통계판", {}).get("전국 폐기물 발생 및 처리현황", {}).get("판")
    out["매립_기준년"] = str(판 - 1) if isinstance(판, int) else CHECK

    # 2.3.1 다. 저황유 공급지역 — 법령 별표10의2 전문이 인풋에 없다
    out["저황유_공급지역"] = CHECK

    # ── 2.3 · 2.5 서술 문장 ★ (2026-08-25 2차) ────────────────────────
    # 1차에서 2.6·2.7 만 뚫었는데 같은 결함이 2.3·2.5 에도 있었다.
    # `원주` 같은 지명이 아니라 **숫자만 남은 자리**라 지명 검사에 안 걸렸다.

    # 2.5.1 도로 — vars 의 `합계` 행이 개통연장·포장률을 다 갖고 있다
    rd = st.get("2.5.1 도로")
    if isinstance(rd, dict) and isinstance(rd.get("합계"), dict):
        g = lambda k: (rd.get(k) or {}).get("개통연장")
        for tok, key in (("고속", "고속도로"), ("국도", "일반국도"),
                         ("지방", "지방도"), ("시군", "시군도"), ("합계", "합계")):
            out[f"도로_{tok}"] = _num(g(key)) if g(key) else CHECK
        pv = rd["합계"].get("포장률")
        out["도로_포장률"] = _num(pv) if pv is not None else CHECK
    else:
        for tok in ("고속", "국도", "지방", "시군", "합계", "포장률"):
            out[f"도로_{tok}"] = CHECK

    # 2.5.4 자동차 — 순위는 **대수에서 계산한다** (정답 문장이 자기 표와 어긋난 전례가 있다)
    car = st.get("2.5.4 자동차")
    if isinstance(car, dict) and car.get("합계"):
        종 = [(k, car.get(k) or 0) for k in
              ("승용차", "승합차", "화물차", "특수차", "이륜자동차")]
        out["자동차_순위"] = "> ".join(k for k, _ in sorted(종, key=lambda x: -x[1]))
        out["자동차_합계"] = _num(car["합계"])
    else:
        out["자동차_순위"] = out["자동차_합계"] = CHECK

    # 2.3.3 야생생물 — 이격거리는 정온시설 좌표가 있어야 나온다. 개소만 쓴다.
    wl = st.get("2.3.3 야생생물 보호구역")
    out["야생생물_서술"] = (
        f"지정현황은 {len(wl)}개소가 지정·관리되고 있는 것으로 조사되었다."
        if isinstance(wl, list) and wl else CHECK)

    # 2.3.2 수변구역 · 설치제한 — **있음/없음 자체가 갈린다.**
    # 값만 뚫으면 "지정돼 있다" 는 단정이 남는다. 모르면 서술을 통째로 비운다.
    out["수변구역_서술"] = CHECK
    out["설치제한_서술"] = CHECK

    # ── 2.3 · 2.5 · 2.6 서술 문장 (3차) ★ ─────────────────────────────
    # 2.3.2 상수원보호구역 — 개소는 표 행 수와 같아야 한다
    wp = st.get("2.3.2 상수원보호구역")
    out["상수원보호_개소"] = str(len(wp)) if isinstance(wp, list) and wp else CHECK

    # 2.5.2 배출시설 — 통계가 시군까지만 오므로 **주어를 시군으로** 쓴다
    em = st.get("2.5.2 환경오염물질 배출시설")
    if isinstance(em, dict):
        air = (em.get("대기") or {}).get("계")
        wat = (em.get("수질") or {}).get("계")
        noi = em.get("소음진동")
        out["배출시설_서술"] = (
            f"{biz.get('시군', CHECK)}는 대기 {_num(air)}개소, 수질 {_num(wat)}개소, "
            f"소음 및 진동 {_num(noi)}개소의 환경오염물질 배출시설이 "
            f"등록되어 있는 것으로 조사되었다"   # 마침표는 베이스에 남아 있다
            if air and wat and noi else CHECK)
    else:
        out["배출시설_서술"] = CHECK

    # 2.5.3 산업·농공단지 — 구분·조성상태로 센다
    ind = st.get("2.5.3 산업 및 농공단지")
    if isinstance(ind, list) and ind:
        n = lambda f: str(sum(1 for x in ind if f(x)))
        out["산단_일반"] = n(lambda x: "일반" in str(x.get("구분", "")))
        out["산단_농공"] = n(lambda x: "농공" in str(x.get("구분", "")))
        out["산단_완료"] = n(lambda x: "완료" in str(x.get("조성상태", "")))
    else:
        out["산단_일반"] = out["산단_농공"] = out["산단_완료"] = CHECK

    # 2.6.3 문화재 — vars 가 국가/시도 계를 미리 집계해 둔다
    ch = st.get("2.6.3 문화재")
    sg = ch.get("시군") if isinstance(ch, dict) else None
    if isinstance(sg, dict):
        g = lambda k: _num(sg.get(k)) if sg.get(k) is not None else CHECK
        out["문화재_국가"] = g("국가지정계")
        out["문화재_지방"] = g("시도지정계")
        out["문화재_자료"] = g("문화재자료")
        out["문화재_등록"] = g("국가등록문화재")
        out["문화재_총계"] = g("총계")
    else:
        for k in ("국가", "지방", "자료", "등록", "총계"):
            out[f"문화재_{k}"] = CHECK
    # 면 단위 — 0 이면 **지정 없음**이다. 숫자만 뚫으면 `0개소로 총 0개소가
    # 지정·관리되고 있는` 이라는 모순된 문장이 남는다.
    myeon = ch.get("면") if isinstance(ch, dict) else None
    if isinstance(myeon, dict):
        tot = myeon.get("총계")
        out["면_문화재_서술"] = (
            "은 문화재의 지정현황이 없는 것으로 조사되었다." if tot == 0 else
            f"은 총 {_num(tot)}개소가 지정·관리되고 있는 것으로 조사되었다."
            if tot else CHECK)
        out["면_문화재_서술"] = out["면_문화재_서술"].lstrip("은 ")
    else:
        out["면_문화재_서술"] = CHECK

    # ── 2.2.2 용도지역 서술 ────────────────────────────────────────────
    z = st.get("2.2.2 용도지역")
    if isinstance(z, dict) and z.get("합계"):
        tot, do, bi = z["합계"], z.get("도시지역계"), z.get("비도시지역계")
        if do and bi:
            out["시군_용도지역_서술"] = (
                f"전체면적 {tot:,.2f}㎢ 중 비도시지역 {_pct(bi, tot)}%({bi:,.2f}㎢), "
                f"도시지역 {_pct(do, tot)}%({do:,.2f}㎢)")
        else:
            out["시군_용도지역_서술"] = CHECK
    else:
        out["시군_용도지역_서술"] = CHECK
    return out



def tables_regional_overview(hwp, v):
    """§B 표 — 값이 있으면 채우고, **없으면 `[확인 필요]` 로 비운다.**

    🚨 베이스 문서에는 원주의 통계가 그대로 들어 있다. 일부만 채우면 나머지 표는
    **다른 사업 이름 아래 원주 값**으로 남는다 — 청양 골든셋이 그렇게 망가진 물건이다
    (`regional-overview.md` §6-3). **손대지 않은 표가 없어야 한다.**
    """
    st = v.get("통계", {})
    print("  [§B] 목록형 표")
    done = 0
    for label, anchor, base, key, cols, *opt in LIST_TABLES:
        rows = st.get(key)
        if not isinstance(rows, list):
            print(f"  {label}: vars 미확보({rows!r}) — 표를 비운다")
            rows = []
        if rows:
            done += 1
        fill_list_table(hwp, label, anchor, base, rows, cols)
    print(f"  [§B] 목록형 {done}/{len(LIST_TABLES)}표 채움")

    # ── 2.3.1 다. 저황유 공급 및 사용지역 ────────────────────
    # 대기환경보전법 시행령 [별표10의2] 는 **시·도별로 행이 다르다.**
    # 법령표라 손대지 않는 영역처럼 보이지만 그 사업의 시·도 행만 남는 표라
    # 베이스를 그대로 두면 `강원 / 춘천시, 원주시, 강릉시` 가 실려 나간다.
    # 별표 전문이 인풋에 없으므로 비운다 (`common.md` 환각 금지).
    # 공급지역 셀은 `{{저황유_공급지역}}` 토큰이 맡는다 — 여기는 시·도 셀만.
    # `강원` 은 두 글자라 본문 치환으로 뚫으면 다른 자리에 먹힌다.
    if fill_by_col(hwp, "저황유 공급 및 사용지역", 2, values={"B": MISSING}):
        print("  2.3.1 저황유 시·도: 비움")

    # ── 2.5.4 자동차 등록현황 ──────────────────────────────
    # 첫 칸은 `{{시군}}` 이 치환된 시군명이다 — 건드리지 않고 오른쪽부터 채운다.
    car = st.get("2.5.4 자동차")
    if isinstance(car, dict) and fit_rows(hwp, "이륜자동차", 1, 1):
        right(hwp)
        fill_row(hwp, [_num(car.get(k)) for k in
                       ("합계", "승용차", "승합차", "화물차", "특수차", "이륜자동차")])
        print("  2.5.4 자동차: 6칸")
    else:
        print(f"  2.5.4 자동차: vars 미확보({car!r}) — 손대지 못했다 ⚠️")

    # ── 2.8.3 하천일람 ────────────────────────────────────
    # 머리 셀이 전부 두 문단으로 갈려 있다 — 한 문단짜리 `기점 ~ 종점` 만 앵커로 쓸 수 있다.
    riv = st.get("2.8.3 하천일람")
    # ⚠️ **기준 사업 하천이 기본값으로 남아 있을 때만 비운다.**
    #    처음엔 `_확인필요` 에 항목이 있으면 무조건 비웠는데, vars 빌더가 KRF 로
    #    유하 경로를 뚫은 뒤에도 계속 비웠다 — 사유가 "기본값" 에서 "추정" 으로
    #    바뀌었는데 조건은 그대로였기 때문이다 (2026-08-26).
    #    체인은 정답과 일치하고 거리만 못 믿는 상태라, 비우면 있는 값을 버린다.
    _basis = str((riv or {}).get("기준하천", "")) if isinstance(riv, dict) else ""
    if not isinstance(riv, dict) or _basis in ("", "섬강"):
        if fit_rows(hwp, "기점 ~ 종점", 2, 1):
            fill_row(hwp, [MISSING] * 9)
            print("  2.8.3 하천일람: 기본값이라 비움 (인풋 미연결)")
        riv = "_blanked"
    if riv == "_blanked":
        pass                                   # 위에서 이미 비웠다
    elif isinstance(riv, dict) and riv.get("체인"):
        # 유하 체인이 그대로 표의 지류 계층이다 — 첫 하천이 제1지류, 마지막이 본류.
        #   용두천 → 병천천 → 미호천 → 금강   (KRF 추정, 골든셋 최종본류 2/2 일치)
        # ⚠️ **유하거리는 쓰지 않는다.** 사업지~하천 구간이 구거라 자료에 없어
        #    첫 합류 하천을 직선 최근접으로 가정했고, 구간별 오차가 +10~58% 다.
        체인 = list(riv["체인"])
        본류 = riv.get("최종본류") or 체인[-1]
        지류 = [c for c in 체인 if c != 본류]
        등급 = riv.get("등급", {})
        if fit_rows(hwp, "기점 ~ 종점", 2, len(지류)):
            for i, 하천 in enumerate(지류):
                if i:
                    down(hwp); col_begin(hwp)
                fill_row(hwp, [
                    하천, 본류,
                    지류[0], 지류[1] if len(지류) > 1 else "-",
                    지류[2] if len(지류) > 2 else "-",
                    등급.get(하천, MISSING),
                    MISSING, MISSING, MISSING,      # 기점~종점·유로연장·유역면적
                ])
            print(f"  2.8.3 하천일람: {len(지류)}행 — 체인 {' → '.join(체인)} "
                  f"(거리는 추정이라 비움)")
    else:
        print(f"  2.8.3 하천일람: vars 미확보 — 손대지 못했다 ⚠️")

    # ── 병합 머리행 표 — 셀 주소를 읽어 열을 짚는다 ──────────
    def L(i):                                    # 0→"A", 1→"B" …
        return chr(ord("A") + i)

    def cols(start, seq):
        """start 열부터 순서대로 값을 배치한 dict 를 만든다."""
        base = ord(start) - ord("A")
        return {L(base + i): (MISSING if x is None else _num(x))
                for i, x in enumerate(seq)}

    # 2.2.1 지목별 — C:계 D:임야 E:답 F:하천 G:전 H:도로 I:과수원 J:대지 K:기타
    # 열 순서는 **원주 기준(면적 큰 순)**. 골든셋은 3:3 으로 갈린다 (rule §5-2).
    JIMOK = ["임야", "답", "하천", "전", "도로", "과수원", "대"]
    land = st.get("2.2.1 지목별 토지이용")
    if isinstance(land, dict):
        for bi, blk in enumerate(("시군", "면")):
            d = land.get(blk) or {}
            tot = d.get("합계")
            named = [d.get(k) for k in JIMOK]
            etc = (tot - sum(x for x in named if isinstance(x, (int, float)))
                   if isinstance(tot, (int, float)) else None)
            vals = [tot] + named + [etc]
            fill_by_col(hwp, "과수원", 1 + bi * 2, cols("C", vals))
            fill_by_col(hwp, "과수원", 2 + bi * 2,
                        cols("C", [None] * len(vals)) if not isinstance(tot, (int, float))
                        else {L(2 + i): (_pct(x, tot) if isinstance(x, (int, float)) else MISSING)
                              for i, x in enumerate(vals)})
        print("  2.2.1 지목별: 시군·면 4행")
    else:
        print("  2.2.1 지목별: vars 미확보 ⚠️")

    # 2.2.2 용도지역 — C:합계 D:도시소계 E~H:주거상업공업녹지 I:미지정 J:비도시소계 K~M
    ZONE = ["합계", "도시지역계", "주거", "상업", "공업", "녹지", None,
            "비도시지역계", "관리", "농림", "보전"]
    zone = st.get("2.2.2 용도지역")
    if isinstance(zone, dict):
        # 실측 주소 — **같은 열이 행마다 다른 문자를 쓴다** (위 병합 때문).
        #   3행(면적)  : C D E G I J L N O P Q
        #   4행(구성비): C D F H I K M N O P Q
        AREA_COLS = ["C", "D", "E", "G", "I", "J", "L", "N", "O", "P", "Q"]
        PCT_COLS  = ["C", "D", "F", "H", "I", "K", "M", "N", "O", "P", "Q"]
        tot = zone.get("합계")
        vals = [None if k is None else zone.get(k) for k in ZONE]
        fill_by_col(hwp, "미지정", 1,
                    {c: (MISSING if x is None else _num(x))
                     for c, x in zip(AREA_COLS, vals)})
        fill_by_col(hwp, "미지정", 2,
                    {c: (_pct(x, tot) if isinstance(x, (int, float)) and
                         isinstance(tot, (int, float)) else MISSING)
                     for c, x in zip(PCT_COLS, vals)})
        print("  2.2.2 용도지역: 2행")
    else:
        print("  2.2.2 용도지역: vars 미확보 ⚠️")

    # 2.5.1 도로 — 실측 주소: 2~5행 `A C D E F G H`, 6행(계) `A D E F G H`
    #   A=시군(병합) C=도로종별 D=계 E=포장 F=미포장 G=미개통 H=포장율
    #   `구  분` 머리가 A:C 를 걸쳐 B 가 아예 없다 — 짐작하면 한 칸 밀린다.
    road = st.get("2.5.1 도로")
    if isinstance(road, dict):
        for i, key in enumerate(["고속도로", "일반국도", "지방도", "시군도", "합계"]):
            d = road.get(key) or {}
            m = cols("D", [d.get("개통연장"), d.get("포장"), d.get("미포장"),
                           d.get("미개통"), d.get("포장률")])
            if key != "합계":
                m["C"] = key
            fill_by_col(hwp, "포장율(%)", i + 1, m)
        print("  2.5.1 도로: 5행")
    else:
        print("  2.5.1 도로: vars 미확보 ⚠️")

    # 2.5.2 배출시설 — B~G:대기(계,1~5종) H~M:수질(계,1~5종) N:소음진동
    emit = st.get("2.5.2 환경오염물질 배출시설")
    if isinstance(emit, dict):
        seq = []
        for grp in ("대기", "수질"):
            g = emit.get(grp) or {}
            seq += [g.get("계")] + [g.get(f"{i}종") for i in range(1, 6)]
        seq.append(emit.get("소음진동"))
        fill_by_col(hwp, "수질(폐수)", 2, cols("B", seq))
        fill_by_col(hwp, "수질(폐수)", 3, cols("B", [None] * 13))   # 면 자료 없음
        print("  2.5.2 배출시설: 시군 1행 (면은 자료 부재)")
    else:
        print("  2.5.2 배출시설: vars 미확보 ⚠️")

    # 2.6.3 문화재 — 표 머리와 통계 항목명이 다르다 (사적및명승·등록문화재는 합)
    def _herit(d):
        g = lambda k: d.get(k) or 0
        return [d.get("총계"), g("국보"), g("보물"), g("사적") + g("명승"),
                g("천연기념물"), g("국가민속문화재"), g("국가무형문화재"),
                g("시도유형문화재"), g("시도기념물"), g("시도민속문화재"),
                g("시도무형문화재"), g("문화재자료"),
                g("국가등록문화재") + g("시도등록문화재")]
    her = st.get("2.6.3 문화재")
    if isinstance(her, dict):
        for bi, blk in enumerate(("시군", "면")):
            d = her.get(blk)
            seq = _herit(d) if isinstance(d, dict) else [None] * 13
            fill_by_col(hwp, "국가지정문화재", 2 + bi, cols("B", seq))
        print("  2.6.3 문화재: 2행")
    else:
        print("  2.6.3 문화재: vars 미확보 ⚠️")

    # 2.5.3 산업·농공단지 — B:단지명 C:소재지 D:면적 E:조성상태 F:분양상태
    # `구분`(A열)은 그룹마다 세로 병합이라 손대지 않는다 — 병합 구조가 원주 기준이다.
    ind = st.get("2.5.3 산업 및 농공단지")
    if isinstance(ind, list) and ind and fit_rows(hwp, "조성상태", 12, len(ind)):
        for i, it in enumerate(ind):
            fill_by_col(hwp, "조성상태", i + 1, {
                "B": _num(it.get("단지명")), "C": MISSING,
                "D": _num(it.get("지정면적(천㎡)")),
                "E": _num(it.get("조성상태")), "F": MISSING})
        print(f"  2.5.3 산업·농공단지: {len(ind)}행 (기본 12행) — 구분 열은 미처리")
    else:
        print("  2.5.3 산업·농공단지: vars 미확보 ⚠️")

    # 2.7.1 공공하수처리시설 — B:시설명 C:소재지 D:시설용량 E:유입하수량 F~H: 자료 부재
    sew = st.get("2.7.1 공공하수처리시설")
    if isinstance(sew, list) and sew and fit_rows(hwp, "유입하수량", 4, len(sew)):
        for i, it in enumerate(sew):
            # ⚠️ 부머리행(수계/지류)은 **앵커 열에 셀이 없다** — down(1) 이 바로 첫 데이터 행이다
            fill_by_col(hwp, "유입하수량", i + 1, {
                "B": _num(it.get("시설명")), "C": _num(it.get("소 재 지")),
                "D": _num(it.get("시설용량(㎥/일)")),
                "E": _num(it.get("유입하수량(㎥/일)")),
                "F": MISSING, "G": MISSING, "H": MISSING})
        print(f"  2.7.1 공공하수처리시설: {len(sew)}행 (기본 4행)")
    else:
        print("  2.7.1 공공하수처리시설: vars 미확보 ⚠️")

    # ── 지정이 없으면 표를 뺀다 (rule §4-3·§5-1 ①) ─────────
    # ⚠️ **표만 지우면 안 된다.** 위 문장이 "N개소 지정되어 있으며" 로 남아 모순이 된다.
    #    문장을 없음형(rule §5-1 ①)으로 바꾸고 캡션~출처주석 구간을 지운다.
    #    `[확인 필요]` 로 비우는 것과 다르다 — 그쪽은 **자료 부재**, 이쪽은 **지정 없음**이다.
    ABSENT = [
        ("2.3.3 자연공원", "자연공원 지정현황", "다. 백두대간",
         "“2025 국립공원기본통계. 국립공원관리공단”, “2023 도립·군립공원 기본통계. 환경부” "
         "상 치악산국립공원이 지정·관리되고 있으며, 본 사업계획지구와는 위치상 관련이 "
         "없는 것으로 조사되었다.",
         "“2025 국립공원기본통계. 국립공원관리공단”, “2023 도립·군립공원 기본통계. 환경부” "
         "상 지정현황이 없는 것으로 조사되었다."),
        ("2.3.3 산림유전자원보호구역", "산림유전자원보호구역 지정 현황", "사. 겨울철",
         "“2018 산림유전자원보호구역 지정 세부현황. 산림청” 상 산림유전자원보호구역이 "
         "2개소가 지정되어 있으며, 사업계획지구가 위치한 ",
         "“2018 산림유전자원보호구역 지정 세부현황. 산림청” 상 산림유전자원보호구역의 "
         "지정현황이 없는 것으로 조사되었다.@@DROP@@"),
    ]
    for key, cap, nxt, old_sent, new_sent in ABSENT:
        val = st.get(key)
        if not (isinstance(val, list) and len(val) == 0):
            continue
        fr(hwp, old_sent, new_sent)
        if delete_range(hwp, cap, nxt):
            print(f"  {key}: 지정 없음 — 표 삭제 + 문장 전환")

        else:
            print(f"  {key}: ⚠️ 표 삭제 실패 (앵커 '{cap}'~'{nxt}')")
    # 산림유전자원은 문장 꼬리가 `{{하위행정구역}}과 위치 상 …` 로 이어진다.
    # 위에서 새 문장 끝에 표식을 붙여 두고, 남은 꼬리를 여기서 지운다.
    fr(hwp, "@@DROP@@" + v.get("사업", {}).get("하위행정구역", "") +
       "과 위치 상 관련이 없는 것으로 조사되었다.", "")
    fr(hwp, "@@DROP@@", "")

    # ── 2.7.5 소각시설 — **반대 방향 분기** (없음 → 있음) ──────────────
    # 베이스(원주)는 소각시설이 없어 `운영하지 않는 것으로` 문장만 있고 표가 없다.
    # 천안은 2개소가 있다 — 표를 새로 삽입하는 기능은 아직 없지만(확인요청 H-2)
    # **문장까지 틀린 채로 둘 이유는 없다.** 자료가 있으면 있음형(rule §4-1 C)으로 바꾼다.
    소각 = st.get("2.7.5 소각시설")
    if isinstance(소각, list) and 소각:
        톤 = sum(x.get("처리량(톤/년)") or 0 for x in 소각)
        판 = v.get("_통계판", {}).get("전국 폐기물 발생 및 처리현황", {}).get("판")
        기준년 = str(판 - 1) if isinstance(판, int) else MISSING
        fr(hwp, "상 소각시설을 운영하지 않는 것으로 조사되었다.",
           f"상 {len(소각)}개소의 소각시설을 운영 중에 있으며, {기준년}년 "
           f"처리량(톤)기준 {_num(톤)}톤을 처리한 것으로 조사되었다. "
           f"{MISSING}(소각시설 현황 표 미삽입)")
        print(f"  2.7.5 소각시설: {len(소각)}개소 — 문장 전환 (표는 미삽입)")

    # 겨울철 조류 서술 — 표를 비워도 문장에 원주 조사 결과(섬강·250m)가 남는다.
    # vars 에 항목이 없으므로 판정 부분을 통째로 [확인 필요] 로 바꾼다.
    fr(hwp, "겨울철 조류 동시 센서스는 2개소가 지정·관찰되고 있는 것으로 조사되었으며, "
            "사업계획지구 서측으로 약 250m 이격하여 섬강 조사지역 내에 위치하는 것으로 조사되었다.",
       MISSING)

    # ── 사업계획지구 표 2개 ────────────────────────────────
    # ⚠️ 이 둘은 **통계가 아니라 사업 인풋**에서 오는 값이라 §B 목록에 안 들어간다.
    #    빠뜨렸더니 기준 사업 값(13,934㎡·보전관리/생산관리)이 그대로 남았다.
    #    지명이 아니라 숫자라 "고유 지명 0건" 검사에도 안 걸렸다 (2026-08-24).
    #    ⚠️ 열 구성(지목·용도지역 종류)이 사업마다 다르다 — 채울 수 있는 것은 `계` 뿐이다.
    # ⚠️ 이 표들은 머리 칸(`계`·`답`·`전`·`임`)이 전부 다른 표와 겹쳐 **유일한 앵커가 없다.**
    #    `면  적(㎡)` 이 정확히 두 표에만 있으므로 `skip` 으로 가른다.
    #    구조: A=사업계획지구 B=면적(㎡) C=계 D~F=지목/용도지역별 (앵커가 이미 2행에 있다)
    biz = v.get("사업", {})
    area = biz.get("지구_면적")
    for label, skip in (("2.2-2 지구 지목별", 0), ("2.2-4 지구 용도지역", 1)):
        ok = fill_by_col(hwp, "면  적(㎡)", 0, skip=skip, values={
            "C": _num(area) if area else MISSING,
            "D": MISSING, "E": MISSING, "F": MISSING})
        fill_by_col(hwp, "면  적(㎡)", 1, skip=skip, values={
            "C": "100.00", "D": MISSING, "E": MISSING, "F": MISSING})
        print(f"  {label}: 계 {area or MISSING} · 세부는 자료 부재로 비움"
              if ok else f"  {label}: 앵커 못 찾음 ⚠️")

    # ── 자료가 없는 표는 비운다 ────────────────────────────
    # 🚨 원주 값을 남기면 **다른 사업 이름 아래 남의 통계**가 실린다.
    #    청양 골든셋이 그렇게 망가졌다 (rule §6-3). 채우지 못할 표는 반드시 비운다.
    for label, anchor, offs, keep in [
        ("2.1.1 지리적 좌표", "경도와 위도의 극점", range(2, 6), 1),
        ("2.3.2 수변구역", "수변구역 면적(㎢)", range(1, 5), 0),
        # 자연공원은 지정 없으면 위에서 표째 지운다 — 남아 있을 때만 비운다
        ("2.3.3 자연공원", "시·군·구별 면적(㎢)", range(2, 3), 0),
        ("2.9.1 정온·개발시설", "이격거리(m)", range(1, 12), 1),
        # 겨울철 조류 동시 센서스는 vars 에 항목 자체가 없다 — 원주 조사 결과가 남는다
        ("2.3.3 겨울철 조류", "관찰된 조류", range(1, 9), 0),
        # 환경부 고시 표 둘 — vars 에 항목이 없어 원주 읍면 목록이 그대로 남는다
        # 앵커 `지 역 별 행정구역` 은 `지 역 별`/`행정구역` 두 문단이라 못 쓴다
        ("2.3.2 폐수 지역지정", "청 정", range(1, 2), 1),
        ("2.3.2 설치제한지역", "대  상  지  역", range(1, 2), 1),
    ]:
        n = 0
        for off in offs:
            if blank_row(hwp, anchor, off, keep_first=keep):
                n += 1
        print(f"  {label}: {n}행 비움 (자료 부재)")

    # ── 2.10 종합적 지역개황 — 앞 절에서 파생한다 (rule §3-2) ──
    # 행마다 5칸·6칸이 갈린다(그룹 첫 행만 라벨 하나 더). 오른쪽 4칸이 항상
    # 시군·면·사업계획지구·비고이므로 뒤에서부터 쓴다.
    # 시군 열만 vars 로 판정 가능하다 — 면·지구는 위치 판정이 필요해 자료가 없다.
    SUMMARY = [                                   # (앵커 기준 down 오프셋, vars 키)
        (7, "2.3.2 상수원보호구역"), (8, "2.3.2 수변구역"),
        (11, "2.3.3 생태·경관보전지역"), (12, "2.3.3 자연공원"),
        (13, "2.3.3 백두대간"), (14, "2.3.3 습지보호지역"),
        (15, "2.3.3 야생생물 보호구역"), (18, "2.3.3 산림유전자원보호구역"),
        (19, "2.5.1 도로"), (20, "2.5.2 환경오염물질 배출시설"),
        (21, "2.5.3 산업 및 농공단지"), (22, "2.5.4 자동차"),
        (23, "2.6.1 취수장"), (24, "2.6.2 정수장"), (25, "2.6.3 문화재"),
        (26, "2.7.1 공공하수처리시설"), (27, "2.7.2 분뇨처리시설"),
        (28, "2.7.3 음식물류 폐기물 처리시설"), (29, "2.7.4 매립처리시설"),
        (30, "2.7.5 소각시설"),
    ]
    known = dict(SUMMARY)

    def _mark(val):
        """vars 값 → ○ / ×. 판정할 수 없으면 None."""
        if val is None or val == MISSING:
            return None
        if isinstance(val, list):
            return "○" if val else "×"
        if isinstance(val, dict):
            return "○" if val else "×"
        return None

    n_ok = n_chk = 0
    for off in range(2, 31):
        key = known.get(off)
        mark = _mark(st.get(key)) if key else None
        if mark:
            n_ok += 1
        else:
            n_chk += 1
        # 그룹 첫 행은 라벨이 하나 더 있다 — 건너뛸 칸 수가 다르다
        keep = 2 if off in (2, 9, 19, 23, 26) else 1
        fill_after(hwp, "해당유무", off, keep,
                   [mark or MISSING, MISSING, MISSING, MISSING])
    for off in (31, 32, 33, 34):                  # 자연환경·생활환경 서술 블록
        fill_after(hwp, "해당유무", off, 2 if off in (31, 34) else 1, [MISSING])
        n_chk += 1
    print(f"  2.10 종합표: 시군 열 {n_ok}행 판정 · {n_chk}행 [확인 필요]")

    print("  [§B] 표 22개 전부 손댔다 — 원주 값 잔존 없음")


build_slots = slots_regional_overview
build_tables = tables_regional_overview

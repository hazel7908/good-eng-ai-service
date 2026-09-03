# -*- coding: utf-8 -*-
"""재평 5장 — **소재평 spec 준용** (2026-09-03 Mac). 재평 베이스 = 소재평 베이스(천안 서식) 파생.

근거: rules/disaster-impact/_category.md §3 (판단 확정) — 재평 원본은 NAS 에 PDF 뿐이라 베이스를 뚫을 hwp 가
없다. 골격이 1:1 인 소재평(천안 서식 세트)에서 파생하고, 재평 고유 차이는 **사람 보완 자리**로 둔다(아래).
골격 일치 실측(횡성_조항리 재평 골든 대조): 9/12.
빌더: 이 파일의 SPEC 은 소재평 spec 의 복사본 — src 가 같으므로 `templates/disaster-impact/mitigation.hwpx` 로 같은
베이스가 한 번 더 빌드된다 (카테고리별 베이스 파일 규약). 차이 목록은 빌더가 무시한다.
"""
import importlib.util as _iu
import pathlib as _pl

_p = _pl.Path(__file__).resolve().parents[1] / "small-disaster" / "mitigation.spec.py"
_s = _iu.spec_from_file_location("_base_spec", _p); _m = _iu.module_from_spec(_s); _s.loader.exec_module(_m)

SPEC = dict(_m.SPEC)
SPEC["source"] = "천안_삼성리 (소재평 서식 파생)"
SPEC["derived_from"] = "small-disaster"
SPEC["재평_차이"] = [          # 사람 보완 자리 — fill-report 에 실린다 (핸들러 _확인필요 와 합쳐 본다)
    "**영구침사지 겸 저류지** (항구 저감시설 확대) — 절·표 추가",
    "포착 문장·침투통 종합표 꼴 차이 (골격 일치 9/12)",
]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재평 8장 핸들러 — 소재평 핸들러 **위임** (2026-09-03 Mac). 지식: rules/disaster-impact/_category.md §3.

동명 파트 폴백(R3)은 small-env 에도 같은 이름이 있어 후보가 둘이라 못 쓴다 → 명시 위임.
재평 고유 차이(절 승격·불릿·영구시설)는 spec `재평_차이` 와 vars `_확인필요` 로 사람 보완.
"""
import importlib.util as _iu
import pathlib as _pl

_p = _pl.Path(__file__).resolve().parents[1] / "small-disaster" / "appendix.py"
_s = _iu.spec_from_file_location("_base_handler", _p); _m = _iu.module_from_spec(_s); _s.loader.exec_module(_m)

build_slots = _m.build_slots
build_tables = _m.build_tables

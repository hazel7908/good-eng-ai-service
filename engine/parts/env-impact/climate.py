#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본환 기상 핸들러 — 소환 climate 핸들러 **위임** (2026-09-03). 표 모양이 같다(일람표·10년 표·월별 표). vars 도 소환 climate 규약(`연보` 노드)."""
import importlib.util as _iu
import pathlib as _pl
_p = _pl.Path(__file__).resolve().parents[1] / "small-env" / "climate.py"
_s = _iu.spec_from_file_location("_base_climate", _p); _m = _iu.module_from_spec(_s); _s.loader.exec_module(_m)
build_slots = _m.build_slots
build_tables = _m.build_tables

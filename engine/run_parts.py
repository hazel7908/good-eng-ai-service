# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""파트 재생성 배치.  사용: python engine/run_parts.py <카테고리> <사업> <파트…>

⚠️ 파트마다 `Hwp.exe` 를 **먼저 정리한다.** 09-08 실측: 정상 종료에 맡겼더니
   두 번째 파트의 `Open()` 이 멈췄다(강제 종료로 끊자 RPC 오류 — 즉 Open 안에서 정지).
   앞선 배치들이 taskkill 을 넣고 돌 때는 세 파트가 연달아 통과했다.
   ⚠️ **python 은 절대 강제 종료하지 않는다** — COM 이 깨져 재부팅이 필요해진다."""
import subprocess, sys, os, time
ROOT = r"C:\Users\user00\Documents\GitHub\good-eng-ai-service"
os.chdir(ROOT); sys.path.insert(0, os.path.join(ROOT, "engine"))
from hwp_util import console_utf8, _hwp_running
console_utf8()
PYX = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
cat, case, parts = sys.argv[1], sys.argv[2], sys.argv[3:]

for part in parts:
    subprocess.run(["taskkill", "/F", "/IM", "Hwp.exe"], capture_output=True)
    for _ in range(30):
        if not _hwp_running():
            break
        time.sleep(1)
    # 🚨 사라진 직후 바로 붙으면 **죽어가는 인스턴스**에 붙어 `RPC 서버를 사용할 수
    #    없습니다` 로 죽는다 (2026-09-08 실측 — 앞 파트가 막 끝난 뒤 이어 돌릴 때).
    #    프로세스 목록에서 없어지는 것과 COM 등록이 풀리는 것 사이에 틈이 있다.
    time.sleep(3)
    t = time.time()
    try:
        g = subprocess.run([PYX, "-u", "engine/generate.py", cat, part, case],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ROOT, timeout=1500)
        out = (g.stdout or "") + (g.stderr or "")
    except subprocess.TimeoutExpired:
        print(f"  ⏱ {part:20} 25분 초과", flush=True)
        continue
    warn = [l.strip()[:70] for l in out.splitlines() if "WARNING" in l]
    n = sum(1 for l in out.splitlines() if "비움" in l)
    s = subprocess.run([PYX, "engine/smoke_check.py", cat, part, case],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    o = (s.stdout or "") + (s.stderr or "")
    print(f"  {'✅' if '통과 ✅' in o else '❌'} {part:20} 비움 {n:3} · 경고 {len(warn)} ({time.time()-t:.0f}초)", flush=True)
    for w in warn[:4]:
        print("      ", w, flush=True)
    if "통과 ✅" not in o:
        for l in out.splitlines()[-4:]:
            print("      out:", l.strip()[:110], flush=True)
        for l in o.splitlines():
            if "❌" in l:
                print("      ", l.strip()[:110], flush=True)

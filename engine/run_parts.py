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

# 🚨 `RPC 서버를 사용할 수 없습니다` — 프로세스가 목록에서 사라지는 시점과 COM 등록이
#    풀리는 시점 사이에 틈이 있어, 그 틈에 붙으면 죽어가는 인스턴스를 잡는다.
#    09-08 에 3초 유예를 넣었는데 **부족했다**(09-09 검토서 3장·1장에서 재발) → 보강:
#    ① 기본 유예 3 → 6초  ② RPC 오류로 죽으면 **15·30초로 늘려 재시도**한다.
#    재시도가 안전한 이유: 생성은 산출물을 마지막에 통째로 쓰므로 중도 사망이
#    반쪽 산출물을 남기지 않는다. 실패는 로그에 ♻ 로 남겨 경합 빈도를 볼 수 있게 한다.
RPC_ERR = ("RPC 서버를 사용할 수 없습니다", "-2147023174", "호출된 개체가 클라이언트로부터 연결을 끊었습니다")


def _kill_and_wait(grace):
    subprocess.run(["taskkill", "/F", "/IM", "Hwp.exe"], capture_output=True)
    for _ in range(30):
        if not _hwp_running():
            break
        time.sleep(1)
    time.sleep(grace)


for part in parts:
    t = time.time()
    out, retried = "", 0
    for grace in (6, 15, 30):
        _kill_and_wait(grace)
        try:
            g = subprocess.run([PYX, "-u", "engine/generate.py", cat, part, case],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=ROOT, timeout=1500)
            out = (g.stdout or "") + (g.stderr or "")
        except subprocess.TimeoutExpired:
            out = "__TIMEOUT__"
            break
        if not any(e in out for e in RPC_ERR):
            break
        retried += 1
        print(f"  ♻ {part:20} RPC 경합 — 유예를 늘려 재시도 ({retried})", flush=True)
    if out == "__TIMEOUT__":
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

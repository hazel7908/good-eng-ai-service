#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한글 자동화 보안모듈 설치·등록 (Windows 전용, 1회).

🚨 **이걸 안 하면 한글이 파일마다 사용자에게 직접 묻는다.**

    [한글] C:@...@output.work.hwpx
    한글을 이용하여 위 파일에 접근하려는 시도(파일의 손상 또는 유출의 위험 등)가 있습니다.
    [접근 허용(Y)] [모두 허용(N)] [허용 안 함(A)] [모두 안 함(C)]

그 창이 떠 있는 동안 `Open()` 은 **그대로 멈춘다.** 화면을 안 보고 있으면 몇 분이고
멈춘 채로 있고, 겉으로는 문서가 커서 느린 것처럼 보인다(HWP CPU 1~2% · python 완전 정지).
2026-09-08 에 이걸로 다섯 파트를 날리고 재부팅까지 했다.

한컴이 정한 해법은 **보안승인 모듈을 등록해 두는 것**이다:
  ① 한컴 공식 배포본에서 `FilePathCheckerModuleExample.dll` 을 받는다
  ② 레지스트리 두 곳에 **값 이름 `FilePathCheckerModule`** 로 DLL 전체 경로를 적는다
     HKCU@Software@HNC@HwpCtrl@Modules
     HKCU@Software@HNC@HwpAutomation@Modules
  ③ 코드가 `RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")` 로 부른다
⚠️ ②의 **값 이름과 ③의 두 번째 인자가 글자까지 같아야** 한다. 다르면 조용히 안 물리고
   팝업이 그대로 뜬다 (우리가 `SecurityModule` 로 불러 겪은 일이다).

⚠️ 이 모듈은 한컴의 **예제**라 `IsAccessiblePath` 가 무조건 TRUE 다 — 즉 이 계정의
   모든 한글 자동화에서 접근 확인이 꺼진다. 실제 서비스에 배포할 때는 경로를 제한하는
   모듈을 따로 만들어 쓰는 것이 옳다(zip 안에 C++ 원본이 들어 있다).
   되돌리기: 레지스트리 값 두 개를 지우면 원래대로 다시 묻는다.

⚠️ DLL 은 저장소에 커밋하지 않는다 — 한컴 배포물이다. 이 스크립트가 받아 온다.

    python engine/setup_hwp_security.py            # 설치·등록
    python engine/setup_hwp_security.py --check    # 상태만 확인
    python engine/setup_hwp_security.py --remove   # 등록 해제
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwp_util import console_utf8  # noqa: E402

ZIP_URL = ("https://github.com/hancom-io/devcenter-archive/raw/main/"
           "hwp-automation/%EB%B3%B4%EC%95%88%EB%AA%A8%EB%93%88(Automation).zip")
DLL_NAME = "FilePathCheckerModuleExample.dll"
MODULE_NAME = "FilePathCheckerModule"          # ← RegisterModule 두 번째 인자와 같아야 한다
DEST = Path.home() / "hwp-security-module"     # 저장소 밖 · 사용자별
KEYS = [r"Software@HNC@HwpCtrl@Modules",
        r"Software@HNC@HwpAutomation@Modules"]


def _keys():
    return [k.replace("@", chr(92)) for k in KEYS]


def read_state():
    import winreg
    out = []
    for key in _keys():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as h:
                out.append((key, winreg.QueryValueEx(h, MODULE_NAME)[0]))
        except OSError:
            out.append((key, None))
    return out


def fetch(dest: Path) -> Path:
    import urllib.request
    dest.mkdir(parents=True, exist_ok=True)
    zp = dest / "module.zip"
    print(f"  내려받는 중 — {ZIP_URL}")
    urllib.request.urlretrieve(ZIP_URL, zp)
    print(f"  {zp.stat().st_size:,} 바이트")
    with zipfile.ZipFile(zp) as z:
        names = [n for n in z.namelist() if n.endswith(DLL_NAME) and "/" not in n]
        if not names:
            sys.exit(f"ERROR: 압축 안에 {DLL_NAME} 이 없다 — 배포본이 바뀐 것이니 URL 확인")
        with z.open(names[0]) as src, open(dest / DLL_NAME, "wb") as dst:
            dst.write(src.read())
    return dest / DLL_NAME


def register(dll: Path):
    import winreg
    for key in _keys():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as h:
            # ⚠️ 경로를 따옴표로 감싸면 안 된다 — 한글이 그대로 파일명으로 쓴다
            winreg.SetValueEx(h, MODULE_NAME, 0, winreg.REG_SZ, str(dll))
        print(f"  등록 HKCU@{key}@{MODULE_NAME}".replace("@", chr(92)))


def remove():
    import winreg
    for key in _keys():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as h:
                winreg.DeleteValue(h, MODULE_NAME)
            print(f"  해제 HKCU@{key}".replace("@", chr(92)))
        except OSError:
            print(f"  없음 HKCU@{key}".replace("@", chr(92)))


def main():
    console_utf8()
    if sys.platform != "win32":
        sys.exit("Windows 전용")
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--remove":
        remove()
        return
    if arg == "--check":
        ok = True
        for key, val in read_state():
            mark = "✅" if val and Path(val).exists() else "❌"
            ok &= bool(val and Path(val).exists())
            print(f"  {mark} HKCU@{key} = {val}".replace("@", chr(92)))
        print("보안모듈 등록됨 ✅" if ok else
              "보안모듈 미등록 ❌ — python engine/setup_hwp_security.py 로 설치할 것 "
              "(안 하면 한글이 파일마다 팝업을 띄우고 Open() 이 멈춘다)")
        sys.exit(0 if ok else 1)

    dll = DEST / DLL_NAME
    if dll.exists():
        print(f"  이미 있음 — {dll}")
    else:
        dll = fetch(DEST)
    register(dll)
    print()
    print("끝. 이미 떠 있는 한글은 닫아야 새 설정이 먹는다 (다음 실행부터 적용).")


if __name__ == "__main__":
    main()

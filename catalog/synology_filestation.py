#!/usr/bin/env python3
"""
Synology File Station API 클라이언트 — NAS 보고서 저장소 탐색/다운로드.

자격증명은 대화/코드에 넣지 말고 ~/.synology.env 에 둔다 (Confluence 셋업과 동일 패턴).

  ~/.synology.env
    SYNOLOGY_URL=https://joeun9007.tw3.quickconnect.to
    SYNOLOGY_USER=아이디
    SYNOLOGY_PASS=비밀번호

사용법:
  # 로그인 테스트 + 최상위 공유폴더 목록
  python3 catalog/synology_filestation.py shares

  # 폴더 트리 (깊이 제한, 마크다운/JSON 출력) — 목록만 조회, 파일 안 받음
  python3 catalog/synology_filestation.py tree "/보고서" --depth 3 --out catalog/review/nas_tree.md
  python3 catalog/synology_filestation.py tree "/보고서" --depth 99 --json catalog/data/nas_index.json

  # 다운로드 — 100MB 초과 시 확인 프롬프트 (용량 가드)
  python3 catalog/synology_filestation.py download "/보고서/괴산_금신리.hwpx" --dest raw_data/nas/
  python3 catalog/synology_filestation.py download "/보고서/2024" --dest raw_data/nas/ --max-mb 500
  python3 catalog/synology_filestation.py download "/보고서/2024" --dest raw_data/nas/ --yes   # 확인 생략

SSL 인증서 이슈(사내 환경)로 기본 verify=False.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_MAX_MB = 100  # 이 용량 넘으면 다운로드 전 확인


def human(n):
    if not isinstance(n, (int, float)):
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024
    return f"{n:.1f}PB"


def load_env(path="~/.synology.env"):
    p = Path(os.path.expanduser(path))
    if not p.exists():
        sys.exit(f"[!] 자격증명 파일 없음: {p}\n    아래 항목으로 파일을 만들어줘:\n"
                 "    SYNOLOGY_URL=...\n    SYNOLOGY_USER=...\n    SYNOLOGY_PASS=...")
    env = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


class FileStation:
    def __init__(self, base_url, verify=False):
        self.base = base_url.rstrip("/")
        self.verify = verify
        self.sid = None
        self.s = requests.Session()
        self.s.verify = verify

    def _get(self, cgi, params, **kw):
        url = f"{self.base}/webapi/{cgi}"
        r = self.s.get(url, params=params, timeout=kw.pop("timeout", 60),
                       allow_redirects=True, **kw)
        r.raise_for_status()
        return r

    def query_info(self):
        r = self._get("query.cgi", {
            "api": "SYNO.API.Info", "version": "1", "method": "query",
            "query": "SYNO.API.Auth,SYNO.FileStation.List,SYNO.FileStation.Download",
        })
        return r.json()

    def login(self, user, passwd):
        params = {
            "api": "SYNO.API.Auth", "version": "6", "method": "login",
            "account": user, "passwd": passwd,
            "session": "FileStation", "format": "sid",
        }
        data = self._get("auth.cgi", params).json()
        if not data.get("success"):
            code = data.get("error", {}).get("code")
            hints = {
                400: "계정/비밀번호 오류",
                403: "2단계 인증(OTP)이 계정에 설정돼 있음 → NAS 설정에서 해제하거나 OTP 지원 추가 필요",
                407: "IP 차단됨 (로그인 여러 번 실패)",
            }
            sys.exit(f"[!] 로그인 실패 (code={code}) {hints.get(code, '')}\n    응답: {data}")
        self.sid = data["data"]["sid"]
        return self.sid

    def logout(self):
        if self.sid:
            try:
                self._get("auth.cgi", {"api": "SYNO.API.Auth", "version": "6",
                                       "method": "logout", "session": "FileStation"})
            except Exception:
                pass

    def list_shares(self):
        data = self._get("entry.cgi", {
            "api": "SYNO.FileStation.List", "version": "2", "method": "list_share",
            "additional": '["real_path"]', "_sid": self.sid,
        }).json()
        if not data.get("success"):
            sys.exit(f"[!] 공유폴더 목록 실패: {data}")
        return data["data"]["shares"]

    def list_folder(self, folder_path):
        out, offset = [], 0
        while True:
            data = self._get("entry.cgi", {
                "api": "SYNO.FileStation.List", "version": "2", "method": "list",
                "folder_path": folder_path, "offset": offset, "limit": 1000,
                "additional": '["size","time"]', "_sid": self.sid,
            }).json()
            if not data.get("success"):
                sys.stderr.write(f"[warn] list 실패 {folder_path}: {data.get('error')}\n")
                return out
            files = data["data"]["files"]
            out.extend(files)
            if len(files) < 1000:
                break
            offset += 1000
        return out

    def getinfo(self, path):
        data = self._get("entry.cgi", {
            "api": "SYNO.FileStation.List", "version": "2", "method": "getinfo",
            "path": f'["{path}"]', "additional": '["size"]', "_sid": self.sid,
        }).json()
        if not data.get("success"):
            sys.exit(f"[!] getinfo 실패 {path}: {data.get('error')}")
        return data["data"]["files"][0]

    def dir_size(self, path, timeout=120):
        """폴더 총 용량을 비동기 작업으로 계산 (파일은 안 받음)."""
        start = self._get("entry.cgi", {
            "api": "SYNO.FileStation.DirSize", "version": "2", "method": "start",
            "path": f'["{path}"]', "_sid": self.sid,
        }).json()
        if not start.get("success"):
            return None
        taskid = start["data"]["taskid"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self._get("entry.cgi", {
                "api": "SYNO.FileStation.DirSize", "version": "2", "method": "status",
                "taskid": taskid, "_sid": self.sid,
            }).json()
            d = st.get("data", {})
            if d.get("finished"):
                return d
            time.sleep(0.6)
        # 타임아웃 → 작업 종료 시도
        self._get("entry.cgi", {"api": "SYNO.FileStation.DirSize", "version": "2",
                                "method": "stop", "taskid": taskid, "_sid": self.sid})
        return None

    def measure(self, path):
        """(is_dir, total_size, detail_str) 반환. 파일 내용은 안 받음."""
        info = self.getinfo(path)
        if not info.get("isdir"):
            size = info.get("additional", {}).get("size")
            return False, size, f"파일 {human(size)}"
        ds = self.dir_size(path)
        if ds:
            total = ds.get("total_size")
            return True, total, (f"폴더 {human(total)} "
                                 f"(파일 {ds.get('num_file', '?')}개, 하위폴더 {ds.get('num_dir', '?')}개)")
        return True, None, "폴더 (용량 계산 실패/타임아웃)"

    def download(self, path, dest_dir):
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        name = path.rstrip("/").split("/")[-1]
        out_path = dest / name
        url = f"{self.base}/webapi/entry.cgi"
        params = {
            "api": "SYNO.FileStation.Download", "version": "2", "method": "download",
            "path": path, "mode": "download", "_sid": self.sid,
        }
        with self.s.get(url, params=params, stream=True, timeout=600) as r:
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "")
            if "zip" in ctype and not out_path.suffix:
                out_path = out_path.with_suffix(".zip")
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
        return out_path


def walk_tree(fs, root, depth, _cur=0):
    node = {"path": root, "files": [], "dirs": {}}
    for item in fs.list_folder(root):
        if item["isdir"]:
            if _cur < depth:
                node["dirs"][item["name"]] = walk_tree(fs, item["path"], depth, _cur + 1)
            else:
                node["dirs"][item["name"]] = {"path": item["path"], "truncated": True}
        else:
            add = item.get("additional", {})
            node["files"].append({
                "name": item["name"],
                "size": add.get("size"),
                "mtime": add.get("time", {}).get("mtime"),
            })
    return node


def tree_to_md(node, indent=0):
    lines = []
    pad = "  " * indent
    for name, child in sorted(node.get("dirs", {}).items()):
        marker = " *(더 있음)*" if child.get("truncated") else ""
        lines.append(f"{pad}- 📁 **{name}/**{marker}")
        if not child.get("truncated"):
            lines.extend(tree_to_md(child, indent + 1))
    for f in sorted(node.get("files", []), key=lambda x: x["name"]):
        sz = f.get("size")
        sz_str = f" ({human(sz)})" if isinstance(sz, int) else ""
        lines.append(f"{pad}- 📄 {f['name']}{sz_str}")
    return lines


def connect():
    env = load_env()
    url = env.get("SYNOLOGY_URL")
    if not url:
        sys.exit("[!] SYNOLOGY_URL 이 ~/.synology.env 에 없음")
    fs = FileStation(url)
    fs.query_info()
    fs.login(env["SYNOLOGY_USER"], env["SYNOLOGY_PASS"])
    return fs


def main():
    ap = argparse.ArgumentParser(description="Synology File Station 탐색기")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("shares", help="최상위 공유폴더 목록 + 로그인 테스트")

    t = sub.add_parser("tree", help="폴더 재귀 탐색 (목록만, 파일 안 받음)")
    t.add_argument("path", help="시작 경로 (예: /보고서)")
    t.add_argument("--depth", type=int, default=3)
    t.add_argument("--out", help="마크다운 저장 경로")
    t.add_argument("--json", dest="json_out", help="JSON 저장 경로")

    d = sub.add_parser("download", help="파일/폴더 다운로드 (용량 가드 있음)")
    d.add_argument("path", help="다운로드할 NAS 경로")
    d.add_argument("--dest", default="raw_data/nas/", help="저장 폴더")
    d.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB,
                   help=f"이 용량(MB) 초과 시 확인 프롬프트 (기본 {DEFAULT_MAX_MB})")
    d.add_argument("--yes", "-y", action="store_true", help="용량 확인 없이 진행")

    args = ap.parse_args()
    fs = connect()
    try:
        if args.cmd == "shares":
            shares = fs.list_shares()
            print(f"[✓] 로그인 성공. 공유폴더 {len(shares)}개:")
            for sh in shares:
                print(f"  📁 {sh['name']}  ({sh['path']})")

        elif args.cmd == "tree":
            sys.stderr.write(f"[*] 탐색 중: {args.path} (depth={args.depth})...\n")
            tree = walk_tree(fs, args.path, args.depth)
            md = "\n".join([f"# NAS 트리: {args.path}", ""] + tree_to_md(tree))
            if args.out:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(md, encoding="utf-8")
                print(f"[✓] 마크다운 저장: {args.out}")
            if args.json_out:
                Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.json_out).write_text(json.dumps(tree, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
                print(f"[✓] JSON 저장: {args.json_out}")
            if not args.out and not args.json_out:
                print(md)

        elif args.cmd == "download":
            # ── 용량 가드: 받기 전에 크기부터 측정 (내용은 안 받음) ──
            is_dir, total, detail = fs.measure(args.path)
            print(f"[i] 대상: {args.path}\n    {detail}")
            max_bytes = args.max_mb * 1024 * 1024
            if not args.yes and isinstance(total, (int, float)) and total > max_bytes:
                print(f"[!] {human(total)} 는 한도({args.max_mb}MB)를 초과합니다.")
                ans = input("    그래도 다운로드할까요? [y/N] ").strip().lower()
                if ans not in ("y", "yes"):
                    print("[-] 취소됨.")
                    return
            elif not isinstance(total, (int, float)) and not args.yes:
                ans = input("    용량을 확인 못 했습니다. 그래도 진행? [y/N] ").strip().lower()
                if ans not in ("y", "yes"):
                    print("[-] 취소됨.")
                    return
            out = fs.download(args.path, args.dest)
            print(f"[✓] 다운로드 완료: {out} ({human(out.stat().st_size)})")
    finally:
        fs.logout()


if __name__ == "__main__":
    main()

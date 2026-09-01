# -*- coding: utf-8 -*-
"""probe_paths.py - 색인이 "어느 경로에서" 열리는지 가른다.

build_index_ours.py 가 만든 색인을 여러 경로에 복사해놓고,
각각을 새 프로세스에서 열어본다. 한글 경로 문제인지 OneDrive 문제인지 구분한다.

사용:
    python probe_paths.py
    python probe_paths.py --src "C:\\Users\\ADMINI~1\\AppData\\Local\\Temp\\bidar_index_build"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROBE_SRC = (
    "import json,sys\n"
    "import chromadb\n"
    "out={}\n"
    "try:\n"
    "    c=chromadb.PersistentClient(path=sys.argv[1])\n"
    "    col=c.get_collection(sys.argv[2])\n"
    "    out['get_collection']='OK'\n"
    "    out['count']=col.count()\n"
    "    out['ok']=True\n"
    "except Exception as e:\n"
    "    out['ok']=False\n"
    "    out['error']=type(e).__name__+': '+str(e)\n"
    "print('__PROBE__'+json.dumps(out,ensure_ascii=False))\n"
)


def probe(path: Path, coll: str) -> dict:
    r = subprocess.run([sys.executable, "-c", PROBE_SRC, str(path), coll],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in (r.stdout or "").splitlines():
        if line.startswith("__PROBE__"):
            return json.loads(line[len("__PROBE__"):])
    return {"ok": False, "error": "(출력 없음) " + (r.stderr or "")[-200:]}


def files_of(p: Path):
    if not p.exists():
        return []
    return sorted((str(f.relative_to(p)), f.stat().st_size) for f in p.rglob("*") if f.is_file())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(Path(tempfile.gettempdir()) / "bidar_index_build"),
                    help="열리는 것이 확인된 원본 색인 폴더")
    ap.add_argument("--collection", default="rfp_chunks")
    ap.add_argument("--keep", action="store_true", help="테스트 사본을 지우지 않는다")
    a = ap.parse_args()

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass

    src = Path(a.src)
    print("=" * 78)
    print("probe_paths.py - 색인이 열리는 경로 조건 판별")
    print("=" * 78)
    print(f"\n원본 : {src}")
    if not src.exists():
        print("  !! 원본 폴더가 없다. build_index_ours.py 를 먼저 돌리고 --src 로 경로를 넘겨라.")
        sys.exit(1)
    fs = files_of(src)
    for n, s in fs:
        print(f"  {s:>14,}  {n}")
    total = sum(s for _, s in fs)
    print(f"  합계 {total:,} byte")

    r0 = probe(src, a.collection)
    print(f"\n원본 열기 : {'PASS  count()=' + str(r0.get('count')) if r0.get('ok') else 'FAIL  ' + str(r0.get('error'))[:160]}")
    if not r0.get("ok"):
        print("  원본부터 안 열린다. 여기서 멈춘다.")
        sys.exit(1)

    home = Path.home()
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or ""
    cases = [
        ("1. ASCII + OneDrive 밖",        Path("C:/bidar_probe/ascii_plain")),
        ("2. 한글 + OneDrive 밖",         Path("C:/bidar_probe/한글경로_테스트")),
        ("3. 공백 + OneDrive 밖",         Path("C:/bidar_probe/space dir/vs")),
        ("4. ASCII + OneDrive 안",        (Path(onedrive) / "bidar_probe_ascii") if onedrive else None),
        ("5. 한글 + OneDrive 안 (현재 상태)", (Path(onedrive) / "바탕 화면" / "중급 프로젝트" / "vector_store_ours") if onedrive else None),
    ]

    print(f"\nOneDrive 환경변수 : {onedrive or '(없음)'}")
    results = []
    made = []
    for label, dst in cases:
        print(f"\n[{label}]")
        if dst is None:
            print("  건너뜀 (OneDrive 경로를 못 찾음)")
            results.append((label, None, "건너뜀"))
            continue
        print(f"  경로 {dst}")
        try:
            if dst.exists():
                # 5번(현재 상태)은 이미 있는 걸 그대로 본다
                if label.startswith("5."):
                    pass
                else:
                    shutil.rmtree(dst, ignore_errors=True)
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dst)
                made.append(dst)
                time.sleep(1.0)
        except Exception as e:
            print(f"  복사 실패 : {type(e).__name__}: {e}")
            results.append((label, False, f"복사 실패: {e}"))
            continue

        got = files_of(dst)
        nbin = sum(1 for n, _ in got if n.endswith(".bin"))
        print(f"  파일 {len(got)}개 / .bin {nbin}개 / 합계 {sum(s for _, s in got):,} byte")
        r = probe(dst, a.collection)
        if r.get("ok"):
            print(f"  결과 : PASS  count()={r.get('count')}")
            results.append((label, True, f"count()={r.get('count')}"))
        else:
            print(f"  결과 : FAIL  {str(r.get('error'))[:180]}")
            results.append((label, False, str(r.get("error"))[:180]))

    print("\n" + "=" * 78)
    print("판정표")
    print("=" * 78)
    for label, ok, note in results:
        mark = "PASS" if ok else ("----" if ok is None else "FAIL")
        print(f"  [{mark}] {label}")
        print(f"         {note}")

    ok_map = {l: o for l, o, _ in results}
    print()
    a1 = ok_map.get("1. ASCII + OneDrive 밖")
    a2 = ok_map.get("2. 한글 + OneDrive 밖")
    a4 = ok_map.get("4. ASCII + OneDrive 안")
    if a1 and a2 is False:
        print("  -> 경로의 한글이 원인이다. 색인은 ASCII 경로에 두어야 한다.")
    elif a1 and a2 and a4 is False:
        print("  -> OneDrive 동기화 폴더가 원인이다. 색인은 OneDrive 밖에 두어야 한다.")
    elif a1 and a2 and a4:
        print("  -> 둘 다 아니다. 5번(현재 경로)만 실패했다면 그 폴더 상태를 봐야 한다.")
    elif a1 is False:
        print("  -> ASCII + OneDrive 밖에서도 실패했다. 복사 자체가 색인을 깨뜨린다는 뜻이다.")
    else:
        print("  -> 조합이 애매하다. 위 판정표를 그대로 공유해라.")

    if not a.keep:
        for d in made:
            shutil.rmtree(d, ignore_errors=True)
        root = Path("C:/bidar_probe")
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        print("\n테스트 사본 정리 완료 (--keep 을 주면 남긴다)")


if __name__ == "__main__":
    main()

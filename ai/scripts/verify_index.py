"""ai/scripts/verify_index.py - 이미 만들어진 Chroma 색인이 실제로 열리는지 확인한다.

    python ai/scripts/verify_index.py --persist-dir C:/bidar/vector_store

서버 기동 전, 색인을 옮긴 뒤, 남에게서 색인을 받았을 때 쓴다.

같은 프로세스 안에서 열어보는 것으로는 판정할 수 없다. Chroma 는 프로세스 안에
인덱스를 들고 있어서, 방금 만든 색인은 디스크에 아무것도 안 써져 있어도 열린다.
그래서 여기서는 항상 별도 프로세스를 띄운다.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

_PROBE = (
    "import json,sys\n"
    "import chromadb\n"
    "out={}\n"
    "try:\n"
    "    c=chromadb.PersistentClient(path=sys.argv[1])\n"
    "    col=c.get_collection(sys.argv[2])\n"
    "    out['get_collection']='OK'\n"
    "    out['count']=col.count()\n"
    "    d=col.get(limit=1,include=['embeddings'])\n"
    "    e=d.get('embeddings')\n"
    "    out['dim']=len(e[0]) if e is not None and len(e)>0 else None\n"
    "    out['ok']=True\n"
    "except Exception as ex:\n"
    "    out['ok']=False\n"
    "    out['error']=type(ex).__name__+': '+str(ex)\n"
    "print('__PROBE__'+json.dumps(out,ensure_ascii=False))\n"
)


def probe(path: str, collection: str) -> dict:
    r = subprocess.run(
        [sys.executable, "-c", _PROBE, str(path), collection],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in (r.stdout or "").splitlines():
        if line.startswith("__PROBE__"):
            return json.loads(line[len("__PROBE__"):])
    return {"ok": False, "error": "(하위 프로세스 출력 없음) " + (r.stderr or "")[-300:]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist-dir", required=True)
    ap.add_argument("--collection", default="rfp_chunks")
    args = ap.parse_args()

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass

    p = Path(args.persist_dir)
    print(f"경로 : {p}")
    bad = sorted({ch for ch in str(p) if ord(ch) > 127})
    if bad:
        print(f"  !! 경로에 ASCII 밖 문자가 있다: {''.join(bad)!r}"
              f"  -> chromadb 가 HNSW 색인을 못 연다")
    if not p.exists():
        print("  폴더가 없다")
        sys.exit(2)

    files = sorted((str(f.relative_to(p)), f.stat().st_size) for f in p.rglob("*") if f.is_file())
    print(f"\n[파일] {len(files)}개")
    for name, size in files:
        print(f"  {size:>14,}  {name}")
    need = ("data_level0.bin", "header.bin", "length.bin", "link_lists.bin")
    have = {Path(n).name for n, _ in files if n.endswith(".bin")}
    missing = [x for x in need if x not in have]
    print(f"  .bin {len(have)}/4" + (f"  누락 {missing}" if missing else ""))

    db = p / "chroma.sqlite3"
    if db.exists():
        con = sqlite3.connect(str(db))
        cur = con.cursor()
        print("\n[sqlite]")
        print(f"  integrity_check   {cur.execute('PRAGMA integrity_check;').fetchone()[0]}")
        for t in ("embeddings", "embedding_metadata", "embeddings_queue", "segments"):
            try:
                print(f"  {t:<20}{cur.execute(f'select count(*) from {t};').fetchone()[0]}")
            except Exception as e:
                print(f"  {t:<20}(조회 실패: {e})")
        try:
            for row in cur.execute("select id, scope from segments;"):
                print(f"    {row}")
        except Exception:
            pass
        con.close()
    else:
        print("\n[sqlite] chroma.sqlite3 가 없다")

    print("\n[검증] 새 프로세스에서 열기")
    r = probe(str(p), args.collection)
    if r.get("ok"):
        print(f"  PASS  count()={r.get('count')}  dim={r.get('dim')}")
        sys.exit(0)
    print(f"  FAIL  {r.get('error')}")
    sys.exit(1)


if __name__ == "__main__":
    main()

"""ai/scripts/build_index.py - ingestion 파이프라인 실행 (색인 재구축).

    python ai/scripts/build_index.py \
        --chunks ai/data/processed/RFP100_chunks_C0_DEV_v0.1.jsonl \
        --documents ai/data/processed/RFP100_documents_DEV_v0.1.jsonl \
        --persist-dir C:/bidar/vector_store

C0 Chunk를 KURE-v1으로 임베딩해 Chroma에 색인한다. C0는 재청킹하지 않는다.

완료 판정은 collection.count() 로 하지 않는다. count() 는 sqlite 를 읽으므로
HNSW 색인(.bin)이 하나도 안 써져 있어도 전체 건수를 돌려준다. 이 스크립트는
색인을 만든 뒤 **별도 프로세스**를 띄워 다시 열어보고, 거기서 성공해야 PASS 로 본다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ai.embeddings.embedder import KureEmbedder
from ai.ingestion.indexer import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_COLLECTION,
    DEFAULT_SYNC_THRESHOLD,
    build_index,
    non_ascii_part,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ai/
DATA_DIR = PROJECT_ROOT / "data"

_PROBE = (
    "import json,sys\n"
    "import chromadb\n"
    "out={}\n"
    "try:\n"
    "    c=chromadb.PersistentClient(path=sys.argv[1])\n"
    "    col=c.get_collection(sys.argv[2])\n"
    "    out['count']=col.count()\n"
    "    out['peek']=col.peek(1)['ids']\n"
    "    out['ok']=True\n"
    "except Exception as e:\n"
    "    out['ok']=False\n"
    "    out['error']=type(e).__name__+': '+str(e)\n"
    "print('__PROBE__'+json.dumps(out,ensure_ascii=False))\n"
)


def verify_fresh_process(persist_dir: str, collection: str) -> dict:
    """색인을 새 프로세스에서 열어본다. 이 스크립트의 유일한 성공 판정 기준."""
    r = subprocess.run(
        [sys.executable, "-c", _PROBE, str(persist_dir), collection],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in (r.stdout or "").splitlines():
        if line.startswith("__PROBE__"):
            return json.loads(line[len("__PROBE__"):])
    return {"ok": False, "error": "(하위 프로세스 출력 없음) " + (r.stderr or "")[-300:]}


def bin_files(persist_dir: str) -> list[tuple[str, int]]:
    p = Path(persist_dir)
    if not p.exists():
        return []
    return sorted((str(f.relative_to(p)), f.stat().st_size) for f in p.rglob("*.bin"))


def main() -> None:
    parser = argparse.ArgumentParser(description="RFP C0 청크를 임베딩해 Chroma에 색인한다.")
    parser.add_argument(
        "--chunks", default=str(DATA_DIR / "processed" / "RFP100_chunks_C0_DEV_v0.1.jsonl")
    )
    parser.add_argument(
        "--documents", default=str(DATA_DIR / "processed" / "RFP100_documents_DEV_v0.1.jsonl")
    )
    parser.add_argument("--persist-dir", default=str(DATA_DIR / "vector_store"))
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sync-threshold", type=int, default=DEFAULT_SYNC_THRESHOLD)
    parser.add_argument("--keep-existing", action="store_true",
                        help="persist-dir 를 비우지 않는다 (기본은 비우고 시작)")
    args = parser.parse_args()

    bad = non_ascii_part(args.persist_dir)
    if bad:
        print(f"색인 경로에 ASCII 밖 문자가 있다: {bad!r}", file=sys.stderr)
        print(f"  경로: {args.persist_dir}", file=sys.stderr)
        print("  chromadb 는 이런 경로의 HNSW 색인을 열지 못한다."
              " ASCII 경로를 --persist-dir 로 지정해라.", file=sys.stderr)
        sys.exit(2)

    embedder = KureEmbedder(device=args.device)
    collection = build_index(
        args.chunks,
        embedder,
        documents_path=args.documents,
        collection_name=args.collection,
        persist_dir=args.persist_dir,
        batch_size=args.batch_size,
        sync_threshold=args.sync_threshold,
        fresh=not args.keep_existing,
    )
    n_inproc = collection.count()
    del collection

    print(f"\n색인 추가 완료 (같은 프로세스 count()={n_inproc}) - 아직 완료 판정이 아니다")

    bins = bin_files(args.persist_dir)
    print(f"\n[디스크] .bin {len(bins)}개")
    for name, size in bins:
        print(f"  {size:>14,}  {name}")

    print("\n[검증] 새 프로세스에서 다시 열기")
    res = verify_fresh_process(args.persist_dir, args.collection)
    if res.get("ok"):
        print(f"  PASS  count()={res.get('count')}  peek={res.get('peek')}")
        print(f"\n색인 완료: {res.get('count')}개 청크")
        print(f"  경로 : {args.persist_dir}")
        print(f"  backend 환경변수 : AI_RETRIEVER_PERSIST_DIR={args.persist_dir}")
    else:
        print(f"  FAIL  {res.get('error')}")
        print("\n색인이 디스크에 온전히 남지 않았다. 위 [디스크] 목록과 이 에러를 함께 확인해라.")
        sys.exit(1)


if __name__ == "__main__":
    main()

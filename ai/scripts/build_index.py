"""ai/scripts/build_index.py — ingestion 파이프라인 실행 (색인 재구축).

    python ai/scripts/build_index.py \\
        --chunks ai/data/processed/RFP100_chunks_C0_DEV_v0.1.jsonl \\
        --documents ai/data/processed/RFP100_documents_DEV_v0.1.jsonl

C0 Chunk를 KURE-v1으로 임베딩해 Chroma에 색인한다. C0는 재청킹하지 않는다
(docs/RETRIEVAL_HANDOFF_v0.1.md 3.1 — 최초 Baseline은 C0를 그대로 사용).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ai.embeddings.embedder import KureEmbedder
from ai.ingestion.indexer import build_index

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ai/
DATA_DIR = PROJECT_ROOT / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="RFP C0 청크를 임베딩해 Chroma에 색인한다.")
    parser.add_argument(
        "--chunks", default=str(DATA_DIR / "processed" / "RFP100_chunks_C0_DEV_v0.1.jsonl")
    )
    parser.add_argument(
        "--documents", default=str(DATA_DIR / "processed" / "RFP100_documents_DEV_v0.1.jsonl")
    )
    parser.add_argument("--persist-dir", default=str(DATA_DIR / "vector_store"))
    parser.add_argument("--collection", default="rfp_chunks")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    embedder = KureEmbedder(device=args.device)
    collection = build_index(
        args.chunks,
        embedder,
        documents_path=args.documents,
        collection_name=args.collection,
        persist_dir=args.persist_dir,
    )
    print(f"인덱싱 완료: {collection.count()}개 청크")


if __name__ == "__main__":
    main()

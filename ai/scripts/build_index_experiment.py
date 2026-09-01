# -*- coding: utf-8 -*-
"""build_index_ours.py - C0 청크를 Chroma 에 색인하고, 새 프로세스에서 열릴 때까지 스스로 재시도한다.

리트리버 원본(`ai/scripts/build_index.py` + `ai/src/ai/ingestion/indexer.py`) 대비 고친 것:

  F1  빌드 후 flush 검증        원본은 add() 끝나고 바로 return. .bin 이 안 써져도 모른다.
  F2  성공 판정 기준            원본은 count() 로 판정. count() 는 sqlite 를 읽어서
                               .bin 이 없어도 4931 이 나온다. 여기서는 "새 프로세스에서
                               열리는가" 로만 판정한다. 같은 프로세스 재오픈은 증거가 아니다
                               (Chroma 의 Rust 백엔드가 프로세스 안에 인덱스를 들고 있다).
  F3  세그먼트 폴더 정리        원본은 delete_collection -> create_collection 이라
                               옛 UUID 폴더가 남는다. 매번 폴더를 비우고 시작한다.
  F4  budget_amount 0 보존      원본 `doc.get("budget_amount") or -1` 은 0 을 -1 로 바꾼다.
  F5  batch_size CLI 노출       원본은 64 하드코딩.
  F6  sync_threshold 지정       HNSW 를 디스크에 내리는 임계치를 명시한다.
  F7  자동 재시도               한 번 실패하면 조합을 바꿔가며 스스로 다시 시도한다.
                               임베딩은 한 번만 하고 색인 단계만 반복한다.
                               동기화 폴더(OneDrive 등)를 피해 로컬 임시폴더에서 만든 뒤
                               최종 경로로 복사하고, 그 자리에서 다시 검증한다.

사용:
    pip install "chromadb==1.5.9"
    python build_index_ours.py                      # C0 전체 4931건
    python build_index_ours.py --scope gold         # 850건 빠른 확인

산출:
    <중급 프로젝트>/vector_store_ours/            Chroma 색인 (검증 통과한 것)
    <중급 프로젝트>/retrieval_hits_chroma.jsonl   노트북 셀 10-B 입력
    보고용/index_report.md
    보고용/fig_index.png
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent           # 보고용/
ROOT = HERE.parent                               # 중급 프로젝트/
DATA = ROOT / "코드잇 AI 12기 중급 프로젝트"

DEF_CHUNKS = DATA / "DataToRetrieval" / "RFP100 dataset v0.1 for Retrieval" / "RFP100_chunks_C0_DEV_v0.1.jsonl"
DEF_DOCS = DATA / "DataToRetrieval" / "RFP100 dataset v0.1 for Retrieval" / "RFP100_documents_DEV_v0.1.jsonl"
DEF_GOLD = DATA / "DataToGeneration" / "RFP100 dataset v0.1 for Generation" / "RFP100_Gold_Questions_v0.2_Canonical.jsonl"
DEF_PERSIST = ROOT / "vector_store_ours"
DEF_HITS = ROOT / "retrieval_hits_chroma.jsonl"

MODEL_ID = "nlpai-lab/KURE-v1"
EXPECT_CHROMA = "1.5.9"
SYNC_KEYWORDS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "box sync")

LIST_FIELDS = ("section_path", "block_ids", "requirement_ids")
METADATA_FIELDS = (
    "document_id", "split", "chunk_index", "section_path", "block_ids",
    "requirement_ids", "char_start", "char_end", "page_start", "page_end",
    "chunking_version", "source_text_version",
)

# 새 프로세스에서 색인을 열어보는 검사기. 이 스크립트의 유일한 성공 판정 기준이다.
PROBE_SRC = (
    "import json,sys\n"
    "import chromadb\n"
    "out={}\n"
    "try:\n"
    "    c=chromadb.PersistentClient(path=sys.argv[1])\n"
    "    col=c.get_collection(sys.argv[2])\n"
    "    out['count']=col.count()\n"
    "    out['peek']=col.peek(1)['ids']\n"
    "    d=col.get(limit=1,include=['embeddings'])\n"
    "    out['dim']=len(d['embeddings'][0]) if d.get('embeddings') is not None and len(d['embeddings'])>0 else None\n"
    "    out['ok']=True\n"
    "except Exception as e:\n"
    "    out['ok']=False\n"
    "    out['error']=type(e).__name__+': '+str(e)\n"
    "print('__PROBE__'+json.dumps(out,ensure_ascii=False))\n"
)


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def gold_chunk_ids(q):
    out = []
    for ev in q.get("gold_evidence") or []:
        for c in ev.get("c0_chunk_ids") or []:
            if c not in out:
                out.append(c)
    return out


def chunk_to_metadata(chunk: dict, document_lookup: dict) -> dict:
    """리트리버 indexer.py 34~49줄과 동일. budget_amount 만 F4 로 고쳤다."""
    metadata = {}
    for field in METADATA_FIELDS:
        value = chunk.get(field)
        if field in LIST_FIELDS:
            value = json.dumps(value or [], ensure_ascii=False)
        elif value is None:
            value = ""
        metadata[field] = value

    doc = document_lookup.get(chunk["document_id"], {})
    metadata["title"] = doc.get("title", "")
    metadata["agency"] = doc.get("agency", "")
    b = doc.get("budget_amount")
    metadata["budget_amount"] = -1 if b is None else b      # F4
    metadata["budget_status"] = doc.get("budget_status", "")
    return metadata


def dir_report(path: Path):
    out = []
    if not path.exists():
        return out
    for p in sorted(path.rglob("*")):
        if p.is_file():
            out.append((str(p.relative_to(path)), p.stat().st_size))
    return out


def bin_state(path: Path):
    need = ("data_level0.bin", "header.bin", "length.bin", "link_lists.bin")
    have = {Path(n).name for n, _ in dir_report(path) if n.endswith(".bin")}
    d0 = next((s for n, s in dir_report(path) if Path(n).name == "data_level0.bin"), 0)
    return need, have, [x for x in need if x not in have], d0


def sqlite_facts(db: Path):
    f = {}
    if not db.exists():
        return {"error": "chroma.sqlite3 없음"}
    con = sqlite3.connect(str(db))
    try:
        cur = con.cursor()
        f["integrity_check"] = cur.execute("PRAGMA integrity_check;").fetchone()[0]
        for t in ("embeddings", "embedding_metadata", "embeddings_queue", "collections", "segments"):
            try:
                f[t] = cur.execute(f"select count(*) from {t};").fetchone()[0]
            except Exception as e:
                f[t] = f"(조회 실패: {e})"
        try:
            f["segment_rows"] = cur.execute("select id, scope, type from segments;").fetchall()
        except Exception as e:
            f["segment_rows"] = f"(조회 실패: {e})"
    finally:
        con.close()
    return f


def probe_fresh(path: Path, collection: str) -> dict:
    """완전히 새 프로세스에서 색인을 열어본다. 성공 판정은 오직 이것으로 한다."""
    r = subprocess.run([sys.executable, "-c", PROBE_SRC, str(path), collection],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in (r.stdout or "").splitlines():
        if line.startswith("__PROBE__"):
            return json.loads(line[len("__PROBE__"):])
    return {"ok": False, "error": "(하위 프로세스 출력 없음) " + (r.stderr or "")[-300:]}


def non_ascii_part(p: Path) -> str | None:
    """경로에 ASCII 밖 문자가 있으면 그 문자들을 돌려준다.

    chromadb 1.5.9 Windows 빌드는 non-ASCII 경로의 HNSW 색인(.bin)을 못 연다.
    sqlite 는 열리므로 get_collection 은 성공하고 count()/query() 에서 죽는다.
    2026-09-01 실측: ASCII 경로 PASS / 한글 경로 FAIL / 공백은 무관 / OneDrive 는 무관.
    """
    bad = sorted({ch for ch in str(p) if ord(ch) > 127})
    return "".join(bad) if bad else None


def ascii_fallback_dir() -> Path:
    """한글이 안 섞인 안전한 색인 위치."""
    if os.name == "nt":
        drive = os.environ.get("SystemDrive", "C:")
        return Path(f"{drive}/bidar/vector_store")
    return Path.home() / "bidar" / "vector_store"


def is_synced_dir(p: Path) -> str | None:
    s = str(p).lower()
    for kw in SYNC_KEYWORDS:
        if kw in s:
            return kw
    return None


def build_once(persist: Path, collection_name: str, chunks, vecs, doc_lookup,
               batch_size: int, sync_threshold: int | None):
    """persist 를 비우고 색인을 새로 만든다. (elapsed, count_inproc, coll_meta) 를 돌려준다."""
    import chromadb
    if persist.exists():
        shutil.rmtree(persist, ignore_errors=True)
    persist.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist))
    meta = {"hnsw:space": "cosine"}
    if sync_threshold:
        meta["hnsw:sync_threshold"] = sync_threshold
    try:
        col = client.create_collection(collection_name, metadata=meta)
    except Exception as e:
        print(f"      metadata {meta} 거부됨({type(e).__name__}) -> hnsw:space 만으로 재시도")
        meta = {"hnsw:space": "cosine"}
        col = client.create_collection(collection_name, metadata=meta)

    t0 = time.time()
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        col.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=[v.tolist() for v in vecs[i:i + batch_size]],
            documents=[c["text"] for c in batch],
            metadatas=[chunk_to_metadata(c, doc_lookup) for c in batch],
        )
    n = col.count()
    elapsed = time.time() - t0

    del col
    del client
    gc.collect()
    time.sleep(1.0)
    return elapsed, n, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default=str(DEF_CHUNKS))
    ap.add_argument("--documents", default=str(DEF_DOCS))
    ap.add_argument("--gold", default=str(DEF_GOLD))
    ap.add_argument("--persist-dir", default=str(DEF_PERSIST), help="최종 색인 위치")
    ap.add_argument("--work-dir", default=None,
                    help="색인을 실제로 만드는 위치. 비우면 로컬 임시폴더(동기화 폴더 밖)")
    ap.add_argument("--out", default=str(DEF_HITS))
    ap.add_argument("--report-dir", default=str(HERE))
    ap.add_argument("--collection", default="rfp_chunks")
    ap.add_argument("--device", default=None, help="cuda / cpu. 비우면 자동")
    ap.add_argument("--batch-size", type=int, default=256, help="F5. 리트리버 원본은 64 고정")
    ap.add_argument("--embed-batch", type=int, default=32)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--scope", choices=["all", "gold"], default="all")
    ap.add_argument("--sync-threshold", type=int, default=100, help="F6")
    ap.add_argument("--keep-work", action="store_true", help="작업 폴더를 지우지 않는다")
    a = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    print("=" * 78)
    print("build_index_ours.py - C0 -> Chroma 색인 + 새 프로세스 검증 + 자동 재시도")
    print("=" * 78)

    import chromadb
    ver = getattr(chromadb, "__version__", "(불명)")
    print(f"\n[환경]")
    print(f"  python       {sys.version.split()[0]}")
    print(f"  chromadb     {ver}   (리트리버가 쓴 버전 {EXPECT_CHROMA})")
    if ver != EXPECT_CHROMA:
        print(f"  !! 버전이 다르다. 같은 조건으로 보려면: pip install \"chromadb=={EXPECT_CHROMA}\"")

    final = Path(a.persist_dir)
    if a.work_dir:
        work = Path(a.work_dir)
    else:
        work = Path(tempfile.gettempdir()) / "bidar_index_build"
    kw = is_synced_dir(final)
    na_final = non_ascii_part(final)
    na_work = non_ascii_part(work)
    print(f"  최종 경로    {final}" + (f"   (!! '{kw}' 동기화 폴더 안)" if kw else ""))
    if na_final:
        print(f"     !! 이 경로에 ASCII 밖 문자가 있다: {na_final}")
        print(f"        chromadb {ver} 는 non-ASCII 경로의 .bin 을 못 읽는다(2026-09-01 실측).")
        print(f"        여기서 실패하면 자동으로 {ascii_fallback_dir()} 로 옮겨 다시 확인한다.")
    print(f"  작업 경로    {work}" + ("   (!! 여기도 동기화 폴더 안)" if is_synced_dir(work) else "   (동기화 폴더 밖)"))
    if na_work:
        print(f"     !! 작업 경로에도 ASCII 밖 문자가 있다: {na_work}  --work-dir 로 ASCII 경로를 지정해라.")

    # ---------------------------------------------------------------- 입력
    chunks_all = read_jsonl(a.chunks)
    docs = read_jsonl(a.documents)
    gold = read_jsonl(a.gold)
    doc_lookup = {d["document_id"]: d for d in docs}
    print(f"\n[입력]")
    print(f"  C0 청크      {len(chunks_all)}건")
    print(f"  문서 메타    {len(docs)}건")
    print(f"  Gold 질문    {len(gold)}건")

    target_docs = sorted({q["document_id"] for q in gold if q.get("document_id")})
    if a.scope == "gold":
        use = [c for c in chunks_all if c["document_id"] in target_docs]
        print(f"  scope=gold   대상 문서 {len(target_docs)}개 -> 청크 {len(use)}건")
    else:
        use = chunks_all
        print(f"  scope=all    청크 {len(use)}건 (전체)")

    # ---------------------------------------------------------------- 임베딩 (한 번만)
    import torch
    from sentence_transformers import SentenceTransformer
    dev = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n[임베딩] {MODEL_ID}  device={dev}   (재시도해도 이 단계는 다시 안 한다)")
    t0 = time.time()
    model = SentenceTransformer(MODEL_ID, device=dev)
    print(f"  모델 로드 {time.time() - t0:.1f}초")

    t0 = time.time()
    vecs = model.encode([c["text"] for c in use], batch_size=a.embed_batch,
                        normalize_embeddings=True, show_progress_bar=True)
    vecs = np.asarray(vecs, dtype=np.float32)
    t_embed = time.time() - t0
    dim = int(vecs.shape[1])
    print(f"  청크 {len(use)}건  {t_embed:.1f}초  ({t_embed / len(use) * 1000:.1f} ms/건)  dim={dim}")

    qvecs = np.asarray(model.encode([q["question"] for q in gold], batch_size=a.embed_batch,
                                    normalize_embeddings=True), dtype=np.float32)
    n_c = np.linalg.norm(vecs, axis=1)
    n_q = np.linalg.norm(qvecs, axis=1)
    print(f"  L2 norm  청크 {n_c.min():.4f}~{n_c.max():.4f}   질문 {n_q.min():.4f}~{n_q.max():.4f}"
          f"   (1.0 이어야 정규화 정상)")

    # ---------------------------------------------------------------- 색인 + 자동 재시도
    # (설명, 만들 위치, sync_threshold, batch_size)
    plans = [
        ("A. 로컬 작업폴더 + sync_threshold 지정", work, a.sync_threshold, a.batch_size),
        ("B. 로컬 작업폴더 + Chroma 기본 임계치", work, None, a.batch_size),
        ("C. 로컬 작업폴더 + 임계치 지정 + batch 64(원본과 동일)", work, a.sync_threshold, 64),
        ("D. 최종 경로에 직접 + sync_threshold 지정", final, a.sync_threshold, a.batch_size),
    ]

    attempts = []
    winner = None
    for label, where, sth, bs in plans:
        print(f"\n[시도] {label}")
        print(f"       위치 {where}")
        el, n_inproc, meta = build_once(where, a.collection, use, vecs, doc_lookup, bs, sth)
        need, have, missing, d0 = bin_state(where)
        facts = sqlite_facts(where / "chroma.sqlite3")
        pr = probe_fresh(where, a.collection)
        print(f"       add {el:.1f}초, 같은 프로세스 count()={n_inproc}")
        print(f"       .bin {len(have)}/4" + (f"  누락 {missing}" if missing else "")
              + f"   data_level0={d0:,} byte")
        print(f"       sqlite embeddings={facts.get('embeddings')} "
              f"queue={facts.get('embeddings_queue')} integrity={facts.get('integrity_check')}")
        if pr.get("ok"):
            print(f"       새 프로세스 열기 : PASS  count()={pr.get('count')} dim={pr.get('dim')}")
        else:
            print(f"       새 프로세스 열기 : FAIL  {str(pr.get('error'))[:200]}")
        attempts.append({"label": label, "where": str(where), "sync_threshold": sth,
                         "batch_size": bs, "add_sec": round(el, 1), "count_inproc": n_inproc,
                         "bin_have": len(have), "bin_missing": missing, "data_level0": d0,
                         "sqlite": {k: v for k, v in facts.items() if k != "segment_rows"},
                         "fresh_ok": bool(pr.get("ok")), "fresh": pr})
        if pr.get("ok"):
            winner = attempts[-1]
            break

    if winner is None:
        print("\n" + "=" * 78)
        print("전부 실패했다. 아래 [시도] 출력을 그대로 공유하면 원인 지점이 잡힌다.")
        print("=" * 78)
        for at in attempts:
            print(f"  {at['label']}: .bin {at['bin_have']}/4, "
                  f"새 프로세스 {str(at['fresh'].get('error'))[:120]}")
        sys.exit(1)

    print(f"\n[성공] {winner['label']}")

    # ---- 작업폴더에서 만들었으면 최종 경로로 복사하고 그 자리에서 다시 검증 ----
    src = Path(winner["where"])
    used = src
    copy_note = "작업폴더에서 바로 사용"
    if src != final:
        print(f"\n[복사] {src} -> {final}")
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, final)
        pr2 = probe_fresh(final, a.collection)
        if pr2.get("ok"):
            print(f"       최종 경로 새 프로세스 열기 : PASS  count()={pr2.get('count')}")
            used = final
            copy_note = "작업폴더에서 만들어 최종 경로로 복사, 그 자리에서 재검증 통과"
        else:
            print(f"       최종 경로 새 프로세스 열기 : FAIL  {str(pr2.get('error'))[:200]}")
            if na_final:
                print(f"       원인: 최종 경로의 ASCII 밖 문자 {na_final}")
            # ---- ASCII 대체 경로로 자동 이전 ----
            alt = ascii_fallback_dir()
            print(f"\n[대체 경로] {alt} 로 옮겨서 다시 확인한다")
            try:
                if alt.exists():
                    shutil.rmtree(alt, ignore_errors=True)
                alt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, alt)
                time.sleep(1.0)
                pr3 = probe_fresh(alt, a.collection)
            except Exception as e:
                pr3 = {"ok": False, "error": f"복사 실패 {type(e).__name__}: {e}"}
            if pr3.get("ok"):
                print(f"       새 프로세스 열기 : PASS  count()={pr3.get('count')}")
                shutil.rmtree(final, ignore_errors=True)
                used = alt
                copy_note = (f"최종 경로 `{final}` 는 경로에 ASCII 밖 문자({na_final})가 있어 "
                             f"chromadb 가 색인을 열지 못한다. `{alt}` 로 옮겨 사용한다")
            else:
                print(f"       새 프로세스 열기 : FAIL  {str(pr3.get('error'))[:200]}")
                print(f"       !! 대체 경로도 실패. 작업폴더 사본을 그대로 쓴다.")
                used = src
                copy_note = (f"최종 경로와 대체 경로 모두에서 열리지 않아 작업폴더 사본을 사용. "
                             f"이 경로는 임시폴더이므로 재부팅 시 사라질 수 있다")

    need, have, missing, d0 = bin_state(used)
    facts = sqlite_facts(used / "chroma.sqlite3")
    files_used = dir_report(used)

    print(f"\n[확정 색인] {used}")
    for name, size in files_used:
        print(f"  {size:>14,}  {name}")
    print(f"  .bin {len(have)}/4" + (f"  누락 {missing}" if missing else ""))
    print(f"  sqlite embeddings={facts.get('embeddings')} "
          f"queue={facts.get('embeddings_queue')} integrity={facts.get('integrity_check')}")
    if isinstance(facts.get("segment_rows"), list):
        for row in facts["segment_rows"]:
            print(f"    {row}")

    # ---------------------------------------------------------------- 검색
    print(f"\n[검색] Gold {len(gold)}문항 (top_k={a.top_k}, document_id 하드필터)")
    client = chromadb.PersistentClient(path=str(used))
    col = client.get_collection(a.collection)

    by_doc = {}
    for i, c in enumerate(use):
        by_doc.setdefault(c["document_id"], []).append(i)

    rows, detail = [], []
    t0 = time.time()
    for qi, q in enumerate(gold):
        qid, doc = q["question_id"], q.get("document_id")
        g = gold_chunk_ids(q)

        chroma_hits = []
        try:
            r = col.query(query_embeddings=[qvecs[qi].tolist()],
                          n_results=a.top_k, where={"document_id": doc})
            for rank, cid in enumerate(r["ids"][0]):
                chroma_hits.append({
                    "rank": rank + 1,
                    "chunk_id": cid,
                    "document_id": r["metadatas"][0][rank]["document_id"],
                    "score": round(1.0 - float(r["distances"][0][rank]), 6),
                    "text": r["documents"][0][rank],
                })
        except Exception as e:
            print(f"  {qid} query 실패: {type(e).__name__}: {e}")

        idxs = by_doc.get(doc, [])
        np_hits = []
        if idxs:
            sims = vecs[idxs] @ qvecs[qi]
            for rank, j in enumerate(np.argsort(-sims)[:a.top_k]):
                np_hits.append({"rank": rank + 1,
                                "chunk_id": use[idxs[j]]["chunk_id"],
                                "score": round(float(sims[j]), 6)})

        c_ids = [h["chunk_id"] for h in chroma_hits]
        n_ids = [h["chunk_id"] for h in np_hits]
        rows.append({"question_id": qid, "hits": chroma_hits})
        detail.append({
            "question_id": qid, "document_id": doc,
            "question_type": q.get("question_type"),
            "n_candidates": len(idxs), "gold": g,
            "chroma_ids": c_ids, "numpy_ids": n_ids,
            "chroma_rank": next((i + 1 for i, x in enumerate(c_ids) if x in g), None),
            "numpy_rank": next((i + 1 for i, x in enumerate(n_ids) if x in g), None),
            "chroma_top1": chroma_hits[0]["score"] if chroma_hits else None,
            "numpy_top1": np_hits[0]["score"] if np_hits else None,
            "same_order": c_ids == n_ids,
        })
    t_search = time.time() - t0
    print(f"  {len(gold)}문항 {t_search:.2f}초  ({t_search / max(len(gold), 1) * 1000:.0f} ms/문항)")

    scored = [d for d in detail if d["gold"]]
    def recall(key, k):
        return sum(1 for d in scored if d[key] and d[key] <= k) / len(scored)

    print(f"\n  Recall (gold_evidence 있는 {len(scored)}문항)")
    print(f"    {'k':<4}{'chroma':>12}{'numpy 대조군':>16}")
    for k in (1, 3, 5):
        print(f"    {k:<4}{recall('chroma_rank', k) * 100:>11.1f}%{recall('numpy_rank', k) * 100:>15.1f}%")

    n_same = sum(1 for d in detail if d["same_order"])
    dscore = [abs(d["chroma_top1"] - d["numpy_top1"])
              for d in detail if d["chroma_top1"] is not None and d["numpy_top1"] is not None]
    print(f"\n  두 방식 top-{a.top_k} 순서 일치 : {n_same}/{len(detail)}")
    if dscore:
        print(f"  top1 score 최대 차이       : {max(dscore):.6f}  (0 에 가까워야 정상)")

    del col, client
    gc.collect()

    # ---------------------------------------------------------------- 저장
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n저장 : {outp}")

    rd = Path(a.report_dir); rd.mkdir(parents=True, exist_ok=True)
    L = ["# 색인 재구축 리포트 (build_index_ours.py)", ""]
    L += [f"- chromadb `{ver}` / 리트리버가 쓴 버전 `{EXPECT_CHROMA}`",
          f"- 모델 `{MODEL_ID}` (device={dev}), `normalize_embeddings=True`",
          f"- scope `{a.scope}` - 청크 {len(use)}/{len(chunks_all)}건, dim={dim}",
          f"- 임베딩 {t_embed:.1f}초 / 검색 {t_search:.2f}초",
          f"- **확정 색인 위치** `{used}`",
          f"- {copy_note}", ""]
    L += ["## 시도 기록", "",
          "| # | 조합 | batch | sync_threshold | .bin | queue | 새 프로세스 열기 |",
          "|---|---|---|---|---|---|---|"]
    for i, at in enumerate(attempts, 1):
        L.append(f"| {i} | {at['label']} | {at['batch_size']} | "
                 f"{at['sync_threshold'] or '(기본)'} | {at['bin_have']}/4 | "
                 f"{at['sqlite'].get('embeddings_queue')} | "
                 f"{'PASS' if at['fresh_ok'] else 'FAIL - ' + str(at['fresh'].get('error'))[:60]} |")
    L += ["", "판정 기준은 **새 프로세스에서 열리는가** 하나다. "
          "같은 프로세스 재오픈은 Chroma 가 메모리에 든 인덱스를 재사용하므로 증거가 안 된다.", ""]
    L += ["## 확정 색인 파일", "", "| 파일 | 바이트 |", "|---|---|"]
    for name, size in files_used:
        L.append(f"| `{name}` | {size:,} |")
    L += ["", f"- `.bin` {len(have)}/4, 누락: {missing if missing else '없음'}",
          f"- `PRAGMA integrity_check` = `{facts.get('integrity_check')}`",
          f"- sqlite `embeddings` {facts.get('embeddings')}행 / "
          f"`embeddings_queue` {facts.get('embeddings_queue')}행", ""]
    L += ["## Recall", "", "| k | chroma | numpy 대조군 |", "|---|---|---|"]
    for k in (1, 3, 5):
        L.append(f"| {k} | {recall('chroma_rank', k) * 100:.1f}% | {recall('numpy_rank', k) * 100:.1f}% |")
    L += ["", f"gold_evidence 없는 문항은 분모에서 제외 (n={len(scored)}).", "",
          f"두 방식 top-{a.top_k} 순서 일치 {n_same}/{len(detail)}"
          + (f", top1 score 최대 차이 {max(dscore):.6f}" if dscore else ""), ""]
    L += ["## 문항별", "", "| qid | 후보 | gold | chroma 순위 | numpy 순위 | chroma top1 | 일치 |",
          "|---|---|---|---|---|---|---|"]
    for d in detail:
        L.append(f"| {d['question_id']} | {d['n_candidates']} | {len(d['gold'])} | "
                 f"{d['chroma_rank'] or '-'} | {d['numpy_rank'] or '-'} | "
                 f"{d['chroma_top1'] if d['chroma_top1'] is not None else '-'} | "
                 f"{'O' if d['same_order'] else 'X'} |")
    (rd / "index_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"저장 : {rd / 'index_report.md'}")

    # ---------------------------------------------------------------- 그림
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    ok_font = False
    for f_ in ("Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"):
        if any(f_.lower() in ff.name.lower() for ff in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f_; ok_font = True; break
    plt.rcParams["axes.unicode_minus"] = False
    T = (lambda k, e: k) if ok_font else (lambda k, e: e)

    fig, ax = plt.subplots(2, 2, figsize=(14, 9))

    # (1) 시도별 결과
    a0 = ax[0][0]
    labels = [at["label"].split(".")[0] for at in attempts]
    vals = [at["bin_have"] for at in attempts]
    cols = ["#2e7d32" if at["fresh_ok"] else "#c62828" for at in attempts]
    a0.bar(range(len(attempts)), vals, color=cols)
    for i, at in enumerate(attempts):
        a0.text(i, at["bin_have"] + 0.08, "PASS" if at["fresh_ok"] else "FAIL",
                ha="center", fontsize=9,
                color="#2e7d32" if at["fresh_ok"] else "#c62828")
    a0.set_xticks(range(len(attempts))); a0.set_xticklabels(labels)
    a0.set_ylim(0, 4.6); a0.set_ylabel(T(".bin 개수", ".bin count")); a0.grid(axis="y", alpha=.3)
    a0.set_title(T("시도별 결과 (초록=새 프로세스 열기 성공)",
                   "attempts (green = fresh-process open OK)"), fontsize=10)

    # (2) 확정 색인 파일 크기
    a1 = ax[0][1]
    names = [Path(n).name for n, _ in files_used]
    sizes = [s for _, s in files_used]
    a1.barh(range(len(names)), [s / 1e6 for s in sizes], color="#1565c0")
    a1.set_yticks(range(len(names))); a1.set_yticklabels(names, fontsize=8); a1.invert_yaxis()
    a1.set_xlabel("MB"); a1.grid(axis="x", alpha=.3)
    a1.set_title(T(f"확정 색인 파일 (.bin {len(have)}/4)",
                   f"final index files (.bin {len(have)}/4)"), fontsize=10)

    # (3) Recall
    a2 = ax[1][0]
    ks = [1, 3, 5]; w = 0.36
    cv = [recall("chroma_rank", k) * 100 for k in ks]
    nv = [recall("numpy_rank", k) * 100 for k in ks]
    a2.bar([i - w / 2 for i in range(3)], cv, w, label="chroma", color="#2e7d32")
    a2.bar([i + w / 2 for i in range(3)], nv, w, label="numpy", color="#ef6c00")
    for i in range(3):
        a2.text(i - w / 2, cv[i] + 1, f"{cv[i]:.0f}", ha="center", fontsize=8)
        a2.text(i + w / 2, nv[i] + 1, f"{nv[i]:.0f}", ha="center", fontsize=8)
    a2.set_xticks(range(3)); a2.set_xticklabels([f"@{k}" for k in ks])
    a2.set_ylim(0, 110); a2.set_ylabel("%"); a2.legend(fontsize=8); a2.grid(axis="y", alpha=.3)
    a2.set_title(T(f"Recall@k  (n={len(scored)})", f"Recall@k  (n={len(scored)})"), fontsize=10)

    # (4) 문항별 top1 대조
    a3 = ax[1][1]
    qids = [d["question_id"] for d in detail]
    ct = [d["chroma_top1"] if d["chroma_top1"] is not None else np.nan for d in detail]
    nt = [d["numpy_top1"] if d["numpy_top1"] is not None else np.nan for d in detail]
    y = np.arange(len(qids))
    a3.scatter(ct, y, s=42, color="#2e7d32", label="chroma", zorder=3)
    a3.scatter(nt, y, s=42, facecolors="none", edgecolors="#ef6c00", lw=1.6, label="numpy", zorder=3)
    a3.set_yticks(y); a3.set_yticklabels(qids, fontsize=8); a3.invert_yaxis()
    a3.set_xlabel("top1 cosine"); a3.legend(fontsize=8); a3.grid(axis="x", alpha=.3)
    a3.set_title(T("문항별 top1 score - 두 방식이 겹쳐야 정상",
                   "top1 score per question (should overlap)"), fontsize=10)

    fig.tight_layout()
    figp = rd / "fig_index.png"
    fig.savefig(figp, dpi=130)
    print(f"저장 : {figp}")

    if src != final and used == final and not a.keep_work:
        shutil.rmtree(src, ignore_errors=True)
        print(f"\n작업폴더 정리 : {src}")

    # ---------------------------------------------------------------- 마무리
    print("\n" + "=" * 78)
    print("결과")
    print("=" * 78)
    print(f"  성공한 조합 : {winner['label']}")
    print(f"  확정 색인   : {used}")
    print(f"  .bin        : {len(have)}/4" + (f"  누락 {missing}" if missing else ""))
    print(f"  새 프로세스에서 열기 : PASS")
    print(f"  Recall@1/3/5 : {recall('chroma_rank',1)*100:.1f}% / "
          f"{recall('chroma_rank',3)*100:.1f}% / {recall('chroma_rank',5)*100:.1f}%"
          f"   (numpy 대조군과 순서 {n_same}/{len(detail)} 일치)")
    if used != final:
        print(f"\n  !! 최종 경로 {final} 에서는 색인이 열리지 않았다.")
        print(f"     서버·리트리버에 넘길 때는 위 '확정 색인' 경로의 폴더를 그대로 옮겨야 한다.")
    print(f"\n  노트북 셀 10-B 의 HITS_FILE :")
    print(f"    {outp}")
    print(f"  retriever.py 를 쓸 때의 환경변수 :")
    print(f"    AI_RETRIEVER_PERSIST_DIR={used}")


if __name__ == "__main__":
    main()

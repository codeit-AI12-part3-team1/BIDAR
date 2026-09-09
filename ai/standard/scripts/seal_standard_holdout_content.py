"""
STANDARD_HOLDOUT 15건의 실제 documents/chunks 원문을 지금 시점에 미리 뽑아서 봉인한다.

원칙: "Holdout 산출물은 만들어서 봉인하되, 개발 handoff에는 넣지 않는다."
- 지금 STANDARD_DATASET_v0(standard_v0_baseline/dataset/)와 동일한 M0~M2 파이프라인 산출물에서
  그대로 slice한다 (재파싱/재청킹 없음 -> parser/chunker 버전 드리프트 위험 없음).
- 결과는 standard_holdout_15/sealed_content/ 에만 쓰고, DEV/VAL handoff 트리
  (standard_v0_split_70_15_15/)에는 절대 넣지 않는다.

입력:
  - governance/standard_v0_split_crosswalk_v0.1.jsonl (split == FINAL_HOLDOUT)
  - standard_v0_baseline/dataset/documents.jsonl
  - standard_v0_baseline/dataset/chunk_dataset.jsonl
  - standard_v0_baseline/dataset/index_config.json (파이프라인 버전 근거)
  - standard_v0_baseline/MANIFEST.json (파이프라인 버전 근거)

출력:
  standard_holdout_15/sealed_content/
  ├── documents.jsonl   (15건)
  ├── chunks.jsonl
  ├── sealed_content_manifest.json   (건수/해시/파이프라인 버전 근거/봉인일)
  └── README.md
"""
import hashlib
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEALED_DIR = f"{ROOT}\\standard_holdout_15\\sealed_content"


def norm_filename(s):
    if not s:
        return s
    s = re.sub(r"[()\[\]]", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    cw = [json.loads(l) for l in open(f"{ROOT}\\governance\\standard_v0_split_crosswalk_v0.1.jsonl", encoding="utf-8")]
    holdout = [c for c in cw if c["split"] == "FINAL_HOLDOUT"]
    # 이 프로젝트의 100건짜리 crosswalk에 고정된 숫자(15)가 아니라 "존재하는지"만 검증한다 -
    # 다른 규모/비율의 데이터셋을 넣어도 그대로 재사용 가능해야 하기 때문.
    assert holdout, "crosswalk에 FINAL_HOLDOUT split이 하나도 없음 - split 컬럼 확인 필요"
    assert all(c["holdout_sealed"] for c in holdout)

    canonical_group_size = {}
    for c in holdout:
        canonical_group_size[c["canonical_doc_id"]] = canonical_group_size.get(c["canonical_doc_id"], 0) + 1
    by_canonical_and_name = {(c["canonical_doc_id"], norm_filename(c["original_name"])): c for c in holdout}
    doc_id_by_canonical_unambiguous = {
        c["canonical_doc_id"]: c["document_id"] for c in holdout if canonical_group_size[c["canonical_doc_id"]] == 1
    }

    def resolve_document_id(canonical_doc_id, filename):
        key = (canonical_doc_id, norm_filename(filename))
        if key in by_canonical_and_name:
            return by_canonical_and_name[key]["document_id"], "filename_match"
        if canonical_doc_id in doc_id_by_canonical_unambiguous:
            return doc_id_by_canonical_unambiguous[canonical_doc_id], "canonical_unique"
        return None, "unresolved"

    holdout_canonical_ids = {c["canonical_doc_id"] for c in holdout}
    role_by_canonical = {c["canonical_doc_id"]: "STANDARD_HOLDOUT" for c in holdout}

    documents = [json.loads(l) for l in open(f"{ROOT}\\standard_v0_baseline\\dataset\\documents.jsonl", encoding="utf-8")]
    chunks = [json.loads(l) for l in open(f"{ROOT}\\standard_v0_baseline\\dataset\\chunk_dataset.jsonl", encoding="utf-8")]

    os.makedirs(SEALED_DIR, exist_ok=True)

    doc_count = 0
    unresolved_docs = []
    docs_written_ids = set()
    with open(f"{SEALED_DIR}\\documents.jsonl", "w", encoding="utf-8") as fw:
        for d in documents:
            cid = d["canonical_doc_id"]
            if cid not in holdout_canonical_ids:
                continue
            did, method = resolve_document_id(cid, d.get("source_filename", ""))
            if did is None:
                unresolved_docs.append(cid)
                continue
            d_out = dict(d)
            d_out["document_id"] = did
            d_out["semantic_role"] = role_by_canonical[cid]
            d_out["split_version"] = "STANDARD_V0_SPLIT_70_15_15_v0.1"
            d_out["document_id_resolve_method"] = method
            fw.write(json.dumps(d_out, ensure_ascii=False) + "\n")
            doc_count += 1
            docs_written_ids.add(cid)

    chunk_count = 0
    empty_text = 0
    fk_orphan = 0
    with open(f"{SEALED_DIR}\\chunks.jsonl", "w", encoding="utf-8") as fw:
        for c in chunks:
            cid = c["metadata"]["canonical_doc_id"]
            if cid not in holdout_canonical_ids:
                continue
            if cid not in docs_written_ids:
                fk_orphan += 1
                continue
            src_filenames = c["metadata"].get("source_filenames") or []
            did, method = resolve_document_id(cid, src_filenames[0] if src_filenames else "")
            if did is None:
                continue
            c_out = dict(c)
            c_out["metadata"] = dict(c["metadata"])
            c_out["metadata"]["document_id"] = did
            c_out["metadata"]["semantic_role"] = role_by_canonical[cid]
            c_out["metadata"]["document_id_resolve_method"] = method
            if not c_out.get("text", "").strip():
                empty_text += 1
            fw.write(json.dumps(c_out, ensure_ascii=False) + "\n")
            chunk_count += 1

    index_config = json.load(open(f"{ROOT}\\standard_v0_baseline\\dataset\\index_config.json", encoding="utf-8"))
    baseline_manifest = json.load(open(f"{ROOT}\\standard_v0_baseline\\MANIFEST.json", encoding="utf-8"))

    manifest = {
        "role": "STANDARD_HOLDOUT_SEALED_CONTENT",
        "not_project_final_holdout": True,
        "principle": "Holdout 산출물은 만들어서 봉인하되, 개발 handoff에는 넣지 않는다",
        "sealed_at": "2026-09-07",
        "document_count": doc_count,
        "chunk_count": chunk_count,
        "fk_orphan": fk_orphan,
        "empty_text": empty_text,
        "unresolved_documents": unresolved_docs,
        "pipeline_version_evidence": {
            "source": "standard_v0_baseline (STANDARD_DATASET_v0와 동일 M0~M2 산출물에서 재파싱 없이 slice)",
            "index_config": index_config,
            "baseline_manifest_run_config": baseline_manifest.get("run_config"),
            "baseline_frozen_at": baseline_manifest.get("frozen_at"),
        },
        "content_file_hashes": {
            "documents.jsonl": sha256_file(f"{SEALED_DIR}\\documents.jsonl"),
            "chunks.jsonl": sha256_file(f"{SEALED_DIR}\\chunks.jsonl"),
        },
        "access_policy": {
            "excluded_from_dev_handoff": True,
            "excluded_from_dev_handoff_path": "standard_v0_split_70_15_15/ (dev/, val/ 만 존재, 이 폴더는 미포함)",
            "open_condition": "Retriever/Generator가 나머지 DEV/VAL 세트로 충분히 freeze된 뒤, Standard Holdout 평가 시점 1회",
        },
    }
    with open(f"{SEALED_DIR}\\sealed_content_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    readme = f"""# STANDARD_HOLDOUT_{len(holdout)} / sealed_content

ROLE = STANDARD_HOLDOUT_SEALED_CONTENT
NOT PROJECT FINAL HOLDOUT
DO NOT USE FOR DEVELOPMENT OR TUNING
개발 handoff 패키지(`standard_v0_split_70_15_15/`)에 이 폴더 내용을 포함하지 않습니다.

## 왜 지금 미리 만들어뒀나

Standard Holdout 평가 시점에 새로 파싱/청킹하지 않고, DEV/VAL과 동일 시점(`standard_v0_baseline`,
동일 parser/chunker/config)에 이미 만들어진 원문에서 그대로 slice했습니다. 그래야 나중에
parser/chunker가 바뀌어도 이 {len(holdout)}건은 지금 시점 기준으로 고정된 채 평가 조건이 흔들리지
않습니다. `sealed_content_manifest.json`의 `pipeline_version_evidence`에 그 근거(embedding
모델/토크나이저/seed/baseline frozen 시각)와 이 두 파일 자체의 sha256을 같이 기록해뒀습니다.

## 봉인 해제 조건

`sealed_content_manifest.json`의 `access_policy.open_condition` 참고 — Retriever/Generator가
나머지 DEV/VAL 세트로 충분히 freeze된 뒤, Standard Holdout 평가 시점에 딱 1회 엽니다.
"""
    with open(f"{SEALED_DIR}\\README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    summary = [
        f"documents: {doc_count}",
        f"chunks: {chunk_count}",
        f"fk_orphan: {fk_orphan}, empty_text: {empty_text}, unresolved_documents: {unresolved_docs}",
    ]
    with open(f"{ROOT}\\governance\\_last_run_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary))


if __name__ == "__main__":
    main()

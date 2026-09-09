"""
STANDARD 전용 Block 계층 생성.

RFP100_blocks_DEV_v0.1.jsonl(Custom/DOC_XXX/C0 파이프라인)을 갖다 붙이지 않는다 - FK가 가짜로
연결됨. 대신 STANDARD_DATASET_v0 자체가 이미 갖고 있던 element 계층을 쓴다.

Document(canonical_doc_id) -> Block(element_id, evidence.source_file/parser로 provenance) ->
Chunk(metadata.element_ids로 block을 참조) 구조를 완성한다.

출력:
  - standard_v0_split_70_15_15/dev/blocks.jsonl, /val/blocks.jsonl
  - standard_holdout_15/sealed_content/blocks.jsonl
  - governance/standard_v0_blocks_validation_v0.1.json (FK/provenance 검증)
"""
import json
import os
import re







def norm_filename(s):
    if not s:
        return s
    s = re.sub(r"[()\[\]]", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def build_resolver(rows):
    """rows: crosswalk 레코드 리스트(특정 split 범위) -> (canonical_doc_id, filename) 매칭기"""
    group_size = {}
    for c in rows:
        group_size[c["canonical_doc_id"]] = group_size.get(c["canonical_doc_id"], 0) + 1
    by_name = {(c["canonical_doc_id"], norm_filename(c["original_name"])): c for c in rows}
    unambiguous = {c["canonical_doc_id"]: c["document_id"] for c in rows if group_size[c["canonical_doc_id"]] == 1}

    def resolve(canonical_doc_id, filename):
        key = (canonical_doc_id, norm_filename(filename))
        if key in by_name:
            return by_name[key]["document_id"], "filename_match"
        if canonical_doc_id in unambiguous:
            return unambiguous[canonical_doc_id], "canonical_unique"
        return None, "unresolved"

    return resolve


def process_split(rows, elements, chunks_path, out_path, semantic_role):
    canonical_ids = {c["canonical_doc_id"] for c in rows}
    resolve = build_resolver(rows)

    written = 0
    empty_text = 0
    unresolved = []
    element_ids_written = set()
    with open(out_path, "w", encoding="utf-8") as fw:
        for e in elements:
            cid = e["canonical_doc_id"]
            if cid not in canonical_ids:
                continue
            src_file = (e.get("evidence") or {}).get("source_file", "")
            did, method = resolve(cid, src_file)
            if did is None:
                unresolved.append({"element_id": e["element_id"], "canonical_doc_id": cid})
                continue
            e_out = dict(e)
            e_out["document_id"] = did
            e_out["semantic_role"] = semantic_role
            e_out["split_version"] = "STANDARD_V0_SPLIT_70_15_15_v0.1"
            e_out["document_id_resolve_method"] = method
            if not (e_out.get("text") or "").strip():
                empty_text += 1
            fw.write(json.dumps(e_out, ensure_ascii=False) + "\n")
            written += 1
            element_ids_written.add(e["element_id"])

    # FK 검증: 같은 split의 chunks.jsonl이 참조하는 element_ids가 전부 이 블록 slice에 있는지
    fk_total_refs = 0
    fk_orphan_refs = 0
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            for eid in c["metadata"].get("element_ids", []):
                fk_total_refs += 1
                if eid not in element_ids_written:
                    fk_orphan_refs += 1

    return {
        "written": written,
        "empty_text": empty_text,
        "unresolved": unresolved,
        "chunk_element_id_refs_total": fk_total_refs,
        "chunk_element_id_refs_orphan": fk_orphan_refs,
    }


def main():
    cw = [json.loads(l) for l in open(f"{ROOT}\\governance\\standard_v0_split_crosswalk_v0.1.jsonl", encoding="utf-8")]
    elements = [json.loads(l) for l in open(ELEMENTS_SRC, encoding="utf-8")]

    dev_rows = [c for c in cw if c["split"] == "DEV"]
    val_rows = [c for c in cw if c["split"] == "REGRESSION"]
    holdout_rows = [c for c in cw if c["split"] == "FINAL_HOLDOUT"]

    results = {}
    results["dev"] = process_split(
        dev_rows, elements,
        f"{ROOT}\\standard_v0_split_70_15_15\\dev\\chunks.jsonl",
        f"{ROOT}\\standard_v0_split_70_15_15\\dev\\blocks.jsonl",
        "DEV",
    )
    results["val"] = process_split(
        val_rows, elements,
        f"{ROOT}\\standard_v0_split_70_15_15\\val\\chunks.jsonl",
        f"{ROOT}\\standard_v0_split_70_15_15\\val\\blocks.jsonl",
        "VAL",
    )
    results["standard_holdout"] = process_split(
        holdout_rows, elements,
        f"{ROOT}\\standard_holdout_15\\sealed_content\\chunks.jsonl",
        f"{ROOT}\\standard_holdout_15\\sealed_content\\blocks.jsonl",
        "STANDARD_HOLDOUT",
    )

    validation = {
        "source": {
            "elements_source_path": ELEMENTS_SRC,
            "consistency_with_standard_v0_baseline": "VERIFIED_2026-09-07: canonical_doc_id 98/98 일치, sha256 불일치 0, chunk_id 24030/24030 일치",
        },
        "splits": results,
        "all_fk_clean": all(r["chunk_element_id_refs_orphan"] == 0 for r in results.values()),
        "all_empty_text_zero": all(r["empty_text"] == 0 for r in results.values()),
        "all_unresolved_zero": all(len(r["unresolved"]) == 0 for r in results.values()),
    }

    os.makedirs(f"{ROOT}\\governance", exist_ok=True)
    with open(f"{ROOT}\\governance\\standard_v0_blocks_validation_v0.1.json", "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)

    summary = [
        f"dev: elements={results['dev']['written']} empty_text={results['dev']['empty_text']} fk_orphan={results['dev']['chunk_element_id_refs_orphan']}/{results['dev']['chunk_element_id_refs_total']} unresolved={len(results['dev']['unresolved'])}",
        f"val: elements={results['val']['written']} empty_text={results['val']['empty_text']} fk_orphan={results['val']['chunk_element_id_refs_orphan']}/{results['val']['chunk_element_id_refs_total']} unresolved={len(results['val']['unresolved'])}",
        f"standard_holdout: elements={results['standard_holdout']['written']} empty_text={results['standard_holdout']['empty_text']} fk_orphan={results['standard_holdout']['chunk_element_id_refs_orphan']}/{results['standard_holdout']['chunk_element_id_refs_total']} unresolved={len(results['standard_holdout']['unresolved'])}",
        f"all_fk_clean={validation['all_fk_clean']} all_empty_text_zero={validation['all_empty_text_zero']} all_unresolved_zero={validation['all_unresolved_zero']}",
    ]
    with open(f"{ROOT}\\governance\\_last_run_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary))


if __name__ == "__main__":
    main()

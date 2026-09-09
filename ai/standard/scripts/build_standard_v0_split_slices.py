"""
STANDARD_V0_70_15_15_SPLIT_EXECUTION_GUIDE.md 5절(documents/blocks/chunks split) + 7절(handoff 구조).

DEV(70) + VAL(=REGRESSION, 15)에 대해서만 실제 documents/chunks 원문을 slice한다.
STANDARD_HOLDOUT(15)은 여기서 슬라이스하지 않는다 (봉인 정책 - standard_holdout_15/README.md 참고).

입력:
  - governance/standard_v0_split_crosswalk_v0.1.jsonl
  - standard_v0_baseline/dataset/documents.jsonl
  - standard_v0_baseline/dataset/chunk_dataset.jsonl

출력:
  standard_v0_split_70_15_15/
  ├── dev/documents.jsonl, dev/chunks.jsonl
  ├── val/documents.jsonl, val/chunks.jsonl
  ├── standard_v0_split_manifest.jsonl   (DEV/VAL 100건 crosswalk 그대로 복사, HOLDOUT 제외)
  ├── validation_report.json
  └── README.md

주의: standard_v0_baseline/dataset/에는 별도 blocks.jsonl이 없음(M0~M2 산출물이 document+chunk
2계층으로만 구성됨). 01/STANDARD 가이드가 예시로 든 blocks.jsonl은 이번 산출물에 포함하지 않는다.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = f"{ROOT}\\standard_v0_split_70_15_15"

SPLIT_TO_DIR = {"DEV": "dev", "REGRESSION": "val"}


def norm_filename(s):
    """괄호/공백 제거 후 비교 - Kaggle 업로드 과정에서 파일명 sanitize로 괄호가 빠지는 경우가 있어
    표준화 후 매칭한다 (memory: kaggle-zip-nfd-byte-limit-bug와 유사한 sanitize 패턴)."""
    if not s:
        return s
    s = re.sub(r"[()\[\]]", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def main():
    cw = [json.loads(l) for l in open(f"{ROOT}\\governance\\standard_v0_split_crosswalk_v0.1.jsonl", encoding="utf-8")]
    handoff = [c for c in cw if c["split"] in SPLIT_TO_DIR]  # HOLDOUT 제외
    holdout_total = len([c for c in cw if c["split"] == "FINAL_HOLDOUT"])
    # 이 프로젝트의 100건짜리 crosswalk에 고정된 숫자(85)가 아니라, crosswalk 전체 건수 기준으로
    # 검증한다 - 다른 규모의 데이터셋을 넣어도 그대로 재사용 가능해야 하기 때문.
    assert handoff, "crosswalk에 DEV/REGRESSION split이 하나도 없음 - split 컬럼 확인 필요"
    assert len(handoff) + holdout_total == len(cw), (
        f"handoff({len(handoff)}) + holdout({holdout_total})가 crosswalk 전체({len(cw)})와 안 맞음 - "
        "split 값에 DEV/REGRESSION/FINAL_HOLDOUT 외 다른 값이 섞였을 수 있음"
    )

    # canonical_doc_id가 겹치는(완전 동일 콘텐츠) 경우가 있어 canonical_doc_id만으로는
    # document_id를 유일하게 못 찾는다 -> (canonical_doc_id, 정규화 파일명) 복합키로 우선 매칭하고,
    # 겹치지 않는 경우에만 canonical_doc_id 단독 매칭으로 폴백한다.
    by_canonical_and_name = {}
    canonical_group_size = {}
    for c in handoff:
        canonical_group_size[c["canonical_doc_id"]] = canonical_group_size.get(c["canonical_doc_id"], 0) + 1
        key = (c["canonical_doc_id"], norm_filename(c["original_name"]))
        by_canonical_and_name[key] = c

    role_by_canonical = {c["canonical_doc_id"]: c["semantic_role"] for c in handoff}
    dir_by_canonical = {c["canonical_doc_id"]: SPLIT_TO_DIR[c["split"]] for c in handoff}
    # 모호하지 않은(그룹 크기 1) canonical_doc_id는 여기로 바로 조회
    doc_id_by_canonical_unambiguous = {
        c["canonical_doc_id"]: c["document_id"] for c in handoff if canonical_group_size[c["canonical_doc_id"]] == 1
    }
    # canonical_doc_id가 겹치는 그룹: document_id 목록 (형제 document_id 태깅용)
    siblings_by_canonical = {}
    for c in handoff:
        if canonical_group_size[c["canonical_doc_id"]] > 1:
            siblings_by_canonical.setdefault(c["canonical_doc_id"], []).append(c["document_id"])

    def resolve_document_id(canonical_doc_id, filename):
        """filename(정규화)으로 우선 매칭, 실패 시 모호하지 않은 canonical_doc_id로 폴백."""
        key = (canonical_doc_id, norm_filename(filename))
        if key in by_canonical_and_name:
            return by_canonical_and_name[key]["document_id"], "filename_match"
        if canonical_doc_id in doc_id_by_canonical_unambiguous:
            return doc_id_by_canonical_unambiguous[canonical_doc_id], "canonical_unique"
        return None, "unresolved"

    documents = [json.loads(l) for l in open(f"{ROOT}\\standard_v0_baseline\\dataset\\documents.jsonl", encoding="utf-8")]
    chunks = [json.loads(l) for l in open(f"{ROOT}\\standard_v0_baseline\\dataset\\chunk_dataset.jsonl", encoding="utf-8")]

    os.makedirs(f"{OUT_DIR}\\dev", exist_ok=True)
    os.makedirs(f"{OUT_DIR}\\val", exist_ok=True)

    doc_writers = {
        "dev": open(f"{OUT_DIR}\\dev\\documents.jsonl", "w", encoding="utf-8"),
        "val": open(f"{OUT_DIR}\\val\\documents.jsonl", "w", encoding="utf-8"),
    }
    chunk_writers = {
        "dev": open(f"{OUT_DIR}\\dev\\chunks.jsonl", "w", encoding="utf-8"),
        "val": open(f"{OUT_DIR}\\val\\chunks.jsonl", "w", encoding="utf-8"),
    }

    doc_counts = {"dev": 0, "val": 0}
    docs_written_ids = set()
    unresolved_docs = []
    doc_id_written_by_canonical = {}
    for d in documents:
        cid = d["canonical_doc_id"]
        if cid not in dir_by_canonical:
            continue  # HOLDOUT이거나 (있을 수 없지만) 미매핑
        did, resolve_method = resolve_document_id(cid, d.get("source_filename", ""))
        if did is None:
            unresolved_docs.append({"canonical_doc_id": cid, "source_filename": d.get("source_filename")})
            continue
        d_out = dict(d)
        d_out["document_id"] = did
        d_out["semantic_role"] = role_by_canonical[cid]
        d_out["split_version"] = "STANDARD_V0_SPLIT_70_15_15_v0.1"
        d_out["document_id_resolve_method"] = resolve_method
        if cid in siblings_by_canonical:
            d_out["duplicate_content_sibling_document_ids"] = [x for x in siblings_by_canonical[cid] if x != did]
        target = dir_by_canonical[cid]
        doc_writers[target].write(json.dumps(d_out, ensure_ascii=False) + "\n")
        doc_counts[target] += 1
        docs_written_ids.add(cid)
        doc_id_written_by_canonical.setdefault(cid, set()).add(did)

    chunk_counts = {"dev": 0, "val": 0}
    empty_text_count = 0
    orphan_chunk_count = 0
    unresolved_chunks = 0
    for c in chunks:
        cid = c["metadata"]["canonical_doc_id"]
        if cid not in dir_by_canonical:
            continue
        if cid not in docs_written_ids:
            orphan_chunk_count += 1
            continue
        src_filenames = c["metadata"].get("source_filenames") or []
        did, resolve_method = resolve_document_id(cid, src_filenames[0] if src_filenames else "")
        if did is None:
            unresolved_chunks += 1
            continue
        c_out = dict(c)
        c_out["metadata"] = dict(c["metadata"])
        c_out["metadata"]["document_id"] = did
        c_out["metadata"]["semantic_role"] = role_by_canonical[cid]
        c_out["metadata"]["document_id_resolve_method"] = resolve_method
        if cid in siblings_by_canonical:
            c_out["metadata"]["duplicate_content_sibling_document_ids"] = [x for x in siblings_by_canonical[cid] if x != did]
        if not c_out.get("text", "").strip():
            empty_text_count += 1
        target = dir_by_canonical[cid]
        chunk_writers[target].write(json.dumps(c_out, ensure_ascii=False) + "\n")
        chunk_counts[target] += 1

    for w in list(doc_writers.values()) + list(chunk_writers.values()):
        w.close()

    # split manifest (HOLDOUT 제외한 85건)
    with open(f"{OUT_DIR}\\standard_v0_split_manifest.jsonl", "w", encoding="utf-8") as f:
        for c in handoff:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # FK 검증: 각 slice의 chunk canonical_doc_id가 같은 slice documents에 다 있는지
    def fk_check(split_dir):
        doc_ids = set()
        with open(f"{OUT_DIR}\\{split_dir}\\documents.jsonl", encoding="utf-8") as f:
            for line in f:
                doc_ids.add(json.loads(line)["canonical_doc_id"])
        bad = 0
        empty = 0
        total = 0
        with open(f"{OUT_DIR}\\{split_dir}\\chunks.jsonl", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                total += 1
                if rec["metadata"]["canonical_doc_id"] not in doc_ids:
                    bad += 1
                if not rec.get("text", "").strip():
                    empty += 1
        return {"chunk_total": total, "fk_orphan": bad, "empty_text": empty, "document_count": len(doc_ids)}

    validation = {
        "dev": fk_check("dev"),
        "val": fk_check("val"),
        "cross_slice_orphan_chunks_skipped": orphan_chunk_count,
        "document_id_unresolved_count": len(unresolved_docs),
        "document_id_unresolved": unresolved_docs,
        "chunk_document_id_unresolved_count": unresolved_chunks,
        "duplicate_content_groups": len(siblings_by_canonical),
        "note": f"STANDARD_HOLDOUT({holdout_total})은 정책상 이 산출물에서 제외됨 (standard_holdout_15/ 참고)",
    }

    with open(f"{OUT_DIR}\\validation_report.json", "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)

    if siblings_by_canonical:
        dup_lines = []
        for canonical_id, doc_ids in siblings_by_canonical.items():
            dup_lines.append(f"- `{canonical_id}`: {', '.join(f'`{d}`' for d in sorted(set(doc_ids)))}")
        dup_section = (
            "## 완전 동일 콘텐츠(SHA-256 동일) 문서 그룹 처리\n\n"
            f"아래 {len(siblings_by_canonical)}개 canonical_doc_id는 서로 다른 document_id가 완전히 "
            "동일한 원본 파일(SHA-256 일치)을 가리킵니다. `canonical_doc_id`만으로는 어느 document_id에 "
            "대응하는지 구분이 안 되므로, 원본 파일명(정규화 후)으로 매칭해 각 물리적 documents.jsonl 행을 "
            "올바른 document_id에 연결했습니다(`document_id_resolve_method: filename_match`). Chunk는 "
            "그룹 중 실제로 청킹된 쪽 하나에서만 나오므로, 나머지 document_id는 "
            "`duplicate_content_sibling_document_ids` 필드로 표시해 \"이 chunk가 그 문서의 근거로도 쓰일 "
            "수 있다\"는 걸 잃지 않게 했습니다.\n\n" + "\n".join(dup_lines) + "\n"
        )
    else:
        dup_section = "## 완전 동일 콘텐츠(SHA-256 동일) 문서 그룹\n\n이번 데이터셋에는 해당 사례가 없습니다.\n"

    readme = f"""# STANDARD_V0_SPLIT_70_15_15 — DEV/VAL Handoff

`STANDARD_DATASET_v0`({ '`standard_v0_baseline/dataset/`' })를 `RFP100_splits_v0.1.json` 배정
그대로 승계해 DEV({doc_counts['dev']})/VAL(=REGRESSION,{doc_counts['val']})만 slice한 것입니다.
corpus/chunk boundary/ID 자체는 바꾸지 않았습니다(01_STANDARD_DATASET_TO_EXISTING_RAG_COMPAT_GUIDE_v0.1.md
9절 Case A).

## 포함 안 된 것

- `STANDARD_HOLDOUT`({holdout_total}건): `standard_holdout_15/`에 신원만 봉인돼 있고 원문은 없음. 여기도 없음.
- `blocks.jsonl`: `standard_v0_baseline/dataset/`에 원래 없음(document + chunk 2계층 구성).
  Structural Block이 필요하면 별도로 확인 필요.

## 각 레코드에 추가된 필드

기존 `canonical_doc_id`/`chunk_id`는 그대로 보존하고, 아래 필드만 덧붙였습니다.

- `document_id` (예: `{handoff[0]['document_id']}`) — 기존 Retriever/Generator handoff 인터페이스 ID
- `semantic_role` (`DEV` / `VAL`) — split 값(`DEV`/`REGRESSION`)의 의미역
- `split_version`: `STANDARD_V0_SPLIT_70_15_15_v0.1`
- `document_id_resolve_method`: `filename_match` 또는 `canonical_unique`

{dup_section}
## 파일

- `dev/documents.jsonl`, `dev/chunks.jsonl`
- `val/documents.jsonl`, `val/chunks.jsonl`
- `standard_v0_split_manifest.jsonl` — DEV+VAL {len(handoff)}건 crosswalk (HOLDOUT 제외)
- `validation_report.json` — FK/empty text 검증 결과
"""
    with open(f"{OUT_DIR}\\README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    summary = [
        f"documents: dev={doc_counts['dev']} val={doc_counts['val']}",
        f"chunks: dev={chunk_counts['dev']} val={chunk_counts['val']}",
        f"orphan_chunk_skipped(문서 slice에 없는 chunk): {orphan_chunk_count}",
        f"validation: {json.dumps(validation, ensure_ascii=False)}",
    ]
    with open(f"{ROOT}\\governance\\_last_run_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary))


if __name__ == "__main__":
    main()


"""
STANDARD_V0_70_15_15_SPLIT_EXECUTION_GUIDE.md 5절 — Standard Holdout 15 Seal

입력: governance/standard_v0_split_crosswalk_v0.1.jsonl (split == FINAL_HOLDOUT)
출력: standard_holdout_15/{STANDARD_HOLDOUT_MANIFEST.json, selected_ids.txt, artifact_hashes.json, README.md}

이 스크립트는 crosswalk에서 이미 확정된 15건을 그대로 옮겨 적을 뿐, 새로운 선정/판단을 하지 않는다.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = f"{ROOT}\\standard_holdout_15"


def main():
    cw = [json.loads(l) for l in open(f"{ROOT}\\governance\\standard_v0_split_crosswalk_v0.1.jsonl", encoding="utf-8")]
    holdout = [c for c in cw if c["split"] == "FINAL_HOLDOUT"]

    # 이 프로젝트의 100건짜리 crosswalk에 고정된 숫자(15)가 아니라 "존재하는지"만 검증한다 -
    # 다른 규모/비율의 데이터셋을 넣어도 그대로 재사용 가능해야 하기 때문.
    assert holdout, "crosswalk에 FINAL_HOLDOUT split이 하나도 없음 - split 컬럼 확인 필요"
    assert all(c["holdout_sealed"] for c in holdout), "holdout_sealed=False 레코드가 섞여 있음"
    assert all(not c["allowed_during_development"] for c in holdout), "allowed_during_development=True 레코드가 섞여 있음"

    os.makedirs(OUT_DIR, exist_ok=True)

    manifest = {
        "role": "STANDARD_HOLDOUT",
        "not_project_final_holdout": True,
        "split_version": "STANDARD_V0_SPLIT_70_15_15_v0.1",
        "source": {
            "split_assignment_ssot": "RFP100_splits_v0.1.json",
            "detailed_mapping_source": "RFP100_split_v0.1.csv",
            "canonical_doc_id_source": "standard_v0_baseline/dataset/documents.jsonl",
            "crosswalk_file": "governance/standard_v0_split_crosswalk_v0.1.jsonl",
        },
        "seal_date_recorded_in_source_csv": "2026-08-25",
        "manifest_created_at": "2026-09-07",
        "count": len(holdout),
        "documents": [
            {
                "document_id": c["document_id"],
                "canonical_doc_id": c["canonical_doc_id"],
                "procurement_group_key": c["procurement_group_key"],
                "content_group_id": c["content_group_id"],
                "sha256": c["sha256"],
            }
            for c in holdout
        ],
        "policy": {
            "do_not_use_for": [
                "Retrieval tuning",
                "Generation prompt tuning",
                "Threshold decisions",
                "Semantic/manual review of content",
            ],
            "allowed_prior_exposure": "corpus-wide machine extraction/statistics only, performed before split freeze",
            "excluded_from": [
                "Retrieval/Generation dev notebooks",
                "automatic index build",
            ],
        },
    }

    with open(f"{OUT_DIR}\\STANDARD_HOLDOUT_MANIFEST.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with open(f"{OUT_DIR}\\selected_ids.txt", "w", encoding="utf-8") as f:
        for c in holdout:
            f.write(f"{c['canonical_doc_id']}\n")

    artifact_hashes = {c["document_id"]: {"canonical_doc_id": c["canonical_doc_id"], "sha256": c["sha256"]} for c in holdout}
    with open(f"{OUT_DIR}\\artifact_hashes.json", "w", encoding="utf-8") as f:
        json.dump(artifact_hashes, f, ensure_ascii=False, indent=2)

    readme = f"""# STANDARD_HOLDOUT_{len(holdout)}

ROLE = STANDARD_HOLDOUT
NOT PROJECT FINAL HOLDOUT
DO NOT USE FOR DEVELOPMENT OR TUNING

Standard V0 {len(cw)}건 중 {len(holdout)}건, `RFP100_splits_v0.1.json`(2026-08-25 확정)의
FINAL_HOLDOUT 배정을 그대로 승계한 것입니다. Live Final Holdout 30건과는 역할이 다릅니다 —
이건 Standard 데이터셋 내부 검증용이고, 프로젝트 전체 최종 E2E 평가는 별도로 Live Final Holdout
30에서 수행합니다.

## 금지 사항

- Retrieval 튜닝에 사용 금지
- Generation prompt 튜닝에 사용 금지
- threshold 결정에 사용 금지
- 오류 사례를 보고 다시 개발하지 않음 (개발 중 이 {len(holdout)}건의 실패를 원인으로 파서/청커/프롬프트를 고치지 않음)
- Retrieval/Generation 개발용 notebook 및 자동 index 구축 대상에서 기본 제외

## 이 폴더가 갖고 있는 것 / 갖고 있지 않은 것

- `selected_ids.txt` / `STANDARD_HOLDOUT_MANIFEST.json` / `artifact_hashes.json`에는 **신원 식별자
  (canonical_doc_id, sha256, 공고번호)만** 있습니다. `RFP100_splits_v0.1.json`의
  `holdout_integrity_note`에 명시된 대로 "corpus-wide machine extraction/statistics"는 split 전에
  이미 이뤄졌고, 이 신원 정보는 그 결과물입니다.
- 이 폴더에는 **문서 원문, chunk, 파싱 결과가 들어있지 않습니다.** {len(holdout)}건의 실제
  콘텐츠(documents/blocks/chunks)는 이 폴더에 slice해 넣지 않고, Pipeline candidate가 충분히
  안정화된 뒤 Standard 내부 최종 검증 시점에만 별도로 접근합니다.

## 봉인 해제 조건

Pipeline candidate(Retriever/Generator 설정)가 나머지 DEV/VAL 세트로 충분히 안정화된 뒤,
Standard 내부 최종 검증(1회) 목적으로만 사용합니다. 그 전까지는 이 폴더의 내용을 참고해 파서,
청커, retriever, prompt, threshold를 바꾸지 않습니다.
"""
    with open(f"{OUT_DIR}\\README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    print("done")


if __name__ == "__main__":
    main()

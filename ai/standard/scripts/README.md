# scripts/ — Standard v0 데이터셋 70/15/15 split & holdout 빌드 스크립트

실행 순서대로 나열.

1. **`build_standard_v0_crosswalk.py`** — 문서 ID 간 매핑표(크로스워크)를 처음 만들 때 사용
2. **`build_standard_v0_blocks.py`** — Document/Block/Chunk 3계층 구조를 만들 때 사용
3. **`build_standard_v0_split_slices.py`** — DEV/VAL 데이터를 실제로 나눠 담을 때 사용
4. **`seal_standard_holdout.py`** — Holdout 문서의 신원(ID)만 확정/봉인할 때 사용
5. **`seal_standard_holdout_content.py`** — Holdout 문서의 실제 내용까지 미리 뽑아 봉인할 때 사용

# live_collect/ — 나라장터(G2B) LIVE 데이터 수집 파이프라인

실행 순서대로 나열. `uv run python <script>.py`로 실행.

1. **`collect_notices.py`** — 특정 기간의 입찰공고 목록을 처음 수집할 때 사용
2. **`select_targets.py`** — 수집된 공고 중 실제로 첨부파일까지 받아올 대상을 추릴 때 사용
3. **`collect_attachments.py`** — 선별된 공고의 첨부파일 다운로드 URL을 조회할 때 사용
4. **`download_files.py`** — 조회된 URL로 실제 파일을 다운로드하고 검증할 때 사용
5. **`build_live_dev_inventory.py`** — 수집이 끝난 뒤, 문서별 대표(primary) 파일을 정리한 인벤토리가 필요할 때 사용
6. **`replace_candidates.py`** — 다운로드에 실패한 후보를 다른 후보로 교체하고 싶을 때 사용
7. **`build_holdout_seal.py`** — 최종 검증용 홀드아웃 문서 30건을 확정/봉인할 때 사용

## 공통 인프라 (직접 실행하지 않고, 위 스크립트들이 내부적으로 불러다 씀)
- **`config.py`** — API 키/경로 등 공통 설정이 필요할 때
- **`quota.py`** — API 일일 호출 한도를 넘지 않게 관리해야 할 때
- **`api_client.py`** — G2B API를 실제로 호출해야 할 때

## 설정 파일
- `pyproject.toml` / `uv.lock` — 의존성 설치할 때
- `.env.example` — 처음 세팅할 때 이 파일을 복사해 `.env`로 만들고 본인 API 키를 채워 넣음

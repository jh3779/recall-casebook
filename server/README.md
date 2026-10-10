# server — 결함 선례 찾기 API 서버

질문(영어)을 받아 같은 부품의 리콜 선례와 원인 서술을 **원문 그대로** 돌려준다. 판정하지 않는다(AGENTS.md 2절).
결정 근거: DEC-038(API 서버)·DEC-039(검색 방식)·DEC-042(벡터 보관·고객사 선례).

## 띄우기

1. 로컬 build 파일이 있어야 한다: `data/processed/defect/`의 `build.json`·`recalls.jsonl`·`eval.jsonl`·`causes.jsonl`·`causes.manifest.json`
   (`scripts/defect_precedent/README.md` — 팀 드라이브 사본 또는 `nhtsa build`·`rclrpt all`).
2. Supabase에 같은 build와 카드 벡터가 있어야 한다 (`.env`의 `DATABASE_URL`, 값은 출력하지 않는다):
   ```bash
   uv run --env-file .env python -m scripts.defect_precedent.load_db schema
   uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes full
   uv run --env-file .env python -m server.rag.embeddings schema
   uv run --env-file .env python -m server.rag.embeddings load    # 카드 30,350장 임베딩(CPU 약 9분, RETRIEVAL_CACHE 캐시가 있으면 바로)
   ```
3. 서버:
   ```bash
   uv run --env-file .env uvicorn server.api:app --port 8000
   curl localhost:8000/health
   curl -X POST localhost:8000/search -H 'content-type: application/json' -d '{"question":"airbag inflator rupture"}'
   ```
   시작할 때 build 파일 해시·DB 벡터 기록·카드 16장 재임베딩을 대조하고, 어긋나면 뜨지 않는다.

## 응답 (`POST /search`)

| 칸 | 뜻 |
|---|---|
| `build_id`·`snapshot_date`·`model` | 이 답이 쓴 데이터 판본과 임베딩 모델 — 되짚기용 |
| `customer_precedents[]` | 고객사(`maker_group` ∈ Hyundai Motor America·Kia) 카드, 합친 순위 상위 100 안에서 최대 5건 |
| `precedents[]` | 그 밖의 회사 카드 상위 10건 |
| 카드: `rank` | 합친 순위(1부터) — 두 구역이 같은 순위를 나눠 쓴다 |
| 카드: `campno`·`maker`·`maker_group`·`received_date`·`components`·`dup_group` | NHTSA 리콜 카드 칸 그대로 |
| 카드: `defect`·`consequence`·`remedy` | 결함·결과·시정 원문 (`source` = NHTSA FLAT_RCL, 스냅샷 날짜) |
| 카드: `cause` | Part 573 원인 칸. `status = filled`면 `text`(원문 그대로)·`speaker`(리콜 제조사)·`source`(캠페인·PDF 파일·sha256·제출일). 그 밖의 `status`: `no_573_report`(보고서 원문 없음, 대부분 2014-08-20 이전) · `cause_empty`·`cause_no_field`(칸이 비었거나 없음) · `version_unresolved`(최신 판본을 정하지 못함 — 글을 싣지 않는다) · `verify_failed`(원문 대조 실패 — 글을 뺀다) |

응답의 모든 리콜 번호는 검색 후보 안에 있어야 하고, 원인 글은 원문과 글자 그대로 같아야 한다(`server/rag/verify.py`).

## 검증

- `uv run pytest tests/test_rag_server.py` — DB·모델 없이 도는 테스트 + `TEST_DATABASE_URL`이 있으면 pgvector 왕복 테스트.
- 대리 평가 재현: `uv run --env-file .env python -m server.rag.parity --vectors db` → 749문항 Hit@1·3·5·10 = 0.311·0.411·0.462·0.542 (보고서 v2와 같음).

## 아직 없는 것

조사 요약 원인(NHTSA 조사관)·추정 표현 표시·확인 항목 틀(계획 PR 2), 부품 범위 좁히기 실험(PR 3), 배포 주소·CORS·호출 상한.

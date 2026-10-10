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
3. 서버용 조회 전용 계정 (배포 전 필수, DEC-042) — 서버는 시작할 때 `data_builds`·`embedding_sets`·`recall_embeddings`를 읽기만 한다.
   적재용 관리자 연결(`DATABASE_URL`, RLS 우회)을 서버에 두지 않도록, Supabase SQL 편집기에서 조회 전용 계정을 만들어 `.env`의
   `SERVER_DATABASE_URL`에 넣는다(비밀번호는 직접 정하고 저장소에 남기지 않는다). 테이블에 RLS가 켜져 있어 SELECT 권한과 함께 정책이 필요하다:
   ```sql
   create role rag_reader login password '<직접 정한 비밀번호>';
   grant usage on schema public to rag_reader;
   grant select on data_builds, embedding_sets, recall_embeddings to rag_reader;
   create policy rag_reader_select on data_builds       for select to rag_reader using (true);
   create policy rag_reader_select on embedding_sets    for select to rag_reader using (true);
   create policy rag_reader_select on recall_embeddings for select to rag_reader using (true);
   ```
   일회용 `pgvector/pgvector:pg17`에서 확인: 이 계정으로 서버 시작 성공, 삭제·추가·다른 테이블 조회는 권한 오류(2026-10-10). Supabase 풀러 주소를 쓰면
   사용자 이름이 `rag_reader.<프로젝트 ref>` 형식이 된다. `SERVER_DATABASE_URL`이 없으면 서버는 `DATABASE_URL`로 읽고 경고한다(로컬 개발용).
4. 서버:
   ```bash
   uv run --env-file .env uvicorn server.api:app --port 8000
   curl localhost:8000/health
   curl -X POST localhost:8000/search -H 'content-type: application/json' -d '{"question":"airbag inflator rupture"}'
   ```
   시작할 때 build 파일(적재와 같은 검사)·DB에 적재된 원인 명세(실패 사유 포함)·DB 벡터 기록·카드 16장 재임베딩을 대조하고, 어긋나면 뜨지 않는다.

## 응답 (`POST /search`)

| 칸 | 뜻 |
|---|---|
| `build_id`·`snapshot_date`·`model` | 이 답이 쓴 데이터 판본과 임베딩 모델 — 되짚기용 |
| `customer_precedents[]` | 고객사(`maker_group` ∈ Hyundai Motor America·Kia) 카드, 합친 순위 상위 100 안에서 최대 5건 |
| `precedents[]` | 그 밖의 회사 카드 상위 10건 |
| 카드: `rank` | 합친 순위(1부터) — 두 구역이 같은 순위를 나눠 쓴다 |
| 카드: `campno`·`maker`·`maker_group`·`received_date`·`components`·`dup_group` | NHTSA 리콜 카드 칸 그대로 |
| 카드: `defect`·`consequence`·`remedy` | 결함·결과·시정 원문 (`source` = NHTSA FLAT_RCL, 스냅샷 날짜) |
| 카드: `cause` | Part 573 원인 칸. `status = filled`면 `text`(원문 그대로)·`speaker`(리콜 제조사)·`source`(캠페인·PDF 파일·sha256·제출일)가 반드시 있다. 그 밖의 `status`에는 글이 없다: `no_573_report`(573 원문 수집 범위 밖 — 접수일 2014-08-20 이전) · `report_status_unknown`(범위 안인데 원문 목록에도 읽기 실패 목록에도 없음 — 이유 미확인, 현재 build 274장) · `report_unreadable`(보고서는 있지만 읽지 못함 — `reason`에 사유, 현재 build 18개 캠페인) · `cause_empty`·`cause_no_field`(칸이 비었거나 없음) · `version_unresolved`(최신 판본을 정하지 못함) · `verify_failed`(원문 대조 실패 — 글을 뺀다) |

응답은 Pydantic 모델(`server/api.py`의 `SearchResponse`)로 검사한다 — 모델에 없는 칸(판정 칸 포함)이나 말한 주체·출처가 빠진 원인 글은 내보내지 않고 서버 오류로 끝난다. 응답의 모든 리콜 번호는 검색 후보 안에 있어야 하고, 원인 글은 원문과 글자 그대로 같아야 한다(`server/rag/verify.py`). 지금은 카드와 원인 글을 검색 결과·원문에서 그대로 꺼내므로 구조상 항상 통과하는 방어선이다 — 조사 요약 원인처럼 고른 문장이 들어오는 다음 PR부터 실제로 걸러낸다.

질문은 영어 단어가 하나 이상 있어야 한다(색인·모델이 영어 — 기획 1절). 공백뿐이거나 영어 단어가 없으면 422로 돌려보낸다.

## 검증

- `uv run pytest tests/test_rag_server.py` — DB·모델 없이 도는 테스트 + `TEST_DATABASE_URL`이 있으면 pgvector 왕복 테스트.
- 대리 평가 재현: `uv run --env-file .env python -m server.rag.parity --vectors db` → 749문항 Hit@1·3·5·10 = 0.311·0.411·0.462·0.542 (보고서 v2와 3자리 점수가 같음 — 입력 sha256이 보고서와 다르거나 점수가 다르면 종료 코드 1). 화면 구성(고객사 최대 5건 + 그 밖 10건)에 정답 리콜이 하나라도 보이는 비율은 0.543(`shown_any`, 보고서에 없는 새 값 — 최대 15건을 보여 주므로 상위 10과 같은 조건이 아니다).
- 서버는 질문마다, 연구 코드는 749문항을 한 번에 곱해서 유사도 값이 같은(동점) 카드의 순서가 다를 수 있다. 그래서 "같은 계산"의 보장은 동점 없는 벡터 단위 테스트 + 실제 데이터 3자리 점수 재현이다.

## 아직 없는 것

조사 요약 원인(NHTSA 조사관)·추정 표현 표시·확인 항목 틀(계획 PR 2), 부품 범위 좁히기 실험(PR 3), 배포 주소·CORS·호출 상한.

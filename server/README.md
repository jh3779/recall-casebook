# server — 결함 선례 찾기 API 서버

질문(영어)을 받아 같은 부품의 리콜 선례와 원인 서술을 **원문 그대로** 돌려준다. 판정하지 않는다(AGENTS.md 2절).
결정 근거: DEC-038(API 서버)·DEC-039(검색 방식)·DEC-042(벡터 보관·고객사 선례)·DEC-044(조사 요약 원인·표시 꼬리표·확인 항목·벡터 로컬 사본).

## 띄우기

1. 로컬 build 파일이 있어야 한다: `data/processed/defect/`의 `build.json`·`recalls.jsonl`·`eval.jsonl`·`causes.jsonl`·`causes.manifest.json`
   (`scripts/defect_precedent/README.md` — 팀 드라이브 사본 또는 `nhtsa build`·`rclrpt all`). 조사 요약을 붙이려면 같은 날 받은 원본
   `data/raw/nhtsa/manifest.json`·`FLAT_INV.zip`도 있어야 한다 — `manifest.json`의 sha256이 build의 `raw_manifest_sha256`과 같아야 서버가 뜬다.
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
   사용자 이름이 `rag_reader.<프로젝트 ref>` 형식이 된다. 이 SQL은 `tests/test_rag_server.py`의 pg 테스트가 그대로 실행해 조회 성공·쓰기 거부를 확인한다.
   **서버에는 관리자 연결을 두지 않는다** — `SERVER_DATABASE_URL`만 든 서버 전용 파일 `.env.server`(gitignore됨)로 띄운다.
   `SERVER_DATABASE_URL`이 없으면 서버는 시작하지 않는다. 계정을 만들기 전 로컬 개발에서만 `ALLOW_ADMIN_DB_FOR_SERVER=1`을 붙여 `.env`의 관리자 연결로 읽을 수 있다(경고를 남긴다).
4. 서버:
   ```bash
   uv run --env-file .env.server uvicorn server.api:app --port 8000
   # 조회 전용 계정을 만들기 전, 로컬 개발에서만:
   ALLOW_ADMIN_DB_FOR_SERVER=1 uv run --env-file .env uvicorn server.api:app --port 8000
   curl localhost:8000/health
   curl -X POST localhost:8000/search -H 'content-type: application/json' -d '{"question":"airbag inflator rupture"}'
   ```
   시작할 때 build 파일(적재와 같은 검사)·DB에 적재된 원인 명세(실패 사유 포함)·DB 벡터 기록·카드 16장 재임베딩·조사 원본 해시를 대조하고, 어긋나면 뜨지 않는다.
   카드 벡터는 정본이 DB이고, 처음 뜰 때 받아 `data/processed/defect/vector_cache/`(gitignore)에 사본을 둔다. 다음부터는 옆에 둔 sha256이 사본과 같고, DB 기록이 맞고,
   DB에서 고르게 뽑은 64줄(마지막 줄 포함)이 사본과 글자 그대로 같을 때만 사본을 쓴다(아니거나 사본이 깨졌으면 다시 받는다). 운영 Supabase 기준 처음 18~100초,
   사본이 있으면 약 8~10초(2026-10-10, 집 회선 실측 — 벡터 46MB를 약 1.8MB/s로 받는다).

## 응답 (`POST /search`)

| 칸 | 뜻 |
|---|---|
| `build_id`·`snapshot_date`·`model` | 이 답이 쓴 데이터 판본과 임베딩 모델 — 되짚기용 |
| `customer_precedents[]` | 고객사(`maker_group` ∈ Hyundai Motor America·Kia) 카드, 합친 순위 상위 100 안에서 최대 5건 |
| `precedents[]` | 그 밖의 회사 카드 상위 10건 |
| 카드: `rank` | 합친 순위(1부터) — 두 구역이 같은 순위를 나눠 쓴다 |
| 카드: `campno`·`maker`·`maker_group`·`received_date`·`components`·`dup_group` | NHTSA 리콜 카드 칸 그대로 |
| 카드: `defect`·`consequence`·`remedy` | 결함·결과·시정 원문 (`source` = NHTSA FLAT_RCL, 스냅샷 날짜, `speaker` = "NHTSA 리콜 기록 요약(FLAT_RCL 결함·결과·시정 칸) — 원본에 작성 주체 표시 없음" 고정 문구 — 작성 주체를 짐작하지 않는다, DEC-047 ③) |
| 카드: `cause` | Part 573 원인 칸. `status = filled`(원인 글) 또는 `stated_unknown`(원인 칸 글이 "NR"·"Still being investigated"·"unknown"처럼 미보고·조사 중 표현으로 **시작**하거나 "NR - Not Reported"·"has not reported the cause"를 포함한다 — DEC-047. 뒤에 원인이 이어지는 글도 있다(예: 26V219 "UNCLEAR WORK INSTRUCTION…", 15V158 "unknown -- axles were received…") — 화면은 "원인을 모른다"로 단정하지 말고 원문을 보여 준다)이면 `text`(원문)·`speaker`(리콜 제조사)·`source`(캠페인·PDF 파일·sha256·제출일·`text_basis`)가 반드시 있다. `text_basis` = 이 build의 원인 파일을 만든 판독 규칙이 기록한 정리 방식(원인 명세 `causes.manifest.json`의 값 — 현재 `rclrpt-2026-10-12b; pdftotext-layout; page-header-footer-removed; whitespace-collapsed`: PDF 글자 추출, 쪽 경계(form feed) 바로 뒤의 머리말·머리말만 있는 줄·49 CFR 꼬리말·줄 전체 쪽 표시 제거, 공백 정리. 일반 본문에 인용된 보고서 제목은 자기 번호든 다른 번호든 남긴다. 기록이 없는 원인 파일이면 서버가 시작하지 않는다). 그 밖의 `status`에는 글이 없다: `no_573_report`(573 원문 수집 범위 밖 — 접수일 2014-08-20 이전) · `report_status_unknown`(범위 안인데 원문 목록에도 읽기 실패 목록에도 없음 — 이유 미확인, 현재 build 274장) · `report_unreadable`(보고서는 있지만 읽지 못함 — `reason`에 사유, 현재 build 18개 캠페인) · `cause_empty`·`cause_no_field`(칸이 진짜 비었거나 없음 — 미보고·조사 중 서술은 `stated_unknown`) · `version_unresolved`(최신 판본을 정하지 못함) · `verify_failed`(원문 대조 실패 — 글을 뺀다) |
| 카드: `cause.flags` | `filled`·`stated_unknown` 573 원인 글의 표시 꼬리표 — 판정이 아니라 글에 그 표현이 있다는 사실. `unknown_expression`(원인 미확인 표현 있음 — `cause_trials.UNKNOWN_RE`)·`hedge_expression`(추정 표현 있음 — `appear(s/ed) to`·`might`·`possibly`·`likely`·`probably`·`suspect(ed)`·`believe(d)`, 2026-10-10 고정, `may`·`could`는 결과 설명에 흔해 뺐다). `spans`는 원문의 시작·끝·글자. 조사 요약에는 붙이지 않는다(규칙이 573 원인 칸으로만 검증됨) |
| 카드: `investigations[]` | 이 리콜에 연결된 NHTSA 결함 조사 요약(`FLAT_INV`, 요약이 있는 것만). `action`(조사 번호)·`speaker`(NHTSA 결함 조사 — 조사관 요약)·`subject`·`summary`(원문 그대로)·`open_date`·`close_date`(원본 칸 그대로, 비어 있으면 빈 문자열). **색인에는 넣지 않는다**(시험 질문 출처라 누수). 조사 기록의 리콜 번호가 9자리로 카드와 같을 때만 잇는다 — 6자리(캠페인 번호)로 적힌 기록은 어느 카드인지 짐작해야 해서 잇지 않고, 그 경우 "조사 요약 없음"과 구별되지 않는다. 현재 build: 1,870장에 연결, 917개 조사, 2개 이상 연결된 카드 35장(6자리 기록 72,977줄은 앞 6자리로 보면 284장에 걸림) |
| 카드: `checklist[]` | 확인 항목 고정 틀(LLM 없음) — `same_part`(같은 부품: `components`)·`failure_mode`(고장 양상: 결함 원문 `defect` + 결과 원문 `consequence`, 칸 이름으로 구분)·`remedy`(시정 원문)·`supplier`(573 `supplier_names`, 판본 미확정 보고서는 제외)·`cause_speaker`(원인을 말한 주체: 573 리콜 제조사 `cause.speaker`, NHTSA 조사 `investigations.speaker` + 원본 조사 번호 `investigations.action`). 항목마다 `evidence[]`(칸 이름·원문 글)가 있고, 근거가 없는 항목은 싣지 않는다. 같은지 다른지는 판단하지 않는다 |

응답은 Pydantic 모델(`server/api.py`의 `SearchResponse`)로 검사한다 — 모델에 없는 칸(판정 칸 포함)이나 말한 주체·출처가 빠진 원인 글은 내보내지 않고 서버 오류로 끝난다. 응답의 모든 리콜 번호는 검색 후보 안에 있어야 하고, 원인 글은 원문과 글자 그대로 같아야 한다(`server/rag/verify.py`). 지금은 카드와 원인 글을 검색 결과·원문에서 그대로 꺼내므로 구조상 항상 통과하는 방어선이다. 조사 요약은 시작 때 읽은 조사 기록과 같은 글인지(원본 zip은 시작 때 sha256 대조), 573 원인 글의 꼬리표 구간은 그 글의 같은 위치·같은 글자인지도 본다 — 어긋나면 응답을 내보내지 않는다(원문을 옮기는 경로라 어긋나면 코드 결함).

질문은 영어 단어가 하나 이상 있어야 한다(색인·모델이 영어 — 기획 1절). 공백뿐이거나 영어 단어가 없으면 422로 돌려보낸다.

## 검증

- `uv run pytest tests/test_rag_server.py` — DB·모델 없이 도는 테스트 + `TEST_DATABASE_URL`이 있으면 pgvector 왕복 테스트.
- 대리 평가 재현: `uv run --env-file .env python -m server.rag.parity --vectors db` → 749문항 Hit@1·3·5·10 = 0.311·0.411·0.462·0.542 (보고서 v2와 3자리 점수가 같음 — 입력 sha256이 보고서와 다르거나 점수가 다르면 종료 코드 1). 화면 구성(고객사 최대 5건 + 그 밖 10건)에 정답 리콜이 하나라도 보이는 비율은 0.543(`shown_any`, 보고서에 없는 새 값 — 최대 15건을 보여 주므로 상위 10과 같은 조건이 아니다).
- 카드 전체 점검: `uv run python -m server.rag.parity --stats`(벡터·DB 불필요) — 전체 카드를 응답과 같은 경로(카드 → 원문 대조 → 확인 항목 → 응답 모델)로 만들어 모델 통과 수·원인 상태 분포·꼬리표 수(상태별)·조사 연결 수를 낸다. build `f1fe1843ed0f2c66`: 30,350장 모두 통과, 조사 연결 1,870장·917건·2건 이상 35장, 꼬리표 `filled` 226·541(DEC-044 수치와 같음) + `stated_unknown` 75·1(DEC-047 뒤 새로 생김).
- 서버와 연구 스크립트가 함께 쓰는 판별 규칙(원인 미확인 표현 `UNKNOWN_RE`, 원문 대조 `check`, 조사 요약 자리표시)은 `scripts/defect_precedent/rules.py` 한 곳에 둔다 — 실험을 고치다 서버 동작이 말없이 바뀌지 않게. `tests/test_rules.py`가 정규식을 글자 그대로 고정한다.
- 서버는 질문마다, 연구 코드는 749문항을 한 번에 곱해서 유사도 값이 같은(동점) 카드의 순서가 다를 수 있다. 그래서 "같은 계산"의 보장은 동점 없는 벡터 단위 테스트 + 실제 데이터 3자리 점수 재현이다.

## 아직 없는 것

부품 범위 좁히기 실험(계획 PR 3), 배포 주소·CORS·호출 상한(#63), 화면 문구(박성호 님, PR #60). 생산 기간 확인 항목은 카드에 연식·생산일 칸이 없어 뺐다.

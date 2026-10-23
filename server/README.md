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
3. 서버용 조회 전용 계정 (배포 전 필수, DEC-042) — 서버는 시작할 때 `data_builds`·`embedding_sets`·`recall_embeddings`·`serving_bundles`(배포 경로의 묶음 기록, DEC-049)를 읽기만 한다. `serving_bundles`는 `python -m server.rag.bundle schema`로 먼저 만든다.
   적재용 관리자 연결(`DATABASE_URL`, RLS 우회)을 서버에 두지 않도록, Supabase SQL 편집기에서 조회 전용 계정을 만들어 `.env`의
   `SERVER_DATABASE_URL`에 넣는다(비밀번호는 직접 정하고 저장소에 남기지 않는다). 테이블에 RLS가 켜져 있어 SELECT 권한과 함께 정책이 필요하다:
   ```sql
   create role rag_reader login password '<직접 정한 비밀번호>';
   grant usage on schema public to rag_reader;
   grant select on data_builds, embedding_sets, recall_embeddings, serving_bundles to rag_reader;
   create policy rag_reader_select on data_builds       for select to rag_reader using (true);
   create policy rag_reader_select on embedding_sets    for select to rag_reader using (true);
   create policy rag_reader_select on recall_embeddings for select to rag_reader using (true);
   create policy rag_reader_select on serving_bundles   for select to rag_reader using (true);
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

`POST /search`는 IP당 1분 60회(`RATE_LIMIT_PER_MINUTE`)를 넘으면 429와 `Retry-After`를 낸다 — `server/ratelimit.py`, 시험 `tests/test_rate_limit.py`, 배포 쪽 WAF 안전망은 `docs/guides/배포_Vercel.md` 3-2절(이슈 #63, DEC-057).

요청은 `{"question": "<영어 결함 설명>"}` 하나만 받는다 — 모르는 칸이 있거나(예: `top_k`) 영어 단어가 없으면 422로 거부한다(2026-10-12, PR #86).

## 서빙 묶음 (배포용, DEC-049)

배포 환경(Vercel)에는 로컬 build 파일이 없으므로, 로컬에서 위 1·2단계 검사를 통과한 build를 파일 하나(`serving_<build_id>.tar`)로 묶어 Supabase Storage에 올린다. 묶음에는 카드(`recalls.jsonl` 순서 그대로)·원인 행(`text_basis` 포함)·실패 사유·원인 명세·카드에 연결된 조사 요약·벡터(정규화 전)·임베딩 모델 파일이 들어 있고, `meta.json`에 파일별 sha256과 카드 글 해시가 있다. 같은 입력이면 바이트까지 같다.

```bash
uv run --env-file .env python -m server.rag.bundle schema   # serving_bundles 테이블(embeddings.sql 뒤에)
uv run --env-file .env python -m server.rag.bundle build    # data/processed/defect/serving/serving_<build_id>.tar
uv run --env-file .env python -m server.rag.bundle upload   # Storage 버킷 serving-bundles/<build_id>/<sha256>.tar + serving_bundles 기록
uv run --env-file .env python -m server.rag.bundle verify   # 공개 주소에서 받아 기록 sha256과 대조하고 되살려 본다
```

- **Supabase Free 플랜은 파일 하나가 최대 50MB**(Pro 이상 500GB, 공식 문서 Storage › Limits) — 묶음(155.4MB)은 Free 플랜에서 올라가지 않는다. 우리 프로젝트는 Pro(사용자 답 2026-10-12) — 대시보드 Storage 설정의 **Global file size limit**를 묶음 크기(약 160MB) 이상으로 올린 뒤 `upload`를 실행한다.
- 버킷 `serving-bundles`는 **공개 읽기**로 만든다(Supabase 대시보드 — 사용자 계정 작업). 들어 있는 것은 공개 NHTSA 자료에서 만든 값이고, 무결성은 DB `serving_bundles.bundle_sha256` 대조로 지킨다. 쓰기는 로컬의 `SUPABASE_SERVICE_ROLE_KEY`로만 한다.
- 묶음을 여는 함수 `load_bundle`은 기록된 sha256을 인자로 받아 먼저 대조하고, tar 항목 이름·종류(일반 파일, `model/` 아래 상대 경로만), 필수 파일, 형식 판본, 파일별 해시, 카드 글 해시, 벡터 모양을 본다. `upload`는 로컬 묶음이 이 build와 같은지 본 뒤 올리고, 공개 주소의 실제 파일을 받아 sha256·build를 대조한 다음에만 DB에 기록한다. `SUPABASE_URL`이 `https://`가 아니면 멈춘다.
- `serving_bundles` 기록은 (build, 모델, 묶음 형식 판본)마다 하나이고 한 번 쓰면 바꾸지 않는다 — 같은 조합의 다른 묶음을 올리려 하면 멈춘다. 묶음 형식(`bundle.py` `FORMAT`)을 바꾸면 새 기록이 된다. 같은 조합의 묶음을 고쳐 다시 만들어야 하면 `FORMAT`을 올린다 — 기록 행을 손으로 지우지 않는다.
- 실측(2026-10-12, build `f1fe1843ed0f2c66`): 묶음 155.4MB(그중 모델 약 67MB·벡터 약 47MB), 만들기 13초, 되살리기 0.2초 — 되살린 build는 로컬 `load_build()` 결과와 같다.

### 서버를 묶음에서 띄우기 (`RAG_SOURCE=bundle`, DEC-050)

```bash
RAG_SOURCE=bundle SERVING_BUILD_ID=<build_id> SUPABASE_URL=<프로젝트 주소> \
  uv run --env-file .env.server uvicorn server.api:app --port 8000
```

- `RAG_SOURCE`가 없거나 비어 있거나 `local`이면 지금까지처럼 로컬 build 파일로 뜬다(시연). `bundle`이면 로컬 데이터 파일을 읽지 않는다. 그 밖의 값이면 시작하지 않는다.
- 시작 순서: fastembed 판본 → DB `serving_bundles`에서 (build, 모델, 묶음 형식) 기록 → 공개 주소에서 `/tmp/serving/<sha256>.tar`로 받기(이미 있으면 다시 받지 않음) → 기록 sha256과 대조(다르면 파일을 지우고 멈춤) → `meta.json` 파일별 해시·카드 글 해시 → 묶음의 build·모델·fastembed 판본이 지금 서버와 같은지 → DB 원인 명세(`check_against_db`) → DB 벡터 기록(`check_set`) → DB에서 뽑은 64줄+마지막 줄이 묶음 벡터와 글자 그대로 같은지 → 묶음 안 모델 파일로 모델 열기(`specific_model_path`) → 탐침 16장. 하나라도 어긋나면 서버를 띄우지 않는다.
- `SERVING_BUILD_ID`·`SUPABASE_URL`이 없으면 시작하지 않는다 — 어느 build로 띄울지 짐작하지 않는다. 관리자 키는 필요 없다(공개 읽기 버킷 + 조회 전용 계정).
- `/health`와 `/search` 응답의 `bundle_sha256`에 쓴 묶음의 sha256이 실린다(로컬 경로는 `null`).
- 실측(2026-10-12, build `f1fe1843ed0f2c66`, Storage 대신 로컬 묶음 파일·운영 DB 조회): 시작 6.7초(로컬 경로 9.3초), 최대 RSS 1.07GB(로컬 경로 1.43GB, macOS), 749문항 `parity --vectors bundle` = 0.311·0.411·0.462·0.542·shown_any 0.543(로컬 경로와 같음), 질문 40개의 `/search` 응답이 `bundle_sha256` 칸을 빼고 로컬 경로와 글자 그대로 같음.
- CORS 허용 주소는 환경변수 `ALLOWED_ORIGINS`(쉼표로 구분)로 바꾼다. 없으면 `http://localhost:5173`.

## 응답 (`POST /search`)

| 칸 | 뜻 |
|---|---|
| `build_id`·`snapshot_date`·`model` | 이 답이 쓴 데이터 판본과 임베딩 모델 — 되짚기용 |
| `bundle_sha256` | 서빙 묶음으로 띄운 서버가 쓴 묶음 파일의 sha256(DB `serving_bundles`와 같은 값). 로컬 파일 경로는 `null` |
| `customer_precedents[]` | 고객사(`maker_group` ∈ Hyundai Motor America·Kia) 카드, 합친 순위 상위 100 안에서 최대 5건 |
| `precedents[]` | 그 밖의 회사 카드 상위 10건 |
| 카드: `rank` | 합친 순위(1부터) — 두 구역이 같은 순위를 나눠 쓴다 |
| 카드: `campno`·`maker`·`maker_group`·`received_date`·`components`·`dup_group` | NHTSA 리콜 카드 칸 그대로 |
| 카드: `defect`·`consequence`·`remedy` | 결함·결과·시정 원문 (`source` = NHTSA FLAT_RCL, 스냅샷 날짜, `speaker` = "NHTSA 리콜 기록 요약(FLAT_RCL 결함·결과·시정 칸) — 원본에 작성 주체 표시 없음" 고정 문구 — 작성 주체를 짐작하지 않는다, DEC-047 ③) |
| 카드: `cause` | Part 573 원인 칸. `status = filled`(원인 글) 또는 `stated_unknown`(원인 칸 글이 "NR"·"Still being investigated"·"unknown"처럼 미보고·조사 중 표현으로 **시작**하거나 "NR - Not Reported"·"has not reported the cause"를 포함한다 — DEC-047. 뒤에 원인이 이어지는 글도 있다(예: 26V219 "UNCLEAR WORK INSTRUCTION…", 15V158 "unknown -- axles were received…") — 화면은 "원인을 모른다"로 단정하지 말고 원문을 보여 준다)이면 `text`(원문)·`speaker`(리콜 제조사)·`source`(캠페인·PDF 파일·sha256·제출일·`text_basis`)가 반드시 있다. `text_basis` = 이 build의 원인 파일을 만든 판독 규칙이 기록한 정리 방식(원인 명세 `causes.manifest.json`의 값 — 현재 `rclrpt-2026-10-12b; pdftotext-layout; page-header-footer-removed; whitespace-collapsed`: PDF 글자 추출, 쪽 경계(form feed) 바로 뒤의 머리말·머리말만 있는 줄·49 CFR 꼬리말·줄 전체 쪽 표시 제거, 공백 정리. 일반 본문에 인용된 보고서 제목은 자기 번호든 다른 번호든 남긴다. 기록이 없는 원인 파일이면 서버가 시작하지 않는다). 그 밖의 `status`에는 글이 없다: `no_573_report`(573 원문 수집 범위 밖 — 접수일 2014-08-20 이전) · `report_status_unknown`(범위 안인데 원문 목록에도 읽기 실패 목록에도 없음 — 이유 미확인, 현재 build 274장) · `report_unreadable`(보고서는 있지만 읽지 못함 — `reason`에 사유, 현재 build 18개 캠페인) · `cause_empty`·`cause_no_field`(칸이 진짜 비었거나 없음 — 미보고·조사 중 서술은 `stated_unknown`) · `version_unresolved`(최신 판본을 정하지 못함) · `verify_failed`(원문 대조 실패 — 글을 뺀다) |
| 카드: `cause.flags` | `filled`·`stated_unknown` 573 원인 글의 표시 꼬리표 — 판정이 아니라 글에 그 표현이 있다는 사실. `unknown_expression`(원인 미확인 표현 있음 — `rules.UNKNOWN_RE`)·`hedge_expression`(추정 표현 있음 — `appear(s/ed) to`·`might`·`possibly`·`likely`·`probably`·`suspect(ed)`·`believe(d)`, 2026-10-10 고정, `may`·`could`는 결과 설명에 흔해 뺐다). `spans`는 원문의 시작·끝·글자. 조사 요약에는 붙이지 않는다(규칙이 573 원인 칸으로만 검증됨) |
| 카드: `investigations[]` | 이 리콜에 연결된 NHTSA 결함 조사 요약(`FLAT_INV`, 요약이 있는 것만). `action`(조사 번호)·`speaker`(NHTSA 결함 조사 — 조사관 요약)·`subject`·`summary`(원문 그대로)·`open_date`·`close_date`(원본 칸 그대로, 비어 있으면 빈 문자열). **색인에는 넣지 않는다**(시험 질문 출처라 누수). 조사 기록의 리콜 번호가 9자리로 카드와 같을 때만 잇는다 — 6자리(캠페인 번호)로 적힌 기록은 어느 카드인지 짐작해야 해서 잇지 않고, 그 경우 "조사 요약 없음"과 구별되지 않는다. 현재 build: 1,870장에 연결, 917개 조사, 2개 이상 연결된 카드 35장(6자리 기록 72,977줄은 앞 6자리로 보면 284장에 걸림) |
| 카드: `checklist[]` | 확인 항목 고정 틀(LLM 없음) — `same_part`(같은 부품: `components`)·`production_period`(생산 기간: 573 `Production Dates`를 블록마다 원문 그대로 `머리글 | 원문`으로, 날짜까지 읽힌 블록의 앞 5개 — **이 항목에만** `source`(읽은 보고서 판본 `campaign`·`file`·`pdf_sha256`·`submission_date`, 필수)·`omitted`(한도로 싣지 못한 블록 수)·`unread`(날짜가 적히지 않았거나 읽을 수 없어 뺀 블록 수)가 있고 응답 모델이 `item`으로 나뉘어 다른 항목에는 올 수 없다; 판본 미확정 보고서·573 범위 밖 리콜·읽힌 블록이 없는 보고서는 싣지 않으며 사용자 생산 기간과 겹치는지는 판단하지 않는다, DEC-059)·`failure_mode`(고장 양상: 결함 원문 `defect` + 결과 원문 `consequence`, 칸 이름으로 구분)·`remedy`(시정 원문)·`supplier`(573 `supplier_names`, 판본 미확정 보고서는 제외)·`cause_speaker`(원인을 말한 주체: 573 리콜 제조사 `cause.speaker`, NHTSA 조사 `investigations.speaker` + 원본 조사 번호 `investigations.action`). 항목마다 `evidence[]`(칸 이름·원문 글)가 있고, 근거가 없는 항목은 싣지 않는다. 같은지 다른지는 판단하지 않는다 |

응답은 Pydantic 모델(`server/api.py`의 `SearchResponse`)로 검사한다 — 모델에 없는 칸(판정 칸 포함)이나 말한 주체·출처가 빠진 원인 글은 내보내지 않고 서버 오류로 끝난다. 응답의 모든 리콜 번호는 검색 후보 안에 있어야 하고, 원인 글은 원문과 글자 그대로 같아야 한다(`server/rag/verify.py`). 지금은 카드와 원인 글을 검색 결과·원문에서 그대로 꺼내므로 구조상 항상 통과하는 방어선이다. 조사 요약은 시작 때 읽은 조사 기록과 같은 글인지(원본 zip은 시작 때 sha256 대조), 573 원인 글의 꼬리표 구간은 그 글의 같은 위치·같은 글자인지도 본다 — 어긋나면 응답을 내보내지 않는다(원문을 옮기는 경로라 어긋나면 코드 결함).

질문은 영어 단어가 하나 이상 있어야 한다(색인·모델이 영어 — 기획 1절). 공백뿐이거나 영어 단어가 없으면 422로 돌려보낸다.

## 8D 초안 (`POST /draft`, DEC-065)

8D의 D2(문제 기술)·D4(원인)에 담은 선례의 **원문을 묶어** 보여 준다. LLM은 묶음과 제목을 정할 뿐 문장을 쓰지 않고, 묶음에 넣는 인용은 **그 출처의 전체 원문**을 서버가 그대로 싣는다(LLM이 문장 일부만 짚어도 "may"·"not" 같은 한정어가 빠진 조각은 나가지 않는다 — PR #141 리뷰).

- 요청: `{"question": "...", "campnos": ["24V412000", ...최대 6개], "step": "d2" | "d4"}`. 번호가 **이 질문의 검색 결과 밖**이면 422(밖의 번호는 지어낸 것으로 본다).
- 응답: `groups`(서버 내부용 제목 + 원문 인용 — 화면은 제목을 보이지 않는다: 번호·칸·원문 구간 `start`/`end`(출처 전체라 `0`~원문 길이)·말한 주체·출처), `ungrouped`(묶이지 않은 원문 전체), `questions`(고정 확인 질문), `picked_questions`(D4에서 LLM이 고정 풀 `QUESTION_POOL`(P1~P10)에서 **번호로** 고른 확인 질문 최대 3개 — 문장은 풀의 글자이며 버린 번호는 이유별로 `rejected.unknown_question`(풀 밖·문자열 아님), `rejected.duplicate_question`(이미 고른 번호 반복), `rejected.over_limit_question`(상한 3개를 넘은 유효한 번호)으로 센다. D2·꺼짐·실패는 빈 목록, DEC-071), `rejected`(원문과 다르다고 버린 인용 수와 버린 질문 번호 수), `degraded`.
- **기본은 꺼짐**: `DRAFT_ENABLED=1`과 `OPENAI_API_KEY`가 있어야 켜진다(키 없이 켜면 시작하지 않는다). 꺼져 있거나 LLM 호출이 실패하면 `degraded`(`disabled`·`llm_failed`)와 함께 묶음 없이 원문 목록(`ungrouped`)만 준다.
- LLM: 기본 `gpt-6-luna`·추론 `none`(`DRAFT_MODEL`·`DRAFT_REASONING_EFFORT`), OpenAI Responses API를 표준 라이브러리로 부른다(`store: false`, 구조화 출력). 입력은 공개 선례 원문뿐이다. 키는 응답·오류에 싣지 않는다.
- 호출 상한: IP당 1분 6회(`DRAFT_RATE_LIMIT_PER_MINUTE`, `/search` 상한과 따로 센다). 넘으면 429 + `Retry-After`.
- 표본 관찰 스크립트: `uv run --env-file .env python -m scripts.defect_precedent.draft_sample --dry-run` — 기록은 `docs/experiments/실험_8D초안표본.md`.

## 검증

- `uv run pytest tests/test_rag_server.py` — DB·모델 없이 도는 테스트 + `TEST_DATABASE_URL`이 있으면 pgvector 왕복 테스트.
- 대리 평가 재현: `uv run --env-file .env python -m server.rag.parity --vectors db` → 749문항 Hit@1·3·5·10 = 0.311·0.411·0.462·0.542 (보고서 v2와 3자리 점수가 같음 — 입력 sha256이 보고서와 다르거나 점수가 다르면 종료 코드 1). 화면 구성(고객사 최대 5건 + 그 밖 10건)에 정답 리콜이 하나라도 보이는 비율은 0.543(`shown_any`, 보고서에 없는 새 값 — 최대 15건을 보여 주므로 상위 10과 같은 조건이 아니다).
- 배포 경로 재현: `uv run --env-file .env python -m server.rag.parity --vectors bundle --bundle data/processed/defect/serving/serving_<build_id>.tar` — 묶음의 카드·벡터·모델 파일로 같은 점수가 나와야 한다(묶음 build가 로컬 build와 같아야 실행된다).
- 카드 전체 점검: `uv run python -m server.rag.parity --stats`(벡터·DB 불필요) — 전체 카드를 응답과 같은 경로(카드 → 원문 대조 → 확인 항목 → 응답 모델)로 만들어 모델 통과 수·원인 상태 분포·꼬리표 수(상태별)·조사 연결 수를 낸다. build `f1fe1843ed0f2c66`: 30,350장 모두 통과, 조사 연결 1,870장·917건·2건 이상 35장, 꼬리표 `filled` 226·541(DEC-044 수치와 같음) + `stated_unknown` 75·1(DEC-047 뒤 새로 생김).
- 서버와 연구 스크립트가 함께 쓰는 판별 규칙(원인 미확인 표현 `UNKNOWN_RE`, 원문 대조 `check`, 조사 요약 자리표시)은 `scripts/defect_precedent/rules.py` 한 곳에 둔다 — 실험을 고치다 서버 동작이 말없이 바뀌지 않게. `tests/test_rules.py`가 정규식을 글자 그대로 고정한다.
- 서버는 질문마다, 연구 코드는 749문항을 한 번에 곱해서 유사도 값이 같은(동점) 카드의 순서가 다를 수 있다. 그래서 "같은 계산"의 보장은 동점 없는 벡터 단위 테스트 + 실제 데이터 3자리 점수 재현이다.

## 아직 없는 것

배포 화면 주소의 CORS 값(작업 F — 허용 주소는 `ALLOWED_ORIGINS`로 바꿀 수 있다), 화면의 429 처리(작업 F), 화면 문구(박성호 님, PR #60). 부품 범위 좁히기는 시험 뒤 기각했다(DEC-045).

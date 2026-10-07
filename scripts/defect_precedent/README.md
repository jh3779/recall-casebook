# 결함 선례 데이터·시험지 스크립트

결함 선례 찾기 도우미(현행 팀 주제, DEC-030, 기획 `docs/기획_결함선례.md`)의 데이터·시험지·기준 점수를 만드는 스크립트다.
원본과 결과물은 커밋하지 않는다 (`data/raw/`, `data/processed/`는 `.gitignore`). 기준 실행을 고정하는 작은 파일(`baseline_2026-10-06.json` — 원본·카드·시험지·573 판본의 sha256)만 커밋한다.

> **재현 범위**: 2026-10-06 기준 점수(0.510)와 573 표본(205/95)은 **그날의 원본 사본이 있을 때만** 같은 값으로 다시 만들 수 있다. NHTSA는 같은 주소에 매일 새 파일을 덮어쓰고 옛 파일을 주지 않으며, 원본은 저장소에 커밋하지 않는다(AGENTS.md 7절). 지금 사본은 작업자 로컬(`data/raw/nhtsa/`, `data/raw/rclrpt/`)에만 있다 — **팀 공용 보관 위치는 아직 정하지 않았다**(후속). 사본이 없으면 `fetch`로 받은 새 원본에서 `--allow-drift`로 같은 질문 번호만 "재평가"할 수 있고, 그 값은 기준 점수와 다를 수 있다.

## 실행 순서

```bash
uv run python -m scripts.defect_precedent.nhtsa fetch          # NHTSA 원본 zip 받기 (약 27MB) + manifest.json
uv run python -m scripts.defect_precedent.nhtsa build          # recalls.jsonl · eval.jsonl (약 2초, 원본 sha256 검증 후)
uv run python -m scripts.defect_precedent.bm25_baseline        # 기준 점수 Hit@1·3·5·10 (약 1분)
uv run python -m scripts.defect_precedent.rclrpt sample 300    # 원본 보고서(Part 573) 무작위 표본 판독 (pdftotext 필요)
```

**기준 실행을 다시 잴 때**는 기준 파일을 넘긴다.

- `bm25_baseline --baseline`: 원본 manifest·`recalls.jsonl`·`eval.jsonl`의 sha256이 기준 파일과 모두 같을 때만 "재현"으로 실행하고, 다르면 중단한다. 같은 원본 사본이 없어 현재 데이터로 같은 질문 번호만 다시 재려면 `--allow-drift`를 붙인다 — 출력에 "재평가 (재현 아님)"으로 표시된다.
- `rclrpt sample --baseline`: 현재 목록을 다시 조회하지 않고 기준 파일에 적힌 **당시 판본 목록(582개)**만 받아 각 PDF의 sha256을 확인한 뒤 판독한다. 해시가 다르면 그 리콜은 실패 목록으로 간다.

```bash
uv run python -m scripts.defect_precedent.bm25_baseline --baseline scripts/defect_precedent/baseline_2026-10-06.json
uv run python -m scripts.defect_precedent.rclrpt sample --baseline scripts/defect_precedent/baseline_2026-10-06.json
```

- 새 기준을 만들 때: `uv run python -m scripts.defect_precedent.nhtsa freeze scripts/defect_precedent/baseline_<날짜>.json` (원본과 다른 날 만든 eval이면 중단한다)
- `fetch`는 옛 원본을 지우지 않고 `data/raw/nhtsa.<받은 시각>`으로 보관한다.
- NHTSA 원본 URL은 매일 덮어써져서 옛 스냅샷을 다시 받을 수 없다. 원본은 커밋하지 않으므로 **같은 원본 사본(`data/raw/nhtsa` 또는 fetch가 보관한 `data/raw/nhtsa.<받은 시각>`)을 지우지 않는다** — 다른 사람은 사본을 넘겨받아야 재현할 수 있다.
- `rclrpt all`(약 1.2만 건, 수 시간)은 팀 확인 후에 돌린다.
- 원본 줄의 칸 수가 명세와 다르면 `build`가 그 줄 번호를 보여 주고 중단한다 (값이 옆 칸으로 밀렸을 수 있어 추측해 맞추지 않는다).

## 만들어지는 파일 (`data/processed/defect/`)

| 파일 | 한 줄 = | 칸 |
|---|---|---|
| `recalls.jsonl` | 리콜 카드 1건 | `campno, maker, raw_maker, components[], defect, consequence, remedy, received_date, recall_type, influenced_by, dup_group, snapshot_date` |
| `eval.jsonl` | 시험 질문 1개 (조사 1건) | `action_no, question, open_date, gold_campnos[], set[]` (`all` · `since2010` · `rclrpt_range`) |
| `causes_sample.jsonl` / `causes.jsonl` | 원본 보고서 1건 (최신 판본) | `campaign, versions, source_file, submission_date, cause_text, cause_status(filled/empty/no_field), supplier_names[], supplier_countries[], new_form, pdfs{판본: sha256}, resolution(auto/manual/unresolved), unresolved_reasons[]` |
| `causes_*_failures.jsonl` | 읽지 못한 리콜 1건 | `campaign, keys[], error` (받기·변환 실패, 기준 sha256 불일치 — "원인 칸 없음"과 구분) |
| `build.json` | build 1회 | `raw_manifest_sha256, recalls_sha256, eval_sha256, snapshot_date` — 카드·시험지가 어떤 원본에서 나왔는지. build는 이 셋을 한 폴더에 만든 뒤 폴더째 교체한다 |

- `maker`는 회사명 대응표가 생기기 전까지 `raw_maker`와 같다.
- `dup_group`이 같은 리콜은 결함 설명 본문이 같다 (약어를 고려해 자른 첫 문장 = 회사·차종 나열을 뺀 본문이 60자 넘게 같음). **서로 다른 회사가 같은 공급사 부품 설명을 그대로 쓴 경우도 여기 묶인다** (예: Gillig·Cummins 구동계, Unicell·Mickey Truck의 ASA 모니터). 검색에서 묶음당 1건만 보여 주면 "다른 회사의 같은 부품 선례"가 숨겨질 수 있으니, 묶음의 회사 목록은 함께 보여 준다.
- `set`의 `rclrpt_range`는 **첫 번째 정답 리콜**의 접수일이 2014-08-20 이후인 질문이다 (정답 중 하나라도 기준이면 94개).
- `campaign`은 리콜 번호 앞 6자리(예: `24V412`)다. `recalls.jsonl`의 `campno`(예: `24V412000`) 앞 6자리와 잇는다.
- 원본 보고서 판독: 수정본 중 `Submission Date`가 가장 늦은 판본을 쓴다(날짜 형식 `JUN 05, 2024` · `NOV 18,2014` · `Sep 14, 2015`를 모두 읽음). 날짜를 모르는 판본(글자 없는 이미지, 제출일 미판독)이 하나라도 있으면 최신판을 짐작하지 않고 `resolution = "unresolved"`로 두어 원인 칸 통계에서 뺀다. 사람이 이미지 판본을 열어 확인한 제출일은 `manual_submission_dates.json`(PDF 주소 → 제출일·sha256·확인 기록)에 적고, PDF sha256이 같을 때만 쓴다 (`resolution = "manual"`). 원인 칸 중간에 끼는 쪽 꼬리말("The information contained in this report…", "Page 3 of 5")은 지운다.

## 기준값 (2026-10-06, `baseline_2026-10-06.json`)

| 항목 | 값 |
|---|---|
| 리콜 줄 → 카드 | 327,429 → 30,350 |
| 결함 조사 / 시험 질문 | 5,349 / 749 (2010년 이후 214, 573 범위 91) |
| 질문 길이 | 중앙값 182자, 400자 초과 34개, 35자 미만 10개 |
| 본문이 같은 리콜 | 6,404 |
| BM25 Hit@10 (전체 749) | **0.510** (주 지표: 연결 리콜 중 하나라도) / 0.503 (첫 번째 연결 리콜만) |
| BM25 Hit@10 (2010년 이후 214 / 573 범위 91) | 0.706 / 0.736 |
| 573 표본 300건 원인 칸 | 채워짐 205 (68.3%) · 비어 있음 95 · 미확정 0 · 읽지 못함 0 (25V063은 이미지 판본 제출일을 사람이 확인 — `manual`) |
| PDF 텍스트 변환 | poppler `pdftotext` 26.08.0 (`-layout`) — 다른 버전이면 판독 결과가 달라질 수 있다 |

- 이 점수는 **대리 평가**다 — 정답 리콜의 99.6%가 조사 시작 뒤 접수라 "과거 선례 찾기"는 재지 못한다.
- 알려진 한계: 시험 질문 중 내용이 없는 문구가 몇 개 남아 있다 (예: `A`, `DD`, `SEE ATTACHED SUMMARY.`, `See attached closing resume summary.` — 35자 미만 10개 중 다수). 749개 정의를 유지하려고 걸러내지 않았다.
- 문장 자르기는 `WWW.NHTSA.GOV` 같은 대문자 도메인 표기에서 잘못 자를 수 있다. 현재 749개 질문에는 해당 사례가 없다.
- 후속 (PR #25 리뷰에서 나옴, 기준을 새로 만들 때 처리):
  - `freeze`는 `causes_sample*.jsonl`이 이번 build와 같은 입력·시드에서 나왔는지 확인하지 않는다 → `causes_sample`에 build 해시와 시드를 함께 적고 freeze에서 대조한다.
  - `rclrpt sample --baseline`은 일반 `sample`과 같은 파일명에 덮어쓰고, 고른 판본(`selected`)·기대값(`expected`)을 자동 비교하지 않는다. 실패 행은 `pdfs`가 비어 저장되어, 실패가 있는 표본으로 기준을 만들면 그 리콜의 판본 해시가 고정되지 않는다 (2026-10-06 기준은 실패 0건).
  - `rclrpt all`용 재시도·이어받기가 없다.
  - 기준 원본(NHTSA zip·명세·573 PDF)의 팀 공용 보관 위치와 받는 절차를 정한다 (위 "재현 범위").

## DB 적재 (Supabase, DEC-034)

```bash
uv run python -m scripts.defect_precedent.load_db check --causes sample --expect-rows 300  # DB 없이 파일만 검증 (해시·날짜·정답 리콜·캠페인 연결·원인 파일 줄 수)
uv run --env-file .env python -m scripts.defect_precedent.load_db schema                  # schema.sql 적용 (여러 번 해도 됨)
uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes sample --expect-rows 300  # 스냅샷 1개 적재 + 건수 대조 + 직전 스냅샷과 비교 (오류면 전체 되돌림)
uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes full --expect-rows 11737  # 573 전체가 생긴 뒤 (기대 건수가 파일 줄 수와 같아야 올림)
```

- 연결 문자열은 `.env`의 `DATABASE_URL`(Supabase 대시보드 Connect → 로컬 스크립트는 Direct connection, IPv6가 안 되면 Session pooler). 값은 출력·커밋하지 않는다.
- **스냅샷별로 보관한다.** 줄마다 `snapshot_date`를 두고 새 스냅샷을 올려도 지난 스냅샷은 그대로다. 평소 조회는 `recalls_latest`·`eval_questions_latest`·`causes_latest` 뷰(데이터가 남은 가장 최근 스냅샷)로 한다. 같은 스냅샷을 다시 올리면 그 스냅샷의 줄만 통째로 바꾸고, **같은 날짜인데 원본·카드·시험지 해시가 다르면 덮어쓰지 않고 중단**한다.
- 올리는 테이블: `data_builds`(스냅샷 1개 = 1줄. 원본·원인 파일의 종류·이름·sha256·건수, 직전 스냅샷 대비 변경 요약) · `recalls` · `eval_questions` · `causes`. 회사명 대응표(`maker_aliases`)는 PR #29 병합 뒤 추가한다.
- `--causes`와 `--expect-rows`는 반드시 적는다 (파일을 자동으로 고르지 않는다). `sample`은 `causes_sample.jsonl`(지금은 300건), `full`은 `causes.jsonl`이다. 기대 건수가 파일 줄 수와 다르면(중간까지만 만들어진 파일) 올리지 않는다.
- **같은 날짜에 다른 원인 파일을 올리면 기본은 중단한다** (이전 근거를 되살릴 수 없게 되기 때문). 표본을 전체본으로 바꾸는 것처럼 의도한 교체만 `--replace-causes`를 붙이고, 이전 파일의 종류·이름·sha256·건수는 `data_builds.causes_history`에 남는다.
- **스냅샷을 지우는 명령은 없다.** 지운 데이터를 되살릴 보관소(아카이브)와 복원 절차가 생기기 전에는 NHTSA가 옛 파일을 다시 주지 않아 근거를 잃는다 — 필요해지면 아카이브와 함께 추가한다 (DEC-034 미결).
- 날짜는 `date` 타입이다. 칸마다 정해진 형식(`YYYYMMDD`, `snapshot_date`는 `YYYY-MM-DD`)만 받고, 틀리면 몇 번째 줄인지 알려 주고 중단한다.
- `recalls.campaign6`은 DB가 `left(campno, 6)`으로 채우는 생성 칸이다. `causes.campaign`과 이을 때 쓴다 (`c.snapshot_date = r.snapshot_date and c.campaign = r.campaign6`). **한 캠페인이 `recalls` 여러 건에 붙을 수 있다** (282개 캠페인) — 카드 수를 셀 때 `distinct campno`를 쓴다.
- 모든 테이블은 RLS를 켜고 정책을 두지 않았다 — Supabase의 anon·authenticated API 키로는 읽히지 않는다. `*_latest` 뷰는 `security_invoker = true`다 (없으면 뷰가 RLS를 우회한다). 서버·스크립트는 `postgres` 계정으로 접속한다.
- 중복·변경을 종류별로 어떻게 다루는지: [`docs/데이터_중복_처리_패턴.md`](../../docs/데이터_중복_처리_패턴.md)
- CI(`lint-and-test`)는 일회용 Postgres 17을 띄워 DB 테스트도 항상 실행한다 (`REQUIRE_DB_TESTS=1` — DB가 없으면 건너뛰지 않고 실패).
- 로컬 확인(DB 테스트 포함): `docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=localtest -p 54329:5432 postgres:17` 뒤 `TEST_DATABASE_URL=postgresql://postgres:localtest@localhost:54329/postgres uv run pytest tests/test_load_db.py`. 테스트가 `public` 스키마를 통째로 지우므로 주소가 localhost가 아니면 건너뛴다.

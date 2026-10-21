# 결함 선례 데이터·시험지 스크립트

결함 선례 찾기 도우미(현행 팀 주제, DEC-030, 기획 `docs/product/기획_결함선례.md`)의 데이터·시험지·기준 점수를 만드는 스크립트다.
원본과 결과물은 커밋하지 않는다 (`data/raw/`, `data/processed/`는 `.gitignore`). 기준 실행을 고정하는 작은 파일(`baseline_2026-10-06.json`은 회사명 반영 전 카드용, `baseline_2026-10-06_maker-aliases.json`는 반영한 카드용, `baseline_2026-10-06_production-dates.json`은 생산 기간 판독 규칙(DEC-059)으로 다시 만든 원인 파일용 — 원본·카드·시험지·573 판본의 sha256)만 커밋한다.

> **재현 범위**: 2026-10-06 기준 점수(0.510)와 573 표본(10/6 첫 판독 205/95, 2026-10-12 규칙 205/83/12)은 **그날의 원본 사본이 있을 때만** 같은 값으로 다시 만들 수 있다. NHTSA는 같은 주소에 매일 새 파일을 덮어쓰고 옛 파일을 주지 않으며, 원본은 저장소에 커밋하지 않는다(AGENTS.md 7절). 사본은 **팀 구글 드라이브**에 `data/` 폴더 압축본(`data.zip` — `raw/nhtsa`·`raw/rclrpt`·`processed/defect`, 2026-10-07 보관)으로 둔다. 링크는 저장소에 적지 않는다 — 우지훈에게 받는다. 받은 사본이 같은지는 `bm25_baseline --baseline`(원본·카드·시험지)과 `rclrpt sample --baseline`(573 PDF)이 각각 sha256으로 확인한다. 사본이 없으면 `fetch`로 받은 새 원본에서 `--allow-drift`로 같은 질문 번호만 "재평가"할 수 있고, 그 값은 기준 점수와 다를 수 있다.

## 실행 순서

```bash
uv run python -m scripts.defect_precedent.nhtsa fetch          # NHTSA 원본 zip 받기 (약 27MB) + manifest.json
uv run python -m scripts.defect_precedent.nhtsa build          # recalls.jsonl · eval.jsonl (약 2초, 원본 sha256 검증 후)
uv run python -m scripts.defect_precedent.bm25_baseline        # 기준 점수 Hit@1·3·5·10 (약 1분)
uv run python -m scripts.defect_precedent.rclrpt sample 300    # 원본 보고서(Part 573) 무작위 표본 판독 (pdftotext 필요)
uv run python -m scripts.defect_precedent.why_stats --baseline scripts/defect_precedent/baseline_2026-10-06_production-dates.json --full  # 573 전수 확인(완성본·명세 필요, 하한~상한). `--full` 없이 돌리면 표본 추정. **원인 파일 판본마다 기준 파일이 다르다** — 생산 기간을 읽는 새 `causes.jsonl`(sha256 b34edec908d5…, DEC-059)은 이 파일, 옛 `causes.jsonl`(06b0fe44990f…)은 `baseline_2026-10-06_maker-aliases.json`을 쓴다(다른 판본에는 "전수 결과가 기준 파일의 고정값과 다르다"로 멈춘다).
uv run python -m scripts.defect_precedent.why_stats --baseline scripts/defect_precedent/baseline_2026-10-06_maker-aliases.json  # 기획 5절 "왜" 집계 (원인 표현·조사 요약·표본 추정·질문의 회사 이름 겹침, 추가 수집 없음)
```

**기준 실행을 다시 잴 때**는 기준 파일을 넘긴다.

- `bm25_baseline --baseline`: 원본 manifest·`recalls.jsonl`·`eval.jsonl`의 sha256이 기준 파일과 모두 같을 때만 "재현"으로 실행하고, 다르면 중단한다. 같은 원본 사본이 없어 현재 데이터로 같은 질문 번호만 다시 재려면 `--allow-drift`를 붙인다 — 출력에 "재평가 (재현 아님)"으로 표시된다.
- `rclrpt sample --baseline`: 현재 목록을 다시 조회하지 않고 기준 파일에 적힌 **당시 판본 목록(582개)**만 받아 각 PDF의 sha256을 확인한 뒤 판독한다. 해시가 다르면 그 리콜은 실패 목록으로 간다.
- `why_stats --baseline`: 원본 manifest·카드·시험지 sha256과 573 표본의 캠페인·원인 칸 내용(기준 파일의 `causes_sample.content_sha256`)이 모두 같을 때만 "재현"으로 실행하고, 다르면 멈춘다(`--allow-drift`는 현재 데이터로 "재계산"). 입력 사본은 구글 드라이브 `defect_data_2026-10-06`(저장소와 같은 `data/` 구조, 원본 `data/raw/nhtsa/`와 `data/processed/defect/`의 4개 파일)이고, 링크는 `.agent/HANDOFF.md` 할 일 20번에 적었다. 2014-08-20 이후 리콜이 캠페인과 1:1이 아니면 전체 추정을 내지 않는다. `--full`은 `--baseline`이 필수이고 기준 파일의 `causes_full`(대상 목록·실패 목록·원인 파일·명세 파일 지문, 줄 수)과도 대조해서 일부 캠페인만 모은 파일은 통과하지 못한다.

```bash
uv run python -m scripts.defect_precedent.bm25_baseline --baseline scripts/defect_precedent/baseline_2026-10-06_maker-aliases.json
uv run python -m scripts.defect_precedent.rclrpt sample --baseline scripts/defect_precedent/baseline_2026-10-06.json
```

- 새 기준을 만들 때: `uv run python -m scripts.defect_precedent.nhtsa freeze scripts/defect_precedent/baseline_<날짜>.json` (원본과 다른 날 만든 eval이면 중단한다)
- `fetch`는 옛 원본을 지우지 않고 `data/raw/nhtsa.<받은 시각>`으로 보관한다.
- `build`는 사람이 확인한 회사명 대응표(`maker_aliases.csv`)를 읽어 카드의 `maker`(정리한 이름)와 `maker_group`(같은 회사로 묶어 볼 단위)을 채운다 (DEC-036). 신고서 원문은 `raw_maker`에 그대로 남는다. 확인이 끝나지 않은 표이거나 표에 없는 이름이 있으면 중단한다. `build.json`에 표의 sha256(`maker_aliases_sha256`)이 남고 `verify_build`가 대조한다. `build`는 `data/processed/defect/`를 통째로 바꾸니 옛 카드가 필요하면 먼저 보관해 둔다. 옛 카드(`build.json`에 `maker_aliases_sha256`이 없음)가 있으면 옛 기준 `baseline_2026-10-06.json`으로 재현되고, 새로 만든 카드는 새 기준으로만 재현된다(코드가 옛 카드를 새로 만들지는 못한다 — 옛 값이 필요하면 커밋 `9e8381f`를 체크아웃). 대응표 해시는 파일 전체 기준이라 확인본을 한 글자라도 고치면 `build`를 다시 하고 새 기준을 freeze해야 한다. 대조한 초안의 해시(`maker_aliases_draft_sha256`, #45)도 같이 남고 대조된다 — 초안을 다시 만들면 `build`를 다시 하고 기준 파일의 초안 해시 칸을 고친다. 이 해시는 기록용이라 확인본과 초안의 "확인 필요"를 함께 지우는 변경은 막지 못하고, 초안의 "확인 필요" 줄 수(31) 고정 테스트와 PR 리뷰가 막는다(DEC-036 운영 메모 ⑤). 새 기준은 `baseline_2026-10-06_maker-aliases.json`이다 — 같은 2026-10-06 원본·시험지·573 표본·전수 결과 고정값에서 카드(`maker`·`maker_group`)만 달라졌고, BM25 점수(Hit@10 0.510 / 0.503)는 같다(BM25는 회사 이름을 색인하지 않는다). 옛 기준은 회사명 반영 전 카드용으로 남겨 둔다.
- NHTSA 원본 URL은 매일 덮어써져서 옛 스냅샷을 다시 받을 수 없다. 원본은 커밋하지 않으므로 **같은 원본 사본(`data/raw/nhtsa` 또는 fetch가 보관한 `data/raw/nhtsa.<받은 시각>`)을 지우지 않는다** — 다른 사람은 사본을 넘겨받아야 재현할 수 있다.
- **573 전체 수집(`rclrpt all`)은 하기로 결정했다 (2026-10-07 사용자 결정).** 대상은 접수일 2014-08-20 이후이면서 573 보고서가 있는 **11,737개 캠페인**(2026-10-07 목록 기준 — 접수일 이후 카드는 12,011건이지만 보고서가 없는 리콜이 있다)이다. PDF 약 2.4만 개, 약 5GB. 파일럿 1,000건(15.5분, 읽음 999·실패 1)으로 잰 전체 소요 시간은 **약 3.5~4시간**이다. 순서:
  1. `pdftotext --version`이 **poppler**인지 확인한다 (xpdf 등 다른 도구는 시작 단계에서 멈춘다. Windows: `winget install oschwartz10612.Poppler`).
  2. 같은 도구로 기준 표본을 재현한다: `rclrpt sample --baseline scripts/defect_precedent/baseline_2026-10-06.json` → 채워짐 205 · 미보고·조사 중 서술 83 · 비어 있음 12 · 미확정 0이 나와야 한다(2026-10-12 규칙, DEC-047 — 10/6 첫 판독은 서술을 빈칸에 섞어 채워짐 205 · 비어 있음 95). 다르면 도구 버전 차이이므로 전체 수집으로 넘어가지 않는다.
  3. 파일럿: `rclrpt sample 1000 --out data/processed/defect/causes_pilot_1000.jsonl`로 실패율·시간을 잰다 (받은 PDF는 전체 수집에서 그대로 쓴다).
  4. 전체: `rclrpt all --expect-campaigns 11737` — 시작할 때 목록의 수집 대상 수가 기대 값과 다르면 PDF를 받기 전에 중단한다(서버가 일부만 돌려줘도 완성본처럼 보이는 것을 막음). 일시 오류는 자동 재시도, 이미 받은 PDF는 건너뛰므로 끊겨도 같은 명령으로 이어서 한다. 200건마다 `causes.partial.jsonl`에 중간 저장하고, **실패가 하나라도 있으면 `causes.jsonl`을 만들지 않는다** (`causes_failures.jsonl`을 보고 원인을 정한 뒤 다시 실행).
  5. **다시 해도 같은 실패(원본 결함)**가 있으면 완성본이 만들어지지 않는다 (예: `RCLRPT-14E059-8941.PDF`는 HTTP 200·`application/pdf`로 응답하지만 내용은 "Artemis Login Page" HTML, 글자 없는 이미지 PDF에 사람이 확인한 제출일이 없는 경우). `causes_failures.jsonl`의 목록을 확인한 뒤 `--accept-failures 캠페인:실패종류:원본파일·내용지문…`(실패했을 때 화면에 나오는 토큰을 복사한다. 확인한 목록이 이번 실패와 캠페인·종류·원본 파일·**받은 내용(sha256)**까지 정확히 같아야 하고, 일시 오류 `download_failed`·코드 오류 `unexpected`는 수용할 수 없음)를 붙여 다시 실행하면(받은 PDF는 건너뛴다) 완성본이 만들어지고, 수용한 캠페인 목록·실패 목록 파일의 sha256·기대 캠페인 전체 목록의 sha256이 명세에 남는다. `all`을 시작하면 이전 실행의 완성본·명세·실패 기록은 `….<시각>.prev.…`(같은 시각이 한 묶음)로 옮겨 둔다(이번 실행이 실패해도 이전 결과가 기본 경로에 남지 않게).
  6. 끝나면 완성본 `causes.jsonl`과 **명세 `causes.manifest.json`**(줄 수·실패 건수와 목록·파일 sha256·캠페인 목록 sha256·기대 캠페인 수·pdftotext 버전)이 함께 생긴다. `load_db load --causes full`이 사람이 입력한 숫자 대신 이 명세와 대조해 올린다. 받은 PDF가 HTML 오류 문서(`%PDF`로 시작하지 않음)이면 저장하지 않고, `pdftotext`가 읽지 못한 PDF는 `.bad`로 옮겨 다음 실행에서 다시 받는다. `pdftotext` 출력은 `-enc UTF-8`로 고정하고 컴퓨터 기본 인코딩에 기대지 않는다.
- 원본 줄의 칸 수가 명세와 다르면 `build`가 그 줄 번호를 보여 주고 중단한다 (값이 옆 칸으로 밀렸을 수 있어 추측해 맞추지 않는다).

## 만들어지는 파일 (`data/processed/defect/`)

| 파일 | 한 줄 = | 칸 |
|---|---|---|
| `recalls.jsonl` | 리콜 카드 1건 | `campno, maker, maker_group, raw_maker, components[], defect, consequence, remedy, received_date, recall_type, influenced_by, dup_group, snapshot_date` |
| `eval.jsonl` | 시험 질문 1개 (조사 1건) | `action_no, question, open_date, gold_campnos[], set[]` (`all` · `since2010` · `rclrpt_range`) |
| `causes_sample.jsonl` / `causes.jsonl` | 원본 보고서 1건 (최신 판본) | `campaign, versions, source_file, submission_date, cause_text, cause_status(filled/stated_unknown/empty/no_field — stated_unknown = 원인 칸이 미보고·조사 중 표현으로 시작하는 글, 원문 보존), supplier_names[], supplier_countries[], new_form, production_dates[{label, raw, start, end}](573 `Production Dates` 줄을 블록마다 원문 그대로 — `raw`는 공백 정리만, `start`·`end`는 정확히 `날짜 - 날짜`일 때만 YYYYMMDD이고 아니면 빈 문자열, `label`은 번호 붙은 블록 머리글 또는 빈 문자열(PDF가 긴 머리글을 줄바꿈하면 **첫 줄에서 끊길 수 있다**, 길이와 무관하게 생긴다 — 쉼표·`&`·`;`로 끝나는 라벨 339블록(80자 미만도 60블록), 90자 이상은 고유 159개(두 집합은 57블록 겹침), 이어지는 줄은 붙이지 않음), 이상해 보이는 값은 고치지 않음, 전체본 명세의 `production_dates_basis`, DEC-059), pdfs{판본: sha256}, resolution(auto/manual/unresolved), unresolved_reasons[]` |
| `causes_*_failures.jsonl` | 읽지 못한 리콜 1건 | `campaign, keys[], error` (받기·변환 실패, 기준 sha256 불일치 — "원인 칸 없음"과 구분) |
| `build.json` | build 1회 | `raw_manifest_sha256, recalls_sha256, eval_sha256, maker_aliases_sha256, maker_aliases_draft_sha256, snapshot_date` — 카드·시험지가 어떤 원본과 어떤 회사명 대응표(확인본·대조한 초안)에서 나왔는지. `verify_build`가 기록된 칸을 모두 대조한다(옛 build.json에 없는 칸은 건너뜀, 초안 해시는 #45). build는 카드·시험지·build.json을 한 폴더에 만든 뒤 폴더째 교체하고, 이 단계가 만들지 않는 파일·하위 폴더(573 판독 결과, 시트, 벡터 사본 등)는 새 폴더로 옮겨 둔다 |

- `maker`는 회사명 대응표(초안 `maker_aliases_draft.csv`는 `uv run python -m scripts.defect_precedent.maker_aliases`가 만들고, 사람이 확인한 `maker_aliases.csv`는 스크립트가 건드리지 않는다. 안내 `docs/labeling/회사명_대응표_안내.md`, DEC-033)의 확인본을 `build`가 카드에 반영한 값이다(DEC-036, PR #42). 대응표는 `maker`(정리한 이름)와 `maker_group`(같은 회사로 묶어 볼 단위) 두 칸을 담고, 신고서 원문 이름은 `raw_maker`에 그대로 남는다. 적용한 표의 sha256은 `build.json`의 `maker_aliases_sha256`(확인본)·`maker_aliases_draft_sha256`(대조한 초안)에 남는다.
- `dup_group`이 같은 리콜은 결함 설명 본문이 같다 (약어를 고려해 자른 첫 문장 = 회사·차종 나열을 뺀 본문이 60자 넘게 같음). **서로 다른 회사가 같은 공급사 부품 설명을 그대로 쓴 경우도 여기 묶인다** (예: Gillig·Cummins 구동계, Unicell·Mickey Truck의 ASA 모니터). 검색에서 묶음당 1건만 보여 주면 "다른 회사의 같은 부품 선례"가 숨겨질 수 있으니, 묶음의 회사 목록은 함께 보여 준다.
- `set`의 `rclrpt_range`는 **첫 번째 정답 리콜**의 접수일이 2014-08-20 이후인 질문이다 (정답 중 하나라도 기준이면 94개).
- `campaign`은 리콜 번호 앞 6자리(예: `24V412`)다. `recalls.jsonl`의 `campno`(예: `24V412000`) 앞 6자리와 잇는다.
- 원본 보고서 판독: 수정본 중 `Submission Date`가 가장 늦은 판본을 쓴다(날짜 형식 `JUN 05, 2024` · `NOV 18,2014` · `Sep 14, 2015`를 모두 읽음). 날짜를 모르는 판본(글자 없는 이미지, 제출일 미판독)이 하나라도 있으면 최신판을 짐작하지 않고 `resolution = "unresolved"`로 두어 원인 칸 통계에서 뺀다. 사람이 이미지 판본을 열어 확인한 제출일은 `manual_submission_dates.json`(PDF 주소 → 제출일·sha256·확인 기록)에 적고, PDF sha256이 같을 때만 쓴다 (`resolution = "manual"`). 원인 칸 중간에 끼는 쪽 꼬리말("The information contained in this report…", "Page 3 of 5")은 지운다.

## 기준값 (2026-10-06, `baseline_2026-10-06.json` · 회사명 반영 카드는 `baseline_2026-10-06_maker-aliases.json`, 점수 같음 · 생산 기간을 읽는 원인 파일의 전수 결과 지문은 `baseline_2026-10-06_production-dates.json`, 카드·점수 같음)

| 항목 | 값 |
|---|---|
| 리콜 줄 → 카드 | 327,429 → 30,350 |
| 결함 조사 / 시험 질문 | 5,349 / 749 (2010년 이후 214, 573 범위 91) |
| 질문 길이 | 중앙값 182자, 400자 초과 34개, 35자 미만 10개 |
| 본문이 같은 리콜 | 6,404 |
| BM25 Hit@10 (전체 749) | **0.510** (주 지표: 연결 리콜 중 하나라도) / 0.503 (첫 번째 연결 리콜만) |
| BM25 Hit@10 (2010년 이후 214 / 573 범위 91) | 0.706 / 0.736 |
| 573 표본 300건 원인 칸 | 채워짐 205 (68.3%) · 미보고·조사 중 서술 83 · 비어 있음 12 · 미확정 0 · 읽지 못함 0 (2026-10-12 규칙. 10/6 첫 판독은 비어 있음 95에 서술이 섞여 있었다) (25V063은 이미지 판본 제출일을 사람이 확인 — `manual`) |
| PDF 텍스트 변환 | poppler `pdftotext` 26.08.0 (`-layout`) — 다른 버전이면 판독 결과가 달라질 수 있다. **25.07.0(Windows winget)에서도 같은 결과를 확인했다** (2026-10-07: 205 · 95 · 미확정 0, 300행 JSON 동일, 판본 582개 sha256 일치 — 옛 규칙 기준 확인이고, 2026-10-12 규칙(DEC-047)은 26.08.0에서만 확인) |

- 이 점수는 **대리 평가**다 — 정답 리콜의 99.6%가 조사 시작 뒤 접수라 "과거 선례 찾기"는 재지 못한다.
- 알려진 한계: 시험 질문 중 내용이 없는 문구가 몇 개 남아 있다 (예: `A`, `DD`, `SEE ATTACHED SUMMARY.`, `See attached closing resume summary.` — 35자 미만 10개 중 다수). 749개 정의를 유지하려고 걸러내지 않았다.
- 문장 자르기는 `WWW.NHTSA.GOV` 같은 대문자 도메인 표기에서 잘못 자를 수 있다. 현재 749개 질문에는 해당 사례가 없다.
- 후속 (PR #25 리뷰에서 나옴, 기준을 새로 만들 때 처리):
  - `freeze`는 `causes_sample*.jsonl`이 이번 build와 같은 입력·시드에서 나왔는지 확인하지 않는다 → `causes_sample`에 build 해시와 시드를 함께 적고 freeze에서 대조한다.
  - `rclrpt sample --baseline`은 일반 `sample`과 같은 파일명에 덮어쓰고, 고른 판본(`selected`)·기대값(`expected`)을 자동 비교하지 않는다. 실패 행은 `pdfs`가 비어 저장되어, 실패가 있는 표본으로 기준을 만들면 그 리콜의 판본 해시가 고정되지 않는다 (2026-10-06 기준은 실패 0건).
  - ~~`rclrpt all`용 재시도·이어받기가 없다.~~ (2026-10-07: 자동 재시도·중간 저장·진행률·불완전 파일 차단을 넣었다. PDF 단위 이어받기는 원래 있었다.)
  - ~~기준 원본의 팀 공용 보관 위치와 받는 절차를 정한다~~ — 2026-10-07 팀 구글 드라이브로 정함 (위 "재현 범위", `docs/guides/환경셋팅.md` 4절).

## DB 적재 (Supabase, DEC-034)

```bash
uv run python -m scripts.defect_precedent.load_db check --causes sample                    # DB 없이 파일만 검증 (해시·날짜·정답 리콜·캠페인 연결·원인 파일 명세 대조)
uv run --env-file .env python -m scripts.defect_precedent.load_db schema                  # schema.sql 적용 (여러 번 해도 됨)
uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes sample    # build 1개 적재 + 건수 대조 + 직전 날짜 build와 비교 (오류면 전체 되돌림)
uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes full      # 573 전체가 생긴 뒤 (causes.manifest.json 명세와 대조)
```

- 연결 문자열은 `.env`의 `DATABASE_URL`(Supabase 대시보드 Connect → 로컬 스크립트는 Direct connection, IPv6가 안 되면 Session pooler). 값은 출력·커밋하지 않는다.
- **build 단위로 보관한다.** `build_id`는 입력 파일 4개(원본 명세·카드·시험지·원인 파일)의 sha256으로 정해지는 불변 식별자다. **내용이 하나라도 다르면 다른 build라서 같은 날짜라도 덮어쓰지 않고 둘 다 남는다** (예: 같은 날짜의 표본 build와 전체 build). 줄마다 `build_id`를 두고 `(build_id, 번호)`가 기본키다. 같은 build를 다시 올리면 저장된 행 해시·원인 명세가 새 계산과 모두 같을 때만 아무것도 바꾸지 않고 끝나고, 하나라도 다르면 덮어쓰지 않고 중단한다.
- 평소 조회는 `recalls_latest`·`eval_questions_latest`·`causes_latest` 뷰로 한다. 뷰는 `latest_build`가 고른 build 하나만 보여 준다: **전체본(full)이 있으면 가장 최근 전체본 → 없을 때만 가장 최근 표본(sample) → 같은 종류 안에서는 나중에 올린 것.** 나중 날짜의 표본을 올려도 전체본이 가려지지 않고, 표본 build는 지워지지 않는다. 표본만 보려면 `recalls_latest_sample`·`eval_questions_latest_sample`·`causes_latest_sample` 뷰를 쓴다. 표본 기준 파일(`baseline_2026-10-06.json`)은 저장소의 것만 쓰고 명령으로 바꿀 수 없다(불완전한 표본이 정상 데이터로 올라가는 것을 막기 위해).
- 변경 요약(`data_builds.change_summary`): 리콜·시험지는 직전 날짜의 build와, **원인(`causes`)은 같은 종류(표본/전체본)의 직전 build와** 비교한다 (크기가 다른 표본과 전체본을 비교하면 '사라짐'이 부풀려진다). 원인이 다른 날짜와 비교됐으면 출력에 비교 대상 날짜·build가 따로 적힌다.
- 올리는 테이블: `data_builds`(build 1개 = 1줄. 원본·원인 파일의 종류·이름·sha256·건수, 대조한 명세, 직전 날짜 build 대비 변경 요약) · `recalls` · `eval_questions` · `causes`. 회사명 대응표는 따로 테이블로 올리지 않고 카드의 `maker`·`maker_group` 칸으로 들어간다(DEC-036).
- **원인 파일의 완전성은 사람이 입력한 숫자가 아니라 독립된 명세와 대조한다.** `--causes`는 반드시 적는다 (파일을 자동으로 고르지 않는다).
  - `sample`(`causes_sample.jsonl`): 커밋된 기준 파일 `baseline_2026-10-06.json`의 `rclrpt_sample` 300개 캠페인과 **정확히 같아야** 한다 (줄 수와 캠페인 목록 모두).
  - `full`(`causes.jsonl`): `rclrpt all`이 완성본과 함께 만드는 `causes.manifest.json`(줄 수·파일 sha256·캠페인 목록 sha256·기대 캠페인 수)과 같아야 한다. **명세가 없으면 올리지 않는다** — 중간까지만 만들어진 파일에는 명세가 없다. 원본 자체의 결함으로 읽지 못한 캠페인은 `rclrpt all --accept-failures`로 수용한 목록(`failed_campaigns`)이 명세에 있고, `줄 수 + 실패 = 기대 캠페인 수`가 맞아야 하며 실패한 캠페인은 파일에 있으면 안 된다 (대조한 명세는 `data_builds.causes_spec`에 남는다). 명세에는 원인 글 정리 방식(`text_basis`, DEC-047)이 반드시 있어야 하고, 수집 대상을 정한 카드 파일의 지문(`recalls_sha256`, 2026-10-12부터 기록)이 있으면 `build.json`의 `recalls_sha256`과 같아야 한다 — 다른 카드 스냅샷으로 모은 원인 파일을 붙이지 않는다(기록이 없는 그 전 수집분은 경고만 한다).
- 날짜는 `date` 타입이다. 칸마다 정해진 형식(`YYYYMMDD`, `snapshot_date`는 `YYYY-MM-DD`)만 받고, 틀리면 몇 번째 줄인지 알려 주고 중단한다.
- `recalls.campaign6`은 DB가 `left(campno, 6)`으로 채우는 생성 칸이다. `causes.campaign`과 이을 때 쓴다 (`c.build_id = r.build_id and c.campaign = r.campaign6`). **한 캠페인이 `recalls` 여러 건에 붙을 수 있다** (282개 캠페인) — 카드 수를 셀 때 `distinct campno`를 쓴다.
- 모든 테이블은 RLS를 켜고 정책을 두지 않았다 — Supabase의 anon·authenticated API 키로는 읽히지 않는다. `*_latest`·`latest_build` 뷰는 `security_invoker = true`다 (없으면 뷰가 RLS를 우회한다). 적재 스크립트는 관리자 연결(`DATABASE_URL`, RLS 우회)을 쓰고, 서버는 조회 전용 계정(`SERVER_DATABASE_URL`, `rag_reader`)을 쓴다 — 배포 때 세 테이블(`data_builds`·`embedding_sets`·`recall_embeddings`)에 `rag_reader` 조회 정책을 더한다(`server/README.md` 3단계, DEC-042 ⑤).
- **build를 지우는 명령은 없다.** 지운 데이터를 되살릴 보관소(아카이브)와 복원 절차가 생기기 전에는 NHTSA가 옛 파일을 다시 주지 않아 근거를 잃는다 — 필요해지면 아카이브와 함께 추가한다 (DEC-034 미결).
- 중복·변경을 종류별로 어떻게 다루는지: [`docs/product/데이터_중복_처리_패턴.md`](../../docs/product/데이터_중복_처리_패턴.md)
- CI(`lint-and-test`)는 일회용 Postgres 17(pgvector 포함)을 띄워 DB 테스트도 실행한다 (`REQUIRE_DB_TESTS=1` — DB가 없으면 건너뛰지 않고 실패). 단, 2026-10-10부터 Actions가 꺼져 있어(DEC-040) CI는 돌지 않는다 — 병합 전에는 `scripts/local_ci.sh`를 `LOCAL_CI_REQUIRE_PR=1`과 `TEST_DATABASE_URL`(일회용 DB)을 붙여 돌려 DB 테스트까지 로컬에서 확인한다.
- 로컬 확인(DB 테스트 포함): `docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=localtest -e POSTGRES_DB=lgcns_test -p 54329:5432 pgvector/pgvector:pg17` 뒤 `TEST_DATABASE_URL=postgresql://postgres:localtest@localhost:54329/lgcns_test uv run pytest tests/test_load_db.py`. 테스트가 `public` 스키마를 통째로 지우므로 주소가 localhost가 아니면 건너뛴다.

## 원인 품질 표본 — 573 원인 칸 30건 + 조사 요약 30건 (기획 6절 표 "원인 품질", `cause_quality.py`)

서버가 선례 카드에 붙여 보여 주는 원인 글(573 원인 칸 원문·연결된 조사 요약)이 실제로 원인을 말하는지 **사람이** 표시하고 비율만 낸다. 원인 미확인 150건(`cause_trials`, 꼬리표 정확도)과는 다른 시험이다.

```bash
uv run python -m scripts.defect_precedent.cause_quality sheet --out data/processed/defect/cause_quality_<날짜>   # 약 40초, cause_quality_573.csv·cause_quality_inv.csv
uv run python -m scripts.defect_precedent.cause_quality score --sheet data/processed/defect/cause_quality_<날짜>/cause_quality_573.csv   # 조사 요약 시트도 따로
```

- 표본 규칙(결과를 보기 전에 고정, 파일 머리말): 749문항을 시드 `20261011`로 섞고, 질문마다 서버 화면에 실제로 나오는 카드(고객사 최대 5 + 그 밖 10) 중 합친 순위 10위 안인 카드에서 원인 글을 **출처별로**(573 원인 칸 / 조사 요약) 모아 같은 시드로 하나씩 고른다 — 출처마다 30건, 시트 두 장(같은 리콜·같은 원인 글은 한 번만). 질문의 출처 조사 요약은 빼고(누수), 30건이 차면 멈춘다.
- **시트를 더블클릭으로 열지 말고, 스프레드시트의 "가져오기"로 모든 칸을 텍스트로 가져온다. 저장은 CSV UTF-8로** (573 시트에는 `25E074` 같은 캠페인 번호가 6줄 있다) — `21E027` 같은 캠페인 번호가 숫자(`2.1E+28`)로 바뀌면 `score`가 그 줄·칸을 알려 주며 멈춘다(`.meta.json`의 줄별 읽기 전용 칸과 대조). 573 줄에는 어느 판본 PDF의 글인지(`source_file`·`pdf_sha256`·`submission_date`)가 있다.
- 결과는 시트마다 "749문항 대리 평가 질문 30개에서, 서버 화면에 나오고 합친 순위 10위 안인 카드의 원인 글이 **원인을 말하는 글의 비율**"이다 — 서비스 전체 원인 품질이나 "원인이 맞는 문장인가"(기획 6절 문구)의 판정이 아니다(서비스 원칙 1).
- `sheet`는 30건을 채우지 못하면 시트를 만들지 않는다. 출력 폴더에 시트·메타가 이미 있으면 멈춘다(표시한 시트를 빈 시트로 덮어쓰지 않게) — 다시 만들려면 새 폴더를 쓴다.
- 벡터는 서버의 로컬 사본(`data/processed/defect/vector_cache/`)을 쓴다 — 서버를 한 번 띄우면 생긴다. DB·유료 API 호출은 없다.
- 표시(`label`): `yes`(이 리콜의 결함 원인을 말한다) / `no`(현상·조사 경과·"원인 미확인"만) / `unsure`. `labeler_id`는 실명 대신 임의 기호. AI는 표시하지 않는다(AGENTS.md 5-2).
- `score`는 시트 옆 `.meta.json`의 표본 지문과 다르거나(줄을 빼거나 더함 — 정렬은 괜찮다), `cause_text`·질문·카드·말한 주체 칸이 바뀌었거나(`text_sha256`·`row_sha256`), 표시·`labeler_id`가 빈 줄이 있으면 멈춘다. 표시는 대소문자를 가리지 않는다. 보고 값은 yes 비율(분모 yes+no, unsure는 따로)과 Wilson 95% 구간을 전체와 출처별(573 원인 칸 / 조사 요약)로 — 기획 6절 "엔진 2 원인 문장"에 해당하는 것은 573 숫자다.
- 2026-10-11 시트(`build_id c6872ae8e9743c56`): 573 30건(표본 지문 `c0da342e8a6239a9`)·조사 요약 30건(`1c1077367c6b9185`), 시트마다 리콜·질문·원인 글 모두 서로 다름. **보고는 시트마다 따로**(6절 "엔진 2 원인 문장"은 573 시트) — 두 숫자를 합치지 않는다. 표시 전에 규칙을 세 번 고쳤다: 화면 밖 카드 제외(첫 시트 `9428e8162d635d85`, 리콜 5건 교체), 변조 검사 칸·573 원본 PDF 칸 추가(같은 표본으로 재생성), 섞은 30건(573 13 · 조사 요약 17, `a0029d755f925dbe`)을 출처별 30건씩으로(사용자 결정, 이슈 #75) — 파일 머리말 "규칙 변경 기록".

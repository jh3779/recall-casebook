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
- **573 전체 수집(`rclrpt all`)은 하기로 결정했다 (2026-10-07 사용자 결정).** 대상은 접수일 2014-08-20 이후이면서 573 보고서가 있는 **11,737개 캠페인**(2026-10-07 목록 기준 — 접수일 이후 카드는 12,011건이지만 보고서가 없는 리콜이 있다)이다. PDF 약 2.3만 개, 약 5GB. 파일럿 1,000건(15.5분, 읽음 999·실패 1)으로 잰 전체 소요 시간은 **약 3.5~4시간**이다. 순서:
  1. `pdftotext --version`이 **poppler**인지 확인한다 (xpdf 등 다른 도구는 시작 단계에서 멈춘다. Windows: `winget install oschwartz10612.Poppler`).
  2. 같은 도구로 기준 표본을 재현한다: `rclrpt sample --baseline scripts/defect_precedent/baseline_2026-10-06.json` → 채워짐 205 · 비어 있음 95 · 미확정 0이 나와야 한다. 다르면 도구 버전 차이이므로 전체 수집으로 넘어가지 않는다.
  3. 파일럿: `rclrpt sample 1000 --out data/processed/defect/causes_pilot_1000.jsonl`로 실패율·시간을 잰다 (받은 PDF는 전체 수집에서 그대로 쓴다).
  4. 전체: `rclrpt all --expect-campaigns 11737` — 시작할 때 목록의 수집 대상 수가 기대 값과 다르면 PDF를 받기 전에 중단한다(서버가 일부만 돌려줘도 완성본처럼 보이는 것을 막음). 일시 오류는 자동 재시도, 이미 받은 PDF는 건너뛰므로 끊겨도 같은 명령으로 이어서 한다. 200건마다 `causes.partial.jsonl`에 중간 저장하고, **실패가 하나라도 있으면 `causes.jsonl`을 만들지 않는다** (`causes_failures.jsonl`을 보고 원인을 정한 뒤 다시 실행).
  5. **다시 해도 같은 실패(원본 결함)**가 있으면 완성본이 만들어지지 않는다 (예: `RCLRPT-14E059-8941.PDF`는 HTTP 200·`application/pdf`로 응답하지만 내용은 "Artemis Login Page" HTML, 글자 없는 이미지 PDF에 사람이 확인한 제출일이 없는 경우). `causes_failures.jsonl`의 목록을 확인한 뒤 `--accept-failures 캠페인:실패종류:원본파일·내용지문…`(실패했을 때 화면에 나오는 토큰을 복사한다. 확인한 목록이 이번 실패와 캠페인·종류·원본 파일·**받은 내용(sha256)**까지 정확히 같아야 하고, 일시 오류 `download_failed`·코드 오류 `unexpected`는 수용할 수 없음)를 붙여 다시 실행하면(받은 PDF는 건너뛴다) 완성본이 만들어지고, 수용한 캠페인 목록·실패 목록 파일의 sha256·기대 캠페인 전체 목록의 sha256이 명세에 남는다. `all`을 시작하면 이전 실행의 완성본·명세·실패 기록은 `….<시각>.prev.…`(같은 시각이 한 묶음)로 옮겨 둔다(이번 실행이 실패해도 이전 결과가 기본 경로에 남지 않게).
  6. 끝나면 완성본 `causes.jsonl`과 **명세 `causes.manifest.json`**(줄 수·실패 건수와 목록·파일 sha256·캠페인 목록 sha256·기대 캠페인 수·pdftotext 버전)이 함께 생긴다. `load_db load --causes full`이 사람이 입력한 숫자 대신 이 명세와 대조해 올린다. 받은 PDF가 HTML 오류 문서(`%PDF`로 시작하지 않음)이면 저장하지 않고, `pdftotext`가 읽지 못한 PDF는 `.bad`로 옮겨 다음 실행에서 다시 받는다. `pdftotext` 출력은 `-enc UTF-8`로 고정하고 컴퓨터 기본 인코딩에 기대지 않는다.
- 원본 줄의 칸 수가 명세와 다르면 `build`가 그 줄 번호를 보여 주고 중단한다 (값이 옆 칸으로 밀렸을 수 있어 추측해 맞추지 않는다).

## 만들어지는 파일 (`data/processed/defect/`)

| 파일 | 한 줄 = | 칸 |
|---|---|---|
| `recalls.jsonl` | 리콜 카드 1건 | `campno, maker, raw_maker, components[], defect, consequence, remedy, received_date, recall_type, influenced_by, dup_group, snapshot_date` |
| `eval.jsonl` | 시험 질문 1개 (조사 1건) | `action_no, question, open_date, gold_campnos[], set[]` (`all` · `since2010` · `rclrpt_range`) |
| `causes_sample.jsonl` / `causes.jsonl` | 원본 보고서 1건 (최신 판본) | `campaign, versions, source_file, submission_date, cause_text, cause_status(filled/empty/no_field), supplier_names[], supplier_countries[], new_form, pdfs{판본: sha256}, resolution(auto/manual/unresolved), unresolved_reasons[]` |
| `causes_*_failures.jsonl` | 읽지 못한 리콜 1건 | `campaign, keys[], error` (받기·변환 실패, 기준 sha256 불일치 — "원인 칸 없음"과 구분) |
| `build.json` | build 1회 | `raw_manifest_sha256, recalls_sha256, eval_sha256, snapshot_date` — 카드·시험지가 어떤 원본에서 나왔는지. build는 이 셋을 한 폴더에 만든 뒤 폴더째 교체한다 |

- `maker`는 회사명 대응표(초안 `maker_aliases_draft.csv`는 `uv run python -m scripts.defect_precedent.maker_aliases`가 만들고, 사람이 확인한 `maker_aliases.csv`는 스크립트가 건드리지 않는다. 안내 `docs/회사명_대응표_안내.md`, DEC-033)를 카드에 적용하기 전까지 `raw_maker`와 같다. 대응표는 `maker`(정리한 이름)와 `maker_group`(같은 회사로 묶어 볼 단위) 두 칸을 담는다 — 확인 전이라 아직 카드에는 적용하지 않았다.
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
| PDF 텍스트 변환 | poppler `pdftotext` 26.08.0 (`-layout`) — 다른 버전이면 판독 결과가 달라질 수 있다. **25.07.0(Windows winget)에서도 같은 결과를 확인했다** (2026-10-07: 205 · 95 · 미확정 0, 300행 JSON 동일, 판본 582개 sha256 일치) |

- 이 점수는 **대리 평가**다 — 정답 리콜의 99.6%가 조사 시작 뒤 접수라 "과거 선례 찾기"는 재지 못한다.
- 알려진 한계: 시험 질문 중 내용이 없는 문구가 몇 개 남아 있다 (예: `A`, `DD`, `SEE ATTACHED SUMMARY.`, `See attached closing resume summary.` — 35자 미만 10개 중 다수). 749개 정의를 유지하려고 걸러내지 않았다.
- 문장 자르기는 `WWW.NHTSA.GOV` 같은 대문자 도메인 표기에서 잘못 자를 수 있다. 현재 749개 질문에는 해당 사례가 없다.
- 후속 (PR #25 리뷰에서 나옴, 기준을 새로 만들 때 처리):
  - `freeze`는 `causes_sample*.jsonl`이 이번 build와 같은 입력·시드에서 나왔는지 확인하지 않는다 → `causes_sample`에 build 해시와 시드를 함께 적고 freeze에서 대조한다.
  - `rclrpt sample --baseline`은 일반 `sample`과 같은 파일명에 덮어쓰고, 고른 판본(`selected`)·기대값(`expected`)을 자동 비교하지 않는다. 실패 행은 `pdfs`가 비어 저장되어, 실패가 있는 표본으로 기준을 만들면 그 리콜의 판본 해시가 고정되지 않는다 (2026-10-06 기준은 실패 0건).
  - ~~`rclrpt all`용 재시도·이어받기가 없다.~~ (2026-10-07: 자동 재시도·중간 저장·진행률·불완전 파일 차단을 넣었다. PDF 단위 이어받기는 원래 있었다.)
  - 기준 원본(NHTSA zip·명세·573 PDF)의 팀 공용 보관 위치와 받는 절차를 정한다 (위 "재현 범위").

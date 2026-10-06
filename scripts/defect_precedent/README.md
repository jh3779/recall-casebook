# 결함 선례 데이터·시험지 스크립트

결함 선례 기획(`docs/기획_결함선례.md`, DEC-030 — 현재 팀 주제 아님, 재검토 안건, PR #23)의 수치를 저장소에서 재현한다.
원본과 결과물은 커밋하지 않는다 (`data/raw/`, `data/processed/`는 `.gitignore`). 기준 실행을 고정하는 작은 파일(`baseline_2026-10-06.json`)만 커밋한다.

## 실행 순서

```bash
uv run python -m scripts.defect_precedent.nhtsa fetch          # NHTSA 원본 zip 받기 (약 27MB) + manifest.json
uv run python -m scripts.defect_precedent.nhtsa build          # recalls.jsonl · eval.jsonl (약 2초, 원본 sha256 검증 후)
uv run python -m scripts.defect_precedent.bm25_baseline        # 기준 점수 Hit@1·3·5·10 (약 1분)
uv run python -m scripts.defect_precedent.rclrpt sample 300    # 원본 보고서(Part 573) 무작위 표본 판독 (pdftotext 필요)
```

**같은 시험지·같은 표본으로 비교할 때**는 기준 파일을 넘긴다. 원본이 매일 갱신돼 질문이 늘거나 목록이 바뀌어도 기준 실행과 같은 질문·같은 리콜만 쓴다.

```bash
uv run python -m scripts.defect_precedent.bm25_baseline --baseline scripts/defect_precedent/baseline_2026-10-06.json
uv run python -m scripts.defect_precedent.rclrpt sample --baseline scripts/defect_precedent/baseline_2026-10-06.json
```

- 새 기준을 만들 때: `uv run python -m scripts.defect_precedent.nhtsa freeze scripts/defect_precedent/baseline_<날짜>.json`
- NHTSA 원본 URL은 매일 덮어써져서 옛 스냅샷을 다시 받을 수 없다. 기준 파일의 sha256으로 "같은 원본인지"만 확인할 수 있다.
- `rclrpt all`(약 1.2만 건, 수 시간)은 팀 확인 후에 돌린다.

## 만들어지는 파일 (`data/processed/defect/`)

| 파일 | 한 줄 = | 칸 |
|---|---|---|
| `recalls.jsonl` | 리콜 카드 1건 | `campno, maker, raw_maker, components[], defect, consequence, remedy, received_date, recall_type, influenced_by, dup_group, snapshot_date` |
| `eval.jsonl` | 시험 질문 1개 (조사 1건) | `action_no, question, open_date, gold_campnos[], set[]` (`all` · `since2010` · `rclrpt_range`) |
| `causes_sample.jsonl` / `causes.jsonl` | 원본 보고서 1건 (최신 판본) | `campaign, versions, source_file, submission_date, cause_text, cause_status(filled/empty/no_field), supplier_names[], supplier_countries[], new_form, image_only_versions` |
| `causes_*_failures.jsonl` | 읽지 못한 리콜 1건 | `campaign, error` (받기·변환 실패 — "원인 칸 없음"과 구분) |

- `maker`는 회사명 대응표가 생기기 전까지 `raw_maker`와 같다.
- `dup_group`이 같은 리콜은 결함 설명 본문이 같다 (약어를 고려해 자른 첫 문장 = 회사·차종 나열을 뺀 본문이 60자 넘게 같음). **서로 다른 회사가 같은 공급사 부품 설명을 그대로 쓴 경우도 여기 묶인다** (예: Gillig·Cummins 구동계, Unicell·Mickey Truck의 ASA 모니터). 검색에서 묶음당 1건만 보여 주면 "다른 회사의 같은 부품 선례"가 숨겨질 수 있으니, 묶음의 회사 목록은 함께 보여 준다.
- `set`의 `rclrpt_range`는 **첫 번째 정답 리콜**의 접수일이 2014-08-20 이후인 질문이다 (정답 중 하나라도 기준이면 94개).
- `campaign`은 리콜 번호 앞 6자리(예: `24V412`)다. `recalls.jsonl`의 `campno`(예: `24V412000`) 앞 6자리와 잇는다.
- 원본 보고서 판독: 수정본 중 `Submission Date`가 가장 늦은 판본을 쓴다(날짜 형식 `JUN 05, 2024` · `NOV 18,2014` · `Sep 14, 2015`를 모두 읽음). 글자가 없는 이미지 판본은 건너뛰고 `image_only_versions`에 센다. 원인 칸 중간에 끼는 쪽 꼬리말("The information contained in this report…", "Page 3 of 5")은 지운다.

## 기준값 (2026-10-06, `baseline_2026-10-06.json`)

| 항목 | 값 |
|---|---|
| 리콜 줄 → 카드 | 327,429 → 30,350 |
| 결함 조사 / 시험 질문 | 5,349 / 749 (2010년 이후 214, 573 범위 91) |
| 질문 길이 | 중앙값 182자, 400자 초과 35개, 35자 미만 10개 |
| 본문이 같은 리콜 | 6,394 |
| BM25 Hit@10 (전체 749) | **0.511** (주 지표: 연결 리콜 중 하나라도) / 0.505 (첫 번째 연결 리콜만) |
| BM25 Hit@10 (2010년 이후 214 / 573 범위 91) | 0.706 / 0.736 |
| 573 표본 300건 원인 칸 | 채워짐 205 (68.3%) · 비어 있음 95 · 읽지 못함 0 |

- 이 점수는 **대리 평가**다 — 정답 리콜의 99.6%가 조사 시작 뒤 접수라 "과거 선례 찾기"는 재지 못한다.
- 알려진 한계: 시험 질문 중 내용이 없는 문구가 몇 개 남아 있다 (예: `A`, `DD`, `SEE ATTACHED SUMMARY.`, `See attached closing resume summary.` — 35자 미만 10개 중 다수). 749개 정의를 유지하려고 걸러내지 않았다.

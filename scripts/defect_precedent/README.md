# 결함 선례 데이터·시험지 스크립트

결함 선례 기획(`docs/기획_결함선례.md`, DEC-030 — 현재 팀 주제 아님, 재검토 안건)의 수치를 저장소에서 재현한다.
원본과 결과물은 커밋하지 않는다 (`data/raw/`, `data/processed/`는 `.gitignore`).

## 실행 순서

```bash
uv run python -m scripts.defect_precedent.nhtsa fetch          # NHTSA 원본 zip 받기 (약 27MB) + manifest.json
uv run python -m scripts.defect_precedent.nhtsa build          # recalls.jsonl · eval.jsonl (약 2초)
uv run python -m scripts.defect_precedent.bm25_baseline        # 기준 점수 Hit@1·3·5·10 (약 1분)
uv run python -m scripts.defect_precedent.rclrpt sample 300    # 원본 보고서(Part 573) 표본 판독 (pdftotext 필요)
```

`rclrpt all`(약 1.2만 건, 수 시간)은 팀 확인 후에 돌린다.

## 만들어지는 파일 (`data/processed/defect/`)

| 파일 | 한 줄 = | 칸 |
|---|---|---|
| `recalls.jsonl` | 리콜 카드 1건 | `campno, maker, raw_maker, components[], defect, consequence, remedy, received_date, recall_type, influenced_by, dup_group, snapshot_date` |
| `eval.jsonl` | 시험 질문 1개 (조사 1건) | `action_no, question, open_date, gold_campnos[], set[]` (`all` · `since2010` · `rclrpt_range`) |
| `causes_sample.jsonl` / `causes.jsonl` | 원본 보고서 1건 (최신 판본) | `campaign, versions, source_file, submission_date, cause_text, cause_status(filled/empty/no_field), supplier_names[], supplier_countries[], new_form` |

- `maker`는 회사명 대응표가 생기기 전까지 `raw_maker`와 같다.
- `dup_group`이 같은 리콜은 결함 설명 본문이 복사된 것이다 (첫 문장 = 회사·차종 나열을 뺀 본문이 60자 넘게 같음).
- `campaign`은 리콜 번호 앞 6자리(예: `24V412`)다. `recalls.jsonl`의 `campno`(예: `24V412000`) 앞 6자리와 잇는다.

## 기준값 (2026-10-06 스냅샷)

| 항목 | 값 |
|---|---|
| 리콜 줄 → 카드 | 327,429 → 30,347 (같은 날 오후 갱신본은 30,350) |
| 결함 조사 / 시험 질문 | 5,349 / 749 (2010년 이후 214, 573 범위 91) |
| 본문이 복사된 리콜 | 4,761 |
| BM25 Hit@10 | 0.611~0.613 (주 지표: 연결 리콜 중 하나라도) / 0.605 (첫 번째 연결 리콜만) |
| 573 표본 300건 원인 칸 | 205건 채워짐 (68.3%) |

매일 갱신되는 원본이라 조금씩 달라질 수 있다. 크게 다르면 `manifest.json`의 받은 시각과 함께 보고한다.
시험 점수는 **대리 평가**다 — 정답 리콜의 99.6%가 조사 시작 뒤 접수라 "과거 선례 찾기"는 재지 못한다.

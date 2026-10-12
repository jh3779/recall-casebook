# 실험: gpt-6-luna와 gpt-4o-mini 비교 (2026-10-12)

> **C 정답 표시자는 표시를 끝낼 때까지 2·3절을 읽지 않는다** — 모델별 답 경향이 애매한 문장의 표시에 섞이지 않게(AGENTS.md 5-2). C의 모델별 판정 건수는 이 문서에 싣지 않는다. **공개 기록**: A·B 시험의 집계(빈 목록 건수 등)는 2026-10-12 대화로 표시자(우지훈)에게 이미 전해졌다 — C 채점을 보고할 때 이 사실을 함께 적는다.

> 목적: 가격 차이가 크지 않으면 연구용 LLM 시험을 gpt-6-luna로 바꿀 수 있는지 같은 입력으로 잰다(사용자 요청 2026-10-12).
> **서비스는 LLM을 부르지 않는다** — 원인은 573 원문을 그대로 보여 준다(DEC-039, `docs/실험_P2_검색방식비교.md` 5절). 이 비교는 연구용 시험 스크립트(`engine2_trial.py`·`cause_trials.py`)의 모델 선택이다.

## 1. 조건

- 모델: `gpt-6-luna`(추론 강도 `reasoning.effort = none` — 사용자 선택), `gpt-4o-mini`(문서상 스냅샷 `gpt-4o-mini-2024-07-18` — 응답의 실제 모델 이름은 결과에 기록하지 않았다, 추론 설정 없음 — 10/8 시험과 같은 요청).
- 같은 날(2026-10-12) 같은 입력으로 두 모델을 모두 다시 쟀다 — 같은 모델도 실행마다 3~7건 결과가 달라지므로(10/8 관찰) 10/8 수치와 섞지 않는다.
- 입력 판본: 카드 `recalls_sha256 3f996182fe2efb37`, 시험지 `fe5433db5c7864a0`, 원인 파일 `causes_sha256 06b0fe44990fe859`(DEC-047 재수집본 — 10/8 시험 때와 다르다).
- 시험 세 가지(지시문은 10/8과 같다):
  - **A. 573 원인 칸에서 원인 문장 고르기** (`engine2_trial`, 30건)
  - **B. 원인 칸이 없는 카드의 결함 설명에서 원인 문장 고르기** (`cause_trials defect`, 30건)
  - **C. "원인 미확인" 걸러내기** (`cause_trials unknown`, 150건, 시드 20261008)
- 가격(OpenAI 모델 문서, 2026-10-12 확인, 100만 토큰당): gpt-6-luna 입력 0.10달러·캐시 입력 0.01달러·출력 0.50달러 / gpt-4o-mini 입력 0.15달러·캐시 입력 0.075달러·출력 0.60달러. Luna는 추론 모델이고 기본 추론 강도는 `medium`이다(이번에는 `none`).
- 결과 파일: `data/processed/defect/llm_trials_20261012/`(커밋하지 않음 — 결과마다 `.meta.json`에 판본·모델·추론 강도·지시문).

## 2. 결과

| | 시험 | gpt-6-luna (none) | gpt-4o-mini |
|---|---|---|---|
| 돌려준 문자열이 모두 원문과 글자 그대로 일치 | A (30) | 28건 | 30건 |
| 　글자를 바꿔 글자 대조에서 버려진 건 | A | **0건** | 0건 |
| 　빈 목록("원인을 말하지 않음") | A | 2건 | 0건 |
| 　원인 칸 전체를 돌려줌 | A | 20건 | 22건 |
| 돌려준 문자열이 모두 원문과 일치 | B (30) | 11건 | 17건 |
| 　글자를 바꿔 버려진 건 | B | **0건** | **3건** |
| 　빈 목록 | B | 19건 | 10건 |
| 글자를 바꿔 버려진 건 | C (150) | **0건** | **5건** |
| 응답 해석 실패 | A·B·C | 0건 | 0건 |
| 평균 응답 시간 | A / B / C | 2.24 / 1.59 / 1.67초 | 1.34 / 1.17 / 1.17초 |
| 토큰(입력·출력) | A+B+C | 46,395 · 7,941 | 46,815 · 7,225 |
| **비용(210회)** | A+B+C | **약 0.0086달러** | **약 0.0114달러** |

- C의 "미확인으로 본 건수"는 이 문서에 싣지 않는다. 정답을 사람이 표시하는 중이라(표시 전 관찰이 판단에 섞이지 않게 — AGENTS.md 5-2, `docs/실험_P2_검색방식비교.md` 5-2 B), 표시가 끝난 뒤 `cause_trials score`로 두 결과를 함께 채점해 이 절에 더한다.
- 출력 토큰이 4o-mini와 비슷해 `none`에서는 추론 토큰이 거의 쓰이지 않은 것으로 보인다(응답의 출력 토큰 합계만 기록했다 — 추론 토큰을 따로 세지 않았다).

## 3. 읽는 법

1. **가격**: 같은 210회에 Luna가 약 25% 싸다(0.0086 vs 0.0114달러). 둘 다 1센트 남짓이라 이 규모에서는 차이가 작다.
2. **원문을 고쳐 쓰는가**: 이번 1회 실행에서 Luna는 세 시험 210회 중 원문 글자를 바꾼 건이 없었다(다만 답을 낸 건 자체가 적었다 — B에서 Luna 11건, 4o-mini 20건. 같은 모델도 실행마다 3~7건이 달라지므로(10/8 관찰) 이 차이는 참고용이다). 4o-mini는 B에서 3건, C에서 5건 바꿨다(10/8에도 C 5건, 대문자 변경 등). 이 단서들 때문에 원문 보존의 우열은 말하지 않는다. 다만 버려진 글은 글자 대조가 이미 걸러 내므로 화면에 바뀐 글이 나가지는 않는다.
3. **빈 목록이 많다**: Luna는 A에서 2건, B에서 19건을 "원인을 말하지 않음"으로 돌려줬다(4o-mini 0·10건). B는 결함 설명이 "무엇이 고장 나는지"만 말하는 경우가 많아 빈 목록이 맞을 수 있고(10/8 관찰: 4o-mini가 "왜"가 아니라 "무엇"을 고른 경우가 여럿), 원인을 놓친 것일 수도 있다. **어느 쪽이 맞는지는 사람 확인 전이라 정확도로 말하지 않는다.**
4. **속도**: Luna가 질문당 0.4~0.9초 느렸다.

## 4. 결정과 남은 확인

**결정 — 사용자 지정에 따른 운영 선택(2026-10-12, "그럼 luna로 지정해서 해보자")**: 연구용 시험 스크립트의 기본 모델을 `gpt-6-luna`(추론 강도 `none`)로 한다 — `--model`을 주지 않거나 `--model gpt-6-luna`만 적으면 이 조합(추론 강도 `none` — 문서 기본값 `medium`이 아님)으로 돈다(`cause_trials.py` `DEFAULT_MODEL`·`model_and_effort`, `engine2_trial.py`도 같은 함수). 다른 모델은 `--model`로 지정하고, 추론 강도는 `--reasoning-effort`를 줄 때만 보낸다.

**이 결정은 품질 우위를 근거로 한 것이 아니다.** 이번 수치가 보여 주는 것은 ① 같은 210회에서 Luna가 더 쌌다(차이는 1센트 미만) ② 이번 1회 실행에서 Luna는 원문 글자를 바꾼 건이 없었다 — 다만 답을 낸 건 자체가 적어(B 11 대 20) 바꿀 기회도 적었다 — 뿐이고, "원인을 맞게 골랐는가"(A·B)·"미확인을 맞게 걸렀는가"(C)는 아직 모른다.

- **남은 확인**: 사람 표시 뒤 같은 판본에서 두 모델을 채점해, 두 모델의 정확도 차이가 기준 폭 0.03 **미만**이면 같다고 보고 Luna를 유지하며, Luna가 0.03 이상 낮으면 기본값을 다시 정한다(같다고 보는 기준 — `docs/기획_결함선례.md` 6절, AGENTS.md 5-1·5-3). C는 표시 시트가 있고(채점 판본 주의는 5절), A·B는 사람 정답 표시를 따로 해야 한다(AI가 표시하지 않는다, AGENTS.md 5-2 — 질문을 만든 세션이 아닌 다른 세션에서).
- 서비스 경로는 바뀌지 않는다(LLM 없음).

## 5. 재현

```bash
# 추론 모델에는 --reasoning-effort를 준다(주지 않으면 요청에 넣지 않는다 — 4o-mini 등)
O=data/processed/defect/llm_trials_20261012
mkdir -p "$O"
uv run --with openai --env-file .env python -m scripts.defect_precedent.engine2_trial --model gpt-6-luna --reasoning-effort none --n 30 --out $O/e2_luna.jsonl
uv run --with openai --env-file .env python -m scripts.defect_precedent.engine2_trial --model gpt-4o-mini --n 30 --out $O/e2_4omini.jsonl
uv run --with openai --env-file .env python -m scripts.defect_precedent.cause_trials defect --model gpt-6-luna --reasoning-effort none --n 30 --out $O/def_luna.jsonl
uv run --with openai --env-file .env python -m scripts.defect_precedent.cause_trials defect --model gpt-4o-mini --n 30 --out $O/def_4omini.jsonl
uv run --with openai --env-file .env python -m scripts.defect_precedent.cause_trials unknown --model gpt-6-luna --reasoning-effort none --n 150 --out $O/unk_luna.jsonl
uv run --with openai --env-file .env python -m scripts.defect_precedent.cause_trials unknown --model gpt-4o-mini --n 150 --out $O/unk_4omini.jsonl
# 사람 표시 뒤 채점(API 호출 없음)
uv run python -m scripts.defect_precedent.cause_trials score --sheet <표시한.csv> $O/unk_luna.jsonl $O/unk_4omini.jsonl
```

허용하는 추론 강도 값은 `none`·`low`·`medium`·`high`·`xhigh`·`max`(OpenAI 모델 문서)이고 스크립트가 그 밖의 값을 거부한다.

**주의 — 채점 판본**: C의 사람 표시 시트(`data/processed/defect/cause_unknown_2026-10-09/unknown_label_sheet.csv`)는 원인 파일 판본 `d215ff583281b5ed`로 만들었고, 이번 결과는 DEC-047 재수집본 `06b0fe44990fe859`로 만들었다. 이번 150건은 시트와 표본·원문이 글자까지 같다(2026-10-12 `text_sha256` 대조 — DEC-047로 글이 바뀐 21V503·22V400·26E009·26V404는 표본에 없음). 그러나 `score`는 결과 메타의 원인 판본이 시트 판본과 같아야 채점하므로(`scripts/defect_precedent/cause_trials.py`의 `score` — 결과 메타의 `causes_sha256`을 시트 판본과 대조) 이번 결과는 그대로는 거부된다. 표시가 끝나면 ① 시트 판본으로 두 모델을 다시 재거나(그 판본 원인 파일이 로컬 `data/processed/defect/causes.20261007.jsonl`로 남아 있다 — sha256 `d215ff583281b5ed…`, 2026-10-12 확인. 다만 시험 스크립트에는 원인 파일 경로 옵션이 없고 `provenance()`가 원인 파일과 명세를 함께 대조하므로, `causes.jsonl`·`causes.manifest.json`을 함께 `20261007` 판본으로 잠시 바꿔 재고 끝나면 되돌려야 한다) ② 원문 해시가 모두 같을 때 판본 차이를 허용하도록 `score`를 바꾸는 것 중 하나를 정한다(정하기 전에는 채점하지 않는다).

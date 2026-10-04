# PRD — 온보딩 체크리스트 RAG

> 이 문서는 `docs/기획v1.md`·`docs/진행계획.md`·`.agent/DECISIONS.md`에 이미 있는 결정을 제품 요구사항 형식으로 정리한 것이다. 숫자·근거는 원본 문서를 인용하며, 이 문서에서 새로 지어내지 않는다. 원본이 바뀌면 이 문서도 다시 맞춘다.

## 1. 한 줄 정의

GitLab 공개 핸드북을 근거로, 신규 입사자·부서 이동자가 새 업무를 맡았을 때 적용될 수 있는 온보딩 체크리스트 항목과 확인 기준을 원문 근거와 함께 정리해 주는 RAG 서비스 (AGENTS.md 1절, DEC-010).

## 2. 배경·문제 정의

- **대상**: 신규 입사자 + 부서 이동자 (`기획v1.md` 1절).
- **데이터**: GitLab 공개 핸드북 스냅샷(`suuuuuuungho/GitLab_Data` 커밋 `0ab0299`). 34개 부서 폴더, 4,612개 md, 약 1,175만 토큰(글자수÷4 경험칙) — `docs/handbook/README.md`, `scripts/fetch_handbook_dataset.py`로 재현·검증.
- **고통 포인트 8개**(`기획v1.md` 1절) — **5번만 근거 있음**(핸드북 `people-group/promotions-transfers.md:701`), 나머지 7개는 **가설**이며 실제 사례로 검증 전까지 평가셋 근거로 쓰지 않는다. 섣불리 "확정된 문제"로 포장하지 않는 게 이 PRD의 전제다.

## 3. 목표

1. 체크리스트 생성 — 질문에 맞는 항목·기준·확인 방법을 근거 문서와 함께 제시한다.
2. 판정하지 않는다 — "적용됩니다/안 됩니다"를 말하지 않는다(AGENTS.md 2절 1항).
3. 근거 없는 말을 하지 않는다 — 모든 항목에 `source_path#heading_path` 근거를 단다(2절 2항).
4. 추적 가능해야 한다 — 답변 → 근거 문서 → 데이터 버전(`commit_sha`) → 원본 위치까지 되짚을 수 있다(2절 4항).

## 4. 범위

### 포함 — 도메인 3개 (DEC-020, `기획v1.md` 3절)

| 도메인 | 배정 부서 |
|---|---|
| 인사 (People) | people-group, hiring, people-policies, total-rewards, labor-and-employment-notices, entity |
| 엔지니어링 (Engineering) | engineering, security, product, product-development |
| 영업·지원 (Sales·Support) | sales, support, customer-experience, marketing, solutions-architects, resellers, alliances |

**공용 폴더 6개**(세 도메인이 모두 색인 가능): company, about, values, communication, tools-and-tips, upstream-studios.

### 제외 — 11개 폴더 (DEC-020)

leadership, ceo, board-meetings, eba, acquisitions, legal, finance, business-technology, eta, enterprise-data, it — 경영진 운영·내부 지원 조직 자료라 온보딩 체크리스트 범위 밖. 질문에서 필요가 확인되면 공용으로 옮길 수 있다.

세부 제외 사례(폴더 단위 매핑보다 촘촘함): `customer-experience/customer-onboarding/`은 GitLab **고객**(제품 구독자) 대상 콘텐츠라 영업·지원 도메인에서 추가 제외(`기획v1.md` 4절 "영업·지원 — 데이터 처리 설계" 4번).

### 하지 않는 것

- 판정("적용됩니다/안 됩니다") — 원칙적으로 배제(AGENTS.md 2절).
- 담당자 미확정 상태에서의 전사 공통 전체 커버 — DEC-020에서 전사 공통을 도메인에서 빼고 공용/제외로 재분배.

## 5. 핵심 플로우 (`기획v1.md` 5절)

```
① 질문 입력(user_type + 업무 상황) → ② 질문 분류(도메인, 규칙+LLM) → ③ 모델 분류(도메인별 RAG 구성)
   → ④ 검색(도메인별 청크 top-k) → ⑤ 근거 범위 고정 → ⑥ 체크리스트 생성(고정 스키마)
   → ⑦ 인용 검증(코드로 검사, 범위 밖 제거) → ⑧ 답변
```

서비스 원칙은 특정 단계가 구조로 강제한다 — 판정 없음(⑥ 스키마 자체), 근거(⑤⑦), 추적성(④⑧). 프롬프트 지시가 아니라 코드 검증이 최종 방어선이다.

## 6. 출력 스키마 (DEC-019)

응답 전체: `{commit_sha, items: [...]}`. `items` 원소 필드:

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `item` | string | 예 | 체크리스트 항목 |
| `reason` | string | 예 | 왜 필요한지 |
| `criteria` | string \| null | 아니오 | 적용을 가르는 기준(판정 아님) |
| `check_method` | string \| null | 아니오 | 확인 방법 |
| `source` | string `"path#heading"` | 예 | 코드가 `chunk_key` 메타데이터로 채움, 모델이 안 씀 |
| `evidence_quote` | string | 예 | 원문 발췌, 근거 없으면 항목 전체 제거 |
| `domains` | string[] | 예 | 근거 청크의 도메인 합집합 |

`null` 허용은 `criteria`·`check_method`뿐이고, 화면에는 "확인 필요"로만 표시(저장 값은 항상 `null`). 상세 규칙·검증 테스트 사례는 `.agent/DECISIONS.md` DEC-019.

## 7. 평가 (성공 기준)

- 지표: Recall@k·Hit@k(k=1,3,5,10). 차이 0.03 미만이면 같다고 본다(`기획v1.md` 3절).
- 질문 세트 3종 — **문서 유래**(FAQ, 동작 확인용), **합성**(역할극, 모델 최종 선택용, DEC-021), **실제**(확보되면 추가 비교용, DEC-013·016). 세 세트는 합산하지 않고 따로 보고한다.
- 도메인당 최소 34개, `user_type`별 12개, `scenario_type`별 5개(DEC-021·022). 못 채운 도메인은 0.03 비교 대신 문항별 성공/실패로 보고.
- 평가셋은 AI·팀원이 지어내지 않는다(AGENTS.md 5절) — 질문 출처·정답 표시자(`labeler_id`)를 평가표에 기록.

## 8. 일정 (`docs/진행계획.md`)

| 날짜 | 단계 |
|---|---|
| 10/2 | 주제 확정(완료) |
| 10/6~7 | 도메인별 PoC, 방향 확정 |
| 10/8~10 | 평가 정답표, 파트 분담·발표자 확정 |
| 10/12~14 | 개발(실제 3일) |
| 10/15~16 | 기능 설명 |
| 10/17~18 | 보완 |
| 10/19 | 발표 준비 |
| 10/20 | 발표 |

## 9. 미결 — 팀 확인 필요

- 도메인 3개 vs 팀원 4명 배치, 공용 폴더 6개 색인 담당 (`기획v1.md` 5절 미결, DEC-020 영향)
- 질문 분류 방식(규칙/임베딩/LLM)과 그 평가셋
- 도메인별 기술 스택 — 인사·엔지니어링은 미정, 영업·지원은 초안 제안됨(`기획v1.md` 4절)
- `user_type`(신규/이동)이 검색·생성을 바꾸는 방식의 가설 확인

## 10. 참고 문서

- `docs/기획v1.md` — 전체 기획, 데이터 실측, 아키텍처
- `docs/진행계획.md` — 일정·역할·위험 요소
- `.agent/DECISIONS.md` — DEC-010~022 (주제 전환부터 평가 규칙까지)
- `docs/handbook/README.md`, `scripts/fetch_handbook_dataset.py` — 데이터 재현

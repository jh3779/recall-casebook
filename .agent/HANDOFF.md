# Agent Handoff

_갱신: 2026-10-03_

## Current Objective

PR #7(기획v1·평가 규칙)·#8(데이터 스크립트)은 병합 완료(main `4c0db4a`·`a43f62d`). 지금은 **이슈 정리 PR**(chore: 병합 게이트·프로토콜 정리, docs: 옛 기획 폐기 안내·출력 스키마)을 리뷰·병합하고, 10/6 팀 회의 안건과 도메인 PoC를 준비하는 것.


## Current Phase

없음 — `PROJECT_CONTEXT.md`에 Phases 로드맵이 아직 없다. 느슨하게는 "기획 단계"(10/2 주제 결정 ~ 10/6-7 도메인별 PoC 전).

## Completed

- PR #7 오픈, Codex 자동 리뷰 "머지 전 필수 보완" 5건을 전부 반영해 커밋 `813a772`로 push함(AGENTS.md 2·5절 재작성, 고통 포인트 `(가설)` 표시, 34개 부서↔도메인 매핑 초안, `scripts/fetch_handbook_dataset.py`, stale 문서 정리).
- grilling Q1~Q5를 사용자 인터뷰(AskUserQuestion)로 결정 — 다섯 개 모두 권장안 채택. 그중 평가 규칙·중복 제거 키는 [[DEC-011]]로 기록.
- `docs/기획v1.md` 3절 반영:
  - "PoC 공통 기준" 표: 중복 제거 키 `(source_path, commit_sha, heading_path)` 명시(코퍼스·최소 DB 행), "평가 질문 유형"(문서 유래 / 상황 서술, 합산 안 함) 행, "평가 질문 최소 개수"(도메인당 30, 미달 시 문항별 성공/실패 목록) 행 추가.
  - "전사 공통 분할안 (제안)" 소절: 문화·리더십 9개 폴더 747,230 토큰 / 지원 부서·내부 IT 6개 폴더 1,414,776 토큰 / `upstream-studios` 공용(224,901). 공용 2순위 후보 `tools-and-tips`.

## Last Work

(10/3 저녁) PR #12 병합(main `52a83c4`, 이슈 #2·#3 닫힘), 이슈 #4는 계획 없음으로 닫음. PR #13(`docs/기획.md` 폐기 안내 + 5절 출력 스키마, DEC-019)은 자동 리뷰가 "위험도 상"(안내 문서가 옛 규제 서비스를 지시한다)을 세 번 반복했으나 main의 AGENTS.md·PROJECT_CONTEXT.md·HANDOFF.md·시작하기.md에는 옛 용어가 없음을 직접 확인해 근거 반박 예정(사용자 승인). CI 자동 리뷰 도입 검토는 바탕화면 `CI_자동리뷰_검토_2026-10-03.md`(10/12 이후 권고, 이번에 사용자가 Codex로 진행하기로 정함).

2026-10-03 이슈 정리: ① `merge_gate.py`가 변경 요청·미해결 스레드를 수정된 결과 코멘트보다 먼저 failure로 표시(테스트 2개 먼저, #3 O1) ② `MERGE_PROTOCOL.md`·`SKILL.md`에 결과 코멘트 마지막 줄 전체 SHA·리뷰 출처 칸·"결과 코멘트는 고치지 말고 새로 올린다" 명시(#3 N1·N2) ③ DEC-017(#4 리뷰 전용 계정 안 쓰기로 함 — 자동 리뷰봇의 리뷰로만 확인) ④ DEC-018 + `settings.json` deny(`gh api` 병합 경로, #2) ⑤ 별도 docs PR: `docs/기획.md` 폐기 안내(#10), 5절 출력 스키마에 `criteria`·`check_method`·`evidence_quote`(#11). 검사: ruff check·format 통과, pytest 66 passed.


## Current State

브랜치 `docs/project-skeleton`. 정확한 커밋·변경 상태는 이 문서가 아니라 `git status --short`·`git log -3`로 먼저 확인한다(이 문서의 상태 기술은 커밋 순간 어긋나기 쉽다).

## Open Issues

- **열린 이슈**: #5(merge-gate 필수 승격 — 선행 조건이던 #4 B안은 폐기, 시점은 10/10 병합 절차 간소화 결정 뒤. 할 일 1번은 PR #7·#8에서 pass 게시로 확인됨). #4(리뷰 전용 계정)는 하지 않기로 하고 닫음([[DEC-017]]), #9(데이터셋 해시 검증, 데이터셋 갱신 시), #10·#11(위 docs PR이 해소).
- **팀 확인 필요**: ① 전사 공통을 나누면 도메인 5개 vs 팀원 4명 — 한 명이 두 도메인을 맡을지, 하위 범위로만 쓸지 ② `tools-and-tips` 공용 여부(본문 일부만 확인) ③ 5절 미결 4건(② 분류 방식, 복수 도메인 허용, 도메인 5개화, `user_type` 분기).
- **실제 질문 사례를 어디서 얻을지 미정(팀 결정, 10/6 회의 안건 1순위)** — 없으면 모델 최종 선택을 못 한다([[DEC-013]]·[[DEC-014]]·[[DEC-016]]). FAQ 정의(질문형 제목 556개 처리)와 도메인별 FAQ 문항 수 실측도 미정.
- 인사·엔지니어링·전사 공통 담당자 미정(10/7까지, `docs/진행계획.md`). 발표자 미정(10/10까지).
- **주의(재발 방지)**: `.gitignore`에 `docs/handbook/*`가 없는 브랜치에서 `uv run ruff format .`을 돌리면 로컬 데이터셋 md가 바뀐다(ruff 0.15가 md 코드블록도 포맷). 지금 main에는 규칙이 있어 안전하다.
- **재발 방지**: 결과 코멘트를 수정(PATCH)하면 `merge-gate`가 무효로 본다 — 틀리면 새 코멘트로 올린다.
- `기획v1.md` 4·6·7절은 뼈대뿐 — 도메인별 PoC(10/6~7) 이후 채운다. 5절은 초안.


## Important Decisions

- [[DEC-010]] 주제를 온보딩 체크리스트 RAG로 전환 (DEC-003 대체)
- [[DEC-011]] 평가 질문 두 세트 분리·도메인당 최소 30문항(→34, DEC-015)·중복 제거 키
- [[DEC-012]] 문서 유래 평가 질문은 FAQ 형태만 (체크리스트·runbook은 정답 문서 후보)
- [[DEC-013]] 상황 서술 세트는 실제 사례 확보 전 점수 제외 + 중복 제거 키에 `chunk_hash`
- [[DEC-014]] `domains[]` 확정, FAQ 점수는 모델 선택의 단독 근거 아님
- [[DEC-015]] 공용 테이블에서 임베딩 분리, 도메인당 최소 평가 문항 34개, AGENTS.md 5절 질문 출처 두 세트
- [[DEC-016]] 실제 질문 출처는 비식별 기록(익명 `source_id`), 실제 질문 세트도 최소 34개

## Failed Attempts

- grilling Q5("미커밋 변경을 어떻게 나눠 커밋할지")를 지난 세션 HANDOFF 기준으로 써 두었는데, 실제로는 그 변경이 이미 `813a772`로 push돼 질문 전제가 틀려 있었다. **근본 원인**: HANDOFF의 Current State를 git 실제 상태와 대조하지 않고 질문을 만들었다. **신호**: 커밋·브랜치·변경 범위에 관한 질문을 사용자에게 던지기 직전 → 먼저 `git status`·`git log -3`을 실행해 전제를 확인하고, 어긋나면 질문을 고쳐 묻는다.
- `npx skills add`로 스킬 자동 설치 시도 → 자동 모드 안전장치가 "외부 코드 실행"으로 차단. **신호**: npx/pip 등으로 외부 패키지를 받아 즉시 실행하는 명령 → 에이전트가 실행하지 말고 사용자에게 `!` 접두사로 직접 실행하도록 안내한다. (`mattpocock-skills` 플러그인은 user 범위로 설치·활성화돼 있음을 `claude plugin list`로 확인함.)

## Relevant Files

- `docs/기획v1.md` — 메인 기획 문서. 3절 "PoC 공통 기준" 표와 "전사 공통 분할안" 소절이 이번 변경
- `.agent/DECISIONS.md` — DEC-010~016 (평가·스키마·개인정보 규칙은 DEC-011~016)
- `docs/진행계획.md`(+`쉬운버전/`) — 팀 일정·담당자 미정 항목
- `AGENTS.md` 5절 — 상황 서술 세트와의 충돌 여부 확인 대상
- `docs/MERGE_PROTOCOL.md` — 병합 전 게이트
- `docs/handbook/content/handbook/` — 데이터 원문(gitignore). 실측은 폴더별 `find -name '*.md'` + 바이트÷4

## Next Action

1. 이슈 정리 PR 2개: 리뷰 확인 → 새 지적 처리 → `pre-merge-check` → 사용자 병합 지시 대기
2. 10/6 회의: 실제 질문 수집 경로·목표 수, 담당자·발표자, 팀 확인 항목
3. 영업·지원 PoC(우지훈): 프로토타입, 기술 스택, FAQ 문항 수 실측


## Definition of Done

`기획v1.md` 1~7번 + 발표 전 점검까지 전부 실제 내용(뼈대 아님)으로 채워지고, 모든 수치가 `scripts/fetch_handbook_dataset.py`로 재현된 이 저장소 데이터에서 나온 값이며, 발표 전 점검 체크리스트 항목을 전부 체크할 수 있는 상태.

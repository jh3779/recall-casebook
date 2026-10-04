# Agent Handoff

_갱신: 2026-10-04_

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

2026-10-03 이슈 정리: ① `merge_gate.py`가 변경 요청·미해결 스레드를 수정된 결과 코멘트보다 먼저 failure로 표시(테스트 2개 먼저, #3 O1) ② `MERGE_PROTOCOL.md`·`SKILL.md`에 결과 코멘트 마지막 줄 전체 SHA·리뷰 출처 칸·"결과 코멘트는 고치지 말고 새로 올린다" 명시(#3 N1·N2) ③ DEC-017(#4 리뷰 전용 계정 안 쓰기로 함 — 자동 리뷰봇의 리뷰로만 확인) ④ DEC-018 + `settings.json` deny(`gh api` 병합 경로, #2) ⑤ 별도 docs PR: `docs/기획.md` 폐기 안내(#10), 5절 출력 스키마에 `criteria`·`check_method`·`evidence_quote`(#11). 검사: ruff check·format 통과, pytest 66 passed.


## Current State

브랜치 `docs/project-skeleton`. 정확한 커밋·변경 상태는 이 문서가 아니라 `git status --short`·`git log -3`로 먼저 확인한다(이 문서의 상태 기술은 커밋 순간 어긋나기 쉽다).

## Open Issues

- **할 일 목록 — GitHub 이슈에서 내부로 이전함(2026-10-04, 사용자 결정)**: 열려 있던 이슈 #5·#9·#14를 닫고 내용을 아래로 옮겼다(이슈는 삭제하지 않고 닫기만 했다 — DEC-017·DEC-018 등이 이슈 번호를 인용해서 번호와 토론 기록을 남겨 둠). #10·#11은 PR #13 병합 시 자동으로 닫힌다. 새 할 일은 이슈 대신 여기에 적는다.
  1. **`merge-gate` 필수 체크 승격** (구 #5): 현재 필수 체크는 `lint-and-test`·`check-branch-name`·`validate-pr-title`·`pr-verify` 4개. 선행 조건이던 리뷰 전용 계정(B안)은 폐기([[DEC-017]])라 **시점만 정하면 된다 — 10/10 병합 절차 간소화 결정 뒤 권고**. 주의: ruleset에 `bypass_actors`가 없어 사소한 PR도 리뷰와 ✅ 결과 코멘트가 있어야 병합되고, push마다 리뷰를 다시 기다려야 한다. 적용은 `gh api`로 ruleset(`main 보호`)에 `merge-gate` 한 줄 추가, 문제가 생기면 같은 호출로 뺀다. 할 일 1번(실제 상태 게시 확인)은 PR #7·#8·#12·#13에서 pass 게시로 완료. GitHub Review 제출 시 재판정은 현행 유지(재판정 코멘트), 팀원이 Review 기능을 쓰기 시작하면 `schedule` 재판정 검토.
  2. **데이터셋 검증 강화** (구 #9): `scripts/fetch_handbook_dataset.py`는 md 4,612개 개수만 확인한다. 전체 커밋 SHA(7자리 대신), 정렬한 `상대 경로 + 파일 해시` 목록의 전체 해시 검증, 내용 하나만 바꾸고 개수 유지 시 실패하는 테스트, 머리말의 "34개 핵심 부서" 검증 또는 문구 수정. 추가 약점: 다운로드 타임아웃·재시도 없음, `verify()`·`remove_non_doc_files()` 단위 테스트 없음. 데이터셋을 갱신할 때 처리.
  3. **`gh api` 병합 deny 패턴 실제 차단 검증** (구 #14): `Bash(gh api*/pulls/*/merge*)`·`Bash(gh api*mergePullRequest*)`가 안전한 더미 명령(`gh api repos/o/r/pulls/0/merge -X PUT`)을 호출 전에 막는지, `gh api graphql` 리뷰 스레드 조회·`gh pr view --json mergeStateStatus`는 안 막는지 확인하고 [[DEC-018]] "영향"을 갱신. 병합을 막지 않는 항목.
  4. **옛 기획 폐기 안내·출력 스키마** (구 #10·#11): `docs/기획.md` 폐기 안내와 5절 출력 스키마([[DEC-019]])는 PR #13이 처리. `docs/기획_뼈대.md`는 이미 첫머리에 폐기 안내가 있어 그대로 둠.
  5. **CI에 자동 리뷰 넣기(Codex)** (새 항목): 지금은 서버(M1)의 디스코드 봇이 리뷰한다. 사용자가 CI에서 Codex로 진행하기로 정함 — 공식 액션 `openai/codex-action` 또는 `codex exec`(CLI) 모두 가능. 결정 대기: 방식(액션 권장 vs CLI 직접), 모델·월 예산, 인증(API 키 vs 구독 로그인 가능 여부 확인), 시점(10/12 이후 권고, 비용 0인 1단계는 언제든). 근거·워크플로 골격·리뷰 프롬프트 초안·비용 추정은 바탕화면 `CI_자동리뷰_검토_2026-10-03.md`. 구현 시 `pull_request_target` + main 체크아웃 + PR diff 파일 전달(DEC-009 원칙), `merge-gate`가 허용 작성자(`github-actions[bot]`)를 보게 수정, 기존 봇과 병행 후 전환, 실호출 전 사용자 비용 승인(AGENTS.md 7절).
  6. **서버 리뷰봇 토큰 종류 확인** (새 항목, [[DEC-017]] 영향): 지금 봇이 소유자 전체 권한 토큰을 쓰면 이 저장소 PR·이슈 코멘트 권한만 가진 fine-grained 토큰으로 줄이는 것을 서버에서 검토.
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

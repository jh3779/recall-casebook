# Agent Handoff

_갱신: 2026-10-02_

## Current Objective

PR #7(`docs/project-skeleton` → `main`)에 grilling 결과(Q1~Q5: 평가 기준·도메인 매핑)를 반영한 `기획v1.md` 변경을 커밋·push하고, 새 커밋 기준 자동 리뷰를 받아 `docs/MERGE_PROTOCOL.md` 게이트를 전부 ✅로 만드는 것.

## Current Phase

없음 — `PROJECT_CONTEXT.md`에 Phases 로드맵이 아직 없다. 느슨하게는 "기획 단계"(10/2 주제 결정 ~ 10/6-7 도메인별 PoC 전).

## Completed

- PR #7 오픈, Codex 자동 리뷰 "머지 전 필수 보완" 5건을 전부 반영해 커밋 `813a772`로 push함(AGENTS.md 2·5절 재작성, 고통 포인트 `(가설)` 표시, 34개 부서↔도메인 매핑 초안, `scripts/fetch_handbook_dataset.py`, stale 문서 정리).
- grilling Q1~Q5를 사용자 인터뷰(AskUserQuestion)로 결정 — 다섯 개 모두 권장안 채택. 그중 평가 규칙·중복 제거 키는 [[DEC-011]]로 기록.
- `docs/기획v1.md` 3절 반영:
  - "PoC 공통 기준" 표: 중복 제거 키 `(source_path, commit_sha, heading_path)` 명시(코퍼스·최소 DB 행), "평가 질문 유형"(문서 유래 / 상황 서술, 합산 안 함) 행, "평가 질문 최소 개수"(도메인당 30, 미달 시 문항별 성공/실패 목록) 행 추가.
  - "전사 공통 분할안 (제안)" 소절: 문화·리더십 9개 폴더 747,230 토큰 / 지원 부서·내부 IT 6개 폴더 1,414,776 토큰 / `upstream-studios` 공용(224,901). 공용 2순위 후보 `tools-and-tips`.

## Last Work

grilling 반영 직후 체크포인트. 검사 결과: `uv run ruff check .` 통과, `uv run ruff format --check .` 통과(25 files), `uv run pytest` 59 passed. 추가한 문장은 `scripts/ci/pr_checks.py:31`의 판정 문구 패턴에 걸리지 않음을 grep으로 확인.

## Current State

`git status --short` (2026-10-02 체크포인트 시점):
```
 M .agent/DECISIONS.md
 M .agent/HANDOFF.md
 M .agent/SESSION_LOG.md
 M docs/기획v1.md
```
`docs/기획v1.md`는 +21/-2줄. 브랜치 `docs/project-skeleton`은 origin과 같은 `813a772`까지 push된 상태이며, 위 변경은 **커밋 전**이다. 커밋 메시지 안: `docs: 기획v1 평가 기준·도메인 매핑 grilling 결과 반영`.

## Open Issues

- **커밋·push 대기** — 사용자 승인 후 진행. push하면 최신 커밋이 바뀌므로 리뷰봇 리뷰를 다시 받아야 한다.
- **팀 확인 필요 4건**: ① 상황 서술 평가 세트가 AGENTS.md 5절("평가셋을 지어내지 않는다")과 충돌하는지 ② 전사 공통을 나누면 도메인 5개 vs 팀원 4명 — 한 명이 두 도메인을 맡을지, 하위 범위로만 쓸지 ③ `domain` 컬럼 배열화 ④ `tools-and-tips` 공용 여부(본문 미확인).
- 실측에서 확인: 전사 공통은 폴더 수(16)는 최다지만 토큰(2,386,907)은 엔지니어링(4,490,880)·영업·지원(3,223,880)보다 작다 — 분할 근거는 분량이 아니라 성격 혼재.
- Codex 리뷰 "선택 개선" 2건: ① `DOCUMENTS.md` 관련 — 근거 없는 지적이라 반박 처리 예정 ② `기획v1.md` H1 제목·마지막 줄바꿈 — 미반영.
- 인사·엔지니어링·전사 공통 담당자 미정(10/7까지, `docs/진행계획.md`).
- `기획v1.md` 4~7절은 뼈대뿐 — 도메인별 PoC(10/6~7) 이후 채운다.
- `PROJECT_CONTEXT.md` Goal·Tech Stack이 옛 주제 기준일 수 있음(DEC-010 "영향" 항목) — 갱신 여부 미확인.

## Important Decisions

- [[DEC-010]] 주제를 온보딩 체크리스트 RAG로 전환 (DEC-003 대체)
- [[DEC-011]] 평가 질문 두 세트 분리·도메인당 최소 30문항·중복 제거 키

## Failed Attempts

- grilling Q5("미커밋 변경을 어떻게 나눠 커밋할지")를 지난 세션 HANDOFF 기준으로 써 두었는데, 실제로는 그 변경이 이미 `813a772`로 push돼 질문 전제가 틀려 있었다. **근본 원인**: HANDOFF의 Current State를 git 실제 상태와 대조하지 않고 질문을 만들었다. **신호**: 커밋·브랜치·변경 범위에 관한 질문을 사용자에게 던지기 직전 → 먼저 `git status`·`git log -3`을 실행해 전제를 확인하고, 어긋나면 질문을 고쳐 묻는다.
- `npx skills add`로 스킬 자동 설치 시도 → 자동 모드 안전장치가 "외부 코드 실행"으로 차단. **신호**: npx/pip 등으로 외부 패키지를 받아 즉시 실행하는 명령 → 에이전트가 실행하지 말고 사용자에게 `!` 접두사로 직접 실행하도록 안내한다. (`mattpocock-skills` 플러그인은 user 범위로 설치·활성화돼 있음을 `claude plugin list`로 확인함.)

## Relevant Files

- `docs/기획v1.md` — 메인 기획 문서. 3절 "PoC 공통 기준" 표와 "전사 공통 분할안" 소절이 이번 변경
- `.agent/DECISIONS.md` — DEC-011 신규
- `docs/진행계획.md`(+`쉬운버전/`) — 팀 일정·담당자 미정 항목
- `AGENTS.md` 5절 — 상황 서술 세트와의 충돌 여부 확인 대상
- `docs/MERGE_PROTOCOL.md` — 병합 전 게이트
- `docs/handbook/content/handbook/` — 데이터 원문(gitignore). 실측은 폴더별 `find -name '*.md'` + 바이트÷4

## Next Action

1. 사용자 승인 후 위 4개 파일을 커밋 하나로 묶어 push (PR #7에 반영)
2. 리뷰봇의 새 리뷰 확인 → `pre-merge-check` 스킬로 게이트 점검 → 사용자에게 병합 여부 확인
3. 팀 확인 4건(Open Issues)과 34개 부서↔도메인 매핑을 팀과 확정(담당자 확정 10/7과 함께)

## Definition of Done

`기획v1.md` 1~7번 + 발표 전 점검까지 전부 실제 내용(뼈대 아님)으로 채워지고, 모든 수치가 `scripts/fetch_handbook_dataset.py`로 재현된 이 저장소 데이터에서 나온 값이며, 발표 전 점검 체크리스트 항목을 전부 체크할 수 있는 상태.

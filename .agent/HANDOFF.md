# Agent Handoff

_갱신: 2026-10-02_

## Current Objective

`docs/기획v1.md` — 온보딩 체크리스트 RAG(GitLab 핸드북 기반) 기획서를 작성 중. 신규 입사자·부서 이동자 대상. 지금은 전체 문서(기획v1.md·진행계획.md·.agent/*)의 상호 정합성(경로·수치·섹션 번호)을 맞추는 중.

## Current Phase

없음 — `PROJECT_CONTEXT.md`에 Phases 로드맵이 아직 정의돼 있지 않다. 느슨하게는 "기획 단계"(10/2 주제 결정 완료 ~ 10/6-7 프로토타입 전).

## Completed

- **기획v1.md 1~3절**: 고통 포인트(1~8)·RAG 필요성(9~14, 번호는 문서 전체 연속번호)·데이터셋 실측(34개 핵심 부서·4,612개 md·추정 약 1,175만 토큰) 작성 완료. 4~7절(기술스택·아키텍처·개선사항·어려움)은 도메인별(인사/엔지니어링/전사 공통/영업·지원) 뼈대만.
- **데이터셋 정리**: 비문서 파일 13개(핸드북.zip 등) 삭제, 73MB→56MB. 사용자가 폴더를 `docs/GitLab_Data-main` → `docs/handbook`으로 직접 이름 변경. `docs/handbook/README.md` 작성(구조·실측치·재현 방법).
- **PR #6 닫음**: 옛 초안(`기획_온보딩.md`, 68건·11개 부서)을 `기획v1.md`로 대체한다는 코멘트와 함께.
- **커밋 2개 push 완료** (`docs/project-skeleton`): `f7ff989`(기획v1 1~3절+뼈대, DEC-010, gitignore), `7630748`(진행계획.md 이식).
- **`docs/onboarding-plan` 브랜치 조사**: 주제 후보가 실제 4개였음을 확인(결함 선례·문서 구조화·온보딩·코드 온보딩) + 팀 진행 계획 문서 발견. `진행계획.md`(+쉬운버전)는 커밋, 기각된 후보 3종 중 `기획_문서구조화.md`·`기획_코드온보딩.md`는 삭제, `기획_결함선례.md`는 사용자 바탕화면(`~/Desktop/결함선례_기획/`)으로 이동(모두 사용자 지시).
- **`진행계획.md`(+쉬운버전) 재작성**: 10/2 결정 결과(주제 확정)로 2절 교체, 역할표에 영업·지원=우지훈 반영, 위험요소 갱신.
- **AGENTS.md 갱신**: 8절에 "파트 작업은 문서 작성까지가 마무리" 원칙 추가, 1절 프로젝트 한 줄 설명을 온보딩 RAG로, 0절 읽기 순서를 `기획v1.md`로 교체.
- **전체 문서 정합성 점검(이번 체크포인트)**: `docs/GitLab_Data-main` 잔존 경로, "88건·15개 부서" 잔존 수치, `발표 전 점검`의 끊어진 번호 참조(8번→존재 안 함), DEC-010의 기각 문서 설명 불일치, `.gitignore`가 `docs/handbook/README.md`까지 가려버리던 문제를 찾아 수정. "유사 서비스 조사" 섹션은 사용자 결정으로 **복원하지 않고** 참조 번호만 정리.

## Last Work

사용자 요청 "전체 문서 정합성 확인 후 기본 틀만 어느정도 생성해줘"에 따라 위 정합성 점검·수정을 실행 중. `.gitignore`를 `docs/handbook/*` + `!docs/handbook/README.md`로 바꿔 README만 추적되게 고쳤고, `기획v1.md`·`.agent/PROJECT_CONTEXT.md`·`.agent/DECISIONS.md`의 stale 경로/수치/섹션번호를 수정했다. 이 HANDOFF.md 자체도 그 일환으로 갱신 중.

## Current State

`git status --short --untracked-files=all` 기준 (데이터셋 `docs/handbook/content/`는 ignore돼 제외):
```
 M .agent/DECISIONS.md
 M .agent/PROJECT_CONTEXT.md
 M .gitignore
 M AGENTS.md
 M docs/기획v1.md
 M docs/쉬운버전/진행계획.md
 M docs/진행계획.md
?? docs/handbook/README.md
```
브랜치: `docs/project-skeleton` (origin에 `f7ff989`·`7630748`까지 push됨, 위 변경은 아직 커밋 전). `docs/기획.md`(옛 주제, 커밋됨)·`docs/기획_뼈대.md`(이전 버전, 커밋됨, 역사 기록용이라 수정 안 함)는 그대로.

## Open Issues

- 위 변경사항(.gitignore·AGENTS.md·기획v1.md·PROJECT_CONTEXT.md·DECISIONS.md·진행계획.md류·handbook/README.md) **아직 커밋 안 됨** — 사용자 확인 후 커밋할 것.
- 4~7절(기술스택·아키텍처·개선사항·어려움)은 여전히 뼈대뿐 — 도메인별 PoC(10/6~7) 이후 채운다.
- 인사·엔지니어링·전사 공통 파트 담당자가 아직 미정(10/7까지, `진행계획.md` 참고).
- 토큰 수는 글자수÷4 경험칙 추정치. `tiktoken` 설치 시 pyproject.toml·uv.lock 변경 필요 — 사용자 확인 대기.
- AGENTS.md 2절("서비스 원칙")이 아직 Compliance 전용 예시(40 CFR 63.xxxx(a) 인용 형식, 조문 서명 비유)로 남아 있다 — 원칙 자체(판정 안 함·근거·추적성)는 온보딩 주제에도 그대로 승계됐지만, 예시 문구는 아직 안 고쳤다.

## Important Decisions

- [[DEC-010]] 주제를 온보딩 체크리스트 RAG로 전환, 이번 체크포인트에서 Alternatives 설명을 실제 결과(삭제/이동 반영)로 갱신 (`.agent/DECISIONS.md`)
- DEC-003 Superseded by DEC-010

## Failed Attempts

해당 없음 — 이번 국면도 문서 작성·정합성 수정 위주라 폐기한 접근이 없었다.

## Relevant Files

- `docs/기획v1.md` — 메인 기획 문서
- `docs/진행계획.md`(+`쉬운버전/`) — 팀 일정·역할·위험 요소
- `docs/handbook/README.md`, `docs/handbook/content/`(ignore됨) — 데이터셋
- `.agent/PROJECT_CONTEXT.md`, `.agent/DECISIONS.md` — 이번에 같이 갱신함

## Next Action

1. 이번 정합성 수정 커밋·push할지 사용자에게 확인
2. AGENTS.md 2절 예시를 온보딩 주제에 맞게 고칠지 확인 (Open Issues 참고)
3. 도메인별 PoC 착수 시 기획v1.md 4~7절 채우기 시작

## Definition of Done

`기획v1.md` 1~7번 + 발표 전 점검까지 전부 실제 내용(뼈대 아님)으로 채워지고, 모든 수치가 이 저장소 데이터(`docs/handbook/`)에서 직접 재현된 값이며, 발표 전 점검 체크리스트 항목을 전부 체크할 수 있는 상태.

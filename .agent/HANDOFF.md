# Agent Handoff

_갱신: 2026-10-02_

## Current Objective

`docs/기획v1.md` — 온보딩 체크리스트 RAG(GitLab 핸드북 기반) 기획서를 7단계 틀로 작성 중. 신규 입사자·부서 이동자 대상.

## Current Phase

없음 — `PROJECT_CONTEXT.md`에 Phases 로드맵이 아직 정의돼 있지 않다. 느슨하게는 "기획 단계"(10/2 주제 결정 ~ 10/6-7 프로토타입 전).

## Completed

- **1절 문제 정의**: 문제 배경 + 신규 입사자(1~4)·부서 이동자(5~7)·공통(8) 고통 포인트를 번호 매겨 작성. 5번은 `people-group/promotions-transfers.md:701` 근거 인용 포함.
- **2절 RAG가 필수적인 이유**: 1~6번 작성. 1번은 사용자 요청으로 파인튜닝 대비 설명을 빼고 "갱신 지연 없이 반영" 중심으로 재작성.
- **3절 GitLab 데이터셋 실측 결과**: `docs/GitLab_Data-main/handbook/content`를 직접 측정. 전체 4,625개 파일(md 4,612개), `handbook/` 하위 36개 디렉토리 중 조직 부서가 아닌 스텁 2개(`job-description-library`, `teamops`) 제외한 **핵심 부서 34개**. 부서별 추정 토큰 수(글자수÷4 경험칙) 표 작성.
- **4~8절 + 발표 전 점검**: 뼈대(표 헤더·가이드 문구)만 작성. 4번(유사 서비스 조사·차별점)·5번(기술 스택)은 **도메인 4개(인사/엔지니어링/전사 공통/영업·지원)별 하위 섹션**으로 분리 — 사용자가 "도메인마다 달라질 수 있다"고 지적해 반영.
- **DECISIONS.md**: DEC-010 추가 — 주제를 Compliance AI(참고 레포 기반)에서 온보딩 체크리스트 RAG(GitLab 핸드북)로 전환했음을 기록. DEC-003은 Superseded by DEC-010 처리.

## Last Work

사용자가 "기술 스택과 유사 서비스 조사·차별점도 도메인마다 달라질 수 있다"고 지적 → `기획v1.md` 4·5절을 단일 표에서 인사/엔지니어링/전사 공통/영업·지원 4개 하위 섹션(각자 표)으로 재구성. 그 직후 사용자가 "현재 내용 기록해줘"라고 해서 이 체크포인트를 실행 중.

## Current State

`git status --short` 기준:
```
 M CLAUDE.md                         (trailing newline 1줄 — 내 작업 아님, 원인 미상)
?? docs/GitLab_Data-main/            (GitLab 핸드북 데이터셋, 미추적)
?? docs/기획_뼈대.md                  (이전 버전 기획 틀, 미추적)
?? docs/기획v1.md                     (현재 작업 중인 기획서, 미추적)
```
브랜치: `docs/project-skeleton`. 커밋 없음 — 전부 untracked/unstaged 상태. `docs/기획.md`(옛 주제 7단계 문서, 커밋됨)는 그대로 둠.

## Open Issues

- `PROJECT_CONTEXT.md`의 Goal·Tech Stack이 아직 옛 주제(Compliance AI, 참고 레포 기준) 그대로다 — DEC-010에 영향으로 기록해뒀고, 다음 체크포인트 전 갱신 필요.
- `기획v1.md` 2절 4번 항목에 옛 수치("88건·15개 부서")가 남아있다 — 3절 실측치(36개 디렉토리·4,612개 md)와 불일치. 사용자에게 1차 보고했으나 아직 정정 지시는 없음.
- 4~8절은 뼈대뿐 실제 내용이 없다 — 팀 PoC(10/6~7) 이후 채울 예정.
- 토큰 수는 글자수÷4 경험칙 추정치다. `tiktoken` 미설치로 정밀 측정 안 함(설치 시 pyproject.toml·uv.lock 변경 — 사용자 확인 필요).
- `docs/기획.md`(옛 주제)·`docs/기획_뼈대.md`(이전 버전)와 `docs/기획v1.md`(현재 버전) 세 문서의 보관/정리 방향이 정해지지 않았다.

## Important Decisions

- [[DEC-010]] 주제를 온보딩 체크리스트 RAG로 전환 (`.agent/DECISIONS.md`)
- DEC-003 Superseded by DEC-010

## Failed Attempts

해당 없음 — 이번 국면은 문서 작성·데이터 실측 위주라 폐기한 접근이 없었다.

## Relevant Files

- `docs/기획v1.md` — 현재 작업 중인 메인 기획 문서
- `docs/GitLab_Data-main/handbook/content/` — 데이터 원문(측정 대상)
- `docs/기획.md`, `docs/기획_뼈대.md` — 옛 버전(참고용)
- `.agent/DECISIONS.md` — DEC-010

## Next Action

1. `기획v1.md` 2절 4번의 "88건·15개 부서" 옛 수치를 3절 실측치로 정정할지 사용자에게 확인
2. `.agent/PROJECT_CONTEXT.md` Goal·Tech Stack을 온보딩 RAG 주제로 갱신
3. 도메인별(인사/엔지니어링/전사 공통/영업·지원) PoC 착수 시 4·5절 표를 실제 내용으로 채우기 시작

## Definition of Done

`기획v1.md` 1~8번 + 발표 전 점검까지 전부 실제 내용(뼈대 아님)으로 채워지고, 모든 수치가 참고 레포 인용이 아니라 **이 저장소 데이터(`docs/GitLab_Data-main/`)에서 직접 재현**된 값이며, 발표 전 점검 체크리스트 항목을 전부 체크할 수 있는 상태.

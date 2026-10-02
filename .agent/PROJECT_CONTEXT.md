# Project Context

## Goal

LG CNS AI Campus RAG 팀 프로젝트 — **온보딩 체크리스트 RAG**. GitLab 공개 핸드북을 데이터로 써서, 신규 입사자·부서 이동자가 새 업무를 맡았을 때 적용될 수 있는 온보딩 항목 후보와 확인 기준을 근거 문서와 함께 정리해 준다. 판정("적용됩니다/안 됩니다")은 하지 않는다. 상세: `docs/기획v1.md` (DEC-010으로 주제 전환, 옛 주제 문서는 `docs/기획.md`에 참고용으로 남아 있음). <!-- principle-ok: 금지 문구를 설명하기 위해 인용한 메타 문장, 실제 판정 필드 아님 -->

## Current Product Direction

- 데이터: GitLab 공개 핸드북 스냅샷([suuuuuuungho/GitLab_Data](https://github.com/suuuuuuungho/GitLab_Data) 커밋 `0ab0299`, 로컬 `docs/handbook/content`, `.gitignore`됨). 실측: 전체 4,612개 파일(전부 md — 비문서 파일 13개는 정리함), `handbook/` 하위 36개 디렉토리 중 핵심 부서 34개(스텁 2개 제외), 추정 약 1,175만 토큰(글자수÷4 경험칙). 상세: `docs/handbook/README.md`.
- 대상: 신규 입사자 + 부서 이동자. 근거: 핸드북 `people-group/promotions-transfers.md:701`(직무 전환자도 새 직무 온보딩 완료 필요).
- 도메인 4개(인사/엔지니어링/전사 공통/영업·지원)로 나눠 각자 최소 DB + RAG PoC를 먼저 만들고, 그 결과로 전체 방향을 정한다(2026-10-02 팀 회의 결론).
- 서비스 원칙(옛 주제에서 승계): ① 판정하지 않는다 ② 근거 없는 말은 하지 않는다 ③ 추적 가능해야 한다.
- 미결: 도메인별 기술 스택(`기획v1.md` 4번), 아키텍처 설계(5번), before/after 수치(6번) — 전부 뼈대만 있고 팀 PoC(10/6~7) 이후 채운다. (기획v1.md에는 "유사 서비스 조사" 단계가 따로 없다 — 의도적으로 뺀 구조다.)

## Team

- 4명: 박성호·박예원·우지훈(@jh3779)·이승노. 발표일 2026-10-20. 파트 배정(2026-10-02): 인사·엔지니어링·전사는 다른 팀원, 우지훈은 영업+지원(Sales·Support). GitHub 아이디가 확정되면 `.github/CODEOWNERS`를 채운다.

## Tech Stack

- 미확정 — 도메인별 PoC(기획v1.md 4번) 결과를 보고 정한다. 옛 주제(Compliance AI) 때 썼던 Python·PostgreSQL·Kanon 2·BM25+RRF·gpt-5-mini 조합은 참고 레포 스택일 뿐, 이번 주제에 그대로 쓸지는 결정된 바 없다.

## Tooling

- Python 3.12 + **uv**(의존성·가상환경, DEC-004), lefthook(git 훅), ruff + pytest, CI `ci.yml`.
- 에이전트 행동강령 원본은 `AGENTS.md`, `CLAUDE.md`는 import만 (DEC-005).

## Constraints

- 비밀키·토큰은 절대 커밋하지 않는다 (`.env`만 사용, lefthook pre-commit이 차단).
- main 직접 push 금지 — 단명 브랜치 → PR → squash merge (`CONTRIBUTING.md`).

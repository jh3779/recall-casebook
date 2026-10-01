# Project Context

## Goal

LG CNS AI Campus RAG 팀 프로젝트 — **미국 제조업 공장 Compliance AI**. Title V 허가를 받은 미국 중소 제조 공장의 환경 담당자가 서류(반기 보고·연간 인증·초과 신고·갱신)를 쓸 때, 적용될 수 있는 조항 후보와 확인 기준을 최신 근거 조문(40 CFR Part 63)과 함께 정리해 준다. 상세: `docs/기획.md`.

## Current Product Direction

- 기획 초안은 참고 레포 [suuuuuuungho/US-Factory-Compliance-Service](https://github.com/suuuuuuungho/US-Factory-Compliance-Service) `main@0103ea0`(2026-09-30)의 `1_Project_full.md`를 7단계 템플릿에 옮긴 것이다 (DEC-003). **수치는 참고 레포 실측값이며 이 저장소에서 재현하지 않았다.**
- 서비스 원칙 2개(참고 레포에서 승계): ① 판정하지 않는다 — 답변 JSON에 `applies`·`verdict` 필드 없음 ② 근거 없는 말은 하지 않는다.
- 미결: 상용 유사 서비스 조사(`docs/기획.md` 2번), 기술 스택 선택 이유(4번 빈칸), 참고 레포와의 관계(이어서 개발 / 새로 구현 / 범위 변경).

## Team

- 우지훈(@jh3779) + 팀원 미확정. 팀원 GitHub 아이디가 확정되면 `.github/CODEOWNERS`를 채운다.

## Tech Stack

- 참고 레포 기준: Python · PostgreSQL(Supabase) · FastAPI(Render) · Next.js(Vercel) · Kanon 2 임베더/리랭커 · BM25+RRF · gpt-5-mini. 이 팀에서 그대로 쓸지는 미확정.

## Tooling

- Python 3.12 + **uv**(의존성·가상환경, DEC-004), lefthook(git 훅), ruff + pytest, CI `ci.yml`.
- 에이전트 행동강령 원본은 `AGENTS.md`, `CLAUDE.md`는 import만 (DEC-005).

## Constraints

- 비밀키·토큰은 절대 커밋하지 않는다 (`.env`만 사용, lefthook pre-commit이 차단).
- main 직접 push 금지 — 단명 브랜치 → PR → squash merge (`CONTRIBUTING.md`).

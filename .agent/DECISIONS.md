# Decisions

## DEC-001: 다른 프로젝트와 동일한 GitHub Flow 협업 규칙 채택
- **Decision**: branch-strategy-kit 기반 단명 브랜치 전략(`main` 단일 영구 브랜치, `<type>/<name>` 8종 접두어, Conventional Commits PR 제목, squash merge)을 채택한다.
- **Reason**: file-converter·SACHO·project-human-p 등 기존 저장소와 규칙을 통일해 팀원·봇(리뷰봇·플랜봇)이 동일하게 동작하게 한다.
- **Alternatives**: Git Flow(develop 브랜치 유지) — 소규모 단기 프로젝트에 과함.
- **Status**: Accepted
- **Date**: 2026-10-01

## DEC-002: git 훅은 pre-commit 프레임워크 대신 lefthook
- **Decision**: 로컬 git 훅을 lefthook(`lefthook.yml` + `scripts/check-*.sh`)으로 관리한다. pre-commit: 비밀 파일·개인키·1MB 초과 차단 / commit-msg: Conventional Commits / pre-push: main 직접 push 차단 → 브랜치명 (piped).
- **Reason**: 사용자 지시. SACHO와 같은 방식이며, 언어 무관 단일 바이너리라 Python 환경 없이 설치된다.
- **Alternatives**: pre-commit 프레임워크 — 초기 셋팅에서 썼다가 교체.
- **Status**: Accepted
- **Date**: 2026-10-01

## DEC-003: 기획 초안은 US-Factory-Compliance-Service 기반
- **Decision**: `docs/기획.md` 초안을 [suuuuuuungho/US-Factory-Compliance-Service](https://github.com/suuuuuuungho/US-Factory-Compliance-Service) `main@0103ea0`의 `1_Project_full.md` 내용으로 채운다. 원문에 근거 없는 칸은 "아직 없음"으로 둔다.
- **Reason**: 사용자 지시("일단은 이 레포 확인해서"). 잠정 결정 — 팀 검토 후 범위가 바뀔 수 있다.
- **Alternatives**: 새 주제로 기획 — 미검토.
- **Status**: Proposed
- **Date**: 2026-10-01

## DEC-004: Python 의존성·가상환경은 uv로 관리
- **Decision**: Python 3.12(`.python-version`) + uv(`pyproject.toml`·`uv.lock`, `required-version >=0.12.5`). `package = false`. 런타임 의존성은 스택 확정 전까지 비워 두고 dev 그룹에 pytest·ruff만 둔다. CI는 `uv sync --locked`.
- **Reason**: 사용자 지시(RAG 개발 환경). career-radar·file-converter와 같은 방식이고, lock 파일로 팀원 간 환경을 똑같이 맞출 수 있다.
- **Alternatives**: pip + requirements.txt (참고 레포 방식) — lock·Python 버전 관리가 약함. Poetry — 팀 내 사용 사례 없음.
- **Status**: Accepted
- **Date**: 2026-10-01

## DEC-005: 에이전트 행동강령은 AGENTS.md 원본 + CLAUDE.md import
- **Decision**: 규칙 원본을 `AGENTS.md`에 두고 `CLAUDE.md`는 `@AGENTS.md`로 불러온 뒤 Claude 전용 내용만 덧붙인다. 팀 공유 권한은 `.claude/settings.json`.
- **Reason**: Claude Code·Codex 등 여러 에이전트가 같은 규칙을 읽게 하고, 두 파일이 서로 어긋나는 것을 막는다 (maple-helper와 같은 구조).
- **Alternatives**: CLAUDE.md·AGENTS.md를 각각 작성 (project-human-p 방식) — 두 파일이 실제로 달라져 있었음(`diff` 확인).
- **Status**: Accepted
- **Date**: 2026-10-01

## DEC-006: main 룰셋 — PR·필수 체크 강제, 필수 승인 0명
- **Decision**: 룰셋 `main 보호`로 삭제·force push를 막고, PR(squash만)과 필수 상태 체크 3개(`lint-and-test`·`check-branch-name`·`validate-pr-title`)를 강제한다. 필수 승인 수는 0명, bypass 없음.
- **Reason**: 팀원이 아직 합류하지 않아 승인 1명 이상이면 본인 PR을 영구히 병합할 수 없다(작성자 승인은 세지 않음). lanecoach-ai DEC-006과 같은 판단. 규칙 위반·테스트 실패는 체크로 막는다.
- **Alternatives**: 승인 1명 + CODEOWNERS 리뷰 필수 — 팀원 초대·수락 후 재검토.
- **Status**: Accepted
- **Date**: 2026-10-01

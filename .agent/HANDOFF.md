# Agent Handoff

_갱신: 2026-10-01_

## Current Objective

협업용 저장소 초기 셋팅 + 기획 초안 + uv 개발환경 + 에이전트 행동강령.

## Current Phase

P0 — 저장소 셋팅 완료·GitHub 업로드 완료(`jh3779/LG_CNS_RAG_main`, private), 기획 초안은 팀 검토 전.

## Completed

- 협업 설정: README, CONTRIBUTING(GitHub Flow·브랜치/PR 규칙·lefthook 설치), PR 템플릿, CODEOWNERS(빈 틀), CI 워크플로 5개(브랜치명·PR 제목 검사, 리뷰봇·플랜봇 알림, stale 브랜치 정리), .gitignore/.gitattributes/.editorconfig, .env.example
- git 훅: pre-commit 프레임워크 대신 **lefthook** (DEC-002). `lefthook.yml` + `scripts/check-{staged,commit-msg,branch}.sh`. 로컬 `lefthook install` 완료, 스크립트 동작 수동 확인함.
- uv 셋팅 (DEC-004): `pyproject.toml`(런타임 의존성 비움, dev: pytest·ruff), `.python-version` 3.12, `uv.lock`, `tests/test_smoke.py`, CI `ci.yml`. lefthook pre-commit에 ruff 추가. 로컬에서 `uv sync` → ruff·pytest 통과 확인. 안내서 `docs/개발환경.md`.
- 에이전트 행동강령 (DEC-005): `AGENTS.md`(원본) + `CLAUDE.md`(@import + Claude 전용 보충) + `.claude/settings.json`(팀 공유 권한: uv/git 읽기 허용, .env 읽기·force push·PR 병합·pip install 차단).
- 전체 셋팅 안내서 `docs/시작하기.md`: 도구 설치 → 저장소 받기 → 작업 흐름 → 자동 검사 → 에이전트 → 관리자 최초 설정(9절, 첫 push·병합 방식·룰셋·초대 명령 포함).
- `docs/기획.md`: 참고 레포 기반으로 7단계 채움 (DEC-003). 2번 상용 서비스 조사와 4번 일부 "왜 골랐나"는 "아직 없음".

## Repo Status (2026-10-01)

- https://github.com/jh3779/LG_CNS_RAG_main (private). 첫 커밋 `edefe82` main push → CI `ci.yml` 전 단계 success.
- 병합: squash만, 커밋 메시지 = PR 제목, 머지 후 브랜치 자동 삭제.
- 룰셋 `main 보호`(id 24290303): 삭제·force push 차단, PR 필수(승인 0명, squash만), 필수 체크 `lint-and-test`·`check-branch-name`·`validate-pr-title` (DEC-006).
- CI 필수 체크 5개: 기존 3개 + `pr-verify`(PR 상세 검증) + `merge-gate`(자동 리뷰·스레드·결과 코멘트 → 커밋 상태) (DEC-008).
- 필수 리뷰어 없음 → 대신 병합 전 검증 프로토콜 `docs/MERGE_PROTOCOL.md` + 스킬 `.claude/skills/pre-merge-check/` (DEC-007). `gh pr merge`는 settings에서 ask.
- 미설정: 팀원 초대·CODEOWNERS, `DISCORD_EVENT_WEBHOOK` 시크릿.

## Next Steps

1. 팀이 `docs/기획.md` 검토 — 특히 참고 레포와의 관계(이어서/새로/범위 변경) 결정
4. 팀원 collaborator 초대 + `.github/CODEOWNERS` 채우기
5. 기술 스택 확정 → `uv add`로 런타임 의존성 추가 (후보 목록: `docs/개발환경.md` 4절)
6. Discord 봇 연동이 필요하면 저장소 시크릿 `DISCORD_EVENT_WEBHOOK` 등록

## Open Questions

- 참고 레포 코드를 가져와 이어서 개발하는가, 기획만 참고하고 새로 만드는가
- 상용 유사 서비스 조사
- 팀 구성 및 역할 분담

# CLAUDE.md

이 저장소의 규칙 원본은 `AGENTS.md`다. 아래 import로 그대로 불러온다 — 규칙은 `AGENTS.md`에서만 고친다.

@AGENTS.md

## Claude Code 전용 보충

- **큰 작업은 Plan Mode로 시작한다.** 여러 파일을 건드리거나 설계 판단이 필요한 작업은 계획을 먼저 보여주고 승인을 받는다.
- **병렬 세션은 worktree로 나눈다.** 같은 폴더에서 세션 두 개가 git을 만지지 않게 `claude --worktree <이름>`을 쓴다. (`.claude/worktrees/`는 gitignore됨)
- **세션 인계**: 작업을 끊을 때는 `.agent/` 문서를 갱신한다 (AGENTS.md 8절). 사용자 환경에 `handoff` 스킬이 있으면 `/checkpoint`로 해도 된다.
- **병합 전 검증은 `pre-merge-check` 스킬로 한다** (`.claude/skills/pre-merge-check/`). "병합해 줘", "머지해도 돼?" 같은 요청을 받으면 묻지 않고 먼저 이 스킬을 실행한다(검증은 바로 한다 — 실제 병합 명령은 PR 번호를 든 지시가 있을 때만, 없으면 번호를 되묻는다, DEC-046). 기준은 `docs/MERGE_PROTOCOL.md`.
- **팀 공유 설정**: `.claude/settings.json`(커밋됨)에 공통 권한을 둔다. 개인 설정은 `.claude/settings.local.json`(gitignore됨)에 둔다.
- 라이브러리 사용법은 기억에 의존하지 말고 공식 문서(context7 MCP 등)로 확인한다. 특히 LLM·임베딩 SDK는 버전마다 API가 바뀐다.

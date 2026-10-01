# LG_CNS_RAG

LG CNS AI Campus RAG 팀 프로젝트 — **미국 제조업 공장 Compliance AI**.

대기 배출 허가(Title V)를 받은 미국 중소 공장의 환경 담당자가 보고·인증·신고·갱신 서류를 쓸 때,
공장에 적용될 수 있는 조항 후보와 확인할 기준을 **최신 근거 조문(40 CFR Part 63)과 함께** 정리해 주는 RAG 서비스.
판정("적용됩니다")은 하지 않는다.

> 기획 상세: [`docs/기획.md`](docs/기획.md) — 초안은 [US-Factory-Compliance-Service](https://github.com/suuuuuuungho/US-Factory-Compliance-Service)를 기반으로 작성했다.
> 기술 스택이 확정되면 이 README에 실행 방법을 추가한다.

## 시작하기

> 처음이라면 **[`docs/시작하기.md`](docs/시작하기.md)** 를 위에서부터 따라 한다 (도구 설치 → 첫 PR → 관리자 설정).

```bash
git clone <repo-url>
cd LG_CNS_RAG_main
uv sync                # Python 3.12 + 의존성 설치 (.venv)
lefthook install       # git 훅 설치
cp .env.example .env   # 실제 키는 .env에만 — 절대 커밋하지 않는다
uv run pytest          # 확인
```

도구 설치(uv·lefthook)와 패키지 추가·노트북·문제 해결은 [`docs/개발환경.md`](docs/개발환경.md)를 본다.

## 협업 규칙

AI 에이전트로 작업할 때의 규칙은 [`AGENTS.md`](AGENTS.md)에 있다.

브랜치·커밋·PR 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 따른다.

## 디렉터리

| 경로 | 용도 |
|---|---|
| `docs/` | 기획(`기획.md`)·개발환경(`개발환경.md`) 등 문서 |
| `tests/` | pytest 테스트 |
| `AGENTS.md` · `CLAUDE.md` | AI 에이전트 행동강령 (원본은 AGENTS.md) |
| `.claude/settings.json` | Claude Code 팀 공유 권한 설정 |
| `.agent/` | AI 에이전트 세션 인계 문서 (PROJECT_CONTEXT · HANDOFF · DECISIONS · SESSION_LOG) |
| `.github/` | PR 템플릿, CODEOWNERS, CI 워크플로 |
| `scripts/` | lefthook이 호출하는 검사 스크립트 |

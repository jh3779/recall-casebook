# LG_CNS_RAG

LG CNS AI Campus RAG 팀 프로젝트 — **온보딩 체크리스트 RAG**.

GitLab 공개 핸드북을 근거로, 신규 입사자·부서 이동자가 새 업무를 맡았을 때 적용될 수 있는 온보딩 체크리스트 항목과
확인 기준을 **원문 근거(`source_path#heading_path`)와 함께** 정리해 주는 RAG 서비스.
판정("적용됩니다")은 하지 않는다.

> 기획 상세: [`docs/기획v1.md`](docs/기획v1.md). 옛 주제(미국 제조업 공장 Compliance AI) 문서 [`docs/기획.md`](docs/기획.md)는 폐기된 참고용이다 (DEC-010).
> 기술 스택이 확정되면 이 README에 실행 방법을 추가한다.

## 지금 어디까지 왔나

- **주제**: 온보딩 체크리스트 RAG (DEC-010). 데이터는 GitLab 공개 핸드북 스냅샷(34개 핵심 부서, md 4,612개).
- **구조**: 인사 · 엔지니어링 · 영업·지원 **3개 도메인**이 각자 최소 DB + RAG PoC를 만들고, 모든 도메인이 쓰는 **공용 폴더 6개**와 색인에서 뺀 폴더 11개를 따로 둔다 (자세한 배정은 [`docs/기획v1.md`](docs/기획v1.md) 3절, DEC-020).
- **서비스 흐름**: 사용자가 질문 전에 유형(신규/이동)과 새 부서를 고르면 → 질문 분류 → 도메인별 검색 → 근거 범위 고정 → 체크리스트 생성 → 인용 검증 순으로 답한다 (기획v1 5절, 초안).
- **일정**: 발표 2026-10-20, 개발 10/12~14. 일정·역할·위험은 [`docs/진행계획.md`](docs/진행계획.md).
- **지금 할 일·열린 결정**은 [`.agent/HANDOFF.md`](.agent/HANDOFF.md)에 있다. 이슈 대신 이 문서가 할 일 목록을 가진다.

## 데이터 받기

핸드북 데이터셋(`docs/handbook/content/`)은 커밋하지 않는다. 지정 커밋에서 받아 4,612개 md를 검증한다:

```bash
uv run python scripts/fetch_handbook_dataset.py
```

구조·실측·재현 방법은 [`docs/handbook/README.md`](docs/handbook/README.md).

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
| `docs/` | 기획(`기획v1.md`, 대안 주제 재검토 안건 `기획_결함선례.md` — 현재 팀 주제 아님, DEC-030)·진행계획·개발환경·병합 전 검증 프로토콜(`MERGE_PROTOCOL.md`)·핸드북 데이터셋 안내(`handbook/README.md`) 등 문서 |
| `tests/` | pytest 테스트 |
| `AGENTS.md` · `CLAUDE.md` | AI 에이전트 행동강령 (원본은 AGENTS.md) |
| `.claude/settings.json` | Claude Code 팀 공유 권한 설정 |
| `.agent/` | AI 에이전트 세션 인계 문서 (PROJECT_CONTEXT · HANDOFF · DECISIONS · SESSION_LOG) |
| `.github/` | PR 템플릿, CODEOWNERS, CI 워크플로 |
| `scripts/` | lefthook이 호출하는 검사 스크립트, CI 로직(`ci/`), 핸드북 데이터셋 재현 스크립트(`fetch_handbook_dataset.py`) |

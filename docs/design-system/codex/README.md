# Codex 작업 지시 — 검색 화면 구현 (공통 규칙)

> 이 폴더는 **Codex(구현 에이전트)**에게 주는 지시문이다. 사람은 Codex에 "`docs/design-system/codex/README.md`와 `task-D-…md`를 읽고 작업 D를 해 줘"처럼 한 작업씩 맡긴다.
> 작성: 2026-10-13 (우지훈 결정 기반, Claude Code 작성). 설계 정본은 `docs/design-system/`(v1.0).

## 작업 순서

| 작업 | 파일 | 브랜치 | 결과 |
|---|---|---|---|
| D | [task-D-pr60-cleanup.md](task-D-pr60-cleanup.md) | `feat/frontend-showroom`(PR #60에 커밋을 더함) | #60 정리 — main 합치기, 데모 데이터 원문 정정, 문구, 쇼룸 토큰, DEC-052 |
| E | [task-E-search-view.md](task-E-search-view.md) | `feat/search-view` (D 병합 뒤 main에서) | 검색 전용 화면 + 공개 API 연동, DEC-053 |
| F | [task-F-frontend-deploy.md](task-F-frontend-deploy.md) | `chore/frontend-vercel-deploy` (E 병합 뒤) | 화면 Vercel 배포 준비(설정·문서·런북). 실제 배포는 사람이 한다 |

한 작업이 병합된 뒤 다음 작업을 시작한다. 작업 하나 = PR 하나.

> **실제 진행(2026-10-13)**: D·E는 Codex가 한 작업본에서 함께 구현해, #60(`5be42cb`)을 합친 `feat/search-view`의 **PR #105 하나**로 올렸다. #60은 #105로 대체하고 닫았다(사용자 결정). F는 위 표대로 #105 병합 뒤 시작한다.

## 먼저 읽을 것 (순서대로)

1. `AGENTS.md` — 저장소 규칙의 원본. 이 파일과 충돌하면 AGENTS.md가 이긴다.
2. `.agent/HANDOFF.md` — Next Action 1(화면 연결)과 Current State.
3. `docs/design-system/README.md`와 그 폴더 전체 — 화면이 따를 설계 v1.0. `tokens/tokens.css`·`copy/*.md`·`components/*.md`가 값과 문구의 정본이다.
4. 작업 파일(task-D/E/F).

## 꼭 지킬 규칙 (AGENTS.md 요약 — 원문을 다시 읽을 것)

**서비스 원칙 (화면 구조로 지킨다)**
- **판정하지 않는다**: "리콜 대상입니다", "원인은 ~입니다", "해당합니다/해당되지 않습니다", "적용됩니다" 같은 결론 문구와 `applies`·`verdict`·`is_applicable`·`recall_required` 같은 칸을 만들지 않는다. 판정 인상을 주는 색(빨강·초록·경고 주황)을 검색 화면에 쓰지 않는다. <!-- principle-ok: 금지 문구를 설명하기 위해 인용 -->
- **원문은 감싸기만**: 서버가 준 결함·결과·시정·원인·조사 요약 글을 번역·요약·대소문자 정리·문자 치환하지 않는다. 화면에 넣을 때는 React 텍스트 노드(자동 이스케이프)로만 넣고 `dangerouslySetInnerHTML`을 쓰지 않는다. 보이지 않는 제어 문자(예: U+0092)도 원문이다.
- **말한 주체와 출처**: 원문마다 서버의 `speaker`와 번호(리콜 번호·573 캠페인·조사 번호)를 붙인다.
- **없으면 이유와 함께**: 원인 원문이 없으면 `copy/cause-status.md`의 상태 문구를 보인다. 짐작해 채우지 않는다.

**명령**
- 프런트는 `frontend/`에서 **npm만**: `npm ci` · `npm run lint` · `npm run build` · `npm test`. `yarn`·`pnpm` 금지. 의존성을 바꾸면 `package-lock.json`을 npm으로 갱신해 같이 커밋한다. `package.json`에 없는 스크립트를 지어 쓰지 않는다.
- Python은 **uv만**: `uv run ruff check . && uv run ruff format --check . && uv run pytest`. `pip install`·`requirements.txt` 금지.
- 작업을 끝냈다고 말하기 전에 프런트 4개 명령과 Python 3개 명령을 돌리고 **결과(통과 수·실패)를 그대로** 보고한다. 못 돌린 것은 못 돌렸다고 쓴다(예: DB 시험은 `TEST_DATABASE_URL`이 없으면 skip — skip 수를 적는다).

**git · PR**
- 브랜치 `<type>/<소문자-하이픈>`. 커밋·PR 제목 `<type>: <한국어 설명>` — type은 `feat fix refactor docs research data chore remove`, **설명 첫 글자를 영어 대문자로 시작하지 않는다**(훅이 막는다 — 한국어로 시작하면 안전).
- **main에 직접 커밋·push 금지.** `--no-verify`·`LEFTHOOK=0` 금지. **이미 push한 커밋을 rebase·amend·force push하지 않는다** — 고칠 거리는 새 커밋으로.
- PR 본문은 `.github/pull_request_template.md`의 절(변경 요약·변경 유형·체크리스트·검증 방법·병합 전 검증·관련 이슈)을 모두 채운다. 본문에 사람을 `@태그`하지 않는다.
- **병합하지 않는다.** 병합 전 검증(`docs/MERGE_PROTOCOL.md` — 자동 리뷰·Codex 리뷰봇·엄격 local CI·결과 코멘트)과 병합은 Claude Code 세션과 사람이 한다. Codex는 PR을 열고 리뷰 지적이 오면 새 커밋으로 고친다.
- 커밋 훅이 1MB 넘는 파일을 막는다. 3D 모델 `.glb`(약 10MB·8MB)는 커밋하지 않는다(`frontend/public/models/`는 gitignore).

**비밀값**
- `.env`·`.env.*`를 읽거나 출력하지 않는다. API 키·토큰을 코드·로그·커밋·PR에 넣지 않는다. `VITE_*` 환경변수에는 공개돼도 되는 값(공개 API 주소)만 넣는다.

**기록 (AGENTS.md 8절)**
- 되돌리기 어려운 결정은 `.agent/DECISIONS.md`에 다음 번호로(작업 D = DEC-052, E = DEC-053, F = DEC-054 — 쓰기 직전 main의 마지막 번호를 다시 확인). 기존 DEC 본문은 고치지 않는다.
- 의미 있는 진전은 `.agent/HANDOFF.md`(현재 상태로 고쳐 씀)와 `.agent/SESSION_LOG.md`(한 줄 추가). HANDOFF "할 일 목록"의 항목은 완료나 폐기 결정 전에는 지우지 않는다.

## 멈추고 사람에게 물어볼 때

- 지시문과 실제 코드·데이터가 다를 때(줄 번호·바이트·파일이 없음 등) — 짐작해 고치지 말고 보고.
- 서버 응답 계약(`server/api.py`)을 바꿔야 할 것 같을 때 — 이번 작업 범위 밖이다.
- 설계 문서(`docs/design-system/`)와 다르게 만들어야 할 이유가 생겼을 때.
- 네트워크·계정이 필요한 일(공개 API 호출이 막힘, Vercel 로그인, 비공개 artifact 접근).

## 보고 형식 (작업이 끝나면)

1. 바꾼 파일과 이유(작업 지시의 항목 번호와 연결)
2. 돌린 명령과 결과(통과 수·실패·skip)
3. 지시와 다르게 한 것과 이유
4. 못 한 것·사람이 해야 할 것
5. 연 PR 번호

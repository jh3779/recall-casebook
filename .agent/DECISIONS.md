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
- **Status**: Superseded by DEC-010
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

## DEC-007: 필수 리뷰어 대신 병합 전 검증 프로토콜(문서 규칙)
- **Decision**: main 룰셋의 필수 승인은 0명으로 유지하고, 병합 전에 `docs/MERGE_PROTOCOL.md` 게이트 9개(CI, 자동 리뷰 존재·최신성, 지적 전부 처리, 스레드 해결, diff 정독, 서비스 원칙 스윕, RAG 근거, 의존성·인계)를 돌려 결과 표를 PR 코멘트로 남긴다. Claude Code는 `pre-merge-check` 스킬로 실행. `gh pr merge`는 deny → ask로 바꿔, 사용자가 명시적으로 지시하고 게이트가 ✅일 때만 에이전트가 병합할 수 있게 했다.
- **Reason**: 사용자 지시("리뷰어 필수는 없이, 대신 문서로 에이전트에게 병합 전 자동리뷰 내용 확인"). project-human-p의 MERGE_PROTOCOL + pre-merge-check 구조를 가져옴.
- **Alternatives**: 룰셋 `required_review_thread_resolution` 켜기 — 구조적으로 강제되지만 사용자가 문서 규칙을 지시해 이번엔 G-05 게이트로만 확인. 필수 승인 1명 — 사용자가 원하지 않음.
- **Status**: Accepted
- **Date**: 2026-10-01

## DEC-008: 병합 전 검증 중 기계 판정 가능한 게이트를 CI 필수 체크로
- **Decision**: `pr-verify`(scripts/ci/pr_checks.py — 판정 필드·비밀값·RAG 수치 근거·PR 본문·type 목록 6곳·문서 링크·AGENTS import)와 `merge-gate`(scripts/ci/merge_gate.py — 현재 head 기준 자동 리뷰·미해결 스레드 0·✅ 결과 코멘트 → 커밋 상태)를 추가하고 룰셋 필수 체크를 5개로 늘린다. 필수 승인은 계속 0명.
- **Reason**: 사용자 지시("CI에도 내부 상세 검증"). DEC-007의 문서 규칙만으로는 에이전트가 따를 때만 지켜지므로, 기계로 판정 가능한 부분은 병합 버튼에서 막는다.
- **Alternatives**: 룰셋 `required_review_thread_resolution` — merge-gate가 G-05를 함께 보므로 중복. 외부 비밀값 스캐너(gitleaks 등) — 지금 규모에는 정규식으로 충분, 필요 시 추가.
- **한계**: G-04·G-06 내용 판단은 기계로 못 함 (merge-gate는 결과 코멘트 존재까지만). issue_comment 트리거는 main의 워크플로를 쓰므로 이 PR 병합 전에는 push 이벤트로만 판정. 스레드 resolve는 이벤트가 없어 수동 재실행 필요.
- **Status**: Accepted
- **Date**: 2026-10-01

## DEC-009: merge-gate는 main 코드로만 실행, 2단계 도입
- **Decision**: `merge-gate` 트리거를 `pull_request_target`·`issue_comment`로 바꾸고 (처음엔 `workflow_dispatch`도 넣었으나 PR 브랜치로 수동 실행하면 PR이 고친 워크플로가 쓰기 권한으로 돌아 제거 — 리뷰봇 `88648fa` 리뷰) checkout을 main으로 고정한다(PR 코드 미실행, API로만 판정). 이 워크플로가 main에 없으면 PR에서 돌 수 없으므로 필수 체크에서 잠시 빼고(1단계) PR #1 병합 후 다음 PR에서 상태 게시를 확인해 다시 필수로 넣는다(2단계). 함께: Codex 리뷰 형식 인식, 결과 코멘트 뒤 새 리뷰면 pending, G-02(출처)는 수동 게이트로 명시, RAG 경로 설정을 `scripts/ci/pr_verify.toml`로 이동(G-09 충돌 해소), RAG 근거에 지표 이름 요구·skip은 검증 방법 섹션 안에서만.
- **Reason**: 리뷰봇(Codex) 리뷰(PR #1, head `9c78f5d`·`def6923`) — `statuses: write`로 PR이 고칠 수 있는 스크립트를 실행해 PR이 자기 게이트를 통과시킬 수 있었음(C2). 사용자 승인("보완 작업 진행").
- **Alternatives**: `pull_request`·`pull_request_review` 유지 + 스크립트 경로만 main에서 받기 — 워크플로 파일 자체가 PR 쪽이라 PR이 고칠 수 있어 기각.
- **남은 한계**: 같은 계정 자기 인증, 쓰기 권한자의 상태 위조 → 리뷰 전용 계정·GitHub App 필요(이슈 #4, 사용자 결정 대기).
- **Status**: Accepted
- **Date**: 2026-10-01

## DEC-010: 프로젝트 주제를 "온보딩 체크리스트 RAG"(GitLab 핸드북)로 전환
- **Decision**: 기존 주제(미국 제조업 공장 Compliance AI, 참고 레포 `US-Factory-Compliance-Service` 기반)를 접고, **GitLab 공개 핸드북**(`suuuuuuungho/GitLab_Data` 스냅샷 `0ab0299`, 로컬 `docs/handbook/`, `.gitignore`됨)을 데이터로 쓰는 **신규 입사자·부서 이동자 온보딩 체크리스트 RAG**로 전환한다. 기획은 `docs/기획v1.md`에 새로 작성 중(1~3번 작성 완료, 4~7번은 뼈대만 — "유사 서비스 조사" 단계는 의도적으로 뺐다). 데이터는 36개 부서 디렉토리·md 4,612개(핵심 부서 34개, 스텁 2개 제외), 추정 약 1,175만 토큰(글자수÷4 경험칙, 정밀 토크나이저 미설치).
- **Reason**: 2026-10-02 팀 회의 결론 — 각 파트(인사/엔지니어링/전사 공통/영업·지원)가 자기 도메인의 최소 DB + RAG PoC를 먼저 만들고 그 결과로 전체 방향을 정하기로 함. `docs/기획v1.md` 1절 근거: 핸드북 `people-group/promotions-transfers.md:701`(직무 전환자도 새 직무 온보딩 완료 필요).
- **Alternatives**: 원격 브랜치 `docs/onboarding-plan`(2026-10-01~02, 커밋 `5c58368`·`d7e0a29`)에서 실제로 4개 주제 후보를 7단계 틀로 다 써봤다 — ① 기존 Compliance AI(규제 RAG) ② **결함 선례 RAG**(`docs/기획_결함선례.md`, 리콜·결함조사 선례 검색) ③ **온보딩 문서 구조화 에이전트**(`docs/기획_문서구조화.md`, 상충 내용 병합 없이 나란히 제시) ④ **코드 이해 도우미**(`docs/기획_코드온보딩.md`, 신규 개발자용 코드 설명+퀴즈). 이 중 ③과 가까운 "사내 온보딩 문서 정리·생성 에이전트"(`docs/기획_온보딩.md`, PR #6)가 반쯤 채택됐다가, 이번 세션에서 데이터를 GitLab 핸드북으로 구체화하면서 `docs/기획v1.md`로 다시 쓰여 최종 채택됐다(PR #6은 닫음). ②④(`기획_문서구조화.md`·`기획_코드온보딩.md`)는 사용자 지시로 저장소에서 삭제했다. ③(`기획_결함선례.md`)는 "기각된 주제 후보" 표시를 달아 사용자 바탕화면(`~/Desktop/결함선례_기획/`)으로 옮겼다 — 더 이상 이 저장소 안에 없다.
- **영향**: `.agent/PROJECT_CONTEXT.md`의 Goal·Tech Stack 설명이 아직 옛 주제(Compliance AI) 기준이라 **다음 체크포인트 전에 갱신 필요**. `docs/기획.md`(옛 주제 7단계 문서)는 참고용으로 남겨두고 새 작업은 `docs/기획v1.md`에서 이어간다. `docs/진행계획.md`(팀 일정·역할·위험 요소, `docs/onboarding-plan`에서 이식)도 날짜·일정 부분은 참고용으로 같이 가져왔다.
- **Status**: Accepted (DEC-003을 대체함)
- **Date**: 2026-10-02

# Agent Handoff

_갱신: 2026-10-02_

## Current Objective

PR #7(`docs/project-skeleton` → `main`)의 Codex 자동 리뷰 지적 5건(머지 전 필수 보완)을 반영 중. 반영 후 `docs/MERGE_PROTOCOL.md` 게이트를 다시 돌려 병합 가능 상태로 만드는 것이 목표.

## Current Phase

없음 — `PROJECT_CONTEXT.md`에 Phases 로드맵이 아직 정의돼 있지 않다. 느슨하게는 "기획 단계"(10/2 주제 결정 완료 ~ 10/6-7 프로토타입 전).

## Completed

- **PR #7 오픈·리뷰 수신**: 커밋 `f7ff989`·`7630748`·`e3c95a5`·`8b47247`까지 push, `@jh3779` 리뷰 요청 태그 포함 PR 생성. `pr-verify` 1차 실패(판정 문구 오탐) → `principle-ok` 주석으로 해결(커밋 `8b47247`). Codex 자동 리뷰가 "머지 전 필수 보완" 5건을 지적 (PR #7 코멘트, 2026-10-02T07:26).
- **5건 전부 검증**: 파일:줄 대조로 전부 CONFIRMED 확인(아래 Important Decisions 참고 불필요 — 리뷰 자체가 근거).
- **1) AGENTS.md 2·5절 규제 서비스 잔재 제거**: 2절을 `source_path#heading_path` 근거 형식으로 재작성(40 CFR 조문 언급 삭제), 5절 평가셋 규칙을 "핸드북 실제 질문에서 추출"로 교체, 기준 폭 출처를 `기획v1.md` 3절로 변경.
- **2) 평가셋 근거 명시**: `기획v1.md` 1절 고통 포인트 8개 중 7개에 `(가설)` 표시, 3절 PoC 공통 기준에 "평가 질문 출처"(핸드북 실제 질문만 사용, 가설 항목은 검증 전까지 평가셋 근거로 안 씀) 행 추가.
- **3) 34개 부서 ↔ 도메인 매핑**: 각 부서 `_index.md` 실제 설명을 확인해 `기획v1.md` 3절에 초안 표 추가(인사 6·엔지니어링 5·전사공통 16·영업지원 7). "팀 확인 필요"로 명시, 전사 공통이 넓다는 점도 `진행계획.md`에 반영.
- **4) 데이터셋 재현 스크립트**: `scripts/fetch_handbook_dataset.py` 작성(지정 커밋 `0ab0299`에서 다운로드 → 비문서 파일 13개 제거 → md 4,612개 검증, 불일치 시 실패). **실제로 실행해 성공 확인**(55M, 4,612개 md). `docs/handbook/README.md` 재현 방법을 이 스크립트로 교체.
- **5) HANDOFF·기획·진행계획 stale 정리**: `기획_뼈대.md`에 "폐기된 과거 초안" 경고 헤더 추가, `진행계획.md`·`쉬운버전/진행계획.md`의 "금융 vs 전사공통 불일치"(이미 해소됨)·"88건 수치 안 고쳐짐"(이미 고침) 항목을 현재 상태로 교체. `pyproject.toml` description도 온보딩 주제로 변경.

## Last Work

위 5건을 전부 반영한 직후. 로컬 검증(`ruff check`·`ruff format --check`·`pytest`) 통과 확인함. 아직 커밋 전.

## Current State

`git status --short --untracked-files=all` 기준 (데이터셋 `docs/handbook/content/`는 ignore돼 제외):
```
 M AGENTS.md
 M docs/handbook/README.md
 M docs/기획_뼈대.md
 M docs/기획v1.md
 M docs/쉬운버전/진행계획.md
 M docs/진행계획.md
 M pyproject.toml
?? scripts/fetch_handbook_dataset.py
```
브랜치 `docs/project-skeleton`은 origin에 `8b47247`까지 push됨(PR #7 오픈). 위 변경은 **아직 커밋 전** — 커밋·push하면 PR #7에 자동으로 반영된다.

## Open Issues

- 위 변경 커밋·push 필요. 이후 리뷰봇이 새 커밋에 다시 리뷰를 달 것이므로, `docs/MERGE_PROTOCOL.md`대로 그 결과도 확인해야 한다.
- 리뷰의 "선택 개선" 2건은 아직 미반영: ① 기준 문서 `DOCUMENTS.md` 관련 — 리뷰 자체가 "자동 검증 경고"로 근거 부족이라고 표시했으므로 **반박 처리**(실제로 그런 파일·정책 지정 기록 없음, 무시해도 됨). ② `기획v1.md`에 H1 제목·마지막 줄바꿈 추가 — 아직 안 함.
- `기획v1.md` 3절 "34개 부서 ↔ 도메인 매핑"은 초안이다 — 전사 공통이 16개로 넓어 팀 확인·재배분이 필요할 수 있다.
- 인사·엔지니어링·전사 공통 파트 담당자가 아직 미정(10/7까지, `진행계획.md` 참고).
- 4~7절(기술스택·아키텍처·개선사항·어려움)은 여전히 뼈대뿐 — 도메인별 PoC(10/6~7) 이후 채운다.

## Important Decisions

- [[DEC-010]] 주제를 온보딩 체크리스트 RAG로 전환 (`.agent/DECISIONS.md`)
- DEC-003 Superseded by DEC-010

## Failed Attempts

- `npx skills add`로 Wayfinder 스킬 자동 설치 시도 → Claude Code 자동 모드 안전장치가 "외부 코드 실행"으로 차단. **신호**: npx/pip 등으로 외부 패키지를 받아 즉시 실행하는 명령은 에이전트가 자동 실행할 수 없다 — 사용자에게 `!` 접두사로 직접 실행하도록 안내한다. 사용자가 `claude plugins install mattpocock-skills`를 직접 실행해 해결함.

## Relevant Files

- `docs/기획v1.md` — 메인 기획 문서 (1~3절 내용 보강, 4~7절 뼈대)
- `docs/진행계획.md`(+`쉬운버전/`) — 팀 일정·역할·위험 요소
- `AGENTS.md` — 2·5절 재작성함
- `scripts/fetch_handbook_dataset.py` — 데이터셋 재현 스크립트 (신규)
- `docs/handbook/README.md` — 데이터셋 구조·재현 방법

## Next Action

1. 위 변경 커밋·push (PR #7에 반영)
2. 리뷰봇의 새 리뷰 확인 → `docs/MERGE_PROTOCOL.md` 게이트 전부 ✅인지 확인 후 사용자에게 병합 여부 확인
3. 34개 부서 ↔ 도메인 매핑 초안을 팀(특히 인사·엔지니어링·전사 담당자)과 확정

## Definition of Done

`기획v1.md` 1~7번 + 발표 전 점검까지 전부 실제 내용(뼈대 아님)으로 채워지고, 모든 수치가 `scripts/fetch_handbook_dataset.py`로 재현된 이 저장소 데이터에서 나온 값이며, 발표 전 점검 체크리스트 항목을 전부 체크할 수 있는 상태.

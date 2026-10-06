# Project Context

## Goal

LG CNS AI Campus RAG 팀 프로젝트 — **결함 선례 찾기 도우미** (DEC-030, 2026-10-06 온보딩 RAG에서 전환). 한국 부품사에서 북미 수출 차종을 맡은 품질·제품안전 엔지니어가 원인 모를 결함을 받았을 때, 미국 정부(NHTSA) 공개 리콜·결함 조사에서 같은 부품의 다른 회사 선례와 그 원인 서술을 원문 그대로 리콜 번호와 함께 찾아 준다. 판정("리콜 대상입니다", "원인은 이것입니다")은 하지 않는다. 상세: `docs/기획_결함선례.md`. 이전 주제 문서(온보딩 `docs/기획v1.md`, Compliance AI `docs/기획.md`)는 참고용. <!-- principle-ok: 금지 문구를 설명하기 위해 인용한 메타 문장, 실제 판정 필드 아님 -->

## Current Product Direction

- 데이터: NHTSA ODI 공개 flat 파일(리콜 30,350건·결함 조사 5,349건, 매일 갱신)과 리콜 원본 보고서 Part 573 PDF(2014-08 이후, 원인·공급사 칸). 재현 스크립트·기준 파일: `scripts/defect_precedent/`.
- 사용자: 한국 부품사의 북미 수출 차종 품질·제품안전 엔지니어. 질문은 영어만(현장 말투·한국어 제외). 검색은 회사 이름이 아니라 부품 기준이며, 고객사(현대·기아·제네시스) 선례를 먼저 보여 준다.
- 평가: 정부 기록(조사 → 리콜) 749문항은 대리 평가 — 기준선 BM25 Hit@10 0.510. "과거 선례 찾기"는 시점 평가(사람 정답 표시)로 따로 잰다.
- 서비스 원칙: ① 판정하지 않는다 ② 근거 없는 말은 하지 않는다(리콜 번호·원문 그대로, 글자 대조) ③ 추측하지 않는다 ④ 추적 가능해야 한다 (AGENTS.md 2절).

## Team

- 4명: 박성호·박예원·우지훈(@jh3779)·이승노. 발표일 2026-10-20. 역할(2026-10-06 확정, 이슈 #24): A 데이터·시험지 박예원 · B RAG(찾기·원인 옮기기) 우지훈 · C 검사·화면·발표 박성호 · D 근거·품질 확인 이승노. GitHub 아이디가 확정되면 `.github/CODEOWNERS`를 채운다.

## Tech Stack

- 확정: Python 3.12 + uv, 데이터 처리·기준선은 표준 라이브러리(BM25 직접 구현). 미정: 뜻 검색(임베딩)·순위 합치기·원인 옮기기 LLM — B 파트 실험으로 정한다 (`docs/기획_결함선례.md` 4절).

## Tooling

- Python 3.12 + **uv**(의존성·가상환경, DEC-004), lefthook(git 훅), ruff + pytest, CI `ci.yml`.
- 에이전트 행동강령 원본은 `AGENTS.md`, `CLAUDE.md`는 import만 (DEC-005).

## Constraints

- 비밀키·토큰은 절대 커밋하지 않는다 (`.env`만 사용, lefthook pre-commit이 차단).
- main 직접 push 금지 — 단명 브랜치 → PR → squash merge (`CONTRIBUTING.md`).

## Agent Permissions

**자유롭게 한다**
- 파일 읽기, `git status`·`git log`·`git diff`, `uv run ruff check`·`ruff format --check`·`pytest`
- 문서·코드 수정 (요청 범위 안에서)

**요청받았을 때만 한다** (AGENTS.md 6절)
- 커밋, push, PR 생성
- 병합: 사용자가 그 PR의 병합을 명시적으로 지시하고 `MERGE_PROTOCOL.md` 게이트가 전부 ✅일 때만 `gh pr merge <N> --squash`
- force push: 요청 시에만 `--force-with-lease`

**먼저 묻고 확인받는다** (AGENTS.md 5·7절)
- 유료 API(LLM·임베딩) 대량 호출 — 예상 호출 수·비용을 먼저 말한다
- 전체 재색인·재임베딩 — 소량 표본 결과를 보여 준 뒤 진행한다
- 평가셋 변경(질문 추가·정답 표시)
- 서비스 원칙(2절)·되돌리기 어려운 결정 변경 — `DECISIONS.md`에 DEC로 남긴다

**하지 않는다**
- main 직접 커밋·push, `--no-verify`·`LEFTHOOK=0`으로 훅 우회
- `.env` 읽기·출력, 키·토큰 커밋
- 원본 데이터·벡터 인덱스 커밋, 실제 질문 원문의 저장소 반입
- 같은 컨텍스트에서 자기 작업을 "문제없음"으로 리뷰

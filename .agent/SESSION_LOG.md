# Session Log

<!-- 체크포인트마다 한 줄만 append. HANDOFF.md는 매번 덮어써 과거가 사라지므로,
     "언제 무엇을 했는지"의 이력은 이 파일과 git history에서 본다. -->

- 2026-10-01: 협업 저장소 초기 셋팅 — 다른 프로젝트 기준 CONTRIBUTING·PR 템플릿·CI 워크플로·.agent/ 문서 생성
- 2026-10-01: pre-commit → lefthook 교체(DEC-002), 참고 레포 기반 `docs/기획.md` 7단계 초안 작성(DEC-003)
- 2026-10-01: uv 개발환경(DEC-004)·`docs/개발환경.md`·CI `ci.yml`, 에이전트 행동강령 AGENTS.md/CLAUDE.md/.claude/settings.json(DEC-005)
- 2026-10-01: 전체 셋팅 안내서 `docs/시작하기.md` 작성, README·AGENTS.md에서 연결
- 2026-10-01: GitHub private 저장소 생성·첫 push(CI green), squash 전용·브랜치 자동 삭제, 룰셋 `main 보호` 적용(DEC-006)
- 2026-10-01: 병합 전 검증 프로토콜(MERGE_PROTOCOL.md·pre-merge-check 스킬) 도입, `gh pr merge` deny→ask (DEC-007)
- 2026-10-01: CI 상세 검증 추가 — `pr-verify`·`merge-gate` 워크플로 + scripts/ci + 테스트 23개, 룰셋 필수 체크 5개로 (DEC-008)
- 2026-10-01: Codex 리뷰(놓쳤던 2건) 반영 — merge-gate main 전용 실행·2단계 도입(DEC-009), Codex 형식 인식·결과 뒤 리뷰 무효화, pr-verify 근거 강화, 설정 파일 분리
- 2026-10-02: 주제를 온보딩 체크리스트 RAG(GitLab 핸드북)로 전환(DEC-010, DEC-003 대체) — `docs/기획v1.md` 1~3절 작성(고통 포인트·RAG 필요성·데이터셋 실측), 4~8절 뼈대(도메인별 하위 섹션 포함)
- 2026-10-02: PR #6 닫음, 데이터셋 정리(73MB→56MB)·`docs/handbook`로 개명, `docs/onboarding-plan` 브랜치에서 진행계획.md 이식, 기각 후보 문서 삭제/이동, AGENTS.md 갱신, 전체 문서 정합성 수정(stale 경로·수치·섹션번호·gitignore)
- 2026-10-02: 기획v1 grilling Q1~Q5 반영 — 평가 질문 유형(문서 유래/상황 서술) 분리·도메인당 최소 30문항, 중복 제거 키 확정, 전사 공통 분할안(실측)·공용 폴더 후보 제안
- 2026-10-02: 기획v1 5절(아키텍처·워크플로우) 초안 — 질문 분류→모델 분류→검색→근거 범위 고정→생성→인용 검증, 미결 4건 기록

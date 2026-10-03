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

## DEC-011: PoC 평가 질문을 두 세트로 나누고, 최소 30문항·공용 테이블 중복 제거 키를 정한다
- **Decision**: `docs/기획v1.md` 3절 "PoC 공통 기준"에 다음을 넣는다. ① 평가표에 "질문 유형" 열 — **문서 유래**(핸드북에 이미 쓰인 체크리스트·FAQ·runbook에서 추출, 기준선 Recall@k용 본 세트)와 **상황 서술**(사람이 직접 쓰고 작성자·정답 표시자를 기록하는 소량 세트, 도메인당 5~10개). 두 점수는 합산하지 않고 따로 보고한다. ② 문서 유래 세트는 **도메인당 최소 30문항**, 못 채우면 그 사실과 개수를 기록하고 0.03 비교 대신 문항별 성공/실패 목록으로 보고한다. ③ 공용 참조 테이블의 **중복 제거 키는 `(source_path, commit_sha, heading_path)`**.
- **Reason**: grilling Q1·Q2·Q4, 사용자 인터뷰로 권장안 채택(2026-10-02). Q1: 문서 유래 질문은 정답 문장을 거의 그대로 옮겨 검색이 쉽게 맞아, 실제 입력("SA 팀으로 이동했는데 뭘 해야 해?")과의 간극을 따로 봐야 한다. Q2: 20문항이면 한 문항 = 0.05라 동등 판정 폭 0.03을 구분할 수 없다(30문항 ≈ 0.033). Q4: 공용 폴더를 여러 도메인이 각자 색인하면 합칠 때 같은 청크가 중복돼 검색 결과가 오염된다.
- **Alternatives**: Q1 문서 유래만 사용 — 간극을 기록만 하고 측정하지 않아 기각. Q2 50문항 — 문서 유래 규칙상 못 채우는 도메인이 늘어 기각. Q4 공용 폴더를 아예 두지 않음 — `upstream-studios`처럼 여러 도메인에 걸친 폴더가 실제로 있어 기각.
- **남은 확인**: 상황 서술 세트가 AGENTS.md 5절("평가셋을 지어내지 않는다")과 충돌하는지 팀 확인. `domain` 컬럼 배열화는 검토 중. 전사 공통 분할안·공용 폴더 목록은 아직 **제안**이라 이 결정에 넣지 않았다.
- **Status**: Accepted — ①의 "문서 유래" 출처는 DEC-012로, "상황 서술" 세트와 ③의 키는 DEC-013으로 바뀜
- **Date**: 2026-10-02

## DEC-012: 문서 유래 평가 질문은 FAQ 형태만 쓰고, 체크리스트·runbook 문장은 정답 문서 후보로만 쓴다
- **Decision**: DEC-011의 "문서 유래" 세트 출처를 **핸드북에 이미 질문 형태로 쓰인 FAQ**로 좁힌다. 체크리스트 항목·onboarding101류 runbook 문장은 질문 출처로 쓰지 않고 정답 문서 후보로만 쓴다. AGENTS.md 5절 2항과 `docs/기획v1.md` 3절 "평가 질문 출처"·"최소 개수" 행에 반영.
- **Reason**: PR #7 두 번째 Codex 리뷰(커밋 `813a772`). 체크리스트 문장을 그대로 질문으로 쓰면 질문과 정답 문서에 같은 단어가 반복돼 단어 검색만으로 맞는다 — 모델을 이 점수로 고르면 실제 질문에서 성능이 낮을 수 있다. DEC-011 Q1과 같은 문제의식이며 이를 출처 단계에서 막는다.
- **Alternatives**: 현행(체크리스트·runbook 포함) 유지 — 점수 부풀림 위험으로 기각. 문서 유래 세트 폐지 — 임의 질문 금지 원칙상 평가셋이 없어져 기각.
- **영향**: FAQ가 적은 도메인은 30문항을 못 채울 수 있다(미달 시 문항별 성공/실패 목록으로 보고, DEC-011 ②). 도메인별 FAQ 개수는 아직 실측 전이다.
- **Status**: Accepted (사용자 승인 2026-10-02, 팀 확인 항목 남음)
- **Date**: 2026-10-02

## DEC-013: 상황 서술 평가 세트는 실제 사례 확보 전까지 점수에서 제외하고, 중복 제거 키에 chunk_hash를 넣는다
- **Decision**: ① "상황 서술" 질문은 실제 사례(인터뷰·온보딩 문의·지원 요청)에서 수집해 출처를 기록하기 전까지 "작성 예정"으로 두고, 모델·파라미터 선택 점수에 쓰지 않는다. 팀원이 직접 지어 쓴 질문은 넣지 않는다. 기준선은 FAQ 유래 "문서 유래" 세트만으로 낸다. ② 공용 테이블에 `chunk_hash`(공백 정리한 `chunk_text`의 해시) 컬럼을 추가하고 중복 제거 키를 `(source_path, commit_sha, heading_path, chunk_hash)`로 바꾼다. DEC-011의 ①(상황 서술 세트 운영)과 ③(키)을 대체한다.
- **Reason**: PR #7 세 번째 Codex 리뷰(커밋 `ef8fc44`) 필수 보완 2건, 사용자 승인. ① 사람이 쓴 질문은 팀이 예상한 표현에 검색 설정이 맞춰질 위험이 있고 "임의로 질문을 지어내지 않는다"와 충돌한다. ② 한 제목 아래를 여러 청크로 나누면 세 필드가 모두 같아, 이전 키로는 정상 청크가 하나만 남는다.
- **Alternatives**: ① 상황 서술 세트를 팀원이 작성 — 임의 질문 금지와 충돌해 기각. ② `chunk_index` 사용 — 도메인마다 청킹이 달라 같은 위치가 다른 텍스트일 수 있어 기각. 공통 문서를 한 번만 청킹 — 도메인별로 청킹을 자유롭게 고르는 4절 방침과 충돌해 기각.
- **영향**: 상황 서술 세트가 실제 사례 확보 전에는 비어 있어, 실제 입력과의 간극을 지금은 측정하지 못한다(알려진 한계). 실제 사례를 얻을 경로(인터뷰·문의)는 아직 정해지지 않았다. `chunk_hash`의 정규화 규칙(공백 정리 범위)은 PoC 때 구체화한다.
- **Status**: Accepted (사용자 승인 2026-10-02)
- **Date**: 2026-10-02

## DEC-014: 공용 테이블의 domain을 domains[]로 확정하고, FAQ 점수는 모델 선택의 단독 근거로 쓰지 않는다
- **Decision**: ① 공용 참조 테이블의 `domain`을 `domains`(배열)로 확정한다. 중복 청크를 합칠 때 `domains`는 합집합으로 보존하고, 검색은 `domains`에 선택된 도메인이 포함되는지로 거른다. ② FAQ 유래 점수는 "검색 동작 확인용"으로만 쓰고, 모델·파라미터의 최종 선택은 출처를 기록한 실제 질문 세트의 before/after가 나온 뒤에 한다. 그 전에는 기술 동작 확인까지만 한다.
- **Reason**: PR #7 네 번째 Codex 리뷰(커밋 `26c5100`) 필수 보완 2건, 사용자 승인(2026-10-03). ① 단일 `domain`이면 공용 청크를 합칠 때 한 도메인 값만 남아 다른 도메인 검색에서 그 청크가 빠진다. ② FAQ 질문 문장이 검색 대상에도 그대로 있어 단어가 같은 문서를 찾는 방식만으로 점수가 높게 나온다.
- **Alternatives**: ① 청크 테이블과 `chunk_id-domain` 연결 테이블 분리 — 공용 스키마 "컬럼만 합의"하는 4절 방침상 컬럼 하나로 끝나는 배열을 택했고, 도메인 PoC에서 불편하면 재검토한다. ② FAQ 점수로 모델을 선택 — 점수가 부풀려져 실제 질문 성능을 못 봐 기각.
- **영향**: 실제 질문 사례를 확보하기 전에는 모델 최종 선택을 못 한다(DEC-013의 알려진 한계와 같은 뿌리). 사례를 얻을 경로가 팀 결정 사항으로 남는다. DEC-011의 "domain 배열화 검토 중"은 이 결정으로 해소.
- **Status**: Accepted (사용자 승인 2026-10-03)
- **Date**: 2026-10-03

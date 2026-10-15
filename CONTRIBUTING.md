# 기여 규칙 — 브랜치 · 커밋 · PR

이 저장소는 [branch-strategy-kit](https://github.com/Seongyul-Lee/branch-strategy-kit)의
**GitHub Flow 기반 단명 브랜치 전략**을 따른다 (file-converter·SACHO 등 다른 프로젝트와 동일 규칙).

## 0. Git Hooks 설정 (최초 1회 필수)

브랜치명·커밋 메시지 규칙은 `lefthook`으로 commit/push 시 자동 검증된다. 설치하지 않으면 검증 없이 통과되므로, 저장소를 처음 받으면 먼저 실행한다.

```bash
brew install lefthook     # Windows: scoop install lefthook
lefthook install
```

⚠️ 클라이언트 측 방어선이다. `--no-verify`로 우회하면 통과되며, 평소에는 서버 쪽 CI가 한 번 더 검사한다 — **Actions를 끈 동안(아래 '자동 검증' 안내)은 다시 검사하는 곳이 없으므로 병합 전 검증 G-01의 엄격 모드가 PR에 남긴 코멘트로 확인한다.**
훅을 일시적으로 끄려면 `LEFTHOOK=0 git push`, 특정 검사만 건너뛰려면 `LEFTHOOK_EXCLUDE=<이름> git push`를 쓴다
(`SKIP=`은 lefthook에서 동작하지 않는다 — SACHO 실측).

## 핵심 원칙
- **`main`이 유일한 영구 브랜치.** develop/staging 등 long-lived 브랜치 금지.
- **모든 변경은 단명 브랜치 → PR → squash merge.** main 직접 push 금지.
- 브랜치 수명 1~2일 이내. 머지 후 브랜치 즉시 삭제. (발표 준비 문서 PR은 면제 — 한시, AGENTS.md 6-1)
- 릴리스는 브랜치가 아닌 Git tag (`v0.1.0` 등).

## 브랜치 네이밍
`<type>/<lowercase-hyphen-name>` — 소문자·숫자·하이픈만 (한국어/대문자/언더스코어 금지), 3~5단어 권장.

| 접두어 | 용도 | 예시 |
|---|---|---|
| `feat/` | 신규 기능 | `feat/hybrid-retriever` |
| `fix/` | 버그 수정 | `fix/chunk-overlap` |
| `refactor/` | 동작 변경 없는 리팩터 | `refactor/loader-registry` |
| `docs/` | 문서만 변경 | `docs/planning-stage1` |
| `research/` | 탐색·실험 (임베딩 모델 비교 등) | `research/embedding-compare` |
| `data/` | 스키마·인덱스·데이터 파이프라인 | `data/vector-index-v2` |
| `chore/` | 빌드/CI/설정 | `chore/ci-setup` |
| `remove/` | 파일·기능 제거 | `remove/legacy-loader` |

## 커밋 메시지 · PR 제목
**Conventional Commits** — `<type>: <설명>`. subject는 한국어 허용, **첫 글자만 대문자(A-Z) 금지**.

```
feat: 하이브리드 검색 리트리버 추가     ✅
fix: PDF 청크 중복 제거                 ✅
Feat: Add retriever                     ❌ (대문자 시작)
```

PR 제목은 squash merge 후 main의 커밋 메시지가 되므로 위 형식 필수.

## 리뷰 요청
- PR 본문에는 리뷰어를 `@태그`하지 않는다. 리뷰·병합 확인 요청은 병합 전 검증 결과 코멘트의 마지막 줄에 병합할 사람을 `@태그`해서 한다 (DEC-043).
- 리뷰 코멘트는 결론만 쓰지 않고 근거(`파일:줄` 인용, 판단 이유)를 함께 남긴다.

## 자동 검증

> ⏸️ **2026-10-10부터 GitHub Actions를 임시로 껐다**(계정 한도, DEC-040). 그동안 PR의 CI 체크는 돌지 않고 GitHub가 병합을 막지 않는다 — push 때 lefthook이 `scripts/local_ci.sh`를 돌리고(훅 우회 금지), 병합 전 검증 G-01은 저장소 소유자(우지훈)가 `LOCAL_CI_REQUIRE_PR=1` 엄격 모드로 돌리고 스크립트가 PR에 남긴 `### 🧪 local CI (엄격)` 코멘트로 확인한다(출력을 손으로 옮기지 않는다, `docs/MERGE_PROTOCOL.md` 7절). 프런트(`frontend/`)를 바꾸면 `npm ci`·`npm run lint`·`npm run build`·`npm test` 결과를 PR에 적는다. 한도가 생기면 7절 5단계로 되돌리고 이 안내를 지운다.

- `.github/workflows/ci.yml` — uv로 설치 후 ruff lint·format 검사 + pytest (`uv sync --locked`라 `uv.lock` 누락도 잡음)
- `.github/workflows/pr-verify.yml` — PR 내용 상세 검증: 판정 필드·비밀값·RAG 수치 근거·PR 본문 필수 항목 + 저장소 정합성(type 목록 일치·문서 링크·AGENTS import). `scripts/ci/pr_checks.py`
- `.github/workflows/frontend-ci.yml` — React 화면(`frontend/`) 검사(`npm ci`·lint·build·test). **필수 체크가 아님**, `frontend/**`가 바뀐 PR에서만 돌고 `frontend/package.json`이 있을 때만 검사한다(`frontend/`가 없거나 `.nvmrc`·`.gitkeep`·`README.md`만 있으면 건너뜀, 그 밖의 파일이 있는데 `package.json`이 없으면 실패). `package.json`이 있는데 `.nvmrc`·`package-lock.json`이 없어도 실패 (DEC-032)
- `.github/workflows/merge-gate.yml` — 병합 게이트: 현재 head 기준 자동 리뷰·미해결 스레드 0·변경 요청 없음·✅ 검증 결과 코멘트(그 뒤 새 리뷰 없음) → 커밋 상태 `merge-gate`. **main 코드로만 실행** (DEC-009). `scripts/ci/merge_gate.py`. ⏸️ 2단계 도입 중이라 아직 필수 체크 아님
- `.github/workflows/branch-name-check.yml` — 브랜치명 규칙 CI 검증
- `.github/workflows/pr-title-check.yml` — PR 제목 Conventional Commits 검증
- `.github/workflows/stale-branches.yml` — 30일 방치 브랜치 주간 정리 (닫힌 PR·PR 없는 브랜치)
- `lefthook.yml` — 로컬 git 훅: 커밋 시 비밀 파일·개인키·1MB 초과 파일 차단 + ruff 자동 수정·포맷, 커밋 메시지 형식 검사, push 시 main 직접 push 차단·브랜치명 검사·CI 필수 검사 로컬 실행(`scripts/local_ci.sh`) (`scripts/check-*.sh`)
- PR 본문은 `.github/pull_request_template.md` 체크리스트를 채운다

> 브랜치 타입 목록을 바꿀 때는 이 문서의 표, `AGENTS.md`, `scripts/check-branch.sh`·`check-commit-msg.sh`,
> `branch-name-check.yml`의 PATTERN, `pr-title-check.yml`의 types **여섯 곳을 함께** 갱신한다. 하나라도 다르면 `pr-verify`가 실패한다.

## 머지 규칙
- **Squash merge만 허용** (merge commit/rebase merge 금지) · linear history 유지
- **필수 리뷰어는 없다** (룰셋 승인 0명, DEC-006). 대신 병합 전에 [`docs/MERGE_PROTOCOL.md`](docs/MERGE_PROTOCOL.md)의 게이트를 돌린다 — 자동 리뷰가 최신 커밋 기준으로 있고, 그 지적이 전부 처리(반영/반박/후속 이슈)됐고, 리뷰 스레드가 모두 해결됐는지 확인한 결과 표가 **PR 코멘트로 ✅ 게시된 뒤에만** 병합한다
- 작성자는 자기 PR을 직접 close하지 않는다
- **공동 작업 모드 (한시, ~2026-10-20, DEC-062)**: 병합은 작성자를 뺀 팀원 누구나 할 수 있고(게이트·PR 번호 지시·최신 main 확인은 그대로), 문서만 바뀌는 PR은 G-03 재리뷰를 조건부로 생략할 수 있다. 담당 파트 밖 수정, 브랜치 소유, 인계 문서 충돌 방지, 조사·테스트의 외부 근거는 `AGENTS.md` 6-1절을 따른다.
- 머지 후 원격 브랜치 삭제, 로컬은 정리(clean up)

## 비밀값
- API 키·토큰은 `.env`에만 둔다. `.env.example`에는 키 이름만 적는다.
- 실수로 커밋했다면 즉시 키를 폐기(rotate)하고 팀에 알린다 — 히스토리 삭제만으로는 부족하다.

## 저장소 설정으로 강제되는 것 (2026-10-01 적용, `jh3779/LG_CNS_RAG_main`)
| 정책 | 강제 수단 | 상태 |
|---|---|---|
| squash merge만 허용 (커밋 메시지 = PR 제목) | 저장소 설정 + 룰셋 `allowed_merge_methods` | ✅ 적용됨 |
| 머지 후 원격 브랜치 삭제 | 저장소 설정: `delete_branch_on_merge` | ✅ 적용됨 |
| 브랜치명·PR 제목 규칙 + lint·테스트 + PR 상세 검증 | CI 필수 상태 체크 4개 (`lint-and-test` · `check-branch-name` · `validate-pr-title` · `pr-verify`) | ✅ 적용됨 — 실패 시 병합 불가 (⏸️ 2026-10-10부터 필수 체크 해제·Actions 중단, DEC-040 — 복원은 `docs/MERGE_PROTOCOL.md` 7절 5단계) |
| 병합 게이트 (`merge-gate`) | CI 필수 상태 체크 | ⏸️ 2단계 도입 중 (DEC-009) — main 병합 후 다음 PR에서 동작 확인 뒤 필수로 |
| main 직접 push·force push·삭제 차단, PR 필수 | 룰셋 `main 보호` (Pro 플랜이라 private에서 동작) | ✅ 적용됨 — 필수 승인 0명, 대신 병합 전 검증 프로토콜(문서 규칙) |
| CODEOWNERS 승인 게이트 | 룰셋 "Require review from Code Owners" | ⬜ 팀원 확정 후 결정 |

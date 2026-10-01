# 병합 전 검증 프로토콜

> **원칙: 게이트 하나라도 ❌면 병합하지 않는다.**
>
> 이 저장소의 main 룰셋은 **필수 리뷰어를 두지 않는다**(승인 0명, DEC-006). 사람 승인 대신
> **자동 리뷰를 받고, 그 지적을 하나도 빠짐없이 처리했는지**를 이 문서의 게이트로 확인한다.
> 게이트 중 기계로 판정할 수 있는 것은 **CI가 필수 체크로 강제**한다(2-1절). 리뷰의 출처(G-02)와 내용 판단(지적을 제대로 처리했나, diff를 읽었나)은 기계가 못 하므로 **병합하는 사람이 직접 확인**한다.
>
> - 이 문서가 **기준(정본)** 이다. Claude Code의 실행 절차는 [`.claude/skills/pre-merge-check/SKILL.md`](../.claude/skills/pre-merge-check/SKILL.md).
>   둘이 어긋나면 이 문서에 맞춰 스킬을 고친다.
> - 다른 에이전트(Codex 등)는 이 문서의 명령을 그대로 실행한다.

---

## 0. 언제 적용하나

- 사용자가 **"병합해 줘", "머지 전 검토해 줘", "병합해도 돼?"** 라고 할 때 — 병합 버튼을 누르기 전에 항상.
- 에이전트가 PR 작업을 끝내고 "준비됐다"고 보고하기 전.
- 예외: 사용자가 특정 게이트를 **명시적으로** 건너뛰라고 한 경우만. 이때도 결과 코멘트에 `G-XX 스킵(사용자 지시)`를 남긴다.

## 1. 자동 리뷰란

PR의 **현재 head 커밋**을 대상으로, 사람이 아닌 리뷰어가 남긴 지적 목록이다. 아래 중 하나 이상이면 된다.

| 출처 | 어디에 남나 |
|---|---|
| 리뷰봇 (Codex, `review-bot-notify.yml`이 PR push를 알림) | PR 코멘트 — 첫 줄 `### 🤖 자동 리뷰 (Codex) — 커밋 <SHA>` (PR #1에서 게시 확인, 2026-10-01). push 몇 분 뒤에 올라오므로 결과 코멘트를 쓰기 전에 기다린다 |
| Claude Code `/code-review` 또는 리뷰 에이전트 | PR 코멘트로 게시 |
| 기타 AI 리뷰 도구 | PR 리뷰·코멘트 |

**자동 리뷰로 인정하는 조건**

- **리뷰 기준 커밋이 PR의 현재 head와 같아야 한다.**
  - GitHub 리뷰(Review)는 `.commit.oid == headRefOid`로 확인한다.
  - GitHub 리뷰로 남길 때는 **본문(요약)을 반드시 쓴다.** 인라인 코멘트만 있고 본문이 빈 리뷰는 `merge-gate`가 자동 리뷰로 세지 않는다(스레드 답글이 만드는 빈 리뷰와 구분할 수 없어서).
  - 코멘트로 남긴 리뷰는 **첫 줄을 `## 🤖 자동 리뷰 (head <짧은 SHA>)`** 로 쓰고, 그 SHA가 head와 일치해야 한다. (코멘트에는 커밋 정보가 없어서 첫 줄로 정한다.)
- **작성자 에이전트가 자기 코드를 같은 컨텍스트에서 "문제없음"이라고 하는 것은 자동 리뷰가 아니다.** 별도 리뷰 도구·에이전트(새 컨텍스트)로 리뷰한다.
- `## ✅/❌ 병합 전 검증 결과` 코멘트(4절)는 리뷰가 아니라 **게이트 결과**다. 자동 리뷰로 세지 않는다.
- **심각도는 리뷰어가 매긴다.** 작성자는 심각도를 낮출 수 없다.

> ⚠️ **알려진 한계** — 작성자 에이전트가 리뷰 도구를 직접 돌리고 지적을 스스로 "반박" 처리하는 것까지 구조적으로 막지는 못한다. 그래서 **반박은 반드시 근거(`파일:줄`)를 남기고**, 병합하는 사람이 4절 결과 코멘트의 "지적 처리 내역"에서 반박 항목을 직접 확인한다. 🔴 심각 지적은 반박할 수 없다.

---

## 2. 게이트

| ID | 게이트 | 통과 기준 | 확인 방법 |
|---|---|---|---|
| G-01 | **CI** | 필수 체크(`lint-and-test` · `check-branch-name` · `validate-pr-title` · `pr-verify`) 모두 pass. `merge-gate`는 결과 코멘트를 게시해야 통과하므로 결과 코멘트 작성 시점에는 보지 않는다 (지금은 2단계 도입 중이라 필수 아님, 2-1절) | `gh pr checks <N>` |
| G-02 | **자동 리뷰 존재** | 자동 리뷰가 1건 이상 있다. 없으면 **직접 돌려서** PR 코멘트로 남긴 뒤 진행 | `gh pr view <N> --json reviews,comments` |
| G-03 | **리뷰가 최신 커밋 기준** | 자동 리뷰의 기준 커밋 = 현재 head (1절 조건). 리뷰 뒤에 커밋이 추가됐으면 재리뷰 | 리뷰 `.commit.oid` 또는 코멘트 첫 줄의 SHA vs `headRefOid` (커밋 **시각** 비교는 rebase·amend 때 틀리므로 쓰지 않는다) |
| G-04 | **지적 전부 처리** | 모든 지적에 처리 결과가 있다: **반영**(커밋 SHA) / **반박**(근거 `파일:줄`) / **후속 이슈**(이슈 링크). 🔴 심각(버그·보안·데이터 손실·서비스 원칙 위반) 지적은 **반영만** 허용. 반영으로 커밋이 늘면 G-01·G-03부터 다시 | 리뷰 본문을 전부 읽고 표로 정리 |
| G-05 | **리뷰 스레드 해결** | 미해결 인라인 리뷰 스레드 0개 | 아래 [3절](#3-명령-모음) GraphQL |
| G-06 | **diff 정독 · PR 설명 일치** | `gh pr diff <N>` 전량을 읽었고, PR 제목·본문이 실제 변경과 맞는다 (요약만 보고 넘기지 않는다) | `gh pr diff <N>` |
| G-07 | **서비스 원칙 스윕** | 판정 필드(`applies` · `verdict` · `is_applicable`)·"적용됩니다/적용되지 않습니다"류 출력이 새로 생기지 않았다. 비밀값·`.env`가 없다 | 아래 grep |
| G-08 | **RAG 품질 근거** | 검색·답변·프롬프트·청킹·색인을 바꿨다면 PR 본문 "검증 방법"에 **같은 평가셋 before → after 수치**가 있다. 해당 없으면 "해당 없음" | PR 본문 확인 |
| G-09 | **의존성 · 인계 문서** | `pyproject.toml`을 바꿨으면 `uv.lock`도 바뀌었다. 의미 있는 진전·결정이면 `.agent/`가 갱신됐다 | `gh pr diff <N> --name-only` |

### 2-1. CI가 자동으로 확인하는 것

| 필수 체크 | 워크플로 → 스크립트 | 강제하는 게이트 | 판정 |
|---|---|---|---|
| `lint-and-test` | `ci.yml` | G-01, G-09 일부 | ruff · pytest · `uv sync --locked`(pyproject와 uv.lock 불일치) |
| `pr-verify` | `pr-verify.yml` → `scripts/ci/pr_checks.py` | G-07, G-08 + 저장소 정합성 | 코드·프롬프트에 판정 필드·문구(`applies`·`verdict`·`is_applicable` 변형 포함, 대소문자 무시 / `docs/`·루트 `*.md`·테스트·CI 제외 / 줄에 `principle-ok: <이유>` 주석으로 예외) · 커밋별 추가 줄 + 최종 diff의 비밀값 패턴·`.env` · RAG 경로 변경 시 "검증 방법"에 **지표 이름 + before → after 수치** · PR 본문 필수 항목(섹션 존재 포함) · 브랜치 type 목록 6곳 일치 · 문서 상대 링크 · `CLAUDE.md`의 `@AGENTS.md` |
| `merge-gate` ⏸️ | `merge-gate.yml` → `scripts/ci/merge_gate.py` | **G-03**, G-05 + 결과 코멘트 | 현재 head 기준 자동 리뷰 존재(리뷰 에이전트 `## 🤖 자동 리뷰 (head …)` · 리뷰봇 `### 🤖 자동 리뷰 (Codex) — 커밋 …` · 본문 있는 GitHub 리뷰) · 미해결 스레드 0 · 리뷰어별 마지막 상태가 `CHANGES_REQUESTED`가 아님 · 현재 head의 가장 최근 결과 코멘트가 ✅ **그리고 그 뒤에 새 리뷰가 없음**. 없으면 pending, ❌·미해결 스레드·변경 요청이면 failure |

⏸️ `merge-gate`는 **2단계 도입 중**이라 지금은 필수 체크가 아니다 (DEC-009). 아래 "🔒 실행 위치"로 바꾸면서, 이 워크플로가 main에 들어가기 전에는 PR에서 돌 수 없게 됐기 때문이다.
1단계: 필수 체크에서 빼고 PR #1(이 워크플로)을 main에 병합 → 2단계: 다음 PR에서 `merge-gate`가 실제로 상태를 게시하는 것을 확인한 뒤 필수 체크에 다시 넣는다. 그 전까지 이 게이트들은 4절 결과 코멘트로 사람이 확인한다.

- **🔒 실행 위치 (DEC-009)** — `merge-gate`는 상태를 기록하는 쓰기 권한을 가지므로 **main의 코드만** 실행한다. 트리거는 `pull_request_target`·`issue_comment`·`workflow_dispatch`(셋 다 main의 워크플로 파일로 돈다)이고, checkout도 main으로 고정하며 PR 정보는 API로만 읽는다. 그래서 PR이 `merge-gate.yml`이나 `merge_gate.py`를 고쳐도 자기 게이트에는 반영되지 않는다. PR 쪽 워크플로로 도는 `pull_request`·`pull_request_review` 트리거는 쓰지 않는다.
- **재판정** — 코멘트를 남기면 다시 판정한다(결과 코멘트 게시가 곧 재판정). GitHub 리뷰 제출·스레드 resolve는 main 코드로 도는 트리거가 없으므로(공식 문서 "Events that trigger workflows"에 `pull_request_review_thread` 없음, 2026-10-01 확인), 그 뒤에는 아래처럼 코멘트를 남기거나 Actions에서 `merge-gate`를 PR 번호로 수동 실행한다.
  ```bash
  gh pr comment <N> -b "merge-gate 재판정"
  ```
- RAG 경로는 `scripts/ci/pr_verify.toml`의 `rag-paths`로 정한다 (대소문자 무시, `docs/`·루트 `*.md`·`tests/` 제외 — `prompts/*.md`는 포함). `pyproject.toml`에 두지 않는 이유는 G-09(pyproject를 바꾸면 uv.lock도) 규칙과 부딪히기 때문이다. 수치를 낼 수 없는 정당한 경우는 **"## 검증 방법" 섹션 안에** `[skip-rag-evidence: 이유]`를 적는다.
- **CI가 판정하지 못하는 것**: **G-02(리뷰를 누가 썼나 — 출처)**, G-04(지적 처리가 타당한가), G-06(diff를 실제로 읽었나·PR 설명이 맞나), G-09의 `.agent/` 갱신 필요성. 이것들은 결과 코멘트를 쓰는 에이전트와 **병합하는 사람이 직접 확인하는 수동 게이트**다. `merge-gate`는 "현재 head에 리뷰 표시와 ✅ 결과 표시가 순서대로 있는지"까지만 본다.
- **⚠️ 알려진 한계 (CI)**
  - **같은 계정의 자기 인증 (G-02)**: 리뷰 에이전트·리뷰봇(Codex)·결과 코멘트가 모두 PR 작성자와 같은 `jh3779` 계정으로 올라간다. 그래서 작성자 혼자 표시 두 개를 달아 `merge-gate`를 통과시킬 수 있다. 리뷰 전용 계정(봇) 또는 GitHub App 도입 후 그 계정의 리뷰·결과만 인정한다 — 이슈 #4.
  - **상태 위조**: 쓰기 권한이 있는 사람은 자기 PR에 워크플로를 추가해 `merge-gate`라는 이름의 상태를 직접 기록할 수 있다(GitHub Actions의 상태는 모두 같은 앱 이름으로 기록됨). 필수 체크를 특정 GitHub App의 상태로 고정해야 막힌다 — 이슈 #4.
  - `pr-verify`·`lint-and-test`는 **PR의 코드로** 돈다(쓰기 권한 없음). 그래서 `scripts/ci/`나 테스트를 고치는 PR은 자기 검사를 약하게 만들 수 있다 — 이런 PR은 G-06에서 특히 diff를 확인한다.
  - 수치 근거(G-08)는 형식(지표 이름 + `숫자 → 숫자`)만 본다. 같은 평가셋인지·수치가 맞는지는 사람이 본다.
  - Dependabot·fork PR에서의 동작은 확인하지 않았다. 현재 private·Dependabot 없음 — 도입하면 확인한다.

로컬에서 미리 돌려 보기:

```bash
BASE_SHA=$(git merge-base origin/main HEAD) HEAD_SHA=HEAD PR_BODY="$(gh pr view <N> --json body -q .body)" \
  python3 scripts/ci/pr_checks.py
REPO=jh3779/LG_CNS_RAG_main PR_NUMBER=<N> python3 scripts/ci/merge_gate.py   # 상태는 게시하지 않음
```

---

## 3. 명령 모음

```bash
N=<PR 번호>
REPO=jh3779/LG_CNS_RAG_main

# G-01 CI
gh pr checks $N

# G-02 · G-03 현재 head, 리뷰(기준 커밋 포함), 코멘트 첫 줄
gh pr view $N --json headRefOid,reviews,comments \
  -q '{head: .headRefOid[0:7],
       reviews: [.reviews[] | {author: .author.login, state, commit: .commit.oid[0:7]}],
       comments: [.comments[] | {author: .author.login, at: .createdAt, first_line: (.body | split("\n")[0])}]}'
gh pr view $N --comments          # 본문까지 전부 읽기

# G-05 미해결 리뷰 스레드 (100개 초과 시 누락 — 그 규모가 되면 페이지네이션 추가)
gh api graphql -F o=${REPO%/*} -F r=${REPO#*/} -F n=$N -f query='
query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
  reviewThreads(first:100){nodes{isResolved path line comments(first:1){nodes{author{login} body}}}}}}}' \
  -q '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved|not)]'

# G-06 diff
gh pr diff $N

# G-07 서비스 원칙 · 비밀값 (추가된 줄만)
gh pr diff $N | grep -E '^\+' | grep -nEi 'applies|verdict|is_applicable|적용됩니다|적용되지 않습니다' || echo "판정 표현 없음"
gh pr diff $N --name-only | grep -E '(^|/)\.env($|\.)' | grep -v '\.env\.example' || echo ".env 없음"

# G-09 의존성 · 인계 문서
gh pr diff $N --name-only | grep -E '^(pyproject\.toml|uv\.lock|\.agent/)' || echo "의존성·.agent 변경 없음"
```

G-07 grep에 걸렸다고 바로 실패는 아니다 — 문서·테스트에서 "판정 필드를 만들지 않는다"고 **설명**하는 줄이면 통과. 답변 스키마·프롬프트·출력 코드에 들어간 경우만 ❌.

---

## 4. 결과 보고 — PR 코멘트로 남긴다

게이트를 돌린 뒤 **결과를 PR 코멘트로 게시한다** (사람이 병합 버튼 앞에서 바로 볼 수 있게). 첫 줄은 고정 문구로 시작한다.

```markdown
## ✅ 병합 전 검증 결과 (head `abc1234`)

| 게이트 | 결과 | 근거 |
|---|---|---|
| G-01 CI | ✅ | 3/3 pass |
| G-02 자동 리뷰 존재 | ✅ | /code-review (2026-10-01 14:30) |
| G-03 최신 커밋 기준 | ✅ | 리뷰 14:30 > 마지막 커밋 14:12 |
| G-04 지적 처리 | ✅ | 3건: 반영 2 (`def5678`), 반박 1 (`src/x.py:42` — 이유) |
| G-05 스레드 해결 | ✅ | 미해결 0 |
| G-06 diff·설명 | ✅ | 파일 4개 전량 확인 |
| G-07 원칙 스윕 | ✅ | 판정 표현 없음, .env 없음 |
| G-08 RAG 근거 | 해당 없음 | 검색·답변 코드 변경 없음 |
| G-09 의존성·인계 | ✅ | uv.lock 동반, HANDOFF 갱신 |

### 자동 리뷰 지적 처리 내역
| # | 지적 (출처) | 심각도 | 처리 | 근거 |
|---|---|---|---|---|

@<병합할 사람> 병합 전 검증 확인 요청드립니다.
```

- 하나라도 ❌면 제목을 `## ❌ 병합 전 검증 결과`로 쓰고, 실패 게이트·원인·제안 수정을 적는다. **병합하지 않는다.**
- 이 코멘트를 남긴 뒤 커밋이 추가되면 결과는 무효 — 다시 돌린다.

## 5. 병합은 누가 하나

- 기본은 **사람**이 위 코멘트를 보고 squash merge 한다.
- 에이전트는 사용자가 **그 PR의 병합을 명시적으로 지시한 경우에만** 병합할 수 있고, 그때도 4절 코멘트가 ✅로 게시된 뒤여야 한다. (Claude Code는 `.claude/settings.json`에서 이 명령이 매번 확인을 묻도록 돼 있다.)
- 병합 명령에는 **결과 코멘트에 적힌 head SHA를 반드시 붙인다.** 코멘트 게시 뒤에 push가 들어왔으면 GitHub이 병합을 거부한다.
  ```bash
  gh pr merge <N> --squash --match-head-commit <결과 코멘트의 head SHA(전체)>
  ```
- 사람이 웹에서 병합할 때도 결과 코멘트의 head SHA가 PR의 최신 커밋과 같은지 보고 누른다.

## 6. 이 문서의 갱신 규칙

- 병합 뒤에 문제가 발견되면, 어느 게이트가 놓쳤는지 따져서 **게이트를 추가하거나 고친다.** "다음엔 조심하자"로 끝내지 않는다.
- 게이트가 너무 많아 실제로 안 지켜지면 그것도 실패다. 지켜지지 않는 게이트는 빼거나 CI로 옮긴다.

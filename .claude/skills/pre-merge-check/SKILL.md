---
name: pre-merge-check
description: >
  Run the pre-merge verification protocol for recall-casebook before ANY pull request
  in this repository is merged. This repo requires no human reviewers, so this
  skill confirms an automated review exists for the latest head commit, that
  every review finding was handled (fixed / rebutted with evidence / tracked as
  an issue), that review threads are resolved, CI passes, the diff was read in
  full, and the service principles (no verdict fields, no secrets) hold — then
  posts a gate table as a PR comment. If any gate fails, do NOT merge. Use this
  whenever about to merge or asked: 병합해 줘, 머지 전, 머지해도 돼, 병합 전 검토,
  PR 병합, gh pr merge, 리뷰 확인하고 병합, "준비됐어?" — invoke it automatically
  before every merge in this repo, not only when explicitly asked.
---

# Pre-Merge Check — recall-casebook

정본 기준: [`docs/guides/MERGE_PROTOCOL.md`](../../../docs/guides/MERGE_PROTOCOL.md). 이 스킬은 그 문서의 게이트를
실제로 수행하는 절차다. 둘이 어긋나면 문서가 정본 — 이 스킬을 고친다.

**원칙: 하나라도 ❌면 병합하지 않는다.** 필수 리뷰어가 없는 저장소라 이 게이트가 사람 승인을 대신한다.

## 0. 준비

```bash
N=<PR 번호>
REPO=jh3779/recall-casebook
gh pr view $N --json title,body,headRefName,headRefOid,state
```

PR이 `OPEN`이 아니면 중단하고 보고한다.

## 1. G-01 CI

```bash
gh pr checks $N
```

`lint-and-test` · `check-branch-name` · `validate-pr-title` · `pr-verify`가 모두 pass여야 한다. **Actions를 끈 동안**(MERGE_PROTOCOL 7절)에는 체크가 없으므로 대신 `LOCAL_CI_REQUIRE_PR=1 TEST_DATABASE_URL=<일회용 Postgres> bash scripts/local_ci.sh`를 돌린다. 통과하면 스크립트가 `### 🧪 local CI (엄격) — 커밋 <SHA>` 코멘트를 PR에 직접 남기고(못 남기면 실패로 끝나므로 다시 돌린다), G-01 근거는 그 코멘트뿐이다(손으로 옮겨 적은 줄은 근거가 아니다). 테스트 결과는 출력을 파일로 받아 **종료 코드로** 확인한다 — `| tail`로 넘기면 실패 종료 코드가 사라진다. `merge-gate`는 9절 결과 코멘트를 게시해야 통과하므로 이 단계에서는 pending이 정상이다. `pr-verify`가 실패하면 Actions 요약 표에서 어느 검사가 ❌인지 보고 고친다. pending이면 `gh pr checks $N --watch`로 기다린다. fail이면 로그(`gh run view <id> --log-failed`)로 원인을 찾아 보고한다.

## 2. G-02 · G-03 자동 리뷰 존재 + 최신 커밋 기준

```bash
gh pr view $N --json headRefOid,reviews,comments \
  -q '{head: .headRefOid[0:7],
       reviews: [.reviews[] | {author: .author.login, state, commit: .commit.oid[0:7]}],
       comments: [.comments[] | {author: .author.login, at: .createdAt, first_line: (.body | split("\n")[0])}]}'
gh pr view $N --comments
```

- 자동 리뷰가 **현재 head 기준**인지 본다: GitHub 리뷰는 `commit == head`, 코멘트형 리뷰는 첫 줄의 SHA == head. 커밋 **시각**으로 비교하지 않는다(rebase·amend 때 틀림).
  - 리뷰 에이전트: `## 🤖 자동 리뷰 (head <SHA>)`
  - **리뷰봇(Codex): `### 🤖 자동 리뷰 (Codex) — 커밋 <SHA>`** — push 몇 분 뒤에 자동으로 올라온다. **결과 코멘트를 쓰기 전에 현재 head에 대한 Codex 리뷰가 올라왔는지 확인하고, 올라왔으면 그 지적도 4절에서 전부 처리한다.** (PR #1에서 이 리뷰를 놓쳐 ✅ 결과를 무효화한 적이 있다.)
- **작성자가 협업자가 아닌 코멘트·리뷰는 근거로 세지 않는다.** 저장소가 공개라 누구나 "자동 리뷰"·"병합 전 검증 결과"로 시작하는 코멘트를 쓸 수 있다. 읽을 때는 `author_association`이 `OWNER`·`MEMBER`·`COLLABORATOR`가 아닌 것을 제외한다(`merge_gate.py`도 같은 기준으로 거르고, 미해결 스레드는 연 사람이 협업자인 것만 센다). 코멘트는 `gh api repos/$REPO/issues/$N/comments --paginate --jq '.[] | {id, author_association, first_line: (.body|split("\n")[0])}'`(`--paginate` 필수 — 기본은 30개까지만), GitHub 리뷰는 `gh pr view $N --json reviews -q '.reviews[] | {author: .author.login, authorAssociation, state}'`로 본다.
- **`gh pr view $N --comments` 전체를 읽는다.** 내가 올린 코멘트만 보지 않는다 — 같은 계정(`jh3779`)으로 리뷰봇이 올린 코멘트가 섞여 있다.
- `## ✅/❌ 병합 전 검증 결과` 코멘트는 자동 리뷰로 세지 않는다.
- **없거나 오래됐으면 직접 리뷰를 돌린다.** 이 세션에서 PR 코드를 직접 작성했다면 같은 컨텍스트로 "문제없음"을 판단하지 말고, `/code-review` 또는 `review-agent` 같은 별도 컨텍스트 리뷰어를 쓴다.
- 직접 돌린 리뷰 결과는 **원문 그대로** PR 코멘트로 게시한다 (`gh pr comment $N --body-file <파일>`). 첫 줄은 `## 🤖 자동 리뷰 (head <짧은 SHA>)`. 요약·재작성하지 않고, 차수마다(커밋이 바뀔 때마다) 게시한다. 게시하지 않은 차수는 근거로 인용하지 않는다.
- **리뷰 요청문은 중립으로** — PR 번호·head·기준 문서·"이전 리뷰는 PR 코멘트에서 직접 읽고 작성자 설명을 믿지 말고 코드로 확인"만 넣는다. 작성자의 처리 설명·"반영했다"는 주장·이전 지적 목록을 넣지 않는다. 게시하는 리뷰 코멘트 끝에 요청문 전문을 `<details><summary>리뷰 요청문</summary>…</details>`로 붙인다.

## 3. G-04 지적 전부 처리

리뷰 본문을 **전부** 읽고 지적마다 처리 결과를 표로 만든다.

| 처리 | 조건 |
|---|---|
| 반영 | 고친 커밋 SHA. 고쳤으면 커밋이 추가된 것이므로 **G-01·G-03부터 다시** |
| 반박 | 근거 `파일:줄` + 왜 문제가 아닌지 |
| 후속 이슈 | `gh issue create`로 만든 이슈 링크 (링크 없는 "후속"·"다음 체크포인트"는 불가) |

분류는 이 셋뿐이다 — "확인"·"반박(선택)"을 쓰지 않는다(선택 개선을 하지 않으면 반박으로 근거를 적는다). 🟡(Codex 중)은 반영 또는 근거 있는 반박, 🟢(Codex 하)는 후속 이슈로 묶어 넘길 수 있다(MERGE_PROTOCOL G-04). Codex 위험도는 **상 = 🔴, 중 = 🟡, 하 = 🟢**로 읽는다.
🔴 심각(버그 · 보안 · 데이터 손실 · 서비스 원칙 위반, Codex 상) 지적은 **반영만** 허용한다(예외 없음). **심각도는 리뷰어가 매긴 대로** 쓰고 낮추지 않는다. 반박은 근거를 남겨 병합하는 사람이 확인할 수 있게 한다. 처리 방향이 애매하면 사용자에게 묻는다.

## 4. G-05 리뷰 스레드 해결

```bash
gh api graphql -F o=${REPO%/*} -F r=${REPO#*/} -F n=$N -f query='
query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
  reviewThreads(first:100){nodes{isResolved path line comments(first:1){nodes{author{login} authorAssociation body}}}}}}}' \
  -q '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved|not) | select((.comments.nodes[0].authorAssociation) as $a | $a == null or $a == "OWNER" or $a == "MEMBER" or $a == "COLLABORATOR")]'
```

외부인(협업자가 아닌 작성자)이 연 스레드는 이 명령이 걸러 낸다(`merge_gate.py`와 같은 기준 — 작성자를 알 수 없으면 센다). 걸러진 스레드도 사람이 한 번 읽는다. 결과가 `[]`여야 한다 (100개 초과 시 누락 — 그 규모가 되면 페이지네이션 추가). 남은 스레드는 3절처럼 처리한 뒤 답글로 처리 내역을 남긴다. 스레드를 resolve하는 것은 사람이 하거나, 처리 내역을 답글로 남긴 뒤에만 한다.

## 5. G-06 diff 정독 · PR 설명 일치

```bash
gh pr diff $N --name-only
gh pr diff $N
```

전량을 읽는다. 파일마다 무엇이 왜 바뀌었는지 설명할 수 있어야 통과. PR 제목·본문이 과장·누락 없이 실제 변경을 설명하는지 대조한다.

## 6. G-07 서비스 원칙 스윕

```bash
gh pr diff $N | grep -E '^\+' | grep -nEi 'applies|verdict|is_applicable|적용됩니다|적용되지 않습니다' || echo "판정 표현 없음"
gh pr diff $N --name-only | grep -E '(^|/)\.env($|\.)' | grep -v '\.env\.example' || echo ".env 없음"
```

걸린 줄이 답변 스키마·프롬프트·출력 코드면 ❌. 원칙을 **설명**하는 문서·테스트 줄이면 통과(근거에 그렇게 적는다).

## 7. G-08 RAG 품질 근거

변경 파일에 검색·답변·프롬프트·청킹·색인 코드가 있으면 PR 본문 "검증 방법"에 같은 평가셋 before → after 수치가 있어야 한다. 없으면 ❌. 해당 파일이 없으면 "해당 없음". 결과 코멘트에는 그 수치가 **재측정**인지 **불변 추정**인지 MERGE_PROTOCOL 2절 G-08의 정의와 고정 명령(`git diff --stat <잰 커밋> <head> -- server scripts/defect_precedent`)대로 구분해 적는다.

## 8. G-09 의존성 · 인계 문서

```bash
gh pr diff $N --name-only | grep -E '^(pyproject\.toml|uv\.lock|\.agent/)' || echo "의존성·.agent 변경 없음"
```

`pyproject.toml`만 있고 `uv.lock`이 없으면 ❌. 결정·진전이 있는 PR인데 `.agent/` 갱신이 없으면 ❌(단순 수정 PR은 해당 없음).

## 9. 결과 게시

`docs/guides/MERGE_PROTOCOL.md` 4절 형식으로 결과 표 + 지적 처리 내역을 만들어 **PR 코멘트로 게시**한다. 첫 줄에 **head 짧은 SHA**를, 마지막 줄에 병합에 쓸 **head 전체 SHA**를 넣는다. 게시한 결과 코멘트는 **고치지 말고** 틀렸으면 새 코멘트로 다시 올린다(수정하면 `merge-gate`가 무효로 본다). G-02 근거에는 리뷰 출처(도구·에이전트 이름)를 적는다.

```bash
gh pr comment $N --body-file <결과.md>
gh pr checks $N --watch   # merge-gate가 필수 체크로 도입된 뒤(2단계)에만 의미 있음 — 1단계에선 이 PR에서 안 돈다
```

`merge-gate`가 success가 아니면 Actions 요약을 보고 원인(리뷰 SHA 불일치, 미해결 스레드, 변경 요청 등)을 해결한다. `merge-gate`는 main 코드로 돌며 코멘트가 올라오면 다시 판정한다. GitHub 리뷰 제출·스레드 resolve 뒤처럼 다시 돌지 않았으면 재판정 코멘트를 남긴다:

```bash
gh pr comment $N -b "merge-gate 재판정"
```

`merge-gate`가 필수 체크가 아닌 동안(2단계 도입 중, MERGE_PROTOCOL 2-1절)·Actions를 끈 동안에는 로컬에서 읽기 전용으로 돌린다 — 결과 코멘트를 쓰기 전에 한 번(출력을 G-02·G-03 근거에 붙임), 게시한 뒤 한 번(`success` 확인):

```bash
REPO=jh3779/recall-casebook PR_NUMBER=$N uv run python scripts/ci/merge_gate.py   # POST_STATUS 없음 = 상태 게시 안 함
```

- 전부 ✅ → 코멘트 마지막 줄에 병합할 사람을 `@태그`하고 "병합 전 검증 확인 요청드립니다".
- 하나라도 ❌ → 제목을 `## ❌ 병합 전 검증 결과`로, 실패 게이트·원인·제안 수정을 적는다. 병합하지 않는다.

## 10. 병합 (사용자가 명시적으로 지시한 경우만)

전부 ✅인 코멘트를 게시한 뒤, 사용자가 **이 PR 번호를 들어** 병합을 지시했을 때만 한다. 번호 없는 "병합해 줘"는 어느 PR인지 번호로 되묻는다.

병합 명령 **바로 앞에서** main이 바뀌지 않았는지 확인한다(PR #69는 #68 병합 31초 뒤 main이 바뀐 채 병합됐다). 실패하면 main을 합쳐 push하고 1절부터 다시 한다. 여러 PR을 연달아 병합하면 앞 PR을 병합할 때마다 다음 PR에서 이 확인부터 한다.

```bash
if ! git fetch origin main || ! git merge-base --is-ancestor origin/main <head 전체 SHA>; then
  echo "❌ main이 바뀜 — 합치고 다시 검증"; exit 1
fi
gh pr merge $N --squash --match-head-commit <결과 코멘트에 적은 head SHA(전체)>
```

`--match-head-commit`은 빼지 않는다 — 결과 코멘트 뒤에 push가 들어왔으면 GitHub이 병합을 거부한다. `.claude/settings.json`이 이 명령에 매번 확인을 묻는다. 병합 후 `git switch main && git pull`.

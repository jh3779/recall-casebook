# git 명령어 설명서

이 저장소에서 실제로 쓰는 git·gh 명령이 **무엇을 하는지, 언제 쓰는지, 무엇을 조심하는지**를 정리한 사전이다.
매일의 작업 순서는 [`시작하기.md`](시작하기.md) 4절, 브랜치·커밋·PR 규칙 원문은 [`CONTRIBUTING.md`](../../CONTRIBUTING.md)에 있다.

---

## 1. 먼저 알아 둘 개념 세 가지

**① 세 칸 — 작업 폴더 → 스테이징 → 커밋**

```text
[작업 폴더]  ──git add──▶  [스테이징]  ──git commit──▶  [커밋(내 컴퓨터 이력)]  ──git push──▶  [GitHub]
 파일을 고친 상태          "이번에 저장할 것" 목록        저장된 한 장면                      팀이 보는 곳
```

고친다고 바로 저장되지 않는다. `add`로 고르고 `commit`으로 저장하고 `push`로 올린다.

**② 로컬과 원격** — 내 컴퓨터의 저장소(로컬)와 GitHub의 저장소(원격, 이름 `origin`)는 따로 있다. `pull`·`fetch`로 받아 오고 `push`로 올린다. 서로 자동으로 맞춰지지 않는다.

**③ 브랜치** — 같은 저장소 안의 독립된 작업 줄기다. `main`은 팀 공용 기준선이라 **직접 커밋·push하지 않고**, 작업마다 브랜치를 만들어 PR로 합친다.

---

## 2. 매일 쓰는 명령

| 명령 | 하는 일 | 언제 | 조심할 것 |
|---|---|---|---|
| `git status` | 지금 어떤 파일이 바뀌었고 무엇이 스테이징됐는지 본다 | 아무 때나, 특히 커밋 전 | 습관처럼 자주 본다 |
| `git switch main` | `main` 브랜치로 옮겨 간다 | 새 작업 시작 전 | 커밋 안 한 변경이 있으면 막힐 수 있다 (4절 `stash`) |
| `git pull` | 지금 브랜치와 짝인 원격 브랜치(예: `main` ↔ `origin/main`)의 새 커밋을 받아 합친다 | `main`으로 옮긴 직후 | 자기 브랜치에서 `pull`해도 `main`의 변경은 들어오지 않는다 — `main`을 반영하려면 4절 `fetch` + `merge origin/main` |
| `git switch -c docs/my-change` | 지금 위치에서 새 브랜치를 만들고 옮겨 간다 | 작업 시작 | 이름은 `<type>/<소문자-하이픈>` (5절) |
| `git diff` | 아직 스테이징 안 한 변경 내용을 줄 단위로 본다 | 커밋 전 확인 | `git diff --staged`는 스테이징한 것만 본다 |
| `git add <파일>` | 그 파일의 지금 상태를 스테이징한다 | 저장할 파일을 고를 때 | `git add .`은 의도치 않은 파일(데이터·`.env`)까지 넣을 수 있어 파일을 지정하는 편이 안전하다 |
| `git commit -m "docs: 설명"` | 스테이징한 것을 커밋으로 저장한다 | 한 덩어리 일이 끝났을 때 | 커밋 직전에 훅이 검사한다 (5절) |
| `git push -u origin <브랜치>` | 내 브랜치를 GitHub에 올린다. `-u`는 다음부터 `git push`만 쳐도 되게 연결한다 | 처음 올릴 때 | `main`에서 push하면 훅이 막는다 |
| `git push` | 연결된 원격 브랜치에 새 커밋을 올린다 | 두 번째부터 | — |
| `git log --oneline -5` | 최근 커밋 5개를 한 줄씩 본다 | 무엇이 쌓였는지 확인 | — |

---

## 3. GitHub CLI (`gh`)

| 명령 | 하는 일 |
|---|---|
| `gh auth login` | GitHub 로그인 (1회) |
| `gh pr create --title "docs: 설명" --body-file pr.md` | 지금 브랜치로 PR을 만든다. **본문에는 PR 템플릿(`.github/pull_request_template.md`)의 섹션이 있어야 한다** — `## 변경 요약`(내용), `## 변경 유형`(체크 1개 이상), `## 관련 이슈`(없으면 "없음")가 비면 필수 검사 `pr-verify`가 실패한다. 제목은 `<type>: 한국어 설명` |
| `gh pr create --fill` | 커밋 메시지로 제목·본문을 채운다. 템플릿 섹션이 들어가지 않으므로, 쓰면 만든 뒤 `gh pr edit <번호> --body-file pr.md`나 웹에서 본문을 템플릿대로 고친다 |
| `gh pr view <번호>` | PR 내용·상태를 본다. `--comments`를 붙이면 리뷰 코멘트까지 본다 |
| `gh pr checks <번호>` | 자동 검사(CI) 결과를 본다. 필수 4개(`lint-and-test`·`check-branch-name`·`validate-pr-title`·`pr-verify`)가 pass여야 한다 |
| `gh pr list` | 열린 PR 목록 |
| `gh issue view <번호>` | 이슈 내용 (예: 파트 분배 이슈 #24) |

병합은 **squash merge**만 쓴다 — PR의 커밋들이 PR 제목 한 줄로 합쳐져 main에 들어간다. 병합 전에는 [`MERGE_PROTOCOL.md`](MERGE_PROTOCOL.md)의 검증을 거친다.

---

## 4. 상황별 처방

| 상황 | 명령 | 설명 |
|---|---|---|
| 내 브랜치에 최신 `main`을 반영하고 싶다 | `git fetch origin` → `git merge origin/main` | `fetch`는 받아 오기만 하고, `merge`가 합친다. 충돌이 나면 표시된 파일을 고치고 `git add` → `git commit` |
| 스테이징을 취소하고 싶다 | `git restore --staged <파일>` | 파일 내용은 그대로, 스테이징 목록에서만 뺀다 |
| 아직 `add`하지 않은 변경을 버리고 싶다 | `git restore <파일>` | 스테이징된 상태로 되돌린다(`add`한 내용은 남는다). 마지막 커밋 상태로 완전히 되돌리려면 `git restore --staged --worktree <파일>`. **버린 변경은 복구되지 않는다** |
| 커밋 안 한 변경을 잠시 치우고 다른 브랜치로 가야 한다 | `git stash` → (작업 후) `git stash pop` | 변경을 임시 보관했다가 다시 꺼낸다. **새로 만든(추적 안 되는) 파일은 기본으로 치우지 않는다** — 함께 치우려면 `git stash -u` |
| 방금 한 커밋 메시지를 고치고 싶다 (아직 push 전) | `git commit --amend -m "docs: 새 메시지"` | push한 뒤에는 쓰지 않는다 — 이력이 바뀌어 다시 올리려면 force push가 필요하다. **훅에 막혀 커밋이 만들어지지 않았을 때는 `--amend`를 쓰지 않는다** — 바로 앞의 (이미 push했을 수 있는) 커밋이 고쳐진다. 메시지를 고쳐 `git commit -m`을 다시 실행한다 |
| 브랜치 이름을 잘못 지었다 | `git branch -m docs/correct-name` | 지금 브랜치 이름을 바꾼다. 새 이름도 규칙(영문 소문자·숫자·하이픈)을 지켜야 push가 통과한다 |
| PR이 병합된 뒤 정리 | `git switch main` → `git pull` → `git branch -d <브랜치>` | 원격 브랜치는 병합 때 자동 삭제된다. squash merge라 로컬 브랜치가 git 이력상 "병합 안 됨"으로 보여 `-d`가 거부할 수 있다. 그때는 ① PR이 Merged이고 ② 로컬 브랜치 끝 커밋이 PR의 마지막 커밋과 같은지(`git rev-parse <브랜치>`와 `gh pr view <번호> --json headRefOid -q .headRefOid`) 확인한 뒤에만 `git branch -D <브랜치>`로 지운다. 다르면 병합 뒤 새 커밋이 있다는 뜻이니 지우지 않는다 |
| 두 작업을 동시에 (AI 세션 두 개 등) | 기존 브랜치: `git worktree add ../폴더 <브랜치>` / 새 브랜치: `git worktree add -b <새-브랜치> ../폴더` | 한 저장소에서 폴더를 하나 더 만들어 다른 브랜치를 연다. 같은 폴더에서 두 세션이 git을 만지지 않게 한다. 이미 다른 폴더에서 열린 브랜치는 열 수 없다 |

---

## 5. 훅이 막을 때 — 메시지와 해결

`lefthook install`을 해 두면 커밋·push 직전에 아래 검사가 돈다 (`lefthook.yml`).

| 시점 | 검사 | 막혔을 때 메시지 | 해결 |
|---|---|---|---|
| 커밋 | 커밋 메시지 형식 | `❌ 커밋 메시지가 Conventional Commits 형식이 아닙니다.` | `<type>: <설명>` 형식으로. type은 `feat fix refactor docs research data chore remove` 8개. **설명 첫 글자가 영어 대문자면 안 된다** — 예: `docs: PR #26 정리`는 막히고 `docs: 인계 문서 정리`는 통과 |
| 커밋 | `.env`·개인키·1MB 초과 파일 | 해당 파일 안내 | `git restore --staged <파일>`로 빼기 |
| 커밋 | ruff 린트·포맷 (`.py`) | ruff 오류 | 대부분 자동으로 고쳐 다시 넣어 준다. 남은 것만 손으로 고치고 다시 커밋 |
| push | `main` 직접 push | `❌ main 브랜치에 직접 push 금지.` | `git switch -c <type>/<이름>`으로 브랜치를 만들어 push한다(커밋이 그대로 새 브랜치로 따라온다). **이미 `main`에 커밋한 상태였다면** 로컬 `main`이 원격과 갈라진 채 남으므로, `reset --hard`로 혼자 지우지 말고 팀원에게 정리를 부탁한다 |
| push | 브랜치명 형식 | `❌ 브랜치명 '…'이 규칙을 위반합니다.` | `git branch -m <type>/<소문자-하이픈>` (한국어·대문자·밑줄 금지) |

---

## 6. 이 저장소에서 하지 않는 것

| 하지 않는 것 | 이유 |
|---|---|
| `main`에 직접 커밋·push | 팀 공용 기준선. 모든 변경은 PR과 병합 전 검증을 거친다 |
| `git commit --no-verify`, `LEFTHOOK=0` | 훅 우회. 우회해도 GitHub 검사에서 다시 걸린다 |
| `git push --force` | 남의 커밋을 덮어쓸 수 있다. 꼭 필요하면 요청을 받은 뒤 `--force-with-lease`로만 |
| `git reset --hard`, 공용 브랜치 이력 고치기 | 커밋하지 않은 변경과 이력이 사라진다 |
| 데이터·`.env` 커밋 | 커밋한 것은 지워도 git 이력에 남는다. 원본·결과물은 스크립트로 다시 만든다 |
| 남의 브랜치에 말없이 push | 그 사람의 작업과 충돌한다. 먼저 묻는다 |

---

## 7. 한 번에 보는 작업 한 바퀴

```bash
git switch main && git pull                 # 1. 최신 main
git switch -c docs/setup-guide-fix          # 2. 브랜치
# ... 파일 수정 ...
git status && git diff                      # 3. 무엇이 바뀌었나
uv run ruff check . && uv run ruff format --check . && uv run pytest   # 4. 검사 (AGENTS.md 4절)
git add docs/guides/환경셋팅.md                     # 5. 고르기
git commit -m "docs: 환경셋팅 안내 오타 수정"  # 6. 저장 (훅 검사)
git push -u origin docs/setup-guide-fix     # 7. 올리기 (훅 검사)
gh pr create --title "docs: 환경셋팅 안내 오타 수정" --body-file pr.md   # 8. PR (본문은 템플릿 섹션대로) → 리뷰 → 병합 전 검증 → squash merge
```

#!/usr/bin/env bash
# local_ci.sh — CI 필수 검사 4개(lint-and-test · check-branch-name · validate-pr-title · pr-verify)를 로컬에서 그대로 돈다.
#
# 쓰는 곳:
#   - lefthook pre-push(03-local-ci) — push 전에 자동으로 돈다.
#   - Actions 한도가 바닥나 CI를 끈 동안의 병합 전 검증 G-01 근거(docs/MERGE_PROTOCOL.md 8절) —
#     `bash scripts/local_ci.sh` 출력 마지막 줄(검사한 커밋 SHA)을 결과 코멘트에 붙인다.
#
# 검사 대상은 **커밋된 HEAD**다. 작업 트리의 커밋하지 않은 변경이 결과에 섞이지 않게 HEAD를 임시 worktree에 꺼내서 돈다.
# PR이 열려 있으면 gh로 제목·본문을 읽어 제목 규칙과 PR 본문 검사(변경 요약·검증 방법 수치 등)도 돈다.
# DB 테스트(tests/test_load_db.py의 pg 테스트)는 TEST_DATABASE_URL이 있을 때만 필수로 돈다 — CI는 Postgres 17을 띄워 REQUIRE_DB_TESTS=1로 돈다.
#   로컬 Postgres: docker run -d --rm --name lgcns-test-pg -e POSTGRES_PASSWORD=localtest -p 54331:5432 postgres:17
#                  TEST_DATABASE_URL=postgresql://postgres:localtest@localhost:54331/postgres bash scripts/local_ci.sh

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
HEAD_SHA=$(git -C "$ROOT" rev-parse HEAD)
BRANCH=$(git -C "$ROOT" branch --show-current)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/local-ci.XXXXXX")
cleanup() { git -C "$ROOT" worktree remove --force "$TMP" >/dev/null 2>&1 || rm -rf "$TMP"; }
trap cleanup EXIT

git -C "$ROOT" worktree add --detach --quiet "$TMP" "$HEAD_SHA"
cd "$TMP"

echo "== [1/4] lint-and-test (커밋 ${HEAD_SHA:0:7})"
uv sync --locked --quiet
uv run --locked ruff check .
uv run --locked ruff format --check .
if [[ -n "${TEST_DATABASE_URL:-}" ]]; then
  REQUIRE_DB_TESTS=1 uv run --locked pytest -q -rs
else
  echo "   (TEST_DATABASE_URL 없음 — DB 테스트는 건너뜀. CI와 똑같이 하려면 위 docker 명령으로 Postgres를 띄운다)"
  uv run --locked pytest -q
fi
if [[ -f frontend/package.json ]] && git -C "$ROOT" diff --name-only "$(git -C "$ROOT" merge-base origin/main "$HEAD_SHA")" "$HEAD_SHA" | grep -q '^frontend/'; then
  echo "   frontend 변경 — npm 검사"
  (cd frontend && npm ci --silent && npm run lint --if-present && npm run build --if-present && npm test --if-present)
fi

echo "== [2/4] check-branch-name ($BRANCH)"
if [[ "$BRANCH" != "main" ]]; then
  # 임시 worktree는 detached라 브랜치 이름을 원래 저장소에서 읽어 같은 규칙으로 본다
  (cd "$ROOT" && bash scripts/check-branch.sh name)
fi

echo "== [3/4] validate-pr-title · [4/4] pr-verify"
git -C "$ROOT" fetch --quiet origin main || echo "   (origin/main을 받지 못함 — 마지막으로 받은 origin/main 기준)"
BASE_SHA=$(git -C "$ROOT" merge-base origin/main "$HEAD_SHA")
if PR=$(cd "$ROOT" && gh pr view --json title,body 2>/dev/null); then
  PR_TITLE=$(printf '%s' "$PR" | python3 -c 'import json,sys; print(json.load(sys.stdin)["title"])')
  PR_BODY=$(printf '%s' "$PR" | python3 -c 'import json,sys; print(json.load(sys.stdin)["body"])')
  export PR_TITLE PR_BODY
else
  echo "   (열린 PR이 없거나 gh를 쓸 수 없음 — PR 제목·본문 검사는 PR을 연 뒤 다시 돌린다)"
fi
BASE_SHA="$BASE_SHA" HEAD_SHA="$HEAD_SHA" python3 scripts/ci/pr_checks.py

echo "✅ local CI 통과 — 커밋 $HEAD_SHA"

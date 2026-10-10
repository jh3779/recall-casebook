#!/usr/bin/env bash
# local_ci.sh — CI 필수 검사 4개(lint-and-test · check-branch-name · validate-pr-title · pr-verify)를 로컬에서 그대로 돈다.
#
# 쓰는 곳:
#   - lefthook pre-push(03-local-ci) — push 전에 자동으로 돈다.
#   - Actions 한도가 바닥나 CI를 끈 동안의 병합 전 검증 G-01 근거(docs/MERGE_PROTOCOL.md 7절) — 이때는 반드시
#       git merge origin/main   # CI가 보던 "PR을 main에 합친 상태"와 맞춘다
#       LOCAL_CI_REQUIRE_PR=1 TEST_DATABASE_URL=<일회용 Postgres> bash scripts/local_ci.sh
#     로 돌린 출력만 쓴다. 이 모드는 열린 PR이 없거나, PR의 최신 커밋(headRefOid)이 검사한 커밋과 다르거나,
#     DB 테스트를 건너뛰면 실패한다.
#
# 검사 대상은 **커밋된 HEAD**다. 작업 트리의 커밋하지 않은 변경이 결과에 섞이지 않게 HEAD를 임시 worktree에 꺼내서 돈다.
# 이 브랜치의 **열린** PR이 있으면 gh로 제목·본문을 읽어 제목 규칙과 PR 본문 검사(변경 요약·검증 방법 수치 등)도 돈다.
# DB 테스트(tests/test_load_db.py·test_rag_server.py의 pg 테스트)는 TEST_DATABASE_URL이 있을 때만 돈다 — CI는 Postgres 17(pgvector 포함)을 띄워 REQUIRE_DB_TESTS=1로 돈다.
#   ⚠️ 이 테스트는 대상 DB의 public 스키마를 지운다. 반드시 일회용 컨테이너에만 쓴다:
#      docker run -d --rm --name lgcns-test-pg -e POSTGRES_PASSWORD=localtest -p 54331:5432 pgvector/pgvector:pg17
#      TEST_DATABASE_URL=postgresql://postgres:localtest@localhost:54331/postgres bash scripts/local_ci.sh
# 프런트(frontend/) 검사는 CI 필수가 아니라(frontend-ci.yml) 여기 넣지 않았다 — frontend/package.json이 생기는 PR에서 함께 넣는다.
# AGENTS.md 6절의 훅 우회 금지(--no-verify, LEFTHOOK=0)는 CI를 끈 동안에도 그대로다.

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
HEAD_SHA=$(git -C "$ROOT" rev-parse HEAD)
BRANCH=$(git -C "$ROOT" branch --show-current)
REQUIRE_PR="${LOCAL_CI_REQUIRE_PR:-0}"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/local-ci.XXXXXX")
cleanup() { git -C "$ROOT" worktree remove --force "$TMP" >/dev/null 2>&1 || rm -rf "$TMP"; }
trap cleanup EXIT

if [[ "$REQUIRE_PR" == "1" ]]; then
  # 병합 근거로 쓸 때는 CI가 보던 "main에 합친 상태"와 맞춘다 — 최신 origin/main이 HEAD에 들어 있어야 한다
  # 이 스크립트·검사 스크립트(scripts/·lefthook.yml)는 작업 트리에서 돌므로, 커밋하지 않은 변경이 있으면 근거로 쓰지 않는다
  if ! git -C "$ROOT" diff --quiet HEAD -- scripts/ lefthook.yml; then
    echo "❌ scripts/·lefthook.yml에 커밋하지 않은 변경이 있다 — 커밋·push한 뒤 다시 돌린다"
    exit 1
  fi
  git -C "$ROOT" fetch --quiet origin main
  MAIN_AT_START=$(git -C "$ROOT" rev-parse origin/main)
  if ! git -C "$ROOT" merge-base --is-ancestor origin/main "$HEAD_SHA"; then
    echo "❌ 최신 origin/main이 검사할 커밋(${HEAD_SHA:0:7})에 들어 있지 않다 — git merge origin/main 후 push하고 다시 돌린다"
    exit 1
  fi
fi

git -C "$ROOT" worktree add --detach --quiet "$TMP" "$HEAD_SHA"
cd "$TMP"

echo "== [1/4] lint-and-test (커밋 ${HEAD_SHA:0:7})"
uv sync --locked --quiet
uv run --locked ruff check .
uv run --locked ruff format --check .
if [[ -n "${TEST_DATABASE_URL:-}" ]]; then
  REQUIRE_DB_TESTS=1 uv run --locked pytest -q -rs
  DB_TESTS="실행됨"
else
  if [[ "$REQUIRE_PR" == "1" ]]; then
    echo "❌ LOCAL_CI_REQUIRE_PR=1인데 TEST_DATABASE_URL이 없다 — 병합 근거로 쓰려면 DB 테스트까지 돌린다"
    exit 1
  fi
  echo "   (TEST_DATABASE_URL 없음 — DB 테스트는 건너뜀. CI와 똑같이 하려면 머리말의 일회용 Postgres를 띄운다)"
  uv run --locked pytest -q
  DB_TESTS="건너뜀"
fi

echo "== [2/4] check-branch-name ($BRANCH)"
if [[ "$BRANCH" != "main" ]]; then
  # 임시 worktree는 detached라 브랜치 이름을 원래 저장소에서 읽어 같은 규칙으로 본다
  (cd "$ROOT" && bash scripts/check-branch.sh name)
fi

echo "== [3/4] validate-pr-title · [4/4] pr-verify"
git -C "$ROOT" fetch --quiet origin main || echo "   (origin/main을 받지 못함 — 마지막으로 받은 origin/main 기준)"
BASE_SHA=$(git -C "$ROOT" merge-base origin/main "$HEAD_SHA")
PR_NOTE="열린 PR 없음 — PR 제목·본문 검사 안 함"
PY="uv run --locked python"   # 시스템 python3에 기대지 않는다
pr_field() { printf '%s' "$PR" | $PY -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }
PR=$(cd "$ROOT" && gh pr view --json title,body,state,headRefOid,number 2>/dev/null || true)
if [[ -n "$PR" ]] && [[ "$(pr_field state 2>/dev/null)" == "OPEN" ]]; then
  PR_NUMBER=$(pr_field number)
  PR_HEAD=$(pr_field headRefOid)
  PR_TITLE=$(pr_field title)
  PR_BODY=$(pr_field body)
  export PR_TITLE PR_BODY
  PR_NOTE="PR #$PR_NUMBER 제목·본문 검사함"
  if [[ "$PR_HEAD" != "$HEAD_SHA" ]]; then
    if [[ "$REQUIRE_PR" == "1" ]]; then
      echo "❌ PR #${PR_NUMBER}의 최신 커밋(${PR_HEAD:0:7})이 검사한 커밋(${HEAD_SHA:0:7})과 다르다 — push한 뒤 다시 돌린다"
      exit 1
    fi
    PR_NOTE="$PR_NOTE (PR 최신 커밋 ${PR_HEAD:0:7} ≠ 검사 커밋 — push 전이라면 정상)"
  fi
elif [[ "$REQUIRE_PR" == "1" ]]; then
  echo "❌ LOCAL_CI_REQUIRE_PR=1인데 이 브랜치($BRANCH)의 열린 PR을 찾지 못했다(gh 인증·네트워크 확인)"
  exit 1
else
  echo "   ($PR_NOTE — PR을 연 뒤 다시 돌린다)"
fi
# PR_TITLE이 있으면 pr_checks.py의 check_pr_title이 validate-pr-title과 같은 규칙으로 제목을 검사한다(#55)
BASE_SHA="$BASE_SHA" HEAD_SHA="$HEAD_SHA" $PY scripts/ci/pr_checks.py

if [[ "$REQUIRE_PR" == "1" ]]; then
  # 검사하는 사이 main이 움직였으면 새 변경을 합쳐 다시 돌려야 한다
  git -C "$ROOT" fetch --quiet origin main
  if [[ "$(git -C "$ROOT" rev-parse origin/main)" != "$MAIN_AT_START" ]]; then
    echo "❌ 검사하는 동안 origin/main이 바뀌었다(${MAIN_AT_START:0:7} → $(git -C "$ROOT" rev-parse --short origin/main)) — main을 다시 합치고 돌린다"
    exit 1
  fi
  echo "✅ local CI 통과(엄격 — 병합 근거로 쓸 수 있음) — 커밋 $HEAD_SHA · DB 테스트 $DB_TESTS · $PR_NOTE · origin/main 포함"
else
  echo "✅ local CI 통과(기본 — 병합 근거 아님, 엄격 모드는 LOCAL_CI_REQUIRE_PR=1) — 커밋 $HEAD_SHA · DB 테스트 $DB_TESTS · $PR_NOTE"
fi

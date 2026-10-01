#!/usr/bin/env bash
# check-branch.sh — pre-push 브랜치 검증 (2개 모드)
#
# Usage:
#   bash scripts/check-branch.sh no-main-push   # main 직접 push 차단
#   bash scripts/check-branch.sh name           # 브랜치명 정규식 검증

set -euo pipefail

MODE="${1:-}"
BRANCH=$(git branch --show-current)

case "$MODE" in
  no-main-push)
    if [[ "$BRANCH" == "main" ]]; then
      echo "❌ main 브랜치에 직접 push 금지."
      echo "   새 브랜치를 만드세요: git switch -c <type>/<name>"
      exit 1
    fi
    ;;

  name)
    [[ "$BRANCH" == "main" ]] && exit 0
    PATTERN="^(feat|fix|refactor|docs|research|data|chore|remove)/[a-z0-9][a-z0-9-]*$"
    if ! echo "$BRANCH" | grep -Eq "$PATTERN"; then
      echo "❌ 브랜치명 '$BRANCH'이 규칙을 위반합니다."
      echo "   올바른 형식: feat/hybrid-retriever, fix/chunk-overlap, research/embedding-compare"
      echo "   허용 type: feat | fix | refactor | docs | research | data | chore | remove"
      echo "   브랜치 이름 변경: git branch -m <type>/<올바른-이름>"
      exit 1
    fi
    ;;

  *)
    echo "❌ Usage: $0 {no-main-push|name}"
    exit 2
    ;;
esac

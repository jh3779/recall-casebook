#!/usr/bin/env bash
# check-commit-msg.sh — Conventional Commits 형식 검증
#
# Usage: bash scripts/check-commit-msg.sh <commit-msg-file>
# lefthook commit-msg 훅에서 호출된다.

set -euo pipefail

MSG_FILE="${1:-}"

if [[ -z "$MSG_FILE" || ! -f "$MSG_FILE" ]]; then
  echo "❌ 커밋 메시지 파일을 찾을 수 없습니다: ${MSG_FILE}"
  exit 1
fi

FIRST_LINE=$(head -n1 "$MSG_FILE")

# 빈 메시지는 git이 알아서 중단한다
[[ -z "$FIRST_LINE" ]] && exit 0

# git이 자동 생성하는 merge/revert 커밋은 통과
case "$FIRST_LINE" in
  "Merge "*|"Revert "*) exit 0 ;;
esac

# 한글 subject 허용. 첫 글자 대문자(A-Z) 금지 규칙은 .github/workflows/pr-title-check.yml(subjectPattern), scripts/ci/pr_checks.py(check_pr_title), scripts/check-commit-msg.sh(PATTERN) 세 곳에 있다 — 바꿀 때 함께 고친다(#56). 설명 최소 길이는 다르다: yml·py는 2글자(`[^A-Z].+`), 커밋 훅은 1글자(`[^A-Z].*`)
PATTERN="^(feat|fix|refactor|docs|research|data|chore|remove)(\(.+\))?!?: [^A-Z].*"
if ! echo "$FIRST_LINE" | grep -Eq "$PATTERN"; then
  echo "❌ 커밋 메시지가 Conventional Commits 형식이 아닙니다."
  echo "   첫 줄: $FIRST_LINE"
  echo ""
  echo "   올바른 예:"
  echo "     feat: 하이브리드 검색 리트리버 추가"
  echo "     fix(rag): 청크 중복 제거"
  echo "     data: 벡터 인덱스 v2 재생성"
  echo "   허용 type: feat | fix | refactor | docs | research | data | chore | remove"
  exit 1
fi

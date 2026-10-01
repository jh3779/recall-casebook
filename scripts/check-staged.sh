#!/usr/bin/env bash
# check-staged.sh — pre-commit: 커밋하면 안 되는 파일 차단
#
# Usage: bash scripts/check-staged.sh <file>...
# lefthook pre-commit 훅이 {staged_files}를 넘겨 호출한다.

set -euo pipefail

MAX_KB=1024
FAIL=0

for f in "$@"; do
  [[ -f "$f" ]] || continue

  case "$(basename "$f")" in
    .env.example) ;;
    .env|.env.*)
      echo "❌ 비밀 파일 커밋 금지: $f  (키는 .env에만, .env.example에는 이름만)"
      FAIL=1 ;;
  esac

  if grep -Eq -- "-----BEGIN ([A-Z]+ )?PRIVATE KEY-----" "$f" 2>/dev/null; then
    echo "❌ 개인키로 보이는 내용이 있습니다: $f"
    FAIL=1
  fi

  size_kb=$(( $(wc -c < "$f") / 1024 ))
  if (( size_kb > MAX_KB )); then
    echo "❌ ${MAX_KB}KB 초과 파일: $f (${size_kb}KB) — 데이터·인덱스는 재현 스크립트로 생성합니다"
    FAIL=1
  fi
done

exit $FAIL

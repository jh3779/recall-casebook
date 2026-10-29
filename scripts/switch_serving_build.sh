#!/usr/bin/env bash
# 공개 API(Vercel 프로젝트 lg-cns-rag)가 띄울 서빙 build를 바꾸거나 되돌린다 (docs/배포_Vercel.md 3-1a절, DEC-059).
#
# 사용: bash scripts/switch_serving_build.sh <BUILD>            (확인을 묻고 바꾼다)
#       bash scripts/switch_serving_build.sh <BUILD> --check    (아무것도 바꾸지 않고 사전 점검만)
# 허용 BUILD: 아래 expected 표에 적힌 build뿐이다. 새 build를 쓰려면 먼저 이 표(expected)와 docs/배포_Vercel.md 3-1a 표에 묶음 sha256을 더한다.
# Python이 필요 없다(장애 때 기기마다 다르게 동작하지 않게 curl·sed·grep·vercel만 쓴다).
# 접속 정보는 읽지도 출력하지도 않는다. Vercel CLI 로그인(vercel whoami)이 필요하다.
#
# 실패하면 이렇게 움직인다 — 환경변수와 공개 서버가 어긋난 채 끝나지 않게 한다:
#   - 환경변수 변경 실패          → 배포하지 않고 이전 값으로 되돌린 뒤 멈춘다
#   - 배포 명령 실패             → 이전 값으로 되돌리고 /health를 본다. 이전 build가 아니거나 읽히지 않으면 이전 build를 다시 배포한다 (명령이 실패해도 원격 배포는 올라갔을 수 있다)
#   - 배포 뒤 /health가 안 맞음   → 위와 같다 (이전 값 복구 → 이전 build 다시 배포 → /health 확인)
#   - 이전 값 복구가 실패          → 변수가 없는 채로 재배포하면 서버가 시작하지 못하므로 재배포하지 않고 대시보드 안내만 한다
#   - Ctrl-C·터미널 종료(배포 명령이 끝나기 전) → 환경변수를 이전 값으로 되돌리고(재배포는 안 함) 공개 상태를 다시 보라고 알린다
#     배포 명령이 끝난 뒤의 /health 확인 중 끊기면 환경변수는 새 값 그대로 둔다(서버도 새 build). 복구(recover) 중에는 신호를 무시한다
#     터미널을 닫아 화면 출력이 실패해도 멈추지 않고(echo 재정의) 환경변수 복구를 안내 출력보다 먼저 한다
#   - 작업 폴더가 깨끗한 최신 main이 아님 → vercel deploy --prod 가 작업 폴더 전체를 올리므로 --check도 중단한다
#   - 공개 서버가 이미 그 build   → 숨은 환경변수만 그 값으로 다시 맞춘다 (배포 없음)

set -euo pipefail

# 터미널 창을 닫으면 화면 출력이 실패한다 — 출력 실패가 set -e로 스크립트를 멈춰 환경변수 복구가 중단되지 않게 한다.
echo() { builtin echo "$@" 2>/dev/null || true; }

# macOS 기본 bash 3.2에는 연관 배열이 없어 case로 표를 둔다 (build → 묶음 sha256).
expected() {
  case "$1" in
    f1fe1843ed0f2c66) echo dd0efac013a47dd9cb5b303d4d7958724e9cba21254f4bb9bc6f7f87a190bc1a ;;
    5e32c164b15a544a) echo b466430d989b55e1d623346f70461428b6ec83bfbb0508eff40bbf4d98c25127 ;;
    *) echo "" ;;
  esac
}
API=https://lg-cns-rag.vercel.app
SLEEP=${SWITCH_SLEEP:-10}

BUILD=${1:-}
MODE=${2:-apply}
[ -n "$BUILD" ] && [ -n "$(expected "$BUILD")" ] || { echo "중단: BUILD는 f1fe1843ed0f2c66(생산 기간 이전)·5e32c164b15a544a(생산 기간 포함) 중 하나여야 한다"; exit 1; }
[ "$MODE" = apply ] || [ "$MODE" = "--check" ] || { echo "중단: 두 번째 인수는 --check만 쓸 수 있다"; exit 1; }

unset VIRTUAL_ENV
cd "$(git rev-parse --show-toplevel)"

[ -f .vercel/project.json ] || { echo "중단: .vercel/project.json이 없다 — vercel link --yes --project lg-cns-rag 를 먼저 한다"; exit 1; }
PROJECT=$(sed -n 's/.*"projectName"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' .vercel/project.json | head -1)
[ "$PROJECT" = "lg-cns-rag" ] || { echo "중단: 저장소 루트가 lg-cns-rag 프로젝트에 연결돼 있지 않다 (지금: ${PROJECT:-읽지 못함}) — vercel link --yes --project lg-cns-rag"; exit 1; }

# 로그인·권한을 먼저 확인한다 (/health는 로그인 없이 읽혀서 이 확인이 없으면 --check가 거짓으로 통과한다).
ACCOUNT=$(vercel whoami 2>/dev/null | tail -1) || true
[ -n "$ACCOUNT" ] || { echo "중단: Vercel에 로그인돼 있지 않다 (vercel login)"; exit 1; }
# 파이프로 바로 grep -q에 넘기지 않는다 — pipefail 아래에서 grep이 먼저 닫으면 vercel이 SIGPIPE로 죽어 거짓으로 중단할 수 있다.
ENV_LIST=$(vercel env ls production 2>/dev/null) || true
printf '%s' "$ENV_LIST" | grep -q SERVING_BUILD_ID || { echo "중단: Production 환경변수 목록을 읽지 못했거나 SERVING_BUILD_ID가 없다 (권한·프로젝트 확인)"; exit 1; }
echo "Vercel 계정: $ACCOUNT"

# /health를 "build sha256" 한 줄로 읽는다. 읽지 못하면 빈 문자열.
health() {
  local j b s
  j=$(curl -s -m 60 "$API/health" || true)
  b=$(printf '%s' "$j" | sed -n 's/.*"build_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  s=$(printf '%s' "$j" | sed -n 's/.*"bundle_sha256"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  [ -n "$b" ] && [ -n "$s" ] && echo "$b $s" || echo ""
}

CURRENT=$(health)
[ -n "$CURRENT" ] || { echo "중단: 현재 공개 /health를 읽지 못했다"; exit 1; }
CUR_BUILD=${CURRENT%% *}
echo "현재 공개 API: $CURRENT"
[ -n "$(expected "$CUR_BUILD")" ] || { echo "중단: 현재 build($CUR_BUILD)가 알려진 값이 아니라 실패 시 복구할 값을 정할 수 없다"; exit 1; }
[ "$CURRENT" = "$CUR_BUILD $(expected "$CUR_BUILD")" ] || { echo "중단: 현재 묶음 sha256이 표와 다르다"; exit 1; }

# 환경변수를 지우고 다시 넣는다. 지우기는 값이 없을 때도 실패하므로 무시하고, 넣기가 성공했는지로 판단한다.
set_env() {
  vercel env rm SERVING_BUILD_ID production --yes >/dev/null 2>&1 || true
  printf '%s' "$1" | vercel env add SERVING_BUILD_ID production
}

# 배포하고 /health가 target(build+sha256)과 같아질 때까지 최대 3번 본다.
deploy_and_verify() {
  local target=$1 h
  vercel deploy --prod || return 1
  for _ in 1 2 3; do
    h=$(health)
    echo "/health: ${h:-읽지 못함}"
    [ "$h" = "$target $(expected "$target")" ] && return 0
    sleep "$SLEEP"
  done
  return 1
}

if [ "$CUR_BUILD" = "$BUILD" ]; then
  echo "공개 서버는 이미 $BUILD 입니다. 다만 앞선 실패로 환경변수가 다른 값으로 남았을 수 있어, 환경변수를 $BUILD 로 다시 맞출 수 있습니다(배포는 하지 않습니다)."
  [ "$MODE" = apply ] || { echo "사전 점검 통과 (--check라 바꾸지 않았다)"; exit 0; }
  read -r -p "SERVING_BUILD_ID를 $BUILD 로 다시 맞출까요? [y/N] " a
  [ "$a" = "y" ] || [ "$a" = "Y" ] || { echo "중단했습니다."; exit 0; }
  set_env "$BUILD" || { echo "!! 환경변수 설정에 실패했다 — 대시보드 Settings > Environment Variables에서 SERVING_BUILD_ID=$BUILD 를 직접 넣는다"; exit 1; }
  echo "환경변수를 $BUILD 로 맞췄습니다 (공개 서버는 바뀌지 않음)."
  exit 0
fi

# vercel deploy --prod 는 지금 작업 폴더의 코드 전체를 올린다 — 깨끗한 최신 main이 아니면 데이터 build만 바꾸는 배포가 되지 않는다.
git fetch -q origin main || { echo "중단: git fetch origin main에 실패해 최신 main을 확인할 수 없다"; exit 1; }
[ -z "$(git status --short)" ] || { echo "중단: 작업 폴더에 커밋하지 않은 변경이 있다 — vercel deploy --prod 가 그대로 올라가므로 깨끗한 최신 main에서만 한다"; exit 1; }
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "중단: HEAD가 origin/main과 다르다 — 최신 main(git switch main && git pull)에서만 한다"; exit 1; }

[ "$MODE" = apply ] || { echo "사전 점검 통과 — $CUR_BUILD → $BUILD 로 바꿀 수 있다 (--check라 바꾸지 않았다)"; exit 0; }

read -r -p "SERVING_BUILD_ID를 $CUR_BUILD → $BUILD 로 바꿔 재배포할까요? 공개 서비스가 바뀝니다. [y/N] " a
[ "$a" = "y" ] || [ "$a" = "Y" ] || { echo "중단했습니다."; exit 0; }

restore_env() {
  echo "!! 환경변수를 이전 값 $CUR_BUILD 로 되돌린다"
  set_env "$CUR_BUILD" || {
    echo "!! 이전 값 복구에 실패했다 — 환경변수가 없는 채로 재배포하면 서버가 시작하지 못하므로 재배포하지 않는다. 대시보드 Settings > Environment Variables에서 SERVING_BUILD_ID=$CUR_BUILD 를 직접 넣은 뒤 /health 를 확인하고, 이전 build가 아니면 이 스크립트를 $CUR_BUILD 로 다시 실행한다"
    echo "!! 실패한 배포가 몇 분 뒤에 늦게 완료돼 새 build가 공개될 수 있다 — 환경변수를 고쳐도 진행 중인 배포는 취소되지 않으니 대시보드 Deployments에서 진행 중인 배포가 없어질 때까지 /health 를 계속 다시 본다"
    return 1
  }
}

# 복구에 들어가면 신호를 무시한다 — 복구 도중 끊기면 환경변수와 공개 서버가 어긋나거나 변수가 없는 채 끝날 수 있다(이 구간에서는 trap을 풀어 둔 상태).
enter_recovery() {
  trap '' INT TERM HUP
  echo "!! 복구를 시작한다 — 복구 중에는 Ctrl-C 등 신호를 무시한다 (vercel 이 멈추면 다른 터미널에서 프로세스를 종료하고 대시보드에서 SERVING_BUILD_ID 를 직접 확인한다)"
}

# 새 build로 바꾸다 실패했을 때: 환경변수를 이전 값으로 복구하고, 공개 서버가 이전 build가 아니거나 읽히지 않으면
# 이전 build를 다시 배포해 확인한다. 배포 명령이 실패해도 원격 배포가 이미 올라갔을 수 있어 공개 상태를 단정하지 않는다.
recover() {
  restore_env || return 1
  if [ "$(health)" = "$CUR_BUILD $(expected "$CUR_BUILD")" ]; then
    echo "공개 서버는 이전 build $CUR_BUILD 그대로입니다 (환경변수도 이전 값으로 복구)."
    echo "!! 실패한 배포가 몇 분 뒤에 늦게 완료돼 새 build가 공개될 수 있다 — 대시보드 Deployments에서 진행 중인 배포가 없어질 때까지 /health를 다시 본다 (새 build가 보이면 이 스크립트를 $CUR_BUILD 로 다시 실행한다)"
    return 0
  fi
  echo "!! 공개 서버가 $CUR_BUILD 로 확인되지 않는다 — 이전 build를 다시 배포한다"
  if deploy_and_verify "$CUR_BUILD"; then
    echo "이전 build $CUR_BUILD 로 되돌렸습니다. 원인은 vercel logs 로 본다. 실패한 배포가 늦게 완료되면 새 build가 다시 공개될 수 있으니 대시보드 Deployments에서 진행 중인 배포가 없어질 때까지 /health를 다시 본다."
  else
    echo "!! 되돌린 배포도 $CUR_BUILD 로 확인되지 않았다 — 지금 바로 vercel logs 와 대시보드를 확인한다"
    echo "!! 실패한 배포가 몇 분 뒤에 늦게 완료돼 새 build가 공개될 수 있다 — 대시보드 Deployments에서 진행 중인 배포가 없어질 때까지 /health를 다시 본다"
    return 1
  fi
}

# Ctrl-C·터미널 종료로 끊겨도 환경변수가 새 값(또는 없는 상태)으로 남지 않게 이전 값을 되돌려 넣고, 공개 상태를 다시 보라고 알린다.
# 재배포는 하지 않는다 — 끊은 시점에 원격 배포가 이미 올라갔을 수 있어 공개 상태를 단정할 수 없다.
on_interrupt() {
  trap '' INT TERM HUP
  set +e
  # 터미널을 닫아 출력이 막혀도 복구가 먼저 되도록 안내 출력보다 앞에서 환경변수를 되돌린다(출력은 숨긴다).
  if set_env "$CUR_BUILD" >/dev/null 2>&1; then
    echo
    echo "!! 중단됐다 — 환경변수를 이전 값 $CUR_BUILD 로 되돌렸다 (재배포는 하지 않았다)"
  else
    echo
    echo "!! 중단됐고 이전 값 복구에도 실패했다 — 대시보드 Settings > Environment Variables에서 SERVING_BUILD_ID=$CUR_BUILD 를 직접 넣는다"
  fi
  echo "!! 원격 배포는 계속 진행됐을 수 있다 — /health 의 build_id 를 확인한다. 환경변수와 공개 서버가 다른 build면 원하는 build 인수로 이 스크립트를 다시 실행한다(공개 서버가 이미 그 build면 환경변수만 맞춘다): 되돌리려면 $CUR_BUILD, 새 build를 원하면 $BUILD"
  echo "!! 복구 중에는 신호를 무시한다 — vercel 이 멈추면 다른 터미널에서 프로세스를 종료하고 대시보드 Settings > Environment Variables 에서 SERVING_BUILD_ID 를 직접 확인한다"
  exit 130
}
trap on_interrupt INT TERM HUP

if ! set_env "$BUILD"; then
  echo "!! 환경변수를 $BUILD 로 바꾸지 못했다 — 배포하지 않는다"
  restore_env || true
  exit 1
fi

if ! vercel deploy --prod; then
  echo "!! 배포 명령이 실패했다 — 원격에서 배포가 올라갔는지 알 수 없어 공개 /health로 확인한다"
  enter_recovery
  recover || true
  exit 1
fi

# 배포 명령이 끝나면 새 build가 이미 올라간 것이다 — 이후 구간에서 끊겨도 환경변수를 이전 값으로 되돌리지 않는다(되돌리면 서버=새 build, 환경변수=이전 값으로 어긋난다).
trap - INT TERM HUP

for _ in 1 2 3; do
  H=$(health)
  echo "/health: ${H:-읽지 못함}"
  if [ "$H" = "$BUILD $(expected "$BUILD")" ]; then echo "바꿨습니다: $BUILD"; exit 0; fi
  sleep "$SLEEP"
done

echo "!! 배포 뒤 /health가 $BUILD 로 확인되지 않았다 — $CUR_BUILD 로 되돌린다"
enter_recovery
recover || true
exit 1

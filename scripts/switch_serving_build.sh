#!/usr/bin/env bash
# 공개 API(Vercel 프로젝트 lg-cns-rag)가 띄울 서빙 build를 바꾸거나 되돌린다 (docs/배포_Vercel.md 3-1a절, DEC-059).
#
# 사용: bash scripts/switch_serving_build.sh <BUILD>            (확인을 묻고 바꾼다)
#       bash scripts/switch_serving_build.sh <BUILD> --check    (아무것도 바꾸지 않고 사전 점검만)
# 허용 BUILD: 아래 expected 표에 적힌 build뿐이다. 새 build를 쓰려면 먼저 이 표(expected)와 docs/배포_Vercel.md 3-1a 표에 묶음 sha256을 더한다.
# 접속 정보는 읽지도 출력하지도 않는다. Vercel CLI 로그인(vercel whoami)이 필요하다.

set -euo pipefail

# macOS 기본 bash 3.2에는 연관 배열이 없어 case로 표를 둔다 (build → 묶음 sha256).
expected() {
  case "$1" in
    f1fe1843ed0f2c66) echo dd0efac013a47dd9cb5b303d4d7958724e9cba21254f4bb9bc6f7f87a190bc1a ;;
    5e32c164b15a544a) echo b466430d989b55e1d623346f70461428b6ec83bfbb0508eff40bbf4d98c25127 ;;
    *) echo "" ;;
  esac
}
API=https://lg-cns-rag.vercel.app

BUILD=${1:-}
MODE=${2:-apply}
[ -n "$BUILD" ] && [ -n "$(expected "$BUILD")" ] || { echo "중단: BUILD는 f1fe1843ed0f2c66(생산 기간 이전)·5e32c164b15a544a(생산 기간 포함) 중 하나여야 한다"; exit 1; }
[ "$MODE" = apply ] || [ "$MODE" = "--check" ] || { echo "중단: 두 번째 인수는 --check만 쓸 수 있다"; exit 1; }

unset VIRTUAL_ENV
cd "$(git rev-parse --show-toplevel)"

[ -f .vercel/project.json ] || { echo "중단: .vercel/project.json이 없다 — vercel link --yes --project lg-cns-rag 를 먼저 한다"; exit 1; }
[ "$(python3 -c "import json;print(json.load(open('.vercel/project.json'))['projectName'])")" = "lg-cns-rag" ] \
  || { echo "중단: 저장소 루트가 lg-cns-rag 프로젝트에 연결돼 있지 않다 (vercel link --yes --project lg-cns-rag)"; exit 1; }
echo "Vercel 계정: $(vercel whoami 2>/dev/null | tail -1)"

health() { curl -s -m 60 "$API/health" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["build_id"],d["bundle_sha256"])'; }
CURRENT=$(health) || { echo "중단: 현재 공개 /health를 읽지 못했다"; exit 1; }
CUR_BUILD=${CURRENT%% *}
echo "현재 공개 API: $CURRENT"
[ -n "$(expected "$CUR_BUILD")" ] || { echo "중단: 현재 build($CUR_BUILD)가 알려진 값이 아니라 실패 시 복구할 값을 정할 수 없다"; exit 1; }
[ "$CURRENT" = "$CUR_BUILD $(expected "$CUR_BUILD")" ] || { echo "중단: 현재 묶음 sha256이 표와 다르다"; exit 1; }
[ "$CUR_BUILD" != "$BUILD" ] || { echo "이미 $BUILD 입니다. 바꿀 것이 없습니다."; exit 0; }
[ "$MODE" = apply ] || { echo "사전 점검 통과 — $CUR_BUILD → $BUILD 로 바꿀 수 있다 (--check라 바꾸지 않았다)"; exit 0; }

read -r -p "SERVING_BUILD_ID를 $CUR_BUILD → $BUILD 로 바꿔 재배포할까요? 공개 서비스가 바뀝니다. [y/N] " a
[ "$a" = "y" ] || [ "$a" = "Y" ] || { echo "중단했습니다."; exit 0; }

set_env() { vercel env rm SERVING_BUILD_ID production --yes && printf '%s' "$1" | vercel env add SERVING_BUILD_ID production; }

if ! set_env "$BUILD"; then
  echo "!! 환경변수 변경에 실패했다 — 이전 값 $CUR_BUILD 로 복구를 시도한다 (배포는 하지 않는다)"
  set_env "$CUR_BUILD" || echo "!! 복구도 실패했다. 대시보드 Settings > Environment Variables에서 SERVING_BUILD_ID=$CUR_BUILD 를 직접 넣고 재배포한다"
  exit 1
fi

vercel deploy --prod
for i in 1 2 3; do
  H=$(health || true)
  echo "/health: $H"
  [ "$H" = "$BUILD $(expected "$BUILD")" ] && { echo "바꿨습니다: $BUILD"; exit 0; }
  sleep 10
done
echo "!! $BUILD 로 확인되지 않았다 — vercel logs 로 원인을 보고, 급하면 'bash scripts/switch_serving_build.sh $CUR_BUILD' 로 되돌린다"
exit 1

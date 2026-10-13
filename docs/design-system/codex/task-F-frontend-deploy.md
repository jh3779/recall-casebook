# 작업 F — 화면 Vercel 배포 준비

> 먼저 [README.md](README.md)(공통 규칙)를 읽는다. 시작 조건: 작업 E가 main에 병합됨. `git switch main && git pull && git switch -c chore/frontend-vercel-deploy`.
> **Codex가 하는 것**: 배포 설정 파일·문서·런북(사람이 그대로 따라 할 명령 목록). **사람이 하는 것**: Vercel 로그인·프로젝트 생성·환경변수·실제 배포·API 재배포 — Codex 환경에는 Vercel 계정과 3D 모델 파일이 없다.

## 배경

- API는 Vercel 프로젝트 `lg-cns-rag`(Production `https://lg-cns-rag.vercel.app`, 함수 지역 `syd1`)로 이미 배포돼 있다(`docs/배포_Vercel.md` 3-1절, DEC-051). 저장소 루트의 `.vercelignore`는 **API 전용 허용 목록**이라 `frontend/`를 올리지 않는다.
- 화면은 **별도 Vercel 프로젝트**(예: `lg-cns-rag-web`)로, **CLI 배포만** 한다(Git 연동 배포는 gitignore된 `public/models/*.glb`가 빠져 3D가 안 뜬다).
- 공개 API의 CORS 허용 주소(`ALLOWED_ORIGINS`)는 지금 비어 있어 기본값 `http://localhost:5173`만 허용된다. 배포 화면 주소를 넣고 **API를 다시 배포해야** 적용된다(서버가 시작할 때 한 번 읽음).

## 1. 파일

| 파일 | 내용 |
|---|---|
| `frontend/.vercelignore` (새) | **허용 목록**: `/*` 다음 `!index.html` `!package.json` `!package-lock.json` `!.nvmrc` `!tsconfig*.json` `!vite.config.ts` `!src` `!public`. `public/models/*.glb`는 업로드에 들어가고 `node_modules`·`dist`·`.env*`는 빠진다 |
| `frontend/vercel.json` (새) | `{"$schema": "https://openapi.vercel.sh/vercel.json", "framework": "vite", "buildCommand": "npm run build", "outputDirectory": "dist", "installCommand": "npm ci"}` — 공식 문서(context7 또는 vercel.com/docs)로 키 이름을 확인하고 쓴다 |
| `frontend/package.json` | `"engines": {"node": "24.x"}` 추가(Vercel은 `.nvmrc`를 읽지 않는다). 의존성은 바꾸지 않으므로 lock은 그대로여야 한다 — `npm install`이 lock을 바꾸면 그 변경만 함께 커밋 |
| `frontend/src/vercelignore.test.ts` (새, 선택) | `.vercelignore` 첫 줄이 `/*`이고 허용 목록이 위와 같은지, `.env`·`dist`·`node_modules`가 허용되지 않는지 (API 쪽 `tests/test_vercel_entry.py`와 같은 취지) |

## 2. 런북 — `docs/배포_Vercel.md` 2절을 고쳐 쓴다 (사람이 그대로 따라 할 명령)

다음 순서를 명령까지 적는다:

1. **3D 모델 준비**: #105 뒤 쇼룸 차종은 쏘나타·쏘렌토(DEC-054)다. `frontend/README.md` "3D 모델 파일" 절대로 `public/models/sonata.glb`·`sorento.glb`를 두고, `shasum -a 256 frontend/public/models/{sonata,sorento}.glb`가 `frontend/public/data/vehicle-sources.json`의 값(쏘나타 `e3a9bf1e821ba553e23c51da3d7ac668a9a0e5678a9ba304fd329b4ae0355470` 116,543,736바이트 · 쏘렌토 `fd39a70b9e34b1ce4a153ed890b5a2acfc10092bd84559e03c74ef59962c6470` 18,780,960바이트)과 같은지 확인한다. 화면이 실제로 부르는 경로는 `frontend/src/config.ts`의 `glb`(`models/sonata.glb`·`models/sorento.glb`)다 — 다르면 그 값을 따른다. 옛 트럭 모델(`d608c0bc…`·`f8532a1d…`)은 작업 D의 보관 기록이며 배포하지 않는다. **쏘나타가 약 111MiB라 Vercel 정적 파일 크기 한도를 공식 문서로 먼저 확인**하고, 넘으면 멈추고 사람에게 묻는다.
2. **프로젝트 연결**(처음 한 번): `cd frontend && vercel project add lg-cns-rag-web && vercel link --yes --project lg-cns-rag-web`. `vercel link`가 `.gitignore`에 `.env*`를 덧붙이면 그 줄을 지운다(루트 `.gitignore`의 `.env.example` 추적을 깨지 않게 — API 배포 때 실제로 있었던 일, DEC-051).
3. **환경변수**: `printf 'https://lg-cns-rag.vercel.app' | vercel env add VITE_API_BASE production` (빌드 때 화면에 들어가는 공개값 — 비밀값 금지).
4. **미리보기 배포로 실측**: `vercel deploy` → 업로드 크기(약 135MB, 대부분 `.glb`)·빌드 로그 확인. 화면이 부르는 **두 모델 모두** 받아 지문을 대조한다: `vercel curl /models/sonata.glb --deployment <주소> -- -s -o /tmp/sonata.glb && shasum -a 256 /tmp/sonata.glb`, 같은 방법으로 `/models/sorento.glb`. 둘 다 1단계 값과 같아야 통과다. **하위 폴더의 `.vercelignore`가 기대대로 읽혔는지**(업로드 목록에 `node_modules` 없음) 확인 — 안 되면 대안 `vercel build --prod && vercel deploy --prebuilt --prod`(로컬 빌드 결과 `dist`만 올림)로 바꾸고 문서를 고친다.
5. **Production**: `vercel deploy --prod` → 주소 기록(예: `https://lg-cns-rag-web.vercel.app`).
6. **API CORS 열기**(저장소 루트, API 프로젝트): `printf 'https://lg-cns-rag-web.vercel.app,http://localhost:5173' | vercel env add ALLOWED_ORIGINS production` → `vercel deploy --prod`(같은 `SERVING_BUILD_ID`) → 확인:
   ```bash
   curl -si -X OPTIONS https://lg-cns-rag.vercel.app/search \
     -H "Origin: https://lg-cns-rag-web.vercel.app" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: content-type" | grep -i access-control-allow-origin
   curl -s https://lg-cns-rag.vercel.app/health      # build_id f1fe1843ed0f2c66 그대로인지
   ```
   localhost를 빼면 로컬 개발이 막힌다. 미리보기 배포 주소는 허용되지 않으니 그 주소의 검색 실패는 정상(문서에 명시).
7. **확인**: 공개 화면에서 예시 질문 한 건이 끝까지 되는지, 쇼룸이 뜨는지, 모바일 390px, 출처 꼬리의 build_id가 `/health`와 같은지.

## 3. 문서·기록

- `docs/배포_Vercel.md`: 2절(화면) 위 런북, 3-1절에 `ALLOWED_ORIGINS` 값과 API 재배포 기록 자리(실측은 사람이 채움 — 빈칸에 "배포 뒤 기입").
- `frontend/README.md`: "배포 화면의 `/models/*.glb`에서도 받을 수 있다" — 3D 모델 받는 길이 하나 더 생긴다(리뷰 지적 "새로 받은 사람은 3D 실행 불가" 해소).
- `.agent/DECISIONS.md` **DEC-055**(DEC-054는 #105 쇼룸 차종 결정이 썼다 — 쓰기 직전 main의 마지막 번호를 다시 확인): 화면은 별도 Vercel 프로젝트·CLI 전용 배포(이유: `.glb` gitignore), `ALLOWED_ORIGINS`에 화면 주소 + localhost. 공개 화면이 생기면 인증·호출 상한(#63)이 더 급해진다는 점을 영향에 적는다.
- `.agent/HANDOFF.md`: Next Action을 "사람이 런북 실행 → 실측 기입 → #63"으로. #93(Vercel 프로젝트 구성 명시)을 이 PR로 닫을 수 있으면 `Closes #93`, 남으면 `Refs #93`.

## 4. 검증

```bash
cd frontend && npm ci && npm run lint && npm run build && npm test
cd .. && uv run ruff check . && uv run ruff format --check . && uv run pytest
```

`npm run build` 결과 `dist/`에 `models/`가 들어 있는지(파일이 있을 때) 또는 없을 때도 빌드가 되는지.

## 5. PR

제목 예: `chore: 화면 Vercel 배포 설정과 런북`. 본문에 "실제 배포·CORS 변경·API 재배포는 사람이 런북대로 한다"를 분명히 적는다. 관련 이슈 `Refs #93 · Refs #63`. 병합하지 않는다.

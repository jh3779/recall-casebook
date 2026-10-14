# 작업 F — 화면 Vercel 배포 준비

> 먼저 [README.md](README.md)(공통 규칙)를 읽는다. 시작 조건: 작업 E(#105)와 **#63(호출 상한·CORS)**이 main에 병합됨. `git switch main && git pull && git switch -c chore/frontend-vercel-deploy`.
> **Codex가 하는 것**: 배포 설정 파일·문서·런북(사람이 그대로 따라 할 명령 목록). **사람이 하는 것**: Vercel 로그인·프로젝트 생성·환경변수·실제 배포·API 재배포 — Codex 환경에는 Vercel 계정과 3D 모델 파일이 없다.


> **실행 완료(2026-10-14, PR #119, DEC-058)** — 아래 1·2절은 **작업 전 계획**이다. 지금 따라 할 절차는 [`docs/배포_Vercel.md`](../../배포_Vercel.md) 2절 런북이다. 실행하며 계획과 달라진 것:
> - `.vercelignore`는 `!public` 뒤 `public/models/*`를 다시 막고 `sonata.glb`·`sorento.glb`만 연다(보관 모델 제외, #108) (아래 1절 표에 반영).
> - 원본 쏘나타(116,543,736바이트, `e3a9bf1e…`)는 Vercel CLI 업로드 100MB 한도에 걸려(업로드 129.8MB → 실패, 예상 135MB) 쓰이지 않는 텍스처 좌표만 지운 배포본(44,211,620바이트, `6e00b860…`)을 쓴다. 그래서 지문 대조 기준은 배포본이고 업로드는 약 61MiB다 (아래 2절 1·4단계에 반영).
> - 배포본을 만드는 `@gltf-transform/core`를 개발 의존성으로 더해 lock이 바뀌었다 (아래 1절 표에 반영).
> - 새 프로젝트의 첫 배포는 미리보기가 아니라 Production에 붙었다. 429 화면 처리(DEC-057 ⑤)도 이 작업에서 했다.
## 배경

- API는 Vercel 프로젝트 `lg-cns-rag`(Production `https://lg-cns-rag.vercel.app`, 함수 지역 `syd1`)로 이미 배포돼 있다(`docs/배포_Vercel.md` 3-1절, DEC-051). 저장소 루트의 `.vercelignore`는 **API 전용 허용 목록**이라 `frontend/`를 올리지 않는다.
- #63은 비밀값 없는 보호(IP별 호출 상한·허용 주소 CORS)로 정했다(사용자 결정 2026-10-13) — 화면은 키 없이 `{"question"}`만 보내는 지금 요청 계약 그대로다. 화면에 키·토큰을 넣지 않는다. #63이 `ALLOWED_ORIGINS` 설정 방법을 바꿨다면 6단계는 그 방법을 따른다.
- 화면은 **별도 Vercel 프로젝트**(예: `lg-cns-rag-web`)로, **CLI 배포만** 한다(Git 연동 배포는 gitignore된 `public/models/*.glb`가 빠져 3D가 안 뜬다).
- 공개 API의 CORS 허용 주소(`ALLOWED_ORIGINS`)는 작업 전에는 비어 있어 기본값 `http://localhost:5173`만 허용됐다. 2026-10-14 화면 주소와 localhost를 넣고 API를 다시 배포했다(DEC-058, `docs/배포_Vercel.md` 2절 실측 기록) — 환경변수는 서버가 시작할 때 한 번 읽으므로 바꾸면 재배포해야 한다.

## 1. 파일 *(작업 전 계획 — 실행 결과는 위 머리말)*

| 파일 | 내용 |
|---|---|
| `frontend/.vercelignore` (새) | **허용 목록**: `/*` 다음 `!index.html` `!package.json` `!package-lock.json` `!.nvmrc` `!tsconfig*.json` `!vite.config.ts` `!src` `!public`. (실행: `public/models/*`를 다시 막고 `sonata.glb`·`sorento.glb`만 연다 — #108) `node_modules`·`dist`·`.env*`는 빠진다 |
| `frontend/vercel.json` (새) | `{"$schema": "https://openapi.vercel.sh/vercel.json", "framework": "vite", "buildCommand": "npm run build", "outputDirectory": "dist", "installCommand": "npm ci"}` — 공식 문서(context7 또는 vercel.com/docs)로 키 이름을 확인하고 쓴다 |
| `frontend/package.json` | `"engines": {"node": "24.x"}` 추가(Vercel Node.js 버전 문서: `engines.node`가 프로젝트 설정을 덮어쓴다 — `.nvmrc`는 그 문서에 언급이 없다). (실행: 쏘나타 배포본을 만드는 `@gltf-transform/core`를 개발 의존성으로 더해 lock도 바뀌었다 — DEC-058) — `npm install`이 lock을 바꾸면 그 변경만 함께 커밋 |
| `frontend/src/vercelignore.test.ts` (새, 선택) | `.vercelignore` 첫 줄이 `/*`이고 허용 목록이 위와 같은지, `.env`·`dist`·`node_modules`가 허용되지 않는지 (API 쪽 `tests/test_vercel_entry.py`와 같은 취지) |

## 2. 런북 — `docs/배포_Vercel.md` 2절을 고쳐 쓴다 *(작업 전 계획 — 지금 따라 할 것은 그 2절)*

다음 순서를 명령까지 적는다:

1. **3D 모델 준비** *(실행됨 — 원본 쏘나타는 업로드 한도에 걸려 배포본을 쓴다, DEC-058)*: 절차·지문은 [`docs/배포_Vercel.md`](../../배포_Vercel.md) 2절 1단계를 따른다 — `node scripts/strip-unused-texcoords.mjs <원본> public/models/sonata.glb`로 만든 쏘나타 배포본 `6e00b8603a84e95fac76c1c00f58157fdd21f0044b35f007aea0aecb53499345`(44,211,620바이트) · 쏘렌토 `fd39a70b9e34b1ce4a153ed890b5a2acfc10092bd84559e03c74ef59962c6470`(18,780,960바이트)가 `frontend/public/data/vehicle-sources.json`과 같아야 한다(원본 쏘나타 지문은 그 파일의 `derivedFrom.from`). 화면이 부르는 경로는 `frontend/src/config.ts`의 `glb`다. 옛 트럭·코나 모델은 배포하지 않는다.
2. **프로젝트 연결**(처음 한 번): `cd frontend && vercel project add lg-cns-rag-web && vercel link --yes --project lg-cns-rag-web`. `vercel link`가 `.gitignore`에 `.env*`를 덧붙이면 그 줄을 지운다(루트 `.gitignore`의 `.env.example` 추적을 깨지 않게 — API 배포 때 실제로 있었던 일, DEC-051).
3. **환경변수**: `printf 'https://lg-cns-rag.vercel.app' | vercel env add VITE_API_BASE production` (빌드 때 화면에 들어가는 공개값 — 비밀값 금지).
4. **미리보기 배포로 실측**: `vercel deploy` → 업로드 크기(실행: 원본 쏘나타가 든 업로드 129.8MB(예상 135MB)는 100MB 한도로 실패, 배포본으로 약 61MiB)·빌드 로그 확인. 화면이 부르는 **두 모델 모두** 받아 지문을 대조한다: `vercel curl /models/sonata.glb --deployment <주소> -- -s -o /tmp/sonata.glb && shasum -a 256 /tmp/sonata.glb`, 같은 방법으로 `/models/sorento.glb`. 둘 다 1단계 값과 같아야 통과다. **하위 폴더의 `.vercelignore`가 기대대로 읽혔는지**(업로드 목록에 `node_modules` 없음) 확인 — 안 되면 대안 `vercel build --prod && vercel deploy --prebuilt --prod`(로컬 빌드 결과 `dist`만 올림)로 바꾸고 문서를 고친다.
5. **Production**: `vercel deploy --prod` → 실제 Production 주소를 기록한다(아래에서 `<화면 주소>` — 예: `https://lg-cns-rag-web.vercel.app`이지만 Vercel이 준 값을 쓴다).
6. **API CORS 열기**(저장소 루트, API 프로젝트) — 2단계에서 `frontend/`로 들어왔으므로 **먼저 루트로 나와 API 프로젝트에 연결**한다: `cd .. && vercel link --yes --project lg-cns-rag && cat .vercel/project.json`(`projectName`이 `lg-cns-rag`인지 확인 — `lg-cns-rag-web`이면 멈춘다). 그다음 `printf '<화면 주소>,http://localhost:5173' | vercel env add ALLOWED_ORIGINS production` → `vercel deploy --prod`(같은 `SERVING_BUILD_ID`) → 확인:
   ```bash
   curl -si -X OPTIONS https://lg-cns-rag.vercel.app/search \
     -H "Origin: <화면 주소>" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: content-type" | grep -i access-control-allow-origin
   curl -s https://lg-cns-rag.vercel.app/health      # build_id f1fe1843ed0f2c66 그대로인지
   ```
   localhost를 빼면 로컬 개발이 막힌다. 미리보기 배포 주소는 허용되지 않으니 그 주소의 검색 실패는 정상(문서에 명시).
7. **확인**: 공개 화면에서 예시 질문 한 건이 끝까지 되는지, 쇼룸이 뜨는지, 모바일 390px, 출처 꼬리의 build_id가 `/health`와 같은지.

## 3. 문서·기록

- `docs/배포_Vercel.md`: 2절(화면) 위 런북, 3-1절에 `ALLOWED_ORIGINS` 값과 API 재배포 기록 자리(실측은 사람이 채움 — 빈칸에 "배포 뒤 기입").
- `frontend/README.md`: "배포 화면의 `/models/*.glb`에서도 받을 수 있다" — 3D 모델 받는 길이 하나 더 생긴다(리뷰 지적 "새로 받은 사람은 3D 실행 불가" 해소).
- `.agent/DECISIONS.md` **다음 빈 번호(2026-10-13 기준 DEC-058)**(DEC-054는 #105 쇼룸 차종, DEC-055는 D 파트 복귀, DEC-056은 LLM 사람 평가 제외, DEC-057은 #63 호출 상한 결정이 썼다 — 쓰기 직전 main의 마지막 번호를 다시 확인): 화면은 별도 Vercel 프로젝트·CLI 전용 배포(이유: `.glb` gitignore), `ALLOWED_ORIGINS`에 화면 주소 + localhost. #63(호출 상한·CORS)이 먼저 병합돼 있다는 전제와, 공개 화면의 호출도 #63의 상한을 받는다는 점을 영향에 적는다.
- `.agent/HANDOFF.md`: Next Action을 "사람이 런북 실행 → 실측 기입"으로(#63은 이 작업 전에 끝나 있다). #93(Vercel 프로젝트 구성 명시)을 이 PR로 닫을 수 있으면 `Closes #93`, 남으면 `Refs #93`.

## 4. 검증

```bash
cd frontend && npm ci && npm run lint && npm run build && npm test
cd .. && uv run ruff check . && uv run ruff format --check . && uv run pytest
```

`npm run build` 결과 `dist/`에 `models/`가 들어 있는지(파일이 있을 때) 또는 없을 때도 빌드가 되는지.

## 5. PR

제목 예: `chore: 화면 Vercel 배포 설정과 런북`. 본문에 "실제 배포·CORS 변경·API 재배포는 사람이 런북대로 한다"를 분명히 적는다. 관련 이슈 `Refs #93 · Refs #63`. 병합하지 않는다.

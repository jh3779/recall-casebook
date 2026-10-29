# Vercel 배포 안내 (DEC-048)

> 2026-10-12 기준(2026-10-14 갱신). 공개 화면 `https://lg-cns-rag-web.vercel.app`(2절)·공개 API `https://lg-cns-rag.vercel.app`(3-1절). **발표 시연은 공개 주소로 한다**(DEC-057 ④가 DEC-048 ①을 대체 — 시연 날 절차는 3-2절). 1절의 로컬 포트는 공개 주소가 막혔을 때의 대체 수단이다. 외부 배포는 **일단 Vercel**로 한다. 화면을 먼저 올리고(2절), API는 서빙 묶음(Supabase Storage)으로 발표 전에 옮긴다(3절). API는 **Hobby** 플랜 프로젝트 `lg-cns-rag`로 배포했다(3-1절) — Hobby는 비상업·개인 용도이고 팀 협업 기능은 Pro다.

## 1. 시연 — 로컬 포트 (대체 수단)

> 2026-10-13 DEC-057 ④로 시연 기본은 공개 주소다(3-2절). 이 절은 공개 주소·Vercel이 막혔을 때 쓰는 대체 수단이다.

터미널 두 개로 띄운다(`uvicorn`은 끝날 때까지 터미널을 잡고 있다).

```bash
# 터미널 1 — API 서버 (저장소 루트). 조회 전용 계정이 생기기 전에는 관리자 연결을 명시적으로 허용한다
ALLOW_ADMIN_DB_FOR_SERVER=1 uv run --env-file .env uvicorn server.api:app --port 8000
# 터미널 2 — 화면 (frontend/, PR #60 병합 뒤). 먼저 public/models/에 .glb 두 개를 넣는다(2절)
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

관리자 연결(`DATABASE_URL`, RLS 우회·쓰기 가능)은 적재를 맡은 사람의 컴퓨터에서만 쓴다 — 다른 사람의 노트북으로 시연하면 시연 전에 조회 전용 계정 `rag_reader`를 만들어 `.env.server`(`SERVER_DATABASE_URL`만)로 띄운다(`server/README.md` 3단계).

시연 전 점검: `curl localhost:8000/health`가 `build_id`를 돌려주는지, `/docs`에서 `POST /search` 한 건이 원인 출처(리콜 번호·PDF)와 함께 나오는지, 화면이 데모 스냅샷인지 API 연결 화면인지(아래 첫 항목).

- 화면의 검색 탭은 API를 부른다(#105, DEC-053). 3D 쇼룸 탭은 정적 데모 스냅샷(쏘나타·쏘렌토 26건)이라 검색 결과가 아니다.
- 서버가 시작할 때 읽는 로컬 파일: `data/processed/defect/`의 `build.json`·`recalls.jsonl`·`eval.jsonl`·`causes.jsonl`·`causes.manifest.json`, `data/raw/nhtsa/`의 `manifest.json`·`FLAT_INV.zip`. **드라이브의 `data.zip`·`defect_data_2026-10-08` 사본으로는 서버가 뜨지 않는다**(`docs/guides/환경셋팅.md` 4절 주의) — 서버용 묶음 `defect_data_2026-10-12_dec047`(드라이브 `RAG_main/`에 같은 이름·크기의 zip이 있으나 sha256 `4afde25c…` 일치는 아직 확인하지 못했다 — 내려받아 대조한 뒤 쓰고, 위치와 해시는 `docs/guides/환경셋팅.md` 4절에 적는다)을 쓴다.
- 시작할 때 **Supabase 접속(인터넷)**이 필요하고(DB 명세·벡터 대조), 임베딩 모델 캐시가 없으면 모델(약 67MB)도 내려받는다 — **발표 전에 시연 장소 네트워크에서 한 번 띄워 둔다.**
- CORS는 기본으로 `http://localhost:5173`만 허용한다(환경변수 `ALLOWED_ORIGINS`로 바꿈, DEC-050).

## 2. 화면 배포 — Vercel (작업 F, DEC-058)

**지금 공개 화면: `https://lg-cns-rag-web.vercel.app`** (Vercel 프로젝트 `lg-cns-rag-web`, Hobby, 2026-10-14 첫 배포). API(`lg-cns-rag`)와 **별도 프로젝트**이고 **CLI 배포만** 한다 — Git 연동 배포에는 gitignore된 `public/models/*.glb`가 들어가지 않아 3D가 뜨지 않는다.

| 파일 | 하는 일 |
|---|---|
| `frontend/vercel.json` | `framework: vite`, `installCommand: npm ci`, `buildCommand: npm run build`, `outputDirectory: dist` |
| `frontend/.vercelignore` | **허용 목록**(`/*` 뒤 `!…`) — `index.html`·`package*.json`·`.nvmrc`·`tsconfig*.json`·`vite.config.ts`·`vercel.json`·`src`·`public`, 모델은 화면이 부르는 `sonata.glb`·`sorento.glb`만(보관 트럭·코나 제외, #108). `node_modules`·`dist`·`.env*`는 올라가지 않는다. 시험 `frontend/src/vercelignore.test.ts` |
| `frontend/package.json` `engines.node` | `^24.15.0` — `engines.node`가 프로젝트 설정을 덮어쓴다(Vercel Node.js 버전 문서 — `.nvmrc`는 그 문서에 언급이 없어 쓰지 않는다). 문서상 24 대의 semver 범위는 최신 24.x로 배포된다. 하한 24.15는 시험용 `jsdom` 30의 요구다(2026-10-22, 전에는 `24.x`) |

**크기 한도 — 쏘나타는 줄여서 올린다**: Vercel 한도 문서는 Hobby CLI 배포의 **업로드 소스 합계 100MB**로 적는다(문서의 MB가 어느 단위인지는 확인하지 못했다. 다만 설치된 Vercel CLI는 실패 문구의 한도를 `bytes@3.0.0`(1024 단위)로 표시하므로 CLI는 이 한도를 100MiB(104,857,600바이트)로 읽는다 — 이슈 #123. 아래 CLI 표시 크기도 MiB 값이다)(vercel.com/docs/limits "Static file uploads"). 실패 문구 `File size limit exceeded (100 MB)`(문구의 `100`과 `MB` 사이 공백 유무는 실제 출력으로 확인하지 않았다)로는 파일 하나 기준인지 합계 기준인지 가르지 못했다(2026-10-14 실측: 원본 쏘나타 116,543,736바이트가 든 업로드 129.8MiB(CLI 표시) → 실패). 어느 쪽이든 원본 쏘나타는 혼자 100MB를 넘는다. 지금 올리는 소스 합계는 약 61MiB(쏘나타 배포본 42.2MiB + 쏘렌토 17.9MiB + 코드)라 합계 기준이면 여유가 약 39MiB뿐이다(100MiB − 61MiB) — 모델·데이터를 허용 목록에 더하기 전에 합계를 잰다. 원본 쏘나타에는 재질이 쓰지 않는 텍스처 좌표(TEXCOORD) 속성이 정점마다 여러 벌 붙어 있어, 그것만 지운 배포본(44,211,620바이트)을 쓴다 — 스크립트는 출력을 다시 읽어 남은 정점 속성·인덱스 바이트와 재질 값·텍스처(이미지 지문·texCoord·샘플러)·재질·노드·메시 이름 목록을 원본과 대조하고, 출력 크기·SHA-256·지운 속성 수가 기록값과 같을 때만 쓴다(노드 변환은 `matrix`가 TRS로 다시 쓰여 float32 오차만큼 다를 수 있고 비교하지 않는다. 재질 확장이 있는 모델은 거부 — 이 모델 전용). 원본·배포본 지문은 `frontend/public/data/vehicle-sources.json`(`derivedFrom`)에 있다.

**런북 (사람이 그대로 따라 한다, `frontend/`에서)**

1. **3D 모델 준비** — 먼저 `npm ci`(스크립트가 개발 의존성 `@gltf-transform/core`를 쓴다). `frontend/README.md` "3D 모델 파일" 절대로 원본을 받아 쏘나타는 줄여서 둔다(원본은 116,543,736바이트 파일 — 내려받은 파일이 여럿이면 바이트 수로 고른다):
   ```bash
   SONATA_GLB="$HOME/Downloads/hyundai_sonata_2014 (1).glb"   # 받은 원본 쏘나타 경로로 바꾼다(116,543,736바이트 파일)
   SORENTO_GLB="$HOME/Downloads/kia_sorento.glb"               # 받은 쏘렌토 경로로 바꾼다
   node scripts/strip-unused-texcoords.mjs "$SONATA_GLB" public/models/sonata.glb   # 원본 지문이나 출력 지문(6e00b860…)이 기록값과 다르면 쓰지 않고 멈춘다
   cp "$SORENTO_GLB" public/models/sorento.glb
   shasum -a 256 public/models/sonata.glb public/models/sorento.glb
   ```
   쏘나타 `6e00b8603a84e95fac76c1c00f58157fdd21f0044b35f007aea0aecb53499345`(44,211,620바이트) · 쏘렌토 `fd39a70b9e34b1ce4a153ed890b5a2acfc10092bd84559e03c74ef59962c6470`(18,780,960바이트)여야 한다(`public/data/vehicle-sources.json`). 다른 `.glb`가 폴더에 있어도 `.vercelignore`가 막는다. 스크립트가 "기록된 배포본과 다르다"로 멈추면 `@gltf-transform/core` 판본이나 Node가 바뀐 것이다 — `npm ci`로 lock 판본을 맞춰 다시 하고, 그래도 다르면 새 출력이 원본과 대조를 통과했는지(같은 오류가 아니라 지문만 다른지) 사람이 확인한 뒤 스크립트의 `EXPECTED`와 `vehicle-sources.json`을 함께 고친다(DEC 기록).
2. **프로젝트 연결**(처음 한 번, 이미 됨): `vercel project add lg-cns-rag-web && vercel link --yes --project lg-cns-rag-web`. `vercel link`가 `frontend/.gitignore`(`.vercel`·`.env*`)와 `frontend/.env.local`을 만든다 — `.gitignore`는 지운다(저장소 루트 `.gitignore`가 이미 `.vercel`·`.env.*`를 막고, 새 파일의 `.env*`는 추적 중인 `frontend/.env.example`과 어긋난다). `.env.local`은 열어 보지 않는다(루트 `.gitignore`가 막고 `.vercelignore` 허용 목록에도 없다).
3. **환경변수(선택)**: 화면은 `VITE_API_BASE`가 없으면 `https://lg-cns-rag.vercel.app`을 부른다(`frontend/src/api.ts`). 바꿀 때만 `printf '<API 주소>' | vercel env add VITE_API_BASE production` — 빌드 결과(브라우저)에 들어가는 공개값이라 비밀값을 넣지 않는다(AGENTS.md 7절).
4. **배포**: `vercel deploy --prod`. 업로드 소스는 약 61MiB(대부분 `.glb`) — 이미 올린 같은 파일은 건너뛰어 더 작게 표시될 수 있다(2026-10-14 2차 배포는 42.2MiB로 표시). 새 프로젝트의 **첫 배포는 `--prod` 없이도 Production에 붙는다**(2026-10-14 실제로 그랬다 — 공식 환경 문서: 새 프로젝트의 첫 배포는 항상 production). 배포 뒤 두 모델을 받아 1단계 지문과 대조한다:
   ```bash
   T=$(mktemp -d); for m in sonata sorento; do curl -s -o "$T/$m.glb" https://lg-cns-rag-web.vercel.app/models/$m.glb; done; shasum -a 256 "$T"/*.glb; curl -s -o /dev/null -w "보관 모델 %{http_code}(404여야 함)\n" https://lg-cns-rag-web.vercel.app/models/kona.glb; rm -rf "$T"
   ```
5. **API CORS 열기**(저장소 루트, API 프로젝트) — 먼저 루트로 나와 연결을 확인한다: `cd .. && cat .vercel/project.json`(`projectName`이 `lg-cns-rag`인지 — `lg-cns-rag-web`이면 멈춘다. 다르면 `vercel link --yes --project lg-cns-rag`). 그다음:
   ```bash
   printf 'https://lg-cns-rag-web.vercel.app,http://localhost:5173' | vercel env add ALLOWED_ORIGINS production
   vercel deploy --prod      # 같은 SERVING_BUILD_ID — 환경변수는 서버가 시작할 때 한 번 읽으므로 재배포해야 적용된다
   curl -s https://lg-cns-rag.vercel.app/health      # build_id가 그대로인지(2026-10-14 당시 f1fe1843ed0f2c66, 생산 기간 재배포 뒤에는 5e32c164b15a544a; 첫 요청 13~16초)
   curl -si -X OPTIONS https://lg-cns-rag.vercel.app/search -H "Origin: https://lg-cns-rag-web.vercel.app" \
     -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type" | grep -i access-control-allow-origin
   ```
   localhost를 빼면 로컬 개발이 막힌다. 미리보기 배포 주소는 허용되지 않으니 그 주소의 검색 실패는 정상이다.
6. **확인**: 공개 화면에서 예시 질문 한 건이 끝까지 되는지, 첫 화면 "데이터 판본"의 build가 `/health`와 같은지, 쇼룸이 뜨는지, 모바일 390px.

**2026-10-14 실측 기록**(작업 F): 1차 `vercel deploy`는 원본 쏘나타 때문에 업로드 129.8MiB(CLI 표시) 뒤 `File size limit exceeded (100 MB)`로 실패 — 업로드 목록에 `node_modules`·보관 모델은 없었다(하위 폴더 `.vercelignore`가 읽힘). 줄인 쏘나타로 2차 배포 성공(업로드 표시 42.2MiB — 1차에서 올라간 쏘렌토 등은 건너뛴 것으로 보인다, 빌드 16초, 첫 배포라 Production `lg-cns-rag-web.vercel.app`에 붙음). 공개 주소에서 받은 두 모델 지문이 1단계 값과 같고 `kona.glb`·`.env.local`은 404. API는 `ALLOWED_ORIGINS` 추가 뒤 재배포 — `/health` build `f1fe1843ed0f2c66`(첫 요청 13.1초), 화면 주소의 사전 요청·검색 모두 200에 `access-control-allow-origin: https://lg-cns-rag-web.vercel.app`, 검색 응답에 `access-control-expose-headers: Retry-After`(#117 호출 상한도 이 재배포로 적용). 헤드리스 Chrome으로 공개 화면 첫 화면의 "데이터 판본"이 build `f1fe1843ed0f2c66`으로 뜨는 것을 확인했다. 모바일 390px 쇼룸에서는 부품 분류 패널이 차량을 가린다(기존 화면 배치 — 이 작업 밖, 후속 #120).

- **환경변수에 키를 넣지 않는다.** `VITE_*` 값은 빌드 결과(브라우저)에 그대로 들어간다(AGENTS.md 7절, DEC-032).
- 공개 화면의 검색도 API의 IP별 호출 상한(1분 60회, DEC-057)을 받는다. 화면은 앱 429에 "Too many requests."와 남은 초("N s left", 끝나면 "You can search again.")를 보이고 그동안 [Retry]와 [Find precedents]를 막는다(`frontend/src/casebook/errors.ts`·`useCountdown.ts`, DEC-057 ⑤ — 2026-10-18 선례 검색을 케이스북에 합치며 옛 `frontend/src/search/Feedback.tsx`의 동작을 영어 화면으로 옮겼다, DEC-075). 2026-10-14 첫 배포본에는 429 안내가 없었고 같은 날 PR #119 병합 뒤 화면을 다시 배포해 들어갔다(그때 공개 화면 번들에 "호출이 너무 잦습니다" 문구가 있는 것을 확인 — 합친 화면은 영어 문구라 번들의 한국어 문구가 빠지니, 번들로 확인하려면 "Too many requests"를 찾는다).

## 3. API 배포 — Vercel (서빙 묶음, 발표 전)

API는 지금 구조 그대로는 올리기 어렵다. 서버가 시작할 때 로컬 파일을 읽는데 Git 연동 배포에는 그 데이터가 없고(원본 데이터는 저장소에 넣지 않는다 — AGENTS.md 7절), 벡터 사본을 저장소 경로에 쓰는데(`server/rag/embeddings.py:67-69`·`:155-165`) 실행 중 쓸 수 있는 곳은 `/tmp`뿐이다.

시작(lifespan) 시간이 실행 시간 한도에 들어가는지는 문서에 없어 첫 배포에서 실측한다. 아래 "우리 서버" 열은 **지금 로컬 경로**를 잰 값이다 — 서빙 묶음 경로에서는 임베딩 모델·벡터·연결된 조사 요약이 `/tmp`로 받는 묶음(추정 약 150MB — 받은 파일과 풀어 쓴 모델 파일 약 67MB를 합쳐 약 220MB, `/tmp` 한도 500MB)에 들어가 함수 크기에서 빠지고, `FLAT_INV` 파싱도 없어진다. 묶음 경로의 실측값은 3-1절에 채웠다(함수 크기 근사 약 210MB, 시작 최대 RSS 901MB, 첫 요청 12.8~16.1초).

| 항목 | Vercel 제한(공식 문서, Fluid compute) | 우리 서버(로컬 측정, 2026-10-12) |
|---|---|---|
| 함수 크기 | Python 압축 전 500MB(큰 함수 Beta 5GB) | (로컬 경로, macOS) 의존성 약 194MB + 임베딩 모델 약 67MB — 묶음 경로 Vercel은 Linux 근사 약 210MB(모델은 묶음으로 `/tmp`에 받아 함수 크기에서 빠짐, 3-1절) |
| 메모리 | Hobby 2GB·Pro 4GB | 시작 최대 RSS 약 0.9~1GB — 그중 `FLAT_INV` 파싱(`read_flat`)이 최대 약 665MB |
| 실행 시간 | Hobby 300초 | 시작 8~10초(로컬 사본) / DB에서 벡터를 받으면 18~100초(`server/README.md` 기록)·24~100초(`server/rag/embeddings.py` 주석) — 같은 2026-10-10 집 회선 측정의 두 기록 |
| 파일 쓰기 | `/tmp`만(최대 500MB) | 벡터 사본을 저장소 경로에 씀 → 바꿔야 함 |
| 본문 크기 | 요청·응답 4.5MB | 응답 크기는 카드 15건 기준으로 확인 |
| 지역 | 기본 `iad1` | Supabase 지역 확인 필요 |

조사 요약 원본은 `FLAT_INV.zip`(압축 4.3MB, 풀면 391MB·154,401줄)이다.

**방식 — 서빙 묶음(DEC-048 ⑤)**: build마다 로컬에서 지금과 같은 검사를 통과한 결과(순서 있는 카드·원인·연결된 조사 요약 1,870장·벡터·임베딩 모델)를 파일 하나로 만들어 Supabase Storage에 올리고, 서버는 `RAG_SOURCE=bundle`일 때 `/tmp`로 받아 sha256을 DB 기록과 대조한 뒤 쓴다. DB에서 직접 읽지 않는 이유: 카드 순서가 DB에 없고, `FLAT_INV`가 DB에 없고, 날짜 형식이 다르다(DEC-048 Reason). 로컬 시연 경로(1절)는 데이터를 읽는 방식 그대로 두고, 응답에는 `bundle_sha256` 칸이 `null`로 더해진다(DEC-048 ⑤ⅳ·DEC-050).

배포 서버 환경변수(DEC-050, `.env.example`): `RAG_SOURCE=bundle`·`SERVING_BUILD_ID`(띄울 build)·`SUPABASE_URL`(공개 주소용)·`SERVER_DATABASE_URL`(`rag_reader`)·`ALLOWED_ORIGINS`(배포 화면 주소). 관리자 키(`DATABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY`)는 넣지 않는다.

공개 전 필수: 이슈 #63 — 조회 전용 계정 `rag_reader`(묶음 기록 `serving_bundles` 조회 권한 포함)와 Vercel 환경변수 `SERVER_DATABASE_URL`(관리자 키는 Vercel에 두지 않음), Storage 읽기 자격(공개 읽기 버킷 — DEC-049 ③, 무결성은 `serving_bundles` 기록 sha256 대조), IP별 호출 상한(앱 1분 60회 + Vercel WAF 안전망 — 비밀 키 인증은 두지 않는다, DEC-057), 배포 주소 CORS. 통과 기준: 749문항 H@10 0.542 재현, `/search` 응답이 묶음 sha256 칸(로컬 경로는 `null`)을 빼고 로컬 경로와 바이트까지 같음, Vercel에서 함수 크기·최대 메모리·첫 요청 시간 실측.

> (2026-10-12) 위 "공개 전 필수"는 사용자 결정으로 바뀌어 #63 전에 Production에 먼저 올렸다(아래 3-1, DEC-051 ①). 통과 기준 중 "응답 바이트까지 같음"은 Vercel에서 **충족하지 못했고**, 사용자 결정으로 **CPU가 다른 환경에서는** "같은 749문항의 화면 기준 점수 `shown_any` 차이가 0.03 안 + 완전 같음/순서만 다름/구성 다름 기록"으로 대체했다(DEC-051 ③) — 실측 Vercel 0.545·로컬 0.543, 706·28·15. 같은 기계 안의 비교는 바이트 동일 기준 그대로다. 최대 메모리는 서버가 시작 끝에 로그로 남긴다(3-1). 함수 크기는 Vercel이 출력하지 않아 Linux x86 컨테이너 설치 크기로 근사했다(3-1, 약 210MB).

### 3-1. 실제 배포 (2026-10-12, DEC-051)

**지금 공개 주소: `https://lg-cns-rag.vercel.app`** (Vercel 프로젝트 `lg-cns-rag`, Hobby, 함수 지역 `syd1`). 사용자 결정으로 #63보다 먼저 Production에 올렸다(DEC-051 ①). 비밀 키 인증은 두지 않는다(DEC-057). 앱의 IP별 호출 상한(1분 60회)은 `server/ratelimit.py`로 구현됐고 2026-10-14 작업 F의 API 재배포로 적용됐다(2절 실측 기록). WAF 규칙은 Vercel 대시보드에서 설정해야 하며, 설정 전에는 앱 상한만 있다(아래 3-2).

| 파일 | 하는 일 |
|---|---|
| `app.py` | 진입점 — `server/api.py`의 `app`을 그대로 내보낸다 |
| `vercel.json` | `framework: fastapi`(CLI로 만든 프로젝트는 프리셋이 비어 `app.py`를 함수로 못 찾는다), `regions: ["syd1"]`(운영 Supabase ap-southeast-2와 같은 지역), `maxDuration` 60(첫 요청 실측 12.8~16.1초(아래 실측 표의 네 번) — 최악 16.1초의 약 3.7배. 공개 상태에서 요청 하나가 함수를 오래 붙잡지 않게 실측에 맞춤) |
| `.vercelignore` | CLI 배포는 로컬 폴더를 올린다. Vercel 기본 무시 목록에 `.env`·`.env.server`·`data/`가 없으므로 **필요한 것만 허용**한다(진입점·설정·`pyproject.toml`·`uv.lock`·`.python-version`·`server/`·`scripts/defect_precedent/`) |

Vercel 프로젝트 환경변수(Production): `RAG_SOURCE=bundle` · `SERVING_BUILD_ID=5e32c164b15a544a`(2026-10-14 생산 기간 재배포 — DEC-059; 이전 값 `f1fe1843ed0f2c66`은 되돌리기용, 되돌릴 때는 이 값을 다시 넣고 `vercel deploy --prod`) · `SUPABASE_URL` · `SERVER_DATABASE_URL`(`rag_reader`, Sensitive) · `UV_NO_CONFIG=1`(빌더 uv 0.10.11이 `required-version >=0.12.5`에 걸려서 — DEC-051 ④). `ALLOWED_ORIGINS=https://lg-cns-rag-web.vercel.app,http://localhost:5173`(2026-10-14 작업 F에서 추가하고 재배포 — 2절 실측 기록). 관리자 키(`DATABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY`)는 넣지 않는다.

다시 배포: 저장소 루트에서 `vercel deploy --prod`(먼저 `vercel link --project lg-cns-rag` — `.vercel/`은 gitignore). 값 확인은 `vercel env ls production`(값은 숨김). 로그는 `vercel logs <배포 주소>`.

실측(2026-10-12):

| 항목 | 값 |
|---|---|
| 749문항 화면 기준 점수 `shown_any` | Vercel 공개 주소 **0.545** · 같은 묶음·`rag_reader` 로컬 서버 0.543(기존 기록과 같음) — 차이 0.002, 기준 폭 0.03 안. 문항별 화면 목록: 완전 같음 706 · 순서만 다름 28 · 구성 다름 15(정답 포함 여부가 갈린 문항 1). 원인은 질문 임베딩의 CPU 오차로 **추정**(직접 비교는 안 함) |
| 첫 요청(새 배포 직후 — 묶음 155.4MB 다운로드·검사·모델 로드) | 13.2초 · 12.8초 · 16.1초 · 16.0초(네 번), 이후 0.2~0.5초 |
| 빌드 | 38초, Python 3.12(`.python-version`), uv 0.10.11 |
| CLI 업로드 | 1.7MB |
| 탐침 차이(macOS arm 벡터 ↔ Vercel Linux x86 재계산) | 최대 4.30e-04(콜드 스타트 네 번 모두 같음) → 묶음 경로만 허용 차이 1e-3(`CROSS_MACHINE_ATOL`, DEC-051 ②), 같은 기계는 1e-4. 서버는 통과해도 `탐침 최대 차이 …`를 로그에 남긴다 — `vercel logs <배포 주소> --json`으로 분포를 모아 다시 판단 |
| 시작 최대 RSS | **901MB**(Hobby 2GB 안) — 서버가 시작 끝에 `시작 최대 RSS …MB`를 로그로 남긴다 |
| 함수 크기 | Vercel이 출력하지 않아 **근사로 잼**: Linux x86 컨테이너(`python:3.12-slim`, uv 0.10.11)에 `uv.lock`대로 개발 의존성 없이 설치한 site-packages **약 208MB**(onnxruntime 63·numpy 57·pillow 14·tokenizers 12·psycopg 11MB 등) + 코드 약 2MB ≈ **210MB**(한도 500MB의 약 42%, Vercel 번들 최적화 전 값 — 실제 Vercel 산출물 크기는 미측정). **개발 의존성(`[dependency-groups] dev` — `httpx2`·`pytest`·`ruff`)은 뺀 값**이다 — Vercel 빌더가 이 그룹까지 설치하는지는 공식 문서(Python 런타임 "Dependencies" 절, 2026-10-23 조회)에 적혀 있지 않고 빌드 로그로도 확인하지 못했다(이슈 #103). 포함되면 이 근사보다 커진다(크기는 미측정). 다시 잴 때: `pyproject.toml`·`uv.lock`·`.python-version`을 임시 폴더에 복사해 uv 공식 이미지로 `docker run --rm --platform linux/amd64 -v <폴더>:/src:ro ghcr.io/astral-sh/uv:0.10.11-python3.12-trixie-slim sh -c 'cp -r /src /w && cd /w && UV_NO_CONFIG=1 uv sync --frozen --no-dev -q && du -sm .venv/lib/python3.12/site-packages'`(컨테이너 안). 코드 크기는 컨테이너가 아니라 **호스트(저장소 루트)에서** 따로 잰다: `du -sh server scripts/defect_precedent` — 컨테이너 안 `/w`에는 위 세 파일만 복사돼 있어 `server/`가 없다. (위 208MB는 2026-10-12 `python:3.12-slim` 일회용 컨테이너 안에서 uv 0.10.11을 `pip`으로 설치해 잰 값이다 — 저장소는 `pip install`을 쓰지 않으므로 다시 잴 때는 이 공식 이미지 명령을 쓴다. 같은 날 이 명령으로 재현하려 했으나 이 컴퓨터(Apple Silicon)에서 amd64 컨테이너가 시작되지 않아 확인하지 못했다 — #103) |

### 3-1a. 서빙 build 바꾸기·되돌리기 (DEC-059 운영 반영 기록)

서버가 띄우는 데이터는 Vercel 환경변수 `SERVING_BUILD_ID` 하나로 정해진다(코드 `server/` 변경 없이도 바뀐다). 묶음은 build마다 Storage와 `serving_bundles` 기록에 그대로 남아 있어(지우는 도구가 없다) 값만 바꿔 재배포하면 된다.

| build | 묶음 sha256 | 내용 |
|---|---|---|
| `f1fe1843ed0f2c66` | `dd0efac013a47dd9cb5b303d4d7958724e9cba21254f4bb9bc6f7f87a190bc1a` | 2026-10-06 판본, 생산 기간 칸 없음(DEC-059 이전) |
| `5e32c164b15a544a` | `b466430d989b55e1d623346f70461428b6ec83bfbb0508eff40bbf4d98c25127` | 같은 판본 + 573 생산 기간(DEC-059). 2026-10-14부터 공개 |

**바꾸는 법 — 스크립트 `scripts/switch_serving_build.sh`** (저장소 루트가 `lg-cns-rag`에 연결돼 있어야 한다: `.vercel/project.json`의 `projectName` 확인, 아니면 `vercel link --yes --project lg-cns-rag`. Vercel CLI 로그인 필요, 접속 정보는 읽지도 출력하지도 않는다. 터미널에 명령을 여러 줄 붙여 넣지 말고 한 줄씩 실행한다.)

```bash
bash scripts/switch_serving_build.sh f1fe1843ed0f2c66 --check
bash scripts/switch_serving_build.sh f1fe1843ed0f2c66
```

- 첫 줄 `--check`는 아무것도 바꾸지 않는다: 프로젝트 연결, **Vercel 로그인·Production 환경변수 목록을 읽을 수 있는지**(`/health`는 로그인 없이 읽혀서 이 확인이 없으면 거짓으로 통과한다), 현재 공개 build와 묶음 sha256이 위 표와 같은지를 본다. 둘째 줄이 확인(`y`)을 받은 뒤 실제로 바꾼다. 인수는 위 표의 build 둘 중 하나만 받는다(되돌릴 때 `f1fe…`, 다시 올릴 때 `5e32…`). 새 build를 쓰려면 스크립트의 `expected` 표와 위 표를 함께 고친다. Python이 필요 없다(`curl`·`sed`·`vercel`만).
- 순서: `SERVING_BUILD_ID` 삭제 → 추가 → `vercel deploy --prod` → `/health`를 최대 3번(10초 간격) 확인해 build·묶음 sha256이 표와 같을 때만 성공으로 끝낸다.
- **실패 때의 동작**(`tests/test_switch_serving_build.py`가 가짜 `vercel`·`curl`로 시험): 환경변수 변경이 실패하면 배포하지 않고 이전 값으로 되돌린 뒤 멈춘다 · 배포 명령이 실패해도 원격에서 배포가 올라갔을 수 있어 이전 값으로 되돌린 뒤 `/health`를 보고, 이전 build가 아니거나 읽히지 않으면 이전 build를 **다시 배포**해 확인한다 · 배포 뒤 `/health`가 안 맞을 때도 같다 · 이전 값 복구가 실패하면 변수 없이 재배포하면 서버가 시작하지 못하므로 **재배포하지 않고** 대시보드에서 직접 넣으라고 안내한다 · 공개 서버가 이미 그 build이면 배포 없이 숨은 환경변수만 그 값으로 다시 맞춘다. 실행 도중 Ctrl-C·터미널 종료로 끊기면(배포 명령이 끝나기 전) 환경변수를 이전 값으로 되돌리고(재배포는 하지 않음) 원격 배포가 계속 진행됐을 수 있으니 `/health`를 다시 보라고 알린다. 터미널 창을 닫아 화면 출력이 실패해도 멈추지 않도록 환경변수 복구를 안내 출력보다 먼저 한다. 환경변수와 공개 서버가 다른 build면 원하는 build 인수로 이 스크립트를 다시 실행한다(되돌리려면 이전 build, 새 build를 원하면 새 build — 공개 서버가 이미 그 build면 환경변수만 맞춘다). 배포 명령이 끝난 뒤 `/health` 확인 중에 끊으면 환경변수는 새 값 그대로 둔다(서버도 새 build). 복구(이전 build로 되돌리는 재배포) 중에는 스크립트가 신호를 무시한다 — 다만 자식인 `vercel`(node)은 Ctrl-C를 받아 그 단계가 중단될 수 있고(가짜 `vercel`은 bash라 시험이 이를 보지 못한다), 그러면 스크립트는 다음 단계로 진행해 끝에서 실패 안내를 내므로 끝난 뒤 `/health`와 대시보드의 `SERVING_BUILD_ID`를 확인한다. `vercel`이 멈추면 다른 터미널에서 `ps`로 그 `vercel` 프로세스의 PID를 찾아 `kill <PID>`(안 되면 `kill -KILL <PID>`)로 종료하고 종료 직후 `/health`와 `SERVING_BUILD_ID`를 확인한다. 값을 넣을 때는 내장 `printf`가 아니라 외부 `printf`를 쓴다(터미널이 닫혀 `echo`가 못 쓴 글자가 bash 버퍼에 남으면 내장 `printf`는 그 글자를 환경변수 값 앞에 섞는다). 이전 값 복구마저 실패하면 재배포하지 않고, 대시보드에서 값을 넣은 뒤 `/health`를 확인해 이전 build가 아니면 이전 build 인수로 스크립트를 다시 실행하라고 안내한다(진행 중인 배포가 없어질 때까지 `/health`를 계속 본다). 작업 폴더 점검은 "이미 그 build" 분기(배포하지 않으므로)를 건너뛴다.
- 이 스크립트도 `vercel deploy --prod`로 **지금 작업 폴더의 코드 전체**를 올린다 — 그래서 `--check`를 포함해 작업 폴더에 커밋하지 않은 변경이 있거나 HEAD가 `git fetch` 뒤의 `origin/main`과 다르면 중단한다(아래 "시작 전에 확인"의 첫 항목을 코드로 막은 것이고, 나머지 두 항목은 스크립트도 확인한다). 배포가 실패해 이전 build로 되돌린 뒤에도, 실패한 배포가 늦게 완료돼 새 build가 다시 공개될 수 있으니 대시보드 Deployments에서 진행 중인 배포가 없어질 때까지 `/health`를 다시 본다.

**스크립트를 쓸 수 없을 때의 손 절차** — 아래 `<BUILD>`에 위 표의 build를 넣는다.

**시작 전에 확인** — 이 절차의 `vercel deploy --prod`는 **지금 작업 폴더의 코드 전체**를 Production에 올린다(데이터 build만 바뀌는 게 아니다).
- `git status --short`가 비어 있고 `git rev-parse HEAD`가 `git rev-parse origin/main`(`git fetch` 뒤)과 같은 **깨끗한 최신 main**에서만 한다. 아니면 멈춘다.
- 저장소 루트가 `lg-cns-rag`에 연결돼 있는지 `cat .vercel/project.json`의 `projectName`으로 보고, 아니면 `vercel link --yes --project lg-cns-rag`.
- `vercel whoami`가 계정을 돌려주는지(로그아웃 상태에서도 `/health`는 읽히므로 이것으로 로그인을 확인한다).

**명령은 한 줄씩 실행하고 앞 줄이 성공했는지 본 뒤 다음 줄을 친다.** 여러 줄을 한꺼번에 붙여 넣지 않는다 — zsh은 같은 줄의 `# 설명`을 인수로 넘겨 실패하고, 중간에 실패해도 다음 줄이 계속 돈다(HANDOFF Failed Attempts). 명령 줄에 설명을 붙이지 않는다.

0. 바꾸기 **전에** `curl -s https://lg-cns-rag.vercel.app/health`로 지금의 `build_id`·`bundle_sha256`을 적어 둔다 — 아래 "이전 값"이다.
1. `vercel env rm SERVING_BUILD_ID production --yes`
2. `printf '<BUILD>' | vercel env add SERVING_BUILD_ID production` — **실패하면 배포하지 말고** 아래 "실패했을 때"로 이전 값을 되돌린다. 값이 없으면 서버가 시작하지 않는다(`server/api.py:108-112`).
3. `vercel deploy --prod`
4. `curl -s https://lg-cns-rag.vercel.app/health` — 첫 요청 13~16초. `build_id`·`bundle_sha256`이 위 표와 같아야 끝이다.

실패했을 때(**이전 값으로 되돌리기** — 처음 바꿀 때와 똑같이 지우고 → 넣고 → 배포한다. 새 값이 이미 들어 있으면 `env add`만으로는 교체되지 않는다):
1. `vercel env rm SERVING_BUILD_ID production --yes` — **위 2(새 값 넣기)가 실패해 변수가 이미 없는 경우에는 이 줄을 건너뛰고 2부터 한다.** `vercel env ls production`에 `SERVING_BUILD_ID`가 보이면 있는 것이다. 지우기가 "변수가 없다"가 아닌 다른 이유(로그인·네트워크)로 실패하면 대시보드 Settings > Environment Variables에서 이전 값으로 직접 바꾼다.
2. `printf '<이전 build>' | vercel env add SERVING_BUILD_ID production`
3. `vercel deploy --prod`
4. `curl -s https://lg-cns-rag.vercel.app/health` — `build_id`·`bundle_sha256`이 0번에서 적어 둔 이전 값과 같을 때만 복구 완료다.

- 위 3(처음 배포)이 실패했어도 Vercel에서는 배포가 이어져 몇 분 뒤 새 build가 공개될 수 있다. 되돌린 뒤에도 대시보드 Deployments에서 **진행 중인 배포가 없어질 때까지** 몇 분 간격으로 4를 다시 보고, 새 build가 다시 보이면 복구 1~4를 한 번 더 한다.
- 복구의 2(이전 값 넣기)가 성공하기 전에는 **재배포하지 않는다**(값이 없으면 서버가 시작하지 못한다). 2가 실패하면 대시보드 Settings > Environment Variables에서 직접 넣은 뒤 3~4를 한다.

- `printf`로 넣는다(`echo`는 끝에 줄바꿈이 붙어 build 이름이 틀어진다).
- `/health`의 `build_id`·`bundle_sha256`이 표와 다르면 바뀐 것이 아니다 — `vercel logs <배포 주소>`로 원인을 보고, 아래 확인을 건너뛰지 않는다.
- 검색 확인: `POST /search`(질문 한 건)에서 `build_id`가 같고 카드가 나오는지. 생산 기간 항목(`checklist[].item == "production_period"`)은 `5e32…`에서만 붙고 `f1fe…`에서는 0개가 정상이다.
- 화면은 되돌릴 필요가 없다(생산 기간 항목이 없는 응답도 그대로 그린다).

**검증한 것(2026-10-14)**: 되돌릴 대상 `f1fe1843ed0f2c66` 묶음이 **현재 코드(`0d05342`)로** 기동한다 — 로컬 서버(`RAG_SOURCE=bundle SERVING_BUILD_ID=f1fe1843ed0f2c66`, 조회 전용 계정이 없어 로컬 개발용 `ALLOW_ADMIN_DB_FOR_SERVER=1`로 기동)에서 `/health`가 위 표의 sha256과 같고 `/search`가 200에 카드 11건·생산 기간 항목 0개. 즉 되돌린 뒤 서버가 못 뜨는 경우는 이 확인으로 배제했다. 스크립트 경로 27건(깨끗한 최신 main 점검 2건·INT/TERM/HUP 중단 5건·복구 중 신호·터미널 닫힘 2건(환경변수 복구, 값 오염 없음)·되돌린 배포 확인 실패·`/health` 읽지 못함·묶음 sha256만 틀림 포함)을 가짜 `vercel`·`curl`(터미널 닫힘은 가상 터미널)로 시험했다(`tests/test_switch_serving_build.py`). 스크립트를 일부러 고쳐 시험이 실패하는 것을 확인한 곳: 복구 분기를 건너뛰기, 복구 뒤 `/health` 비교 느슨하게 하기, 환경변수 복구 빼기, "이미 그 build" 분기 깨기, 배포 뒤 목표 일치 비교 느슨하게 하기, 복구 경로마다의 늦은 완료 안내 지우기(복구 실패 경로 포함), 중단 `trap` 전체 삭제·`TERM HUP` 빼기·핸들러가 복구 대신 재배포하게 바꾸기·배포 명령 뒤 `trap` 해제 빼기·복구 구간 신호 무시 빼기, 외부 `printf`를 내장으로 되돌리기·`echo` 재정의 줄 지우기(터미널 닫힘 시험 2건), 깨끗한 작업 폴더 점검 지우기. **시험이 잡지 못하는 것**: 중단 처리 함수 안의 `trap '' INT TERM HUP` 줄(같은 신호가 두 번 와도 복구를 한 번만 하게 하는 것)과 `set +e` 줄은 각각 단독으로 지워도 시험이 통과한다. 안내 출력을 환경변수 복구보다 앞세워도 시험이 통과한다(외부 `printf`와 `echo` 재정의가 있어 순서가 결과를 바꾸지 않기 때문 — 순서는 방어 한 겹을 더한 것일 뿐 시험이 지키지 않는다). 안내문의 일부 문구가 바뀌어도 일부 시험은 통과한다. **알려진 한계**: 닫힌 터미널에서 `echo`가 못 쓴 글자가 `$(…)`(예: `/health` 읽기) 결과 앞에 섞일 수 있어, HUP이 무시된 채 시작했거나 복구 구간에서 터미널이 닫히면 복구가 정상이어도 "확인되지 않았다"로 판단해 이전 build를 한 번 더 배포하고 실패로 끝낼 수 있다(환경변수와 서버는 일치한 채 끝나며, 후속 이슈로 둔다). 진짜 `vercel`(node)을 쓰는 시험은 없다(공개 서비스를 바꾸므로). 공개 `/health`는 `curl`로 읽어 위 표(`5e32…`)와 같음을 확인했다. 스크립트의 `--check` 전체는 이 컴퓨터에 `.vercel` 연결이 없어 실행하지 못했다(2026-10-14 옛 브랜치 때의 읽기 전용 실행은 그 판본의 기록이다). **확인하지 못한 것**: 진짜 Vercel에서 환경변수 삭제·추가·재배포를 이 스크립트로 실행해 보지는 않았다(공개 서비스를 바꾸므로 — 같은 명령 순서는 2026-10-14 생산 기간 재배포에서 사용자가 직접 실행해 성공). 시연 전 연습이 필요하면 사용자가 정해 한다.

**언제 되돌리나(DEC-059 인터뷰 결정 ⑤)**: 10/16 밤까지 배포를 끝내고 10/17부터 동결한다. 동결 뒤 새 build에서 문제가 보이면 위 절차로 `f1fe…`로 되돌리고, 생산 기간 표시는 발표에서 뺀다.

### 3-2. 호출 상한과 시연 준비 (이슈 #63, DEC-057)

**구조 — 두 겹, 둘 다 비밀값 없이**

| 겹 | 위치 | 기준 | 하는 일 |
|---|---|---|---|
| 앱 | `server/ratelimit.py` (CORS 미들웨어 안쪽) | `POST /search`는 1분 `RATE_LIMIT_PER_MINUTE`(기본 60)회, `POST /draft`는 1분 `DRAFT_RATE_LIMIT_PER_MINUTE`(기본 6)회 — 두 경로를 따로 세고, 둘 다 IPv4는 주소별, IPv6는 앞 64비트(/64)별로 센다(DEC-057 추가 결정) | 넘으면 429 + `Retry-After`. 429에도 `Access-Control-Allow-Origin`이 붙고 `Retry-After`는 `Access-Control-Expose-Headers`로 화면이 읽을 수 있다 |
| WAF | Vercel 방화벽 규칙 1개 (Hobby 한도 1개) | **모든 경로**, IP당 1분 120회 *(한도는 에이전트 제안·사용자 채택 2026-10-13. 경로 범위는 PR #117 리뷰로 `/search` → 모든 경로)* | 앱을 우회하는 폭주를 엣지에서 차단. `/health`나 없는 주소도 새 인스턴스를 깨워 서빙 묶음(약 155MB)을 받게 하므로 함께 센다 |

- 앱 60 < WAF 120인 이유: WAF가 막은 429에 CORS 머리글이 붙는지 Vercel 문서에 없다. 정상 사용은 앱의 429(머리글 있음)가 먼저 나가게 한다. WAF는 모든 경로를 세므로 검색 60회에 CORS 사전 요청(OPTIONS)·`/health`가 더해진다 — 사전 요청은 브라우저가 `Access-Control-Max-Age`(Starlette 기본 600초) 동안 재사용해 검색마다 붙지 않는다.
- 앱 카운터는 인스턴스별 메모리라 인스턴스 수만큼 느슨하다. 새 인스턴스마다 서빙 묶음(약 155MB)을 받으므로 폭주하면 Supabase 전송량이 늘 수 있다. WAF 카운터는 지역별로 센다(Vercel 문서).
- 클라이언트 IP는 Vercel 위에서만 `x-forwarded-for`의 첫 값을 쓴다(Vercel이 외부에서 온 값을 덮어써 위조할 수 없다). 그 밖의 환경은 소켓 주소를 쓴다. "Vercel 위"는 환경변수 `VERCEL`로 안다 — 이 값은 프로젝트 설정의 **시스템 환경변수 노출**(공식 문서 문구 "Enable access to System Environment Variables" — 대시보드 문구는 달라질 수 있다)이 켜져 있어야 생긴다(Vercel 문서). 꺼져 있으면 모든 방문자가 한 주소로 묶여 함께 1분 60회에서 막히므로 아래 "앱 상한 확인"으로 배포 뒤 확인한다.
- 시연장이 공유 IP면 호출이 합산된다.

**WAF 규칙 설정 (사용자 계정 작업, 대시보드 문구는 달라질 수 있다)**
1. 프로젝트 `lg-cns-rag` → Firewall → Configure → New Rule.
2. 이름 `api-rate-limit`, 조건: Request Path가 `/`로 시작한다(모든 경로 — 규칙이 1개뿐이라 `/search`만 걸면 `/health`·없는 주소 폭주를 못 막는다).
3. Then: Rate Limit, Fixed Window, 창 60초, 한도 120, 키 IP, 응답 기본(429) → Save → Review Changes → Publish.
4. **평소·시연 상태는 Action Default(429)**다. Log는 요청을 기록만 하고 막지 않아 안전망이 꺼진다 — 처음 트래픽을 보려고 Log로 둘 수는 있지만 시연 전날까지 Default(429)로 되돌리고, 최종 설정이 "모든 경로·고정 창 60초·한도 120·키 IP·Default(429)"인지 대시보드에서 다시 확인한다.

**앱 상한 확인 (배포 뒤 한 번, WAF는 평소 설정 그대로)** — 앱 상한이 Vercel 위에서 실제로 켜졌고 IP별로 갈리는지 본다(시험은 `VERCEL=1`을 가정하므로 배포에서만 확인된다).
1. **60초 동안 이 네트워크에서 API를 부르지 않은 뒤** 시작한다(앞선 호출이 창에 남아 있으면 일찍 429가 나온다). 검색 계산을 하지 않아 빨리 끝나는 잘못된 요청(빈 본문 → 422)도 상한에 세므로(`tests/test_rate_limit.py`의 `test_rejected_requests_count_too`) 그것으로 60초 안에 보낸다:
   ```bash
   T=$(mktemp -d); res="판별 불가"; for i in $(seq -w 1 119); do code=$(curl -s -o "$T/b" -D "$T/h" -w "%{http_code}" -X POST -H "content-type: application/json" -d '{}' https://lg-cns-rag.vercel.app/search); if [ "$code" = 429 ]; then if grep -q "호출이 너무 잦습니다" "$T/b" && grep -qi "^retry-after" "$T/h"; then res="앱 429 ${i}번째"; else res="WAF 429 ${i}번째(앱 아님)"; fi; break; fi; done; echo "$res"; rm -rf "$T"; case "$res" in "앱 429"*) true;; *) false;; esac
   ```
   (번호는 `seq -w`라 `061`처럼 세 자리다. 한글을 변수 바로 뒤에 붙일 때는 `${i}`처럼 중괄호로 감싼다 — macOS zsh·bash가 한글까지 변수 이름으로 읽어 값이 사라진다.)
2. 읽는 법 — **앱 429는 본문이 한국어 `detail`("호출이 너무 잦습니다…")이고 `retry-after`가 있는 응답만** 인정한다(명령이 이것으로 가르고, 앱 429가 아니면 종료 코드 1):
   - **`앱 429 061번째`**: 앱 상한이 켜져 있다.
   - **`앱 429 062~119번째`**: 앱 상한은 켜져 있고 요청이 여러 인스턴스로 나뉜 것이다(인스턴스별 카운터) — 실패가 아니다.
   - **`앱 429 060번째 이전`**: 60초를 쉬지 않았거나 다른 사람의 호출과 한 주소로 묶였을 수 있다 — 60초 쉰 뒤 다시 하고, 그래도 같으면 시스템 환경변수 노출을 확인한다.
   - **`WAF 429 …(앱 아님)`**: 같은 네트워크의 다른 기기 호출이 더해져 WAF(모든 경로 120회)가 먼저 막았다 — 앱 상한의 증거가 아니다. 다른 기기 사용을 멈추고 60초 쉰 뒤 다시 한다.
   - **`판별 불가`**(119번째까지 429 없음): 앱 상한이 꺼진 것인지 인스턴스가 많이 나뉜 것인지 이 방법으로는 가를 수 없다 — 성공으로 기록하지 않는다. 다른 사람이 쓰지 않는 시간에 `RATE_LIMIT_PER_MINUTE`를 잠시 5로 낮춰 다시 배포하고 같은 명령(10번 안에 앱 429가 나와야 함)으로 확인한 뒤 60으로 되돌려 다시 배포한다. **시연 날·다른 사람이 쓰는 시간에는 하지 않는다. 60으로 되돌려 재배포하고 대시보드 값을 다시 확인하기 전에는 끝내지 않는다**(5로 남으면 공개 API가 1분 5회로 막힌다).
3. 위 1단계에서 앱 429를 받은 직후 다른 네트워크(휴대폰 핫스팟)에서 요청 **한 건만** 보낸다: `curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "content-type: application/json" -d '{}' https://lg-cns-rag.vercel.app/search`. 앱 429면 모두 한 주소로 묶인 것이다 — 시스템 환경변수 노출을 확인한다. 422(빈 본문)는 IP별로 갈린다는 **약한 증거**다 — 요청이 상한이 안 찬 다른 인스턴스로 갔어도 422가 나오기 때문이다. 그래서 대시보드에서 시스템 환경변수 노출이 켜져 있는지도 함께 확인해 기록한다.
4. 결과(날짜·처음 429가 나온 번째·다른 네트워크 코드·시스템 환경변수 노출 설정 상태, 위 "판별 불가" 대응으로 한도를 5로 낮췄다면 **60으로 되돌린 재배포와 대시보드 값 재확인**)를 DEC-057에 적는다. 1분 기다리면 풀린다.

**WAF 확인 — 모든 경로 차단과 WAF 429의 CORS 머리글 (배포 뒤 한 번, Production에서)** — **시연 날이나 다른 사람이 쓰는 시간에는 하지 않는다. 4번 원복을 확인하기 전에는 끝내지 않는다**(공개 API가 막힌 채 남는다). Preview는 Production 환경변수가 없고(위 환경변수 표는 Production만) 배포 보호에 걸릴 수 있으며 WAF 규칙 적용 여부도 문서로 확인되지 않아, 재배포 없이 Production에서 잰다.
1. WAF 규칙을 임시로 **창 10초·한도 5**, Action **Default(429)**로 바꿔 Publish한다(앱 상한 60보다 작아야 WAF가 먼저 막는다).
2. 앱이 세지 않는 `/health`와 없는 주소에서도 WAF가 막는지 본다 — 둘 중 하나라도 429가 없으면 실패(종료 코드 1)다. 규칙 조건이 `/search`만으로 잘못 남았으면 여기서 걸린다:
   ```bash
   bad=0; for p in /health "/no-such-path-$(date +%s)"; do got=$(for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" "https://lg-cns-rag.vercel.app$p"; done | grep -c '^429$'); echo "${p}: 429 ${got}회"; [ "$got" -gt 0 ] || bad=1; done; [ "$bad" -eq 0 ] || { echo "실패 — 모든 경로 조건 확인"; false; }
   ```
3. `/search`에서 **처음 나온 429**의 머리글과 본문을 함께 저장해, 한국어 `detail`이 없는(앱이 아닌) WAF 429인지 확인하고 CORS 머리글을 본다 — WAF 429를 확인하지 못하면 종료 코드 1이다(CORS 머리글 유무는 결과로 기록할 값이라 실패로 치지 않는다):
   ```bash
   sleep 11; T=$(mktemp -d); for i in $(seq -w 1 15); do curl -s -o "$T/h$i.body" -D "$T/h$i.head" -w "%{http_code}\n" -X POST -H "Origin: http://localhost:5173" -H "content-type: application/json" -d '{"question":"brake fluid leak"}' https://lg-cns-rag.vercel.app/search; done
   first=$(grep -lE "^HTTP/[0-9.]+ 429" "$T"/h??.head | head -1)
   ok=0; if [ -z "$first" ]; then echo "실패 — 429가 한 번도 안 나옴(규칙 Action·한도·Publish 확인)"; elif grep -q "호출이 너무 잦습니다" "${first%.head}.body"; then echo "실패 — 앱 429임(WAF 한도가 앱보다 작은지 확인)"; else ok=1; echo "첫 WAF 429: $first"; grep -i "access-control-allow-origin" "$first" || echo "WAF 429에 CORS 머리글 없음"; fi; rm -rf "$T"; [ "$ok" -eq 1 ]
   ```
4. 규칙을 원래대로(모든 경로·창 60초·한도 120·Default(429)) 되돌리고 Publish한 뒤 대시보드에서 값을 다시 확인한다.
5. 결과(모든 경로 차단 여부, WAF 429의 CORS 머리글 있음/없음, 날짜)를 이 절과 DEC-057에 적는다. 머리글이 없으면 브라우저가 WAF 429의 본문을 읽지 못해 화면은 "Could not reach the server."로 안내한다 — 화면의 429 안내("Too many requests."와 남은 초("N s left", 끝나면 "You can search again."))는 앱 429에만 나온다(작업 F, 지금은 `frontend/src/casebook/errors.ts`).
6. (IPv6 확인, 이슈 #118) **같은 /64 안의 서로 다른 출발지 IPv6 주소 두 개와 다른 /64의 주소 하나를 쓸 수 있을 때만** 한다 — 한 주소로 `curl -6`을 반복하면 주소 단위로 세는 옛 코드도 429가 나와 /64 묶음의 증거가 되지 않는다. 방법: 주소 A로 한도까지 보낸 뒤 같은 /64의 주소 B로 보내면 429가 이어지고(앱 상한이 /64 단위), 다른 /64의 주소 C로는 200이 나와야 한다. WAF도 같은 방식으로 본다. 그런 환경이 없으면 앱은 자동 시험(`tests/test_rate_limit.py`)으로만 확인했다고 적고 실서버 앱·WAF의 묶음 단위는 "미확인"으로 남긴다(지금은 미확인). 사업자가 /56·/48을 위임하면 /64가 여럿이라 앱 상한만으로는 피해질 수 있고 그때 안전망은 WAF다.

**공개 주소로 시연하는 날 (DEC-057 ④)**
1. **시연 전날까지**: 앱 상한을 올려야 하면 `RATE_LIMIT_PER_MINUTE`를 바꿔 다시 배포한다 — 환경변수 변경은 재배포가 필요하고 재배포는 새 인스턴스라 워밍업이 사라지므로 시연 당일에 하지 않는다. 공개 화면(`https://lg-cns-rag-web.vercel.app`)에서 검색 한 건이 되는지도 본다(화면 주소는 `ALLOWED_ORIGINS`에 들어 있다 — 2절).
2. 시연 날 WAF는 **Default(429) 그대로** 둔다 — Log로 바꾸면 폭주 안전망이 꺼진다. 시연장이 공유 IP라 상한이 걱정되면 전날까지 한도를 조정하거나, 공개 주소가 막히면 1절의 로컬 포트를 대체 수단으로 쓴다.
3. **마지막 단계 — 시연 5분 전**: `curl -s https://lg-cns-rag.vercel.app/health`와 예시 검색 1회를 부른다 — 새 인스턴스가 서빙 묶음을 받아 시작하는 시간을 미리 쓴다. 중간에 인스턴스가 내려가면 첫 요청이 다시 느릴 수 있다(케이스북은 3초가 지나도 응답이 없으면 "The server may be waking up — the first request can take 13–16 seconds."를 보이고 60초 뒤 취소한다 — 그래도 시연 전에 이 워밍업을 한다).
4. 화면은 앱의 429에 "Too many requests."와 남은 초("N s left", 끝나면 "You can search again.")(`Retry-After`)를 보이고 그동안 [Retry]·[Find precedents]를 막는다(작업 F, DEC-058, DEC-075로 케이스북에 옮김). 이 화면 변경은 PR 병합 뒤 화면을 다시 배포해야 공개 주소에 들어간다(2절 4단계).

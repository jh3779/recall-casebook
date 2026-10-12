# Vercel 배포 안내 (DEC-048)

> 2026-10-12 기준. 발표 시연은 **로컬**에서 하고(1절), 외부 배포는 **일단 Vercel**로 한다. 화면을 먼저 올리고(2절), API는 서빙 묶음(Supabase Storage)으로 발표 전에 옮긴다(3절). API는 **Hobby** 플랜 프로젝트 `lg-cns-rag`로 배포했다(3-1절) — Hobby는 비상업·개인 용도이고 팀 협업 기능은 Pro다.

## 1. 시연 — 로컬 포트

터미널 두 개로 띄운다(`uvicorn`은 끝날 때까지 터미널을 잡고 있다).

```bash
# 터미널 1 — API 서버 (저장소 루트). 조회 전용 계정이 생기기 전에는 관리자 연결을 명시적으로 허용한다
ALLOW_ADMIN_DB_FOR_SERVER=1 uv run --env-file .env uvicorn server.api:app --port 8000
# 터미널 2 — 화면 (frontend/, PR #60 병합 뒤). 먼저 public/models/에 .glb 두 개를 넣는다(2절)
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

관리자 연결(`DATABASE_URL`, RLS 우회·쓰기 가능)은 적재를 맡은 사람의 컴퓨터에서만 쓴다 — 다른 사람의 노트북으로 시연하면 시연 전에 조회 전용 계정 `rag_reader`를 만들어 `.env.server`(`SERVER_DATABASE_URL`만)로 띄운다(`server/README.md` 3단계).

시연 전 점검: `curl localhost:8000/health`가 `build_id`를 돌려주는지, `/docs`에서 `POST /search` 한 건이 원인 출처(리콜 번호·PDF)와 함께 나오는지, 화면이 데모 스냅샷인지 API 연결 화면인지(아래 첫 항목).

- **지금 화면은 API를 부르지 않는다.** #60 화면은 `public/data/recalls.json` 데모 스냅샷을 읽는다 — 화면↔API 연결(#60 뒤 작업, HANDOFF 할 일 50)이 끝나기 전의 시연 화면은 우리 검색 결과(카드 30,350장)가 아니다. API 결과를 보여 주려면 연결을 먼저 하거나, API 응답(`curl`·`/docs`)을 따로 보여 준다.
- 서버가 시작할 때 읽는 로컬 파일: `data/processed/defect/`의 `build.json`·`recalls.jsonl`·`eval.jsonl`·`causes.jsonl`·`causes.manifest.json`, `data/raw/nhtsa/`의 `manifest.json`·`FLAT_INV.zip`. **드라이브의 `data.zip`·`defect_data_2026-10-08` 사본으로는 서버가 뜨지 않는다**(`docs/환경셋팅.md` 4절 주의) — 서버용 묶음 `defect_data_2026-10-12_dec047`(드라이브 업로드 뒤 위치를 `docs/환경셋팅.md` 4절에 적는다)을 쓴다.
- 시작할 때 **Supabase 접속(인터넷)**이 필요하고(DB 명세·벡터 대조), 임베딩 모델 캐시가 없으면 모델(약 67MB)도 내려받는다 — **발표 전에 시연 장소 네트워크에서 한 번 띄워 둔다.**
- CORS는 기본으로 `http://localhost:5173`만 허용한다(환경변수 `ALLOWED_ORIGINS`로 바꿈, DEC-050).

## 2. 화면 배포 — Vercel (먼저)

화면은 Vite로 만든 정적 사이트다. PR #60이 main에 병합된 뒤 진행한다.

| Vercel 프로젝트 설정 | 값 | 근거 |
|---|---|---|
| Root Directory | `frontend` | 화면 코드 위치(DEC-032) |
| Framework Preset | Vite | `frontend/vite.config.ts` |
| Build Command | `npm run build` (`tsc -b && vite build`) | `frontend/package.json` |
| Output Directory | `dist` | Vite 기본값 |
| Install Command | `npm ci` | 락 파일 그대로(AGENTS.md 4절) |
| Node.js Version | 프로젝트 설정에서 **24.x** 선택 | Vercel은 `.nvmrc`를 읽지 않고 프로젝트 설정이나 `package.json` `engines.node`를 본다 — 팀 기준은 `frontend/.nvmrc`(24) |

- **선행 필수 — 3D 모델 파일**: #60 `frontend/README.md`는 `public/models/*.glb`(두 파일, 약 10.5MB·8.4MB)를 `.gitignore`에 넣고 드라이브에서 받게 한다. Git 연동 배포에는 이 파일이 들어가지 않아 공개 주소의 화면이 "3D 모델을 불러오지 못했습니다"에서 멈춘다. 배포 전에 넣는 방법을 정한다(빌드 때 내려받기 또는 Vercel CLI 배포 — 저장소 커밋은 1MB 넘는 파일을 막는 커밋 훅 때문에 안 된다) — 박성호 님과(#60 코멘트). CLI 배포는 `.gitignore`가 아니라 `.vercelignore`를 보므로, 쓰게 되면 `.vercelignore`로 올라갈 범위를 제한한다.
- **환경변수에 키를 넣지 않는다.** `VITE_*` 값은 빌드 결과(브라우저)에 그대로 들어간다(AGENTS.md 7절, DEC-032). API 주소처럼 공개돼도 되는 값만 넣는다.
- 배포 뒤 확인: 공개 주소에서 화면이 뜨고 `models/*.glb`가 200으로 받아지는지.

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

공개 전 필수: 이슈 #63 — 조회 전용 계정 `rag_reader`(묶음 기록 `serving_bundles` 조회 권한 포함)와 Vercel 환경변수 `SERVER_DATABASE_URL`(관리자 키는 Vercel에 두지 않음), Storage 읽기 자격(공개 읽기 버킷 — DEC-049 ③, 무결성은 `serving_bundles` 기록 sha256 대조), 인증 또는 호출 상한, 배포 주소 CORS. 통과 기준: 749문항 H@10 0.542 재현, `/search` 응답이 묶음 sha256 칸(로컬 경로는 `null`)을 빼고 로컬 경로와 바이트까지 같음, Vercel에서 함수 크기·최대 메모리·첫 요청 시간 실측.

> (2026-10-12) 위 "공개 전 필수"는 사용자 결정으로 바뀌어 #63 전에 Production에 먼저 올렸다(아래 3-1, DEC-051 ①). 통과 기준 중 "응답 바이트까지 같음"은 Vercel에서 **충족하지 못했고**, 사용자 결정으로 **CPU가 다른 환경에서는** "같은 749문항의 화면 기준 점수 `shown_any` 차이가 0.03 안 + 완전 같음/순서만 다름/구성 다름 기록"으로 대체했다(DEC-051 ③) — 실측 Vercel 0.545·로컬 0.543, 706·28·15. 같은 기계 안의 비교는 바이트 동일 기준 그대로다. 최대 메모리는 서버가 시작 끝에 로그로 남긴다(3-1). 함수 크기는 Vercel이 출력하지 않아 Linux x86 컨테이너 설치 크기로 근사했다(3-1, 약 210MB).

### 3-1. 실제 배포 (2026-10-12, DEC-051)

**지금 공개 주소: `https://lg-cns-rag.vercel.app`** (Vercel 프로젝트 `lg-cns-rag`, Hobby, 함수 지역 `syd1`). **인증·호출 상한이 아직 없다** — 사용자 결정으로 #63보다 먼저 Production에 올렸다(DEC-051 ①). 누구나 `/search`를 부를 수 있으므로 #63을 서두른다.

| 파일 | 하는 일 |
|---|---|
| `app.py` | 진입점 — `server/api.py`의 `app`을 그대로 내보낸다 |
| `vercel.json` | `framework: fastapi`(CLI로 만든 프로젝트는 프리셋이 비어 `app.py`를 함수로 못 찾는다), `regions: ["syd1"]`(운영 Supabase ap-southeast-2와 같은 지역), `maxDuration` 60(첫 요청 실측 13.2초 — 공개 상태에서 요청 하나가 함수를 오래 붙잡지 않게 실측에 맞춤) |
| `.vercelignore` | CLI 배포는 로컬 폴더를 올린다. Vercel 기본 무시 목록에 `.env`·`.env.server`·`data/`가 없으므로 **필요한 것만 허용**한다(진입점·설정·`pyproject.toml`·`uv.lock`·`.python-version`·`server/`·`scripts/defect_precedent/`) |

Vercel 프로젝트 환경변수(Production): `RAG_SOURCE=bundle` · `SERVING_BUILD_ID=f1fe1843ed0f2c66` · `SUPABASE_URL` · `SERVER_DATABASE_URL`(`rag_reader`, Sensitive) · `UV_NO_CONFIG=1`(빌더 uv 0.10.11이 `required-version >=0.12.5`에 걸려서 — DEC-051 ④). `ALLOWED_ORIGINS`는 배포 화면이 생기면 넣는다(없으면 `http://localhost:5173`). 관리자 키(`DATABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY`)는 넣지 않는다.

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
| 함수 크기 | Vercel이 출력하지 않아 **근사로 잼**: Linux x86 컨테이너(`python:3.12-slim`, uv 0.10.11)에 `uv.lock`대로 개발 의존성 없이 설치한 site-packages **약 208MB**(onnxruntime 63·numpy 57·pillow 14·tokenizers 12·psycopg 11MB 등) + 코드 약 2MB ≈ **210MB**(한도 500MB의 약 42%, Vercel 번들 최적화 전 값 — 실제 Vercel 산출물 크기는 미측정). 다시 잴 때: `pyproject.toml`·`uv.lock`·`.python-version`을 임시 폴더에 복사해 uv 공식 이미지로 `docker run --rm --platform linux/amd64 -v <폴더>:/src:ro ghcr.io/astral-sh/uv:0.10.11-python3.12-trixie-slim sh -c 'cp -r /src /w && cd /w && UV_NO_CONFIG=1 uv sync --frozen --no-dev -q && du -sm .venv/lib/python3.12/site-packages'` + `du -sh server scripts/defect_precedent`. (위 208MB는 2026-10-12 `python:3.12-slim` 일회용 컨테이너 안에서 uv 0.10.11을 `pip`으로 설치해 잰 값이다 — 저장소는 `pip install`을 쓰지 않으므로 다시 잴 때는 이 공식 이미지 명령을 쓴다. 같은 날 이 명령으로 재현하려 했으나 이 컴퓨터(Apple Silicon)에서 amd64 컨테이너가 시작되지 않아 확인하지 못했다 — #103) |

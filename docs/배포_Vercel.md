# Vercel 배포 안내 (DEC-048)

> 2026-10-12 기준. 발표 시연은 **로컬**에서 하고(1절), 외부 배포는 **일단 Vercel**로 한다. 화면을 먼저 올리고(2절), API는 서빙 묶음(Supabase Storage)으로 발표 전에 옮긴다(3절). Vercel 플랜(Hobby·Pro)은 아직 정하지 않았다 — Hobby는 비상업·개인 용도이고 팀 협업 기능은 Pro다.

## 1. 시연 — 로컬 포트

```bash
# API 서버 (저장소 루트) — 조회 전용 계정이 생기기 전에는 관리자 연결을 명시적으로 허용한다
ALLOW_ADMIN_DB_FOR_SERVER=1 uv run --env-file .env uvicorn server.api:app --port 8000
# 화면 (frontend/, PR #60 병합 뒤)
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

- **지금 화면은 API를 부르지 않는다.** #60 화면은 `public/data/recalls.json` 데모 스냅샷을 읽는다 — 화면↔API 연결(#60 뒤 작업, HANDOFF 할 일 50)이 끝나기 전의 시연 화면은 우리 검색 결과(카드 30,350장)가 아니다. API 결과를 보여 주려면 연결을 먼저 하거나, API 응답(`curl`·`/docs`)을 따로 보여 준다.
- 서버가 시작할 때 읽는 로컬 파일: `data/processed/defect/`의 `build.json`·`recalls.jsonl`·`eval.jsonl`·`causes.jsonl`·`causes.manifest.json`, `data/raw/nhtsa/`의 `manifest.json`·`FLAT_INV.zip`. **드라이브의 `data.zip`·`defect_data_2026-10-08` 사본으로는 서버가 뜨지 않는다**(`docs/환경셋팅.md` 4절 주의) — 서버용 묶음 `defect_data_2026-10-12_dec047`(드라이브 업로드 뒤 위치를 `docs/환경셋팅.md` 4절에 적는다)을 쓴다.
- 시작할 때 **Supabase 접속(인터넷)**이 필요하고(DB 명세·벡터 대조), 임베딩 모델 캐시가 없으면 모델(약 67MB)도 내려받는다 — **발표 전에 시연 장소 네트워크에서 한 번 띄워 둔다.**
- CORS는 `server/api.py`의 `ALLOWED_ORIGINS`(`http://localhost:5173`)만 허용한다.

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

- **선행 필수 — 3D 모델 파일**: #60 `frontend/README.md`는 `public/models/*.glb`(두 파일, 약 10.5MB·8.4MB)를 `.gitignore`에 넣고 드라이브에서 받게 한다. Git 연동 배포에는 이 파일이 들어가지 않아 공개 주소의 화면이 "3D 모델을 불러오지 못했습니다"에서 멈춘다. 배포 전에 넣는 방법을 정한다(빌드 때 내려받기·Vercel CLI 배포·저장소 등) — 박성호 님과(#60 코멘트).
- **환경변수에 키를 넣지 않는다.** `VITE_*` 값은 빌드 결과(브라우저)에 그대로 들어간다(AGENTS.md 7절, DEC-032). API 주소처럼 공개돼도 되는 값만 넣는다.
- 배포 뒤 확인: 공개 주소에서 화면이 뜨고 `models/*.glb`가 200으로 받아지는지.

## 3. API 배포 — Vercel (서빙 묶음, 발표 전)

API는 지금 구조 그대로는 올리기 어렵다. 서버가 시작할 때 로컬 파일을 읽는데 Git 연동 배포에는 그 데이터가 없고(원본 데이터는 저장소에 넣지 않는다 — AGENTS.md 7절), 벡터 사본을 저장소 경로에 쓰는데(`server/rag/embeddings.py:67-69`·`:155-165`) 실행 중 쓸 수 있는 곳은 `/tmp`뿐이다.

| 항목 | Vercel 제한(공식 문서, Fluid compute) | 우리 서버(로컬 측정, 2026-10-12) |
|---|---|---|
| 함수 크기 | Python 압축 전 500MB(큰 함수 Beta 5GB) | 의존성 약 194MB(macOS 휠 — Linux로 다시 잼) + 임베딩 모델 약 67MB |
| 메모리 | Hobby 2GB·Pro 4GB | 시작 최대 RSS 약 0.9~1GB — 그중 `FLAT_INV` 파싱(`read_flat`)이 최대 약 665MB |
| 실행 시간 | Hobby 300초 | 시작 8~10초(로컬 사본) / DB에서 벡터를 받으면 18~100초(`server/README.md` 기록)·24~100초(`server/rag/embeddings.py` 주석) — 같은 2026-10-10 집 회선 측정의 두 기록 |
| 파일 쓰기 | `/tmp`만(최대 500MB) | 벡터 사본을 저장소 경로에 씀 → 바꿔야 함 |
| 본문 크기 | 요청·응답 4.5MB | 응답 크기는 카드 15건 기준으로 확인 |
| 지역 | 기본 `iad1` | Supabase 지역 확인 필요 |

조사 요약 원본은 `FLAT_INV.zip`(압축 4.3MB, 풀면 391MB·154,401줄)이다.

**방식 — 서빙 묶음(DEC-048 ⑤)**: build마다 로컬에서 지금과 같은 검사를 통과한 결과(순서 있는 카드·원인·연결된 조사 요약 1,870장·벡터·임베딩 모델)를 파일 하나로 만들어 Supabase Storage에 올리고, 서버는 `RAG_SOURCE=bundle`일 때 `/tmp`로 받아 sha256을 DB 기록과 대조한 뒤 쓴다. DB에서 직접 읽지 않는 이유: 카드 순서가 DB에 없고, `FLAT_INV`가 DB에 없고, 날짜 형식이 다르다(DEC-048 Reason). 로컬 시연 경로(1절)는 그대로 둔다.

공개 전 필수: 이슈 #63 — 조회 전용 계정 `rag_reader`와 Vercel 환경변수 `SERVER_DATABASE_URL`(관리자 키는 Vercel에 두지 않음), 인증 또는 호출 상한, 배포 주소 CORS. 통과 기준: 749문항 H@10 0.542 재현, `/search` 응답이 로컬 경로와 바이트까지 같음, Vercel에서 함수 크기·최대 메모리·첫 요청 시간 실측.

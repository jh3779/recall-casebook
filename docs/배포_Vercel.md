# Vercel 배포 안내 (DEC-048)

> 2026-10-12 기준. 발표 시연은 **로컬**에서 하고(아래 1절), 외부 배포는 **Vercel**로 한다. 화면을 먼저 올리고, API는 데이터 읽는 위치를 바꾼 뒤 옮긴다(DEC-048).

## 1. 시연 — 로컬 포트

```bash
# API 서버 (저장소 루트) — 조회 전용 계정이 생기기 전에는 관리자 연결을 명시적으로 허용한다
ALLOW_ADMIN_DB_FOR_SERVER=1 uv run --env-file .env uvicorn server.api:app --port 8000
# 화면 (frontend/, PR #60 병합 뒤)
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

- 서버가 뜨려면 `data/processed/defect/`(카드·DEC-047 원인 파일)와 `data/raw/nhtsa/`(manifest·`FLAT_INV`)가 있어야 한다 — 받는 법은 `docs/환경셋팅.md` 4절(드라이브 사본 주의 포함).
- CORS는 `server/api.py`의 `ALLOWED_ORIGINS`(`http://localhost:5173`)만 허용한다.

## 2. 화면 배포 — Vercel (먼저)

화면은 Vite로 만든 정적 사이트라 Vercel이 바로 빌드한다. PR #60이 main에 병합된 뒤 진행한다.

| Vercel 프로젝트 설정 | 값 | 근거 |
|---|---|---|
| Root Directory | `frontend` | 화면 코드 위치(DEC-032) |
| Framework Preset | Vite | `frontend/vite.config.ts` |
| Build Command | `npm run build` (`tsc -b && vite build`) | `frontend/package.json` |
| Output Directory | `dist` | Vite 기본값 |
| Install Command | `npm ci` | 락 파일 그대로(AGENTS.md 4절) |
| Node.js 버전 | 24 | `frontend/.nvmrc` |

- **환경변수에 키를 넣지 않는다.** `VITE_*` 값은 빌드 결과(브라우저)에 그대로 들어간다(AGENTS.md 7절, DEC-032). API 주소처럼 공개돼도 되는 값만 넣는다.
- 지금 화면(#60)은 API를 부르지 않고 `public/data/*.json` 정적 파일을 읽는다. API를 붙이는 일은 #60과 3절이 끝난 뒤다.
- 확인할 것: 화면이 쓰는 3D 모델 `models/*.glb`가 #60 브랜치에 들어 있지 않다(`frontend/scripts/gltf-json-to-glb.mjs`로 만드는 것으로 보임) — 배포본에 모델이 들어가는지 박성호 님께 확인.

## 3. API 배포 — Vercel (나중, 계획 필요)

API는 지금 그대로 올릴 수 없다 — 서버가 시작할 때 **로컬 파일**(카드 28MB·원인 파일 7.4MB·NHTSA 원본 25MB·벡터 사본)을 읽는데, 원본 데이터는 저장소에 넣지 않으므로(AGENTS.md 7절) git으로 만들어지는 배포본에 없다.

| 항목 | Vercel 제한(공식 문서, Fluid compute) | 우리 서버(로컬 측정) |
|---|---|---|
| 함수 크기 | Python 압축 전 500MB | 의존성 약 194MB + 임베딩 모델(측정 전) |
| 메모리 | Hobby 2GB | 카드 30,350장 + 벡터 약 46MB + 모델 |
| 실행 시간 | Hobby 300초 | 시작 8~10초(로컬 사본) / DB에서 벡터를 받으면 24~100초(집 회선) |
| 파일 쓰기 | `/tmp`만 | 벡터 사본·모델 캐시를 씀 |
| 지역 | 기본 `iad1` | Supabase 지역 확인 필요 |

옮기기 전에 할 일: ① 서버가 읽는 데이터를 Supabase(이미 build 단위로 카드·원인·벡터가 있음) 등에서 읽도록 바꾸기, 시작 대조를 그에 맞게 다시 설계(추적성 AGENTS.md 2-4 유지) ② 조사 요약 원본(`FLAT_INV`) 읽는 위치 ③ 임베딩 모델 위치(빌드 포함 / `/tmp` 내려받기) ④ 이슈 #63 — 조회 전용 계정 `rag_reader`와 Vercel 환경변수 `SERVER_DATABASE_URL`, 인증 또는 호출 상한, 배포 주소 CORS ⑤ 749문항 점수(H@10 0.542) 재현 확인. 세부 계획은 별도 문서로 세운다.

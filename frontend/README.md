# frontend — 결함 선례 찾기

영어 결함 서술을 공개 검색 API로 보내 고객사 선례·다른 회사 선례와 원문·출처를 보여 준다. 설계 정본은 [`docs/design-system/`](../docs/design-system/README.md) v1.0이다. 주소에 해시가 없으면 랜딩이 뜨고(DEC-074), 케이스북(`#casebook`)이 검색 화면이다. 상단에서 케이스북과 3D 쇼룸(`#showroom`)을 전환하고 8D 작성은 `#8d`다. 옛 `#search`는 케이스북으로 간다(DEC-075).

## 실행

Node **24** (`.nvmrc`), npm을 사용한다.

```bash
cd frontend
npm ci
npm run dev       # http://localhost:5173
```

`npm run lint`는 oxlint, `npm run build`는 TypeScript 검사와 Vite 빌드, `npm test`는 vitest다. 기본 포트 5173을 이미 쓰면 자동으로 다른 포트로 넘어가지 않고 안내한다.

## 검색과 API

- 기본 API: `https://lg-cns-rag.vercel.app`. 요청은 `POST /search`의 `{ "question": "..." }`, 판본은 `GET /health`다. 서버 계약은 `server/api.py`를 따른다.
- 다른 API를 쓰려면 `frontend/.env.development.local`에 `VITE_API_BASE=http://localhost:8000`을 지정한 뒤 개발 서버를 다시 시작한다. `.env.example`에는 키 이름만 있다. `VITE_*`는 브라우저에 공개되므로 비밀값을 넣지 않는다.
- 공개 API의 CORS 허용 주소는 공개 화면 `https://lg-cns-rag-web.vercel.app`과 `http://localhost:5173`이다(2026-10-14 작업 F, DEC-058). `127.0.0.1`이나 다른 포트·미리보기 배포 주소에서는 연결이 거부될 수 있다. 화면 배포 절차는 [`docs/배포_Vercel.md`](../docs/배포_Vercel.md) 2절.
- 원문은 React 텍스트 노드로만 그린다. 원인 상태 9종과 모르는 값을 모두 알리며, 문구의 잠정 정본은 [`cause-status.md`](../docs/design-system/copy/cause-status.md)다. 이슈 #53 게시·합의는 별도다.
- 원인 꼬리표는 Python 코드포인트 좌표와 원문을 대조한 구간만 감싼다. 목록·확인 항목의 긴 글은 CSS로만 접고 문자열을 자르지 않는다. 573 파일의 주소는 추측하지 않으며 파일명·SHA-256·제출일·글 정리 방식을 펼쳐 볼 수 있다.
- 60초 뒤 검색을 취소하고, 입력/호출 상한(429 — "Too many requests. Try again in N seconds." 문구만, 남은 초 세기·단추 막기는 없다)/연결/시간 초과/서버/응답 형식 오류를 구분한다(`casebook/errors.ts`). 실패해도 질문은 유지한다. 화면 전환 시 검색 상태도 유지한다. 쇼룸의 분류 검색은 케이스북 질문창을 채우기만 하고 자동 전송하지 않는다. 옛 선례 검색 화면에 있던 3초 뒤 "서버 시작 중" 안내와 429 남은 초 세기는 케이스북으로 합치며 사라졌다(DEC-075 영향 ①, HANDOFF 할 일 70).
- 케이스북은 영어 UI의 3단 작업대(목록·쌓이는 상세·메모)이고 767px 이하는 한 줄로 쌓인다(옛 목록 → 상세 → 목록 전환은 사라졌다). three.js는 쇼룸을 열 때 받으므로 모델 파일이나 WebGL이 없어도 검색이 동작한다.

## 3D 모델 파일 — 커밋하지 않는다

현재 차량은 **쏘나타(YF)·쏘렌토**다. Sketchfab 쏘나타와 사용자 제공 쏘렌토 GLB를 적용했다. 원본 법선·텍스처·스킨을 유지하며 두 모델의 앞 방향·바닥·차체 중심을 맞춘다. 화면의 길이는 5.2 단위로 통일해 실제 차체 크기 비교에는 쓰지 않는다. 회전은 차량 중앙의 수직축에 고정하며 부품 선택 중에도 중심이 이동하지 않는다. 팬·상하 회전은 제한하고 확대·축소는 유지한다.

| 모델 | 출처·저작자 | GLB 크기 |
|---|---|---:|
| 쏘나타 YF | [Hyundai Sonata 2014 — DR1KING100K](https://sketchfab.com/3d-models/hyundai-sonata-2014-7a0e4fa5122e4cc1b57d8b9149916558) | 원본 116,543,736바이트 (1K GLB) → 화면용 44,211,620바이트(쓰이지 않는 텍스처 좌표만 제거) |
| 쏘렌토 | [Kia Sorento — MattDoesBlender](https://sketchfab.com/3d-models/kia-sorento-47a0016ba8b842c780d79ded8fa0a891) | 18,780,960바이트 |

두 파일의 내장 출처는 CC BY 4.0이다. 화면에 저작자·출처·라이선스·변경 사항을 표시한다. 출처와 지문은 `public/data/vehicle-sources.json`에 있다 — `sha256`은 화면에 쓰는 파일(쏘나타는 배포본), 쏘나타 원본 SHA는 `derivedFrom.from`(DEC-058). 쏘렌토는 원본의 회색 재질을 재질 이름에 맞게 나눴고, 원본 바퀴 한 벌을 나머지 세 바퀴 배치 지점에 복제했다.

```bash
# frontend/에서. 사용자가 받은 GLB 경로에 맞게 복사한다.
mkdir -p public/models
# 쏘나타는 재질이 쓰지 않는 텍스처 좌표만 지워 둔다(Vercel CLI 업로드 100MB 한도, DEC-058) — 원본 지문이 다르면 멈춘다
# 원본은 116,543,736바이트 파일(Sketchfab 1K GLB)이다 — 내려받은 파일이 여럿이면 바이트 수로 고른다(다르면 스크립트가 거부). 먼저 npm ci
SONATA_GLB="$HOME/Downloads/hyundai_sonata_2014 (1).glb"   # 받은 원본 쏘나타 경로로 바꾼다
node scripts/strip-unused-texcoords.mjs "$SONATA_GLB" public/models/sonata.glb
cp ~/Downloads/kia_sorento.glb public/models/sorento.glb
node scripts/prepare-vehicle-parts.mjs
```

`public/models/`는 gitignore다. 화면용 두 파일은 공개 화면에서도 받을 수 있다: `https://lg-cns-rag-web.vercel.app/models/sonata.glb`·`/models/sorento.glb`(받은 뒤 `public/data/vehicle-sources.json` 지문과 대조). 쏘나타 화면용 파일은 원본에서 쓰이지 않는 텍스처 좌표(TEXCOORD)만 지운 것이다 — 스크립트는 출력을 다시 읽어 남은 정점 속성·인덱스 바이트와 재질 값·텍스처(이미지 지문·texCoord·샘플러)·재질·노드·메시 이름 목록을 원본과 대조하고, 출력 크기·SHA-256·지운 속성 수가 기록값과 같을 때만 쓴다(노드 변환은 `matrix`가 TRS로 다시 쓰여 float32 오차만큼 다를 수 있고 비교하지 않는다. 재질 확장이 있는 모델은 거부 — 이 모델 전용), 원본 지문은 `vehicle-sources.json`의 `derivedFrom.from`에 있다. 화면에는 CC BY 4.0 변경 사항으로 "미사용 UV 제거"를 표시한다. 그 밖에도 다른 환경에서는 원본 파일을 준비해야 하며 모델이 없으면 실패 안내·검색 복귀 버튼이 뜬다. 원본 메시·재질·본 이름으로 확인된 분류는 원본 형상을 사용한다. 없는 엔진·변속기·연료 배관 등은 일반적인 전륜구동 배치를 단순화한 도형으로 보완한다. 추정 도형은 투시에서만 보이고 실제 기록이 있는 분류에만 연결한다. 화면·핫스팟·패널에 설명용 추정임을 밝힌다. 기타 장비처럼 위치가 하나로 특정되지 않는 분류는 기록만 연다. 쏘나타 화면용 GLB는 약 42MiB(원본 약 111MiB)라 첫 로딩 비용이 여전히 크다. [구현·검증 기록](../docs/프런트_현대기아_모델.md).

## 현재 쇼룸 데모 데이터

`public/data/hyundai-kia-recalls.json`: 2026-10-06 보관 NHTSA 스냅샷에서 **SONATA 2011–2014년식 18건, SORENTO 2021–2023년식 8건**을 추렸다. 쏘나타·쏘렌토 하이브리드는 포함하지 않는다. 검색 결과가 아니며 차종의 전체 연식·최신 리콜 목록을 뜻하지 않는다. 한 리콜에 여러 분류가 있으면 분류별 건수의 합이 총 리콜 수보다 클 수 있다.

```bash
# 저장소 루트에서. 원본 flat ZIP·manifest와 카드 JSONL·build.json이 로컬에 있어야 한다.
uv run python -m scripts.build_showroom_demo --check   # 다시 만들어 커밋된 두 파일과 바이트 대조 → "일치"
uv run python -m scripts.build_showroom_demo           # 판본을 바꿀 때만: 다시 만들어 씀
node frontend/scripts/check-demo-against-cards.mjs data/processed/defect/recalls.jsonl   # 보조: 원문 세 칸·회사명 대조
# 쏘나타 18건 + 쏘렌토 8건 · 원문 대조 26/26 일치
```

생성기는 `data/processed/defect/build.json`이 가리키는 판본만 받는다 — 원본 `manifest.json`·flat ZIP·카드 파일의 sha256이 하나라도 다르면 만들지 않는다. 스냅샷 날짜도 build.json에서 읽고, 화면의 날짜는 manifest에서 읽는다. `--check`는 연식·분류·대상 대수·출처·RECORD_ID까지 포함한 결과 전체를 바이트로 대조한다. 원본 manifest·flat·카드·결과 JSON의 SHA-256과 정확한 차종·연식·RECORD_ID는 `hyundai-kia-manifest.json`에 남긴다. 결함·위험·시정 문장과 회사명은 카드 원문 그대로다. 각 카드에서 NHTSA 원문을 열 수 있으며 대상 대수는 해당 리콜 전체(다른 차종 포함)임을 표시한다. 검색 API·평가셋·색인은 바꾸지 않았다.

## 이전 트럭 모델·데이터 — 보관 기록

아래 Silverado·Ram 모델과 데모 데이터는 현재 화면에서 사용하지 않는다. 기존 검증 기록과 재현 입력을 보존한다.

쇼룸은 PR #60의 커밋 `5be42cb577237f3050f3123fb0d744756727acb1`에서 가져왔다. CCSA(George Mason University)의 FHWA/NHTSA 유한요소 차량 모델을 단순화한 화면이다. 재배포는 **2026-10-13 사용자 결정**으로 허용됐다(DEC-052). `public/models/`는 gitignore이며 커밋 훅의 1MB 제한도 지킨다.

우지훈 소유 [결함 선례 쇼룸 (Copy)](https://claude.ai/artifact/5022cf20-2f08-4389-b13f-5adde11b78d4)의 `models/silverado.gltf.json`·`models/ram.gltf.json`을 받는다. 비공개 artifact이므로 공유받아야 열린다. 아래 명령은 `frontend/`에서 실행한다.

```bash
mkdir -p public/models
node scripts/gltf-json-to-glb.mjs /받은/경로/silverado.gltf.json public/models/silverado.glb
node scripts/gltf-json-to-glb.mjs /받은/경로/ram.gltf.json public/models/ram.glb
shasum -a 256 public/models/*.glb
```

| 파일 | 크기(바이트) | SHA-256 |
|---|---:|---|
| `silverado.glb` | 10,524,576 | `d608c0bca5b7639cb5f735e758287c91b5bc927b5baeafb2ab22898a7b301612` |
| `ram.glb` | 8,446,292 | `f8532a1d34e906bd6817d01175eb185040e4598dfa4bc107052a23214552f512` |

원본 SHA-256: `silverado.gltf.json` = `2bb27ed2fb5482dd9b2b0d7f62b8c6de389fcb619456cbba731cb181fd9e10b0`, `ram.gltf.json` = `08e4d6eb162092c4e46d021275643222193b203d9a3ca4e0f7862e3b8eda8e30`. 변환은 포장만 바꾼다. 2026-10-13 로컬 보관 GLB 두 파일도 위 지문과 일치했다. 모델이 없으면 쇼룸에 실패 안내·검색 복귀 버튼이 뜬다. 옛 트럭 모델은 배포하지 않는다(`.vercelignore`, #108).

이전 트럭 화면에서는 원본의 메모리 사본에 중복 면 제거·45도 기준 음영 평활화를 적용했다. 원본 파일은 유지하며 모서리와 부품 선택 위치를 보존한다. `node scripts/inspect-model-surfaces.mjs`로 트럭 면 수·위치·법선을 확인할 수 있다. 수치와 한계는 [모델 표면 정리 기록](../docs/archive/프런트_모델표면_정리.md)을 따른다. 새 외관 모델에는 이 처리를 적용하지 않는다.

### 이전 쇼룸 데모 데이터

`public/data/`는 artifact 판본 `1791386571-be6b`에서 받은 스냅샷이다. **검색 결과가 아니다.** 전체 재생성 스크립트는 아직 없고, 부품 대응표의 생성 과정도 후속 일이다(HANDOFF 55).

| 파일 | 내용 | SHA-256 |
|---|---|---|
| `recalls.json` | Silverado 36건 + Ram 39건, 최신 접수일 2026-09-24 | `7a74f48ddde6dd1119de05c23a6e0f0173fadf544e8a77564eddd7b6f093270d` |
| `silverado_parts.json` | 메시 이름 → 부품 분류·재질 | `31ea3c52d2344ed1d3fed31cb26387a3da30efa13b9223faaa3c3b25b469748f` |
| `ram_parts.json` | 위와 같음 | `21be2ec38293b12bf6f76b6eefca6d15a19d83b8ad17342d1e3f61f3be83e87b` |

2026-10-13 정리(작업 D): 원래 77건의 파일 SHA-256은 `ce849c25ec5586c16528aa7c6fef2aaa429e4e5e84769d868aab0e280d7b1069`다. `14V614000` remedy의 `GMÂ\u0092s`에서 잘못 끼어든 U+00C2만 빼 `GM\u0092s`로 복원했고, 그 단계에서 77/77건의 원문·회사명이 카드와 같았다. 이어 Silverado HD만 언급하는 아래 두 객체를 Silverado 1500 탭에서 제외했다. 그 외 바이트·순서는 보존했다.

- `13V544000`: 결함 원문에 “Chevrolet Silverado HD, Chevrolet Express, and GMC Sierra HD vehicles”를 명시한다.
- `14V614000`: 결함 원문에 “Silverado HD, Traverse, GMC Acadia, Savana, and Sierra HD vehicles”를 명시한다.

`campno`가 `/^\d{2}E/`인 `13E073000`(Silverado)·`16E041000`(Ram)은 남기고 **장비 리콜** 배지를 붙인다. 리콜별 신고 대상 대수는 전체 리콜 범위이고 다른 차종도 포함한다. 차종 통계는 합산 대수 대신 접수일 범위를 표시한다.

```bash
# 저장소 루트에서. 카드 파일은 gitignore라 로컬에 준비되어 있어야 한다.
node frontend/scripts/check-demo-against-cards.mjs data/processed/defect/recalls.jsonl frontend/public/data/recalls.json
# 총 75건 · 일치 75건 (2026-10-13)
```

## 구조·검증 근거

`App.tsx`는 해시 전환과 공통 판본 조회, `search/`는 검색·표시, `api.ts`는 요청·응답 형식 검사, `showroom/ShowroomView.tsx`는 기존 쇼룸 상태, `showroom/Showroom.ts`는 3D 렌더링을 맡는다. `styles.css`의 쇼룸 스타일·주황색 변수는 `.view-showroom` 안에 한정했고 검색·상단은 정본 토큰의 남색을 쓴다.

Pretendard, Source Serif 4(400·600), JetBrains Mono(400·600)는 npm 패키지에서 번들한다. 외부 글꼴 CDN 호출은 없다. [`React lazy`](https://react.dev/reference/react/lazy)·[`Vite 환경변수`](https://vite.dev/guide/env-and-mode) 공식 문서를 확인했다.

실제 응답 픽스처와 갱신 규칙은 [`src/search/__fixtures__/README.md`](src/search/__fixtures__/README.md), 구현·검증 결과와 남은 확인은 [`docs/프런트_구현_검증.md`](../docs/프런트_구현_검증.md)에 기록한다.

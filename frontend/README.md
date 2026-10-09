# frontend — 결함 선례 쇼룸

Silverado 1500·Ram 1500 3D 모델에서 NHTSA 리콜이 기록된 부품을 고르면, 그 리콜의 번호·결함·결과·조치를 NHTSA 원문 그대로 보여 주는 화면이다.
claude.ai artifact "결함 선례 쇼룸"(판본 `1791386571-be6b`)을 React로 옮겼다. 스택은 Vite + React + TypeScript + three.js다([DEC-041](../.agent/DECISIONS.md)).

아직 Python API 서버(DEC-038)와 연결하지 않았다. 리콜은 `public/data/`의 데모 스냅샷을 읽는다.

## 실행

Node 버전은 `.nvmrc`(24)를 따른다.

```bash
cd frontend
npm ci
# 3D 모델 파일 2개를 public/models/에 넣는다 (아래 "3D 모델 파일")
npm run dev        # http://localhost:5173
```

| 할 일 | 명령 |
|---|---|
| 린트 (oxlint) | `npm run lint` |
| 타입 검사 + 빌드 | `npm run build` |
| 테스트 (vitest) | `npm test` |

## 3D 모델 파일 — 커밋하지 않는다

커밋 훅이 1MB 넘는 파일을 막아서(`scripts/check-staged.sh`) `public/models/`는 `.gitignore`에 넣었다. 팀 드라이브에서 받아 아래 경로에 둔다. 파일이 없으면 화면이 "3D 모델을 불러오지 못했습니다"에서 멈춘다.

| 경로 | 크기(바이트) | sha256 |
|---|---|---|
| `public/models/silverado.glb` | 10,524,576 | `d608c0bca5b7639cb5f735e758287c91b5bc927b5baeafb2ab22898a7b301612` |
| `public/models/ram.glb` | 8,446,292 | `f8532a1d34e906bd6817d01175eb185040e4598dfa4bc107052a23214552f512` |

- 출처: CCSA(George Mason University)의 FHWA/NHTSA 유한요소 차량 모델을 단순화한 것이다. 실차를 역설계했다.
- 만든 방법: artifact의 `models/*.gltf.json`(버퍼를 base64로 품은 glTF)을 `node scripts/gltf-json-to-glb.mjs <in> <out>`으로 `.glb`로 묶었다. 내용은 같고 포장만 바뀐다.
  - 원본 sha256: `silverado.gltf.json` `2bb27ed2fb5482dd9b2b0d7f62b8c6de389fcb619456cbba731cb181fd9e10b0`, `ram.gltf.json` `08e4d6eb162092c4e46d021275643222193b203d9a3ca4e0f7862e3b8eda8e30`

## 데이터 — `public/data/`

artifact 판본 `1791386571-be6b`에서 받은 데모 스냅샷이다. 저장소 스크립트(`scripts/defect_precedent/`)로 만든 파일이 아니다. 리콜 카드에서 다시 만드는 스크립트는 남은 일이다(`.agent/HANDOFF.md`).

| 파일 | 내용 | sha256 |
|---|---|---|
| `recalls.json` | 차종별 NHTSA 리콜(Silverado 38건, Ram 39건, 접수일 최신 2026-09-24). 결함·결과·조치는 원문 그대로 | `ce849c25ec5586c16528aa7c6fef2aaa429e4e5e84769d868aab0e280d7b1069` |
| `silverado_parts.json` | 3D 메시 이름 → 부품 분류(`defect`)·재질(`look`) | `31ea3c52d2344ed1d3fed31cb26387a3da30efa13b9223faaa3c3b25b469748f` |
| `ram_parts.json` | 위와 같음 | `21be2ec38293b12bf6f76b6eefca6d15a19d83b8ad17342d1e3f61f3be83e87b` |

`src/recalls.test.ts`의 "public/data 약속" 테스트가 화면이 기대하는 모양을 확인한다. 리콜 번호 형식, 번호 중복 없음, 분류가 `CATEGORIES` 안에 있는지를 본다.

## 구조

| 경로 | 하는 일 |
|---|---|
| `src/App.tsx` | 화면 상태(차종·외관/결함 투시·고른 부품·도장색)와 동작 |
| `src/showroom/Showroom.ts` | three.js 무대. 모델 로드, 외관 부품 판정, 핫스팟 좌표, 카메라 이동, 재질 전환 |
| `src/components/` | 상단 바·소개·패널(부품 목록·리콜 카드)·하단 도구·핫스팟·로딩 |
| `src/recalls.ts` | 리콜 고르기·집계·표시 형식 (순수 함수, 테스트 있음) |
| `src/config.ts` | 차종·부품 분류·도장색 |

- 상태는 React가 갖고 `Showroom`은 받은 상태대로 그리기만 한다. 핫스팟 위치는 매 프레임 바뀌므로 React 상태에 두지 않는다. `Showroom`이 요소를 직접 옮긴다.
- 폰트는 Pretendard(npm `pretendard`, OFL-1.1)를 번들에 넣는다. 외부 CDN은 쓰지 않는다.

## 서비스 원칙 (AGENTS.md 2절)

- 리콜 카드마다 리콜 번호(`campno`)를 단다. 결함·결과·조치는 NHTSA 영어 원문을 바꾸지 않고 보여 준다.
- 판정 필드와 판정 문구는 넣지 않는다.

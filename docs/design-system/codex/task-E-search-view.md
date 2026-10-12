# 작업 E — 검색 전용 화면 + 공개 API 연동

> 먼저 [README.md](README.md)(공통 규칙)와 `docs/design-system/` 전체(v1.0)를 읽는다. 이 작업의 화면 모양·문구·값은 그 폴더가 정본이다 — 여기 적은 것과 다르면 디자인 시스템을 따르고 차이를 보고한다.
> 시작 조건: 작업 D(PR #60 정리)가 main에 병합됨. `git switch main && git pull && git switch -c feat/search-view`.

## 목표

엔지니어가 **영어 결함 한 줄**을 넣으면 공개 API(`POST https://lg-cns-rag.vercel.app/search`)의 결과를 **목록 + 오른쪽 상세**로 보여 주는 검색 전용 화면. 3D 쇼룸(데모)과는 상단 탭으로 오간다. 3D 모델(`.glb`)이 없거나 WebGL이 없어도 검색 화면은 동작해야 한다.

## 1. 앱 구조 (라우터 라이브러리 없이)

| 파일 | 할 일 |
|---|---|
| `src/App.tsx` | **껍데기로 다시 쓴다**: 공용 상단 바([components/app-bar.md](../components/app-bar.md)) + 현재 화면. 화면 상태 `view`는 `location.hash`에서 처음 값을 읽고(`#search` 기본, `#showroom`), 바뀌면 해시에 쓴다(`hashchange`도 듣는다) |
| `src/showroom/ShowroomView.tsx` (새) | 지금 `App.tsx`의 `App`+`Explorer`를 거의 그대로 옮긴다. `React.lazy(() => import("./showroom/ShowroomView"))` + `<Suspense>`로 불러 **검색 화면이 three.js 묶음을 받지 않게** 한다 |
| 같은 파일 | `new Showroom()`(WebGL 컨텍스트 생성)을 try/catch로 감싸 실패해도 안내를 띄운다. 실패 안내에 "검색 화면으로" 버튼(`location.hash = "search"`) |
| 같은 파일 | `Loader`·`body.xray`는 쇼룸 안에서만 — 언마운트할 때 `body.classList.remove("xray")` |
| `src/styles.css` | `.loader`·`.stage` 등 화면 전체를 덮는 규칙을 `.view-showroom` 아래로 한정. 검색 화면은 일반 문서 흐름(스크롤) |
| 쇼룸 패널(`components/Panel.tsx`) | **"이 분류로 선례 검색" 버튼**(결정 1): 누르면 검색 질문 칸에 분류 영어 이름을 채우고 `#search`로 간다. **자동 검색하지 않는다.** 분류 영어 이름은 `src/config.ts`의 `CATEGORIES`에 `en` 칸을 더해 둔다(예: airbag → `air bag`, brakes → `brakes`, steering → `steering`, fuel → `fuel system`, seat → `seat belt`, tailgate → `tailgate latch`, suspension → `suspension`, driveline → `drive shaft`, transmission → `transmission`). 화면 사이 값 전달은 App 상태(예: `pendingQuestion`)로 |

## 2. 토큰 · 글꼴

- `docs/design-system/tokens/tokens.css`를 **`frontend/src/tokens.css`로 그대로 복사**해 `main.tsx`에서 불러온다(맨 위 주석에 "정본: docs/design-system/tokens/tokens.css — 바꿀 때 둘 다" 한 줄). 쇼룸 `styles.css`와 이름이 겹치는 토큰(`--bg-1`·`--ink`·`--ink-2`·`--ink-3`·`--line`·`--glass`·`--radius`)은 값이 같아야 한다(작업 D에서 `--ink-3` 맞춤). 쇼룸의 `--accent`(주황)와 검색 화면의 `--accent`(남색)는 이름이 같으므로 **검색 화면은 `.view-search` 범위에서 `--accent`를 다시 정의**하거나 검색용 이름(`--accent`를 tokens.css에서 정의하고 쇼룸 쪽을 `--showroom-accent`로 바꾸는 방식) 중 하나를 고르고 보고한다 — 쇼룸 모양이 바뀌면 안 된다.
- 글꼴: npm으로 `@fontsource/source-serif-4`와 `@fontsource/jetbrains-mono`를 추가해 필요한 굵기만(400·600) 불러온다(외부 글꼴 서버 호출 없음). Pretendard는 기존대로.

## 3. API 연결

| 파일 | 내용 |
|---|---|
| `src/vite-env.d.ts` | `interface ImportMetaEnv { readonly VITE_API_BASE?: string }` |
| `src/api.ts` (새) | `API_BASE = (import.meta.env.VITE_API_BASE \|\| "https://lg-cns-rag.vercel.app").replace(/\/+$/, "")`. `search(question: string, signal?: AbortSignal): Promise<SearchResponse>`, `health(): Promise<HealthResponse>`. 오류는 `ApiError { kind: "validation" \| "network" \| "timeout" \| "server" \| "shape"; message: string; status?: number }` |
| | 422 → `validation`, 메시지는 응답 `detail[0].msg`에서 앞의 `"Value error, "`만 뗀 서버 문구 그대로 |
| | `fetch`가 `TypeError` → `network` / `AbortError` → `timeout` / 5xx → `server`(상태 코드) / 응답 모양이 다름 → `shape` |
| | 응답 모양 최소 검사는 손으로 쓴 타입 가드(새 의존성 금지): 최상위 칸, 배열, 카드의 `campno`·`cause.status` 정도 |
| `src/search/types.ts` (새) | `server/api.py`의 Pydantic 모델을 TS로 옮긴다: `SearchResponse`(build_id, bundle_sha256: string\|null, snapshot_date, model, question, customer_precedents, precedents), `Card`(rank, campno, maker, maker_group: string\|null, received_date, components, defect, consequence, remedy, dup_group, source{dataset, snapshot_date, speaker}, cause, investigations, checklist), `Cause`는 `status`로 구분하는 유니온(`filled`·`stated_unknown` → text·speaker·source{campaign,file,pdf_sha256,submission_date,text_basis}·flags[{kind,label,spans[{start,end,text}]}] / `no_573_report` / `report_unreadable` → campaign·reason / 나머지 5종 → campaign / 모르는 값도 받는 형태), `Investigation`(action, speaker, subject, summary, open_date, close_date), `CheckItem`(item, label, evidence[{field,text}]), `HealthResponse`(build_id, bundle_sha256, snapshot_date, cards, model). **서버 코드는 바꾸지 않는다.** |

- 요청 본문은 `{"question": "..."}` 하나(서버가 모르는 칸을 422로 거부한다).
- 공개 API의 CORS는 지금 `http://localhost:5173`만 허용한다 → 로컬 개발은 기본 포트 5173으로. 다른 주소는 작업 F에서 연다.
- 로컬 API 서버로 붙일 때: `frontend/.env.development.local`에 `VITE_API_BASE=http://localhost:8000`(gitignore). `frontend/.env.example`을 새로 만들어 이름만 적는다(값 없이 주석으로 기본값 설명).

## 4. 화면 (설계 문서의 각 절을 그대로 구현)

| 컴포넌트(새 파일, `src/search/`) | 설계 정본 |
|---|---|
| `SearchView.tsx` — 화면 전체, 상태 `idle \| loading \| done \| error`, 들어올 때 `health()` 한 번 | [patterns/screens.md](../patterns/screens.md) |
| `SearchInput.tsx` — 입력·버튼·도움말·예시 질문 | [components/search-input.md](../components/search-input.md) — 예시 질문 4개는 그 문서 표의 문구·순서 그대로 |
| `Welcome.tsx` — 첫 화면(하는 일/하지 않는 일·데이터 판본·쇼룸 바로가기) | [patterns/screens.md](../patterns/screens.md) 1절, 문구는 [copy/ui-text.md](../copy/ui-text.md) |
| `ResultList.tsx`·`ListItem.tsx` | [components/result-list.md](../components/result-list.md) — 고객사 0건이면 구역 유지 + 안내 문구(결정 6) |
| `PrecedentDetail.tsx` — 순서: 머리 → 원문 → 원인 → 조사 → 확인 항목 → 출처 꼬리(결정 3) | [components/precedent-detail.md](../components/precedent-detail.md) |
| `CauseBlock.tsx`·`CauseBadge.tsx` | [components/cause.md](../components/cause.md) |
| `InvestigationBlock.tsx` | [components/investigation.md](../components/investigation.md) |
| `Checklist.tsx` | [components/checklist.md](../components/checklist.md) |
| `Provenance.tsx` — 출처 꼬리(결정 5) | [precedent-detail.md 출처 꼬리](../components/precedent-detail.md#출처-꼬리) |
| `Feedback.tsx` — 로딩·오류 4종+5xx·빈 결과 | [components/feedback.md](../components/feedback.md) |
| `causeStatus.ts` — 상태 → 단계(text/stated/none)·문구 | [copy/cause-status.md](../copy/cause-status.md) **문구 글자 그대로** |
| `highlight.ts` — 꼬리표 강조 조각 | [cause.md 꼬리표](../components/cause.md#꼬리표) |
| `fieldLabels.ts` — evidence `field` → 칸 라벨 | [components/checklist.md](../components/checklist.md) 표 |

**지켜야 할 세부**
- 원문 칸(결함·결과·시정·원인 text·조사 summary·checklist evidence text)은 `lang="en"`, `--font-source`, `white-space: pre-wrap`. 목록의 결함 원문은 CSS로 2줄 자르기만(문자열을 자르지 않는다).
- 날짜 `YYYYMMDD` → `YYYY.MM.DD` 표시만(값은 그대로). 조사 `close_date`가 빈 문자열이면 "기록 없음".
- `maker_group`이 `maker`와 다를 때만 함께 보인다.
- `bundle_sha256`이 `null`이면 "묶음 없음(로컬 파일로 띄운 서버)". sha256은 앞 12자 + `…`, 전체는 `title`.
- 573 PDF 링크를 만들지 않는다(주소 규칙 미확인 — 파일 이름만).
- 로딩: 3초 뒤 안내, `AbortController`로 60초에 끊음. 검색 중 버튼 "찾는 중…" 비활성. 오류가 나도 입력한 질문은 그대로.
- 입력: 영어 글자(`[A-Za-z]`)가 하나도 없으면 보내기 전에 안내, 1~4000자, 한글 조합 중 Enter 무시(`e.nativeEvent.isComposing`).
- 반응형([tokens/spacing.md](../tokens/spacing.md)): 768px 이상 2단(목록 300~380px), 767px 이하 한 단(목록 → 상세, "← 목록").
- 키보드: 목록 항목은 `button`, 초점 링 `--focus`, 탭은 `aria-pressed`.
- **판정 색·문구 금지**(빨강·초록·주황, "위험·안전·확정" 등). 오류 상자 왼쪽 띠도 `--ink-2`.

**`highlight.ts` 규칙(반드시)**
- `spans[].start/end`는 서버(Python)의 **코드포인트** 좌표 → `Array.from(text)`로 잘라야 한다.
- 잘라 낸 값이 `span.text`와 다르면 그 span은 강조하지 않는다. 겹치면 먼저 나온 것만.
- 반환한 조각을 이어 붙이면 **언제나 원문과 같아야** 한다. 같지 않으면 `[{ text }]` 하나로 돌려준다.
- 표시: `unknown_expression` → 점선 밑줄, `hedge_expression` → 물결 밑줄, 글자 색 그대로(`--flag-line`).

## 5. 시험 (vitest — 새 테스트 의존성 추가 없이)

**픽스처**: `src/search/__fixtures__/`
- `search_airbag.json`·`health.json` — `docs/design-system/mockup.html`의 `<script type="application/json" id="data-search">`·`id="data-health"` 내용을 **그대로** 옮긴다(2026-10-13 공개 API 응답, "airbag inflator rupture during deployment"). 고객사 2건·filled·stated_unknown·no_573_report·report_unreadable·꼬리표 3개·조사 연결 카드가 들어 있다.
- `cause_statuses_synthetic.json` — 응답에 없는 상태(`report_status_unknown`·`version_unresolved`·`cause_empty`·`cause_no_field`·`verify_failed`·모르는 값)만 모은 **합성** 카드. 파일 이름과 `__fixtures__/README.md`에 "합성 — 형식 확인용"이라고 적는다.
- 네트워크가 되면 예시 질문 4개의 실제 응답을 더 받아 둬도 된다(받은 날짜·build_id를 README에).

| 시험 파일 | 확인할 것 |
|---|---|
| `causeStatus.test.ts` | 상태 10가지(9종 + 모르는 값) 모두 문구가 있고 `copy/cause-status.md` 표와 글자까지 같다 · campaign·reason이 들어간다 · 단계 매핑(filled→text, stated_unknown→stated, 나머지→none) |
| `highlight.test.ts` | 이어 붙이면 원문과 같다(픽스처의 모든 원인 글) · 비-BMP 문자(예: 😀)와 U+0092가 앞에 있을 때 좌표가 맞다 · 어긋난 span은 강조하지 않는다 · 겹치는 span |
| `api.test.ts` | `globalThis.fetch`를 흉내 내서: 422 메시지 추출, TypeError → network, abort → timeout, 500 → server, 모양 다름 → shape, 정상 응답 통과 |
| `render.test.tsx` | `react-dom/server`의 `renderToStaticMarkup`으로 픽스처를 그려: 원문 세 칸·원인 text·조사 summary가 (HTML 이스케이프한) 원문 그대로 들어 있다 · campno·speaker·text_basis·build_id가 보인다 · 고객사 0건 문구 |
| `principles.test.ts` | ① 렌더 결과 ② `src/**/*.{ts,tsx}` 소스 문자열에 판정 패턴이 0건: `/applies|verdict|is_?applicable|recall[_\s-]?required|리콜\s*대상(입니다|이다)|원인은\s.{0,30}입니다|해당(합니다|됩니다|되지\s*않습니다)|적용(됩니다|되지\s*않습니다)/` — 시험 파일 자신과 주석 설명은 제외 |

## 6. 기록

- `.agent/DECISIONS.md` **DEC-053**: 검색 전용 화면(해시로 쇼룸과 전환, 쇼룸은 lazy), `VITE_API_BASE` 기본값 = 공개 API, 원인 상태 문구 잠정안(정본 `docs/design-system/copy/cause-status.md`), 글꼴 번들 방식, `--accent` 충돌 처리 방식. 서버 응답 계약은 바꾸지 않음.
- `.agent/HANDOFF.md`: 할 일 50(화면↔API 연결)을 완료로(목록에서 지우지 말고 "[완료 날짜 — PR 번호]"), Next Action 1을 "작업 F"로. `SESSION_LOG.md` 한 줄.
- `frontend/README.md`: 검색 화면, `VITE_API_BASE`, CORS(5173), 픽스처 갱신 방법.
- 이슈 #53에 문구 표를 올리는 일은 사람이 한다(보고에 "할 것"으로 적기).

## 7. 검증

```bash
cd frontend && npm ci && npm run lint && npm run build && npm test
cd .. && uv run ruff check . && uv run ruff format --check . && uv run pytest
```

가능하면 수동 확인(`npm run dev`, http://localhost:5173):
1. 첫 화면: 예시 질문 4개, 판본(카드 30,350장 · 스냅샷 2026-10-06)
2. 예시 질문 `electric power steering assist loss` → 고객사 구역에 24V412000이 있고 원인 원문 "Contaminated solder flux…"(HL Mando)가 보이는지
3. 한글만 입력 → 보내기 전 안내 / 서버 422 문구
4. `VITE_API_BASE=http://localhost:1` → 연결 실패 오류
5. `#showroom` → `.glb` 없을 때 실패 안내 → "검색 화면으로"
6. 쇼룸에서 "이 분류로 선례 검색" → 질문 칸만 채워짐(자동 검색 안 함)
7. 모바일 폭(390px)에서 목록 → 상세 → "← 목록"
8. 빌드 결과에서 검색 화면 첫 묶음에 three.js가 없는지(`npm run build` 출력의 청크 크기)

## 8. PR

제목 예: `feat: 검색 전용 화면과 공개 API 연동`. 본문 "검증 방법"에 프런트 4개 명령 결과(테스트 수), 수동 확인 결과(위 1~8), 빌드 청크 크기를 적는다. 검색 품질 코드는 바꾸지 않으므로 G-08은 "해당 없음(서버 변경 없음)". 관련 이슈 `Refs #53 · Refs #60`. 병합하지 않는다.

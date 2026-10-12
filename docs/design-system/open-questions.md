# 결정 기록 — 열린 질문 (v1.0에서 모두 결정)

v0.1의 열린 질문 6개와 이어진 질문 2개를 디자인 인터뷰(우지훈, 2026-10-13)로 정했다. 결정은 해당 문서에 반영했다.

| # | 질문 | 결정 | 반영 |
|---|---|---|---|
| 1 | 쇼룸에서 부품 분류를 누르면 검색으로 이어 줄까? | **버튼으로 질문만 채움** — 쇼룸 패널에 "이 분류로 선례 검색" 버튼, 누르면 검색 화면으로 옮겨 분류 영어 이름(예: *air bag*)을 질문 칸에 채운다. 자동 검색은 하지 않고 사용자가 고쳐 보낸다 | [patterns/screens.md](patterns/screens.md#5-쇼룸-연결) |
| 2 | 예시 질문 | **고객사(현대·기아) 선례가 나오는 질문 위주** — 아래 기준으로 공개 API에 후보 16개를 돌려 4개를 골랐다 | [components/search-input.md](components/search-input.md#예시-질문-첫-화면) |
| 3 | 상세 패널 순서 | **원문 먼저** — 머리 → 결함·결과·시정 원문 → Part 573 원인 → NHTSA 조사 → 확인 항목 → 출처 꼬리 | [components/precedent-detail.md](components/precedent-detail.md) |
| 4 | 원문 글꼴 | **세리프(Source Serif 4) + 쇼룸도 맞춤** — 두 화면 모두 원문은 `--font-source` | [tokens/typography.md](tokens/typography.md) |
| 5 | 판본 정보 범위 | **상단 요약 + 결과 아래 꼬리** — 상단 바에 카드 수·스냅샷, 상세 맨 아래 출처 꼬리에 build·묶음 sha256 앞 12자·스냅샷·모델·질문(전체 값은 마우스를 올리면). 접지 않는다 | [components/app-bar.md](components/app-bar.md) · [precedent-detail.md](components/precedent-detail.md#출처-꼬리) |
| 6 | 고객사 선례 0건 | **구역 유지 + 안내 문구** — "검색 상위 100건 안에 현대·기아 리콜이 없습니다" | [components/result-list.md](components/result-list.md) |
| 7 | 예시 질문 고르는 기준 | **네 가지 모두**: 고객사 선례 1건 이상 · 고객사 선례 중 원인 원문(`filled`) 카드 포함 · 부품 분야가 겹치지 않게 · 시험지 749문항과 겹치지 않게 | [components/search-input.md](components/search-input.md#예시-질문-첫-화면) |
| 8 | 쇼룸 `--ink-3`(`#8c94a1`, 3.06:1)도 맞출까? | **맞춤** — #60 정리(PR D) 때 쇼룸 `styles.css`의 `--ink-3`을 `#636b78`로(투시 모드 어두운 테마 값은 그대로) | [tokens/colors.md](tokens/colors.md) |

## 예시 질문 후보 실행 기록 (2026-10-13, 공개 API, build `f1fe1843ed0f2c66`)

| 질문 | 고객사 선례 | 원인 원문 있는 고객사 카드 | 결과 |
|---|---|---|---|
| electric power steering assist loss | 4 | 24V422000 · 24V412000 | **채택**(조향 — 24V412000은 기획서 573 원문 예 HL Mando MDPS) |
| engine connecting rod bearing failure | 5 | 21V844000 · 19V120000 · 21V727000 · 20V746000 | **채택**(엔진) |
| electrical short in the ABS module may cause fire | 5 | 5건 모두 | **채택**(브레이크·전기) |
| airbag inflator rupture during deployment | 2 | 26V307000 | **채택**(에어백 — 목업 응답과 같은 질문) |
| seat belt pretensioner does not activate | 5 | 5건 모두 | 예비(안전벨트) |
| rearview camera image does not display | 5 | 5건 모두 | 탈락 — 분야 수 제한(4개) |
| brake booster vacuum hose cracks | 3 | 2건 | 탈락 — ABS 질문과 브레이크 분야 겹침 |
| sunroof glass may detach | 3 | 1건 | 탈락 — 분야 수 제한 |
| steering column lock fails to release | 1 | 1건 | 탈락 — 조향 분야 겹침 |
| transmission shifts to neutral unexpectedly | 1 | 1건 | 탈락 — 분야 수 제한 |
| driver airbag may not deploy in a crash | 5 | 0 | 탈락 — 원인 원문 카드 없음 |
| brake fluid leaking from front caliper | 1 | 0 | 탈락 — 원인 원문 카드 없음 |
| fuel pump stops while driving | 3 | 0 | 탈락 — 원인 원문 카드 없음 |
| fuel leak from fuel tank strap | 2 | 0 | 탈락 — 원인 원문 카드 없음 |
| headlamp fails due to wiring short | 1 | 0 | 탈락 — 원인 원문 카드 없음 |
| tire tread separation | 0 | — | 탈락 — 시험지 질문에 포함, 고객사 선례 없음 |

시험지 겹침은 후보 문구가 `data/processed/defect/eval.jsonl`의 질문 안에 그대로 들어 있는지(대소문자 무시)로 확인했다. 결과는 서버 판본·CPU에 따라 순서가 조금 달라질 수 있다(DEC-051 ③) — 구현 PR에서 같은 기준으로 다시 확인한다.

## 이 폴더 밖에서 정할 것

- `report_unreadable` 사유 코드의 한국어 풀이, 원인 칸 없는 카드 문구 — 이슈 #53.
- "원인을 말한 주체" 확인 항목이 "NR" 카드에도 붙는 문제 — 이슈 #84.
- 미보고 판별 경계(`filled`인데 미보고 표현인 글) — 이슈 #83.

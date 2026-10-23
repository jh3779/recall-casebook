# 디자인 시스템 — 결함 선례 찾기 도우미 화면 (v1.0, 2026-10-13)

> **검색 전용 화면**(질문 → 선례·원인 원문)과 3D 쇼룸(PR #60)이 함께 쓰는 디자인 기준이다. 구현 PR(검색 화면 + API 연동)은 이 폴더를 기준으로 만든다.
> 동작하는 목업은 [`mockup.html`](mockup.html) — 내려받아 브라우저로 연다. 목업의 영어 원문과 번호는 공개 API(`https://lg-cns-rag.vercel.app`)가 2026-10-13에 돌려준 응답(`POST /search` "airbag inflator rupture during deployment", `GET /health` build `f1fe1843ed0f2c66`)을 그대로 그렸다.
> 상태: **v1.0 확정** — 열린 질문 6개와 이어진 질문 2개를 인터뷰로 정했다([결정 기록](open-questions.md)). 바꿀 때는 결정 기록에 날짜·이유를 남기고 판을 올린다.
> **시점 표시(2026-10-23, 이슈 #165)**: 이 폴더의 `components/`·`patterns/`가 그리는 "검색 화면"은 옛 한국어 선례 검색 화면(`#search`)이다. 그 화면은 DEC-075(2026-10-18)로 케이스북(`#casebook`, 영어 UI)에 합쳐져 지워졌고 앱 바는 케이스북·3D 쇼룸 탭만 남는다(`app-bar.md`·`screens.md`·`feedback.md`의 서술은 당시 설계). 케이스북 화면 자체의 컴포넌트·화면 구성 기록은 이 폴더에 없다(색 토큰만 `tokens/colors.md`에 케이스북 언급이 있다) — 케이스북 기준으로 갱신할지는 정하지 않았다.

## 폴더 구성

| 파일 | 내용 |
|---|---|
| [principles.md](principles.md) | 화면이 지키는 서비스 원칙(AGENTS.md 2절)과 그 원칙을 지키는 컴포넌트 |
| [tokens/colors.md](tokens/colors.md) | 색 토큰·의미 색(원인 3단계·꼬리표)·대비 수치 |
| [tokens/typography.md](tokens/typography.md) | 글꼴 3종·크기 단계·원문 조판 |
| [tokens/spacing.md](tokens/spacing.md) | 간격·모서리·그림자·초점·반응형 기준 |
| [tokens/tokens.css](tokens/tokens.css) | 위 토큰을 CSS 변수로 — 구현 때 그대로 가져다 쓴다 |
| [components/app-bar.md](components/app-bar.md) | 상단 바·화면 전환·서버 판본 표시 |
| [components/search-input.md](components/search-input.md) | 검색 입력·예시 질문 |
| [components/result-list.md](components/result-list.md) | 목록 구역·목록 항목·부품 칩 |
| [components/precedent-detail.md](components/precedent-detail.md) | 상세 패널 머리·원문 블록·출처 꼬리 |
| [components/cause.md](components/cause.md) | 원인 상태 배지·원인 블록 9종·꼬리표 |
| [components/investigation.md](components/investigation.md) | NHTSA 조사 블록 |
| [components/checklist.md](components/checklist.md) | 확인 항목 |
| [components/feedback.md](components/feedback.md) | 로딩·오류(옛 한국어 화면 5종 + 현재 케이스북 429)·빈 결과 |
| [patterns/screens.md](patterns/screens.md) | 화면 구성 — 첫 화면·결과(데스크톱)·모바일·쇼룸 연결 |
| [copy/cause-status.md](copy/cause-status.md) | 원인 상태 문구(잠정 — 이슈 #53에 올릴 안) |
| [copy/ui-text.md](copy/ui-text.md) | 라벨·안내·버튼 문구 모음 |
| [open-questions.md](open-questions.md) | 결정 기록(열린 질문 8개) · 예시 질문 후보 실행 기록 |
| [mockup.html](mockup.html) | 토큰 견본·컴포넌트·화면 목업(실제 API 응답) |
| [codex/](../archive/design-system-codex/README.md) | 구현 지시문(Codex용) — 공통 규칙 + 작업 D(#60 정리)·E(검색 화면)·F(화면 배포). 세 작업 모두 끝나 `docs/archive/`로 옮겼다 |

## 인터뷰로 정한 것 (우지훈, 2026-10-13)

| 항목 | 결정 |
|---|---|
| 분위기 | 쇼룸과 같은 톤(Pretendard, 유리 패널, 둥근 모서리). 글이 많아 유리 효과는 줄이고 밝은 배경 위주 |
| 강조색 | 남색(`--accent #1f3a68`). 쇼룸 주황 `#ff5a1f`은 쇼룸 안에만 — 경고색을 쓰지 않아 판정 인상을 줄인다 |
| 레이아웃 | 목록 + 오른쪽 상세 패널. 1280px 이상 2단, 모바일 390px는 한 단(목록 → 상세) |
| UI 언어 | 한국어. 원문 칸은 영어 원문 그대로 |
| 원인 상태 | 중립 3단계 — 원문 있음 / 미보고·조사 중 표현 / 원문 없음. 색만으로 구분하지 않고 점 모양과 문구를 함께 |
| 꼬리표 | 밑줄 + 배지 — 원인 미확인 표현은 점선, 추정 표현은 물결. 글자 색은 그대로 |
| 출처 | 원문 블록마다 머리줄(말한 주체 · 번호) 항상, 파일·sha256·text_basis·제출일은 "출처 자세히"로 펼침 |
| 첫 화면 | 예시 질문 · 이 도구가 하는 일/하지 않는 일 · 데이터 판본(`/health`) · 쇼룸 바로가기 |
| 고객사 구역 | 목록 맨 위 별도 구역 + "다른 회사 선례". 항목마다 전체 순위 rank |
| 테마 | 밝은 테마만 |

같은 날 정한 진행 방식: #60 정리·병합과 API 연동은 우지훈이 맡는다, 3D 모델 재배포 허용(`.glb`는 박성호 님께 받음), 로컬 시연 + 화면도 Vercel 배포, 구현 전에 설계를 먼저 한다.

## 근거

`server/api.py` 응답 모델(`SearchResponse`·`Card`·`Cause*`·`Investigation`·`CheckItem`) · `server/README.md` 응답 표 · DEC-042 ③·DEC-044·DEC-047·DEC-051 · PR #60 `frontend/src/styles.css` · 인터뷰 결정(2026-10-13). 진행 순서는 `.agent/HANDOFF.md` Next Action 1.

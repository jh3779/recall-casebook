# 글꼴

## 글꼴 3종

| 토큰 | 글꼴 | 쓰는 곳 | 이유 |
|---|---|---|---|
| `--font-ui` | Pretendard Variable (쇼룸이 npm `pretendard`로 번들) → 대체 Noto Sans KR → 시스템 | 화면 글 전부(라벨·안내·버튼·한국어 문구) | 쇼룸과 같은 글꼴로 한 제품처럼 보이게 |
| `--font-source` | Source Serif 4 → Georgia → Times New Roman | **원문**(결함·결과·시정·원인·조사 요약), 검색 입력, 예시 질문 | 인용한 1차 자료를 화면 글과 한눈에 구별(제안 — [열린 질문 4](../open-questions.md)) |
| `--font-id` | JetBrains Mono → ui-monospace → Consolas | 리콜 번호·조사 번호·캠페인·build_id·sha256·부품 칩·출처 값 | 번호를 정확히 읽고 비교 |

구현에서는 Pretendard를 지금처럼 번들하고, Source Serif 4·JetBrains Mono는 npm(`@fontsource/*`) 번들 또는 시스템 대체 중 하나를 PR E에서 정한다(외부 글꼴 서버 호출을 늘리지 않는 쪽 권장). `mockup.html`은 Pretendard를 불러올 수 없어 Noto Sans KR로 보인다.

## 크기 단계

| 토큰 | 크기 | 굵기 | 쓰는 곳 |
|---|---|---|---|
| `--fs-xs` | 12px | 400–600 | 보조 라벨·바이라인·도움말·판본 정보 |
| `--fs-s` | 13px | 400–600 | 목록 항목·표·확인 항목 |
| `--fs-m` | 14px | 400 / 700(블록 제목) | 본문 기본 |
| `--fs-l` | 16px | 400 | 검색 입력 |
| `--fs-xl` | 20px | 600 | 상세 머리의 리콜 번호 |
| `--fs-2xl` | 28px | 700 | (문서 제목용, 앱 화면에서는 쓰지 않음) |
| `--fs-source` | 15px | 400 | 원문 블록 |

11px은 배지·칩·라벨(대문자 간격 0.04em)에만 쓰고 본문에는 쓰지 않는다.

## 원문 조판

- `font-family: var(--font-source)`, `font-size: var(--fs-source)`, `line-height: 1.65`, `max-width: 72ch`.
- `white-space: pre-wrap` — 원문의 줄바꿈·공백을 그대로 보인다(서버가 이미 공백을 정리했다 — `text_basis`).
- `overflow-wrap: anywhere` — 긴 번호·URL이 칸을 밀지 않게.
- `lang="en"` — 원문 요소에 붙여 읽기 프로그램·하이픈 처리가 영어로 동작하게.
- 대소문자·문장부호를 바꾸지 않는다. 대문자뿐인 옛 리콜 문장(예: "HYUNDAI IS RECALLING …")도 그대로.
- 보이지 않는 제어 문자(예: `14V614000`의 `\u0092`)도 원문이므로 지우지 않는다.

## 숫자

날짜·건수·순위처럼 줄 맞춤이 필요한 숫자는 `font-variant-numeric: tabular-nums`. 날짜는 서버의 `YYYYMMDD`를 `YYYY.MM.DD`로만 바꿔 보인다(값은 그대로).

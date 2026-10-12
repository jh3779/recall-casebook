# 결과 목록 (왼쪽)

## 목록 패널

`--glass` 바탕, 안쪽 12px, 항목 사이 6px, 오른쪽 구분선 `--line`. 데스크톱 폭 300~380px, 길면 패널 안에서 세로 스크롤.

## 구역 제목

| 구역 | 제목 | 부제(`--fs-xs`, `--ink-3`) | 데이터 |
|---|---|---|---|
| 1 | 고객사 선례 · 현대·기아 | 합친 순위 상위 100 안에서 최대 5건 | `customer_precedents` |
| 2 | 다른 회사 선례 | 합친 순위 상위 10건 | `precedents` |

고객사 선례가 0건이면 구역을 숨기지 않고 "검색 상위 100건 안에 현대·기아 리콜이 없습니다"를 보인다(찾아봤다는 사실을 남김 — [열린 질문 6](../open-questions.md)).

## 목록 항목

```
#15  26V307000  Hyundai Motor America                2026.05.14
Hyundai Motor America (Hyundai) is recalling certain 2015-2016 Elantra…   ← 결함 원문 첫 2줄
[AIR BAGS:FRONTAL:DRIVER SIDE:INFLATOR MODULE]  (● 원인 원문 있음)  [NHTSA 조사 1]
```

| 요소 | 사양 |
|---|---|
| 순위 | `#{rank}` — 두 구역이 함께 쓰는 합친 순위. `--font-id` 11px `--ink-3` |
| 리콜 번호 | `campno`, `--font-id` 굵게 |
| 회사 | `maker`. `maker_group`이 다르면 `maker · maker_group` |
| 접수일 | `received_date` → `YYYY.MM.DD`, 오른쪽 끝, tabular-nums |
| 결함 원문 | `defect` 첫 2줄을 자르기만(`-webkit-line-clamp: 2`), `--font-source` 13px, `lang="en"` |
| 부품 칩 | `components` 앞 2개 + 나머지는 `+n`. `--font-id` 11px, `--surface-2` 바탕, 모서리 6px, 원문 그대로(대문자·콜론 포함) |
| 원인 상태 | [원인 상태 배지](cause.md) 3단계 |
| 조사 연결 | `investigations`가 있으면 "NHTSA 조사 {n}" 회색 알약 |

| 상태 | 모양 |
|---|---|
| 일반 | 흰 바탕, 테두리 없음 |
| hover | `--line-strong` 테두리 |
| 선택 | `--accent` 테두리 + 왼쪽 안쪽 3px 남색 띠 |
| 초점 | `--focus` |

항목 전체가 `button`이다. 누르면 오른쪽 상세가 바뀌고(데스크톱) 상세 화면으로 넘어간다(모바일).

## 첫 선택

결과가 오면 첫 항목(고객사 선례가 있으면 그 첫 항목)을 선택한 상태로 연다.

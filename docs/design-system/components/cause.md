# 원인 (Part 573) — 상태 배지 · 원인 블록 · 꼬리표

서버 `cause`는 `status`로 갈리는 다섯 모델 중 하나다(`server/api.py` `CauseText`·`CauseStated`·`CauseNoReport`·`CauseUnreadable`·`CauseMissingText`). 화면은 이를 **3단계**로 묶어 보이고, 단계는 "글이 있는가"만 뜻한다. 문구는 [copy/cause-status.md](../copy/cause-status.md).

## 상태 배지 (목록 항목·블록 제목)

| 단계 | 상태 값 | 배지 | 모양 |
|---|---|---|---|
| 원인 원문 있음 | `filled` | ● 원인 원문 있음 | 남색 실선 1.5px 테두리, 채운 점, 남색 글자 |
| 미보고·조사 중 표현 | `stated_unknown` | ◐ 미보고·조사 중 표현 | `--cause-stated-bg` 바탕 + 실선, 반 점, `--ink-2` 글자 |
| 원인 원문 없음 | `no_573_report` · `report_unreadable` · `report_status_unknown` · `version_unresolved` · `cause_empty` · `cause_no_field` · `verify_failed` · (모르는 값) | ○ 원인 원문 없음 | 회색 점선 1.5px, 빈 점, `--ink-2` 글자 |

11px 굵게, 알약 모양. 색만으로 구분하지 않는다(점 모양·선 모양·문구).

## 원인 블록

제목 "원인 (Part 573)" + 상태 배지. 블록 테두리도 단계를 따른다(실선 남색 / 연회색 바탕 / 회색 점선).

### 원문이 있는 상태 (`filled`, `stated_unknown`)

1. 바이라인: `말한 주체 **리콜 제조사 (Part 573 결함·불합치 보고서)** · 캠페인 {campaign}`
2. 꼬리표가 있으면 꼬리표 배지 줄 + 도움말 "글에 이 표현이 있다는 표시이며 판단이 아닙니다"
3. 원문(`--font-source`, 꼬리표 위치만 밑줄)
4. `stated_unknown`이면 원문 아래 상태 문구(`--fs-s`, `--ink-2`): "원인 서술 대신 미보고·조사 중 등의 표현으로 시작하는 글로 분류됐습니다(DEC-047). 원인을 모른다는 뜻으로 단정하지 않습니다."
5. [출처 자세히](precedent-detail.md#출처-자세히)

`stated_unknown` 중에도 뒤에 실제 원인이 이어지는 글이 있다(예: 26V219 "UNCLEAR WORK INSTRUCTION…") — 그래서 원문을 항상 보인다. 반대로 `filled`인데 미보고 표현인 글도 있다(예: 14E073000 "The cause is under investigation", #83).

### 원문이 없는 상태 (7종 + 모르는 값)

상태 문구 한 줄만(`--fs-s`, `--ink-2`). `campaign`·`reason`은 서버 값을 그대로 끼운다. 빈칸이나 "-"를 보이지 않는다.

## 꼬리표

서버 `flags[]`는 573 원인 글에만 붙는다(조사 요약에는 없음 — DEC-044).

| kind | 서버 label | 원문 표시 | 배지 |
|---|---|---|---|
| `unknown_expression` | 원인 미확인 표현 있음 | 해당 단어에 **점선** 밑줄(2px, `--flag-line`, 밑줄 간격 3px) | 점선 그림 + label |
| `hedge_expression` | 추정 표현 있음 | **물결** 밑줄 | 물결 그림 + label |

규칙:
- 글자 색·굵기·배경을 바꾸지 않는다 — 밑줄만(형광펜은 "중요한 부분"으로 읽혀 판단처럼 보인다).
- 배지와 밑줄에 `title` "원인 미확인 표현" / "추정 표현".
- 추정 표현 목록은 `appear(s/ed) to`·`might`·`possibly`·`likely`·`probably`·`suspect(ed)`·`believe(d)`(may·could는 서버가 뺐다 — `server/README.md`).

### 강조 조각 만드는 법 (구현 규칙)

- `spans[].start/end`는 서버(Python)의 **코드포인트** 좌표다 → `Array.from(text)`로 잘라야 한다(JS 문자열 인덱스는 UTF-16이라 다를 수 있음).
- 잘라 낸 값이 `span.text`와 다르면 그 span은 강조하지 않는다(배지는 남김).
- 겹치는 span은 먼저 나온 것만.
- 조각을 이어 붙이면 언제나 원문과 같아야 한다 — 같지 않으면 강조 없이 원문만 보인다.

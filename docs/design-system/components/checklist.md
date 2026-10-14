# 확인 항목

서버 `checklist[]` — `{item, label, evidence[{field, text}]}`. 근거가 없는 항목은 서버가 싣지 않는다(`server/rag/checks.py`). 화면은 **같다·다르다를 표시하지 않고** 근거 원문만 나란히 둔다(원칙 1).

## 구성

제목 "확인 항목" + 도움말 "근거 원문을 나란히 보여 줄 뿐, 같다·다르다를 표시하지 않습니다". 항목마다 2열:

| 왼쪽(120px) | 오른쪽 |
|---|---|
| 서버 `label` 그대로(굵게) | 근거 줄들: 칸 라벨(`--fs-xs`, `--ink-3`, 96px) + 근거 원문(`--font-source`, `white-space: pre-wrap`, 최대 3줄로 자르기만 — 연속 공백·줄바꿈을 원문대로) |

항목 사이 점선. 모바일은 한 열로 쌓는다.

## 서버 항목과 칸 라벨

| item | label (서버) | evidence field → 화면 칸 라벨 |
|---|---|---|
| `same_part` | 같은 부품 | `components` → 부품 |
| `production_period` | 생산 기간 | `573.production_dates` → 573 생산 기간 칸 (블록마다 `머리글 | 원문`, 앞 5개만 싣고 나머지는 `omitted`로 "외 N개", `source`의 보고서 파일·제출일·sha256을 "출처 보고서" 줄로 보임) |
| `failure_mode` | 고장 양상 | `defect` → 결함, `consequence` → 결과 |
| `remedy` | 시정 | `remedy` → 시정 |
| `supplier` | 공급사 | `573.supplier_names` → 573 공급사 칸 |
| `cause_speaker` | 원인을 말한 주체 | `cause.speaker` → 원인을 말한 주체, `investigations.speaker` → 조사 요약을 말한 주체, `investigations.action` → 조사 번호 |

모르는 field는 field 이름을 그대로 보인다(서버 항목이 늘어도 깨지지 않게).

## 하지 않는 것

- 체크 표시(✓/✗), 일치율, 색 구분.
- 사용자 질문과 근거를 자동 비교한 결과.
- "원인을 말한 주체" 항목이 원인 글이 "NR"인 카드에도 붙는 문제는 #84 마지막 항목에서 정한다 — 화면은 서버 값을 그대로 보인다.

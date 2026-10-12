# 검색 입력 · 예시 질문

## 검색 입력

| 요소 | 사양 |
|---|---|
| 칸 | 흰 바탕, 1.5px `--line-strong` 테두리, 모서리 `--radius-s`. 초점이 들어가면 테두리 `--accent-2` + `--focus` |
| 왼쪽 표시 | "EN" (11px, 굵게, `--ink-3`) — 영어로 쓰는 칸임을 알림 |
| 입력 글 | `--font-source`, `--fs-l`, `lang="en"` |
| 자리 표시 글 | "결함 서술을 영어로 — 예: brake fluid leaking from front caliper" |
| 버튼 | "선례 찾기" — 남색 주 버튼(높이 46px) |
| 아래 도움말 줄 | "영어 질문만 받습니다" · "고객사(현대·기아) 최대 5건 + 다른 회사 상위 10건" · "{n} / 4000자" (`--fs-xs`, `--ink-3`) |

## 입력 규칙 (서버 `SearchRequest`와 같게)

| 경우 | 화면 동작 |
|---|---|
| 빈 값·공백만 | 버튼 비활성 |
| 영어 글자가 하나도 없음(예: 한글만, 숫자만) | 보내기 전에 도움말 줄에 남색 굵게 "영어 단어가 없습니다" — 서버도 422로 거부한다 |
| 4000자 초과 | 입력 막음, 글자 수를 남색으로 |
| 보냄 | 앞뒤 공백은 서버가 지운다. 화면은 받은 응답의 `question`을 출처 꼬리에 그대로 보인다 |
| Enter | 보내기(한글 조합 중 Enter는 무시) |

## 예시 질문 (첫 화면)

알약 버튼(`--radius-pill`, `--font-source`, 흰 바탕·`--line-strong` 테두리). 누르면 칸에 채우고 바로 검색한다.

제안 문구(시험지 749문항의 질문은 쓰지 않음 — 구현 때 기계로 겹침 확인):
- `brake fluid leaking from front caliper`
- `airbag inflator rupture during deployment`
- `steering column lock fails to release`
- `fuel pump stops while driving`

확정은 [열린 질문 2](../open-questions.md).

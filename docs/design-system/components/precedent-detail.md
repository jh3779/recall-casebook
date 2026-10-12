# 선례 상세 (오른쪽 패널)

순서(결정 2026-10-13 — 원문 먼저): **머리 → 결함·결과·시정 원문 → [원인(Part 573)](cause.md) → [NHTSA 조사](investigation.md) → [확인 항목](checklist.md) → 출처 꼬리**. 블록 사이 18px, 패널 안쪽 22~26px, 바탕 `--bg-1`.

## 머리

| 요소 | 사양 |
|---|---|
| 전체 순위 | 회색 알약 "전체 순위 {rank}" |
| 리콜 번호 | `campno`, `--font-id` `--fs-xl` 굵게 |
| 회사 | `maker`, `maker_group`이 다르면 `maker (maker_group)` — `--ink-2` |
| 접수일 | "접수 YYYY.MM.DD" |
| 부품 | `components` 전부 칩으로 |

모바일은 맨 위에 "← 목록" 버튼(흰 바탕 남색 글자).

## 블록 공통

흰 바탕, 1px `--line`, 모서리 `--radius-s`, 안쪽 16px 18px. 제목 줄 = 블록 제목(14px 굵게) + 배지들.

## 바이라인 (말한 주체)

모든 원문 블록의 제목 아래 한 줄: `말한 주체 **{speaker}** · {번호}` (`--fs-xs`, `--ink-2`, speaker만 `--ink` 굵게). speaker는 서버 값을 그대로 쓰고 화면이 바꾸거나 줄이지 않는다.

| 블록 | speaker (서버 고정값) | 번호 |
|---|---|---|
| 결함·결과·시정 | `NHTSA 리콜 기록 요약(FLAT_RCL 결함·결과·시정 칸) — 원본에 작성 주체 표시 없음` | `NHTSA FLAT_RCL 스냅샷 {snapshot_date}` |
| 원인 | `리콜 제조사 (Part 573 결함·불합치 보고서)` | `캠페인 {campaign}` |
| 조사 | `NHTSA 결함 조사 (조사관 요약)` | 조사 번호 `action` |

카드 원문에 "제조사"라고 따로 붙이지 않는다(DEC-047 ③ — 원본에 작성 주체 표시가 없다).

## 결함 · 결과 · 시정 블록

제목 "결함 · 결과 · 시정 (NHTSA 원문)". 칸마다 라벨(11px 굵게 `--ink-3`) "결함" / "결과" / "시정" + 원문(`--font-source` 15px, 줄간격 1.65, `pre-wrap`, `lang="en"`). 세 칸 모두 펼쳐 둔다(목록에서 이미 줄였으므로).

## 출처 자세히

원인 블록 아래 `details`: 요약 줄 "＋ 출처 자세히"(`--accent-2`, 12px 굵게). 펼치면 2열 표(`--font-id` 12px):

| 라벨 | 값 |
|---|---|
| 파일 | `cause.source.file` (예: `odi/rcl/2014/RCLRPT-14E073-0222.pdf`) |
| pdf_sha256 | 전체 64자 |
| 제출일 | `submission_date` → YYYY.MM.DD |
| 글 정리 방식 | `text_basis` 그대로 (예: `rclrpt-2026-10-12b; pdftotext-layout; page-header-footer-removed; whitespace-collapsed`) |

573 PDF로 가는 링크는 만들지 않는다 — 공개 주소 규칙을 확인하지 못했다(짐작해 만들지 않음, 원칙 3). 파일 이름만 보인다.

## 출처 꼬리

상세 맨 아래, 위쪽 구분선, `--font-id` 11px `--ink-3`, 한 줄씩 감싸기:
`build {build_id} · 묶음 {bundle_sha256 앞 12자}… · 스냅샷 {snapshot_date} · 모델 {model} · 질문 {question}`
- `bundle_sha256`이 `null`이면 "묶음 없음(로컬 파일로 띄운 서버)".
- 묶음 전체 sha256은 `title`(마우스를 올리면).
- 응답 하나에 한 번 — 카드마다 같은 값이다.

# 작업 D — PR #60 정리 (쇼룸 화면을 main에 넣을 수 있게)

> **실행 완료된 기록(2026-10-13)** — 이 작업은 PR #105로 구현됐다(#60은 #105로 대체·닫힘). 아래 브랜치·시작 조건은 당시 계획이며 **다시 실행하지 않는다.** 남은 일은 #105 리뷰에서 처리한다.

> 먼저 [README.md](README.md)(공통 규칙)를 읽는다.

## 배경

PR #60(`feat/frontend-showroom`, 박성호 작성, 커밋 `5be42cb` 하나)은 3D 쇼룸 화면을 `frontend/`에 React로 옮긴 PR이다. 10/9 이후 작성자 응답이 없어 **2026-10-13 우지훈이 정리·병합을 맡기로** 했다(사용자 결정). 이 작업은 #60 브랜치에 **새 커밋을 더해** 병합할 수 있게 만든다. 박성호 님 커밋은 그대로 둔다.

병합을 막고 있는 것:
1. main과 `.agent/` 세 파일 충돌(화면 코드는 충돌 없음)
2. 데모 데이터 `frontend/public/data/recalls.json`의 깨진 글자(원칙 2 위반)
3. 리뷰가 지적한 문구(합계 대수·"같은 부품, 다른 회사 선례"·"결함 부품")와 차종 탭에 섞인 리콜
4. 3D 모델 출처·재배포 근거·받는 방법이 문서에 없음

## 0. 준비

```bash
git fetch origin
git switch feat/frontend-showroom      # 없으면: git switch -c feat/frontend-showroom origin/feat/frontend-showroom
git log --oneline -3                   # 5be42cb가 맨 위인지 확인
```

## 1. main 합치기 — 충돌 해결 (커밋 1)

`git merge origin/main` (rebase 금지). 충돌은 `.agent/` 세 파일에만 난다.

**`.agent/DECISIONS.md`**
- main 쪽 273줄 부근의 자리 표시 줄 `> DEC-041은 PR #60(화면 — React `frontend/`)이 쓸 예정이라 비워 둔다.`를 **#60의 `## DEC-041` 절 전체로 바꾼다**(DEC-040과 DEC-042 사이에 오게).
- #60의 DEC-041 안에 있는 "번호 메모"(DEC-041 번호를 어떻게 정했는지 적은 줄)는 이제 맞지 않으므로 그 줄만 지운다. DEC-041의 결정·이유·한계 문장은 고치지 않는다.
- 파일 끝은 main 그대로(DEC-051이 마지막).

**`.agent/HANDOFF.md`**
- **main 판을 기준**으로 한다.
- #60이 Last Work에 넣은 "화면 세션"(2026-10-09) 항목을 Last Work에 넣는다.
- #60이 추가한 할 일 43(3D 모델 파일 나누기)·44(데모 데이터 출처 잇기)는 **54·55로 번호를 바꿔** 목록 끝에 붙인다(main의 43·44는 다른 일이다. main 목록은 53에서 끝난다).
- 할 일 26의 "2026-10-09 진행" 문장을 main의 할 일 26에 붙인다.
- Important Decisions 목록에 DEC-041 줄, Relevant Files에 `frontend/README.md`.

**`.agent/SESSION_LOG.md`** — 양쪽 줄을 모두 남기고 날짜 순서로.

`.gitignore`는 자동 병합된다(`frontend/public/models/` 줄이 남는지 확인).

커밋 제목 예: `chore: main을 병합해 인계 문서 충돌 해결`

## 2. 데모 데이터 원문 정정 (커밋 2)

**사실(2026-10-13 확인)**: `frontend/public/data/recalls.json` 548줄 `14V614000`의 `remedy` 끝에 `GMÂ\u0092s`가 있다. 바이트로 `47 4D C3 82 C2 92 73`. 저장소 카드 원문(`data/processed/defect/recalls.jsonl`의 14V614000 `remedy`)은 `GM\u0092s` = `47 4D C2 92 73`이다. U+0092가 한 번 더 UTF-8로 인코딩되며 `Â`(C3 82)가 끼었다.

- **`C3 82 C2 92` → `C2 92`로만 바꾼다.** `’`(작은따옴표)로 바꾸지 않는다 — 원문은 U+0092이고, 우리가 해석해 고치면 원칙 2 위반이다. 파일의 다른 바이트는 건드리지 않는다(JSON을 다시 직렬화하지 말고 바이트 치환으로).
- 새 스크립트 `frontend/scripts/check-demo-against-cards.mjs <recalls.jsonl 경로>` (Node 내장 모듈만, `package.json` 스크립트로 등록하지 않음 — 수동 실행):
  - 데모 JSON의 모든 리콜(silverado·ram 배열)에 대해: `campno`가 카드 파일에 있는가, `defect`·`consequence`·`remedy`가 카드의 같은 칸과 **바이트까지** 같은가, `maker === 카드.raw_maker`인가.
  - 출력: 총 건수, 일치 수, 다른 칸 목록(campno·칸 이름). 하나라도 다르면 종료 코드 1.
  - 2026-10-13 확인값: 정정 전 77건 중 14V614000 `remedy` 한 칸만 다름, `maker`는 77/77이 `raw_maker`와 같음.
- `data/processed/defect/recalls.jsonl`은 gitignore라 Codex 환경에 없을 수 있다. 없으면 스크립트만 만들고 "실행은 사람이 함"으로 보고한다.
- `frontend/src/recalls.test.ts`의 "public/data 약속" 묶음에 시험 추가: 데모 JSON 문자열 전체에서 `Ã` 또는 `Â` 뒤에 U+0080~U+00BF가 오는 패턴(`/Ã|Â[\u0080-¿]/`)이 0건.

커밋 제목 예: `fix: 14V614000 시정 원문의 깨진 글자를 카드 원문으로 되돌림`

## 3. 차종 탭에서 뺄 리콜·배지 (커밋 3)

**사용자 결정(2026-10-13)**: 
- `13V544000`·`14V614000` — 본문이 Silverado **HD**/Sierra HD만 언급 → `recalls.json`의 `silverado` 배열에서 **뺀다**(이것도 바이트 편집 — 해당 객체만 지우고 나머지 줄·순서는 그대로).
- `13E073000`·`16E041000` — 장비(Equipment) 리콜 → 남기되 카드에 **"장비 리콜" 배지**. 판단 기준은 `campno` 세 번째 글자가 `E`인가(`/^\d{2}E/`).
- 결과: Silverado 36건, Ram 39건(정정 전 38·39). 시험의 건수 단언이 있으면 맞춘다.
- `frontend/README.md` 데이터 절에 뺀 2건과 이유(본문 인용 한 줄씩), 장비 배지 규칙을 적는다.

## 4. 문구 (커밋 4)

| 위치 | 지금 | 바꿀 문구 | 이유 |
|---|---|---|---|
| `components/Hero.tsx` 세 번째 통계 | "리콜 대상 대수(합계)" (`heroStats().unitsM`) | **"접수일 범위"** — 값은 그 차종 리콜의 가장 이른 접수일 ~ 가장 늦은 접수일(`YYYY.MM`–`YYYY.MM`) | `potaff` 합계는 리콜끼리 겹치고 다른 차종도 포함된 수라 오해를 준다. `recalls.ts`의 `unitsM` 계산은 쓰이지 않으면 지운다(시험도 맞춤) |
| `components/Panel.tsx:115` 카드 메타 | `{potaff}대` | `신고 대상 대수 {n} (이 리콜 전체, 다른 차종 포함)` | 같음 |
| `Panel.tsx:89` 교차 버튼 | `같은 부품, 다른 회사 선례 → {차종} {n}건` | `같은 분류({분류명})의 {차종} 리콜 {n}건 보기` | "같은 부품"이 아니라 같은 분류이고 "선례" 판단이 아님 |
| `Panel.tsx:22` eyebrow / `:18` 기본 제목 | "결함 부품" / "결함이 기록된 부품" | "리콜이 기록된 부품 분류" | |
| `Panel.tsx:122` 등 카드 라벨 | "결함 (원문)", 결과, 조치 | **결함 · 결과 · 시정** 라벨 + 위에 한 줄 "NHTSA 원문" | API 용어(remedy = 시정)와 맞춤 |
| 크레딧 줄(`App.tsx` 하단) 또는 TopBar | — | "데모 스냅샷 {n}건 (검색 결과 아님)" 추가 | 쇼룸이 우리 검색 결과로 오해받지 않게 |

## 5. 쇼룸에 디자인 결정 반영 (커밋 4에 함께)

`docs/design-system/open-questions.md` 결정 4·8:
- `frontend/src/styles.css` `:root`의 `--ink-3`을 `#8c94a1` → **`#636b78`**(흰 배경 대비 3.06 → 5.38:1). `body.xray` 안의 `--ink-3`(어두운 테마)은 그대로.
- `:root`에 `--font-source: "Source Serif 4", Georgia, "Times New Roman", serif;`를 추가하고, 리콜 카드의 원문 칸(`recall-text` 등 결함·결과·시정 글)에 `font-family: var(--font-source)`와 `lang="en"`. 글꼴 파일 번들은 작업 E에서 한다(지금은 Georgia로 보여도 된다).

## 6. 3D 모델 기록 (커밋 5)

**사용자 결정(2026-10-13)**: 3D 모델은 재배포해도 된다.

`frontend/README.md` "3D 모델 파일" 절을 고친다:
- 출처: CCSA(George Mason University)의 FHWA/NHTSA 유한요소 차량 모델을 단순화(기존 문장 유지), 재배포는 2026-10-13 사용자 결정(DEC-052).
- **받는 방법**: 우지훈 소유 claude.ai artifact "결함 선례 쇼룸 (Copy)"(`https://claude.ai/artifact/5022cf20-2f08-4389-b13f-5adde11b78d4`, 비공개 — 공유받아야 열림)의 `models/silverado.gltf.json`·`models/ram.gltf.json`을 받아 `node scripts/gltf-json-to-glb.mjs <in> <out>`으로 `public/models/*.glb`를 만든다. 원본 sha256(`2bb27ed2…`·`08e4d6eb…`)과 결과 sha256(`d608c0bc…` 10,524,576B · `f8532a1d…` 8,446,292B)을 `shasum -a 256`으로 대조한다(2026-10-13 이 방법으로 바이트까지 같음을 확인). 작업 F 뒤에는 배포 화면의 `/models/*.glb`에서도 받을 수 있다.
- 3D 모델이 없으면 쇼룸은 "3D 모델을 불러오지 못했습니다"에서 멈춘다(작업 E에서 검색 화면은 이와 무관하게 동작하게 바꾼다).

`.agent/DECISIONS.md`에 **DEC-052**: "3D 모델 재배포 허용과 받는 방법 · 데모 데이터 원문 정정과 범위"
- Decision: ① 3D 모델 재배포 허용(사용자 결정 2026-10-13) ② 받는 방법(위) ③ 데모 데이터 14V614000은 카드 원문(U+0092)으로 정정 — `’`로 바꾸지 않는 이유(원칙 2) ④ 차종 탭에서 HD 2건 제외, 장비 리콜 배지(사용자 결정 2026-10-13) ⑤ 쇼룸 `--ink-3` 진하게·원문 세리프(디자인 시스템 결정 4·8)
- Reason / 검증(대조 스크립트 결과) / 한계(데모 데이터는 여전히 artifact 판본의 스냅샷 — 재생성 스크립트 없음, HANDOFF 할 일 55)

`.agent/HANDOFF.md`: Next Action 1을 "#60 정리 끝(병합 대기) → 작업 E"로, 할 일 54(3D 모델)는 받는 방법이 정해졌다고 갱신. `SESSION_LOG.md` 한 줄.

## 7. 검증

```bash
cd frontend && npm ci && npm run lint && npm run build && npm test
cd .. && uv run ruff check . && uv run ruff format --check . && uv run pytest
node frontend/scripts/check-demo-against-cards.mjs data/processed/defect/recalls.jsonl   # 파일이 있을 때만
```

- 대조 스크립트: 정정 뒤 75건(36+39) 모두 일치가 기대값.
- `npm run dev`로 확인(가능하면): `.glb`가 없으면 실패 안내가 뜨는지, 있으면 쇼룸이 뜨고 카드 문구가 바뀌었는지.
- 판정 문구 검색: `git diff origin/main -- frontend | grep -nE "리콜 대상|원인은|해당합니다|applies|verdict"` 결과가 0건(설명 주석 제외).

## 8. PR

#60에 push하면 PR이 갱신된다. **#60 본문의 박성호 님 내용은 지우지 말고**, 맨 아래에 `## 정리 작업 (우지훈 담당, 2026-10-xx)` 절을 덧붙여 위 1~6과 검증 결과를 적는다. 본문이 템플릿 절(변경 요약·변경 유형·체크리스트·검증 방법·병합 전 검증·관련 이슈)을 갖추지 못했으면 빠진 절만 추가한다. 관련 이슈: `Refs #24 · Refs #53`.

병합하지 않는다 — 리뷰·병합 전 검증은 Claude Code 세션이 한다.

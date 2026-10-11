# P2 API 서버 개발 계획 (10/11~14)

> 승인: 2026-10-10 우지훈(B 파트). 결정 근거 `.agent/DECISIONS.md` DEC-038·039·042. PR 1은 #62로 병합됐다(main `6d12818`), PR 2는 #66.
> 이 문서는 남은 PR 2·3을 누가 맡아도 같은 기준으로 구현하도록 승인된 내용을 옮겨 둔 것이다. 바꾸려면 이 문서와 DEC를 같은 PR에서 고친다.

## 0. 범위 (사용자 결정 2026-10-10)

1차 범위 = 검색 + 573 원인 원문 + 응답 검사(PR 1, 완료) **+ 고객사 선례 먼저(PR 1, 완료) + 조사 요약 원인(정부 조사관) + 확인 항목 고정 틀 + 부품 범위 좁히기**. 데이터는 로컬 build 파일, 카드 벡터는 Supabase(DEC-042). LLM은 쓰지 않는다(DEC-039 ③ — 유료 API 호출 없음).

## 1. PR 2 — 원인·확인 항목 (10/11~13)

| 파일 | 하는 일 |
|---|---|
| `server/rag/investigations.py`(새 파일) | **조사 요약 원인**: raw `data/raw/nhtsa/FLAT_INV.zip`을 서버 시작 때 읽어 카드의 `CAMPNO`로 잇는다(`nhtsa.read_flat`·`INV_COLS`, `why_stats.linked_campnos`와 같은 규칙 — 요약이 비었거나 자리표시 문구면 제외). 같은 조사 번호의 여러 줄(차종별)은 하나로 모은다. 말한 주체 = NHTSA 결함 조사(조사관), 출처 = 조사 번호 `ACTION`·개시일·종료일(원본 칸 그대로 — 종료일이 빈 조사가 있다). 원본은 `manifest.json` sha256 = build `raw_manifest_sha256`이고 `FLAT_INV.zip` sha256 = manifest 기록일 때만 쓴다 — `raw_manifest_sha256`은 build_id의 입력이라 같은 build_id면 같은 조사 원본이고, 응답의 조사 번호(`ACTION`)로 원본 기록을 되짚는다. 원본은 커밋하지 않으므로 서버를 띄우는 곳에 build와 같은 날 받은 `data/raw/nhtsa/`를 두고(팀 드라이브 사본), 없거나 해시가 다르면 서버가 시작하지 않는다(배포 절차는 #63). **색인에는 넣지 않는다** — 시험 질문의 출처라 넣으면 누수(AGENTS.md 5-2). 한 카드에 조사가 여러 건이면 조사 번호별로 따로 싣는다. 같은 조사의 요약 판본이 여러 개면 짐작하지 않고 서버를 띄우지 않는다. |
| `server/rag/flags.py` | 원인 글(573·조사 요약)에 붙는 **표시 꼬리표 — 판정이 아니라 글에 그 표현이 있다는 사실만** 알린다. ① "원인 미확인 표현 있음" — `cause_trials.UNKNOWN_RE`(#53 잠정안, `finditer`로 구간을 얻는다) ② "추정 표현 있음" — 아래 단어 목록. 꼬리표마다 걸린 원문 구간(시작·끝·글자)을 함께 싣는다. |
| `server/rag/checks.py` | **확인 항목 고정 틀**(규칙, LLM 없음). 항목마다 근거 원문(칸 이름 + 글)을 잇고, 근거가 없으면 그 항목을 싣지 않는다. 생산 기간은 카드에 연식·생산일 칸이 없어 1차에서 제외(한계로 기록). |
| `server/api.py` | 응답 모델에 `investigations[]`·`cause.flags`·`checklist[]`를 더한다(상태별 필수 칸·`extra="forbid"` 유지). |

**고정한 것 (2026-10-10 사용자 결정 — 제안한 "좁은 안"과 확인 항목 순서를 "전체 작업 진행"으로 승인. 원인 미확인 150건 정답 표시를 보기 전에 고정했고 표시 결과를 보고 고치지 않는다, AGENTS.md 5-2)**

- 추정 표현 단어(대소문자 무시, 단어 경계): `appear to`·`appears to`·`appeared to`·`might`·`possibly`·`likely`·`probably`·`suspect`·`suspected`·`believe`·`believed`. `may`·`could`는 넣지 않는다 — 원인 서술에서 "may result in", "could cause"처럼 결과를 설명할 때 흔히 써서 추정이 아닌 글에도 걸리기 쉽다.
- 확인 항목 순서와 근거 칸: ① 같은 부품 — 카드 `components`·결함 원문 ② 고장 양상 — 결과 원문 ③ 시정 — 시정 원문 ④ 공급사 — 573 `supplier_names`(있을 때만) ⑤ 원인을 말한 주체 — 573(리콜 제조사)·조사 요약(NHTSA). 화면에 보일 이름은 박성호 님과 정한다(PR #60).

**검증**: 조사 요약은 원본 기록과 같은 글인지, 꼬리표 구간은 그 글의 `text[start:end]`가 구간 글과 같은지 서버 안에서 대조한다(LLM이 없으므로 `engine2_trial.check` 같은 찾기 대조는 필요 없다). 검색 순위를 바꾸지 않으므로 749문항 점수(H@10 0.542)가 그대로인지 `server.rag.parity`로 확인한다. 조사 요약이 붙는 카드 수(현재 build, `why_stats.linked_campnos` 규칙): 요약 있는 조사에 연결된 카드 1,870장, 서로 다른 조사 917개, 조사 2개 이상이 연결된 카드 35장, 조사 하나에 요약 판본 여러 개 0건.

## 2. PR 3 — 부품 범위 좁히기 실험 (10/13~14)

`server/rag/parts.py` — 걸러내지 않고 순위만 바꾼다: 질문 단어를 NHTSA 부품 분류 이름(카드 `components`)에 맞춰, 같은 분류 카드를 RRF 순위 안에서 앞으로 올린다. 같은 749문항 대리 평가로 before/after를 재서 **기준 폭 0.03 이상 나아질 때만 켜고**, 아니면 기본 꺼 두고 기각 이유를 남긴다(AGENTS.md 5-1·5-3·5-4). 규칙은 정답을 보기 전에 정하고, 결과를 보고 단어·가중치를 맞추지 않는다. HANDOFF 할 일 22(부품 연결 규칙)를 이 실험으로 정한다.

## 3. 공통

- PR마다: DEC 기록(확인 항목 틀·꼬리표 규칙·부품 범위), `server/README.md` 응답 칸, HANDOFF·SESSION_LOG, review-agent + Codex 리뷰, 병합 전 검증(Actions를 끈 동안 G-01은 `LOCAL_CI_REQUIRE_PR=1 TEST_DATABASE_URL=<일회용 pgvector/pgvector:pg17> bash scripts/local_ci.sh` 출력 — `docs/MERGE_PROTOCOL.md` 7절).
- 판정 칸·판정 문구를 만들지 않는다(AGENTS.md 2-1). 꼬리표 이름도 "원인 미확인 표현 있음"처럼 글에 대한 사실로 쓴다.

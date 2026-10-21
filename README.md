# Recall Casebook — 결함 선례 찾기 도우미

LG CNS AI Campus RAG 팀 프로젝트 — **결함 선례 찾기 도우미** (DEC-030).

한국 부품사에서 북미 수출 차종을 맡은 품질·제품안전 엔지니어가 원인 모를 결함을 받았을 때, 미국 정부(NHTSA) 공개 리콜·결함 조사에서
같은 부품의 다른 회사 선례와 그 원인 서술을 **원문 그대로, 리콜 번호와 함께** 찾아 주는 RAG 서비스. 판정("리콜 대상입니다")은 하지 않는다. <!-- principle-ok: 금지 문구 인용 -->

> 시연: 화면 <https://lg-cns-rag-web.vercel.app> · API <https://lg-cns-rag.vercel.app> (영어 질문만). 라이선스: [MIT](LICENSE), 데이터·3D 모델 출처는 [NOTICE](NOTICE).
>
> 기획 상세: [`docs/product/기획_결함선례.md`](docs/product/기획_결함선례.md). 데이터·시험지·기준 점수 재현: [`scripts/defect_precedent/README.md`](scripts/defect_precedent/README.md).
> 이전 주제 문서 — 온보딩 RAG [`docs/archive/기획v1.md`](docs/archive/기획v1.md)(DEC-010), Compliance AI [`docs/archive/기획.md`](docs/archive/기획.md) — 는 참고용이다.

## 지금 어디까지 왔나

- **주제**: 결함 선례 찾기 도우미 (DEC-030, 2026-10-06 전환). 데이터는 NHTSA 공개 리콜 30,350건·결함 조사 5,349건과 리콜 원본 보고서(Part 573, 원인·공급사 칸).
- **역할**: A 데이터·시험지 박예원 · B RAG 우지훈 · C 검사·화면·발표 박성호 · D 근거·품질 확인 이승노 (이슈 #24).
- **기준선**: 시험 문제 749개(정부가 기록한 조사 → 리콜, 대리 평가)에서 단순 검색 Hit@10 0.510. 재현 방법은 [`scripts/defect_precedent/README.md`](scripts/defect_precedent/README.md).
- **일정**: 발표 2026-10-20, 10/8~10 준비, 개발 10/12~14. 파트별 일정·역할은 이슈 #24, 할 일·위험은 [`.agent/HANDOFF.md`](.agent/HANDOFF.md). ([`docs/archive/진행계획.md`](docs/archive/진행계획.md)는 이전 주제(온보딩) 기준이라 참고용이다 — 결함 선례 기준 개정은 HANDOFF 할 일.)
- **지금 할 일·열린 결정**은 [`.agent/HANDOFF.md`](.agent/HANDOFF.md)에 있다. 이슈 대신 이 문서가 할 일 목록을 가진다.

## 데이터 받기

원본(NHTSA 공개 파일·리콜 원본 보고서 PDF)과 결과물은 커밋하지 않는다 (`data/raw/`, `data/processed/`는 `.gitignore`). 스크립트로 받아 만든다:

```bash
uv run python -m scripts.defect_precedent.nhtsa fetch      # 원본 받기 + manifest
uv run python -m scripts.defect_precedent.nhtsa build      # 리콜 카드 · 시험지
uv run python -m scripts.defect_precedent.bm25_baseline    # 기준 점수
```

실행 순서·기준 파일·재현 조건은 `scripts/defect_precedent/README.md`. 이전 주제(온보딩)의 핸드북 데이터셋은 `uv run python scripts/fetch_handbook_dataset.py`로 받는다(데이터셋 안내서는 삭제 — git 이력 `6d12818`의 `docs/handbook/README.md`).

## 시작하기

> 처음이라면 **[`docs/guides/시작하기.md`](docs/guides/시작하기.md)** 를 위에서부터 따라 한다 (도구 설치 → 첫 PR → 관리자 설정).

```bash
git clone <repo-url>
cd recall-casebook
uv sync                # Python 3.12 + 의존성 설치 (.venv)
lefthook install       # git 훅 설치
cp .env.example .env   # 실제 키는 .env에만 — 절대 커밋하지 않는다
uv run pytest          # 확인
```

도구 설치(uv·lefthook)와 패키지 추가·노트북·문제 해결은 [`docs/guides/개발환경.md`](docs/guides/개발환경.md)를 본다.

## 협업 규칙

AI 에이전트로 작업할 때의 규칙은 [`AGENTS.md`](AGENTS.md)에 있다.

브랜치·커밋·PR 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 따른다.

## 디렉터리

| 경로 | 용도 |
|---|---|
| `docs/` | 기획(`기획_결함선례.md` — 현행, DEC-030 / 이전 주제 `archive/기획v1.md`·`archive/기획.md`)·제품 요구 `PRD.md`·데이터 구조 `ERD.md`·개발환경·병합 전 검증 프로토콜(`MERGE_PROTOCOL.md`) 등 문서 |
| `tests/` | pytest 테스트 |
| `AGENTS.md` · `CLAUDE.md` | AI 에이전트 행동강령 (원본은 AGENTS.md) |
| `.claude/settings.json` | Claude Code 팀 공유 권한 설정 |
| `.agent/` | AI 에이전트 세션 인계 문서 (PROJECT_CONTEXT · HANDOFF · DECISIONS · SESSION_LOG) |
| `.github/` | PR 템플릿, CODEOWNERS, CI 워크플로 |
| `scripts/` | lefthook이 호출하는 검사 스크립트, CI 로직(`ci/`), 결함 선례 데이터·평가 스크립트(`defect_precedent/`), 이전 주제 핸드북 데이터셋 재현(`fetch_handbook_dataset.py`) |

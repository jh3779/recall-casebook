# docs/ 문서 지도

> **처음 오면** 하는 일에 맞춰 고른다. 에이전트의 시작 순서는 `AGENTS.md` 0절이다. 문서를 새로 만들면 [이름 규칙](guides/문서_이름_규칙.md)에 따라 **아래 폴더 중 하나에 두고 이 지도에 한 줄을 더한다.** 끝난 작업·이전 주제 문서는 지우지 않고 [`archive/`](archive/README.md)로 옮긴다(git 이력 유지).

## 어디부터 읽나

| 누가 | 순서 |
|---|---|
| 이 프로젝트가 처음인 사람 | [`product/PRD.md`](product/PRD.md) → [`product/기획_결함선례.md`](product/기획_결함선례.md) → [`project/업무시나리오_도메인.md`](project/업무시나리오_도메인.md) |
| 코드를 만지려는 사람 | [`guides/시작하기.md`](guides/시작하기.md) → [`guides/환경셋팅.md`](guides/환경셋팅.md) → [`product/ERD.md`](product/ERD.md) |
| 검색 성능·근거가 궁금한 사람 | [`experiments/실험_P2_검색방식비교.md`](experiments/실험_P2_검색방식비교.md) → [`experiments/실험_P4_임베딩모델비교.md`](experiments/실험_P4_임베딩모델비교.md) → [`experiments/실험_P5_희소부품층화.md`](experiments/실험_P5_희소부품층화.md) |
| 프로젝트 진행·역할이 궁금한 사람 | [`project/WBS_역할분배_시간예산.md`](project/WBS_역할분배_시간예산.md) |
| 병합하려는 사람 | [`guides/MERGE_PROTOCOL.md`](guides/MERGE_PROTOCOL.md) |

## 폴더 구조

| 폴더 | 무엇을 두나 | 새 문서를 둘 때의 기준 |
|---|---|---|
| [`product/`](#product--무엇을-만드는가) | 제품 요구·기획·데이터 구조·개발 계획 | "무엇을, 왜 만드는가" |
| [`experiments/`](#experiments--실험검증-기록) | 실험·검증 기록(사전 고정 규칙, 결과, 기각 이유) | 같은 평가셋 before/after 숫자가 있는 문서 |
| [`guides/`](#guides--작업-방법) | 설치·환경·git·병합·배포 방법 | "어떻게 하는가" |
| [`labeling/`](#labeling--사람이-하는-표시-작업-안내) | 사람이 하는 표시·확인 작업 안내(표시자용) | 표시자가 읽는 안내서 |
| [`project/`](#project--진행-기록과-시나리오) | WBS·역할·시간 예산, 업무 시나리오, 시연 시나리오 | 프로젝트를 설명하는 기록 |
| [`design-system/`](design-system/README.md) | 디자인 시스템 v1.0 — 토큰·컴포넌트·문구·목업 | 화면 규칙(프런트 시험이 일부 파일을 읽는다) |
| [`archive/`](archive/README.md) | 이전 주제·끝난 작업 기록 | 현행 판단의 근거로 쓰지 않는다 |
| `images/` | 문서에 들어가는 그림 | |

## product — 무엇을 만드는가

| 문서 | 내용 |
|---|---|
| [`PRD.md`](product/PRD.md) | 제품 요구 정리 — 목표·비목표·기능 요구·서비스 원칙·평가 지표·8D 작성 보조(시험 구현)·위험. 새 주장 없이 아래 문서에서 옮긴 정리본 |
| [`ERD.md`](product/ERD.md) | 데이터 구조 — DB 7개 테이블 ERD, API 응답 모델, 원본에서 서버까지의 데이터 계보(Mermaid) |
| [`기획_결함선례.md`](product/기획_결함선례.md) | 현행 기획 3판(DEC-030) — 문제 정의, 유사 서비스, 기술 스택, 아키텍처, 시험지·기준선(6절), 어려움과 해결 |
| [`계획_케이스북.md`](product/계획_케이스북.md) | 케이스북(D4 집중) 구현 계획 — 3단 화면, 구조로 지키는 것, PR 순서(DEC-067·068) |
| [`계획_P2_API서버.md`](product/계획_P2_API서버.md) · [`계획_P3_리랭커시험.md`](product/계획_P3_리랭커시험.md) | 개발 계획 — API 서버(10/11~14), 재순위화 시험 초안(사전 고정 규칙) |
| [`데이터_중복_처리_패턴.md`](product/데이터_중복_처리_패턴.md) | "같아 보이는 데이터"가 생기는 이유와 처리 위치(DEC-034) |

## experiments — 실험·검증 기록

| 문서 | 내용 |
|---|---|
| [`실험_P2_검색방식비교.md`](experiments/실험_P2_검색방식비교.md) | BM25 · 뜻 검색 · RRF 비교, 30건 원인 추출 시험(DEC-039) |
| [`실험_P4_임베딩모델비교.md`](experiments/실험_P4_임베딩모델비교.md) | 임베딩 모델 비교 — 다른 계열·더 큰 모델 5종, 접두어 없는 사전 설정에서는 채택 후보 없음(arctic 계열은 P4b 전까지 미확정) |
| [`실험_P5_희소부품층화.md`](experiments/실험_P5_희소부품층화.md) | 사례가 적은 부품에서의 성능 — 사후 층화 분석(드묾 0.613 / 중간 0.566 / 흔함 0.429), 재현 스크립트 `scripts/defect_precedent/rare_strata.py` |
| [`실험_LLM_Luna비교.md`](experiments/실험_LLM_Luna비교.md) | gpt-6-luna와 gpt-4o-mini 비교(2026-10-12) |
| [`실험_8D초안표본.md`](experiments/실험_8D초안표본.md) | 8D D2·D4 묶음 초안 표본 관찰 — 평가 아님(DEC-065) |
| [`실험_LLM단독기준선.md`](experiments/실험_LLM단독기준선.md) | 검색 없이 LLM에게만 물은 기준선 — D ② 열람 제한 문서였으나 2026-10-21에 해제됨(DEC-082) |
| [`프런트_구현_검증.md`](experiments/프런트_구현_검증.md) · [`프런트_현대기아_모델.md`](experiments/프런트_현대기아_모델.md) | 화면 구현 검증, 쏘나타·쏘렌토 쇼룸과 추정 부품 표시(DEC-052·054) |

## guides — 작업 방법

| 문서 | 내용 |
|---|---|
| [`시작하기.md`](guides/시작하기.md) | 도구 설치 → 저장소 받기 → 첫 PR 전체 안내 |
| [`환경셋팅.md`](guides/환경셋팅.md) · [`개발환경.md`](guides/개발환경.md) | 결함 선례 작업 환경(데이터 만들기·기준 점수) / uv·lefthook 상세 |
| [`git_명령어.md`](guides/git_명령어.md) | 이 저장소에서 쓰는 git·gh 명령 사전 |
| [`MERGE_PROTOCOL.md`](guides/MERGE_PROTOCOL.md) | 병합 전 검증 게이트 |
| [`배포_Vercel.md`](guides/배포_Vercel.md) | 화면·API Vercel 배포와 호출 상한(DEC-048·057·058) |
| [`문서_이름_규칙.md`](guides/문서_이름_규칙.md) | docs 문서의 폴더·파일 이름·접두어 규칙, 이름을 바꿀 때의 절차(DEC-083) |

## labeling — 사람이 하는 표시 작업 안내

| 문서 | 내용 |
|---|---|
| [`시점평가_정답표시_안내.md`](labeling/시점평가_정답표시_안내.md) | 시점 평가 정답 표시 기준(DEC-037) |
| [`D파트_표시_안내.md`](labeling/D파트_표시_안내.md) · [`D파트_표시_안내_원인미확인.md`](labeling/D파트_표시_안내_원인미확인.md) | D 파트 표시 안내(원인 품질 30건 / 원인 미확인 150건) |
| [`회사명_대응표_안내.md`](labeling/회사명_대응표_안내.md) | 회사명 대응표 확인 작업 |

## project — 진행 기록과 시나리오

| 문서 | 내용 |
|---|---|
| [`WBS_역할분배_시간예산.md`](project/WBS_역할분배_시간예산.md) | 계획 대비 실제 — 단계별 일정, 일별 처리량, WBS 8영역, 역할(RACI), 시간 예산 판단, 다음 프로젝트용 규칙(2026-10-21) |
| [`업무시나리오_도메인.md`](project/업무시나리오_도메인.md) | 도메인 용어표, 5영업일 일별 업무 시나리오(가설), 희소 부품 시나리오, 가치 검증 계획 |
| [`시연영상_시나리오.md`](project/시연영상_시나리오.md) | 시연 영상 촬영 시나리오(랜딩 컷은 앱의 랜딩을 없애는 UI 정돈 작업 — `feat/ui-tidy`, 병합 전 — 이 병합되면 옛 화면 기준이 된다) |

## 옛 경로 → 새 경로 (2026-10-21 폴더 구조화, DEC-083)

`.agent/DECISIONS.md`·`SESSION_LOG.md`의 과거 서술은 기록이라 당시 경로를 그대로 두었다. 거기 적힌 옛 경로는 아래 표로 찾는다. 코드 주석·규칙 문서·현재 상태 문서의 경로는 새 경로로 고쳤다. 이전에 `archive/`로 옮긴 문서의 대응표는 [`archive/README.md`](archive/README.md)다.

| 옛 경로 | 새 경로 |
|---|---|
| `docs/PRD.md` | [`product/PRD.md`](product/PRD.md) |
| `docs/ERD.md` | [`product/ERD.md`](product/ERD.md) |
| `docs/기획_결함선례.md` | [`product/기획_결함선례.md`](product/기획_결함선례.md) |
| `docs/계획_케이스북.md` | [`product/계획_케이스북.md`](product/계획_케이스북.md) |
| `docs/계획_P2_API서버.md` | [`product/계획_P2_API서버.md`](product/계획_P2_API서버.md) |
| `docs/계획_P3_리랭커시험.md` | [`product/계획_P3_리랭커시험.md`](product/계획_P3_리랭커시험.md) |
| `docs/데이터_중복_처리_패턴.md` | [`product/데이터_중복_처리_패턴.md`](product/데이터_중복_처리_패턴.md) |
| `docs/실험_P2_검색방식비교.md` | [`experiments/실험_P2_검색방식비교.md`](experiments/실험_P2_검색방식비교.md) |
| `docs/실험_P4_임베딩모델비교.md` | [`experiments/실험_P4_임베딩모델비교.md`](experiments/실험_P4_임베딩모델비교.md) |
| `docs/실험_LLM_Luna비교.md` | [`experiments/실험_LLM_Luna비교.md`](experiments/실험_LLM_Luna비교.md) |
| `docs/실험_8D초안표본.md` | [`experiments/실험_8D초안표본.md`](experiments/실험_8D초안표본.md) |
| `docs/실험_LLM단독기준선.md` | [`experiments/실험_LLM단독기준선.md`](experiments/실험_LLM단독기준선.md) |
| `docs/프런트_구현_검증.md` | [`experiments/프런트_구현_검증.md`](experiments/프런트_구현_검증.md) |
| `docs/프런트_현대기아_모델.md` | [`experiments/프런트_현대기아_모델.md`](experiments/프런트_현대기아_모델.md) |
| `docs/시작하기.md` | [`guides/시작하기.md`](guides/시작하기.md) |
| `docs/환경셋팅.md` | [`guides/환경셋팅.md`](guides/환경셋팅.md) |
| `docs/개발환경.md` | [`guides/개발환경.md`](guides/개발환경.md) |
| `docs/git_명령어.md` | [`guides/git_명령어.md`](guides/git_명령어.md) |
| `docs/MERGE_PROTOCOL.md` | [`guides/MERGE_PROTOCOL.md`](guides/MERGE_PROTOCOL.md) |
| `docs/배포_Vercel.md` | [`guides/배포_Vercel.md`](guides/배포_Vercel.md) |
| `docs/시점평가_정답표시_안내.md` | [`labeling/시점평가_정답표시_안내.md`](labeling/시점평가_정답표시_안내.md) |
| `docs/D파트_표시_안내.md` | [`labeling/D파트_표시_안내.md`](labeling/D파트_표시_안내.md) |
| `docs/D파트_표시_안내_원인미확인.md` | [`labeling/D파트_표시_안내_원인미확인.md`](labeling/D파트_표시_안내_원인미확인.md) |
| `docs/회사명_대응표_안내.md` | [`labeling/회사명_대응표_안내.md`](labeling/회사명_대응표_안내.md) |
| `docs/시연영상_시나리오.md` | [`project/시연영상_시나리오.md`](project/시연영상_시나리오.md) |

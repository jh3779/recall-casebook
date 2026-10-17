"""결함 선례 찾기 API 서버 (DEC-038·039).

실행 (서버 전용 `.env.server`에는 조회 전용 `SERVER_DATABASE_URL`만 둔다 — 카드 벡터와 원인 명세를 Supabase에서 읽는다):
    uv run --env-file .env.server uvicorn server.api:app --port 8000

- DB 연결은 조회 전용 계정의 `SERVER_DATABASE_URL`만 쓴다(권한은 `server/README.md`). 없으면 시작하지 않는다 — 로컬 개발에서만
  `ALLOW_ADMIN_DB_FOR_SERVER=1`을 직접 붙여 적재용 관리자 연결 `DATABASE_URL`로 읽을 수 있다(경고를 남긴다, DEC-042).

- `POST /search {"question": "..."}` → 고객사 선례, 같은 부품·다른 회사 선례. 카드마다 결함·결과·시정 원문과 Part 573 원인 원문(말한 주체·출처)을 싣는다.
- `POST /draft` → 8D D2·D4에 선례 원문을 묶은 초안(DEC-065). 기본은 꺼짐(`DRAFT_ENABLED=1`) — 꺼지면 묶음 없이 원문 목록만 준다. IP당 1분 6회(`DRAFT_RATE_LIMIT_PER_MINUTE`).
- `GET /health` → 데이터 판본(build_id·스냅샷 날짜)과 카드 수.
- `POST /search`는 IP당 1분 60회(`RATE_LIMIT_PER_MINUTE`)를 넘으면 429와 `Retry-After`를 낸다 — `server/ratelimit.py`, 이슈 #63.
- 판정하지 않는다: 응답에 적용 여부·리콜 필요 여부 같은 칸을 두지 않는다(AGENTS.md 2-1). 모든 응답에 build_id를 싣는다(2-4).
- 시작할 때 로컬 build 파일(적재와 같은 검사)·DB 원인 명세·DB 벡터 기록을 대조하고, 하나라도 어긋나면 서버를 띄우지 않는다.
- 응답은 아래 Pydantic 모델로 검사한다 — 원인 글(`filled`·`stated_unknown`)에는 말한 주체·출처가 반드시 있고, 모델에 없는 칸은 내보내지 않는다.
"""

import os
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scripts.defect_precedent.bm25_baseline import tokenize
from server.rag import customers, draft
from server.rag.build import Build
from server.rag.causes import cause_573
from server.rag.checks import checklist
from server.rag.investigations import SPEAKER_INV
from server.rag.search import Searcher
from server.rag.verify import verify
from server.ratelimit import RateLimiter, RateLimitMiddleware, limit_from_env

# 프런트 개발 서버(Vite 기본 주소). 배포 주소는 환경변수 ALLOWED_ORIGINS(쉼표로 구분)로 바꾼다
DEFAULT_ORIGINS = ["http://localhost:5173"]
CARD_TEXT_SPEAKER = "NHTSA 리콜 기록 요약(FLAT_RCL 결함·결과·시정 칸) — 원본에 작성 주체 표시 없음"
CARD_FIELDS = (
    "campno", "maker", "maker_group", "received_date", "components",
    "defect", "consequence", "remedy", "dup_group",
)  # fmt: skip


@dataclass
class RagState:
    build: Build
    searcher: Searcher
    model_name: str
    investigations: dict[str, list[dict]] = field(
        default_factory=dict
    )  # 리콜 번호 → 조사 요약 (색인에는 없음)
    bundle_sha256: str | None = (
        None  # 서빙 묶음으로 띄웠을 때 그 묶음 sha256 — 로컬 경로는 없음(AGENTS.md 2-4)
    )

    def __post_init__(self):
        self.by_id = {c["campno"]: c for c in self.build.cards}


def server_connection():
    """조회 전용 연결(SERVER_DATABASE_URL). 관리자 연결은 ALLOW_ADMIN_DB_FOR_SERVER=1을 직접 붙였을 때만 — 값은 출력하지 않는다."""
    import psycopg

    url = os.environ.get("SERVER_DATABASE_URL")
    if not url:
        url = os.environ.get("DATABASE_URL")
        if os.environ.get("ALLOW_ADMIN_DB_FOR_SERVER") != "1" or not url:
            raise RuntimeError(
                "SERVER_DATABASE_URL(조회 전용 계정)이 없다 — server/README.md 3단계. "
                "로컬 개발에서만 ALLOW_ADMIN_DB_FOR_SERVER=1로 관리자 연결(DATABASE_URL)을 쓸 수 있다"
            )
        print(
            "경고: ALLOW_ADMIN_DB_FOR_SERVER=1 — 관리자 연결(DATABASE_URL)로 읽는다. 로컬 개발용이고 배포에서는 쓰지 않는다",
            file=sys.stderr,
        )
    return psycopg.connect(url)


def allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()] or DEFAULT_ORIGINS


def load_state() -> RagState:
    """시작 경로는 RAG_SOURCE로 고른다: 없거나 `local`이면 로컬 build 파일(시연), `bundle`이면 서빙 묶음(배포, DEC-049)."""
    source = (
        os.environ.get("RAG_SOURCE", "").strip() or "local"
    )  # .env.example을 복사한 빈 값(RAG_SOURCE=)도 로컬
    if source == "bundle":
        return load_state_from_bundle()
    if source != "local":
        raise RuntimeError(f"RAG_SOURCE={source!r} — local 또는 bundle만 쓴다")
    return load_state_from_files()


def load_state_from_bundle() -> RagState:
    """배포 경로: DB 기록과 sha256이 같은 묶음을 /tmp로 받아, 로컬 경로와 같은 대조(DB 명세·벡터 기록·벡터 표본·탐침)를 한 뒤 쓴다.
    로컬 파일·조사 원본은 읽지 않는다 — 그 검사는 묶음을 만들 때 마쳤다(server/rag/bundle.py)."""
    from fastembed import TextEmbedding

    from scripts.defect_precedent.retrieval_compare import card_text
    from server.rag import bundle, embeddings
    from server.rag.build import check_against_db

    build_id = os.environ.get("SERVING_BUILD_ID", "").strip()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    if not build_id or not supabase_url:
        raise RuntimeError(
            "RAG_SOURCE=bundle에는 SERVING_BUILD_ID와 SUPABASE_URL이 필요하다 — 어느 build로 띄울지 짐작하지 않는다"
        )
    embeddings.check_fastembed()
    with server_connection() as conn:
        loaded = bundle.load_from_bundle(conn, build_id, supabase_url)
        build = loaded.build
        campnos = [c["campno"] for c in build.cards]
        texts = [card_text(c) for c in build.cards]
        check_against_db(conn, build)
        embeddings.check_set(conn, build.build_id, campnos, texts)
        if not embeddings.sample_matches(conn, build.build_id, campnos, loaded.vectors):
            raise embeddings.EmbeddingMismatch(
                "묶음의 벡터가 DB에서 뽑은 줄과 다르다 — 섞인 판본으로 검색하지 않는다"
            )
    model = TextEmbedding(embeddings.MODEL, specific_model_path=str(loaded.model_dir))
    # 묶음은 다른 기계에서 만든 벡터 — CPU에 따른 소수점 오차를 허용한다(DEC-051)
    embeddings.verify_probe(model, texts, loaded.vectors, atol=embeddings.CROSS_MACHINE_ATOL)
    return RagState(
        build,
        Searcher(build.cards, loaded.vectors, model),
        embeddings.MODEL,
        loaded.investigations,
        loaded.sha256,
    )


def load_state_from_files() -> RagState:
    from fastembed import TextEmbedding

    from scripts.defect_precedent.retrieval_compare import card_text
    from server.rag import embeddings
    from server.rag.build import check_against_db, load_build
    from server.rag.investigations import load_investigations

    build = load_build()
    embeddings.check_fastembed()
    model = TextEmbedding(embeddings.MODEL)
    texts = [card_text(c) for c in build.cards]
    with server_connection() as conn:
        check_against_db(conn, build)
        vecs = embeddings.load_vectors(
            conn, build.build_id, [c["campno"] for c in build.cards], texts
        )
    embeddings.verify_probe(model, texts, vecs)
    invs = load_investigations(build.raw_manifest_sha256, {c["campno"] for c in build.cards})
    return RagState(build, Searcher(build.cards, vecs, model), embeddings.MODEL, invs)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Span(Strict):
    start: int = Field(ge=0)
    end: int
    text: str = Field(min_length=1)


class Flag(Strict):
    """글에 이 표현이 있다는 사실 — 판정이 아니다."""

    kind: Literal["unknown_expression", "hedge_expression"]
    label: str
    spans: list[Span] = Field(min_length=1)


class Investigation(Strict):
    """NHTSA 결함 조사 요약 원문 — 말한 주체는 조사관, 출처는 조사 번호.

    표시 꼬리표는 붙이지 않는다 — 규칙이 573 원인 칸으로만 검증됐다(DEC-044)."""

    action: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    subject: str
    summary: str = Field(min_length=1)
    open_date: str
    close_date: str


class Evidence(Strict):
    field: str
    text: str = Field(min_length=1)


class CheckSource(Strict):
    """근거를 읽은 573 보고서 판본 — 파일과 sha256으로 원본을 되짚는다."""

    campaign: str
    file: str
    pdf_sha256: str
    submission_date: str


class CheckItem(Strict):
    item: Literal["same_part", "failure_mode", "remedy", "supplier", "cause_speaker"]
    label: str
    evidence: list[Evidence] = Field(min_length=1)


class ProductionCheckItem(Strict):
    """생산 기간 항목 — 읽은 573 보고서 판본(`source`)이 반드시 있어야 하고, 싣지 못한 블록 수(`omitted`)를 알린다(DEC-059).

    다른 항목에는 이 두 칸이 올 수 없다(`item`으로 모델을 나눠 출처 없는 생산 기간이 응답으로 나가지 못하게 한다)."""

    item: Literal["production_period"]
    label: str
    evidence: list[Evidence] = Field(min_length=1)
    omitted: int = Field(default=0, ge=0)  # 한도(5개) 때문에 싣지 못한 블록 수
    unread: int = Field(
        default=0, ge=0
    )  # 날짜까지 읽히지 않아 싣지 않은 블록 수(`NR - NR`·빈 값·한쪽만 있는 날짜)
    source: CheckSource


AnyCheckItem = Annotated[CheckItem | ProductionCheckItem, Field(discriminator="item")]


class CauseSource(Strict):
    campaign: str
    file: str
    pdf_sha256: str
    submission_date: str
    text_basis: str = Field(
        min_length=1
    )  # 원인 글이 PDF에서 어떻게 정리됐는지(DEC-047) — "원문 그대로"의 범위


class CauseText(Strict):
    """573 원인 칸 원문 그대로 — 말한 주체와 출처 없이는 내보내지 않는다."""

    status: Literal["filled"]
    text: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    source: CauseSource
    flags: list[Flag]


class CauseStated(Strict):
    """제조사가 원인 칸에 원인 대신 "미보고·조사 중"을 적은 경우 — 그 글을 원문 그대로, 말한 주체·출처와 함께 싣는다(DEC-047)."""

    status: Literal["stated_unknown"]
    text: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    source: CauseSource
    flags: list[Flag]


class CauseNoReport(Strict):
    """573 원문 수집 범위 밖(접수일 2014-08-20 이전) — 되짚을 보고서가 없다."""

    status: Literal["no_573_report"]


class CauseUnreadable(Strict):
    """보고서는 있지만 읽지 못했다 — 어느 캠페인을 왜 못 읽었는지 반드시 싣는다."""

    status: Literal["report_unreadable"]
    campaign: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CauseMissingText(Strict):
    """원인 글을 싣지 않는 그 밖의 경우 — 되짚을 캠페인 번호를 반드시 싣는다."""

    status: Literal[
        "report_status_unknown", "version_unresolved", "cause_empty", "cause_no_field", "verify_failed",
    ]  # fmt: skip
    campaign: str = Field(min_length=1)


class CardSource(Strict):
    dataset: Literal["NHTSA FLAT_RCL"]
    snapshot_date: str
    # 결함·결과·시정 글을 누가 썼는지는 원본 칸 설명(RCL.txt: "Defect Summary" 등)에 없다 — 아는 것(출처)만 적는다(DEC-047)
    speaker: Literal[CARD_TEXT_SPEAKER]


class Card(Strict):
    rank: int
    campno: str
    maker: str
    maker_group: str | None
    received_date: str
    components: list[str]
    defect: str
    consequence: str
    remedy: str
    dup_group: str
    source: CardSource
    cause: Annotated[
        CauseText | CauseStated | CauseNoReport | CauseUnreadable | CauseMissingText,
        Field(discriminator="status"),
    ]
    investigations: list[Investigation]
    checklist: list[AnyCheckItem]


class SearchResponse(Strict):
    build_id: str
    bundle_sha256: (
        str | None
    )  # 서빙 묶음으로 띄운 서버만 — build_id만으로는 구별되지 않는 묶음(형식 판본)까지 되짚는다
    snapshot_date: str
    model: str
    question: str
    customer_precedents: list[Card]
    precedents: list[Card]


class HealthResponse(Strict):
    build_id: str
    bundle_sha256: str | None
    snapshot_date: str
    cards: int
    model: str


class SearchRequest(Strict):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def needs_english_words(cls, v: str) -> str:
        # 색인·모델이 영어라(기획 1절) 영어 단어가 없으면 뜻 검색만으로 근거 없는 순위가 나온다 — 받지 않는다
        if not any(
            ch.isalpha() for ch in "".join(tokenize(v))
        ):  # "4wd"·"12v"처럼 섞인 단어는 받고, 숫자만은 받지 않는다
            raise ValueError("영어 단어가 들어간 질문이 필요합니다")
        return v.strip()


class DraftRequest(SearchRequest):
    """담은 선례(검색 결과 안의 번호만)와 단계 — 서버가 질문으로 다시 검색해 그 범위 안인지 확인한다(AGENTS.md 2-2)."""

    campnos: list[Annotated[str, Field(pattern=r"^[0-9]{2}[A-Z][0-9]{6}$")]] = Field(
        min_length=1, max_length=draft.MAX_CARDS
    )
    step: Literal["d2", "d4"]


class DraftItem(Strict):
    """원문에서 잘라 낸 인용 하나 — 말한 주체와 출처 없이는 내보내지 않는다."""

    campno: str
    field: Literal["defect", "consequence", "cause"]
    quote: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int
    speaker: str = Field(min_length=1)
    dataset: str | None = None
    snapshot_date: str | None = None
    cause_status: Literal["filled", "stated_unknown"] | None = None
    cause_source: CauseSource | None = None

    @model_validator(mode="after")
    def needs_provenance(self):
        if self.field == "cause":
            if self.cause_source is None or self.cause_status is None:
                raise ValueError("원인 인용에는 cause_status와 cause_source가 있어야 한다")
        elif not self.dataset or not self.snapshot_date:
            raise ValueError("결함·결과 인용에는 dataset과 snapshot_date가 있어야 한다")
        return self


class DraftGroup(Strict):
    title: str = Field(
        min_length=1, max_length=draft.MAX_TITLE
    )  # 도구가 만든 문장 — 화면이 "도구가 붙인 제목"으로 표시한다
    items: list[DraftItem] = Field(min_length=1)


class PickedQuestion(Strict):
    """LLM이 번호로 고른 확인 질문 — 문장은 서버의 고정 풀(`draft.QUESTION_POOL`) 그대로여야 응답이 나간다(DEC-071)."""

    id: str
    text: str

    @model_validator(mode="after")
    def from_the_fixed_pool(self):
        if draft.QUESTION_POOL.get(self.id) != self.text:
            raise ValueError("확인 질문은 고정 풀의 문장이어야 한다")
        return self


class DraftResponse(Strict):
    build_id: str
    bundle_sha256: str | None
    snapshot_date: str
    question: str
    step: Literal["d2", "d4"]
    titles_generated: Literal[True]
    model: str | None
    degraded: Literal["disabled", "llm_failed"] | None
    reason: str | None = None
    groups: list[DraftGroup]
    ungrouped: list[DraftItem]  # 묶이지 않은 원문 전체 — 꺼짐·실패일 때도 원문 목록으로 쓴다
    questions: list[str]
    picked_questions: list[PickedQuestion] = Field(
        default_factory=list, max_length=draft.MAX_PICK
    )  # D4에서 LLM이 고정 풀에서 번호로 고른 질문 — 꺼짐·실패·D2는 빈 목록
    rejected: dict[str, int]
    relocated: int = Field(
        default=0, ge=0
    )  # 공백만 달라 원문 구간으로 되짚은 인용 수 — 글자는 원문 것


def card_view(state: RagState, campno: str, rank: int) -> dict:
    card = state.by_id[campno]
    cause = cause_573(card, state.build.causes, state.build.unreadable)
    invs = state.investigations.get(campno, [])
    return {
        "rank": rank,
        **{k: card[k] for k in CARD_FIELDS},
        "source": {
            "dataset": "NHTSA FLAT_RCL",
            "snapshot_date": state.build.snapshot_date,
            "speaker": CARD_TEXT_SPEAKER,
        },
        "cause": cause,
        "investigations": [{**i, "speaker": SPEAKER_INV} for i in invs],
    }


def add_checklist(state: RagState, card: dict) -> dict:
    """검사(verify) 뒤에 만든다 — 원인 글이 검사에서 빠지면 '원인을 말한 주체' 근거도 같이 빠지게."""
    campno = card["campno"]
    row = state.build.causes.get(campno[:6])
    invs = state.investigations.get(campno, [])
    card["checklist"] = checklist(state.by_id[campno], row, invs, card["cause"])
    return card


def answer(state: RagState, question: str) -> dict:
    result = state.searcher.search(question)
    cust, others = customers.split(result.ranking, state.by_id)
    customer_cards = [card_view(state, result.ranking[r], r + 1) for r in cust]
    other_cards = [card_view(state, result.ranking[r], r + 1) for r in others]
    verify(
        customer_cards + other_cards, result.candidates, state.build.causes, state.investigations
    )
    for card in customer_cards + other_cards:
        add_checklist(state, card)
    return {
        "build_id": state.build.build_id,
        "bundle_sha256": state.bundle_sha256,
        "snapshot_date": state.build.snapshot_date,
        "model": state.model_name,
        "question": question,
        "customer_precedents": customer_cards,
        "precedents": other_cards,
    }


def make_draft(state: RagState, req: DraftRequest, llm) -> dict:
    """담은 선례의 원문을 단계별로 묶는다. 번호가 이 질문의 검색 결과 밖이면 거절한다 — 밖의 번호는 지어낸 것으로 본다."""
    result = state.searcher.search(req.question)
    outside = [c for c in req.campnos if c not in result.candidates]
    if outside:
        raise HTTPException(
            status_code=422,
            detail=f"이 질문의 검색 결과에 없는 리콜 번호입니다: {', '.join(outside)}",
        )
    rank = {c: i + 1 for i, c in enumerate(result.ranking)}
    cards = [card_view(state, c, rank[c]) for c in dict.fromkeys(req.campnos)]
    verify(cards, result.candidates, state.build.causes, state.investigations)
    out, _ = draft.generate(req.step, cards, llm)
    return {
        "build_id": state.build.build_id,
        "bundle_sha256": state.bundle_sha256,
        "snapshot_date": state.build.snapshot_date,
        "question": req.question,
        "titles_generated": True,
        **out,
    }


def peak_rss_mb() -> int:
    """이 프로세스의 최대 RSS(MB). ru_maxrss 단위는 Linux KB, macOS 바이트."""
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak // (1024 * 1024) if sys.platform == "darwin" else peak // 1024


def create_app(
    loader: Callable[[], RagState] = load_state,
    limiter: RateLimiter | None = None,
    draft_config: draft.DraftConfig | None = None,
    draft_limiter: RateLimiter | None = None,
    draft_llm: Callable | None = None,
) -> FastAPI:
    limiter = limiter or RateLimiter(
        limit_from_env()
    )  # IP당 1분 60회(이슈 #63), 잘못된 값이면 시작하지 않는다
    cfg = (
        draft_config or draft.DraftConfig.from_env()
    )  # 기본 꺼짐 — 잘못된 값·키 없는 켬이면 시작하지 않는다
    draft_limiter = draft_limiter or RateLimiter(cfg.limit)
    llm = draft_llm or cfg.llm()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.rag = loader()
        print(
            f"시작 최대 RSS {peak_rss_mb()}MB", file=sys.stderr
        )  # Vercel 로그에 메모리 항목이 없다(DEC-051)
        yield

    app = FastAPI(title="결함 선례 찾기 도우미", lifespan=lifespan)
    # 나중에 더한 미들웨어가 바깥이다 — CORS를 상한 바깥에 둬야 429에도 Access-Control-Allow-Origin이 붙는다
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
    app.add_middleware(RateLimitMiddleware, limiter=draft_limiter, route=("POST", "/draft"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
        expose_headers=["Retry-After"],  # 브라우저(화면)가 상한 대기 시간을 읽을 수 있게
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> dict:
        s: RagState = app.state.rag
        return {
            "build_id": s.build.build_id,
            "bundle_sha256": s.bundle_sha256,
            "snapshot_date": s.build.snapshot_date,
            "cards": len(s.build.cards),
            "model": s.model_name,
        }

    @app.post("/search", response_model=SearchResponse)
    def search(req: SearchRequest) -> dict:
        return answer(app.state.rag, req.question)

    @app.post("/draft", response_model=DraftResponse)
    def draft_route(req: DraftRequest) -> dict:
        return make_draft(app.state.rag, req, llm)

    return app


app = create_app()

"""결함 선례 찾기 API 서버 (DEC-038·039).

실행 (서버 전용 `.env.server`에는 조회 전용 `SERVER_DATABASE_URL`만 둔다 — 카드 벡터와 원인 명세를 Supabase에서 읽는다):
    uv run --env-file .env.server uvicorn server.api:app --port 8000

- DB 연결은 조회 전용 계정의 `SERVER_DATABASE_URL`만 쓴다(권한은 `server/README.md`). 없으면 시작하지 않는다 — 로컬 개발에서만
  `ALLOW_ADMIN_DB_FOR_SERVER=1`을 직접 붙여 적재용 관리자 연결 `DATABASE_URL`로 읽을 수 있다(경고를 남긴다, DEC-042).

- `POST /search {"question": "..."}` → 고객사 선례, 같은 부품·다른 회사 선례. 카드마다 결함·결과·시정 원문과 Part 573 원인 원문(말한 주체·출처)을 싣는다.
- `GET /health` → 데이터 판본(build_id·스냅샷 날짜)과 카드 수.
- 판정하지 않는다: 응답에 적용 여부·리콜 필요 여부 같은 칸을 두지 않는다(AGENTS.md 2-1). 모든 응답에 build_id를 싣는다(2-4).
- 시작할 때 로컬 build 파일(적재와 같은 검사)·DB 원인 명세·DB 벡터 기록을 대조하고, 하나라도 어긋나면 서버를 띄우지 않는다.
- 응답은 아래 Pydantic 모델로 검사한다 — 원인 글(`filled`)에는 말한 주체·출처가 반드시 있고, 모델에 없는 칸은 내보내지 않는다.
"""

import os
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from scripts.defect_precedent.bm25_baseline import tokenize
from server.rag import customers
from server.rag.build import Build
from server.rag.causes import cause_573
from server.rag.search import Searcher
from server.rag.verify import verify

# 프런트 개발 서버(Vite 기본 주소). 배포 주소는 배포를 정할 때 더한다
ALLOWED_ORIGINS = ["http://localhost:5173"]
CARD_FIELDS = (
    "campno", "maker", "maker_group", "received_date", "components",
    "defect", "consequence", "remedy", "dup_group",
)  # fmt: skip


@dataclass
class RagState:
    build: Build
    searcher: Searcher
    model_name: str

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


def load_state() -> RagState:
    from fastembed import TextEmbedding

    from scripts.defect_precedent.retrieval_compare import card_text
    from server.rag import embeddings
    from server.rag.build import check_against_db, load_build

    build = load_build()
    embeddings.check_fastembed()
    model = TextEmbedding(embeddings.MODEL)
    texts = [card_text(c) for c in build.cards]
    with server_connection() as conn:
        check_against_db(conn, build)
        vecs = embeddings.fetch(conn, build.build_id, [c["campno"] for c in build.cards], texts)
    embeddings.verify_probe(model, texts, vecs)
    return RagState(build, Searcher(build.cards, vecs, model), embeddings.MODEL)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CauseSource(Strict):
    campaign: str
    file: str
    pdf_sha256: str
    submission_date: str


class CauseText(Strict):
    """573 원인 칸 원문 그대로 — 말한 주체와 출처 없이는 내보내지 않는다."""

    status: Literal["filled"]
    text: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    source: CauseSource


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
        CauseText | CauseNoReport | CauseUnreadable | CauseMissingText,
        Field(discriminator="status"),
    ]


class SearchResponse(Strict):
    build_id: str
    snapshot_date: str
    model: str
    question: str
    customer_precedents: list[Card]
    precedents: list[Card]


class HealthResponse(Strict):
    build_id: str
    snapshot_date: str
    cards: int
    model: str


class SearchRequest(BaseModel):
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


def card_view(state: RagState, campno: str, rank: int) -> dict:
    card = state.by_id[campno]
    return {
        "rank": rank,
        **{k: card[k] for k in CARD_FIELDS},
        "source": {"dataset": "NHTSA FLAT_RCL", "snapshot_date": state.build.snapshot_date},
        "cause": cause_573(card, state.build.causes, state.build.unreadable),
    }


def answer(state: RagState, question: str) -> dict:
    result = state.searcher.search(question)
    cust, others = customers.split(result.ranking, state.by_id)
    customer_cards = [card_view(state, result.ranking[r], r + 1) for r in cust]
    other_cards = [card_view(state, result.ranking[r], r + 1) for r in others]
    verify(customer_cards + other_cards, result.candidates, state.build.causes)
    return {
        "build_id": state.build.build_id,
        "snapshot_date": state.build.snapshot_date,
        "model": state.model_name,
        "question": question,
        "customer_precedents": customer_cards,
        "precedents": other_cards,
    }


def create_app(loader: Callable[[], RagState] = load_state) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.rag = loader()
        yield

    app = FastAPI(title="결함 선례 찾기 도우미", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> dict:
        s: RagState = app.state.rag
        return {
            "build_id": s.build.build_id,
            "snapshot_date": s.build.snapshot_date,
            "cards": len(s.build.cards),
            "model": s.model_name,
        }

    @app.post("/search", response_model=SearchResponse)
    def search(req: SearchRequest) -> dict:
        return answer(app.state.rag, req.question)

    return app


app = create_app()

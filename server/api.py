"""결함 선례 찾기 API 서버 (DEC-038·039).

실행 (DATABASE_URL은 .env에만 둔다 — 카드 벡터를 Supabase에서 읽는다):
    uv run --env-file .env uvicorn server.api:app --port 8000

- `POST /search {"question": "..."}` → 고객사 선례, 같은 부품·다른 회사 선례. 카드마다 결함·결과·시정 원문과 Part 573 원인 원문(말한 주체·출처)을 싣는다.
- `GET /health` → 데이터 판본(build_id·스냅샷 날짜)과 카드 수.
- 판정하지 않는다: 응답에 적용 여부·리콜 필요 여부 같은 칸을 두지 않는다(AGENTS.md 2-1). 모든 응답에 build_id를 싣는다(2-4).
- 시작할 때 로컬 build 파일 해시와 DB 벡터 기록을 대조하고, 하나라도 어긋나면 서버를 띄우지 않는다.
"""

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

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


def load_state() -> RagState:
    from fastembed import TextEmbedding

    from scripts.defect_precedent.load_db import connect
    from scripts.defect_precedent.retrieval_compare import card_text
    from server.rag import embeddings
    from server.rag.build import load_build

    build = load_build()
    embeddings.check_fastembed()
    model = TextEmbedding(embeddings.MODEL)
    texts = [card_text(c) for c in build.cards]
    with connect() as conn:
        vecs = embeddings.fetch(conn, build.build_id, [c["campno"] for c in build.cards], texts)
    embeddings.verify_probe(model, texts, vecs)
    return RagState(build, Searcher(build.cards, vecs, model), embeddings.MODEL)


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

    @app.get("/health")
    def health() -> dict:
        s: RagState = app.state.rag
        return {
            "build_id": s.build.build_id,
            "snapshot_date": s.build.snapshot_date,
            "cards": len(s.build.cards),
            "model": s.model_name,
        }

    @app.post("/search")
    def search(req: SearchRequest) -> dict:
        return answer(app.state.rag, req.question)

    return app


app = create_app()

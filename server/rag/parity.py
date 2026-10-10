"""서버 검색 함수로 749문항 대리 평가를 다시 잰다 — 보고서 v2(0.311/0.411/0.462/0.542)와 같아야 한다.

사용법:
    uv run --env-file .env python -m server.rag.parity --vectors db      # 서버와 같이 Supabase 벡터로
    RETRIEVAL_CACHE=<캐시 폴더> uv run python -m server.rag.parity --vectors local   # 연구 캐시 벡터로 (DB 적재 전)
"""

import argparse
import json

from scripts.defect_precedent.retrieval_compare import card_text, load, score
from server.rag import embeddings
from server.rag.build import load_build
from server.rag.search import Searcher


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--vectors", choices=["db", "local"], required=True)
    a = p.parse_args(argv)
    from fastembed import TextEmbedding

    build = load_build()
    embeddings.check_fastembed()
    model = TextEmbedding(embeddings.MODEL)
    texts = [card_text(c) for c in build.cards]
    if a.vectors == "db":
        from scripts.defect_precedent.load_db import connect

        with connect() as conn:
            vecs = embeddings.fetch(conn, build.build_id, [c["campno"] for c in build.cards], texts)
    else:
        from scripts.defect_precedent.retrieval_compare import embed_cards

        _, vecs, _, _ = embed_cards(embeddings.MODEL, texts)
    embeddings.verify_probe(model, texts, vecs)
    searcher = Searcher(build.cards, vecs, model)
    _, questions = load()
    qv = searcher.query_vectors([q["question"] for q in questions])
    rankings = [
        searcher.search(q["question"], v).ranking for q, v in zip(questions, qv, strict=True)
    ]
    print(
        json.dumps(
            {"build_id": build.build_id, "vectors": a.vectors, **score(rankings, questions)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

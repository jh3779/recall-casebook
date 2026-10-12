"""서버 검색 함수로 749문항 대리 평가를 다시 잰다 — 보고서 v2(0.311/0.411/0.462/0.542)와 같아야 한다.

같은 입력(카드·시험지 sha256이 보고서와 같음)일 때만 비교하고, 3자리 반올림 점수가 하나라도 다르면 종료 코드 1로 끝난다.
화면에 보이는 구성(고객사 최대 5건 + 그 밖 10건, DEC-042)의 정답 포함률도 따로 낸다 — 이 값은 보고서에 없어 비교하지 않는다.

사용법:
    uv run --env-file .env python -m server.rag.parity --vectors db      # 서버와 같이 Supabase 벡터로
    RETRIEVAL_CACHE=<캐시 폴더> uv run python -m server.rag.parity --vectors local   # 연구 캐시 벡터로 (DB 적재 전)
    uv run python -m server.rag.parity --vectors bundle --bundle <serving_….tar>   # 서빙 묶음의 카드·벡터·모델로 (배포 경로, DEC-049)
    uv run python -m server.rag.parity --stats   # 벡터 없이: 전체 카드의 응답 모델 통과·조사 연결·꼬리표 수 (DEC-044 검증 수치)
"""

import argparse
import json
import sys
from collections import Counter

from scripts.defect_precedent.retrieval_compare import card_text, load, provenance, score
from server.rag import customers, embeddings
from server.rag.build import load_build
from server.rag.search import Searcher

# docs/실험_P2_검색방식비교.md — 데이터 판본(2절)과 v2 점수(3-A 표)
REPORT_INPUT = {"recalls_sha256": "3f996182fe2efb37", "eval_sha256": "fe5433db5c7864a0"}
REPORT_V2 = {"any@1": 0.311, "any@3": 0.411, "any@5": 0.462, "any@10": 0.542}


def card_stats(build, investigations: dict[str, list[dict]]) -> dict:
    """전체 카드를 서버 응답과 같은 경로(card_view → verify → add_checklist → 응답 모델)로 만들어 센다 — 검색은 하지 않는다."""
    from pydantic import ValidationError

    from server.api import Card, RagState, add_checklist, card_view
    from server.rag.verify import verify

    state = RagState(build, None, "stats", investigations)
    cards = [card_view(state, c["campno"], 1) for c in build.cards]
    verify(cards, {c["campno"] for c in build.cards}, build.causes, investigations)
    failed, flags = 0, Counter()
    for card in cards:
        add_checklist(state, card)
        try:
            Card.model_validate(card)
        except ValidationError:
            failed += 1
        for f in card["cause"].get("flags", []):
            flags[f"{f['kind']}·{card['cause']['status']}"] += 1
    linked = [c for c in cards if c["investigations"]]
    return {
        "cards": len(cards),
        "model_failed": failed,
        "cause_status": dict(sorted(Counter(c["cause"]["status"] for c in cards).items())),
        "flags_by_kind_and_status": dict(sorted(flags.items())),
        "investigation_linked_cards": len(linked),
        "investigation_actions": len({i["action"] for c in linked for i in c["investigations"]}),
        "cards_with_2plus_investigations": sum(len(c["investigations"]) >= 2 for c in linked),
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--vectors", choices=["db", "local", "bundle"])
    mode.add_argument(
        "--stats",
        action="store_true",
        help="검색 점수 대신 전체 카드의 응답 모델 통과·조사 연결·꼬리표 수를 낸다(벡터·DB 불필요)",
    )
    p.add_argument("--bundle", help="--vectors bundle일 때 읽을 서빙 묶음 파일")
    p.add_argument(
        "--allow-drift",
        action="store_true",
        help="입력이 보고서와 달라도 점수를 낸다 — 재현이 아니라 재평가로 표시하고 보고서와 비교하지 않는다",
    )
    a = p.parse_args(argv)
    if a.stats and a.allow_drift:
        p.error("--allow-drift는 검색 점수(--vectors)에만 쓴다")
    if (a.vectors == "bundle") != bool(a.bundle):
        p.error("--bundle은 --vectors bundle과 함께만 쓴다")
    if a.stats:
        from server.rag.investigations import load_investigations

        build = load_build()
        invs = load_investigations(build.raw_manifest_sha256, {c["campno"] for c in build.cards})
        out = {"build_id": build.build_id, **card_stats(build, invs)}
        print(json.dumps(out, ensure_ascii=False))
        if out["model_failed"]:
            sys.exit(f"응답 모델을 통과하지 못한 카드 {out['model_failed']}장")
        return
    from fastembed import TextEmbedding

    data = provenance()
    drift = {k: data[k] for k in REPORT_INPUT} != REPORT_INPUT
    if drift and not a.allow_drift:
        sys.exit(
            f"입력이 보고서와 다르다({data}) — 재현이 아니라 재평가다. 점수를 보려면 --allow-drift (AGENTS.md 5-1)"
        )
    build = load_build()
    embeddings.check_fastembed()
    model_path = None
    if a.vectors == "bundle":
        import atexit
        import shutil
        import tempfile
        from pathlib import Path

        from server.rag.bundle import check_identity, load_bundle, sha256_file

        bundle_path = Path(
            a.bundle
        )  # 로컬에서 만든 묶음을 재는 것이라 그 파일 자신의 sha256으로 연다(기록 대조는 서버 경로)
        work = Path(tempfile.mkdtemp(prefix="parity_bundle_"))
        atexit.register(shutil.rmtree, work, True)  # 풀어 쓴 모델 폴더(약 67MB)를 끝날 때 지운다
        loaded = load_bundle(bundle_path, work, sha256_file(bundle_path))
        check_identity(
            loaded, build
        )  # 카드·원인·명세 전체와 모델·fastembed 판본이 로컬 입력과 같을 때만 '재현'
        build, model_path = loaded.build, str(loaded.model_dir)
    model = TextEmbedding(embeddings.MODEL, specific_model_path=model_path)
    texts = [card_text(c) for c in build.cards]
    if a.vectors == "bundle":
        vecs = loaded.vectors
    elif a.vectors == "db":
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
    by_id = {c["campno"]: c for c in build.cards}
    shown_hits = 0
    for q, ranking in zip(questions, rankings, strict=True):
        cust, others = customers.split(ranking, by_id)
        shown = {ranking[i] for i in cust + others}
        shown_hits += any(g in shown for g in q["gold_campnos"])
    scores = score(rankings, questions)
    got = {k: scores["all"][k] for k in REPORT_V2}
    print(
        json.dumps(
            {
                "build_id": build.build_id,
                "vectors": a.vectors,
                **scores,
                "shown_any": round(shown_hits / len(questions), 3),
                "kind": "재평가(입력이 보고서와 다름)" if drift else "재현",
                "matches_report_v2": None if drift else got == REPORT_V2,
            },
            ensure_ascii=False,
        )
    )
    if not drift and got != REPORT_V2:
        sys.exit(f"보고서 v2 {REPORT_V2}와 다르다: {got}")


if __name__ == "__main__":
    main()

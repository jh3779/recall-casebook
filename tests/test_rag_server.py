"""server/ (API 서버 검색 경로) 테스트.

DB·모델 없이 도는 테스트가 기본이다 — 가짜 임베딩 모델과 작은 build 폴더를 쓴다.
`@pg` 테스트는 pgvector가 있는 Postgres에서 돈다 (tests/test_load_db.py와 같은 TEST_DATABASE_URL·REQUIRE_DB_TESTS 규칙):
    docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=localtest -p 54329:5432 pgvector/pgvector:pg17
"""

import hashlib
import json

import numpy as np
import pytest

from server.rag import customers, embeddings
from server.rag.build import BuildMismatch, load_build
from server.rag.causes import cause_573
from server.rag.search import Searcher
from server.rag.verify import OutOfCandidates, verify
from tests.test_load_db import cause, make_data_dir, pg, pgconn, recall, write_full  # noqa: F401

FORBIDDEN_KEYS = {"applies", "verdict", "is_applicable", "recall_required"}


class FakeModel:
    """단어마다 고정된 축에 1을 더하는 가짜 임베딩 — 같은 단어가 많을수록 가깝다."""

    def _vec(self, text):
        v = np.zeros(384, dtype="float32")
        for w in text.lower().split():
            v[int(hashlib.sha256(w.strip(".,").encode()).hexdigest(), 16) % 384] += 1
        v[0] += 0.01  # 빈 글도 0벡터가 되지 않게
        return v

    def query_embed(self, texts):
        return [self._vec(t) for t in texts]

    def passage_embed(self, texts, **_):
        return [self._vec(t) for t in texts]


def full_data_dir(tmp_path, recalls, causes):
    d = make_data_dir(tmp_path, recalls=recalls)
    write_full(d, causes)
    return d


CARDS = [
    recall("24V001000", defect="Airbag inflator may rupture.", maker_group="Kia"),
    recall("23V002000", defect="Brake line may leak."),
    recall(
        "22V003000", defect="Airbag inflator housing may crack.", maker_group="Hyundai Translead"
    ),
]


def test_load_build_matches_load_db_build_id_and_rejects_changed_files(tmp_path):
    from scripts.defect_precedent import load_db

    d = full_data_dir(tmp_path, CARDS, [cause("24V001")])
    b = load_build(d)
    assert b.build_id == load_db.load_files(d, "full")["build"]["build_id"]
    assert len(b.cards) == 3 and set(b.causes) == {"24V001"}
    (d / "causes.jsonl").write_text((d / "causes.jsonl").read_text() + "\n", encoding="utf-8")
    with pytest.raises(BuildMismatch, match="causes.jsonl"):
        load_build(d)


def test_searcher_fuses_keyword_and_meaning_rankings():
    model = FakeModel()
    vecs = np.array(model.passage_embed([c["defect"] for c in CARDS]))
    r = Searcher(CARDS, vecs, model).search("airbag inflator rupture")
    assert r.ranking[0] == "24V001000"
    assert r.candidates == frozenset(r.ranking)


def test_searcher_matches_research_v2_calculation():
    """retrieval_compare v2와 같은 계산: BM25 상위 100 + 뜻 검색 상위 100 → rrf.

    연구 코드는 질문 749개를 행렬로 한 번에 곱하고 서버는 질문마다 곱한다 — 부동소수 반올림이 달라 **값이 같은(동점) 카드**의
    순서는 바뀔 수 있다. 그래서 동점이 없는 연속값 벡터로 계산 순서를 고정하고, 실제 데이터의 점수 재현은
    `server.rag.parity`(보고서 v2와 3자리 점수가 다르면 종료 코드 1)로 확인한다."""
    from scripts.defect_precedent.bm25_baseline import tokenize
    from scripts.defect_precedent.retrieval_compare import bm25_rankings, card_text, rrf

    words = (
        "brake airbag fuel leak crack wire fire seat belt latch weld rust valve pump hose".split()
    )
    rng = np.random.default_rng(1)
    cards = [
        recall(
            f"2{i:04d}0000"[:9], defect=" ".join(rng.choice(words, 6)), consequence="", remedy=""
        )
        for i in range(240)
    ]

    class ContinuousModel:
        def _vec(self, text):
            seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
            return np.random.default_rng(seed).standard_normal(384).astype("float32")

        def query_embed(self, texts):
            return [self._vec("q:" + t) for t in texts]

        def passage_embed(self, texts, **_):
            return [self._vec(t) for t in texts]

    model = ContinuousModel()
    vecs = np.array(model.passage_embed([c["campno"] + card_text(c) for c in cards]))
    ids = [c["campno"] for c in cards]
    questions = [" ".join(rng.choice(words, 3)) for _ in range(20)]
    bm, _ = bm25_rankings(
        [tokenize(card_text(c)) for c in cards], [tokenize(q) for q in questions], ids
    )
    nv = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    searcher = Searcher(cards, vecs, model)
    qv = searcher.query_vectors(questions)
    dense = [[ids[i] for i in np.argsort(-row)[:100]] for row in qv @ nv.T]
    for q, v, b, dn in zip(questions, qv, bm, dense, strict=True):
        assert searcher.search(q, v).ranking == rrf(b, dn)


def test_customers_use_allowlist_not_name_matching():
    by_id = {c["campno"]: c for c in CARDS}
    ranking = ["22V003000", "24V001000", "23V002000"]
    cust, others = customers.split(ranking, by_id)
    assert [ranking[i] for i in cust] == ["24V001000"]  # Hyundai Translead는 고객사가 아니다
    assert [ranking[i] for i in others] == ["22V003000", "23V002000"]


@pytest.mark.parametrize(
    ("row", "status"),
    [
        (None, "no_573_report"),
        (cause("24V001", resolution="unresolved"), "version_unresolved"),
        (cause("24V001", cause_text="", cause_status="empty"), "cause_empty"),
        (cause("24V001", cause_text=None, cause_status="no_field"), "cause_no_field"),
    ],
)
def test_cause_573_hides_text_when_missing_or_version_unknown(row, status):
    got = cause_573(CARDS[0], {} if row is None else {"24V001": row})
    assert got["status"] == status and "text" not in got


def test_cause_573_marks_reports_we_could_not_read_instead_of_missing():
    got = cause_573(CARDS[0], {}, {"24V001": "non_pdf_response"})
    assert got == {
        "status": "report_unreadable",
        "campaign": "24V001",
        "reason": "non_pdf_response",
    }


def test_load_build_keeps_unreadable_campaigns_from_manifest(tmp_path):
    d = make_data_dir(tmp_path, recalls=CARDS)
    write_full(d, [cause("23V002")], failed_kinds={"24V001": "no_confirmable_date"})
    assert load_build(d).unreadable == {"24V001": "no_confirmable_date"}


def test_cause_573_copies_text_verbatim_with_speaker_and_source():
    row = cause("24V001", pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32})
    got = cause_573(CARDS[0], {"24V001": row})
    assert got["text"] == row["cause_text"]
    assert got["speaker"].startswith("리콜 제조사")
    assert got["source"]["pdf_sha256"] == "cd" * 32


def test_verify_rejects_campno_outside_candidates_and_drops_altered_cause():
    causes = {"24V001": cause("24V001", pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32})}
    card = {"campno": "24V001000", "cause": cause_573(CARDS[0], causes) | {"text": "changed"}}
    card["cause"]["source"] = {"campaign": "24V001"}
    with pytest.raises(OutOfCandidates):
        verify([dict(card)], frozenset({"23V002000"}), causes)
    out = verify([card], frozenset({"24V001000"}), causes)
    assert out[0]["cause"]["status"] == "verify_failed"


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_api_returns_build_id_and_no_judgement_fields(tmp_path):
    from fastapi.testclient import TestClient

    from server.api import RagState, create_app

    d = full_data_dir(
        tmp_path, CARDS, [cause("24V001", pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32})]
    )
    b = load_build(d)
    model = FakeModel()
    vecs = np.array(model.passage_embed([c["defect"] for c in b.cards]))
    state = RagState(b, Searcher(b.cards, vecs, model), "fake")
    with TestClient(create_app(lambda: state)) as client:
        assert client.get("/health").json()["build_id"] == b.build_id
        res = client.post("/search", json={"question": "airbag inflator rupture"})
        for bad in ("", "   ", "에어백 인플레이터 파열", "123"):
            assert client.post("/search", json={"question": bad}).status_code == 422
    body = res.json()
    assert body["build_id"] == b.build_id
    assert [c["campno"] for c in body["customer_precedents"]] == ["24V001000"]
    assert body["customer_precedents"][0]["cause"]["status"] == "filled"
    assert FORBIDDEN_KEYS.isdisjoint(set(_keys(body)))


def test_verify_probe_and_fastembed_version_refuse_mismatched_vectors(monkeypatch):
    import fastembed

    model = FakeModel()
    texts = [c["defect"] for c in CARDS]
    vecs = np.array(model.passage_embed(texts))
    embeddings.verify_probe(model, texts, vecs)
    with pytest.raises(embeddings.EmbeddingMismatch):
        embeddings.verify_probe(model, texts, vecs + 1.0)
    monkeypatch.setattr(fastembed, "__version__", "0.0.1")
    with pytest.raises(embeddings.EmbeddingMismatch, match="0.0.1"):
        embeddings.check_fastembed()


def test_probe_indices_match_research_cache_check(monkeypatch, tmp_path):
    """embed_cards가 캐시를 대조할 때 고르는 카드와 서버가 고르는 카드가 같아야 한다."""
    import fastembed

    from scripts.defect_precedent import retrieval_compare

    seen = []

    class Recorder(FakeModel):
        def __init__(self, _name):
            pass

        def passage_embed(self, texts, **kw):
            seen.append(list(texts))
            return super().passage_embed(texts)

    monkeypatch.setattr(fastembed, "TextEmbedding", Recorder)
    monkeypatch.setattr(retrieval_compare, "CACHE", tmp_path)
    texts = [f"card {i}" for i in range(50)]
    retrieval_compare.embed_cards("fake/model", texts)
    assert seen[0] == [texts[i] for i in embeddings.probe_indices(len(texts))]


@pg
def test_pg_embeddings_round_trip_exactly_and_refuse_overwrite(pgconn, tmp_path, monkeypatch):  # noqa: F811
    from scripts.defect_precedent import load_db
    from scripts.defect_precedent.retrieval_compare import FASTEMBED_VERSION, card_text
    from server.rag import build as build_mod

    d = full_data_dir(tmp_path, CARDS, [cause("24V001")])
    load_db.main(["load", "--causes", "full", "--data-dir", str(d)])
    embeddings.main(["schema"])
    embeddings.main(["schema"])  # 여러 번 적용해도 된다
    b = load_build(d)
    texts = [card_text(c) for c in b.cards]
    rng = np.random.default_rng(0)
    vecs = rng.standard_normal((len(texts), 384)).astype("float32")
    monkeypatch.setattr(build_mod, "PROCESSED", d)
    monkeypatch.setattr(embeddings, "check_fastembed", lambda: None)
    monkeypatch.setattr(
        "scripts.defect_precedent.retrieval_compare.embed_cards",
        lambda model, t: (
            None,
            vecs,
            0.0,
            {"model_fingerprint": "f" * 16, "cache_verified": False},
        ),
    )
    monkeypatch.setattr("server.rag.build.load_build", lambda: load_build(d))
    embeddings.main(["load"])
    embeddings.main(["load"])  # 같은 build는 그대로 두고 끝난다
    got = embeddings.fetch(pgconn, b.build_id, [c["campno"] for c in b.cards], texts)
    with pytest.raises(embeddings.EmbeddingMismatch, match="없다"):
        embeddings.fetch(pgconn, b.build_id, [c["campno"] for c in b.cards], texts, model="other")
    pgconn.execute("update embedding_sets set fastembed_version = '0.0.1'")
    with pytest.raises(SystemExit, match="덮어쓰지 않는다"):
        embeddings.main(["load"])  # 판본이 다른 세트는 "같다"고 넘기지 않고 멈춘다
    pgconn.execute("update embedding_sets set fastembed_version = %s", (FASTEMBED_VERSION,))
    assert np.array_equal(got, vecs)  # float32 값이 그대로 돌아온다
    with pytest.raises(embeddings.EmbeddingMismatch, match="다르다"):
        embeddings.fetch(pgconn, b.build_id, [c["campno"] for c in b.cards], [*texts[:-1], "x"])
    assert (
        json.loads(json.dumps(pgconn.execute("select rows from embedding_sets").fetchone()[0])) == 3
    )

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
        assert client.post("/search", json={"question": ""}).status_code == 422
    body = res.json()
    assert body["build_id"] == b.build_id
    assert [c["campno"] for c in body["customer_precedents"]] == ["24V001000"]
    assert body["customer_precedents"][0]["cause"]["status"] == "filled"
    assert FORBIDDEN_KEYS.isdisjoint(set(_keys(body)))


@pg
def test_pg_embeddings_round_trip_exactly_and_refuse_overwrite(pgconn, tmp_path, monkeypatch):  # noqa: F811
    from scripts.defect_precedent import load_db
    from scripts.defect_precedent.retrieval_compare import card_text
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
    assert np.array_equal(got, vecs)  # float32 값이 그대로 돌아온다
    with pytest.raises(embeddings.EmbeddingMismatch, match="다르다"):
        embeddings.fetch(pgconn, b.build_id, [c["campno"] for c in b.cards], [*texts[:-1], "x"])
    assert (
        json.loads(json.dumps(pgconn.execute("select rows from embedding_sets").fetchone()[0])) == 3
    )

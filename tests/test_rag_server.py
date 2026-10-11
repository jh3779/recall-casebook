"""server/ (API 서버 검색 경로) 테스트.

DB·모델 없이 도는 테스트가 기본이다 — 가짜 임베딩 모델과 작은 build 폴더를 쓴다.
`@pg` 테스트는 pgvector가 있는 Postgres에서 돈다 (tests/test_load_db.py와 같은 TEST_DATABASE_URL·REQUIRE_DB_TESTS 규칙):
    docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=localtest -e POSTGRES_DB=lgcns_test -p 54329:5432 pgvector/pgvector:pg17
"""

import hashlib
import json

import numpy as np
import pytest

from server.rag import customers, embeddings
from server.rag.build import BuildMismatch, check_against_db, load_build
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


def test_cause_573_says_no_report_only_outside_the_573_collection_range():
    old = recall("13V001000", received_date="20130101")
    assert cause_573(old, {}) == {"status": "no_573_report"}
    # 범위 안인데 원문 목록에도 실패 목록에도 없으면 "없다"고 하지 않는다
    assert cause_573(CARDS[0], {}) == {"status": "report_status_unknown", "campaign": "24V001"}


@pytest.mark.parametrize(
    ("row", "status"),
    [
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


def _with_failure(tmp_path, kinds):
    d = make_data_dir(tmp_path, recalls=CARDS)
    write_full(
        d,
        [cause("23V002")],
        failures=1,
        failed_campaigns=["24V001"],
        failed_kinds=kinds,
        expect_campaigns=2,
    )
    return d


def test_load_build_keeps_unreadable_campaigns_from_manifest(tmp_path):
    assert load_build(_with_failure(tmp_path, {"24V001": "no_confirmable_date"})).unreadable == {
        "24V001": "no_confirmable_date"
    }


def test_load_build_rejects_empty_failure_reasons(tmp_path):
    with pytest.raises(BuildMismatch, match="빈 값"):
        load_build(_with_failure(tmp_path, {"24V001": None}))


@pytest.mark.parametrize(
    "cause",
    [
        {"status": "report_unreadable", "campaign": "24V001"},  # 사유 없음
        {"status": "report_unreadable", "campaign": "24V001", "reason": ""},
        {"status": "report_status_unknown"},  # 캠페인 번호 없음
        {"status": "no_573_report", "campaign": "x", "reason": "y"},  # 모델 밖 칸
        # stated_unknown도 원문·말한 주체·출처(정리 방식 포함)가 반드시 있어야 한다(DEC-047, PR #82 리뷰)
        {"status": "stated_unknown", "text": "NR", "speaker": "s", "flags": []},
        {
            "status": "stated_unknown",
            "text": "NR",
            "speaker": "s",
            "flags": [],
            "source": {
                "campaign": "24V001",
                "file": "f",
                "pdf_sha256": "ab" * 32,
                "submission_date": "20240101",
            },
        },  # text_basis 없음
    ],
)
def test_card_model_requires_fields_for_each_cause_status(cause):
    from pydantic import ValidationError

    from server.api import CARD_TEXT_SPEAKER, Card

    card = {
        "rank": 1, "campno": "24V001000", "maker": "m", "maker_group": "Kia", "received_date": "20240101",
        "components": [], "defect": "", "consequence": "", "remedy": "", "dup_group": "24V001000",
        "source": {"dataset": "NHTSA FLAT_RCL", "snapshot_date": "2026-10-06", "speaker": CARD_TEXT_SPEAKER},
        "investigations": [], "checklist": [],
    }  # fmt: skip
    Card.model_validate(
        {**card, "cause": {"status": "no_573_report"}}
    )  # 나머지 칸은 맞다 — 실패는 cause 때문이어야 한다
    with pytest.raises(ValidationError):
        Card.model_validate({**card, "cause": cause})


def test_load_build_rejects_failure_reasons_that_do_not_match_failed_campaigns(tmp_path):
    with pytest.raises(BuildMismatch, match="failed_kinds"):
        load_build(_with_failure(tmp_path, {"22V003": "non_pdf_response"}))


class FakeConn:
    def __init__(self, row):
        self.row = row

    def execute(self, *_):
        return self

    def fetchone(self):
        return self.row


def test_check_against_db_rejects_a_spec_that_differs_from_the_loaded_build(tmp_path):
    b = load_build(_with_failure(tmp_path, {"24V001": "no_confirmable_date"}))
    check_against_db(FakeConn((b.causes_spec,)), b)
    changed = {**b.causes_spec, "failed_kinds": {"24V001": "non_pdf_response"}}
    with pytest.raises(BuildMismatch, match="DB에 적재된 것과 다르다"):
        check_against_db(FakeConn((changed,)), b)  # 같은 build_id인데 실패 사유만 바꾼 명세
    with pytest.raises(BuildMismatch, match="DB에 없다"):
        check_against_db(FakeConn(None), b)


def loaded(row, basis="rclrpt-test; pdftotext-layout"):
    """load_build가 원인 행에 붙이는 것처럼 — 이 build의 원인 글 정리 방식(명세의 text_basis)을 얹는다(DEC-047)."""
    return {**row, "text_basis": basis}


def test_cause_573_copies_text_verbatim_with_speaker_and_source():
    row = loaded(cause("24V001", pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32}))
    got = cause_573(CARDS[0], {"24V001": row})
    assert got["text"] == row["cause_text"]
    assert got["speaker"].startswith("리콜 제조사")
    assert got["source"]["pdf_sha256"] == "cd" * 32


def test_verify_rejects_campno_outside_candidates_and_drops_altered_cause():
    causes = {
        "24V001": loaded(cause("24V001", pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32}))
    }
    card = {"campno": "24V001000", "cause": cause_573(CARDS[0], causes) | {"text": "changed"}}
    card["cause"]["source"] = {"campaign": "24V001"}
    with pytest.raises(OutOfCandidates):
        verify([dict(card)], frozenset({"23V002000"}), causes)
    out = verify([card], frozenset({"24V001000"}), causes)
    assert out[0]["cause"]["status"] == "verify_failed"


def test_verify_also_checks_stated_unknown_text_against_the_source():
    """미보고·조사 중 서술도 원문 대조를 거친다 — 글이 바뀌면 빼고 verify_failed(DEC-047, PR #82 리뷰)."""
    row = loaded(
        cause(
            "24V001",
            text="NR",
            cause_status="stated_unknown",
            pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32},
        )
    )
    causes = {"24V001": row}
    card = {"campno": "24V001000", "cause": cause_573(CARDS[0], causes) | {"text": "Not reported"}}
    assert verify([card], frozenset({"24V001000"}), causes)[0]["cause"]["status"] == "verify_failed"
    same = {"campno": "24V001000", "cause": cause_573(CARDS[0], causes)}
    assert (
        verify([same], frozenset({"24V001000"}), causes)[0]["cause"]["status"] == "stated_unknown"
    )


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_api_returns_build_id_and_no_judgement_fields(tmp_path, monkeypatch):
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
        assert client.post("/search", json={"question": "4wd"}).status_code == 200
        for bad in ("", "   ", "에어백 인플레이터 파열", "123"):
            assert client.post("/search", json={"question": bad}).status_code == 422
    body = res.json()

    from fastapi.exceptions import ResponseValidationError

    import server.api as api_mod

    real = api_mod.cause_573

    def without_speaker(*a):
        c = real(*a)
        c.pop("speaker", None)  # 원문은 그대로 두고 말한 주체만 뺀다 (원문 대조는 통과)
        return c

    monkeypatch.setattr(api_mod, "cause_573", without_speaker)
    with TestClient(create_app(lambda: state)) as client, pytest.raises(ResponseValidationError):
        client.post("/search", json={"question": "airbag inflator rupture"})
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
    # 로컬 사본: 처음엔 DB에서 받아 쓰고, 사본이 DB와 다르면 버리고 다시 받는다
    cache = tmp_path / "vector_cache"
    campnos = [c["campno"] for c in b.cards]
    assert np.array_equal(embeddings.load_vectors(pgconn, b.build_id, campnos, texts, cache), vecs)
    (path,) = cache.glob("*.npy")
    digest = path.with_suffix(".sha256")
    # ① 내용이 바뀐 사본(sha256 불일치) ② 잘린 사본 ③ sha256까지 맞춰 바꾼 사본(DB 표본 대조로 잡음) — 모두 다시 받는다
    for damage in ("changed", "truncated", "changed_with_digest"):
        if damage == "truncated":
            path.write_bytes(path.read_bytes()[:500])
        else:
            np.save(path, np.zeros_like(vecs))
            if damage == "changed_with_digest":
                digest.write_text(hashlib.sha256(path.read_bytes()).hexdigest())
        got = embeddings.load_vectors(pgconn, b.build_id, campnos, texts, cache)
        assert np.array_equal(got, vecs), damage
        assert np.array_equal(np.load(path), vecs)  # 사본도 DB 값으로 다시 썼다
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


def test_server_connection_needs_reader_url_or_explicit_admin_opt_in(monkeypatch):
    from server.api import server_connection

    monkeypatch.delenv("SERVER_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin@localhost:1/x")
    monkeypatch.delenv("ALLOW_ADMIN_DB_FOR_SERVER", raising=False)
    with pytest.raises(RuntimeError, match="SERVER_DATABASE_URL"):
        server_connection()  # 관리자 연결이 있어도 직접 허용하지 않으면 쓰지 않는다


def _readme_reader_sql(role: str, password: str) -> str:
    """server/README.md 3단계의 조회 전용 계정 SQL을 그대로 꺼낸다 (문서와 테스트가 같은 SQL을 쓰게)."""
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "server" / "README.md").read_text(
        encoding="utf-8"
    )
    block = re.search(r"```sql\n(.*?create role rag_reader.*?)```", text, re.S).group(1)
    block = "\n".join(line.strip() for line in block.splitlines())
    return block.replace("<직접 정한 비밀번호>", password).replace("rag_reader", role)


@pg
def test_pg_spec_check_and_readme_reader_role(pgconn, tmp_path, monkeypatch):  # noqa: F811
    import psycopg

    from tests.test_load_db import PG_URL

    d = _with_failure(tmp_path, {"24V001": "no_confirmable_date"})
    from scripts.defect_precedent import load_db

    load_db.main(["load", "--causes", "full", "--data-dir", str(d)])
    embeddings.main(["schema"])
    b = load_build(d)
    check_against_db(pgconn, b)  # jsonb로 저장·조회한 명세가 로컬 명세와 같게 읽힌다

    role = "rag_reader_test"
    if pgconn.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
        pgconn.execute(f"drop owned by {role}")
        pgconn.execute(f"drop role {role}")
    pgconn.execute(_readme_reader_sql(role, "localtest-reader"))
    try:
        url = PG_URL.replace("postgres:localtest@", f"{role}:localtest-reader@", 1)
        monkeypatch.setenv("SERVER_DATABASE_URL", url)
        from server.api import server_connection

        with server_connection() as conn:
            check_against_db(conn, b)
            assert conn.execute("select count(*) from embedding_sets").fetchone()[0] == 0
            for sql in (
                "delete from data_builds",
                "select count(*) from recalls",
                "insert into embedding_sets (build_id) values ('x')",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql)
                conn.rollback()
    finally:
        pgconn.execute(f"drop owned by {role}")
        pgconn.execute(f"drop role {role}")


# ---------------------------------------------------------------------------
# PR 2 — 조사 요약 원인·표시 꼬리표·확인 항목


def test_flags_mark_unknown_and_hedge_expressions_with_verbatim_spans():
    from server.rag.flags import flags

    text = "The root cause has not been determined. It appears to be a supplier weld issue, likely moisture."
    got = {f["kind"]: [s["text"] for s in f["spans"]] for f in flags(text)}
    assert got == {
        "unknown_expression": [
            "root cause has not"
        ],  # 기존 규칙(UNKNOWN_RE)이 앞쪽 표현을 먼저 잡는다
        "hedge_expression": ["appears to", "likely"],
    }
    for f in flags(text):
        for s in f["spans"]:
            assert text[s["start"] : s["end"]] == s["text"]


def test_flags_do_not_treat_may_or_could_as_hedges():
    from server.rag.flags import flags

    assert flags("A cracked hose may result in a fuel leak, which could cause a fire.") == []


def _write_inv(raw_dir, rows):
    """FLAT_INV.zip(탭 구분) + manifest.json — sha256은 실제 파일에서 계산한다."""
    import zipfile

    from scripts.defect_precedent.nhtsa import INV_COLS

    raw_dir.mkdir(parents=True, exist_ok=True)
    body = "".join("\t".join(r.get(c, "") for c in INV_COLS) + "\n" for r in rows)
    with zipfile.ZipFile(raw_dir / "FLAT_INV.zip", "w") as zf:
        zf.writestr("FLAT_INV.txt", body)
    manifest = {"files": {"FLAT_INV.zip": {"sha256": sha256_file(raw_dir / "FLAT_INV.zip")}}}
    (raw_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return sha256_file(raw_dir / "manifest.json")


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inv_row(action, campno, summary="Owners report the airbag inflator ruptured.", **kw):
    return {
        "ACTION": action,
        "CAMPNO": campno,
        "SUMMARY": summary,
        "SUBJECT": "Airbag",
        "ODATE": "20200101",
        "CDATE": "20210101",
        **kw,
    }


def test_load_investigations_links_summaries_verbatim_and_skips_placeholders(tmp_path):
    from server.rag.investigations import load_investigations

    raw = tmp_path / "raw"
    digest = _write_inv(
        raw,
        [
            inv_row("PE20001", "24V001000", summary="  Spaces kept as in the source.  "),
            inv_row(
                "PE20001", "24V001000", summary="  Spaces kept as in the source.  ", MAKE="KIA"
            ),  # 같은 조사의 다른 차종 줄
            inv_row("EA19002", "24V001000"),
            inv_row("PE21003", "23V002000", summary="There is no summary currently available"),
            inv_row("PE21004", "99V999000"),  # 카드에 없는 리콜
        ],
    )
    got = load_investigations(digest, {"24V001000", "23V002000"}, raw)
    assert list(got) == ["24V001000"]
    assert [i["action"] for i in got["24V001000"]] == ["EA19002", "PE20001"]
    assert got["24V001000"][1]["summary"] == "  Spaces kept as in the source.  "


def test_load_investigations_refuses_other_snapshots_and_conflicting_summaries(tmp_path):
    from server.rag.investigations import load_investigations

    raw = tmp_path / "raw"
    digest = _write_inv(raw, [inv_row("PE20001", "24V001000")])
    with pytest.raises(BuildMismatch, match="raw_manifest_sha256"):
        load_investigations("0" * 64, {"24V001000"}, raw)
    (raw / "FLAT_INV.zip").write_bytes(b"changed")
    with pytest.raises(BuildMismatch, match="FLAT_INV.zip"):
        load_investigations(digest, {"24V001000"}, raw)
    digest = _write_inv(
        raw,
        [inv_row("PE20001", "24V001000"), inv_row("PE20001", "24V001000", summary="Other text.")],
    )
    with pytest.raises(BuildMismatch, match="다르다"):
        load_investigations(digest, {"24V001000"}, raw)
    # 같은 조사 번호의 다른 리콜 번호 줄(카드에 없음)이 다른 요약이거나, 제목만 달라도 짐작하지 않는다
    for other in (
        inv_row("PE20001", "99V999000", summary="Revised text."),
        inv_row("PE20001", "24V001000", SUBJECT="Another subject"),
    ):
        digest = _write_inv(raw, [inv_row("PE20001", "24V001000"), other])
        with pytest.raises(BuildMismatch, match="다르다"):
            load_investigations(digest, {"24V001000"}, raw)


def test_checklist_links_evidence_and_skips_items_without_it():
    from server.rag.causes import SPEAKER_573
    from server.rag.checks import checklist
    from server.rag.investigations import SPEAKER_INV

    card = recall(
        "24V001000",
        defect="Airbag inflator may rupture.",
        consequence="",
        remedy="Replace the inflator.",
    )
    filled = {"status": "filled"}
    row = cause("24V001", supplier_names=["ARC Automotive"])
    inv = [{"action": "PE20001"}]
    items = {c["item"]: c["evidence"] for c in checklist(card, row, inv, filled)}
    assert list(items) == ["same_part", "failure_mode", "remedy", "supplier", "cause_speaker"]
    assert [e["field"] for e in items["same_part"]] == ["components"]
    assert items["failure_mode"] == [
        {"field": "defect", "text": "Airbag inflator may rupture."}
    ]  # 결과 원문은 비어 빠짐
    assert items["supplier"] == [{"field": "573.supplier_names", "text": "ARC Automotive"}]
    assert items["cause_speaker"] == [
        {"field": "cause.speaker", "text": SPEAKER_573},
        {"field": "investigations.speaker", "text": SPEAKER_INV},
        {"field": "investigations.action", "text": "PE20001"},  # 원본 조사 번호 그대로
    ]
    stated = [
        c
        for c in checklist(card, row, [], {"status": "stated_unknown"})
        if c["item"] == "cause_speaker"
    ]
    assert stated[0]["evidence"] == [
        {"field": "cause.speaker", "text": SPEAKER_573}
    ]  # 미보고 서술도 말한 주체를 보인다
    bare = {**card, "defect": "", "remedy": ""}
    assert [c["item"] for c in checklist(bare, None, [], {"status": "no_573_report"})] == [
        "same_part"
    ]
    unresolved = {**row, "resolution": "unresolved"}
    assert "supplier" not in {
        c["item"] for c in checklist(card, unresolved, [], {"status": "version_unresolved"})
    }


def test_verify_refuses_altered_investigation_summary_or_wrong_cause_flag_span():
    from server.rag.flags import flags
    from server.rag.verify import NotVerbatim

    original = "The cause is likely corrosion."
    invs = {"24V001000": [{"action": "PE20001", "summary": original}]}
    card = {"campno": "24V001000", "cause": {"status": "no_573_report"},
            "investigations": [{"action": "PE20001", "summary": original}]}  # fmt: skip
    verify([card], frozenset({"24V001000"}), {}, invs)
    bad = {**card, "investigations": [{"action": "PE20001", "summary": original + " "}]}
    with pytest.raises(NotVerbatim):
        verify([bad], frozenset({"24V001000"}), {}, invs)

    row = cause("24V001", cause_text=original)
    good = {"campno": "24V001000", "investigations": [],
            "cause": {"status": "filled", "text": original, "flags": flags(original),
                      "source": {"campaign": "24V001"}}}  # fmt: skip
    verify([good], frozenset({"24V001000"}), {"24V001": row})
    wrong = [
        {"kind": "hedge_expression", "label": "x", "spans": [{"start": 0, "end": 3, "text": "Thx"}]}
    ]
    with pytest.raises(NotVerbatim):  # 573 원인 글의 꼬리표 구간이 원문과 다르다
        verify(
            [{**good, "cause": {**good["cause"], "flags": wrong}}],
            frozenset({"24V001000"}),
            {"24V001": row},
        )


def test_api_returns_investigations_and_checklist(tmp_path):
    from fastapi.testclient import TestClient

    from server.api import RagState, create_app

    d = full_data_dir(
        tmp_path, CARDS, [cause("24V001", pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32})]
    )
    b = load_build(d)
    model = FakeModel()
    vecs = np.array(model.passage_embed([c["defect"] for c in b.cards]))
    invs = {"24V001000": [{"action": "PE20001", "subject": "Airbag", "summary": "Inflator likely ruptured.",
                           "open_date": "20200101", "close_date": "20210101"}]}  # fmt: skip
    state = RagState(b, Searcher(b.cards, vecs, model), "fake", invs)
    with TestClient(create_app(lambda: state)) as client:
        body = client.post("/search", json={"question": "airbag inflator rupture"}).json()
    card = body["customer_precedents"][0]
    assert card["investigations"][0]["speaker"].startswith("NHTSA")
    assert "flags" not in card["investigations"][0]  # 꼬리표는 573 원인 칸에만 (DEC-044)
    assert {c["item"] for c in card["checklist"]} >= {"same_part", "cause_speaker"}
    assert FORBIDDEN_KEYS.isdisjoint(set(_keys(body)))


def test_cause_573_keeps_manufacturer_stated_unknown_text_with_speaker_and_basis():
    """DEC-047: 원인 칸에 "NR"·"조사 중"을 적은 경우도 원문 그대로, 말한 주체·출처·정리 방식과 함께 싣는다."""
    from scripts.defect_precedent.rclrpt import CAUSE_TEXT_BASIS
    from server.rag.causes import SPEAKER_573

    pdf = {"pdfs": {"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "ab" * 32}}
    row = loaded(
        cause("24V001", text="Still being investigated.", cause_status="stated_unknown", **pdf),
        CAUSE_TEXT_BASIS,
    )
    got = cause_573(CARDS[0], {"24V001": row})
    assert (got["status"], got["text"], got["speaker"]) == (
        "stated_unknown",
        "Still being investigated.",
        SPEAKER_573,
    )
    assert got["source"]["text_basis"] == CAUSE_TEXT_BASIS
    filled = cause_573(CARDS[0], {"24V001": loaded(cause("24V001", **pdf), "rclrpt-old; other")})
    assert (
        filled["source"]["text_basis"] == "rclrpt-old; other"
    )  # 서버 상수가 아니라 그 build의 기록을 쓴다


def test_load_build_takes_text_basis_from_manifest_and_refuses_files_without_it(tmp_path):
    """원인 글 정리 방식은 build의 원인 명세에서 읽는다 — 기록이 없는 옛 원인 파일로는 서버를 띄우지 않는다(DEC-047, PR #82 Codex)."""
    d = make_data_dir(tmp_path)
    write_full(d, [cause("24V001")], text_basis="rclrpt-2099-01-01; test")
    b = load_build(d)
    assert b.causes["24V001"]["text_basis"] == "rclrpt-2099-01-01; test"
    d2 = make_data_dir(tmp_path / "old")
    write_full(d2, [cause("24V001")], text_basis=None)
    with pytest.raises(BuildMismatch, match="text_basis"):
        load_build(d2)


def test_card_source_says_who_wrote_card_text_only_as_far_as_the_source_says():
    """카드 글(FLAT_RCL)의 작성 주체는 원본 칸 설명에 없다 — 아는 출처만 적은 고정 문구여야 한다(DEC-047)."""
    from pydantic import ValidationError

    from server.api import CARD_TEXT_SPEAKER, CardSource

    ok = {"dataset": "NHTSA FLAT_RCL", "snapshot_date": "2026-10-06", "speaker": CARD_TEXT_SPEAKER}
    CardSource.model_validate(ok)
    with pytest.raises(ValidationError):
        CardSource.model_validate({**ok, "speaker": "리콜 제조사"})  # 근거 없는 주체 표시는 막는다

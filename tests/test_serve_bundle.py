"""배포 경로(RAG_SOURCE=bundle, DEC-049) — 서버가 DB 기록과 같은 서빙 묶음만 받아 쓰고, 로컬 경로와 같은 대조를 하는지."""

import contextlib
from types import SimpleNamespace

import numpy as np
import pytest

from server.rag import bundle, embeddings
from server.rag.build import BuildMismatch, load_build
from tests.test_bundle import INV, PDFS, _inputs, _sha
from tests.test_load_db import cause, pg, pgconn  # noqa: F401
from tests.test_rag_server import CARDS, FakeModel, full_data_dir


class FakeConn:
    """serving_bundles 한 줄만 돌려주는 가짜 연결."""

    def __init__(self, row):
        self.row = row

    def execute(self, sql, params=None):
        assert "serving_bundles" in sql
        return SimpleNamespace(fetchone=lambda: self.row)


def _served(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    tar = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    return b, vecs, tar, (_sha(tar), f"{b.build_id}/{_sha(tar)}.tar")


def _fake_download(src, calls):
    def f(url, dst):
        calls.append(url)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())

    return f


def test_load_from_bundle_downloads_the_recorded_bundle_once_and_restores_the_build(
    tmp_path, monkeypatch
):
    b, vecs, tar, row = _served(tmp_path)
    calls = []
    monkeypatch.setattr(bundle, "_download", _fake_download(tar, calls))
    work = tmp_path / "serve"
    got = bundle.load_from_bundle(FakeConn(row), b.build_id, "https://x.supabase.co/", work)
    assert got.sha256 == row[0]  # 서버가 응답·/health에 싣는 값
    assert got.build == b and np.array_equal(got.vectors, vecs) and got.investigations == INV
    assert calls == [f"https://x.supabase.co/storage/v1/object/public/serving-bundles/{row[1]}"]
    bundle.load_from_bundle(FakeConn(row), b.build_id, "https://x.supabase.co", work)
    assert len(calls) == 1  # 이미 받은 묶음(이름 = sha256)은 다시 받지 않는다 — 대조는 매번 한다


def test_load_from_bundle_refuses_when_no_record(tmp_path):
    with pytest.raises(bundle.BundleMismatch, match="serving_bundles"):
        bundle.load_from_bundle(FakeConn(None), "b", "https://x", tmp_path)


def test_load_from_bundle_refuses_and_deletes_a_file_other_than_the_recorded_one(
    tmp_path, monkeypatch
):
    b, _, tar, (sha, path) = _served(tmp_path)
    other = tmp_path / "other.tar"
    other.write_bytes(tar.read_bytes() + b"\0")
    monkeypatch.setattr(bundle, "_download", _fake_download(other, []))
    work = tmp_path / "serve"
    with pytest.raises(bundle.BundleMismatch, match="sha256"):
        bundle.load_from_bundle(FakeConn((sha, path)), b.build_id, "https://x", work)
    assert not (work / f"{sha}.tar").exists()  # 다음 시작 때 다시 받는다


def test_load_from_bundle_refuses_a_bundle_of_another_build(tmp_path, monkeypatch):
    b, _, tar, row = _served(tmp_path)
    monkeypatch.setattr(bundle, "_download", _fake_download(tar, []))
    with pytest.raises(bundle.BundleMismatch, match="build"):
        bundle.load_from_bundle(FakeConn(row), "other-build", "https://x", tmp_path / "s")


@pytest.mark.parametrize("what", ["fastembed", "model"])
def test_load_from_bundle_refuses_other_fastembed_version_or_model(tmp_path, monkeypatch, what):
    b, _, tar, row = _served(tmp_path)
    monkeypatch.setattr(bundle, "_download", _fake_download(tar, []))
    if what == "fastembed":
        monkeypatch.setattr(bundle, "FASTEMBED_VERSION", "0.0.0")
    else:  # 서버가 기대하는 모델 이름이 묶음 meta의 모델과 다르다
        monkeypatch.setattr(bundle.embeddings, "MODEL", "BAAI/other-model")
    with pytest.raises(bundle.BundleMismatch, match="fastembed"):
        bundle.load_from_bundle(FakeConn(row), b.build_id, "https://x", tmp_path / "s")


def test_sample_matches_compares_db_rows_exactly(monkeypatch):
    campnos = [f"{i:02d}V001000" for i in range(100)]
    vecs = np.random.default_rng(0).random((100, 384), dtype="float32")
    rows = {c: vecs[i].copy() for i, c in enumerate(campnos)}
    monkeypatch.setattr(
        embeddings, "_read_rows", lambda conn, b, m, want: ((c, rows[c]) for c in want)
    )
    assert embeddings.sample_matches(None, "b", campnos, vecs)
    rows[campnos[-1]] = rows[campnos[-1]] + 1e-6  # 마지막 줄은 늘 표본에 든다
    assert not embeddings.sample_matches(None, "b", campnos, vecs)
    assert not embeddings.sample_matches(None, "b", campnos, vecs[:99])


# ---------------------------------------------------------------------------
# load_state — 경로 고르기와 묶음 경로 순서


def test_load_state_refuses_unknown_source_and_bundle_without_build_id(monkeypatch):
    import server.api as api_mod

    monkeypatch.setenv("RAG_SOURCE", "db")
    with pytest.raises(RuntimeError, match="RAG_SOURCE"):
        api_mod.load_state()
    monkeypatch.setenv("RAG_SOURCE", "bundle")
    monkeypatch.delenv("SERVING_BUILD_ID", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://x")
    monkeypatch.setattr(
        api_mod, "server_connection", lambda: pytest.fail("build를 모르면 DB에 붙지 않는다")
    )
    with pytest.raises(RuntimeError, match="SERVING_BUILD_ID"):
        api_mod.load_state()
    monkeypatch.setenv("SERVING_BUILD_ID", "b")
    monkeypatch.delenv("SUPABASE_URL")
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        api_mod.load_state()


def test_load_state_from_bundle_checks_db_spec_vectors_sample_then_probe(monkeypatch, tmp_path):
    """묶음 경로 순서: fastembed 판본 → DB 연결 → 묶음(기록 sha256 대조) → DB 명세 → DB 벡터 기록 → DB 표본 → 모델(묶음 폴더) → 탐침.
    로컬 build 파일·조사 원본·로컬 벡터 사본은 읽지 않는다. 어느 단계든 실패하면 검색기를 만들지 않는다."""
    import fastembed

    import server.api as api_mod
    from server.rag import build as build_mod
    from server.rag import investigations as inv_mod

    b = load_build(full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)]))
    loaded = bundle.Loaded(b, INV, np.zeros((len(b.cards), 384)), tmp_path / "m", {}, "ab" * 32)
    calls, args = [], {}

    def rec(name, result=None):
        def f(*a, **k):
            calls.append((name, k) if name == "TextEmbedding" else name)
            args[name] = a
            return result

        return f

    @contextlib.contextmanager
    def fake_conn():
        calls.append("connect")
        yield object()

    monkeypatch.setenv("RAG_SOURCE", "bundle")
    monkeypatch.setenv("SERVING_BUILD_ID", b.build_id)
    monkeypatch.setenv("SUPABASE_URL", "https://x")
    for mod, name in ((build_mod, "load_build"), (inv_mod, "load_investigations")):
        monkeypatch.setattr(
            mod, name, lambda *a, _n=name, **k: pytest.fail(f"{_n}를 부르면 안 된다")
        )
    monkeypatch.setattr(embeddings, "load_vectors", lambda *a, **k: pytest.fail("load_vectors"))
    monkeypatch.setattr(embeddings, "check_fastembed", rec("check_fastembed"))
    monkeypatch.setattr(api_mod, "server_connection", fake_conn)
    monkeypatch.setattr(bundle, "load_from_bundle", rec("load_from_bundle", loaded))
    monkeypatch.setattr(build_mod, "check_against_db", rec("check_against_db"))
    monkeypatch.setattr(embeddings, "check_set", rec("check_set"))
    monkeypatch.setattr(embeddings, "sample_matches", rec("sample_matches", True))
    monkeypatch.setattr(fastembed, "TextEmbedding", rec("TextEmbedding", FakeModel()))
    monkeypatch.setattr(embeddings, "verify_probe", rec("verify_probe"))
    monkeypatch.setattr(api_mod, "Searcher", rec("Searcher"))

    state = api_mod.load_state()
    assert calls == [
        "check_fastembed", "connect", "load_from_bundle", "check_against_db", "check_set",
        "sample_matches", ("TextEmbedding", {"specific_model_path": str(tmp_path / "m")}),
        "verify_probe", "Searcher",
    ]  # fmt: skip
    assert state.build is b and state.investigations == INV and state.bundle_sha256 == "ab" * 32
    # 대조에 넘기는 값이 묶음의 카드·벡터 그대로인지 — 순서만 맞고 엉뚱한 값을 대조하는 변경을 막는다
    from scripts.defect_precedent.retrieval_compare import card_text

    campnos, texts = [c["campno"] for c in b.cards], [card_text(c) for c in b.cards]
    assert args["load_from_bundle"][1:] == (b.build_id, "https://x")
    assert args["check_against_db"][1] is b
    assert args["check_set"][1:] == (b.build_id, campnos, texts)
    assert args["sample_matches"][1:3] == (b.build_id, campnos)
    assert args["sample_matches"][3] is loaded.vectors
    assert args["verify_probe"][1] == texts and args["verify_probe"][2] is loaded.vectors
    assert args["Searcher"][0] is b.cards and args["Searcher"][1] is loaded.vectors

    for step, mod in (
        ("load_from_bundle", bundle),
        ("check_against_db", build_mod),
        ("check_set", embeddings),
        ("verify_probe", embeddings),
    ):
        calls.clear()

        def boom(*a, _step=step, **k):
            raise BuildMismatch(f"{_step} 실패")

        with monkeypatch.context() as m:
            m.setattr(mod, step, boom)
            with pytest.raises(BuildMismatch, match=step):
                api_mod.load_state()
        assert "Searcher" not in calls

    calls.clear()
    monkeypatch.setattr(embeddings, "sample_matches", rec("sample_matches", False))
    with pytest.raises(embeddings.EmbeddingMismatch, match="표본|DB에서 뽑은"):
        api_mod.load_state()
    assert "Searcher" not in calls


def test_cors_origins_come_from_env_with_local_default(monkeypatch):
    from fastapi.testclient import TestClient

    import server.api as api_mod

    def preflight(origin):
        app = api_mod.create_app(lambda: None)
        with TestClient(app) as c:
            r = c.options(
                "/search",
                headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
            )
        return r.headers.get("access-control-allow-origin")

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert preflight("http://localhost:5173") == "http://localhost:5173"
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.vercel.app, https://b.example")
    assert preflight("https://b.example") == "https://b.example"
    assert preflight("http://localhost:5173") is None


# ---------------------------------------------------------------------------
# DB — 조회 전용 계정이 묶음 기록을 읽는다


@pg
def test_pg_load_from_bundle_with_recorded_row(pgconn, tmp_path, monkeypatch):  # noqa: F811
    from scripts.defect_precedent import load_db

    d = full_data_dir(tmp_path / "pg", CARDS, [cause("24V001", pdfs=PDFS)])
    load_db.main(["load", "--causes", "full", "--data-dir", str(d)])
    b, vecs, model_dir = _inputs(tmp_path)
    embeddings.main(["schema"])
    pgconn.execute(
        "insert into embedding_sets (build_id, model, fastembed_version, texts_sha256, model_fingerprint, rows) "
        "values (%s, %s, '0.9.0', 'x', 'x', 3)",
        (b.build_id, embeddings.MODEL),
    )
    pgconn.execute(bundle.SCHEMA.read_text(encoding="utf-8"))
    tar = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    sha = _sha(tar)
    bundle.register(pgconn, b.build_id, sha, f"{b.build_id}/{sha}.tar")
    monkeypatch.setattr(bundle, "_download", _fake_download(tar, []))
    got = bundle.load_from_bundle(pgconn, b.build_id, "https://x", tmp_path / "s")
    assert got.build == b


def test_parity_bundle_mode_needs_a_bundle_file_and_only_with_it():
    from server.rag import parity

    for argv in (["--vectors", "bundle"], ["--vectors", "db", "--bundle", "x.tar"]):
        with pytest.raises(SystemExit):
            parity.main(argv)


def test_health_and_search_carry_bundle_sha256_only_when_served_from_a_bundle(tmp_path):
    from fastapi.testclient import TestClient

    import server.api as api_mod
    from server.rag.search import Searcher

    b = load_build(full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)]))
    model = FakeModel()
    vecs = np.array(model.passage_embed([c["defect"] for c in b.cards]), dtype="float32")
    for sha in (None, "ab" * 32):
        state = api_mod.RagState(b, Searcher(b.cards, vecs, model), "fake", {}, sha)
        with TestClient(api_mod.create_app(lambda s=state: s)) as c:
            assert c.get("/health").json()["bundle_sha256"] == sha
            assert c.post("/search", json={"question": "airbag"}).json()["bundle_sha256"] == sha


def test_load_from_bundle_refuses_plain_http(tmp_path):
    with pytest.raises(bundle.BundleMismatch, match="https"):
        bundle.load_from_bundle(FakeConn(("ab" * 32, "x.tar")), "b", "http://x", tmp_path)


def test_download_removes_the_partial_file_when_it_fails(tmp_path, monkeypatch):
    class Broken:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            raise OSError("연결 끊김")

    monkeypatch.setattr(bundle.urllib.request, "urlopen", lambda *a, **k: Broken())
    dst = tmp_path / "serving" / "x.tar"
    with pytest.raises(OSError):
        bundle._download("https://x/a", dst)
    assert list(dst.parent.iterdir()) == []  # 조각 파일(.tmp)도, 완성본도 없다


def test_parity_bundle_mode_scores_with_the_bundle_and_refuses_another_build(
    tmp_path, monkeypatch, capsys
):
    import json

    import fastembed

    from scripts.defect_precedent.retrieval_compare import card_text
    from server.rag import parity

    b = load_build(full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)]))
    model = FakeModel()
    vecs = np.array(model.passage_embed([card_text(c) for c in b.cards]), dtype="float32")
    _, _, model_dir = _inputs(tmp_path / "m")
    tar = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    monkeypatch.setattr(parity, "load_build", lambda: b)
    monkeypatch.setattr(parity, "provenance", lambda: {"recalls_sha256": "x", "eval_sha256": "y"})
    monkeypatch.setattr(embeddings, "check_fastembed", lambda: None)
    opened = []
    monkeypatch.setattr(fastembed, "TextEmbedding", lambda *a, **k: opened.append(k) or model)
    gold = b.cards[0]["campno"]
    question = {"question": card_text(b.cards[0]), "gold_campnos": [gold], "_post": True}
    monkeypatch.setattr(parity, "load", lambda: (None, [question]))
    parity.main(["--vectors", "bundle", "--bundle", str(tar), "--allow-drift"])
    out = json.loads(capsys.readouterr().out)
    assert out["vectors"] == "bundle" and out["all"]["any@1"] == 1.0  # 묶음 벡터로 채점했다
    assert opened[0]["specific_model_path"].endswith("model")  # 묶음 안 모델 파일로 열었다
    other = load_build(
        full_data_dir(
            tmp_path / "o",
            [dict(CARDS[0], defect="Another defect.")] + CARDS[1:],
            [cause("24V001", pdfs=PDFS)],
        )
    )
    other_tar = bundle.write_bundle(other, INV, vecs, model_dir, tmp_path / "other")
    with pytest.raises(bundle.BundleMismatch, match="build"):
        parity.main(["--vectors", "bundle", "--bundle", str(other_tar), "--allow-drift"])


def test_empty_rag_source_from_env_example_means_local(monkeypatch):
    import server.api as api_mod

    used = []
    monkeypatch.setattr(api_mod, "load_state_from_files", lambda: used.append("local") or "state")
    monkeypatch.setattr(api_mod, "load_state_from_bundle", lambda: pytest.fail("bundle"))
    for value in ("", "  ", "local"):
        monkeypatch.setenv("RAG_SOURCE", value)
        assert api_mod.load_state() == "state"
    assert used == ["local"] * 3


def test_download_keeps_the_bundle_folder_private(tmp_path, monkeypatch):
    import io

    class Body(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(bundle.urllib.request, "urlopen", lambda *a, **k: Body(b"tar"))
    folder = tmp_path / "serving"
    folder.mkdir(mode=0o755)  # 이미 있던 폴더도 좁힌다
    bundle._download("https://x/a", folder / "x.tar")
    assert (folder / "x.tar").read_bytes() == b"tar"
    assert folder.stat().st_mode & 0o777 == 0o700


def test_parity_bundle_mode_removes_its_temporary_model_folder(tmp_path, monkeypatch, capsys):
    import atexit
    from pathlib import Path

    import fastembed

    from scripts.defect_precedent.retrieval_compare import card_text
    from server.rag import parity

    b = load_build(full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)]))
    model = FakeModel()
    vecs = np.array(model.passage_embed([card_text(c) for c in b.cards]), dtype="float32")
    _, _, model_dir = _inputs(tmp_path / "m")
    tar = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    monkeypatch.setattr(parity, "load_build", lambda: b)
    monkeypatch.setattr(parity, "provenance", lambda: {"recalls_sha256": "x", "eval_sha256": "y"})
    monkeypatch.setattr(embeddings, "check_fastembed", lambda: None)
    opened = []
    monkeypatch.setattr(fastembed, "TextEmbedding", lambda *a, **k: opened.append(k) or model)
    q = {"question": card_text(b.cards[0]), "gold_campnos": [b.cards[0]["campno"]], "_post": True}
    monkeypatch.setattr(parity, "load", lambda: (None, [q]))
    at_exit = []
    monkeypatch.setattr(atexit, "register", lambda f, *a: at_exit.append((f, a)))
    parity.main(["--vectors", "bundle", "--bundle", str(tar), "--allow-drift"])
    work = Path(opened[0]["specific_model_path"]).parent
    assert work.exists() and len(at_exit) == 1
    f, a = at_exit[0]
    f(*a)  # 프로세스가 끝날 때 도는 정리
    assert not work.exists()

"""서빙 묶음(DEC-048 ⑤) — 로컬 검사를 통과한 build를 파일 하나로 만들고, 그대로 되살리는지."""

import hashlib
import io
import json
import tarfile

import numpy as np
import pytest

from server.rag import bundle
from server.rag.build import load_build
from tests.test_load_db import cause, pg, pgconn, recall  # noqa: F401
from tests.test_rag_server import CARDS, full_data_dir

PDFS = {"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32}
INV = {
    "24V001000": [
        {
            "action": "PE24001",
            "subject": "Airbag",
            "summary": "Owners report the airbag inflator ruptured.",
            "open_date": "20240101",
            "close_date": "",
        }
    ]
}


def _inputs(tmp_path):
    b = load_build(full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)]))
    vecs = np.arange(len(b.cards) * 384, dtype="float32").reshape(len(b.cards), 384) / 7
    model_dir = tmp_path / "model"
    (model_dir / "sub").mkdir(parents=True)
    (model_dir / "model_optimized.onnx").write_bytes(b"\x00onnx\x01" * 10)
    (model_dir / "tokenizer.json").write_text('{"v": 1}', encoding="utf-8")
    (model_dir / "sub" / "config.json").write_text("{}", encoding="utf-8")
    return b, vecs, model_dir


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundle_round_trip_keeps_card_order_causes_investigations_vectors_and_model(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    assert out.name == f"serving_{b.build_id}.tar"
    got = bundle.load_bundle(out, tmp_path / "x")
    assert (
        got.build == b
    )  # 카드 순서·원인 행(text_basis 포함)·실패 사유·명세·원본 명세 해시까지 같다
    assert [c["campno"] for c in got.build.cards] == [c["campno"] for c in CARDS]
    assert got.investigations == INV
    assert got.vectors.dtype == np.float32 and np.array_equal(got.vectors, vecs)
    for rel in ("model_optimized.onnx", "tokenizer.json", "sub/config.json"):
        assert (got.model_dir / rel).read_bytes() == (model_dir / rel).read_bytes()


def test_bundle_bytes_are_the_same_for_the_same_input(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    one = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "a")
    two = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "b")
    assert _sha(one) == _sha(two)  # DB에 적는 sha256이 다시 만들어도 같아야 되짚을 수 있다


def _rewrite(src, dst, member, data):
    """묶음의 한 파일만 바꾼 사본 — meta.json은 그대로 둔다."""
    with tarfile.open(src) as tin, tarfile.open(dst, "w") as tout:
        for info in tin.getmembers():
            body = data if info.name == member else tin.extractfile(info).read()
            info.size = len(body)
            tout.addfile(info, io.BytesIO(body))


@pytest.mark.parametrize("member", ["cards.jsonl", "investigations.json", "model/tokenizer.json"])
def test_load_bundle_refuses_a_member_that_differs_from_meta(tmp_path, member):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    bad = tmp_path / "bad.tar"
    _rewrite(out, bad, member, b"changed")
    with pytest.raises(bundle.BundleMismatch, match=member):
        bundle.load_bundle(bad, tmp_path / "x")


def test_load_bundle_refuses_cards_whose_order_changed(tmp_path):
    """카드 순서가 바뀌면 벡터 줄·탐침 위치가 어긋난다 — meta의 카드 글 해시와 다시 계산한 값으로 막는다."""
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    with tarfile.open(out) as t:
        meta = json.loads(t.extractfile("meta.json").read())
        cards = t.extractfile("cards.jsonl").read().decode().splitlines()
    swapped = ("\n".join([cards[1], cards[0], *cards[2:]]) + "\n").encode()
    meta["files"]["cards.jsonl"] = hashlib.sha256(swapped).hexdigest()
    tmp = tmp_path / "t.tar"
    _rewrite(out, tmp, "cards.jsonl", swapped)
    bad = tmp_path / "bad.tar"
    _rewrite(tmp, bad, "meta.json", json.dumps(meta).encode())
    with pytest.raises(bundle.BundleMismatch, match="texts_sha256"):
        bundle.load_bundle(bad, tmp_path / "x")


def test_check_sha_refuses_a_bundle_other_than_the_recorded_one(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    bundle.check_sha(out, _sha(out))
    with pytest.raises(bundle.BundleMismatch, match="sha256"):
        bundle.check_sha(out, "ab" * 32)


@pg
def test_pg_serving_bundles_record_is_written_once(pgconn, tmp_path):  # noqa: F811
    from scripts.defect_precedent import load_db

    d = full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)])
    load_db.main(["load", "--causes", "full", "--data-dir", str(d)])
    b = load_build(d)
    from server.rag import embeddings

    embeddings.main(["schema"])
    pgconn.execute(
        "insert into embedding_sets (build_id, model, fastembed_version, texts_sha256, model_fingerprint, rows) "
        "values (%s, %s, '0.9.0', 'x', 'x', 3)",
        (b.build_id, embeddings.MODEL),
    )
    pgconn.execute(bundle.SCHEMA.read_text(encoding="utf-8"))
    pgconn.execute(bundle.SCHEMA.read_text(encoding="utf-8"))  # 여러 번 적용해도 된다
    bundle.register(pgconn, b.build_id, "aa" * 32, "x/serving.tar")
    bundle.register(pgconn, b.build_id, "aa" * 32, "x/serving.tar")  # 같으면 그대로
    with pytest.raises(bundle.BundleMismatch, match="덮어쓰지 않는다"):
        bundle.register(pgconn, b.build_id, "bb" * 32, "x/serving.tar")
    assert bundle.recorded(pgconn, b.build_id) == ("aa" * 32, "x/serving.tar")
    assert bundle.recorded(pgconn, "nope") is None

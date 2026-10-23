"""embedding_prefix_check — 지금 카드 글의 캐시만 고른다(같은 행 수의 옛 캐시는 고르지 않는다).

캐시 경로 식은 `retrieval_compare.card_cache_path` 하나이고 `embed_cards`와 이 스크립트가 함께 쓴다(이슈 #175).
"""

import hashlib

import fastembed
import numpy as np
import pytest

from scripts.defect_precedent import embedding_prefix_check as epc
from scripts.defect_precedent import retrieval_compare as rc
from scripts.defect_precedent.retrieval_compare import card_cache_path as cache_file

MODEL = "snowflake/snowflake-arctic-embed-m"


def test_cache_file_follows_current_card_text(tmp_path):
    texts = ["card one", "card two"]
    key = hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]
    assert (
        cache_file(MODEL, texts, tmp_path)
        == tmp_path / f"snowflake_snowflake-arctic-embed-m_{key}.npy"
    )


def test_old_cache_with_same_row_count_is_not_selected(tmp_path):
    old = cache_file(MODEL, ["old one", "old two"], tmp_path)
    new = cache_file(MODEL, ["card one", "card two"], tmp_path)
    assert old != new  # 카드 글이 다르면 행 수가 같아도 다른 캐시 이름
    old.write_bytes(b"stale")
    assert not new.exists()  # 옛 파일이 있어도 지금 카드의 경로는 비어 있다


def test_embed_cards_and_the_prefix_check_share_one_cache_path(tmp_path, monkeypatch):
    """`embed_cards`가 저장한 파일을 `embedding_prefix_check`가 그대로 찾아야 한다 — 두 곳이 식을 따로 복사하면 어긋난다."""
    monkeypatch.setattr(rc, "CACHE", tmp_path)
    monkeypatch.setattr(rc, "FASTEMBED_VERSION", fastembed.__version__)
    monkeypatch.setattr(fastembed, "TextEmbedding", FakeModel)
    texts = [f"card {i}" for i in range(20)]
    rc.embed_cards(MODEL, texts)
    saved = [p.name for p in tmp_path.glob("*.npy")]
    assert saved == [rc.card_cache_path(MODEL, texts).name]


class FakeModel:
    """글자 길이로 벡터를 정하는 가짜 모델 — 같은 글이면 같은 벡터."""

    def __init__(self, name, **kw):
        pass

    def passage_embed(self, texts, **kw):
        return [np.array([float(len(t)), float(sum(map(ord, t)) % 7), 1.0]) for t in texts]


def run_main(tmp_path, monkeypatch, *, cache_rows=None, tamper=False, version=None):
    """카드 20장짜리 가짜 데이터로 `main`을 돌린다. cache_rows: 캐시에 넣을 행 수(None이면 캐시 없음)."""
    cards = [{"campno": f"C{i:02d}"} for i in range(20)]
    monkeypatch.setattr(rc, "load", lambda: (cards, [{"question": "q", "gold_campnos": ["C00"]}]))
    monkeypatch.setattr(rc, "card_text", lambda c: f"card {c['campno']}")
    monkeypatch.setattr(rc, "CACHE", tmp_path)
    monkeypatch.setattr(rc, "FASTEMBED_VERSION", version or fastembed.__version__)
    monkeypatch.setattr(fastembed, "TextEmbedding", FakeModel)
    texts = [f"card {c['campno']}" for c in cards]
    if cache_rows is not None:
        vecs = np.array(FakeModel(MODEL).passage_embed(texts))[:cache_rows]
        if tamper:
            vecs = vecs + 1.0  # 다른 모델·판본으로 만든 캐시
        np.save(rc.card_cache_path(MODEL, texts), vecs)
    epc.main(["--model", MODEL, "--prefix", "p: "])


def test_main_stops_when_fastembed_version_differs_from_the_reported_one(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="보고서는 0.0.0로 쟀다"):
        run_main(tmp_path, monkeypatch, cache_rows=20, version="0.0.0")


def test_main_stops_when_there_is_no_cache_for_the_current_cards(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="벡터 캐시가 없다"):
        run_main(tmp_path, monkeypatch)


def test_main_stops_when_the_cache_has_a_different_row_count(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="카드 수가 지금 카드와 다르다"):
        run_main(tmp_path, monkeypatch, cache_rows=19)


def test_main_stops_when_the_cache_vectors_differ_from_the_current_model(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="지금 모델의 계산과 다르다"):
        run_main(tmp_path, monkeypatch, cache_rows=20, tamper=True)

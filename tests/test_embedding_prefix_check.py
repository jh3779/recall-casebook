"""embedding_prefix_check — 지금 카드 글의 캐시만 고른다(같은 행 수의 옛 캐시는 고르지 않는다)."""

import hashlib

from scripts.defect_precedent.embedding_prefix_check import cache_file


def test_cache_file_follows_current_card_text(tmp_path):
    texts = ["card one", "card two"]
    model = "snowflake/snowflake-arctic-embed-m"
    key = hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]
    assert (
        cache_file(model, texts, tmp_path)
        == tmp_path / f"snowflake_snowflake-arctic-embed-m_{key}.npy"
    )


def test_old_cache_with_same_row_count_is_not_selected(tmp_path):
    model = "snowflake/snowflake-arctic-embed-m"
    old = cache_file(model, ["old one", "old two"], tmp_path)
    new = cache_file(model, ["card one", "card two"], tmp_path)
    assert old != new  # 카드 글이 다르면 행 수가 같아도 다른 캐시 이름
    old.write_bytes(b"stale")
    assert not new.exists()  # 옛 파일이 있어도 지금 카드의 경로는 비어 있다

"""카드 임베딩을 Supabase(pgvector)에 올리고, 서버가 시작할 때 읽어 온다 (DEC-039, 사용자 결정 2026-10-10 — 벡터는 Supabase 보관).

사용법 (연결 문자열은 .env의 DATABASE_URL — 값을 출력하지 않는다):
    uv run --env-file .env python -m server.rag.embeddings schema   # embeddings.sql 적용
    uv run --env-file .env python -m server.rag.embeddings load     # 로컬 build의 카드 30,350장 임베딩(CPU 약 9분, 캐시가 있으면 바로) → 적재

- 카드 글·모델·fastembed 판본은 보고서(docs/실험_P2_검색방식비교.md)의 v2와 같다. 임베딩은 `retrieval_compare.embed_cards`를 그대로
  써서 같은 캐시(`RETRIEVAL_CACHE`)를 공유한다.
- 같은 (build, 모델)이 이미 있으면 덮어쓰지 않는다. 카드 글 해시·줄 수가 같으면 아무것도 하지 않고, 다르면 중단한다.
- 서버는 읽은 벡터를 그대로 믿지 않는다: 카드 글 해시·줄 수·fastembed 판본을 대조하고, 카드 16장을 지금 모델로 다시 임베딩해
  저장된 값과 비교한다(어긋나면 질문 벡터와 카드 벡터가 다른 계산에서 나온 것이라 시작을 거부한다).
"""

import argparse
import hashlib
from pathlib import Path

from scripts.defect_precedent.load_db import connect
from scripts.defect_precedent.retrieval_compare import FASTEMBED_VERSION, card_text

MODEL = "BAAI/bge-small-en-v1.5"
SCHEMA = Path(__file__).with_name("embeddings.sql")
PROBES = 16
ATOL = 1e-4  # embed_cards의 캐시 대조와 같은 기준


class EmbeddingMismatch(RuntimeError):
    """저장된 벡터가 지금 build·모델과 맞지 않거나 없다."""


def texts_sha256(texts: list[str]) -> str:
    return hashlib.sha256("\n".join(texts).encode()).hexdigest()


def probe_indices(n: int) -> list[int]:
    """embed_cards와 같은 위치의 카드 16장."""
    return list(range(0, n, max(1, n // PROBES)))[:PROBES]


def check_fastembed() -> None:
    import fastembed

    if fastembed.__version__ != FASTEMBED_VERSION:
        raise EmbeddingMismatch(
            f"fastembed {fastembed.__version__} — 카드 벡터는 {FASTEMBED_VERSION}로 만든다"
        )


def verify_probe(model, texts: list[str], vecs) -> None:
    """카드 몇 장을 지금 모델로 다시 임베딩해 저장된 벡터와 비교한다."""
    import numpy as np

    idx = probe_indices(len(texts))
    probe = np.array(list(model.passage_embed([texts[i] for i in idx])), dtype="float32")
    if not np.allclose(vecs[idx], probe, atol=ATOL):
        raise EmbeddingMismatch(
            "저장된 카드 벡터가 지금 모델로 다시 계산한 값과 다르다 — 모델 파일·판본이 바뀌었으면 build를 새로 만들어 다시 올린다"
        )


def vec_literal(v) -> str:
    """float32를 그대로 되살리는 자릿수(9)로 쓴다 — 적재 전후 값이 같아야 대리 평가 점수가 그대로 재현된다."""
    return "[" + ",".join(format(float(x), ".9g") for x in v) + "]"


CACHE_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "processed" / "defect" / "vector_cache"
)  # gitignore됨
SAMPLE_ROWS = 64  # 로컬 사본을 쓸 때 DB에서 다시 읽어 글자 그대로 같은지 보는 줄 수


def check_set(
    conn, build_id: str, campnos: list[str], texts: list[str], model: str = MODEL
) -> None:
    """DB의 벡터 기록(판본·카드 글 해시·줄 수)이 지금 카드와 맞는지."""
    row = conn.execute(
        "select fastembed_version, texts_sha256, rows from embedding_sets where build_id = %s and model = %s",
        (build_id, model),
    ).fetchone()
    if row is None:
        raise EmbeddingMismatch(
            f"build {build_id}·{model}의 카드 벡터가 DB에 없다 — "
            "`uv run --env-file .env python -m server.rag.embeddings load`로 먼저 올린다"
        )
    version, digest, n = row
    if version != FASTEMBED_VERSION or digest != texts_sha256(texts) or n != len(campnos):
        raise EmbeddingMismatch(
            f"DB의 벡터 기록(fastembed {version}, {n:,}줄)이 지금 카드·판본과 다르다 — 섞인 판본으로 검색하지 않는다"
        )


def _read_rows(conn, build_id: str, model: str, campnos: list[str] | None):
    """(리콜 번호, float32 벡터)를 바이너리로 읽는다 — 글자 배열(real[])보다 작고 값이 float32 그대로다."""
    from pgvector.psycopg import register_vector

    register_vector(conn)
    sql = "select campno, embedding from recall_embeddings where build_id = %s and model = %s"
    params: tuple = (build_id, model)
    if campnos is not None:
        sql += " and campno = any(%s)"
        params += (campnos,)
    with conn.cursor(binary=True) as cur:
        cur.execute(sql, params)
        yield from ((c, e.to_numpy()) for c, e in cur)


def fetch(conn, build_id: str, campnos: list[str], texts: list[str], model: str = MODEL):
    """(build, 모델)의 벡터 전체를 카드 순서대로 DB에서 읽는다. 정규화하지 않은 값을 돌려준다."""
    import numpy as np

    check_set(conn, build_id, campnos, texts, model)
    pos = {c: i for i, c in enumerate(campnos)}
    vecs = np.zeros((len(campnos), 384), dtype="float32")
    seen = 0
    for campno, emb in _read_rows(conn, build_id, model, None):
        vecs[pos[campno]] = emb
        seen += 1
    if seen != len(campnos):
        raise EmbeddingMismatch(f"DB 벡터 {seen:,}줄 ≠ 카드 {len(campnos):,}장")
    return vecs


def load_vectors(
    conn, build_id: str, campnos: list[str], texts: list[str], cache_dir: Path = CACHE_DIR
):
    """서버가 쓰는 벡터. 정본은 DB이고, 로컬 사본은 DB에서 다시 받는 시간(운영 Supabase에서 30~100초, 2026-10-10 실측)을
    줄이기 위한 것이다. 사본은 DB 기록이 지금 카드와 맞고, DB에서 고르게 뽑은 64줄이 사본과 글자 그대로 같을 때만 쓴다.
    아니면 DB에서 전부 다시 받아 사본을 새로 쓴다. (서버는 그 뒤 16장 재임베딩 대조도 한다 — `verify_probe`)"""
    import numpy as np

    check_set(conn, build_id, campnos, texts)
    path = cache_dir / f"{build_id}_{MODEL.replace('/', '_')}.npy"
    if path.exists():
        cached = np.load(path)
        if cached.shape == (len(campnos), 384):
            idx = list(range(0, len(campnos), max(1, len(campnos) // SAMPLE_ROWS)))[:SAMPLE_ROWS]
            sample = dict(_read_rows(conn, build_id, MODEL, [campnos[i] for i in idx]))
            if len(sample) == len(idx) and all(
                np.array_equal(cached[i], sample[campnos[i]]) for i in idx
            ):
                return cached
    vecs = fetch(conn, build_id, campnos, texts)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npy")
    np.save(tmp, vecs)
    tmp.replace(path)  # 다 쓴 뒤에만 이름을 바꾼다 — 중간에 멈춰도 반쯤 쓴 사본을 쓰지 않는다
    return vecs


def cmd_schema(_args) -> None:
    with connect() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    print("embeddings.sql 적용 완료")


def cmd_load(_args) -> None:
    from scripts.defect_precedent.retrieval_compare import embed_cards
    from server.rag.build import load_build

    build = load_build()
    texts = [card_text(c) for c in build.cards]
    campnos = [c["campno"] for c in build.cards]
    digest = texts_sha256(texts)
    expected = (FASTEMBED_VERSION, digest, len(texts))
    exists_sql = "select fastembed_version, texts_sha256, rows from embedding_sets where build_id = %s and model = %s"

    def same_or_stop(existing) -> bool:
        if existing is None:
            return False
        if tuple(existing) != expected:
            raise SystemExit(
                f"build {build.build_id}·{MODEL}의 벡터가 이미 있는데 판본·카드 글·줄 수가 다르다(DB fastembed {existing[0]}, "
                f"{existing[2]:,}줄) — 덮어쓰지 않는다. fastembed 판본만 바꾼 것이면 build_id가 그대로라 새 build로 풀리지 않는다 — 벡터 세트 키에 판본을 넣는 스키마 변경을 먼저 결정한다(DEC-042). 세트를 손으로 지우지 않는다"
            )
        print(f"build {build.build_id}·{MODEL}의 벡터가 이미 있고 같다 — 아무것도 바꾸지 않았다")
        return True

    with (
        connect() as conn
    ):  # 짧게 먼저 확인한다 — 임베딩(최대 약 9분) 동안 트랜잭션을 열어 두지 않는다
        if same_or_stop(conn.execute(exists_sql, (build.build_id, MODEL)).fetchone()):
            return
    check_fastembed()
    _, vecs, secs, info = embed_cards(MODEL, texts)
    with connect() as conn:  # 정상 종료하면 commit, 예외면 rollback
        if same_or_stop(conn.execute(exists_sql, (build.build_id, MODEL)).fetchone()):
            return
        conn.execute(
            "insert into embedding_sets (build_id, model, fastembed_version, texts_sha256, model_fingerprint, rows) "
            "values (%s, %s, %s, %s, %s, %s)",
            (
                build.build_id,
                MODEL,
                FASTEMBED_VERSION,
                digest,
                info["model_fingerprint"],
                len(texts),
            ),
        )
        with conn.cursor() as cur:
            with cur.copy(
                "copy recall_embeddings (build_id, model, campno, embedding) from stdin"
            ) as cp:
                for campno, v in zip(campnos, vecs, strict=True):
                    cp.write_row((build.build_id, MODEL, campno, vec_literal(v)))
        n = conn.execute(
            "select count(*) from recall_embeddings where build_id = %s and model = %s",
            (build.build_id, MODEL),
        ).fetchone()[0]
        if n != len(texts):
            raise SystemExit(f"DB {n:,}줄 ≠ 카드 {len(texts):,}장 — 되돌린다")
    print(
        f"build {build.build_id}·{MODEL} 벡터 {n:,}줄 적재 완료 (임베딩 {secs:.0f}초, 캐시 대조 {info['cache_verified']})"
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="embeddings", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("schema", help="embeddings.sql 적용")
    sub.add_parser("load", help="로컬 build의 카드 벡터를 올린다")
    a = p.parse_args(argv)
    {"schema": cmd_schema, "load": cmd_load}[a.command](a)


if __name__ == "__main__":
    main()

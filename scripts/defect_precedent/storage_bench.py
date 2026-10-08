"""P2 저장 위치 비교 — 같은 749문항으로 Postgres 전문 검색(FTS)·pgvector를 Python 메모리 검색과 비교한다. 연구용.

사용법 (로컬 Postgres 17 + pgvector, 운영 Supabase가 아님):
    docker run -d --rm --name p2bench -e POSTGRES_PASSWORD=localtest -p 54330:5432 pgvector/pgvector:pg17
    DATABASE_URL=postgresql://postgres:localtest@localhost:54330/postgres uv run python -m scripts.defect_precedent.load_db schema
    (같은 주소로) ... load_db load --causes full
    BENCH_DB=postgresql://postgres:localtest@localhost:54330/postgres RETRIEVAL_CACHE=<임베딩 캐시> \
      uv run --with fastembed python -m scripts.defect_precedent.storage_bench --model BAAI/bge-small-en-v1.5

- FTS: 결함·결과·시정을 `to_tsvector('english', …)` 생성 칸 + GIN 색인, 질문 단어를 OR로 이은 `to_tsquery` + `ts_rank_cd` 상위 10.
  (점수 방식이 BM25와 달라 같은 점수가 나오지 않는다 — DEC-034 미결 ②)
- pgvector: 캐시한 카드 임베딩을 `vector(dim)` 칸 + HNSW(cosine) 색인, 질문 임베딩으로 상위 10.
- 운영 Supabase는 `SUPABASE_DB` 또는 Supabase 주소인 `DATABASE_URL`(`--env-file .env`)이 있을 때만 `select 1` 왕복 시간을 20번 잰다(읽기만).
"""

import argparse
import hashlib
import json
import os
import statistics
import time
from collections import Counter

import psycopg

from scripts.defect_precedent.bm25_baseline import KS, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR
from scripts.defect_precedent.retrieval_compare import CACHE, card_text, read_jsonl


def hits(rankings: list[list[str]], questions: list[dict]) -> dict:
    c = Counter()
    for top, q in zip(rankings, questions, strict=True):
        for k in KS:
            c[k] += any(g in top[:k] for g in q["gold_campnos"])
    return {f"any@{k}": round(c[k] / len(questions), 3) for k in KS}


def timed(cur, sql: str, params) -> tuple[list[str], float]:
    t = time.perf_counter()
    rows = cur.execute(sql, params).fetchall()
    return [r[0] for r in rows], time.perf_counter() - t


def lat(xs: list[float]) -> dict:
    xs = sorted(xs)
    return {
        "p50_ms": round(statistics.median(xs) * 1000, 1),
        "p95_ms": round(xs[int(len(xs) * 0.95)] * 1000, 1),
    }


def main(argv: list[str] | None = None) -> None:
    import numpy as np
    from fastembed import TextEmbedding

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model", required=True)
    a = p.parse_args(argv)

    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    questions = read_jsonl(OUT_DIR / "eval.jsonl")
    texts = [card_text(c) for c in cards]
    key = hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]
    vecs = np.load(CACHE / f"{a.model.replace('/', '_')}_{key}.npy")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    dim = vecs.shape[1]
    model = TextEmbedding(a.model)
    qv = np.array(list(model.query_embed([q["question"] for q in questions])), dtype="float32")
    qv /= np.linalg.norm(qv, axis=1, keepdims=True)
    out: dict = {"model": a.model, "dim": int(dim)}

    with psycopg.connect(os.environ["BENCH_DB"], autocommit=True) as conn:
        cur = conn.cursor()
        build = cur.execute("select build_id from latest_build").fetchone()[0]
        # FTS
        t = time.perf_counter()
        cur.execute(
            "create table if not exists bench_fts as select campno, to_tsvector('english', defect || ' ' || consequence || ' ' || remedy) tsv "
            "from recalls where build_id = %s",
            (build,),
        )
        cur.execute("create index if not exists bench_fts_gin on bench_fts using gin (tsv)")
        out["fts_index_sec"] = round(time.perf_counter() - t, 1)
        ranks, times = [], []
        for q in questions:
            terms = sorted(set(tokenize(q["question"])))
            r, s = timed(
                cur,
                "select campno from bench_fts, to_tsquery('english', %s) qq where tsv @@ qq "
                "order by ts_rank_cd(tsv, qq) desc, campno limit 10",
                (" | ".join(terms),),
            )
            ranks.append(r)
            times.append(s)
        out["postgres_fts"] = {**hits(ranks, questions), **lat(times)}
        # pgvector
        cur.execute("create extension if not exists vector")
        cur.execute(
            f"create table if not exists bench_vec (campno text primary key, v vector({dim}))"
        )
        if cur.execute("select count(*) from bench_vec").fetchone()[0] == 0:
            with cur.copy("copy bench_vec (campno, v) from stdin") as cp:
                for c, v in zip(cards, vecs, strict=True):
                    cp.write_row((c["campno"], "[" + ",".join(f"{x:.6f}" for x in v) + "]"))
        t = time.perf_counter()
        cur.execute(
            "create index if not exists bench_vec_hnsw on bench_vec using hnsw (v vector_cosine_ops)"
        )
        out["hnsw_index_sec"] = round(time.perf_counter() - t, 1)
        ranks, times = [], []
        for v in qv:
            r, s = timed(
                cur,
                "select campno from bench_vec order by v <=> %s::vector limit 10",
                ("[" + ",".join(f"{x:.6f}" for x in v) + "]",),
            )
            ranks.append(r)
            times.append(s)
        out["pgvector_hnsw"] = {**hits(ranks, questions), **lat(times)}
        out["table_sizes"] = {
            t: cur.execute(f"select pg_size_pretty(pg_total_relation_size('{t}'))").fetchone()[0]
            for t in ("bench_fts", "bench_vec")
        }
    # Python 메모리 (같은 임베딩, 정확한 내적)
    times = []
    for v in qv:
        t = time.perf_counter()
        np.argsort(-(vecs @ v))[:10]
        times.append(time.perf_counter() - t)
    out["python_numpy_dense"] = lat(times)
    supa = os.environ.get("SUPABASE_DB") or (
        os.environ.get("DATABASE_URL", "")
        if "supabase" in os.environ.get("DATABASE_URL", "")
        else ""
    )
    if supa:
        with psycopg.connect(supa, prepare_threshold=None) as conn:
            rtt = []
            for _ in range(20):
                t = time.perf_counter()
                conn.execute("select 1").fetchone()
                rtt.append(time.perf_counter() - t)
        out["supabase_roundtrip"] = lat(rtt)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

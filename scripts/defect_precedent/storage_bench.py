"""P2 저장 위치 비교 — 같은 749문항으로 Postgres 전문 검색(FTS)·pgvector를 Python 메모리 검색과 비교한다. 연구용.

사용법 (로컬 Postgres 17 + pgvector, 운영 Supabase가 아님):
    docker run -d --rm --name p2bench -e POSTGRES_PASSWORD=localtest -p 54330:5432 pgvector/pgvector:pg17
    DATABASE_URL=postgresql://postgres:localtest@localhost:54330/postgres uv run python -m scripts.defect_precedent.load_db schema
    (같은 주소로) ... load_db load --causes full
    BENCH_DB=postgresql://postgres:localtest@localhost:54330/postgres RETRIEVAL_CACHE=<임베딩 캐시> \
      uv run --with fastembed --env-file .env python -m scripts.defect_precedent.storage_bench --model BAAI/bge-small-en-v1.5

- 판본 확인: 파일(build.json 해시)과 DB latest build의 `data_builds.recalls_sha256`이 다르면 중단한다. 임베딩 캐시는 지금 모델로 다시 만든 카드 16장과 비교해 맞을 때만 쓴다. 시험 표는 build·모델 이름을 붙여 실행마다 새로 만든다.
- FTS: 결함·결과·시정을 `to_tsvector('english', …)` 표 + GIN 색인, 질문 단어를 OR로 이은 `to_tsquery` + `ts_rank_cd` 상위 10.
  (점수 방식이 BM25와 달라 같은 점수가 나오지 않는다 — DEC-034 미결 ②)
- pgvector: 캐시한 카드 임베딩을 `vector(dim)` 칸 + HNSW(cosine, 기본 ef_search) 색인, 질문 임베딩으로 상위 10.
- 운영 Supabase는 `SUPABASE_DB` 또는 Supabase 주소인 `DATABASE_URL`(`--env-file .env`)이 있을 때만 `select 1` 왕복 시간을 100번 잰다(읽기만).
- 지연 지표: 표본이 100개 이상이면 p50·p95(최근접 순위), 적으면 p50·max.
"""

import argparse
import json
import os
import statistics
import time
from collections import Counter

import psycopg

from scripts.defect_precedent.bm25_baseline import KS, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR
from scripts.defect_precedent.retrieval_compare import (
    card_text,
    embed_cards,
    provenance,
    read_jsonl,
)


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
    out = {"n": len(xs), "p50_ms": round(statistics.median(xs) * 1000, 1)}
    if len(xs) >= 100:
        out["p95_ms"] = round(xs[-(-95 * len(xs) // 100) - 1] * 1000, 1)
    else:
        out["max_ms"] = round(xs[-1] * 1000, 1)
    return out


def vec_literal(v) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def main(argv: list[str] | None = None) -> None:
    import numpy as np

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model", required=True)
    a = p.parse_args(argv)

    if "BENCH_DB" not in os.environ:
        raise SystemExit("BENCH_DB(로컬 Postgres 주소)가 필요하다 — 머리말의 docker 명령 참고")
    if "supabase" in os.environ["BENCH_DB"]:
        raise SystemExit(
            "BENCH_DB가 Supabase를 가리킨다 — 시험 표를 만들므로 로컬 Postgres에서만 돌린다"
        )
    data = provenance()
    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    questions = read_jsonl(OUT_DIR / "eval.jsonl")
    texts = [card_text(c) for c in cards]
    model, vecs, _, emb_info = embed_cards(a.model, texts)
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    dim = vecs.shape[1]
    qv = np.array(list(model.query_embed([q["question"] for q in questions])), dtype="float32")
    qv /= np.linalg.norm(qv, axis=1, keepdims=True)
    out: dict = {"data": data, "model": a.model, "dim": int(dim), "embedding": emb_info}

    with psycopg.connect(os.environ["BENCH_DB"], autocommit=True) as conn:
        cur = conn.cursor()
        build = cur.execute("select build_id from latest_build").fetchone()[0]
        row = cur.execute(
            "select recalls_sha256 from data_builds where build_id = %s", (build,)
        ).fetchone()
        if row[0] != data["recalls_sha256_full"]:
            raise SystemExit(
                f"DB latest build {build}의 recalls_sha256이 파일과 다르다 — 섞인 판본으로 재지 않는다"
            )
        out["db_build_id"] = build
        tag = f"{build[:8]}_{a.model.split('/')[-1].replace('-', '_').replace('.', '_')}"
        fts, vec = f"bench_fts_{tag}", f"bench_vec_{tag}"
        cur.execute(f"drop table if exists {fts}")  # 실행마다 새로 만든다
        cur.execute(f"drop table if exists {vec}")

        t = time.perf_counter()
        cur.execute(
            f"create table {fts} as select campno, "
            "to_tsvector('english', defect || ' ' || consequence || ' ' || remedy) tsv "
            "from recalls where build_id = %s",
            (build,),
        )
        cur.execute(f"create index on {fts} using gin (tsv)")
        out["fts_index_sec"] = round(time.perf_counter() - t, 1)
        ranks, times = [], []
        for q in questions:
            terms = sorted(
                set(tokenize(q["question"]))
            )  # [a-z0-9]+ 토큰만이라 to_tsquery 특수문자가 들어가지 않는다
            r, s = timed(
                cur,
                f"select campno from {fts}, to_tsquery('english', %s) qq where tsv @@ qq "
                "order by ts_rank_cd(tsv, qq) desc, campno limit 10",
                (" | ".join(terms),),
            )
            ranks.append(r)
            times.append(s)
        out["postgres_fts"] = {**hits(ranks, questions), **lat(times)}

        cur.execute("create extension if not exists vector")
        cur.execute(f"create table {vec} (campno text primary key, v vector({dim}))")
        with cur.copy(f"copy {vec} (campno, v) from stdin") as cp:
            for c, v in zip(cards, vecs, strict=True):
                cp.write_row((c["campno"], vec_literal(v)))
        t = time.perf_counter()
        cur.execute(f"create index on {vec} using hnsw (v vector_cosine_ops)")
        out["hnsw_index_sec"] = round(time.perf_counter() - t, 1)
        ranks, times = [], []
        for v in qv:
            r, s = timed(
                cur,
                f"select campno from {vec} order by v <=> %s::vector limit 10",
                (vec_literal(v),),
            )
            ranks.append(r)
            times.append(s)
        out["pgvector_hnsw"] = {**hits(ranks, questions), **lat(times)}
        out["table_sizes"] = {
            t: cur.execute(f"select pg_size_pretty(pg_total_relation_size('{t}'))").fetchone()[0]
            for t in (fts, vec)
        }

    times, ranks = [], []
    ids = [c["campno"] for c in cards]
    for v in qv:  # Python 메모리 (같은 임베딩, 정확한 내적)
        t = time.perf_counter()
        top = np.argsort(-(vecs @ v))[:10]
        times.append(time.perf_counter() - t)
        ranks.append([ids[i] for i in top])
    out["python_numpy_dense"] = {**hits(ranks, questions), **lat(times)}

    url = os.environ.get("DATABASE_URL", "")
    supa = os.environ.get("SUPABASE_DB") or (url if "supabase" in url else "")
    if supa:
        with psycopg.connect(supa, prepare_threshold=None) as conn:
            rtt = []
            for _ in range(100):
                t = time.perf_counter()
                conn.execute("select 1").fetchone()
                rtt.append(time.perf_counter() - t)
        out["supabase_roundtrip"] = lat(rtt)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

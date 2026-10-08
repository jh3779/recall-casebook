"""P2 검색 방식 비교 — 같은 749문항(대리 평가)에서 Hit@1·3·5·10을 잰다. 연구용(research), 서비스 코드가 아니다.

사용법:
    uv run python -m scripts.defect_precedent.retrieval_compare bm25            # v0·v0a·v4 (표준 라이브러리만)
    uv run --with fastembed python -m scripts.defect_precedent.retrieval_compare dense --model BAAI/bge-small-en-v1.5 [--limit 2000]

변형 (정답을 보고 정한 규칙은 없다 — AGENTS.md 5-2):
- v0   BM25, 색인 = 결함·결과·시정 (기준선 0.510과 같은 방식)
- v0a  v0 + 질문에서 회사 이름 단어를 뺀다. 빼는 단어 = 대응표의 모든 회사 이름(`raw_maker`·`maker`·`maker_group`)에
       나오는 길이 3 이상 단어 − why_stats의 일반어 − 리콜 카드 부품 이름(`components`)에 나오는 단어(부품 단어를 지우지 않게).
       사용자는 회사가 아니라 부품으로 묻는다(기획 1절) — 질문에 회사 이름이 섞인 대리 평가 점수가 얼마나 그 이름에 기대는지 본다.
- v0b  v0 + 질문에서 **완성차·브랜드 이름만** 뺀다(아래 `BRANDS`·`BRAND_PHRASES`, 리콜 건수 상위 회사 목록을 보고 사람이 정한 목록 —
       시험지 정답은 보지 않았다). v0a 규칙은 `safety`·`new`·`trucks` 같은 일반어까지 지워 회사 이름 효과만 재지 못한다.
- v4   v0 + 색인에 573 "Description of the Cause"(원인 칸, 연대기 제외)를 붙인다. 2014-08-20 이후 연결 리콜이 있는 문항은 따로 보고.
- dense 로컬 임베딩(fastembed) 코사인 유사도, 색인 = 결함·결과·시정. 결과를 RRF(k=60, 관례값)로 v0과 합친 것도 함께 잰다.
임베딩은 스크래치 폴더에 캐시한다(같은 모델·같은 카드면 다시 계산하지 않음).
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from scripts.defect_precedent.bm25_baseline import BM25, KS, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR, RCLRPT_FROM
from scripts.defect_precedent.why_stats import GENERIC_WORDS

ALIASES = Path(__file__).resolve().parent / "maker_aliases.csv"
CACHE = Path(os.environ.get("RETRIEVAL_CACHE", "/tmp/retrieval_compare_cache"))
RRF_K = 60  # 관례값, 이 시험지로 고르지 않았다
BRANDS = set(
    "ford gm gmc chevrolet chevy buick cadillac oldsmobile pontiac saturn hummer chrysler dodge jeep plymouth "
    "daimlerchrysler fca stellantis freightliner daimler navistar volkswagen vw audi bmw mercedes benz honda acura "
    "paccar kenworth peterbilt nissan infiniti mack toyota lexus scion hyundai kia mazda porsche jaguar subaru "
    "volvo suzuki kawasaki isuzu mitsubishi harley davidson winnebago jayco tesla yamaha".split()
)
BRAND_PHRASES = [("general", "motors"), ("land", "rover"), ("blue", "bird"), ("forest", "river")]


def drop_brands(tokens: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(tokens):
        if any(tuple(tokens[i : i + len(ph)]) == ph for ph in BRAND_PHRASES):
            i += 2
            continue
        if tokens[i] not in BRANDS:
            out.append(tokens[i])
        i += 1
    return out


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def card_text(c: dict) -> str:
    return " ".join((c["defect"], c["consequence"], c["remedy"]))


def maker_words(cards: list[dict]) -> set[str]:
    import csv

    words: set[str] = set()
    with ALIASES.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            for col in ("raw_maker", "maker", "maker_group"):
                words |= {w for w in tokenize(row[col] or "") if len(w) >= 3}
    generic = {w.lower() for w in GENERIC_WORDS}
    part_words = {w for c in cards for comp in c["components"] for w in tokenize(comp)}
    return words - generic - part_words


def score(rankings: list[list[str]], questions: list[dict]) -> dict:
    out = {}
    for name, sel in (("all", questions), ("post2014", [q for q in questions if q["_post"]])):
        idx = (
            [i for i, q in enumerate(questions) if q in sel]
            if name != "all"
            else range(len(questions))
        )
        hits = {"any": Counter(), "first": Counter()}
        for i in idx:
            top, gold = rankings[i], questions[i]["gold_campnos"]
            for k in KS:
                hits["any"][k] += any(g in top[:k] for g in gold)
                hits["first"][k] += gold[0] in top[:k]
        n = len(idx)
        out[name] = {"n": n, **{f"{m}@{k}": round(hits[m][k] / n, 3) for m in hits for k in KS}}
    return out


def load():
    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    questions = read_jsonl(OUT_DIR / "eval.jsonl")
    received = {c["campno"]: c["received_date"] for c in cards}
    for q in questions:
        q["_post"] = any(received.get(g, "") >= RCLRPT_FROM for g in q["gold_campnos"])
    return cards, questions


def bm25_rankings(docs: list[list[str]], queries: list[list[str]], ids: list[str], k: int = 100):
    index = BM25(docs)
    t = time.perf_counter()
    ranks = [[ids[i] for i in index.top(q, k)] for q in queries]
    return ranks, (time.perf_counter() - t) / len(queries)


def run_bm25() -> dict:
    cards, questions = load()
    ids = [c["campno"] for c in cards]
    base_docs = [tokenize(card_text(c)) for c in cards]
    q_tok = [tokenize(q["question"]) for q in questions]
    results = {}

    r, sec = bm25_rankings(base_docs, q_tok, ids)
    results["v0_bm25"] = {**score(r, questions), "sec_per_query": round(sec, 4)}

    drop = maker_words(cards)
    q_nomaker = [[w for w in q if w not in drop] for q in q_tok]
    removed = sum(len(a) - len(b) for a, b in zip(q_tok, q_nomaker, strict=True))
    r, sec = bm25_rankings(base_docs, q_nomaker, ids)
    results["v0a_bm25_no_maker"] = {
        **score(r, questions),
        "sec_per_query": round(sec, 4),
        "drop_vocab": len(drop),
        "tokens_removed": removed,
        "questions_changed": sum(len(a) != len(b) for a, b in zip(q_tok, q_nomaker, strict=True)),
    }

    q_nobrand = [drop_brands(q) for q in q_tok]
    r, sec = bm25_rankings(base_docs, q_nobrand, ids)
    results["v0b_bm25_no_brand"] = {
        **score(r, questions),
        "sec_per_query": round(sec, 4),
        "tokens_removed": sum(len(a) - len(b) for a, b in zip(q_tok, q_nobrand, strict=True)),
        "questions_changed": sum(len(a) != len(b) for a, b in zip(q_tok, q_nobrand, strict=True)),
    }

    causes = {c["campaign"]: c["cause_text"] or "" for c in read_jsonl(OUT_DIR / "causes.jsonl")}
    v4_docs = [tokenize(card_text(c) + " " + causes.get(c["campno"][:6], "")) for c in cards]
    r, sec = bm25_rankings(v4_docs, q_tok, ids)
    results["v4_bm25_plus_573cause"] = {
        **score(r, questions),
        "sec_per_query": round(sec, 4),
        "cards_with_cause": sum(1 for c in cards if causes.get(c["campno"][:6])),
    }
    r, sec = bm25_rankings(v4_docs, q_nobrand, ids)
    results["v4b_bm25_plus_573cause_no_brand"] = {
        **score(r, questions),
        "sec_per_query": round(sec, 4),
    }
    return results


def embed_cards(model_name: str, texts: list[str], key: str):
    import numpy as np
    from fastembed import TextEmbedding

    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{model_name.replace('/', '_')}_{key}.npy"
    model = TextEmbedding(model_name)
    if path.exists():
        return model, np.load(path), 0.0
    t = time.perf_counter()
    vecs = np.array(list(model.passage_embed(texts, batch_size=64)), dtype="float32")
    secs = time.perf_counter() - t
    np.save(path, vecs)
    return model, vecs, secs


def run_dense(model_name: str, limit: int | None) -> dict:
    import numpy as np

    cards, questions = load()
    texts = [card_text(c) for c in cards]
    if limit:  # 표본: 처음 limit장만 임베딩해 속도를 잰다(점수는 내지 않음)
        texts = texts[:limit]
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name)
        t = time.perf_counter()
        vecs = np.array(list(model.passage_embed(texts, batch_size=64)), dtype="float32")
        secs = time.perf_counter() - t
        return {
            "model": model_name,
            "sample_cards": len(texts),
            "dim": int(vecs.shape[1]),
            "sec": round(secs, 1),
            "cards_per_sec": round(len(texts) / secs, 1),
            "projected_full_min": round(len(cards) / (len(texts) / secs) / 60, 1),
        }
    key = hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]
    model, vecs, embed_secs = embed_cards(model_name, texts, key)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    ids = [c["campno"] for c in cards]
    t = time.perf_counter()
    qv = np.array(list(model.query_embed([q["question"] for q in questions])), dtype="float32")
    qv /= np.linalg.norm(qv, axis=1, keepdims=True)
    sims = qv @ vecs.T
    dense_rank = [[ids[i] for i in np.argsort(-row)[:100]] for row in sims]
    q_sec = (time.perf_counter() - t) / len(questions)

    bm, _ = bm25_rankings(
        [tokenize(t) for t in texts], [tokenize(q["question"]) for q in questions], ids
    )

    def rrf(a: list[str], b: list[str]) -> list[str]:
        s: dict[str, float] = {}
        for lst in (a, b):
            for r, cid in enumerate(lst):
                s[cid] = s.get(cid, 0.0) + 1.0 / (RRF_K + r + 1)
        return sorted(s, key=lambda c: -s[c])

    fused = [rrf(a, b) for a, b in zip(bm, dense_rank, strict=True)]
    return {
        "model": model_name,
        "dim": int(vecs.shape[1]),
        "embed_full_sec": round(embed_secs, 1),
        "v1_dense": {**score(dense_rank, questions), "sec_per_query": round(q_sec, 4)},
        "v2_rrf_bm25_dense": score(fused, questions),
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bm25")
    d = sub.add_parser("dense")
    d.add_argument("--model", required=True)
    d.add_argument("--limit", type=int)
    a = p.parse_args(argv)
    if not (OUT_DIR / "recalls.jsonl").exists():
        sys.exit("recalls.jsonl이 없다")
    res = run_bm25() if a.cmd == "bm25" else run_dense(a.model, a.limit)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

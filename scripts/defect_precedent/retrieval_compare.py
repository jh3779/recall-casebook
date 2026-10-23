"""P2 검색 방식 비교 — 같은 749문항(대리 평가)에서 Hit@1·3·5·10을 잰다. 연구용(research), 서비스 코드가 아니다.

사용법:
    uv run python -m scripts.defect_precedent.retrieval_compare bm25            # v0·v0a·v4 (표준 라이브러리만)
    uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.retrieval_compare dense --model BAAI/bge-small-en-v1.5 [--limit 2000]

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
import re
import sys
import time
from collections import Counter
from pathlib import Path

from scripts.defect_precedent.bm25_baseline import BM25, KS, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR, RCLRPT_FROM
from scripts.defect_precedent.why_stats import GENERIC_WORDS

ALIASES = Path(__file__).resolve().parent / "maker_aliases.csv"
# 카드 벡터 캐시 — 임시 폴더(/tmp)는 재부팅 때 지워져 매번 수십 분을 다시 쓰므로 데이터 폴더(커밋 안 함)에 둔다
CACHE = Path(os.environ.get("RETRIEVAL_CACHE", OUT_DIR / "retrieval_cache"))
RRF_K = 60  # 관례값, 이 시험지로 고르지 않았다
FASTEMBED_VERSION = "0.9.0"  # 보고서 수치를 잰 판본 — 다르면 멈춘다(캐시한 카드 벡터와 질문 벡터가 다른 계산에서 나오지 않게)
BRANDS = set(
    "ford gm gmc chevrolet chevy buick cadillac oldsmobile pontiac saturn hummer chrysler dodge jeep plymouth "
    "daimlerchrysler fca stellantis freightliner daimler navistar volkswagen vw audi bmw mercedes benz honda acura "
    "paccar kenworth peterbilt nissan infiniti mack toyota lexus scion hyundai kia mazda porsche jaguar subaru "
    "volvo suzuki kawasaki isuzu mitsubishi harley davidson winnebago jayco tesla yamaha".split()
)
BRAND_PHRASES = [("general", "motors"), ("land", "rover"), ("blue", "bird"), ("forest", "river")]


BRAND_RE = re.compile(
    r"\b(?:"
    + "|".join([r"\s+".join(ph) for ph in BRAND_PHRASES] + sorted(BRANDS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


def strip_brands(text: str) -> str:
    """질문 원문에서 완성차·브랜드 이름(`BRANDS`·`BRAND_PHRASES`)만 지운다. BM25와 뜻 검색에 같은 문장을 쓴다."""
    return re.sub(r"\s+", " ", BRAND_RE.sub(" ", text)).strip()


def provenance() -> dict:
    """결과가 어느 데이터 판본에서 나왔는지 — build.json 해시와 실제 파일 해시가 다르면 중단한다."""
    build = json.loads((OUT_DIR / "build.json").read_text(encoding="utf-8"))
    sha = {
        n: hashlib.sha256((OUT_DIR / n).read_bytes()).hexdigest()
        for n in ("recalls.jsonl", "eval.jsonl", "causes.jsonl")
    }
    if sha["recalls.jsonl"] != build["recalls_sha256"] or sha["eval.jsonl"] != build["eval_sha256"]:
        sys.exit("recalls.jsonl·eval.jsonl이 build.json과 다르다 — 섞인 판본으로 비교하지 않는다")
    manifest = json.loads((OUT_DIR / "causes.manifest.json").read_text(encoding="utf-8"))
    if sha["causes.jsonl"] != manifest["file_sha256"]:
        sys.exit("causes.jsonl이 causes.manifest.json과 다르다 — 섞인 판본으로 비교하지 않는다")
    return {
        "snapshot_date": build["snapshot_date"],
        "recalls_sha256_full": sha["recalls.jsonl"],
        "recalls_sha256": sha["recalls.jsonl"][:16],
        "eval_sha256": sha["eval.jsonl"][:16],
        "causes_sha256": sha["causes.jsonl"][:16],
        "maker_aliases_sha256": (build.get("maker_aliases_sha256") or "")[:16],
    }


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
    subsets = {
        "all": list(range(len(questions))),
        "post2014": [i for i, q in enumerate(questions) if q["_post"]],
    }
    for name, idx in subsets.items():
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

    q_nobrand = [tokenize(strip_brands(q["question"])) for q in questions]
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


def rrf(*rankings: list[str], k: int = RRF_K) -> list[str]:
    """Reciprocal Rank Fusion — 순위 r(0부터)에 1/(k + r + 1)을 더한다. 점수가 같으면 먼저 나온 순서를 유지한다."""
    s: dict[str, float] = {}
    for lst in rankings:
        for r, cid in enumerate(lst):
            s[cid] = s.get(cid, 0.0) + 1.0 / (k + r + 1)
    return sorted(s, key=lambda c: -s[c])


def card_cache_path(model_name: str, texts: list[str], cache: Path | None = None) -> Path:
    """카드 벡터 캐시 파일 경로 — 모델 이름과 **지금 카드 글 전체의 해시**로 정한다. 카드 글이 다른 옛 캐시는 행 수가 같아도
    다른 이름이 된다. `embed_cards`와 `embedding_prefix_check`가 이 식을 함께 쓴다."""
    key = hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]
    return (cache or CACHE) / f"{model_name.replace('/', '_')}_{key}.npy"


def embed_cards(model_name: str, texts: list[str]):
    """카드 임베딩(캐시). 캐시를 쓰기 전에 카드 16장을 지금 모델로 다시 임베딩해 캐시와 비교한다 —
    fastembed·모델 파일이 바뀌었으면 값이 달라지므로 캐시를 버리고 다시 만든다(옛 카드 벡터와 새 질문 벡터가 섞이지 않게)."""
    import fastembed
    import numpy as np
    from fastembed import TextEmbedding

    if fastembed.__version__ != FASTEMBED_VERSION:
        sys.exit(
            f"fastembed {fastembed.__version__} — 보고서는 {FASTEMBED_VERSION}로 쟀다 (`uv run --with fastembed=={FASTEMBED_VERSION}`)"
        )

    CACHE.mkdir(parents=True, exist_ok=True)
    path = card_cache_path(model_name, texts)
    model = TextEmbedding(model_name)
    probe_idx = list(range(0, len(texts), max(1, len(texts) // 16)))[:16]
    probe = np.array(list(model.passage_embed([texts[i] for i in probe_idx])), dtype="float32")
    info = {
        "fastembed": fastembed.__version__,
        "model_fingerprint": hashlib.sha256(np.round(probe, 4).tobytes()).hexdigest()[:16],
        "cache": path.name,
    }
    if path.exists():
        vecs = np.load(path)
        if vecs.shape[0] == len(texts) and np.allclose(vecs[probe_idx], probe, atol=1e-4):
            return model, vecs, 0.0, {**info, "cache_verified": True}
    t = time.perf_counter()
    vecs = np.array(list(model.passage_embed(texts, batch_size=64)), dtype="float32")
    secs = time.perf_counter() - t
    np.save(path, vecs)
    return model, vecs, secs, {**info, "cache_verified": False}


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
    model, vecs, embed_secs, emb_info = embed_cards(model_name, texts)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    ids = [c["campno"] for c in cards]
    t = time.perf_counter()
    qv = np.array(list(model.query_embed([q["question"] for q in questions])), dtype="float32")
    qv /= np.linalg.norm(qv, axis=1, keepdims=True)
    sims = qv @ vecs.T
    dense_rank = [[ids[i] for i in np.argsort(-row)[:100]] for row in sims]
    q_sec = (time.perf_counter() - t) / len(questions)
    nb_text = [strip_brands(q["question"]) for q in questions]
    qv_nb = np.array(list(model.query_embed(nb_text)), dtype="float32")
    qv_nb /= np.linalg.norm(qv_nb, axis=1, keepdims=True)
    dense_nb = [[ids[i] for i in np.argsort(-row)[:100]] for row in qv_nb @ vecs.T]

    docs = [tokenize(t) for t in texts]
    bm, _ = bm25_rankings(docs, [tokenize(q["question"]) for q in questions], ids)
    bm_nb, _ = bm25_rankings(docs, [tokenize(t) for t in nb_text], ids)

    fused = [rrf(a, b) for a, b in zip(bm, dense_rank, strict=True)]
    return {
        "model": model_name,
        "dim": int(vecs.shape[1]),
        "embed_full_sec": round(embed_secs, 1),
        "embedding": emb_info,
        "v1_dense": {**score(dense_rank, questions), "sec_per_query": round(q_sec, 4)},
        "v2_rrf_bm25_dense": score(fused, questions),
        # 회사 이름을 뺀 질문(실사용에 가까움) — 같은 조건의 BM25(v0b)와 비교한다
        "v0b_bm25_no_brand": score(bm_nb, questions),
        "v1b_dense_no_brand": score(dense_nb, questions),
        "v2b_rrf_no_brand": score(
            [rrf(a, b) for a, b in zip(bm_nb, dense_nb, strict=True)], questions
        ),
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
    prov = provenance()
    res = run_bm25() if a.cmd == "bm25" else run_dense(a.model, a.limit)
    res = {"data": prov, **res}
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

"""P5 사후 층화 분석 — 정답 리콜의 부품 라벨 카드 수(희소성)별로 749문항 Hit@10을 다시 읽는다. 연구용(research).

사용법:
    RETRIEVAL_CACHE=data/processed/defect/retrieval_cache \\
        uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.rare_strata

규칙 (docs/experiments/실험_P5_희소부품층화.md 2절, 결과를 보기 전에 고정):
- 희소성 = 정답 리콜의 부품 라벨(`components` 전체 문자열)을 가진 카드 수. 정답이 여럿이면 가장 작은 값,
  한 카드에 라벨이 여럿이면 최솟값. 구간 경계는 `BOUNDS`(분포만 보고 정함).
- 지표 = any@10(정답 중 하나라도 상위 10에 든 비율), 구간별 Wilson 95% 신뢰구간.
- 사후 층화 분석이다 — 튜닝에 쓰지 않고, 대리 평가·시점 평가 점수와 합치지 않는다(AGENTS.md 5-2).
첫 줄에 전체 점수가 기준(BM25 0.510 / RRF 0.542 / 회사 이름 뺀 질문 0.483·0.531)과 같은지 보여 준다.
"""

import collections
import json
import math

from scripts.defect_precedent import retrieval_compare as rc
from scripts.defect_precedent.bm25_baseline import tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR

BOUNDS = (50, 250)  # 드묾 ≤50 / 중간 51~250 / 흔함 >250 — 결과를 보기 전에 고정
RESULT_DIR = OUT_DIR / "rare_strata_20261021"
Z95 = 1.96


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def rarity(question: dict, cards_by_id: dict[str, dict], label_count: collections.Counter) -> int:
    return min(
        min(label_count[x] for x in cards_by_id[g]["components"])
        for g in question["gold_campnos"]
        if g in cards_by_id and cards_by_id[g]["components"]
    )


def main() -> None:
    import numpy as np

    cards, questions = rc.load()
    ids = [c["campno"] for c in cards]
    texts = [rc.card_text(c) for c in cards]
    model, vecs, _, info = rc.embed_cards("BAAI/bge-small-en-v1.5", texts)
    print("캐시 검증:", info["cache_verified"], "fastembed", info["fastembed"])
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)

    def dense(queries: list[str]) -> list[list[str]]:
        qv = np.array(list(model.query_embed(queries)), dtype="float32")
        qv /= np.linalg.norm(qv, axis=1, keepdims=True)
        return [[ids[i] for i in np.argsort(-row)[:100]] for row in qv @ vecs.T]

    docs = [tokenize(t) for t in texts]
    original = [q["question"] for q in questions]
    no_brand = [rc.strip_brands(q) for q in original]
    bm, _ = rc.bm25_rankings(docs, [tokenize(q) for q in original], ids)
    bm_nb, _ = rc.bm25_rankings(docs, [tokenize(q) for q in no_brand], ids)
    dn, dn_nb = dense(original), dense(no_brand)
    runs = {
        "BM25·원래": bm,
        "RRF·원래": [rc.rrf(a, b) for a, b in zip(bm, dn, strict=True)],
        "BM25·회사이름뺌": bm_nb,
        "RRF·회사이름뺌": [rc.rrf(a, b) for a, b in zip(bm_nb, dn_nb, strict=True)],
    }

    by_id = {c["campno"]: c for c in cards}
    label_count = collections.Counter(x for c in cards for x in set(c["components"]))
    rare = [rarity(q, by_id, label_count) for q in questions]
    lo, hi = BOUNDS
    strata = {
        f"드묾(≤{lo})": lambda x: x <= lo,
        f"중간({lo + 1}~{hi})": lambda x: lo < x <= hi,
        f"흔함(>{hi})": lambda x: x > hi,
        "전체": lambda x: True,
    }
    out: dict[str, dict] = {}
    for name, keep in strata.items():
        idx = [i for i, x in enumerate(rare) if keep(x)]
        row: dict = {"n": len(idx)}
        for run_name, ranking in runs.items():
            k = sum(any(g in ranking[i][:10] for g in questions[i]["gold_campnos"]) for i in idx)
            ci = wilson(k, len(idx))
            row[run_name] = {
                "hit": k,
                "rate": round(k / len(idx), 3),
                "ci": [round(c, 3) for c in ci],
            }
        out[name] = row
        rates = {k: v["rate"] for k, v in row.items() if k != "n"}
        print(name, row["n"], rates)

    rarest = [i for i, x in enumerate(rare) if x <= 10]
    for run_name, ranking in runs.items():
        k = sum(any(g in ranking[i][:10] for g in questions[i]["gold_campnos"]) for i in rarest)
        print(f"카드 ≤10장({len(rarest)}문항)", run_name, k)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / "result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

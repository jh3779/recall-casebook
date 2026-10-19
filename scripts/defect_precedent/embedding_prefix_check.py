"""임베딩 모델의 질문 접두어(query prefix) 진단 — 연구용(research), 서비스 코드가 아니다.

`retrieval_compare dense`는 질문을 fastembed 기본값(`query_embed`)으로 임베딩한다. 일부 모델(예: Snowflake Arctic)은
모델 카드가 질문 앞에 지시문을 붙이라고 안내하는데, 기본값은 이를 붙이지 않는다 — 그 모델은 불리하게 잰다.
이 스크립트는 **이미 만든 카드 벡터 캐시**(`retrieval_compare dense --model ...`가 남긴 것)를 그대로 쓰고
질문만 접두어를 붙여 다시 임베딩해 같은 749문항 점수를 낸다(카드는 접두어 없이 색인 — 모델 카드의 문서 쪽 규칙).

사용법(카드 벡터 캐시가 먼저 있어야 한다):
    uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.embedding_prefix_check \\
        --model snowflake/snowflake-arctic-embed-m \\
        --prefix "Represent this sentence for searching relevant passages: "

결과는 **사후 진단**이다 — 사전 고정 규칙(docs/실험_P4_임베딩모델비교.md)의 채택 판단에 쓰지 않는다.
"""

import argparse
import json
import sys

from scripts.defect_precedent import retrieval_compare as rc
from scripts.defect_precedent.bm25_baseline import tokenize


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model", required=True)
    p.add_argument(
        "--prefix", required=True, help="질문 앞에 붙일 지시문(모델 카드의 query prefix)"
    )
    a = p.parse_args(argv)

    import numpy as np
    from fastembed import TextEmbedding

    cards, questions = rc.load()
    ids = [c["campno"] for c in cards]
    texts = [rc.card_text(c) for c in cards]
    found = sorted(rc.CACHE.glob(f"{a.model.replace('/', '_')}_*.npy"))
    if not found:
        sys.exit(
            f"카드 벡터 캐시가 없다 — 먼저 `retrieval_compare dense --model {a.model}`를 돌린다"
        )
    vecs = np.load(found[-1])
    if vecs.shape[0] != len(texts):
        sys.exit("캐시의 카드 수가 지금 카드와 다르다 — 캐시를 다시 만든다")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    model = TextEmbedding(a.model)

    def dense(qs: list[str]) -> list[list[str]]:
        # query_embed가 접두어를 붙이지 않는 모델이므로 접두어를 직접 붙이고 passage_embed로 임베딩한다
        qv = np.array(list(model.passage_embed([a.prefix + q for q in qs])), dtype="float32")
        qv /= np.linalg.norm(qv, axis=1, keepdims=True)
        return [[ids[i] for i in np.argsort(-row)[:100]] for row in qv @ vecs.T]

    plain = [q["question"] for q in questions]
    no_brand = [rc.strip_brands(q) for q in plain]
    docs = [tokenize(t) for t in texts]
    bm, _ = rc.bm25_rankings(docs, [tokenize(q) for q in plain], ids)
    bm_nb, _ = rc.bm25_rankings(docs, [tokenize(q) for q in no_brand], ids)
    d, d_nb = dense(plain), dense(no_brand)

    def hits(rankings: list[list[str]]) -> dict:
        return {
            k: v for k, v in rc.score(rankings, questions)["all"].items() if k.startswith("any")
        }

    out = {
        "model": a.model,
        "prefix": a.prefix,
        "v1_dense": hits(d),
        "v1b_dense_no_brand": hits(d_nb),
        "v2_rrf_bm25_dense": hits([rc.rrf(x, y) for x, y in zip(bm, d, strict=True)]),
        "v2b_rrf_no_brand": hits([rc.rrf(x, y) for x, y in zip(bm_nb, d_nb, strict=True)]),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

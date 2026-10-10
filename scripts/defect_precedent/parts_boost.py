"""P2 실험 v3 — 부품 범위 좁히기: 질문에 나온 부품 분류의 카드를 순위 안에서 올린다 (docs/계획_P2_API서버.md 2절, 연구용).

사용법:
    RETRIEVAL_CACHE=<카드 벡터 캐시 폴더> uv run python -m scripts.defect_precedent.parts_boost

규칙(2026-10-10, 결과를 보기 전에 고정 — 정답을 보고 단어·가중치를 고치지 않는다, AGENTS.md 5-2):
1. 카드의 부품 분류 = `components` 각 항목의 맨 앞 칸(`:` 앞, 예: "SERVICE BRAKES, HYDRAULIC"). 원본에 42가지.
2. 분류 이름을 `,`·`/`·`;`·` AND `로 나눈 구절마다 단어(소문자, 끝의 s 제거)를 얻고, 일반어(`STOP` + 회사명 일반어
   `why_stats.GENERIC_WORDS`)를 뺀다. 남은 단어가 없는 구절은 쓰지 않는다(예: "EQUIPMENT", "UNKNOWN OR OTHER").
3. 구절이 질문에 맞다 = 구절 단어가 모두 질문 단어(같은 정규화)에 있거나, 구절 단어를 이어 붙인 말(예: "airbag")이 질문에 있다.
   분류가 맞다 = 구절 하나라도 맞다.
4. 맞는 분류의 카드를 BM25 + 뜻 검색 RRF 순위(DEPTH 100씩)에서 그 순서대로 뽑아 세 번째 순위로 RRF(k=60)에 더한다.
   맞는 분류가 없으면 순위는 그대로다. 걸러내지 않는다 — 다른 분류 카드도 순위에 남는다.
판정: 같은 749문항 대리 평가 Hit@10(any)이 기준 폭 0.03 이상 오를 때만 서버에 켠다(AGENTS.md 5-1·5-3). 아니면 기각을 기록한다(5-4).
회사 이름을 뺀 질문(`strip_brands`)도 함께 잰다 — 실사용에 가까운 조건.
"""

import json
import re

from scripts.defect_precedent.bm25_baseline import tokenize
from scripts.defect_precedent.retrieval_compare import (
    card_text,
    embed_cards,
    load,
    provenance,
    rrf,
    score,
    strip_brands,
)
from scripts.defect_precedent.why_stats import GENERIC_WORDS

MODEL = "BAAI/bge-small-en-v1.5"
DEPTH = 100
STOP = {"and", "or", "other", "unknown", "system", "service", "equipment", "control"}
STOP_ALL = STOP | {w.lower() for w in GENERIC_WORDS}


def norm(word: str) -> str:
    """복수형 끝을 뗀다 — latches→latch, brakes→brake (점수를 보기 전, 규칙 점검 중 고침)."""
    if len(word) > 4 and word.endswith(("ches", "shes", "xes")):
        return word[:-2]
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def phrases(category: str) -> list[list[str]]:
    out = []
    for part in re.split(r"[,/;]|\bAND\b", category):
        words = [norm(w) for w in tokenize(part) if w not in STOP_ALL]
        words = [w for w in words if w not in STOP_ALL]
        if words:
            out.append(words)
    return out


def matched_categories(question: str, categories: dict[str, list[list[str]]]) -> set[str]:
    q = {norm(w) for w in tokenize(question)}
    return {
        cat
        for cat, phs in categories.items()
        if any(all(w in q for w in ph) or "".join(ph) in q for ph in phs)
    }


def card_categories(card: dict) -> set[str]:
    return {c.split(":")[0].strip() for c in card["components"]}


def main() -> None:
    import numpy as np

    from scripts.defect_precedent.bm25_baseline import BM25

    data = provenance()
    cards, questions = load()
    texts = [card_text(c) for c in cards]
    ids = [c["campno"] for c in cards]
    cats_of = {c["campno"]: card_categories(c) for c in cards}
    categories = {cat: phrases(cat) for cats in cats_of.values() for cat in cats}
    model, vecs, _, emb_info = embed_cards(MODEL, texts)
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    bm = BM25([tokenize(t) for t in texts])

    out = {"data": data, "embedding": emb_info, "rule": {"stop": sorted(STOP), "depth": DEPTH}}
    for variant, qtext in (
        ("original", [q["question"] for q in questions]),
        ("no_brand", [strip_brands(q["question"]) for q in questions]),
    ):
        qv = np.array(list(model.query_embed(qtext)), dtype="float32")
        qv /= np.linalg.norm(qv, axis=1, keepdims=True)
        before, after, n_matched = [], [], 0
        for text, v in zip(qtext, qv, strict=True):
            b = [ids[i] for i in bm.top(tokenize(text), DEPTH)]
            d = [ids[i] for i in np.argsort(-(vecs @ v))[:DEPTH]]
            fused = rrf(b, d)
            cats = matched_categories(text, categories)
            n_matched += bool(cats)
            part_rank = [c for c in fused if cats_of[c] & cats]
            before.append(fused)
            after.append(rrf(b, d, part_rank) if part_rank else fused)
        out[variant] = {
            "questions_with_category": n_matched,
            "before": score(before, questions),
            "after": score(after, questions),
        }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

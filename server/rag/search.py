"""질문 → 리콜 카드 순위 (DEC-039: BM25 상위 100 + 뜻 검색 상위 100을 RRF k=60으로 합친다).

보고서 v2(`retrieval_compare dense`의 `v2_rrf_bm25_dense`)와 같은 계산이다 — 카드 글·토큰화·BM25·RRF는 연구 코드를 그대로 쓴다.
서버 함수로 749문항 대리 평가를 다시 재서 같은 점수가 나오는지 `server.rag.parity`로 확인한다.
"""

from dataclasses import dataclass

from scripts.defect_precedent.bm25_baseline import BM25, tokenize
from scripts.defect_precedent.retrieval_compare import card_text, rrf

DEPTH = 100  # RRF에 넣는 각 순위의 길이 (retrieval_compare와 같음)


@dataclass(frozen=True)
class SearchResult:
    ranking: list[str]  # RRF로 합친 순위 (최대 2 × DEPTH)
    candidates: frozenset[
        str
    ]  # 검색이 넘긴 리콜 범위 — 응답은 이 안의 번호만 인용한다 (AGENTS.md 2-2)


class Searcher:
    def __init__(self, cards: list[dict], vecs, model):
        """vecs = 카드 순서의 임베딩(정규화 전), model = `query_embed`가 있는 fastembed 모델."""
        import numpy as np

        self.ids = [c["campno"] for c in cards]
        self.bm25 = BM25([tokenize(card_text(c)) for c in cards])
        self.vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        self.model = model

    def query_vectors(self, questions: list[str]):
        import numpy as np

        qv = np.array(list(self.model.query_embed(questions)), dtype="float32")
        return qv / np.linalg.norm(qv, axis=1, keepdims=True)

    def search(self, question: str, qvec=None) -> SearchResult:
        """qvec를 주면 질문 임베딩을 다시 계산하지 않는다 (대리 평가에서 749문항을 한 번에 임베딩할 때)."""
        import numpy as np

        if qvec is None:
            qvec = self.query_vectors([question])[0]
        bm = [self.ids[i] for i in self.bm25.top(tokenize(question), DEPTH)]
        dense = [self.ids[i] for i in np.argsort(-(self.vecs @ qvec))[:DEPTH]]
        ranking = rrf(bm, dense)
        return SearchResult(ranking, frozenset(ranking))

"""시험지(eval.jsonl)로 BM25 기준 점수(Hit@1·3·5·10)를 잰다. 외부 패키지 없이 표준 라이브러리만 쓴다.

사용법: uv run python -m scripts.defect_precedent.bm25_baseline [--baseline scripts/defect_precedent/baseline_2026-10-06.json]

색인 대상은 리콜 카드의 결함·결과·시정 텍스트만이다 (조사 요약은 시험 질문의 출처라 넣지 않는다 — 누수 방지).
주 지표는 "연결 리콜 중 하나라도 상위 k개 안"이고, "첫 번째 연결 리콜만"은 참고값이다.
이 시험은 대리 평가다 (docs/기획_결함선례.md 6절).
점수 공식은 rank_bm25의 BM25Okapi와 같게 맞췄다 (k1=1.5, b=0.75, 음수 idf는 평균 idf × 0.25로 대체).
"""

import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from scripts.defect_precedent.nhtsa import OUT_DIR

K1, B, EPSILON = 1.5, 0.75, 0.25
KS = (1, 3, 5, 10)


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25:
    def __init__(self, docs: list[list[str]]):
        self.doc_len = [len(d) for d in docs]
        self.avgdl = sum(self.doc_len) / len(docs)
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, doc in enumerate(docs):
            for term, tf in Counter(doc).items():
                self.postings[term].append((i, tf))
        n = len(docs)
        idf = {
            t: math.log(n - len(p) + 0.5) - math.log(len(p) + 0.5) for t, p in self.postings.items()
        }
        floor = EPSILON * sum(idf.values()) / len(idf)
        self.idf = {t: (v if v >= 0 else floor) for t, v in idf.items()}
        self.n = n

    def top(self, query: list[str], k: int) -> list[int]:
        scores: dict[int, float] = defaultdict(float)
        for term in query:  # 질문에 같은 단어가 여러 번 나오면 여러 번 더한다 (rank_bm25와 같음)
            for i, tf in self.postings.get(term, ()):
                denom = tf + K1 * (1 - B + B * self.doc_len[i] / self.avgdl)
                scores[i] += self.idf[term] * tf * (K1 + 1) / denom
        return sorted(scores, key=lambda i: (-scores[i], i))[:k]


def evaluate(cards: list[dict], questions: list[dict]) -> dict[str, dict[int, float]]:
    ids = [c["campno"] for c in cards]
    index = BM25([tokenize(" ".join((c["defect"], c["consequence"], c["remedy"]))) for c in cards])
    hits = {"any": Counter(), "first": Counter()}
    for q in questions:
        top = [ids[i] for i in index.top(tokenize(q["question"]), max(KS))]
        gold = q["gold_campnos"]
        for k in KS:
            hits["any"][k] += any(g in top[:k] for g in gold)
            hits["first"][k] += gold[0] in top[:k]
    return {name: {k: c[k] / len(questions) for k in KS} for name, c in hits.items()}


def main(baseline: Path | None = None) -> None:
    eval_path = OUT_DIR / "eval.jsonl"
    if not (OUT_DIR / "recalls.jsonl").exists() or not eval_path.exists():
        sys.exit("recalls.jsonl·eval.jsonl이 없다 — 먼저 `... nhtsa build`를 실행한다")
    cards = [json.loads(line) for line in (OUT_DIR / "recalls.jsonl").open(encoding="utf-8")]
    questions = [json.loads(line) for line in eval_path.open(encoding="utf-8")]
    if baseline is not None:
        # 기준 실행과 같은 질문만 — 원본이 갱신돼 질문이 늘거나 줄어도 같은 시험지로 비교한다
        base = json.loads(baseline.read_text(encoding="utf-8"))
        same_file = hashlib.sha256(eval_path.read_bytes()).hexdigest() == base["eval_sha256"]
        by_action = {q["action_no"]: q for q in questions}
        gone = [a for a in base["eval_action_nos"] if a not in by_action]
        if gone:
            sys.exit(f"기준 질문 중 지금 시험지에 없는 것 {len(gone)}개: {gone[:5]}")
        questions = [by_action[a] for a in base["eval_action_nos"]]
        print(
            f"기준 파일 {baseline.name}: eval.jsonl {'같음' if same_file else '달라짐 (질문 목록으로 맞춤)'}"
        )
    result = evaluate(cards, questions)
    print(f"리콜 {len(cards):,}건 색인, 질문 {len(questions):,}개 (대리 평가)")
    for name, label in (
        ("any", "연결 리콜 중 하나라도 (주 지표)"),
        ("first", "첫 번째 연결 리콜만 (참고)"),
    ):
        scores = " · ".join(f"Hit@{k} {result[name][k]:.3f}" for k in KS)
        print(f"  {label}: {scores}")
    print("  2026-10-06 기준값: Hit@10 0.511 (주) / 0.505 (참고)")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(Path(args[1]) if args[:1] == ["--baseline"] and len(args) == 2 else None)

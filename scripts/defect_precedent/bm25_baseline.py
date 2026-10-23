"""시험지(eval.jsonl)로 BM25 기준 점수(Hit@1·3·5·10)를 잰다. 외부 패키지 없이 표준 라이브러리만 쓴다.

사용법: uv run python -m scripts.defect_precedent.bm25_baseline [--baseline scripts/defect_precedent/baseline_2026-10-06_maker-aliases.json]

색인 대상은 리콜 카드의 결함·결과·시정 텍스트만이다 (조사 요약은 시험 질문의 출처라 넣지 않는다 — 누수 방지).
주 지표는 "연결 리콜 중 하나라도 상위 k개 안"이고, "첫 번째 연결 리콜만"은 참고값이다.
이 시험은 대리 평가다 (docs/product/기획_결함선례.md 6절).
점수 공식은 rank_bm25의 BM25Okapi와 같게 맞췄다 (k1=1.5, b=0.75, 음수 idf는 평균 idf × 0.25로 대체).
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from scripts.defect_precedent.nhtsa import OUT_DIR, same_baseline_inputs, verify_build

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


def main(baseline: Path | None = None, allow_drift: bool = False) -> None:
    eval_path = OUT_DIR / "eval.jsonl"
    if not (OUT_DIR / "recalls.jsonl").exists() or not eval_path.exists():
        sys.exit("recalls.jsonl·eval.jsonl이 없다 — 먼저 `... nhtsa build`를 실행한다")
    cards = [json.loads(line) for line in (OUT_DIR / "recalls.jsonl").open(encoding="utf-8")]
    questions = [json.loads(line) for line in eval_path.open(encoding="utf-8")]
    label = "대리 평가"
    if baseline is not None:
        base = json.loads(baseline.read_text(encoding="utf-8"))
        by_action = {q["action_no"]: q for q in questions}
        gone = [a for a in base["eval_action_nos"] if a not in by_action]
        if gone:
            sys.exit(f"기준 질문 중 지금 시험지에 없는 것 {len(gone)}개: {gone[:5]}")
        questions = [by_action[a] for a in base["eval_action_nos"]]
        info = verify_build()
        same = same_baseline_inputs(info, base["build"])
        if same:
            label = f"대리 평가 · {baseline.name} 재현 (원본·카드·시험지 sha256 일치)"
        elif allow_drift:
            label = f"대리 평가 · {baseline.name}의 질문 번호로 현재 데이터 재평가 (재현 아님)"
        else:
            sys.exit(
                "원본·카드·시험지가 기준 파일과 다르다 — 같은 원본 사본(data/raw/nhtsa.<받은 시각>)으로 build하거나,"
                " 현재 데이터로 같은 질문 번호만 재평가하려면 --allow-drift를 붙인다"
            )
    result = evaluate(cards, questions)
    print(f"리콜 {len(cards):,}건 색인, 질문 {len(questions):,}개 ({label})")
    for name, label in (
        ("any", "연결 리콜 중 하나라도 (주 지표)"),
        ("first", "첫 번째 연결 리콜만 (참고)"),
    ):
        scores = " · ".join(f"Hit@{k} {result[name][k]:.3f}" for k in KS)
        print(f"  {label}: {scores}")
    print("  2026-10-06 기준값: Hit@10 0.510 (주) / 0.503 (참고)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BM25 기준 점수 (대리 평가)")
    parser.add_argument(
        "--baseline", type=Path, help="기준 파일의 질문 목록만 쓰고 입력 sha256을 확인한다"
    )
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="입력이 기준과 달라도 같은 질문 번호로 재평가한다",
    )
    args = parser.parse_args()
    if args.baseline is not None and not args.baseline.exists():
        parser.error(f"기준 파일이 없다: {args.baseline}")
    if args.allow_drift and args.baseline is None:
        parser.error("--allow-drift는 --baseline과 함께 쓴다")
    main(args.baseline, args.allow_drift)

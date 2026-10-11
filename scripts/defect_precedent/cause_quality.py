"""원인 품질 표본 30건 — 서버가 선례 카드에 붙여 보여 주는 원인 글이 실제로 원인을 말하는지 사람이 확인한다(기획 6절 표 "원인 품질").

사용법:
    # 표시 시트 만들기 — 서버의 카드 벡터 로컬 사본(data/processed/defect/vector_cache/, 서버를 한 번 띄우면 생긴다)을 쓴다.
    # DB·유료 API 호출 없음
    uv run python -m scripts.defect_precedent.cause_quality sheet --out <폴더>
    # 사람이 표시한 뒤 비율 계산
    uv run python -m scripts.defect_precedent.cause_quality score --sheet <폴더>/cause_quality_sheet.csv

표본 규칙(2026-10-11, 표본·표시를 보기 전에 고정 — 결과를 보고 고치지 않는다, AGENTS.md 5-2):
1. 749문항 대리 평가 질문을 시드 `SEED`로 섞는다.
2. 질문마다 서버 검색(`server.rag.search.Searcher`, DEC-039 — BM25 + bge-small RRF)의 **합친 순위 상위 10건**에서
   **원인 글이 있는 카드**를 모은다(화면의 고객사·그 밖 구역 배치와는 다르다 — 순위만 본다). 원인 글 = 573 원인 칸 원문
   (`server.rag.causes.cause_573`이 `filled`로 돌려주는 것 — 서버 응답과 같은 함수)
   또는 그 카드에 연결된 NHTSA 조사 요약(`server.rag.investigations`, 서버와 같은 연결 규칙). 단 **질문의 출처인 조사 자신의
   요약은 뺀다** — 질문 문장과 같은 글이라 원인 판단을 부풀린다.
3. 모은 (카드, 원인 글) 중 하나를 같은 시드의 난수로 고르고, 이미 고른 리콜 번호는 건너뛴다. 30건이 차면 멈춘다.
4. 시트에는 질문·카드 원문·원인 글·말한 주체만 넣고 순위·검색 방식은 넣지 않는다. 표시(`label`)는 사람이 한다 — AI는 표시하지 않는다.

표시 기준(시트의 `label`): `yes` = 이 글이 이 리콜의 결함 원인(왜 생겼나)을 말한다 / `no` = 원인을 말하지 않는다(현상·조사 경과·
"원인 미확인"만 등) / `unsure` = 판단하기 어렵다. 보고는 yes 비율(분모 = yes+no, unsure는 따로)과 Wilson 95% 구간만 낸다.
"""

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path

from scripts.defect_precedent.cause_trials import sample_sha, text_sha

SEED = 20261011
N = 30
TOP = 10
COLS = [
    "sample_no", "question_action", "question", "campno", "maker", "components", "defect",
    "cause_source", "speaker", "cause_ref", "cause_text", "text_sha256", "label", "labeler_id", "note",
]  # fmt: skip
LABELS = ("yes", "no", "unsure")


def wilson(hits: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(max(0.0, center - half), 3), round(min(1.0, center + half), 3)


def cause_texts(
    card: dict, causes: dict, unreadable: dict, investigations: dict, question_action: str
) -> list[dict]:
    """서버가 이 카드에 붙여 보여 주는 원인 글들(573 원인 원문·조사 요약). 질문 출처 조사의 요약은 뺀다."""
    from server.rag.causes import SPEAKER_573, cause_573
    from server.rag.investigations import SPEAKER_INV

    out = []
    cause = cause_573(card, causes, unreadable)
    if cause["status"] == "filled":
        out.append(
            {
                "cause_source": "573",
                "speaker": SPEAKER_573,
                "cause_ref": cause["source"]["campaign"],
                "cause_text": cause["text"],
            }  # fmt: skip
        )
    for inv in investigations.get(card["campno"], []):
        if inv["action"] != question_action:
            out.append(
                {
                    "cause_source": "조사 요약",
                    "speaker": SPEAKER_INV,
                    "cause_ref": inv["action"],
                    "cause_text": inv["summary"],
                }  # fmt: skip
            )
    return out


def draw(
    questions: list[dict],
    rankings: dict[str, list[str]],
    by_id: dict,
    causes: dict,
    unreadable: dict,
    investigations: dict,
) -> list[dict]:
    """표본 규칙 1~3. rankings = 질문 번호 → 합친 순위."""
    rng = random.Random(SEED)
    order = list(questions)
    rng.shuffle(order)
    picked, seen = [], set()
    for q in order:
        pool = [
            (cid, ct)
            for cid in rankings[q["action_no"]][:TOP]
            if cid not in seen
            for ct in cause_texts(by_id[cid], causes, unreadable, investigations, q["action_no"])
        ]
        if not pool:
            continue
        cid, ct = pool[rng.randrange(len(pool))]
        seen.add(cid)
        card = by_id[cid]
        picked.append(
            {
                "sample_no": len(picked) + 1,
                "question_action": q["action_no"],
                "question": q["question"],
                "campno": cid,
                "maker": card["maker"],
                "components": "; ".join(card["components"]),
                "defect": card["defect"],
                **ct,
                "text_sha256": text_sha(ct["cause_text"]),
                "label": "",
                "labeler_id": "",
                "note": "",
            }
        )
        if len(picked) == N:
            break
    return picked


def cached_vectors(build_id: str, n: int):
    """서버가 쓴 카드 벡터 로컬 사본(`embeddings.load_vectors`). 옆의 sha256과 같을 때만 쓴다 — 값이 지금 모델과 같은지는
    `verify_probe`가 카드 16장을 다시 임베딩해 본다."""
    import numpy as np

    from server.rag import embeddings

    path = embeddings.CACHE_DIR / f"{build_id}_{embeddings.MODEL.replace('/', '_')}.npy"
    digest = path.with_suffix(".sha256")
    if not (path.exists() and digest.exists()):
        sys.exit(f"{path}가 없다 — 서버를 한 번 띄워(`uvicorn server.api:app`) 로컬 사본을 만든다")
    if digest.read_text().strip() != hashlib.sha256(path.read_bytes()).hexdigest():
        sys.exit(f"{path.name}이 옆의 sha256과 다르다 — 서버를 다시 띄워 사본을 새로 받는다")
    vecs = np.load(path)
    if vecs.shape != (n, 384):
        sys.exit(f"{path.name}의 모양 {vecs.shape}이 카드 수 {n}과 맞지 않는다")
    return vecs


def cmd_sheet(a) -> None:
    from fastembed import TextEmbedding

    from scripts.defect_precedent.retrieval_compare import card_text, load
    from server.rag import embeddings
    from server.rag.build import load_build
    from server.rag.investigations import load_investigations
    from server.rag.search import Searcher

    build = load_build()
    embeddings.check_fastembed()
    texts = [card_text(c) for c in build.cards]
    vecs = cached_vectors(build.build_id, len(texts))
    model = TextEmbedding(embeddings.MODEL)
    embeddings.verify_probe(model, texts, vecs)
    searcher = Searcher(build.cards, vecs, model)
    invs = load_investigations(build.raw_manifest_sha256, {c["campno"] for c in build.cards})
    _, questions = load()
    qv = searcher.query_vectors([q["question"] for q in questions])
    rankings = {
        q["action_no"]: searcher.search(q["question"], v).ranking
        for q, v in zip(questions, qv, strict=True)
    }
    by_id = {c["campno"]: c for c in build.cards}
    rows = draw(questions, rankings, by_id, build.causes, build.unreadable, invs)
    a.out.mkdir(parents=True, exist_ok=True)
    sheet = a.out / "cause_quality_sheet.csv"
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    meta = {
        "build_id": build.build_id,
        "seed": SEED,
        "n": len(rows),
        "top": TOP,
        "sample_sha256": sample_sha(
            [(r["campno"] + ":" + r["cause_ref"], r["text_sha256"]) for r in rows]
        ),
        "sheet_sha256": hashlib.sha256(sheet.read_bytes()).hexdigest(),
    }
    sheet.with_name(sheet.name + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), "utf-8"
    )
    print(json.dumps({**meta, "sheet": str(sheet)}, ensure_ascii=False))


def score(rows: list[dict]) -> dict:
    edited = [r["sample_no"] for r in rows if text_sha(r["cause_text"]) != r["text_sha256"]]
    if edited:
        sys.exit(f"시트의 cause_text가 text_sha256과 다르다(원문을 고치지 않는다): {edited[:5]}")
    bad = [r["sample_no"] for r in rows if r["label"].strip() not in LABELS]
    if bad:
        sys.exit(f"표시가 비었거나 yes/no/unsure가 아닌 줄: {bad[:5]}")
    no_id = [r["sample_no"] for r in rows if not r["labeler_id"].strip()]
    if no_id:
        sys.exit(f"labeler_id가 빈 줄: {no_id[:5]}")
    count = {lab: sum(r["label"].strip() == lab for r in rows) for lab in LABELS}
    decided = count["yes"] + count["no"]
    by_source = {}
    for src in sorted({r["cause_source"] for r in rows}):
        sub = [r for r in rows if r["cause_source"] == src]
        y = sum(r["label"].strip() == "yes" for r in sub)
        d = sum(r["label"].strip() in ("yes", "no") for r in sub)
        by_source[src] = {"n": len(sub), "yes": y, "decided": d}
    return {
        "n": len(rows),
        "counts": count,
        "yes_rate": round(count["yes"] / decided, 3) if decided else None,
        "yes_rate_wilson95": wilson(count["yes"], decided),
        "by_source": by_source,
        "note": "분모 = yes+no(unsure는 따로). 서버가 보여 주는 원인 글이 원인을 말하는 비율 — 원인이 옳은지는 판정하지 않는다",
    }


def cmd_score(a) -> None:
    with a.sheet.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    meta_path = a.sheet.with_name(a.sheet.name + ".meta.json")
    meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else None
    if meta is None:
        sys.exit(f"{meta_path.name}이 없다 — 시트를 만든 기록 없이 채점하지 않는다")
    got = sample_sha([(r["campno"] + ":" + r["cause_ref"], r["text_sha256"]) for r in rows])
    if got != meta["sample_sha256"]:
        sys.exit("시트의 표본이 만들 때와 다르다(줄을 빼거나 더했다)")
    print(
        json.dumps(
            {**score(rows), "build_id": meta["build_id"], "seed": meta["seed"]},
            ensure_ascii=False,
            indent=1,
        )
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sh = sub.add_parser("sheet", help="표시 시트 만들기")
    sh.add_argument("--out", type=Path, required=True)
    sc = sub.add_parser("score", help="표시한 시트로 비율 계산")
    sc.add_argument("--sheet", type=Path, required=True)
    a = p.parse_args(argv)
    {"sheet": cmd_sheet, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()

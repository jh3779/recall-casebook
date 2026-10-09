"""시점 평가 후보 묶음과 정답 표시 시트 만들기 (DEC-037, 기획 6절 "시점 평가").

사용법:
    uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.time_eval_candidates \
        --questions scripts/defect_precedent/time_eval_questions.json --set pilot --out-dir <폴더>

- 색인: 문항마다 기준일(`open_date`) **이전에 접수된** 리콜 카드만(`received_date < open_date`). 카드 글은 결함·결과·시정이고
  573 원인 문장은 넣지 않는다(DEC-037).
- 후보: BM25 상위 20 + B 방식(BM25 + bge-small, RRF k=60) 상위 20의 합집합. BM25의 IDF도 기준일 이전 카드로 계산한다.
  뜻 검색은 전체 카드 임베딩(캐시)에서 기준일 이전 카드만 남겨 고른다 — 임베딩은 카드마다 따로 계산되므로 결과가 같다.
- 시트(`labels_<set>.csv`): 문항·후보를 **출처·순위를 숨기고** 문항별로 섞어(action_no·campno 해시 순) 보여 준다.
  같은 리콜의 다른 번호는 `dup_group`이 같다. 표시자는 `label`(yes = 그때 있던 같은 부품 선례 / no / unsure)과 `labeler_id`·`note`를 적고, 두 사람이 함께 표시한 문항의 합의 결과는 `agreed_label`에 적는다(`label`은 합의 전 표시 그대로). AI는 표시하지 않는다(AGENTS.md 5-2).
- 숨긴 정보(`candidates_<set>.json`): 후보별 출처·순위, 기준일 이전 카드 수, 입력 해시, 코드 커밋·스크립트 sha256(커밋하지 않은 변경이 있으면 `--allow-dirty` 없이는 멈춤). 시트 파일의 sha256은 표시자에게 넘길 때 따로 기록한다. 표시가 끝난 뒤 채점에만 쓰고 표시자에게 주지 않는다.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from scripts.defect_precedent.bm25_baseline import BM25, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR
from scripts.defect_precedent.retrieval_compare import (
    card_text,
    embed_cards,
    provenance,
    read_jsonl,
    rrf,
)
from scripts.defect_precedent.time_eval_questions import (  # DEC-037 ⑥ — 질문 파일을 만든 쪽과 같은 상수
    MOD_GAP_MAX_DAYS,
)

MODEL = "BAAI/bge-small-en-v1.5"
TOP = 20
DEPTH = 100  # RRF에 넣는 각 순위의 길이 (retrieval_compare와 같음)


ROOT = Path(__file__).resolve().parents[2]
CODE_FILES = [
    "scripts/defect_precedent/time_eval_candidates.py",
    "scripts/defect_precedent/retrieval_compare.py",
    "scripts/defect_precedent/bm25_baseline.py",
]


def code_provenance(allow_dirty: bool) -> dict:
    """후보를 만든 코드 (DEC-037 ⑦ — 모든 회차가 같은 코드여야 한다). 커밋과 함께 스크립트 sha256을 남긴다 —
    squash 병합 뒤에는 브랜치 커밋이 main에 없으므로 내용 해시로 대조한다. git이 실패하면 시트를 쓰기 전에 멈춘다."""
    import subprocess

    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as e:
            raise SystemExit(
                f"git {' '.join(args)} 실패 — 코드 판본을 기록할 수 없어 멈춘다: {e}"
            ) from e

    dirty = git("status", "--porcelain", "--", "scripts/")
    if dirty and not allow_dirty:
        raise SystemExit("scripts/에 커밋하지 않은 변경이 있다 — 커밋한 뒤 돌리거나 --allow-dirty")
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(dirty),
        "script_sha256": {
            f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in CODE_FILES
        },
    }


def shuffle_key(action_no: str, campno: str) -> str:
    return hashlib.sha256(f"{action_no}:{campno}".encode()).hexdigest()


def unusable_questions(questions: list[dict]) -> list[str]:
    """원문 대조를 통과하지 못했거나, 확보되지 않았거나, PDF 수정일이 없거나 개시일보다 3일 넘게 늦은 문항."""
    bad = []
    for q in questions:
        gap = q.get("pdf_mod_gap_days")
        if (
            q.get("check") != "통과"
            or q.get("status") != "확보"
            or gap is None
            or gap > MOD_GAP_MAX_DAYS
        ):
            bad.append(q.get("action_no", "?"))
    return bad


def indexed_before(cards: list[dict], open_date: str) -> list[int]:
    """기준일 **이전에** 접수된 카드만 (당일 접수는 뺀다). 날짜는 둘 다 YYYYMMDD 문자열."""
    return [i for i, c in enumerate(cards) if c["received_date"] < open_date]


def candidates_for(q: dict, cards: list[dict], toks: list[list[str]], vecs, qvec) -> dict:
    import numpy as np

    keep = indexed_before(cards, q["open_date"])
    ids = [cards[i]["campno"] for i in keep]
    bm = BM25([toks[i] for i in keep])
    bm_rank = [ids[j] for j in bm.top(tokenize(q["question"]), DEPTH)]
    sims = vecs[keep] @ qvec
    dense_rank = [ids[j] for j in np.argsort(-sims)[:DEPTH]]
    b_rank = rrf(bm_rank, dense_rank)
    pool = {}
    for name, rank in (("bm25", bm_rank[:TOP]), ("b_rrf", b_rank[:TOP])):
        for r, cid in enumerate(rank):
            pool.setdefault(cid, {})[name] = r + 1
    return {"n_indexed": len(keep), "pool": pool}


def main(argv: list[str] | None = None) -> None:
    import numpy as np

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument(
        "--set", required=True, help="질문 파일의 묶음 이름(pilot, main, 대체 회차 묶음 등)"
    )
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="커밋하지 않은 scripts/ 변경이 있어도 진행(기록에 dirty 표시)",
    )
    a = p.parse_args(argv)

    data = provenance()
    code = code_provenance(a.allow_dirty)  # 시트를 쓰기 전에 확인한다
    qfile = json.loads(a.questions.read_text(encoding="utf-8"))
    if a.set not in qfile or not isinstance(qfile[a.set], list):
        raise SystemExit(f"질문 파일에 '{a.set}' 묶음이 없다")
    questions = qfile[a.set]
    bad = unusable_questions(questions)
    if bad:
        raise SystemExit(f"시트에 쓸 수 없는 문항(원문 대조·확보·PDF 수정일 3일, DEC-037 ⑥): {bad}")
    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    texts = [card_text(c) for c in cards]
    toks = [tokenize(t) for t in texts]
    model, vecs, _, emb_info = embed_cards(MODEL, texts)
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    qv = np.array(list(model.query_embed([q["question"] for q in questions])), dtype="float32")
    qv /= np.linalg.norm(qv, axis=1, keepdims=True)
    by_id = {c["campno"]: c for c in cards}

    a.out_dir.mkdir(parents=True, exist_ok=True)
    hidden, rows = [], []
    for q, v in zip(questions, qv, strict=True):
        cand = candidates_for(q, cards, toks, vecs, v)
        hidden.append({"action_no": q["action_no"], "open_date": q["open_date"], **cand})
        order = sorted(cand["pool"], key=lambda cid: shuffle_key(q["action_no"], cid))
        for n, cid in enumerate(order, 1):
            c = by_id[cid]
            rows.append(
                [
                    q["action_no"],
                    q["open_date"],
                    q["question"],
                    n,
                    cid,
                    c["dup_group"],
                    c["received_date"],
                    c["maker"],
                    "; ".join(c["components"]),
                    c["defect"],
                    c["consequence"],
                    c["remedy"],
                    "",
                    "",
                    "",
                    "",
                ]
            )
    sheet = a.out_dir / f"labels_{a.set}.csv"
    with sheet.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "action_no",
                "open_date",
                "question",
                "candidate_no",
                "campno",
                "dup_group",
                "received_date",
                "maker",
                "components",
                "defect",
                "consequence",
                "remedy",
                "label",
                "agreed_label",
                "labeler_id",
                "note",
            ]
        )
        w.writerows(rows)
    meta = {
        "data": data,
        "questions_file": str(a.questions),
        "questions_sha256": hashlib.sha256(a.questions.read_bytes()).hexdigest(),
        "code": code,
        "set": a.set,
        "model": MODEL,
        "embedding": emb_info,
        "top": TOP,
        "items": hidden,
    }
    (a.out_dir / f"candidates_{a.set}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    sizes = [len(h["pool"]) for h in hidden]
    print(
        json.dumps(
            {
                "set": a.set,
                "questions": len(questions),
                "rows": len(rows),
                "pool_sizes": sizes,
                "n_indexed": [h["n_indexed"] for h in hidden],
                "sheet": str(sheet),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

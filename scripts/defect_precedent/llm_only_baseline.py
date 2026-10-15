"""LLM 단독 기준선 — 연구용. 검색 결과 없이 질문만 LLM에게 주고, 돌려준 리콜 번호·원인 서술을 데이터와 자동 대조한다.

사용법: uv run --with openai --env-file .env python -m scripts.defect_precedent.llm_only_baseline [--n 3] --out <결과.jsonl>
      채점만(API 호출 없음): uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.llm_only_baseline --score <결과.jsonl>

- 질문: 749문항(`eval.jsonl`) 원문에서 리콜 번호 모양(`00V057000`·`00V-057`·`00V057` 등)만 `[RECALL NO.]`로 가린다.
  126문항은 질문 글에 정답 번호가 들어 있어, 가리지 않으면 베끼기만 해도 맞힌 것으로 센다. 우리 검색도 같은 가린 질문으로 다시 잰다.
- LLM은 질문만 받고 같은 결함의 NHTSA 리콜 번호를 최대 10개, 알면 제조사가 밝힌 원인을 원문 그대로 돌려준다(모르면 비움).
- 채점(AI 없음, 정답은 정부 기록 `gold_campnos` — AGENTS.md 5-2):
  지어낸 번호 = 형식은 맞지만 리콜 데이터(`recalls.jsonl`)에 없는 캠페인, Hit@k = 앞 6자리(캠페인) 기준,
  원인 원문 일치 = 돌려준 원인이 그 캠페인의 573 원인 칸(`causes.jsonl` filled)에 공백 정리 뒤 그대로 들어 있는가.
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.defect_precedent.bm25_baseline import KS, tokenize
from scripts.defect_precedent.cause_trials import model_and_effort
from scripts.defect_precedent.nhtsa import OUT_DIR, RCLRPT_FROM
from scripts.defect_precedent.retrieval_compare import (
    bm25_rankings,
    card_text,
    embed_cards,
    provenance,
    read_jsonl,
    rrf,
)

MASK = "[RECALL NO.]"
# 끝은 \b가 아니라 "숫자가 이어지지 않음" — 원문에 `06V-213THAT`처럼 번호 뒤에 글자가 붙은 문항이 있다
ID_RE = re.compile(r"\b\d{2}\s?[A-Z]\s?-?\s?\d{3}(?:\d{3})?(?!\d)")
CAMPNO_RE = re.compile(r"^(\d{2}[A-Z]\d{3})(\d{3})?$")
INSTRUCTIONS = (
    "You are asked about U.S. NHTSA vehicle safety recalls. Given a description of a vehicle defect, list up to 10 "
    "NHTSA recall campaign numbers (format like 00V057000) for recalls that concern the same defect, most likely first. "
    "For each recall, give the manufacturer's stated cause of the defect quoted exactly as written in its Part 573 "
    "report if you know it; leave the cause empty if you do not know it. Answer from your own knowledge."
)
# OpenAI 모델 문서(2026-10-12 확인, docs/실험_LLM_Luna비교.md 1절) — 100만 토큰당 달러, 비용 추정에만 쓴다
PRICE = {"gpt-6-luna": (0.10, 0.50)}


def mask_ids(text: str) -> str:
    return ID_RE.sub(MASK, text)


def norm_campno(raw: str) -> str | None:
    """`00V-057`·`00 V 057 000`처럼 적은 번호를 `00V057000`/`00V057`로 — 형식이 다르면 None."""
    s = re.sub(r"[\s\-]", "", raw.upper())
    return s if CAMPNO_RE.match(s) else None


def squash(text: str) -> str:
    return " ".join(text.split())


def ask(model: str, effort: str | None, question: str) -> dict:
    from openai import OpenAI
    from pydantic import BaseModel

    class Recall(BaseModel):
        campno: str
        cause: str

    class Answer(BaseModel):
        recalls: list[Recall]

    t = time.perf_counter()
    try:
        rsp = OpenAI().responses.parse(
            model=model,
            instructions=INSTRUCTIONS,
            input=question,
            text_format=Answer,
            **({"reasoning": {"effort": effort}} if effort else {}),
        )
    except Exception as e:  # 한 문항의 실패가 전체를 멈추지 않게 기록만 하고 채점에서 따로 센다
        return {"error": f"{type(e).__name__}: {e}"[:300], "sec": round(time.perf_counter() - t, 2)}
    got = rsp.output_parsed
    return {
        "recalls": [r.model_dump() for r in got.recalls] if got else None,
        "used_model": getattr(rsp, "model", None),
        "in_tok": rsp.usage.input_tokens,
        "out_tok": rsp.usage.output_tokens,
        "sec": round(time.perf_counter() - t, 2),
    }


def run(model: str | None, effort: str | None, n: int | None, out: Path, workers: int) -> None:
    model, effort = model_and_effort(model, effort)
    questions = read_jsonl(OUT_DIR / "eval.jsonl")[:n]
    masked = [mask_ids(q["question"]) for q in questions]
    with ThreadPoolExecutor(workers) as ex:
        answers = list(ex.map(lambda m: ask(model, effort, m), masked))
    with out.open("w") as f:
        for q, m, a in zip(questions, masked, answers, strict=True):
            f.write(json.dumps({"action_no": q["action_no"], "masked_question": m, **a}) + "\n")
    meta = {
        "model": model,
        "reasoning_effort": effort,
        "n": len(questions),
        "instructions": INSTRUCTIONS,
        "mask_re": ID_RE.pattern,
        "inputs": provenance(),
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    in_tok = sum(a.get("in_tok", 0) for a in answers)
    out_tok = sum(a.get("out_tok", 0) for a in answers)
    p_in, p_out = PRICE.get(model, (0, 0))
    print(
        json.dumps(
            {
                "n": len(answers),
                "errors": sum("error" in a for a in answers),
                "in_tok": in_tok,
                "out_tok": out_tok,
                "usd_est": round(in_tok / 1e6 * p_in + out_tok / 1e6 * p_out, 4),
                "used_models": sorted(
                    {a.get("used_model") or "?" for a in answers if "error" not in a}
                ),
            },
            ensure_ascii=False,
        )
    )


def score_llm(
    rows: list[dict], questions: list[dict], campaigns: set[str], causes: dict[str, str]
) -> dict:
    """LLM 결과 채점. 지어낸 번호는 형식이 맞는 번호 중 데이터에 없는 캠페인의 비율."""
    gold = {q["action_no"]: {g[:6] for g in q["gold_campnos"]} for q in questions}
    hits = {k: 0 for k in KS}
    c = {
        "answered": 0,
        "abstained": 0,
        "errors": 0,
        "ids": 0,
        "bad_format": 0,
        "fabricated": 0,
        "q_with_fabricated": 0,
        "causes_given": 0,
        "cause_verbatim": 0,
        "cause_not_in_573": 0,
        "cause_no_573": 0,
    }
    for r in rows:
        if "error" in r or r.get("recalls") is None:
            c["errors"] += 1
            continue
        recs = r["recalls"][:10]
        c["answered" if recs else "abstained"] += 1
        ranked, fab_here = [], False
        for rec in recs:
            cid = norm_campno(rec["campno"])
            if cid is None:
                c["bad_format"] += 1
                continue
            c["ids"] += 1
            camp = cid[:6]
            ranked.append(camp)
            if camp not in campaigns:
                c["fabricated"] += 1
                fab_here = True
            if rec["cause"].strip():
                c["causes_given"] += 1
                src = causes.get(camp)
                if src is None:
                    c["cause_no_573"] += 1
                elif squash(rec["cause"]) in squash(src):
                    c["cause_verbatim"] += 1
                else:
                    c["cause_not_in_573"] += 1
        c["q_with_fabricated"] += fab_here
        for k in KS:
            hits[k] += bool(gold[r["action_no"]] & set(ranked[:k]))
    n = len(rows)
    return {
        "n": n,
        **{f"hit@{k}": round(hits[k] / n, 3) for k in KS},
        **c,
        "fabricated_rate": round(c["fabricated"] / c["ids"], 3) if c["ids"] else None,
    }


def rrf_tops(queries: list[str]) -> tuple[list[list[str]], dict]:
    """서버와 같은 계산(BM25 상위 100 + bge-small 상위 100, RRF)으로 질문마다 상위 10개 리콜 번호."""
    import numpy as np

    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    texts = [card_text(c) for c in cards]
    ids = [c["campno"] for c in cards]
    model, vecs, _, emb = embed_cards("BAAI/bge-small-en-v1.5", texts)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    qv = np.array(list(model.query_embed(queries)), dtype="float32")
    qv /= np.linalg.norm(qv, axis=1, keepdims=True)
    dense = [[ids[i] for i in np.argsort(-row)[:100]] for row in qv @ vecs.T]
    bm, _ = bm25_rankings([tokenize(t) for t in texts], [tokenize(q) for q in queries], ids)
    return [rrf(a, b)[:10] for a, b in zip(bm, dense, strict=True)], emb


def hit_rates(questions: list[dict], tops: list[list[str]]) -> dict:
    """Hit@k — 캠페인 6자리 기준(LLM 채점과 같은 기준). 검색 결과는 모두 색인 안 번호라 지어낸 번호는 0."""
    hits = {k: 0 for k in KS}
    for q, top in zip(questions, tops, strict=True):
        g = {x[:6] for x in q["gold_campnos"]}
        for k in KS:
            hits[k] += bool(g & {t[:6] for t in top[:k]})
    n = len(questions)
    return {"n": n, **{f"hit@{k}": round(hits[k] / n, 3) for k in KS}, "fabricated": 0}


def score(path: Path) -> None:
    rows = read_jsonl(path)
    questions = {q["action_no"]: q for q in read_jsonl(OUT_DIR / "eval.jsonl")}
    qs = [questions[r["action_no"]] for r in rows]
    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    received = {c["campno"]: c["received_date"] for c in cards}
    campaigns = {c["campno"][:6] for c in cards}
    causes = {
        c["campaign"]: c["cause_text"]
        for c in read_jsonl(OUT_DIR / "causes.jsonl")
        if c["cause_status"] == "filled"
    }
    masked_tops, emb = rrf_tops([r["masked_question"] for r in rows])
    raw_tops, _ = rrf_tops(
        [q["question"] for q in qs]
    )  # 가리지 않은 원래 질문 — 기존 보고치와 대조용

    def gold_in(q):
        return any(
            g[:6] in q["question"].replace("-", "").replace(" ", "") for g in q["gold_campnos"]
        )

    subsets = {
        "all": lambda q: True,
        "gold_id_in_question": gold_in,
        "other": lambda q: not gold_in(q),
        "post2014": lambda q: any(received.get(g, "") >= RCLRPT_FROM for g in q["gold_campnos"]),
    }
    report = {"embedding": emb, "llm": {}, "ours_masked": {}, "ours_raw": {}}
    for name, keep in subsets.items():
        idx = [i for i, q in enumerate(qs) if keep(q)]
        if not idx:  # 표본 시험에서는 비는 부분이 있다
            continue
        sub = [qs[i] for i in idx]
        report["llm"][name] = score_llm([rows[i] for i in idx], sub, campaigns, causes)
        report["ours_masked"][name] = hit_rates(sub, [masked_tops[i] for i in idx])
        report["ours_raw"][name] = hit_rates(sub, [raw_tops[i] for i in idx])
    out = path.with_suffix(".score.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path)
    p.add_argument("--score", type=Path, help="결과 파일 채점(API 호출 없음)")
    p.add_argument("--model")
    p.add_argument("--reasoning-effort")
    p.add_argument("--n", type=int, help="앞에서부터 n문항만(표본 시험)")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args(argv)
    if a.score:
        return score(a.score)
    if not a.out:
        sys.exit("--out 또는 --score가 필요하다")
    run(a.model, a.reasoning_effort, a.n, a.out, a.workers)


if __name__ == "__main__":
    main()

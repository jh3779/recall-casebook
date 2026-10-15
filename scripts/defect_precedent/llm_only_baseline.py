"""LLM 단독 기준선 — 연구용. 검색 결과 없이 질문만 LLM에게 주고, 돌려준 리콜 번호·원인 서술을 데이터와 자동 대조한다.

사용법: uv run --with openai --env-file .env python -m scripts.defect_precedent.llm_only_baseline [--n 3] --out <결과.jsonl>
      채점만(API 호출 없음): uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.llm_only_baseline --score <결과.jsonl>

- 질문: 749문항(`eval.jsonl`) 원문에서 리콜 번호 모양(`00V057000`·`00V-057`·`00V057` 등)만 `[RECALL NO.]`로 가린다.
  126문항은 질문 글에 정답 번호가 들어 있어, 가리지 않으면 베끼기만 해도 맞힌 것으로 센다. 우리 검색도 같은 가린 질문으로 다시 잰다.
- LLM은 질문만 받고 같은 결함의 NHTSA 리콜 번호를 최대 10개, 알면 제조사가 밝힌 원인을 원문 그대로 돌려준다(모르면 비움).
- 채점(AI 없음, 정답은 정부 기록 `gold_campnos` — AGENTS.md 5-2):
  지어낸 번호 = 형식은 맞지만 리콜 데이터(`recalls.jsonl`)에 없는 캠페인, Hit@k = 앞 6자리(캠페인) 기준,
  원인 원문 일치 = 돌려준 원인이 그 캠페인의 573 원인 칸 글(`causes.jsonl`의 filled·stated_unknown)에 공백 정리 뒤 그대로
  들어 있는가. 글이 없는 경우(없는 캠페인·573 보고서 없음·원인 칸 빔)는 따로 센다.
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
    # 유료 호출 전에 입력 판본을 읽고 결과 자리를 만든다 — 호출을 다 하고 나서 기록에서 실패하지 않게
    meta = {
        "model": model,
        "reasoning_effort": effort,
        "n": len(questions),
        "instructions": INSTRUCTIONS,
        "mask_re": ID_RE.pattern,
        "inputs": provenance(),
    }
    if (
        out.exists() or out.with_suffix(".meta.json").exists()
    ):  # 옛 결과에 새 메타가 짝지어지지 않게
        sys.exit(f"{out} 또는 그 .meta.json이 이미 있다 — 새 경로로 실행한다")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    with ThreadPoolExecutor(workers) as ex:
        answers = list(ex.map(lambda m: ask(model, effort, m), masked))
    with out.open("w") as f:
        for q, m, a in zip(questions, masked, answers, strict=True):
            f.write(json.dumps({"action_no": q["action_no"], "masked_question": m, **a}) + "\n")
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


def check_result(rows: list[dict], meta: dict, questions: dict[str, dict], inputs: dict) -> None:
    """채점 전 대조 — 결과를 만든 입력 판본이 지금과 같고, 줄 수·문항이 맞고, 가린 질문이 기록된 규칙으로 다시 만든 것과
    같아야 한다(다른 판본을 섞은 점수를 만들지 않는다, AGENTS.md 5-1). 하나라도 다르면 멈춘다."""
    if meta.get("inputs") != inputs:
        sys.exit(f"결과의 입력 판본 {meta.get('inputs')}이 지금 {inputs}과 다르다")
    ids = [r["action_no"] for r in rows]
    if len(rows) != meta.get("n") or len(set(ids)) != len(ids):
        sys.exit(
            f"결과 {len(rows)}줄(중복 {len(ids) - len(set(ids))})이 메타 n={meta.get('n')}과 맞지 않는다"
        )
    rule = re.compile(meta["mask_re"])
    bad = [
        a
        for a in ids
        if a not in questions
        or rule.sub(MASK, questions[a]["question"])
        != next(r for r in rows if r["action_no"] == a)["masked_question"]
    ]
    if bad:
        sys.exit(f"가린 질문이 시험지·기록된 가리기 규칙과 다르다: {bad[:5]}")


def score_llm(
    rows: list[dict],
    questions: list[dict],
    campaigns: dict[str, str],
    causes: dict[str, dict],
    unreadable: dict[str, str],
) -> dict:
    """LLM 결과 채점. 지어낸 번호는 형식이 맞는 번호 중 데이터에 없는 캠페인의 비율(`campaigns`: 캠페인 → 접수일).
    원인은 서버와 같은 함수(`server.rag.causes.cause_573`)로 상태를 가른다 — 573 보고서 없음(범위 밖) / 판독 실패 /
    상태 미확인 / 판본 미확정 / 원인 칸 빔 / 글이 있는 것(filled·stated_unknown — stated_unknown도 원문을 보존한다,
    DEC-047). 판본이 확정되고 글이 있는 것만 공백 정리 뒤 글자 대조한다."""
    from server.rag.causes import cause_573

    gold = {q["action_no"]: {g[:6] for g in q["gold_campnos"]} for q in questions}
    hits = {k: 0 for k in KS}
    c = {
        "answered": 0,
        "abstained": 0,
        "errors": 0,
        "ids": 0,
        "ids_gold": 0,
        "bad_format": 0,
        "fabricated": 0,
        "q_with_fabricated": 0,
        "causes_given": 0,
        "cause_on_fabricated": 0,
        "cause_checked": 0,
        "cause_verbatim": 0,
        "cause_checked_on_gold": 0,  # 정답 리콜에 붙인 원인 — 원문을 옮기는 능력에 가장 가까운 분모
        "cause_verbatim_on_gold": 0,
    }
    status_counts: dict[str, int] = {}
    # 대조한 원인을 상태별로 — stated_unknown 원문은 "NR" 같은 짧은 글이라 원인 문장이 그대로 들어갈 수 없다(구조상 불일치)
    detail: dict[str, dict[str, int]] = {}
    hit1_answered = 0
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
            is_gold = camp in gold[r["action_no"]]
            c["ids_gold"] += is_gold
            if camp not in campaigns:
                c["fabricated"] += 1
                fab_here = True
            if not rec["cause"].strip():
                continue
            c["causes_given"] += 1
            if camp not in campaigns:
                c["cause_on_fabricated"] += 1
                continue
            got = cause_573({"campno": camp, "received_date": campaigns[camp]}, causes, unreadable)
            status_counts[got["status"]] = status_counts.get(got["status"], 0) + 1
            if "text" not in got:
                continue
            hit = squash(rec["cause"]) in squash(got["text"])
            d = detail.setdefault(
                got["status"], {"checked": 0, "verbatim": 0, "on_gold": 0, "verbatim_on_gold": 0}
            )
            d["checked"] += 1
            d["verbatim"] += hit
            d["on_gold"] += is_gold
            d["verbatim_on_gold"] += is_gold and hit
            c["cause_checked"] += 1
            c["cause_verbatim"] += hit
            c["cause_checked_on_gold"] += is_gold
            c["cause_verbatim_on_gold"] += is_gold and hit
        c["q_with_fabricated"] += fab_here
        hit1_answered += bool(recs) and bool(gold[r["action_no"]] & set(ranked[:1]))
        for k in KS:
            hits[k] += bool(gold[r["action_no"]] & set(ranked[:k]))
    n = len(rows)
    return {
        "n": n,
        **{f"hit@{k}": round(hits[k] / n, 3) for k in KS},
        **c,
        "cause_status": dict(sorted(status_counts.items())),
        "cause_check_by_status": dict(sorted(detail.items())),
        # 답한(빈 목록이 아닌) 문항만 분모로 본 Hit@1 — 빈 목록은 지시문이 허용한 행동이라 따로 본다
        "hit@1_answered": round(hit1_answered / c["answered"], 3) if c["answered"] else None,
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
    ids = ids_gold = 0
    for q, top in zip(questions, tops, strict=True):
        g = {x[:6] for x in q["gold_campnos"]}
        ids += len(top)
        ids_gold += sum(t[:6] in g for t in top)
        for k in KS:
            hits[k] += bool(g & {t[:6] for t in top[:k]})
    n = len(questions)
    return {
        "n": n,
        **{f"hit@{k}": round(hits[k] / n, 3) for k in KS},
        "ids": ids,
        "ids_gold": ids_gold,
        "fabricated": 0,
    }


def score(path: Path) -> None:
    rows = read_jsonl(path)
    meta_path = path.with_suffix(".meta.json")
    if not meta_path.exists():
        sys.exit(f"{meta_path}가 없다 — 결과를 만든 입력 판본을 확인할 수 없다")
    questions = {q["action_no"]: q for q in read_jsonl(OUT_DIR / "eval.jsonl")}
    check_result(rows, json.loads(meta_path.read_text()), questions, provenance())
    qs = [questions[r["action_no"]] for r in rows]
    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    received = {c["campno"]: c["received_date"] for c in cards}
    campaigns: dict[str, str] = {}
    for card in cards:  # 캠페인 → 가장 이른 접수일(573 범위 판단에 쓴다, 서버 카드와 같은 값)
        camp = card["campno"][:6]
        campaigns[camp] = min(campaigns.get(camp, card["received_date"]), card["received_date"])
    manifest = json.loads((OUT_DIR / "causes.manifest.json").read_text())
    causes = {  # 서버 build와 같이 원인 명세의 정리 방식을 붙인다(server/rag/build.py, DEC-047)
        c["campaign"]: {**c, "text_basis": manifest.get("text_basis")}
        for c in read_jsonl(OUT_DIR / "causes.jsonl")
    }
    unreadable = dict(
        manifest.get("failed_kinds") or {}
    )  # 서버 build와 같은 출처(server/rag/build.py)
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
    report = {
        "inputs": provenance(),
        "embedding": emb,
        "llm": {},
        "ours_masked": {},
        "ours_raw": {},
    }
    for name, keep in subsets.items():
        idx = [i for i, q in enumerate(qs) if keep(q)]
        if not idx:  # 표본 시험에서는 비는 부분이 있다
            continue
        sub = [qs[i] for i in idx]
        report["llm"][name] = score_llm([rows[i] for i in idx], sub, campaigns, causes, unreadable)
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

"""생성형 RAG 환각 시험 — 연구용. 우리 검색이 고른 상위 10개 선례를 LLM에게 주고 *답을 쓰게* 하면 서비스 원칙 2·3을 얼마나 어기는지 센다.

LLM 단독 기준선(`llm_only_baseline.py`)은 검색 결과 없이 물었다. 이 시험은 그 다음 질문 — "검색 결과를 줘도, 생성하게 하면 지어내는가" — 이다.
서비스 경로는 바꾸지 않는다(서비스에는 LLM이 없다, DEC-039 ③·DEC-056 ④). 정답이 없는 시험이다: Hit@k를 재지 않고 **원칙 위반 수**만 센다.

사용법:
    호출 없이 입력·비용만:  uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.generative_rag_trial --dry-run
    실행:  uv run --with openai --with fastembed==0.9.0 --env-file .env python -m scripts.defect_precedent.generative_rag_trial --out <결과.jsonl>
    채점만(API 호출 없음):  ... --score <결과.jsonl>

- 질문: 749문항(`eval.jsonl`)에서 고정 시드로 무작위 N개. 정답을 보고 고르지 않는다(AGENTS.md 5-2). 질문 속 리콜 번호는 `[RECALL NO.]`로 가린다.
- 검색: 서버와 같은 계산(BM25+bge-small RRF) 상위 10개. LLM에게는 각 선례의 결함·결과·시정 문장과 573 원인 원문(있으면)을 준다.
- 채점(AI 없음): ① 인용한 리콜 번호가 준 10개 밖인가(서비스 원칙 2: 범위 밖 번호는 지어낸 것) ② 원인 인용이 준 원인 원문에 글자 그대로 있는가
  ③ 원인 원문을 주지 않은 선례에 원인을 썼는가 ④ 답 글 속 리콜 번호 모양이 준 10개 밖인가 ⑤ 답 글에 판정 표현이 있는가
  ⑥ 리콜 번호를 달지 않은 문장 수. 의미가 원문과 맞는지(요약이 충실한지)는 자동으로 못 잰다 — 무작위 표본을 사람이 읽는다(점수 파일 `human_read`).
"""

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.ci.pr_checks import PRINCIPLE_PATTERN
from scripts.defect_precedent.cause_trials import model_and_effort
from scripts.defect_precedent.llm_only_baseline import (
    BASELINE,
    ID_RE,
    PRICE,
    check_manifest,
    mask_ids,
    norm_campno,
    rrf_tops,
    squash,
)
from scripts.defect_precedent.nhtsa import OUT_DIR
from scripts.defect_precedent.retrieval_compare import provenance, read_jsonl

SEED = 20261016
N_DEFAULT = 100
HUMAN_READ = 10  # 사람이 읽을 무작위 표본 수
INSTRUCTIONS = (
    "You help a quality engineer who received a defect report. Below are U.S. NHTSA recalls retrieved for the question. "
    "Using ONLY these recalls, write a short answer (at most 6 sentences) that tells the engineer what the precedents say. "
    "Put the recall campaign number in parentheses after each statement, e.g. (12V345000). "
    "In `citations`, list each recall you relied on with `cause_quote`: the manufacturer's stated cause copied exactly "
    "from that recall's cause text above, or an empty string if the recall has no cause text."
)


def load_context() -> tuple[dict, dict, dict, dict]:
    """카드, 캠페인→접수일, 원인 명세, 판독 실패 목록 — 채점과 프롬프트가 같은 데이터를 본다."""
    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    campaigns: dict[str, str] = {}
    for c in cards:
        camp = c["campno"][:6]
        campaigns[camp] = min(campaigns.get(camp, c["received_date"]), c["received_date"])
    raw = (OUT_DIR / "causes.manifest.json").read_bytes()
    check_manifest(raw, json.loads(BASELINE.read_text())["causes_full"]["manifest_sha256"])
    manifest = json.loads(raw)
    causes = {
        c["campaign"]: {**c, "text_basis": manifest.get("text_basis")}
        for c in read_jsonl(OUT_DIR / "causes.jsonl")
    }
    return (
        {c["campno"]: c for c in cards},
        campaigns,
        causes,
        dict(manifest.get("failed_kinds") or {}),
    )


def cause_text(card: dict, causes: dict, unreadable: dict) -> str | None:
    from server.rag.causes import cause_573

    return cause_573(card, causes, unreadable).get("text")


def context_block(top: list[str], by_campno: dict, causes: dict, unreadable: dict) -> str:
    parts = []
    for cid in top:
        c = by_campno[cid]
        cause = cause_text(c, causes, unreadable)
        parts.append(
            f"[{cid}] {c['maker']} · received {c['received_date']}\n"
            f"defect: {c['defect']}\nconsequence: {c['consequence']}\nremedy: {c['remedy']}\n"
            f"cause text: {cause if cause else '(none)'}"
        )
    return "\n\n".join(parts)


def ask(model: str, effort: str | None, question: str, context: str) -> dict:
    from openai import OpenAI
    from pydantic import BaseModel

    class Citation(BaseModel):
        campno: str
        cause_quote: str

    class Answer(BaseModel):
        answer: str
        citations: list[Citation]

    t = time.perf_counter()
    try:
        rsp = OpenAI().responses.parse(
            model=model,
            instructions=INSTRUCTIONS,
            input=f"Question:\n{question}\n\nRecalls:\n{context}",
            text_format=Answer,
            **({"reasoning": {"effort": effort}} if effort else {}),
        )
    except Exception as e:  # 한 문항의 실패가 전체를 멈추지 않게 기록만 하고 채점에서 따로 센다
        return {"error": f"{type(e).__name__}: {e}"[:300], "sec": round(time.perf_counter() - t, 2)}
    got = rsp.output_parsed
    return {
        "output": got.model_dump() if got else None,
        "used_model": getattr(rsp, "model", None),
        "in_tok": rsp.usage.input_tokens,
        "out_tok": rsp.usage.output_tokens,
        "sec": round(time.perf_counter() - t, 2),
    }


def sample_questions(n: int) -> list[dict]:
    qs = read_jsonl(OUT_DIR / "eval.jsonl")
    return random.Random(SEED).sample(qs, min(n, len(qs)))


def prepare(n: int) -> tuple[list[dict], list[str], list[list[str]], list[str]]:
    qs = sample_questions(n)
    masked = [mask_ids(q["question"]) for q in qs]
    tops, _ = rrf_tops(masked)
    by_campno, _, causes, unreadable = load_context()
    ctx = [context_block(t, by_campno, causes, unreadable) for t in tops]
    return qs, masked, tops, ctx


def estimate(model: str, ctx: list[str], masked: list[str]) -> None:
    chars = [len(INSTRUCTIONS) + len(c) + len(m) for c, m in zip(ctx, masked, strict=True)]
    tin, tout = (
        sum(chars) // 3,
        len(ctx) * 400,
    )  # 글자÷3 ≈ 토큰(영어·숫자 섞임, 거친 추정), 출력은 답 6문장+인용 10개 가정
    p_in, p_out = PRICE.get(model, (0.0, 0.0))
    print(
        f"호출 {len(ctx)}회 · 입력 약 {tin:,}토큰(최대 호출 약 {max(chars) // 3:,}) + 출력 약 {tout:,}토큰 → "
        f"약 {tin / 1e6 * p_in + tout / 1e6 * p_out:.3f}달러(가정이 거칠다 — 실제는 실행 뒤 토큰 수로 다시 낸다)"
    )


def run(model: str | None, effort: str | None, n: int, out: Path, workers: int, dry: bool) -> None:
    model, effort = model_and_effort(model, effort)
    qs, masked, tops, ctx = prepare(n)
    estimate(model, ctx, masked)
    if dry:
        return
    meta = {
        "model": model,
        "reasoning_effort": effort,
        "n": len(qs),
        "seed": SEED,
        "instructions": INSTRUCTIONS,
        "mask_re": ID_RE.pattern,
        "action_nos": [q["action_no"] for q in qs],
        "inputs": provenance(),
    }
    if out.exists() or out.with_suffix(".meta.json").exists():
        sys.exit(f"{out} 또는 그 .meta.json이 이미 있다 — 새 경로로 실행한다")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    with ThreadPoolExecutor(workers) as ex:
        answers = list(
            ex.map(lambda a: ask(model, effort, a[0], a[1]), zip(masked, ctx, strict=True))
        )
    with out.open("w") as f:
        for q, m, t, a in zip(qs, masked, tops, answers, strict=True):
            f.write(
                json.dumps({"action_no": q["action_no"], "masked_question": m, "given": t, **a})
                + "\n"
            )
    tin = sum(a.get("in_tok", 0) for a in answers)
    tout = sum(a.get("out_tok", 0) for a in answers)
    p_in, p_out = PRICE.get(model, (0, 0))
    print(
        json.dumps(
            {
                "n": len(answers),
                "errors": sum("error" in a for a in answers),
                "in_tok": tin,
                "out_tok": tout,
                "usd_est": round(tin / 1e6 * p_in + tout / 1e6 * p_out, 4),
                "used_models": sorted(
                    {a.get("used_model") or "?" for a in answers if "error" not in a}
                ),
            },
            ensure_ascii=False,
        )
    )


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
CAMP_IN_TEXT = re.compile(r"\b\d{2}[A-Z]\d{3}(?:\d{3})?\b")


def score_rows(
    rows: list[dict], by_campno: dict, campaigns: dict, causes: dict, unreadable: dict
) -> dict:
    c = dict.fromkeys(
        (
            "answered", "errors", "citations", "cites_out_of_given", "cites_not_in_data", "bad_format",
            "quotes", "quotes_checked", "quotes_verbatim", "quotes_no_cause_given",
            "answer_ids", "answer_ids_out_of_given", "answers_with_judgment",
            "sentences", "sentences_without_id",
        ),
        0,
    )  # fmt: skip
    q_any_violation = 0
    for r in rows:
        out = r.get("output")
        if "error" in r or out is None:
            c["errors"] += 1
            continue
        c["answered"] += 1
        given = {g[:6]: g for g in r["given"]}
        bad = False
        for cit in out["citations"]:
            c["citations"] += 1
            cid = norm_campno(cit["campno"])
            if cid is None:
                c["bad_format"] += 1
                bad = True
                continue
            if cid[:6] not in given:
                c["cites_out_of_given"] += 1
                bad = True
                if cid[:6] not in campaigns:
                    c["cites_not_in_data"] += 1
            if not cit["cause_quote"].strip():
                continue
            c["quotes"] += 1
            if cid[:6] not in given:
                continue  # 범위 밖 번호에 붙은 원인은 대조할 원문이 없다 — 위 범위 밖 번호로 이미 센다
            text = cause_text(by_campno[given[cid[:6]]], causes, unreadable)
            if text is None:
                c["quotes_no_cause_given"] += 1
                bad = True
                continue
            c["quotes_checked"] += 1
            ok = squash(cit["cause_quote"]) in squash(text)
            c["quotes_verbatim"] += ok
            bad = bad or not ok
        for m in CAMP_IN_TEXT.findall(out["answer"]):
            c["answer_ids"] += 1
            if m[:6] not in given:
                c["answer_ids_out_of_given"] += 1
                bad = True
        if PRINCIPLE_PATTERN.search(out["answer"]):
            c["answers_with_judgment"] += 1
            bad = True
        for s in SENT_SPLIT.split(out["answer"].strip()):
            if not s:
                continue
            c["sentences"] += 1
            c["sentences_without_id"] += not CAMP_IN_TEXT.search(s)
        q_any_violation += bad
    c["questions_with_violation"] = q_any_violation
    return c


def score(path: Path) -> None:
    rows = read_jsonl(path)
    meta_path = path.with_suffix(".meta.json")
    if not meta_path.exists():
        sys.exit(f"{meta_path}가 없다 — 결과를 만든 입력 판본을 확인할 수 없다")
    meta = json.loads(meta_path.read_text())
    if meta.get("inputs") != provenance():
        sys.exit(f"결과의 입력 판본 {meta.get('inputs')}이 지금 {provenance()}과 다르다")
    if [r["action_no"] for r in rows] != meta["action_nos"]:
        sys.exit("결과 문항이 메타에 적힌 표본과 다르다")
    by_campno, campaigns, causes, unreadable = load_context()
    report = score_rows(rows, by_campno, campaigns, causes, unreadable)
    ok = [r for r in rows if r.get("output")]
    sample = random.Random(SEED).sample(ok, min(HUMAN_READ, len(ok)))
    report["human_read"] = [
        {
            "action_no": r["action_no"],
            "question": r["masked_question"],
            "answer": r["output"]["answer"],
        }
        for r in sample
    ]
    report["inputs"] = meta["inputs"]
    out = path.with_suffix(".score.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "human_read"}, ensure_ascii=False, indent=1
        )
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path)
    p.add_argument("--score", type=Path, help="결과 파일 채점(API 호출 없음)")
    p.add_argument("--model")
    p.add_argument("--reasoning-effort")
    p.add_argument("--n", type=int, default=N_DEFAULT)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--dry-run", action="store_true", help="입력·비용 추정만")
    a = p.parse_args(argv)
    if a.score:
        return score(a.score)
    if not a.out and not a.dry_run:
        sys.exit("--out, --score 또는 --dry-run이 필요하다")
    run(a.model, a.reasoning_effort, a.n, a.out, a.workers, a.dry_run)


if __name__ == "__main__":
    main()

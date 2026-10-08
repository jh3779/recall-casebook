"""P2 엔진 2(원인 문장 옮기기) 소량 시험 — 연구용. LLM이 573 원인 칸에서 원인 문장을 **한 글자도 바꾸지 않고** 고르는지 본다.

사용법: uv run --with openai --env-file .env python -m scripts.defect_precedent.engine2_trial --model gpt-5.4-mini [--n 30]

- 대상: 시험 질문마다 BM25(v0) 1위 리콜을 고르고, 그 리콜에 573 원인 칸(`cause_text`)이 있는 경우만 앞에서부터 n건
  (정답 여부와 무관하게 "검색이 넘겨준 선례"를 쓴다 — 서비스와 같은 흐름).
- LLM은 원인 칸 원문과 결함 설명만 받고, 원인 문장 목록(원문 그대로) 또는 빈 목록을 돌려준다. 판정·요약·추론은 시키지 않는다.
- 검사(AI 없음): 돌려받은 문장이 원인 칸 원문에 **그대로 들어 있는지**(공백 연속만 하나로 보고 대조). 없으면 버린다.
- 결과: 통과·버림·없음 건수, 응답 시간, 토큰 수. 문장이 "원인을 말하는가"는 사람이 확인한다(D 파트) — 결과 파일에 원문과 함께 남긴다.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from scripts.defect_precedent.bm25_baseline import BM25, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR
from scripts.defect_precedent.retrieval_compare import card_text, read_jsonl

INSTRUCTIONS = (
    "You copy text. From the manufacturer's 'Description of the Cause' text, return the sentence(s) that state the cause "
    "of the defect, copied EXACTLY character for character (do not fix typos, do not shorten, do not paraphrase). "
    "Return an empty list if the text does not state a cause (e.g. 'Unknown', 'Not applicable', still under investigation). "
    "Do not judge whether a recall is required and do not add anything that is not in the text."
)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main(argv: list[str] | None = None) -> None:
    from openai import OpenAI
    from pydantic import BaseModel

    class Extraction(BaseModel):
        cause_sentences: list[str]

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model", required=True)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)

    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    questions = read_jsonl(OUT_DIR / "eval.jsonl")
    causes = {
        c["campaign"]: c
        for c in read_jsonl(OUT_DIR / "causes.jsonl")
        if c["cause_status"] == "filled"
    }
    index = BM25([tokenize(card_text(c)) for c in cards])
    picked, seen = [], set()
    for q in questions:
        top = cards[index.top(tokenize(q["question"]), 1)[0]]
        c = causes.get(top["campno"][:6])
        if c and top["campno"] not in seen:
            seen.add(top["campno"])
            picked.append((q, top, c))
        if len(picked) == a.n:
            break
    if len(picked) < a.n:
        sys.exit(f"대상이 {len(picked)}건뿐이다")

    client = OpenAI()
    rows, tokens_in, tokens_out = [], 0, 0
    for q, card, c in picked:
        t = time.perf_counter()
        rsp = client.responses.parse(
            model=a.model,
            instructions=INSTRUCTIONS,
            input=f"Defect description:\n{card['defect']}\n\nDescription of the Cause:\n{c['cause_text']}",
            text_format=Extraction,
        )
        secs = time.perf_counter() - t
        tokens_in += rsp.usage.input_tokens
        tokens_out += rsp.usage.output_tokens
        got = rsp.output_parsed.cause_sentences if rsp.output_parsed else []
        src = norm(c["cause_text"])
        kept = [s for s in got if s.strip() and norm(s) in src]
        rows.append(
            {
                "action_no": q["action_no"],
                "campno": card["campno"],
                "cause_text": c["cause_text"],
                "returned": got,
                "kept": kept,
                "dropped": [s for s in got if s not in kept],
                "sec": round(secs, 2),
            }
        )
    a.out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    n = len(rows)
    summary = {
        "model": a.model,
        "n": n,
        "all_returned_verbatim": sum(1 for r in rows if r["returned"] and not r["dropped"]),
        "some_dropped": sum(1 for r in rows if r["dropped"]),
        "empty": sum(1 for r in rows if not r["returned"]),
        "avg_sec": round(sum(r["sec"] for r in rows) / n, 2),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

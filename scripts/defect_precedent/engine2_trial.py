"""P2 엔진 2(원인 문장 옮기기) 소량 시험 — 연구용. LLM이 573 원인 칸에서 원인 문장을 **한 글자도 바꾸지 않고** 고르는지 본다.

사용법: uv run --with openai --env-file .env python -m scripts.defect_precedent.engine2_trial --model gpt-5.4-mini [--n 30] --out <결과.jsonl>
      다시 검사만(API 호출 없음, `<결과>.recheck.jsonl`에 씀): uv run python -m scripts.defect_precedent.engine2_trial --recheck <결과.jsonl>

- 대상: 시험 질문마다 BM25(v0) 1위 리콜을 고르고, 그 리콜에 573 원인 칸(`cause_text`)이 있는 경우만 앞에서부터 n건
  (정답 여부와 무관하게 "검색이 넘겨준 선례"를 쓴다 — 서비스와 같은 흐름).
- LLM은 원인 칸 원문과 결함 설명만 받고, 원인 문장 목록(원문 그대로) 또는 빈 목록을 돌려준다. 판정·요약·추론은 시키지 않는다.
- 검사(AI 없음): 돌려받은 문자열이 원인 칸 원문에 **공백까지 포함해 그대로** 들어 있는지 대조하고(정규화 없음), 통과한 것은
  원문에서 찾은 구간(시작·끝 위치)을 남긴다 — 화면에는 모델 문자열이 아니라 이 원문 구간을 보여 준다. 없으면 버린다.
  5단어 미만의 짧은 조각은 따로 센다(문장이 아니라 단어만 돌려준 경우).
- 결과: 통과·버림·없음 건수, 응답 시간, 토큰 수. 문장이 "원인을 말하는가"는 사람이 확인한다(D 파트) — 결과 파일에 원문과 함께 남긴다.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from scripts.defect_precedent.bm25_baseline import BM25, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR
from scripts.defect_precedent.retrieval_compare import card_text, provenance, read_jsonl

INSTRUCTIONS = (
    "You copy text. From the manufacturer's 'Description of the Cause' text, return the sentence(s) that state the cause "
    "of the defect, copied EXACTLY character for character (do not fix typos, do not shorten, do not paraphrase). "
    "Return an empty list if the text does not state a cause (e.g. 'Unknown', 'Not applicable', still under investigation). "
    "Do not judge whether a recall is required and do not add anything that is not in the text."
)


def check(cause_text: str, got: list[str]) -> dict:
    """정규화 없이 원문에서 그대로 찾는다. 통과하면 원문 구간을 돌려준다."""
    spans, dropped = [], []
    for g in got:
        i = cause_text.find(g) if g else -1
        if i < 0:
            dropped.append(g)
        else:
            spans.append({"start": i, "end": i + len(g), "text": cause_text[i : i + len(g)]})
    return {
        "spans": spans,
        "dropped": dropped,
        "short_fragments": sum(1 for sp in spans if len(sp["text"].split()) < 5),
    }


def summarize(model: str, rows: list[dict]) -> dict:
    n = len(rows)
    whole = sum(
        1
        for r in rows
        if r["spans"]
        and " ".join(sp["text"] for sp in r["spans"]).split() == r["cause_text"].split()
    )
    return {
        "model": model,
        "n": n,
        "exact_all_kept": sum(1 for r in rows if r["returned"] and not r["dropped"]),
        "some_dropped": sum(1 for r in rows if r["dropped"]),
        "empty": sum(1 for r in rows if not r["returned"] and not r.get("parse_failed")),
        "parse_failed": sum(
            1 for r in rows if r.get("parse_failed")
        ),  # 이 칸이 없는 옛 결과는 빈 목록과 구분되지 않는다
        "whole_cause_returned": whole,
        "short_fragments": sum(r["short_fragments"] for r in rows),
        "avg_sec": round(sum(r.get("sec", 0) for r in rows) / n, 2),
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--out", type=Path)
    p.add_argument("--recheck", type=Path, help="저장된 결과를 API 호출 없이 다시 검사")
    a = p.parse_args(argv)
    if a.recheck:
        rows = [
            json.loads(line)
            for line in a.recheck.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for r in rows:
            r.update(check(r["cause_text"], r["returned"]))
        out = a.recheck.with_suffix(".recheck.jsonl")  # 원래 결과는 그대로 둔다
        meta = a.recheck.with_suffix(".meta.json")
        if not meta.exists():  # 어느 판본·모델에서 나온 결과인지 모르면 재검사하지 않는다
            sys.exit(f"{meta.name}이 없다 — 원본 결과의 판본을 알 수 없어 재검사하지 않는다")
        m = json.loads(meta.read_text("utf-8"))
        m["recheck_of"] = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "file": a.recheck.name,
            "sha256": hashlib.sha256(a.recheck.read_bytes()).hexdigest(),
            "check_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        out.with_suffix(".meta.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=1), "utf-8"
        )
        out.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )
        print(json.dumps(summarize(a.recheck.stem, rows), ensure_ascii=False, indent=1))
        return
    if not (a.model and a.out):
        sys.exit("--model과 --out이 필요하다 (또는 --recheck)")
    from openai import OpenAI
    from pydantic import BaseModel

    class Extraction(BaseModel):
        cause_sentences: list[str]

    data = provenance()  # recalls·eval은 build.json과, causes는 명세와 해시가 같아야 진행한다
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
        failed = rsp.output_parsed is None  # 거부·해석 실패 — "원인 없음"(빈 목록)과 따로 센다
        got = [] if failed else rsp.output_parsed.cause_sentences
        rows.append(
            {
                "action_no": q["action_no"],
                "campno": card["campno"],
                "cause_text": c["cause_text"],
                "returned": got,
                "parse_failed": failed,
                **check(c["cause_text"], got),
                "sec": round(secs, 2),
            }
        )
    a.out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    meta = {"data": data, "model": a.model, "n": a.n, "instructions": INSTRUCTIONS}
    a.out.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    summary = {
        **summarize(a.model, rows),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "data": data,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

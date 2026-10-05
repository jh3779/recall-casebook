"""영업·지원 도메인 생성 단계 테스트 — 검색 상위 청크 → gpt-4o-mini 체크리스트 → 코드 검증.

기획v1 5절 ⑤⑥⑦을 FAQ 질문으로 돌려 **구조 준수·근거 검증·판정 표현** 같은 자동 지표만 잰다.
FAQ 질문은 "새 업무를 맡은 사람"의 상황이 아니므로 체크리스트 품질은 판단하지 않는다(합성 질문 세트 뒤에 평가).

유료 API(OpenAI)를 부른다 — 호출 수·비용은 실행 전에 출력하고, 예산($)을 넘으면 중단한다(AGENTS.md 7절).
키는 환경변수 `OPENAI_API_KEY`로만 읽는다(`.env`를 읽지 않는다).

사용법 (색인은 sales_support_poc.py의 `index`로 먼저 만든다):
    uv run python -m scripts.sales_support_llm --limit 30                # 계획만 출력 (호출 없음)
    uv run python -m scripts.sales_support_llm --limit 30 --run          # 표본 30개로 실제 호출
    uv run python -m scripts.sales_support_llm --limit 0 --run --retrieval hybrid  # 전체
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from scripts import sales_support_poc as poc

MODEL = "gpt-4o-mini"
# OpenAI 공식 모델 페이지(gpt-4o-mini) 기준 100만 토큰당 가격($). 실제 청구액은 대시보드로 확인한다.
PRICE_INPUT_PER_M = 0.15
PRICE_OUTPUT_PER_M = 0.60
TOP_K_CHUNKS = 5
MAX_CHUNK_CHARS_IN_PROMPT = 2000
MAX_OUTPUT_TOKENS = 1200
DEFAULT_BUDGET_USD = 1.0
DOMAIN = "sales-support"
# 호출 전 추정(여유 포함): 입력 2,500토큰·출력 600토큰 (청크 평균 731자 × 5 + 지시문)
EST_INPUT_TOKENS = 2500
EST_OUTPUT_TOKENS = 600

# 서비스 원칙 — 판정하지 않는다(AGENTS.md 2절 1항). 후보 항목과 근거만 낸다.
INSTRUCTIONS = (
    "You prepare onboarding checklist candidates for a new employee from numbered excerpts of the "
    "GitLab handbook. Use ONLY the excerpts. "
    "For each candidate give: item (what to do), reason (why, based on the excerpt), "
    "criteria (the condition stated in the excerpt that separates when it matters, or null if the "
    "excerpt states none), check_method (how to confirm it is done, as stated in the excerpt, or null), "
    "chunk_no (the excerpt number), evidence_quote (an exact contiguous quote copied from that excerpt "
    "that supports the item). "
    "Do not decide whether anything applies to the user. Do not invent conditions, deadlines, tools or "
    "names that are not in the excerpt. If the excerpts contain nothing relevant, return an empty list. "
    "Write in English."
)

_ITEM_PROPS = {
    "item": {"type": "string"},
    "reason": {"type": "string"},
    "criteria": {"type": ["string", "null"]},
    "check_method": {"type": ["string", "null"]},
    "chunk_no": {"type": "integer"},
    "evidence_quote": {"type": "string"},
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _ITEM_PROPS,
                "required": list(_ITEM_PROPS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

# 판정으로 읽히는 영어 표현 — 출력에 나오는 횟수만 센다(제거하지 않는다)
VERDICT_WORDING = (
    "applies to you",
    "does not apply",
    "do not apply",
    "not applicable",
    "is applicable",
    "you are eligible",
    "you are not eligible",
)


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * PRICE_INPUT_PER_M / 1e6 + output_tokens * PRICE_OUTPUT_PER_M / 1e6


def build_prompt(question: str, chunks: list[poc.Chunk]) -> str:
    parts = [f"Question: {question}", "", "Excerpts:"]
    for n, c in enumerate(chunks, start=1):
        heading = c.heading_path.replace(">", " > ") or "(intro)"
        parts.append(f"[{n}] {heading}\n{c.chunk_text[:MAX_CHUNK_CHARS_IN_PROMPT]}")
    return "\n\n".join(parts)


def validate_items(
    items: list[dict], shown: list[poc.Chunk]
) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    """모델 항목을 코드로 검증한다 (기획v1 5절 ⑦). 통과 항목, 제거 사유별 개수, 경고 개수를 돌려준다.

    제거: 필수 문자열 비어 있음 / 청크 번호가 범위 밖 / evidence_quote가 그 청크 안에 없음(공백 정리 기준).
    `source`·`domains`·`commit_sha`는 모델이 아니라 검증된 청크에서 코드가 채운다.
    경고(제거하지 않고 센다): criteria·check_method가 evidence_quote 밖 글을 쓴 경우, 판정으로 읽히는 표현.
    """
    valid: list[dict] = []
    removed: dict[str, int] = {}
    flags = {"criteria_outside_quote": 0, "check_method_outside_quote": 0, "verdict_wording": 0}

    def drop(reason: str) -> None:
        removed[reason] = removed.get(reason, 0) + 1

    for it in items:
        if not all(
            isinstance(it.get(k), str) and it[k].strip()
            for k in ("item", "reason", "evidence_quote")
        ):
            drop("empty_field")
            continue
        n = it.get("chunk_no")
        if not isinstance(n, int) or not 1 <= n <= len(shown):
            drop("bad_chunk_no")
            continue
        chunk = shown[n - 1]
        quote = poc.collapse_whitespace(it["evidence_quote"])
        if quote not in poc.collapse_whitespace(chunk.chunk_text):
            drop("quote_not_in_chunk")
            continue
        for key, flag in (
            ("criteria", "criteria_outside_quote"),
            ("check_method", "check_method_outside_quote"),
        ):
            value = it.get(key)
            if value and poc.collapse_whitespace(value) not in quote:
                flags[flag] += 1
        text = " ".join(
            str(it.get(k) or "") for k in ("item", "reason", "criteria", "check_method")
        ).lower()
        if any(w in text for w in VERDICT_WORDING):
            flags["verdict_wording"] += 1
        valid.append(
            {
                **it,
                "source": chunk.section_key,
                "domains": [DOMAIN],
                "commit_sha": chunk.commit_sha,
            }
        )
    return valid, removed, flags


def run_question(client, q: poc.EvalQuestion, shown: list[poc.Chunk]) -> dict:
    """질문 하나를 모델에 보내고 검증 결과·토큰·지연을 한 줄 기록으로 돌려준다. 오류가 나도 중단하지 않는다."""
    rec: dict = {
        "question_id": q.question_id,
        "question": q.question,
        "shown_sections": [c.section_key for c in shown],
        "schema_ok": False,
        "n_raw": 0,
        "n_valid": 0,
        "removed": {},
        "flags": {},
        "gold_cited": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_s": 0.0,
        "error": None,
        "valid_items": [],
    }
    start = time.time()
    try:
        response = client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            input=build_prompt(q.question, shown),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "checklist_candidates",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                }
            },
            temperature=0,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            store=False,
        )
    except Exception as e:  # noqa: BLE001 — 한 질문의 실패가 전체 실행을 멈추지 않게 기록만 한다
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["latency_s"] = time.time() - start
        return rec
    rec["latency_s"] = time.time() - start
    usage = getattr(response, "usage", None)
    rec["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
    rec["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
    try:
        items = json.loads(response.output_text)["items"]
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise ValueError("items가 객체 목록이 아님")
    except (ValueError, KeyError, TypeError):
        return rec
    rec["schema_ok"] = True
    valid, removed, flags = validate_items(items, shown)
    rec.update(
        n_raw=len(items),
        n_valid=len(valid),
        removed=removed,
        flags=flags,
        valid_items=valid,
        gold_cited=any(v["source"] in q.gold_section_keys for v in valid),
    )
    return rec


def run_batch(client, jobs: list[tuple[poc.EvalQuestion, list[poc.Chunk]]], budget_usd: float):
    """질문을 차례로 보낸다. 누적 비용이 예산 이상이 되면 거기서 멈추고 (기록, 중단 여부)를 돌려준다."""
    records: list[dict] = []
    spent = 0.0
    for q, shown in jobs:
        if spent >= budget_usd:
            return records, True
        rec = run_question(client, q, shown)
        spent += cost_usd(rec["input_tokens"], rec["output_tokens"])
        records.append(rec)
    return records, spent >= budget_usd and len(records) < len(jobs)


def summarize(records: list[dict]) -> dict:
    n = len(records)
    ok = [r for r in records if r["schema_ok"]]
    raw = sum(r["n_raw"] for r in ok)
    removed: dict[str, int] = {}
    flags = {"criteria_outside_quote": 0, "check_method_outside_quote": 0, "verdict_wording": 0}
    for r in ok:
        for k, v in r["removed"].items():
            removed[k] = removed.get(k, 0) + v
        for k, v in r["flags"].items():
            flags[k] += v
    valid = sum(r["n_valid"] for r in ok)
    in_tok = sum(r["input_tokens"] for r in records)
    out_tok = sum(r["output_tokens"] for r in records)
    lat = sorted(r["latency_s"] for r in records)
    return {
        "n_questions": n,
        "n_api_errors": sum(r["error"] is not None for r in records),
        "schema_ok_rate": len(ok) / n if n else 0.0,
        "items_raw": raw,
        "items_valid": valid,
        "items_valid_rate": valid / raw if raw else 0.0,
        "removed_by_reason": removed,
        "warnings": flags,
        "questions_with_valid_item_rate": sum(r["n_valid"] > 0 for r in ok) / n if n else 0.0,
        "gold_cited_rate": sum(r["gold_cited"] for r in records) / n if n else 0.0,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": cost_usd(in_tok, out_tok),
        "latency_median_s": lat[len(lat) // 2] if lat else 0.0,
    }


def pick_sample(questions: list[poc.EvalQuestion], limit: int) -> list[poc.EvalQuestion]:
    """처음부터 같은 간격으로 뽑아 실행마다 같은 표본이 되게 한다 (limit 0이면 전체)."""
    if not limit or limit >= len(questions):
        return questions
    step = len(questions) / limit
    return [questions[int(i * step)] for i in range(limit)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--handbook-dir", type=Path, default=poc.HANDBOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=poc.OUT_DIR)
    parser.add_argument("--limit", type=int, default=30, help="표본 질문 수 (0이면 전체)")
    parser.add_argument(
        "--questions",
        type=Path,
        help="질문 JSONL (없으면 FAQ에서 뽑는다, 형식은 sales_support_poc.py 참고)",
    )
    parser.add_argument("--retrieval", choices=["bm25", "vector", "hybrid"], default="hybrid")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET_USD, help="비용 상한($)")
    parser.add_argument(
        "--run", action="store_true", help="실제로 API를 호출한다 (없으면 계획만 출력)"
    )
    args = parser.parse_args()
    if not args.handbook_dir.is_dir():
        sys.exit(f"핸드북 데이터가 없습니다: {args.handbook_dir}")

    chunks, vectors = poc.load_checked_index(args.handbook_dir, args.out_dir)
    keys = {c.section_key for c in chunks}
    if args.questions:
        loaded = poc.load_questions(args.questions)
        missing = [q.question_id for q in loaded if not set(q.gold_section_keys) <= keys]
        if missing:
            sys.exit(
                f"정답 섹션이 색인에 없는 질문이 있습니다 ({len(missing)}개, 예: {missing[:3]})"
            )
    else:
        loaded = [q for q in poc.build_faq(args.handbook_dir) if set(q.gold_section_keys) <= keys]
    questions = pick_sample(loaded, args.limit)
    est = len(questions) * cost_usd(EST_INPUT_TOKENS, EST_OUTPUT_TOKENS)
    print(
        f"계획: 질문 {len(questions)}개 × 검색 {args.retrieval} = 호출 {len(questions)}회, 모델 {MODEL}, "
        f"예상 비용 약 ${est:.3f} (상한 ${args.budget:.2f})"
    )
    if not args.run:
        print("호출하지 않았습니다. 실제로 돌리려면 --run을 붙이세요.")
        return

    import os

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("환경변수 OPENAI_API_KEY가 없습니다. 터미널에서 설정한 뒤 다시 실행하세요.")
    from openai import OpenAI

    ranks = poc.Retriever(chunks, vectors).rank([q.question for q in questions])[args.retrieval]
    jobs = [
        (q, [chunks[i] for i in order[:TOP_K_CHUNKS]])
        for q, order in zip(questions, ranks, strict=True)
    ]
    records, stopped = run_batch(OpenAI(), jobs, args.budget)
    summary = summarize(records)
    summary["stopped_by_budget"] = stopped
    summary["retrieval"] = args.retrieval
    summary["question_set_digest"] = poc.question_set_digest(questions)

    run_dir = args.out_dir / "llm_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = run_dir / f"{stamp}_{args.retrieval}_{len(records)}"
    with base.with_suffix(".jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    base.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"저장: {base}.jsonl / .summary.json (gitignore 대상)")


if __name__ == "__main__":
    main()

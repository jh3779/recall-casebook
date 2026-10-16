"""표본 관찰 — 선례 원문 묶음 초안(8D D2·D4)을 LLM으로 만들어 보고 원문 대조 결과를 센다 (DEC-065, 연구용).

이것은 **평가가 아니다** — 정답이 없고 "초안이 쓸 만한가"는 사람이 읽고 판단한다. 여기서 재는 것은 구조적 사실뿐이다:
LLM이 돌려준 인용 중 원문에 없던 것의 수, 묶음 수, 제목에 판정 표현이 걸린 수, 토큰·시간·비용.
서버(`server/rag/draft.py`)와 같은 프롬프트·호출·대조 코드를 그대로 쓴다 — 서비스 경로를 시험하는 것이다.

사용법(공개 API에서 검색 결과를 받아 오고, LLM 키는 --env-file로만 준다 — 값은 출력하지 않는다):
    uv run --env-file .env python -m scripts.defect_precedent.draft_sample --out <결과.jsonl>
    호출 없이 입력과 호출 수만 보기:  ... draft_sample --dry-run
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from functools import partial

from server.rag import draft

API = "https://lg-cns-rag.vercel.app"
# 입력 질문 — 질문마다 출처가 저장소에 있다(새로 지어 쓰지 않았다): 화면 예시 4개(frontend/src/search/examples.ts),
# 시연 질문(HANDOFF 할 일 58), 검색창 안내 문구(SearchInput.tsx), 시연 대체 질문(HANDOFF 할 일 58)
QUESTIONS = [
    "electric power steering assist loss",
    "engine connecting rod bearing failure",
    "electrical short in the ABS module may cause fire",
    "airbag inflator rupture during deployment",
    "loss of power steering assist electric motor driven steering",
    "brake fluid leaking from front caliper",
    "rearview camera image does not display",
]
# OpenAI 모델 문서(2026-10-12 확인, docs/실험_LLM_Luna비교.md 1절) — 100만 토큰당 달러, 비용 추정에만 쓴다
PRICE = {"gpt-6-luna": (0.10, 0.50)}


def search(question: str, api: str) -> dict:
    req = urllib.request.Request(
        f"{api}/search",
        data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pick_cards(resp: dict, n: int, step: str) -> list[dict]:
    """사용자가 담을 법한 선례 — 전체 순위 위쪽 n건. D4는 원인 원문이 있는 선례만 담는다(화면에서 "원인 원문 있음"으로 보인다)."""
    cards = sorted(resp["customer_precedents"] + resp["precedents"], key=lambda c: c["rank"])
    if step == "d4":
        cards = [c for c in cards if c["cause"]["status"] in ("filled", "stated_unknown")]
    return cards[:n]


def run(out: str, api: str, model: str, effort: str, n_cards: int, dry_run: bool) -> None:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not dry_run and not key:
        sys.exit("OPENAI_API_KEY가 없다 — --env-file로 주거나 --dry-run으로 입력만 본다")
    llm = None if dry_run else partial(draft.call_llm, api_key=key, model=model, effort=effort)
    rows, meta = [], {}
    for q in QUESTIONS:
        resp = search(q, api)
        meta = {"build_id": resp["build_id"], "snapshot_date": resp["snapshot_date"], "api": api}
        for step in draft.STEPS:
            cards = pick_cards(resp, n_cards, step)
            sources = draft.build_sources(step, cards)
            if dry_run:
                instr, text = draft.prompt_for(step, sources)
                rows.append(
                    {
                        "question": q,
                        "step": step,
                        "campnos": [c["campno"] for c in cards],
                        "n_sources": len(sources),
                        "chars": len(instr) + len(text),
                    }
                )
                continue
            out_d, used = draft.generate(step, cards, llm)
            rows.append(
                {
                    "question": q,
                    "step": step,
                    "campnos": [c["campno"] for c in cards],
                    "n_sources": len(sources),
                    "draft": out_d,
                    "raw_titles": [g["title"] for g in json.loads(used.text)["groups"]]
                    if used
                    else [],
                    "input_tokens": used.input_tokens if used else 0,
                    "output_tokens": used.output_tokens if used else 0,
                    "seconds": round(used.seconds, 2) if used else 0,
                }
            )
            time.sleep(0.5)
    summary(rows, model, dry_run)
    if not dry_run:
        with open(out, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "meta": {
                            **meta,
                            "model": model,
                            "effort": effort,
                            "n_cards": n_cards,
                            "questions": QUESTIONS,
                        }
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"결과: {out}")


def summary(rows: list[dict], model: str, dry_run: bool) -> None:
    calls = [r for r in rows if r["n_sources"]]
    print(
        f"질문 {len(QUESTIONS)}개 × 단계 {len(draft.STEPS)} = 행 {len(rows)}, 호출할 행(원문이 있는 것) {len(calls)}"
    )
    if dry_run:
        for r in rows:
            print(
                f"  {r['step']} · 원문 {r['n_sources']}개 · 입력 약 {r['chars']}자 · {r['question'][:50]}"
            )
        tokens = sum(r["chars"] for r in calls) // 3  # 글자 ÷ 3 = 토큰 거친 추정(영어·한국어 섞임)
        pin, pout = PRICE.get(model, (0.0, 0.0))
        print(
            f"입력 토큰 약 {tokens:,} + 출력 최대 {len(calls) * draft.MAX_OUTPUT_TOKENS:,} → 비용 상한 약 {tokens * pin / 1e6 + len(calls) * draft.MAX_OUTPUT_TOKENS * pout / 1e6:.4f}달러(출력은 상한 기준 — 실제는 훨씬 적다)"
        )
        return
    rej, degraded = Counter(), Counter()
    tin = tout = 0
    for r in calls:
        d = r["draft"]
        degraded[d["degraded"]] += 1
        rej.update(d["rejected"])
        tin, tout = tin + r["input_tokens"], tout + r["output_tokens"]
    pin, pout = PRICE.get(model, (0.0, 0.0))
    print(
        f"토큰 입력 {tin:,} · 출력 {tout:,} → 약 {tin * pin / 1e6 + tout * pout / 1e6:.5f}달러 · 후퇴(degraded) {dict(degraded)}"
    )
    print(
        f"버린 것(원문 대조) {dict(rej)} · 공백만 달라 원문 구간으로 되짚은 인용 {sum(r['draft']['relocated'] for r in calls)}건"
    )
    raw = [t for r in calls for t in r["raw_titles"]]
    ok = [t for t in raw if draft.title_ok(t)]
    print(
        f"LLM이 처음 붙인 제목 {len(raw)}개 중 서버 규칙(~적은 선례, 40자, 판정 표현 없음)을 통과한 것 {len(ok)}개"
    )
    for t in raw:
        if not draft.title_ok(t):
            print(f"   (규칙 위반) {t}")
    n_groups = sum(len(r["draft"]["groups"]) for r in calls)
    n_items = sum(len(g["items"]) for r in calls for g in r["draft"]["groups"])
    n_src = sum(r["n_sources"] for r in calls)
    print(f"묶음 {n_groups}개 · 묶인 원문 {n_items}/{n_src}건")
    for r in rows:
        d = r.get("draft")
        if not d:
            continue
        print(
            f"\n[{r['step']}] {r['question']}  (원문 {r['n_sources']}개, 묶음 {len(d['groups'])}개, 묶이지 않음 {len(d['ungrouped'])}개)"
        )
        for g in d["groups"]:
            print(f"   ▸ {g['title']}")
            for it in g["items"]:
                print(f"       {it['campno']} · {it['field']}: {it['quote'][:110]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", default="draft_sample.jsonl")
    p.add_argument("--api", default=API)
    p.add_argument("--model", default=draft.DEFAULT_MODEL)
    p.add_argument("--reasoning-effort", default=draft.DEFAULT_EFFORT, choices=draft.EFFORTS)
    p.add_argument("--n-cards", type=int, default=draft.MAX_CARDS)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    run(a.out, a.api, a.model, a.reasoning_effort, a.n_cards, a.dry_run)

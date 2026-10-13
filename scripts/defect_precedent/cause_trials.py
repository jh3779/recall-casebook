"""P2 원인 표시 후속 시험 두 가지 — 연구용. LLM은 원문에서 문장을 **한 글자도 바꾸지 않고** 고르기만 한다.

사용법:
    # A. 573 원인 칸이 없는 리콜: 카드의 결함 설명(`defect`)에서 원인 문장 고르기
    uv run --with openai --env-file .env python -m scripts.defect_precedent.cause_trials defect [--model gpt-6-luna] [--reasoning-effort none] --n 30 --out <결과.jsonl>
    # B. "원인 미확인" 걸러내기: 원인 칸 무작위 표본에 규칙과 LLM을 같이 돌리고, 사람이 표시할 시트를 만든다
    uv run --with openai --env-file .env python -m scripts.defect_precedent.cause_trials unknown [--model gpt-6-luna] [--reasoning-effort none] --n 150 --out <결과.jsonl> --sheet <표시용.csv>
    # B 채점: 사람이 표시한 시트로 정확도를 잰다 (API 호출 없음)
    uv run python -m scripts.defect_precedent.cause_trials score --sheet <표시한.csv> <결과.jsonl> [<결과.jsonl> ...]
    # B 규칙만 채점(DEC-056 — 모델 결과 없이 시트 원문에 지금의 UNKNOWN_RE를 적용)
    uv run python -m scripts.defect_precedent.cause_trials score-rule --sheet <표시한.csv>

- A 대상: 시험 질문마다 BM25(v0) 1위 리콜 중 573 원인 칸이 **없는**(`filled`가 아닌) 카드를 앞에서부터 n건 — engine2_trial과 같은 흐름.
  결함 설명은 리콜 flat 파일의 제조사 서술이다. 조사 요약(ODI)은 시험 질문의 출처라 쓰지 않는다(누수, AGENTS.md 5-2).
- B 대상: 원인 칸이 `filled`인 573 기록에서 시드 고정 무작위 n건. 규칙(`UNKNOWN_RE`)은 표본을 보기 전에 정했다
  (뒤에 `n/?a`를 `n/a`로 좁힘 — 'NA' 오탐 방지, 전체 8,179건에서 결과 불변).
  LLM이 빈 목록을 돌려주면 "원인 미확인"으로 본다. 정답은 사람이 시트의 `label` 칸에 표시한다
  (stated = 원인을 말함 / unknown = 원인을 모른다·조사 중·해당 없음 / mixed = "근본 원인은 모른다"와 추정 원인을 함께 말함).
  채점은 unknown만 양성으로 보고 mixed는 따로 센다. 시트에는 규칙·모델 결과를 넣지 않는다(눈가림).
  AI가 정답을 표시하지 않는다(AGENTS.md 5-2).
- 검사(AI 없음): rules.check(engine2_trial과 같은 검사) — 정규화 없이 원문에서 그대로 찾은 구간만 남긴다.
"""

import argparse
import csv
import hashlib
import json
import random
import sys
import time
from pathlib import Path

from scripts.defect_precedent.bm25_baseline import BM25, tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR
from scripts.defect_precedent.retrieval_compare import card_text, provenance, read_jsonl
from scripts.defect_precedent.rules import UNKNOWN_RE, check

SEED = 20261008
# 추론 모델(gpt-6-luna 등)의 reasoning.effort 허용 값 — OpenAI 모델 문서(developers.openai.com/api/docs/models/gpt-6-luna, 2026-10-12 확인)
REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")
# 기본 모델 — 사용자 지정 2026-10-12(운영 선택, 품질 우위 근거 아님 — docs/실험_LLM_Luna비교.md 4절).
# 정확도는 사람 표시 뒤 채점으로 확인한다.
DEFAULT_MODEL, DEFAULT_EFFORT = "gpt-6-luna", "none"


def model_and_effort(model: str | None, effort: str | None) -> tuple[str, str | None]:
    """기본 모델(--model 없음 또는 같은 이름)이면 추론 강도를 주지 않았을 때 기본 강도로 — `--model gpt-6-luna`만 적어도
    문서 기본값(medium)이 아니라 비교한 조건(none)으로 돈다. 다른 모델은 준 값 그대로, 추론 강도는 줄 때만 보낸다(4o-mini 등)."""
    if model in (None, DEFAULT_MODEL):
        return DEFAULT_MODEL, effort or DEFAULT_EFFORT
    return model, effort


DEFECT_INSTRUCTIONS = (
    "You copy text. From the manufacturer's defect description of a vehicle recall, return the sentence(s) that state "
    "WHY the defect happens (its cause, e.g. a design, material, manufacturing or supplier reason), copied EXACTLY "
    "character for character (do not fix typos or capitalization, do not shorten, do not paraphrase). "
    "Return an empty list if the text only describes what fails or what may happen without stating why. "
    "Do not judge whether a recall is required and do not add anything that is not in the text."
)
UNKNOWN_INSTRUCTIONS = (
    "You copy text. From the manufacturer's 'Description of the Cause' text, return the sentence(s) that state the cause "
    "of the defect, copied EXACTLY character for character (do not fix typos or capitalization, do not shorten, do not "
    "paraphrase). Return an empty list if the text does not state a cause (e.g. 'Unknown', 'Not applicable', the root "
    "cause has not been identified, still under investigation). "
    "Do not judge whether a recall is required and do not add anything that is not in the text."
)
# 원인 미확인 판별 규칙 UNKNOWN_RE(표본을 보기 전에 정함)의 정의는 rules.py — 서버와 함께 쓴다


def rule_unknown(text: str) -> bool:
    return bool(UNKNOWN_RE.search(text))


def llm(
    model: str, instructions: str, text: str, reasoning_effort: str | None = None
) -> tuple[list[str] | None, float, int, int, str | None]:
    from openai import OpenAI
    from pydantic import BaseModel

    class Extraction(BaseModel):
        cause_sentences: list[str]

    t = time.perf_counter()
    rsp = OpenAI().responses.parse(
        model=model,
        instructions=instructions,
        input=text,
        text_format=Extraction,
        **({"reasoning": {"effort": reasoning_effort}} if reasoning_effort else {}),
    )
    got = rsp.output_parsed.cause_sentences if rsp.output_parsed else None  # None = 거부·해석 실패
    used = getattr(
        rsp, "model", None
    )  # 응답이 알려 주는 실제 판본 — 요청 이름(별칭)과 다를 수 있다
    return got, time.perf_counter() - t, rsp.usage.input_tokens, rsp.usage.output_tokens, used


def pick_defect(n: int) -> list[dict]:
    cards = read_jsonl(OUT_DIR / "recalls.jsonl")
    filled = {
        c["campaign"] for c in read_jsonl(OUT_DIR / "causes.jsonl") if c["cause_status"] == "filled"
    }
    index = BM25([tokenize(card_text(c)) for c in cards])
    picked, seen = [], set()
    for q in read_jsonl(OUT_DIR / "eval.jsonl"):
        top = cards[index.top(tokenize(q["question"]), 1)[0]]
        if top["campno"][:6] not in filled and top["defect"].strip() and top["campno"] not in seen:
            seen.add(top["campno"])
            picked.append(
                {"action_no": q["action_no"], "campno": top["campno"], "text": top["defect"]}
            )
        if len(picked) == n:
            return picked
    sys.exit(f"대상이 {len(picked)}건뿐이다")


def pick_unknown(n: int) -> list[dict]:
    rows = [c for c in read_jsonl(OUT_DIR / "causes.jsonl") if c["cause_status"] == "filled"]
    rows.sort(key=lambda c: c["campaign"])
    return [
        {"campaign": c["campaign"], "text": c["cause_text"]}
        for c in random.Random(SEED).sample(rows, n)
    ]


def run(
    mode: str,
    model: str,
    n: int,
    out: Path,
    sheet: Path | None,
    reasoning_effort: str | None = None,
) -> None:
    if sheet and sheet_meta_path(sheet) == out.with_suffix(".meta.json"):
        sys.exit("결과와 시트의 메타 파일 이름이 겹친다 — --out·--sheet 이름을 다르게")
    data = provenance()
    items = pick_defect(n) if mode == "defect" else pick_unknown(n)
    instructions = DEFECT_INSTRUCTIONS if mode == "defect" else UNKNOWN_INSTRUCTIONS
    rows, tin, tout, used_models = [], 0, 0, set()
    for it in items:
        got, sec, i, o, used = llm(model, instructions, it["text"], reasoning_effort)
        tin, tout = tin + i, tout + o
        used_models.add(used)
        failed, got = got is None, got or []
        rows.append(
            {
                **it,
                "returned": got,
                "parse_failed": failed,
                **check(it["text"], got),
                "sec": round(sec, 2),
            }
            | ({"rule_unknown": rule_unknown(it["text"])} if mode == "unknown" else {})
        )
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", "utf-8")
    meta = {
        "data": data,
        "mode": mode,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "response_models": sorted(m for m in used_models if m),
        "n": n,
        "seed": SEED,
        "instructions": instructions,
    }
    out.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), "utf-8"
    )
    if sheet:
        with sheet.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["campaign", "cause_text", "text_sha256", "label", "labeler_id", "note"])
            w.writerows([r["campaign"], r["text"], text_sha(r["text"]), "", "", ""] for r in rows)
        # 시트가 어느 판본·표본에서 나왔는지 — 채점 때 결과 메타를 지금 로컬 파일이 아니라 이 값과 대조한다
        sheet_meta = {
            "causes_sha256": data["causes_sha256"],
            "sample_sha256": sample_sha([(r["campaign"], text_sha(r["text"])) for r in rows]),
            "seed": SEED,
            "n": len(rows),
        }
        sheet_meta_path(sheet).write_text(json.dumps(sheet_meta, indent=1), "utf-8")
    print(
        json.dumps(
            {
                "mode": mode,
                "model": model,
                "n": len(rows),
                "exact_all_kept": sum(1 for r in rows if r["returned"] and not r["dropped"]),
                "some_dropped": sum(1 for r in rows if r["dropped"]),
                "empty": sum(1 for r in rows if not r["returned"] and not r["parse_failed"]),
                "parse_failed": sum(1 for r in rows if r["parse_failed"]),
                "short_fragments": sum(r["short_fragments"] for r in rows),
                "rule_unknown": sum(1 for r in rows if r.get("rule_unknown")),
                "avg_sec": round(sum(r["sec"] for r in rows) / len(rows), 2),
                "tokens_in": tin,
                "tokens_out": tout,
            },
            ensure_ascii=False,
            indent=1,
        )
    )


def confusion(pred: list[bool], gold: list[bool]) -> dict:
    """양성 = "원인 미확인". precision·recall은 미확인을 걸러내는 쪽 기준."""
    tp = sum(p and g for p, g in zip(pred, gold, strict=True))
    fp = sum(p and not g for p, g in zip(pred, gold, strict=True))
    fn = sum(g and not p for p, g in zip(pred, gold, strict=True))
    return {
        "n": len(gold),
        "accuracy": round(sum(p == g for p, g in zip(pred, gold, strict=True)) / len(gold), 3),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
    }


def score_rows(rows: list[dict], labels: dict[str, str]) -> dict:
    """양성 = 사람이 unknown으로 표시. LLM 예측 = 실제로 빈 목록을 돌려준 것(글자 대조에서 버려진 것·해석 실패는 따로 셈).
    규칙은 "원문에 미확인 표현이 있음" 표시용이라 unknown+mixed를 양성으로 본 변형도 함께 낸다."""
    gold = [labels[r["campaign"]] == "unknown" for r in rows]
    gold_any = [labels[r["campaign"]] in ("unknown", "mixed") for r in rows]
    ok = [not r.get("parse_failed") for r in rows]
    return {
        "llm_empty": confusion(
            [not r["returned"] for r, k in zip(rows, ok, strict=True) if k],
            [g for g, k in zip(gold, ok, strict=True) if k],
        ),
        "parse_failed": sum(1 for k in ok if not k),
        "returned_but_all_dropped": sum(1 for r in rows if r["returned"] and not r["spans"]),
        "llm_empty_vs_unknown_or_mixed": confusion(
            [not r["returned"] for r, k in zip(rows, ok, strict=True) if k],
            [g for g, k in zip(gold_any, ok, strict=True) if k],
        ),
        "rule": confusion([r["rule_unknown"] for r in rows], gold),
        "rule_vs_unknown_or_mixed": confusion([r["rule_unknown"] for r in rows], gold_any),
    }


def sheet_meta_path(sheet: Path) -> Path:
    """`x.csv` → `x.csv.meta.json` — 결과 메타(`x.meta.json`)와 이름이 겹치지 않게."""
    return sheet.with_name(sheet.name + ".meta.json")


def sample_sha(pairs: list[tuple[str, str]]) -> str:
    return hashlib.sha256("\n".join(f"{c}:{h}" for c, h in pairs).encode()).hexdigest()[:16]


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def read_sheet(sheet: Path) -> tuple[list[dict], dict[str, str], dict]:
    """표시한 시트를 검사해 (행, campaign→label, 시트 메타)를 돌려준다 — score·score_rule이 함께 쓴다."""
    with sheet.open(encoding="utf-8-sig") as f:  # 엑셀이 BOM을 붙여 저장해도 읽는다
        sheet_rows = list(csv.DictReader(f))
    edited = [r["campaign"] for r in sheet_rows if text_sha(r["cause_text"]) != r["text_sha256"]]
    if edited:  # 표시자가 본 원문 셀이 처음 만든 시트와 다르다(스프레드시트가 자르거나 고친 경우)
        sys.exit(f"시트의 cause_text가 text_sha256과 다르다: {edited[:5]}")
    unnamed = [r["campaign"] for r in sheet_rows if not r["labeler_id"].strip()]
    if unnamed:
        sys.exit(f"labeler_id가 빈 행 {len(unnamed)}개 (AGENTS.md 5-2): {unnamed[:5]}")
    labels = {r["campaign"]: r["label"].strip() for r in sheet_rows}
    mpath = sheet_meta_path(sheet)
    if not mpath.exists():
        sys.exit(
            f"{mpath.name}이 없다 — 이 시트가 어느 causes 판본에서 나왔는지 알 수 없어 채점하지 않는다"
        )
    sheet_meta = json.loads(mpath.read_text("utf-8"))
    if (
        sample_sha([(r["campaign"], r["text_sha256"]) for r in sheet_rows])
        != sheet_meta["sample_sha256"]
    ):
        sys.exit(
            "시트의 행·원문 해시가 시트를 만들 때와 다르다 — 표본이 바뀐 시트는 채점하지 않는다"
        )
    bad = {k: v for k, v in labels.items() if v not in ("stated", "unknown", "mixed")}
    if bad:
        sys.exit(f"label이 stated/unknown/mixed가 아닌 행 {len(bad)}개: {list(bad)[:5]}")
    return sheet_rows, labels, sheet_meta


def label_counts(labels: dict[str, str]) -> dict:
    return {"n": len(labels)} | {
        v: sum(x == v for x in labels.values()) for v in ("unknown", "mixed")
    }


def score_rule(sheet: Path) -> None:
    """서비스 규칙만 잰다(DEC-056) — 시트 원문에 지금의 `UNKNOWN_RE`를 적용하고, 모델 결과는 읽지도 계산하지도 않는다."""
    sheet_rows, labels, sheet_meta = read_sheet(sheet)
    pred = [rule_unknown(r["cause_text"]) for r in sheet_rows]
    gold = [labels[r["campaign"]] == "unknown" for r in sheet_rows]
    gold_any = [labels[r["campaign"]] in ("unknown", "mixed") for r in sheet_rows]
    out = label_counts(labels) | {
        "rule": confusion(pred, gold),
        "rule_vs_unknown_or_mixed": confusion(pred, gold_any),
        "verified": sheet_meta,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


def score(sheet: Path, results: list[Path]) -> None:
    """표시한 시트와 결과가 같은 원문·같은 판본인지 확인한 뒤 잰다(서비스 원칙 4)."""
    sheet_rows, labels, sheet_meta = read_sheet(sheet)
    shown = {r["campaign"]: r["text_sha256"] for r in sheet_rows}
    now = sheet_meta[
        "causes_sha256"
    ]  # 시트를 만든 판본 — 로컬 파일이 바뀌어도 그 시트·결과끼리 채점한다
    out = label_counts(labels)
    for path in results:
        rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
        if {r["campaign"] for r in rows} != set(labels):
            sys.exit(f"{path.name}의 표본이 시트와 다르다")
        changed = [r["campaign"] for r in rows if text_sha(r["text"]) != shown[r["campaign"]]]
        if changed:
            sys.exit(f"{path.name}의 원문이 표시한 시트와 다르다: {changed[:5]}")
        meta = json.loads(path.with_suffix(".meta.json").read_text("utf-8"))
        if meta["data"]["causes_sha256"] != now:  # 시트와 다른 판본의 결과
            sys.exit(
                f"{path.name}은 시트와 다른 causes.jsonl 판본에서 나왔다 — 섞인 판본으로 재지 않는다"
            )
        out[path.stem] = score_rows(rows, labels)
    out["verified"] = sheet_meta  # 대조한 판본·표본 해시를 결과에 남긴다
    print(json.dumps(out, ensure_ascii=False, indent=1))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("mode", choices=["defect", "unknown", "score", "score-rule"])
    p.add_argument("results", nargs="*", type=Path)
    p.add_argument("--model", help=f"기본 {DEFAULT_MODEL}(추론 강도 {DEFAULT_EFFORT})")
    p.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        help="추론 모델에만 — 주지 않으면 요청에 넣지 않는다(4o-mini 등)",
    )
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--out", type=Path)
    p.add_argument("--sheet", type=Path)
    return p


def main(argv: list[str] | None = None) -> None:
    a = parser().parse_args(argv)
    if a.mode == "score-rule":
        if not a.sheet or a.results:
            sys.exit(
                "score-rule에는 --sheet만 준다 — 결과 파일을 주면 모델을 채점하게 된다(DEC-056)"
            )
        score_rule(a.sheet)
        return
    if a.mode == "score":
        if not (a.sheet and a.results):
            sys.exit("score에는 --sheet와 결과 파일이 필요하다")
        score(a.sheet, a.results)
        return
    if not a.out:
        sys.exit("--out이 필요하다")
    a.model, a.reasoning_effort = model_and_effort(a.model, a.reasoning_effort)
    run(a.mode, a.model, a.n, a.out, a.sheet, a.reasoning_effort)


if __name__ == "__main__":
    main()

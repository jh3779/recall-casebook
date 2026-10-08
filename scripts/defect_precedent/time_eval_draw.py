"""시점 평가 문항을 무작위로 뽑는다 (이슈 #38, 기획 6절 시점 평가).

사용법:
    uv run python -m scripts.defect_precedent.time_eval_draw --write   # 뽑은 목록을 파일로 쓴다
    uv run python -m scripts.defect_precedent.time_eval_draw --check   # 파일이 지금 규칙·입력과 같은지 확인한다

749문항 중 조사 개시일이 2007년 이후인 문항(개시 문서 ODI Resume가 공개된 구간)에서 예비 5문항 + 본 45문항을 뽑는다.
사람이 고르면 쉬운 문항만 모일 수 있으므로 **시드를 미리 정해** 뽑고, 목록은 정답 표시 전에 커밋한다.

뽑는 방법은 파이썬 버전에 따라 달라지지 않게 해시로 순위를 매긴다: 문항마다 sha256("시드|조사번호")를 구해
작은 순서대로 50개를 잡고, 앞 5개는 예비·뒤 45개는 본 평가로 나눈다. 질문 글이나 정답은 읽지도 쓰지도 않는다.

**대체 규칙**: 개시 문서를 찾지 못한 조사는 건너뛰고 `reserve`(순위 51번째부터 30개)의 앞에서부터 차례로 채운다.
마음에 드는 문항으로 바꿔 넣지 않는다. 건너뛴 조사와 그 이유는 문서 확보 기록에 남긴다.
"""

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL = REPO_ROOT / "data" / "processed" / "defect" / "eval.jsonl"
BASELINE = Path(__file__).resolve().parent / "baseline_2026-10-06_maker-aliases.json"
OUT = Path(__file__).resolve().parent / "time_eval_draw.json"

SEED = 20261008  # 정한 날짜(2026-10-08). 결과를 보고 바꾸지 않는다
CUTOFF = "20070101"  # 이 날 이후 개시한 조사만 (개시 문서를 2007년부터 확인했다)
PILOT, MAIN, RESERVE = 5, 45, 30


def rank(action_no: str, seed: int = SEED) -> str:
    return hashlib.sha256(f"{seed}|{action_no}".encode()).hexdigest()


def draw(questions: list[dict], seed: int = SEED) -> dict:
    """문항 목록에서 예비·본 평가 조사 번호를 뽑는다 (질문 글·정답은 쓰지 않는다)."""
    pool = {q["action_no"]: q["open_date"] for q in questions if q["open_date"] >= CUTOFF}
    if len(pool) < PILOT + MAIN + RESERVE:
        raise ValueError(f"뽑을 수 있는 문항이 {len(pool)}개뿐이다 (필요 {PILOT + MAIN + RESERVE})")
    picked = sorted(pool, key=lambda a: rank(a, seed))[: PILOT + MAIN + RESERVE]
    as_row = lambda a: {"action_no": a, "open_date": pool[a]}  # noqa: E731
    return {
        "seed": seed,
        "cutoff_open_date": CUTOFF,
        "pool_size": len(pool),
        "pool": [
            [a, pool[a]] for a in sorted(pool)
        ],  # 시험지 없이도 같은 규칙으로 다시 뽑아 볼 수 있게 후보를 남긴다
        "pilot": [as_row(a) for a in picked[:PILOT]],
        "main": [as_row(a) for a in picked[PILOT : PILOT + MAIN]],
        "reserve": [as_row(a) for a in picked[PILOT + MAIN :]],
    }


def build() -> dict:
    if not EVAL.exists():
        sys.exit("시험지(eval.jsonl)가 없다 — 먼저 `... nhtsa build`를 실행한다")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["build"]["eval_sha256"]
    got = hashlib.sha256(EVAL.read_bytes()).hexdigest()
    if got != base:
        sys.exit(
            f"eval.jsonl이 기준 파일과 다르다 ({got[:12]}… ≠ {base[:12]}…) — 같은 시험지로만 뽑는다"
        )
    questions = [json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines() if line]
    return {"eval_sha256": got, **draw(questions)}


def main() -> None:
    if sys.argv[1:] not in (["--write"], ["--check"]):
        sys.exit(
            "사용법: uv run python -m scripts.defect_precedent.time_eval_draw {--write|--check}"
        )
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if sys.argv[1:] == ["--check"]:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit(f"{OUT.name}이 지금 규칙·시험지로 뽑은 결과와 다르다")
        print(f"일치: {OUT.name} (예비 {PILOT} + 본 {MAIN}, 대상 {result['pool_size']}문항)")
        return
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(
        f"예비 {PILOT} + 본 {MAIN}문항을 뽑아 {OUT.name}에 썼다 (시드 {SEED}, 대상 {result['pool_size']}문항)"
    )


if __name__ == "__main__":
    main()

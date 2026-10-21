"""P5 사후 층화 분석 — 정답 리콜의 부품 라벨 카드 수(희소성)별로 749문항 Hit@10을 다시 읽는다. 연구용(research).

사용법:
    RETRIEVAL_CACHE=data/processed/defect/retrieval_cache \\
        uv run --with fastembed==0.9.0 python -m scripts.defect_precedent.rare_strata

규칙 (docs/experiments/실험_P5_희소부품층화.md 2절 — 작성자 기록, 독립 검증 불가):
- 희소성 = 정답 리콜의 부품 라벨(`components` 전체 문자열)을 가진 카드 수. 정답이 여럿이면 가장 작은 값,
  한 카드에 라벨이 여럿이면 최솟값. 구간 경계는 `BOUNDS`(분포만 보고 정함).
- 지표 = any@10(정답 중 하나라도 상위 10에 든 비율), 구간별 Wilson 95% 신뢰구간.
- 사후 층화 분석이다 — 튜닝에 쓰지 않고, 대리 평가·시점 평가 점수와 합치지 않는다(AGENTS.md 5-2).
실행 전에 입력 파일(recalls·eval)의 sha256을 기준 파일과 대조해 다르면 멈춘다(AGENTS.md 5-1: 입력이 다르면
"재현"이 아니라 "재평가"). 끝에는 전체 점수를 기준과 대조해 출력하고, 입력 지문·구간 경계·대조 결과를
`result.json`에 기록한다. 같은 폴더에 다시 실행하면 `result.json`을 덮어쓴다.
"""

import collections
import json
import math
import sys
from pathlib import Path

from scripts.defect_precedent import retrieval_compare as rc
from scripts.defect_precedent.bm25_baseline import tokenize
from scripts.defect_precedent.nhtsa import OUT_DIR, sha256_file, verify_build

BOUNDS = (50, 250)  # 드묾 ≤50 / 중간 51~250 / 흔함 >250 — 분포(건수)만 보고 정함
RESULT_DIR = OUT_DIR / "rare_strata_20261021"
BASELINE = Path(__file__).with_name("baseline_2026-10-06_maker-aliases.json")
# 기준 점수(docs/experiments/실험_P2_검색방식비교.md) — 전체 749문항 any@10
EXPECTED_ALL = {
    "BM25·원래": 0.510,
    "RRF·원래": 0.542,
    "BM25·회사이름뺌": 0.483,
    "RRF·회사이름뺌": 0.531,
}
# bge-small-en-v1.5의 모델 지문 — 실험 P4 결과(`embedding_compare_20261019/BAAI_bge-small-en-v1.5.json`)에서 읽은 값.
# 같은 이름의 모델이어도 가중치·fastembed 판본이 바뀌면 지문이 달라져 "재현"으로 통과시키지 않는다.
EXPECTED_MODEL_FINGERPRINT = "b5fe79bd9de4c0f2"
Z95 = 1.96


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson 95% 신뢰구간 — n이 0이면 구간을 정할 수 없다."""
    if n <= 0:
        raise ValueError("n은 1 이상이어야 한다")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)  # 부동소수 오차로 0·1을 넘지 않게


def rarity(question: dict, cards_by_id: dict[str, dict], label_count: collections.Counter) -> int:
    """정답 리콜들의 부품 라벨 카드 수 중 가장 작은 값. 라벨이 있는 정답이 없으면 ValueError."""
    sizes = [
        min(label_count[x] for x in cards_by_id[g]["components"])
        for g in question["gold_campnos"]
        if g in cards_by_id and cards_by_id[g]["components"]
    ]
    if not sizes:
        raise ValueError(f"부품 라벨이 있는 정답 카드가 없다: {question.get('action_no')}")
    return min(sizes)


def stratum_of(size: int, bounds: tuple[int, int] = BOUNDS) -> str:
    lo, hi = bounds
    return (
        f"드묾(≤{lo})" if size <= lo else f"중간({lo + 1}~{hi})" if size <= hi else f"흔함(>{hi})"
    )


def check_inputs(out_dir: Path = OUT_DIR, baseline: Path = BASELINE) -> dict[str, str]:
    """원본 manifest·카드·시험지 지문을 기준 파일과 대조한다 — 다르면 멈춘다(AGENTS.md 5-1).

    원본 manifest 지문은 `build.json`에서 읽는다(`main`이 먼저 `verify_build`로 build.json이 지금 원본 manifest와
    카드·시험지 파일을 가리키는지 확인한다).
    """
    expected = json.loads(baseline.read_text(encoding="utf-8"))["build"]
    build = json.loads((out_dir / "build.json").read_text(encoding="utf-8"))
    got = {
        "raw_manifest_sha256": build["raw_manifest_sha256"],
        "recalls_sha256": sha256_file(out_dir / "recalls.jsonl"),
        "eval_sha256": sha256_file(out_dir / "eval.jsonl"),
    }
    bad = {k: (expected[k][:12], v[:12]) for k, v in got.items() if expected[k] != v}
    if bad:
        sys.exit(
            f"입력 지문이 {baseline.name}과 다르다 — '재현'이 아니라 '재평가'로 보고한다"
            f"(AGENTS.md 5-1). 기준 → 현재: {bad}"
        )
    return got


def main() -> None:
    import numpy as np

    build_info = verify_build()  # 원본 manifest·카드·시험지·회사명 대응표가 build.json과 같은지
    fingerprints = check_inputs()
    cards, questions = rc.load()
    ids = [c["campno"] for c in cards]
    texts = [rc.card_text(c) for c in cards]
    model, vecs, _, info = rc.embed_cards("BAAI/bge-small-en-v1.5", texts)
    print("입력 지문 일치, 캐시 검증:", info["cache_verified"], "fastembed", info["fastembed"])
    model_ok = info["model_fingerprint"] == EXPECTED_MODEL_FINGERPRINT
    if not model_ok:
        print(
            f"❌ 모델 지문이 기준과 다르다: {info['model_fingerprint']} ≠ {EXPECTED_MODEL_FINGERPRINT}"
        )
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)

    def dense(queries: list[str]) -> list[list[str]]:
        qv = np.array(list(model.query_embed(queries)), dtype="float32")
        qv /= np.linalg.norm(qv, axis=1, keepdims=True)
        return [[ids[i] for i in np.argsort(-row)[:100]] for row in qv @ vecs.T]

    docs = [tokenize(t) for t in texts]
    original = [q["question"] for q in questions]
    no_brand = [rc.strip_brands(q) for q in original]
    bm, _ = rc.bm25_rankings(docs, [tokenize(q) for q in original], ids)
    bm_nb, _ = rc.bm25_rankings(docs, [tokenize(q) for q in no_brand], ids)
    dn, dn_nb = dense(original), dense(no_brand)
    runs = {
        "BM25·원래": bm,
        "RRF·원래": [rc.rrf(a, b) for a, b in zip(bm, dn, strict=True)],
        "BM25·회사이름뺌": bm_nb,
        "RRF·회사이름뺌": [rc.rrf(a, b) for a, b in zip(bm_nb, dn_nb, strict=True)],
    }

    by_id = {c["campno"]: c for c in cards}
    label_count = collections.Counter(x for c in cards for x in set(c["components"]))
    rare = [rarity(q, by_id, label_count) for q in questions]
    names = [stratum_of(x) for x in rare]
    out: dict[str, dict] = {}
    for stratum in [
        *dict.fromkeys(sorted(set(names), key=lambda s: ("드묾", "중간", "흔함").index(s[:2]))),
        "전체",
    ]:
        idx = [i for i, name in enumerate(names) if stratum == "전체" or name == stratum]
        row: dict = {"n": len(idx)}
        for run_name, ranking in runs.items():
            k = sum(any(g in ranking[i][:10] for g in questions[i]["gold_campnos"]) for i in idx)
            ci = wilson(k, len(idx))
            row[run_name] = {
                "hit": k,
                "rate": round(k / len(idx), 3),
                "ci": [round(c, 3) for c in ci],
            }
        out[stratum] = row
        print(stratum, row["n"], {k: v["rate"] for k, v in row.items() if k != "n"})

    rarest = [i for i, x in enumerate(rare) if x <= 10]
    for run_name, ranking in runs.items():
        k = sum(any(g in ranking[i][:10] for g in questions[i]["gold_campnos"]) for i in rarest)
        print(f"카드 ≤10장({len(rarest)}문항)", run_name, k)

    matches = {k: out["전체"][k]["rate"] == v for k, v in EXPECTED_ALL.items()}
    matches["모델 지문"] = model_ok
    print(
        "기준 대조(전체 점수·모델 지문):",
        "✅ 일치" if all(matches.values()) else f"❌ 불일치 {matches}",
    )
    rarest_detail = [
        {
            "action_no": questions[i]["action_no"],
            "gold": questions[i]["gold_campnos"],
            "label_cards": rare[i],
            **{
                f"{name}_rank": next(
                    (r + 1 for r, c in enumerate(ranking[i]) if c in questions[i]["gold_campnos"]),
                    None,
                )
                for name, ranking in runs.items()
                if name.endswith("원래")
            },
        }
        for i in rarest
    ]
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "inputs": fingerprints,
        "build_json": {
            k: v for k, v in build_info.items() if k.endswith("_sha256") or k == "snapshot_date"
        },
        "baseline_file": BASELINE.name,
        "snapshot_date": json.loads(BASELINE.read_text(encoding="utf-8"))["build"]["snapshot_date"],
        "model": {
            "name": "BAAI/bge-small-en-v1.5",
            "fastembed": info["fastembed"],
            "model_fingerprint": info["model_fingerprint"],
            "expected_model_fingerprint": EXPECTED_MODEL_FINGERPRINT,
            "cache": info["cache"],
            "cache_verified": info["cache_verified"],
            "cache_sha256": sha256_file(rc.CACHE / info["cache"]),
        },
        "rarest_label_cards_le10": {"n": len(rarest), "detail": rarest_detail},
        "bounds": BOUNDS,
        "expected_all": EXPECTED_ALL,
        "matches_expected": matches,
        "strata": out,
    }
    (RESULT_DIR / "result.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if not all(matches.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()

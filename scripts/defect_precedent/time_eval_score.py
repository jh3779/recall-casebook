"""시점 평가 채점 — 정답 표시 시트로 후보 묶음 한정 Hit@k·하한을 내고 BM25와 B 방식을 비교한다 (DEC-037 ⑦).

사용법:
    # 예비 5문항 두 사람 일치(합격선, docs/시점평가_정답표시_안내.md 4절) — 합의 전 표시(label)로 계산
    uv run python -m scripts.defect_precedent.time_eval_score agreement --expect 5 --sheets <A의 labels_pilot.csv> <C의 labels_pilot.csv>
    # 본 평가 채점 — 나눠 표시한 시트 여러 개를 합친다(같은 후보를 둘이 표시했으면 agreed_label 필요)
    uv run python -m scripts.defect_precedent.time_eval_score score \
        --candidates <candidates_main.json> [<candidates_<대체 회차>.json> ...] --sheets <시트1.csv> [<시트2.csv> ...] [--partial]

규칙(이 도구 작성자가 정답 표시 결과를 보기 전인 2026-10-11에 DEC-037 ⑦·안내서 4·5절을 그대로 옮겨 고정 — 결과를 보고 고치지 않는다):
- 점수에 쓰는 표시 = `agreed_label`이 있으면 그것, 없으면 `label`. 한 후보에 서로 다른 `label`이 둘 이상인데 `agreed_label`이
  없으면 멈춘다(두 사람이 함께 표시한 문항은 합의 결과를 쓴다 — ⑦(a)).
- "정답 있음" = `yes`가 1개 이상. 아니면 "정답 없음" — 사유는 그 문항의 `note`에 "질문 부품 불명"이 있으면 그것, 아니면
  "후보에 선례 없음"(⑦(g)).
- 방식별 Hit@k = `yes` 후보 중 하나라도 그 방식의 순위 k 안(순위는 숨긴 후보 파일 `candidates_<set>.json`). k = 1·3·5·10.
  ① 후보 묶음 한정(분모 = 정답 있는 문항) ② 하한(분모 = 표시한 전체 문항, 정답 없는 문항은 실패). 모두 Wilson 95% 구간.
- 판정은 Hit@10 하나(분모 = 정답 있는 문항): 정확 McNemar(양측) p < 0.05이고 |B만 맞힘 − BM25만 맞힘|/n ≥ 0.03일 때만
  "차이 있음"과 방향, 아니면 "우열 불확실". 짝 부트스트랩(`default_rng(20261008)`, 10,000회, 2.5·97.5 백분위)은 차이 크기
  설명용이고 판정에 쓰지 않는다(⑦(e)).
- 정답 있는 문항이 34개 미만이면 "미측정"(⑤) — 이때는 비교 결과(`outcome`)도 "미측정"으로 내고 차이 방향을 쓰지 않는다. 정답 있는 문항이 34개를 넘어도 표시한 문항을 모두 쓴다(⑦(g)).
- 시트가 숨긴 후보 파일과 같은 묶음인지(문항·후보 번호가 정확히 같은지), 표시 값이 yes/no/unsure인지, 표시한 줄에
  `labeler_id`가 있는지, 같은 문항의 같은 `dup_group`에 다른 표시가 없는지 먼저 확인하고 어긋나면 멈춘다.
- 표시가 빈 후보가 있으면 멈춘다 — `--partial`이면 그 문항을 빼고 중간 결과로 표시한다(최종 보고에 쓰지 않는다).
"""

import argparse
import csv
import hashlib
import json
import math
import sys
from importlib.metadata import version
from pathlib import Path

LABELS = ("yes", "no", "unsure")
KS = (1, 3, 5, 10)
METHODS = ("bm25", "b_rrf")
MIN_ANSWERED = 34
NO_PART = "질문 부품 불명"
BOOT_SEED, BOOT_N = 20261008, 10_000


def read_sheet(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson(hits: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(max(0.0, center - half), 3), round(min(1.0, center + half), 3)


def mcnemar_exact(b: int, c: int) -> float:
    """양측 정확 McNemar — 불일치 b+c개 중 작은 쪽이 나올 이항(0.5) 확률의 두 배(최대 1)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def merge_labels(sheets: list[list[dict]]) -> dict[tuple[str, str], dict]:
    """(문항, 후보) → 한 줄. 여러 시트의 표시를 합친다 — 서로 다른 label은 agreed_label이 있어야 한다."""
    merged: dict[tuple[str, str], dict] = {}
    for rows in sheets:
        for r in rows:
            key = (r["action_no"], r["campno"])
            m = merged.setdefault(
                key,
                {
                    "action_no": r["action_no"],
                    "campno": r["campno"],
                    "dup_group": r["dup_group"],
                    "labels": [],
                    "labelers": set(),
                    "agreed": set(),
                    "notes": [],
                },
            )
            if m["dup_group"] != r["dup_group"]:
                sys.exit(
                    f"{key}: 시트마다 dup_group이 다르다 {m['dup_group']!r} ≠ {r['dup_group']!r}"
                )
            label, agreed = r.get("label", "").strip(), r.get("agreed_label", "").strip()
            for v in (label, agreed):
                if v and v not in LABELS:
                    sys.exit(f"{key}: 표시 값 {v!r}는 yes/no/unsure가 아니다")
            if label:
                if not r.get("labeler_id", "").strip():
                    sys.exit(f"{key}: 표시했는데 labeler_id가 비어 있다")
                m["labels"].append(label)
                m["labelers"].add(r["labeler_id"].strip())
            if agreed:
                m["agreed"].add(agreed)
            if r.get("note", "").strip():
                m["notes"].append(r["note"].strip())
    for key, m in merged.items():
        if len(m["agreed"]) > 1:
            sys.exit(f"{key}: agreed_label이 시트마다 다르다 {sorted(m['agreed'])}")
        if m["agreed"] and len(m["labelers"]) < 2:
            sys.exit(
                f"{key}: agreed_label은 두 사람 이상이 label을 남긴 후보에만 쓴다(표시자 {len(m['labelers'])}명) — 안내서 1절"
            )
        if m["agreed"]:
            m["final"] = next(iter(m["agreed"]))
        elif len(set(m["labels"])) > 1:
            sys.exit(
                f"{key}: 표시가 서로 다르다 {m['labels']} — 함께 표시한 문항은 agreed_label로 합의 결과를 적는다"
            )
        else:
            m["final"] = m["labels"][0] if m["labels"] else ""
    return merged


def check_against_candidates(merged: dict, items: list[dict]) -> None:
    pool = {(it["action_no"], cid) for it in items for cid in it["pool"]}
    if set(merged) != pool:
        missing, extra = pool - set(merged), set(merged) - pool
        sys.exit(
            f"시트와 숨긴 후보 파일의 후보가 다르다 — 시트에 없음 {len(missing)}개 {sorted(missing)[:3]}, "
            f"후보 파일에 없음 {len(extra)}개 {sorted(extra)[:3]}"
        )
    by_group: dict[tuple[str, str], set[str]] = {}
    for (action, _), m in merged.items():
        if m["final"]:
            by_group.setdefault((action, m["dup_group"]), set()).add(m["final"])
    split = [k for k, v in by_group.items() if len(v) > 1]
    if split:
        sys.exit(f"같은 dup_group에 다른 표시가 있다(안내서 3절) {split[:3]}")


def per_question(merged: dict, items: list[dict], partial: bool) -> tuple[list[dict], list[str]]:
    questions, skipped = [], []
    for it in items:
        rows = [m for (a, _), m in merged.items() if a == it["action_no"]]
        if any(not m["final"] for m in rows):
            if not partial:
                sys.exit(
                    f"{it['action_no']}: 표시가 빈 후보가 있다 — 모두 표시한 뒤 채점한다(중간 결과는 --partial)"
                )
            skipped.append(it["action_no"])
            continue
        yes = [m["campno"] for m in rows if m["final"] == "yes"]
        notes = " ".join(n for m in rows for n in m["notes"])
        labelers = set().union(*(m["labelers"] for m in rows)) if rows else set()
        q = {"action_no": it["action_no"], "answered": bool(yes), "labelers": len(labelers)}
        if not yes:
            all_unsure = all(m["final"] == "unsure" for m in rows)
            q["reason"] = NO_PART if all_unsure and NO_PART in notes else "후보에 선례 없음"
        for method in METHODS:
            ranks = [it["pool"][c][method] for c in yes if method in it["pool"][c]]
            q[method] = min(ranks) if ranks else None
        questions.append(q)
    return questions, skipped


def hit(q: dict, method: str, k: int) -> bool:
    return q[method] is not None and q[method] <= k


def summarize(questions: list[dict], partial: bool = False) -> dict:
    answered = [q for q in questions if q["answered"]]
    n_all, n_ans = len(questions), len(answered)
    out: dict = {
        "labeled_questions": n_all,
        "answered": n_ans,
        "no_answer": {
            r: sum(1 for q in questions if q.get("reason") == r)
            for r in (NO_PART, "후보에 선례 없음")
        },
        "status": "측정"
        if n_ans >= MIN_ANSWERED
        else f"미측정(정답 있는 문항 {n_ans} < {MIN_ANSWERED})",
    }
    for method in METHODS:
        out[method] = {}
        for k in KS:
            h = sum(hit(q, method, k) for q in answered)
            out[method][f"hit@{k}"] = {
                "pool": round(h / n_ans, 3) if n_ans else None,
                "pool_wilson95": wilson(h, n_ans),
                "lower_bound": round(h / n_all, 3) if n_all else None,
                "lower_bound_wilson95": wilson(h, n_all),
            }
    b_only = sum(1 for q in answered if hit(q, "b_rrf", 10) and not hit(q, "bm25", 10))
    bm_only = sum(1 for q in answered if hit(q, "bm25", 10) and not hit(q, "b_rrf", 10))
    p = mcnemar_exact(b_only, bm_only)
    diff = (b_only - bm_only) / n_ans if n_ans else 0.0
    if partial:
        outcome = "미측정(중간 결과)"  # 표시가 안 끝난 문항을 뺀 값 — 발췌해도 방향이 보이지 않게
    elif n_ans < MIN_ANSWERED:
        outcome = "미측정"  # 발췌해도 방향이 보이지 않게 — 숫자는 남기되 판정 문구는 내지 않는다
    elif p < 0.05 and abs(diff) >= 0.03:
        outcome = "차이 있음 — " + ("B가 높음" if diff > 0 else "BM25가 높음")
    else:
        outcome = "우열 불확실"
    out["hit@10_comparison"] = {
        "b_only": b_only,
        "bm25_only": bm_only,
        "mcnemar_exact_p": round(p, 4),
        "diff_b_minus_bm25": round(diff, 3),
        "outcome": outcome,
        "bootstrap95_for_description_only": bootstrap(answered),
    }
    # 두 사람 이상이 표시한 문항 — 재확인 문항(안내서 4절)이 실제로 두 사람 표시로 채점됐는지 눈으로 확인한다
    out["multi_labeler_questions"] = [
        q["action_no"] for q in questions if q.get("labelers", 0) >= 2
    ]
    return out


def bootstrap(answered: list[dict]) -> tuple[float, float] | None:
    if not answered:
        return None
    import numpy as np

    d = np.array([int(hit(q, "b_rrf", 10)) - int(hit(q, "bm25", 10)) for q in answered])
    rng = np.random.default_rng(BOOT_SEED)
    means = d[rng.integers(0, len(d), size=(BOOT_N, len(d)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return round(float(lo), 3), round(float(hi), 3)


def agreement(sheet_a: list[dict], sheet_b: list[dict], expect: int) -> dict:
    """예비 합격선(안내서 4절) — 합의 전 표시(label)로 계산. agreed_label은 쓰지 않는다.
    expect = 두 사람이 함께 표시하기로 한 문항 수(예비 5, 재확인 3) — 덜 표시한 시트로 합격이 나오지 않게."""
    a = {(r["action_no"], r["campno"]): r.get("label", "").strip() for r in sheet_a}
    b = {(r["action_no"], r["campno"]): r.get("label", "").strip() for r in sheet_b}
    ids = []
    for name, sheet in (("첫째", sheet_a), ("둘째", sheet_b)):
        found = {r.get("labeler_id", "").strip() for r in sheet}
        if "" in found or len(found) != 1:
            sys.exit(
                f"{name} 시트의 labeler_id가 모든 줄에 한 사람으로 적혀 있지 않다 {sorted(found)} — 한 사람이 한 시트를 모두 표시한다"
            )
        ids.append(found.pop())
    if ids[0] == ids[1]:
        sys.exit(f"두 시트의 labeler_id가 같다({ids[0]}) — 서로 다른 두 사람의 시트여야 한다")
    if set(a) != set(b):
        sys.exit("두 시트의 문항·후보가 다르다 — 같은 예비 시트를 따로 표시한 것이어야 한다")
    if any(v not in LABELS for v in [*a.values(), *b.values()]):
        sys.exit("표시가 비었거나 yes/no/unsure가 아닌 후보가 있다 — 둘 다 모두 표시한 뒤 계산한다")
    actions = sorted({k[0] for k in a})
    if len(actions) != expect:
        sys.exit(
            f"시트의 문항이 {len(actions)}개다 — 함께 표시하기로 한 {expect}개와 다르다(--expect)"
        )
    q_same = [
        any(a[k] == "yes" for k in a if k[0] == act) == any(b[k] == "yes" for k in b if k[0] == act)
        for act in actions
    ]
    focus = [k for k in a if a[k] in ("yes", "unsure") or b[k] in ("yes", "unsure")]
    cand_rate = round(sum(a[k] == b[k] for k in focus) / len(focus), 3) if focus else None
    one_sided_yes = sorted(k for k in a if (a[k] == "yes") != (b[k] == "yes"))
    passed = all(q_same) and (cand_rate is None or cand_rate >= 0.8)
    return {
        "questions": len(actions),
        "question_level_same": sum(q_same),
        "candidate_focus_n": len(focus),
        "candidate_agreement": cand_rate,
        "pass": passed,
        "one_sided_yes_to_resolve": [list(k) for k in one_sided_yes],
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ag = sub.add_parser("agreement", help="예비 5문항 두 사람 일치(합격선)")
    ag.add_argument("--sheets", type=Path, nargs=2, required=True)
    ag.add_argument(
        "--expect", type=int, required=True, help="함께 표시한 문항 수(예비 5, 재확인 3)"
    )
    sc = sub.add_parser("score", help="본 평가 채점")
    sc.add_argument(
        "--candidates",
        type=Path,
        nargs="+",
        required=True,
        help="숨긴 후보 파일 — 대체 회차를 더 표시했으면 그 파일도 함께(문항이 겹치면 멈춘다)",
    )
    sc.add_argument("--sheets", type=Path, nargs="+", required=True)
    sc.add_argument("--partial", action="store_true", help="표시가 빈 문항을 빼고 중간 결과로 낸다")
    a = p.parse_args(argv)

    if a.cmd == "agreement":
        out = agreement(read_sheet(a.sheets[0]), read_sheet(a.sheets[1]), a.expect)
        out["inputs"] = {str(s): sha256_of(s) for s in a.sheets}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    cands = [json.loads(c.read_text(encoding="utf-8")) for c in a.candidates]
    items = [it for cand in cands for it in cand["items"]]
    seen: dict[str, int] = {}
    for it in items:
        seen[it["action_no"]] = seen.get(it["action_no"], 0) + 1
    if dup := sorted(k for k, v in seen.items() if v > 1):
        sys.exit(f"후보 파일들에 같은 문항이 두 번 있다 {dup[:3]} — 회차마다 다른 문항이어야 한다")
    merged = merge_labels([read_sheet(s) for s in a.sheets])
    check_against_candidates(merged, items)
    questions, skipped = per_question(merged, items, a.partial)
    out = summarize(questions, partial=bool(skipped))
    if skipped:
        out["status"] = (
            f"중간 결과(표시 안 끝난 문항 {len(skipped)}개 제외 — 최종 보고에 쓰지 않음)"
        )
        out["skipped"] = skipped
    out["inputs"] = {
        "candidates": [
            {"file": str(c), "sha256": sha256_of(c), "set": cand["set"], "code": cand.get("code")}
            for c, cand in zip(a.candidates, cands, strict=True)
        ],
        "sheets": {str(s): sha256_of(s) for s in a.sheets},
        "numpy": version("numpy"),  # 부트스트랩 난수열은 numpy 판본에 따라 달라질 수 있다
    }
    out["note"] = (
        "후보 묶음(BM25 상위 20 + B 상위 20) 안에서만 잰 근사 시점 평가 — 일반적인 과거 선례 찾기 성능이 아니다(DEC-037)"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

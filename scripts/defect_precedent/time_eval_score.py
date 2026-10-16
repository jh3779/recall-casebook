"""시점 평가 채점 — 정답 표시 시트로 후보 묶음 한정 Hit@k·하한을 내고 BM25와 B 방식을 비교한다 (DEC-037 ⑦).

사용법:
    # 예비 5문항 두 사람 일치(합격선, docs/시점평가_정답표시_안내.md 4절) — 합의 전 표시(label)로 계산
    uv run python -m scripts.defect_precedent.time_eval_score agreement --phase pilot --candidates <candidates_pilot.json> --sheets <A의 labels_pilot.csv> <C의 labels_pilot.csv>
    #   결과를 파일로 남긴다: … agreement … > agreement_pilot.json
    #   합격해도 한 사람만 yes인 후보는 두 시트에 같은 agreed_label과 합의 이유(note)를 적은 뒤 agreement를 다시 낸다
    #   (resolution_complete가 참이어야 score가 받는다 — 일치율은 label로만 계산하므로 다시 내도 pass는 그대로)
    # 예비 미달이면 재확인 3문항(안내서 4절 — 질문 파일 main 앞 3개)만 추린 두 사람의 시트로:
    #   agreement --phase recheck --candidates <candidates_main.json> --sheets … > agreement_recheck.json
    # score는 agreement 결과 파일을 필수로 받아 이중 표시 검사 범위를 스스로 정한다(옵션으로 고르지 않는다):
    #   예비 합격 → 없음 / 예비 미달·재확인 합격 → 재확인 3문항 / 재확인도 미달 → 본 평가 전 문항(안내서 4절 3항)
    # 본 평가 채점 — 나눠 표시한 시트 여러 개를 합친다(같은 후보를 둘이 표시했으면 agreed_label 필요)
    uv run python -m scripts.defect_precedent.time_eval_score score \
        --candidates <candidates_main.json> [<candidates_<대체 회차>.json> ...] --sheets <시트1.csv> [<시트2.csv> ...] \
        --agreement <agreement_pilot.json> [<agreement_recheck.json>] [--partial]
    # DEC-066(2026-10-16): 예비 일치 확인을 하지 않은 회차 — --agreement 대신 사유를 적는다. 재확인 3문항만 두 사람 표시를 검사한다
    uv run python -m scripts.defect_precedent.time_eval_score score \
        --candidates <candidates_main.json> --sheets <시트1.csv> [<시트2.csv> ...] --pilot-agreement-skipped DEC-066

규칙(이 도구 작성자가 정답 표시 결과를 보기 전인 2026-10-11에 DEC-037 ⑦·안내서 4·5절을 그대로 옮겨 고정 — 결과를 보고 고치지 않는다):
- 점수에 쓰는 표시 = `agreed_label`이 있으면 그것, 없으면 `label`. 한 후보에 서로 다른 `label`이 둘 이상인데 `agreed_label`이
  없으면 멈춘다(두 사람이 함께 표시한 문항은 합의 결과를 쓴다 — ⑦(a)).
- "정답 있음" = `yes`가 1개 이상. 아니면 "정답 없음" — 사유는 그 문항의 `note`에 "질문 부품 불명"이 있으면 그것, 아니면
  "후보에 선례 없음"(⑦(g)). 최종 표시가 모두 unsure인데 메모가 없으면 "unsure만(판단 불가)"로 따로 센다(⑦(a)).
- 방식별 Hit@k = `yes` 후보 중 하나라도 그 방식의 순위 k 안(순위는 숨긴 후보 파일 `candidates_<set>.json`). k = 1·3·5·10.
  ① 후보 묶음 한정(분모 = 정답 있는 문항) ② 하한(분모 = 표시한 전체 문항, 정답 없는 문항은 실패). 모두 Wilson 95% 구간.
- 판정은 Hit@10 하나(분모 = 정답 있는 문항): 정확 McNemar(양측) p < 0.05이고 |B만 맞힘 − BM25만 맞힘|/n ≥ 0.03일 때만
  "차이 있음"과 방향, 아니면 "우열 불확실". 짝 부트스트랩(`default_rng(20261008)`, 10,000회, 2.5·97.5 백분위)은 차이 크기
  설명용이고 판정에 쓰지 않는다(⑦(e)).
- 정답 있는 문항이 34개 미만이면 "미측정"(⑤) — 이때는 비교 결과(`outcome`)도 "미측정"으로 내고 차이 방향을 쓰지 않는다. 정답 있는 문항이 34개를 넘어도 표시한 문항을 모두 쓴다(⑦(g)).
- 시트가 숨긴 후보 파일과 같은 묶음인지(문항·후보 번호가 정확히 같은지), 표시 값이 yes/no/unsure인지, 표시한 줄에
  `labeler_id`가 있는지, 같은 문항의 같은 `dup_group`에 다른 표시가 없는지 먼저 확인하고 어긋나면 멈춘다.
- 표시가 빈 후보가 있으면 멈춘다 — `--partial`이면 그 문항을 빼고 중간 결과로 표시한다(최종 보고에 쓰지 않는다).

사후 변경(2026-10-16, DEC-066 — 이슈 #143, 예비 시트 한 장을 받은 뒤의 변경): 위 규칙의 점수 계산(Hit@k·하한·Wilson·
McNemar·부트스트랩·34문항 기준)은 바꾸지 않았다. `score`에 `--pilot-agreement-skipped DEC-066` 입력을 더했다 — 예비 일치
확인(agreement)을 하지 않은 회차에서 이중 표시 검사 범위를 재확인 3문항으로 정하고(`check_rechecked_dec066`), 갈리지 않은
후보는 같은 `label`을 그대로 쓰며(`agreed_label` 요구 완화), 갈린 후보는 두 시트에 같은 합의값과 note "합의: 우지훈 결정"(정확히 일치)을 요구하고, 갈리지 않은 후보의 합의값과 재확인 3문항 밖의 합의값·두 사람 표시는 막으며, 재확인 범위는 고정 3문항(PE12017·PE11022·PE18009)과 후보 파일의 질문 판본에 대조하고, 결과 파일에 "일치율 미측정"과 갈린 후보 수·채점 보고 한계를 남긴다.
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
UNSURE_ONLY = (
    "unsure만(판단 불가)"  # DEC-037 ⑦(a): unsure만 있으면 정답 없음으로 세고 따로 보고한다
)
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
                    "agreed_by": set(),  # 합의값을 적은 표시자 — 이중 표시 문항은 두 사람 모두 적어야 한다
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
                m["agreed_by"].add(r.get("labeler_id", "").strip())
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
        partial_double = sorted(
            lab for lab in labelers if any(lab not in m["labelers"] for m in rows)
        )
        if len(labelers) >= 2 and partial_double:
            # 두 사람이 표시한 문항(재확인)은 각자 모든 후보를 표시해야 한다 — 일부만 겹치면 나머지가 한 사람 표시로 채점된다
            sys.exit(
                f"{it['action_no']}: 두 사람 이상이 표시했는데 {partial_double}가 일부 후보를 표시하지 않았다(안내서 4절)"
            )
        q = {"action_no": it["action_no"], "answered": bool(yes), "labelers": len(labelers)}
        if not yes:
            all_unsure = all(m["final"] == "unsure" for m in rows)
            if all_unsure:
                q["reason"] = NO_PART if NO_PART in notes else UNSURE_ONLY
            else:
                q["reason"] = "후보에 선례 없음"
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
            for r in (NO_PART, UNSURE_ONLY, "후보에 선례 없음")
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


QUESTIONS = Path(__file__).with_name("time_eval_questions.json")
RECHECK_N = 3  # 안내서 4절 3항: 최종 main 목록의 앞 3문항


def phase_actions(phase: str, questions: Path = QUESTIONS) -> set[str]:
    """함께 표시하기로 정해진 문항(안내서 4절) — 예비는 질문 파일의 pilot 전부, 재확인은 main 앞 3개(내용을 보고 고르지 않는다)."""
    q = json.loads(questions.read_text(encoding="utf-8"))
    rows = q["pilot"] if phase == "pilot" else q["main"][:RECHECK_N]
    return {r["action_no"] for r in rows}


def pool_keys(items: list[dict], actions: set[str]) -> set[tuple[str, str]]:
    """숨긴 후보 파일에서 정해진 문항의 (문항, 후보) 목록."""
    return {
        (it["action_no"], cid) for it in items if it["action_no"] in actions for cid in it["pool"]
    }


def check_rechecked(merged: dict, recheck: set[str], flag: str = "agreement 결과") -> None:
    """재확인을 했다면(안내서 4절 3항) 그 문항의 모든 후보에 서로 다른 두 사람의 label과 agreed_label이 있어야 한다 —
    한 사람 시트만 넘기거나 합의값을 빠뜨리면 합의 전 표시로 공식 점수가 계산된다(PR #72 Codex)."""
    rows = {k: m for k, m in merged.items() if k[0] in recheck}
    missing_q = sorted(recheck - {k[0] for k in rows})
    if missing_q:
        sys.exit(f"두 사람이 표시해야 할 문항 {missing_q[:3]}이 시트에 없다({flag})")
    bad = sorted(k for k, m in rows.items() if len(m["labelers"]) < 2 or not m["agreed"])
    if bad:
        sys.exit(
            f"두 사람이 표시해야 할 문항의 후보 {bad[:3]} 등 {len(bad)}개에 두 사람의 label 또는 agreed_label이 없다({flag}, 안내서 4절)"
        )
    # 합의값은 표시한 사람 모두가 자기 시트에 같은 값으로 적어야 한다 — 한 시트에만 있으면 옮기다 바뀐 값이 그대로
    # 공식 점수가 된다(agreement의 합의 해소 기준과 같게, PR #72 Codex 38dd135). 값이 서로 다르면 merge_labels가 이미 멈춘다.
    one_side = sorted(k for k, m in rows.items() if not m["labelers"] <= m["agreed_by"])
    if one_side:
        sys.exit(
            f"두 사람이 표시해야 할 문항의 후보 {one_side[:3]} 등 {len(one_side)}개에 합의값이 한 사람 시트에만 있다 — 두 시트 모두에 같은 agreed_label을 적는다({flag}, 안내서 4절)"
        )
    # 원래 표시가 달랐다면 합의 이유를 note에 남긴다(안내서 4절 3항 — 어떤 근거로 정했는지 되짚게, PR #72 Codex)
    no_reason = sorted(k for k, m in rows.items() if len(set(m["labels"])) > 1 and not m["notes"])
    if no_reason:
        sys.exit(
            f"두 사람의 표시가 달랐던 후보 {no_reason[:3]} 등 {len(no_reason)}개에 합의 이유(note)가 없다(안내서 4절)"
        )


def require_resolved(g: dict, name: str) -> None:
    """합격한 agreement 결과(예비·재확인)는 한 사람만 yes인 후보를 모두 합의로 해소한 뒤에야 본 평가를 나누는 근거가 된다(안내서 4절 2항)."""
    if g.get("resolution_complete") is not True:
        sys.exit(
            f"{name} 결과가 합격했지만 한 사람만 yes로 표시한 후보 {(g.get('unresolved_one_sided_yes') or [])[:3]}가 합의로 해소되지 않았다 — "
            "두 시트 모두에 같은 agreed_label과 합의 이유(note)를 적고 agreement를 다시 낸다(안내서 4절 2항)"
        )


DEC066 = "DEC-066"
DEC066_NOTE = "합의: 우지훈 결정"  # DEC-066 ③ — 갈린 후보의 합의값을 우지훈이 정했다는 표시(이 문구와 정확히 같아야 한다)
DEC066_RECHECK = frozenset({"PE12017", "PE11022", "PE18009"})  # DEC-066 ②가 고정한 재확인 3문항
DEC066_SCOPE = "재확인 3문항(DEC-066 — 예비 일치 확인 생략, 일치율 미측정)"
DEC066_LIMIT = (  # DEC-066 영향 항목의 채점 보고 한계 문구(고정) — {n}은 재확인 3문항에서 두 사람의 label이 갈린 후보 수
    "표시자 간 일치율 미측정 — 예비 시트 한 장(완성본)을 받은 뒤 절차를 바꿨다. 작성자(B)는 그 시트의 값 종류와 같은 "
    "`dup_group` 안 일치 여부만 확인했고(규칙 변경 결정 전), 값별 개수와 어느 후보가 `yes`인지는 보지 않았다. "
    "재확인 3문항의 갈린 후보({n}건)는 검색을 만든 채점자가 정했다"
)


def check_rechecked_dec066(merged: dict, recheck: set[str]) -> int:
    """DEC-066: 재확인 3문항은 두 사람이 모두 표시하고, label이 갈린 후보만 합의값(우지훈 결정)을 두 시트에 같게 적는다 —
    갈리지 않은 후보는 같은 label을 그대로 쓴다(agreed_label 없어도 됨). 갈린 후보 수를 돌려준다."""
    flag = "DEC-066 재확인 3문항"
    rows = {k: m for k, m in merged.items() if k[0] in recheck}
    missing_q = sorted(recheck - {k[0] for k in rows})
    if missing_q:
        sys.exit(f"두 사람이 표시해야 할 문항 {missing_q[:3]}이 시트에 없다({flag})")
    single = sorted(k for k, m in rows.items() if len(m["labelers"]) < 2)
    if single:
        sys.exit(
            f"두 사람이 표시해야 할 문항의 후보 {single[:3]} 등 {len(single)}개에 두 사람의 label이 없다({flag}, 안내서 4절)"
        )
    split = sorted(k for k, m in rows.items() if len(set(m["labels"])) > 1)
    # 갈린 후보에 합의값이 없으면 merge_labels가 이미 멈춘다. 합의값은 두 시트 모두에 같은 값으로 있어야 한다.
    one_side = sorted(k for k in split if not rows[k]["labelers"] <= rows[k]["agreed_by"])
    if one_side:
        sys.exit(
            f"label이 갈린 후보 {one_side[:3]} 등 {len(one_side)}개에 합의값이 한 사람 시트에만 있다 — 두 시트 모두에 같은 agreed_label을 적는다({flag})"
        )
    no_reason = sorted(k for k in split if DEC066_NOTE not in rows[k]["notes"])
    if no_reason:
        sys.exit(
            f'label이 갈린 후보 {no_reason[:3]} 등 {len(no_reason)}개에 합의 이유 note("{DEC066_NOTE}")가 없다({flag})'
        )
    # 합의값은 재확인 3문항의 갈린 후보에만 쓴다(DEC-066 ②③) — 나머지 문항을 둘이 표시해 갈렸는데 한쪽 시트에만 합의값을
    # 적으면 우지훈 결정도 이유 기록도 없이 갈림이 사라진다
    outside = sorted(k for k, m in merged.items() if k[0] not in recheck and m["agreed"])
    if outside:
        sys.exit(
            f"재확인 3문항 밖의 후보 {outside[:3]} 등 {len(outside)}개에 agreed_label이 있다 — 합의값은 재확인 3문항에만 쓴다({flag})"
        )
    # 합의값은 갈린 후보에만 적는다 — 갈리지 않은 후보는 같은 label을 그대로 쓴다(예전 절차처럼 모든 후보에 채운 시트도 거른다)
    needless = sorted(k for k, m in rows.items() if k not in split and m["agreed"])
    if needless:
        sys.exit(
            f"두 사람의 label이 같은 후보 {needless[:3]} 등 {len(needless)}개에 agreed_label이 있다 — 합의값은 갈린 후보에만 적는다({flag})"
        )
    # 재확인 3문항 밖은 한 문항을 한 사람만 표시한다(DEC-066 ②) — 배정이 겹쳐 둘이 표시하면 표시가 같아도 멈춘다
    doubled = sorted(k for k, m in merged.items() if k[0] not in recheck and len(m["labelers"]) > 1)
    if doubled:
        sys.exit(
            f"재확인 3문항 밖의 후보 {doubled[:3]} 등 {len(doubled)}개를 두 사람 이상이 표시했다 — 나머지 문항은 한 사람만 표시한다({flag})"
        )
    return len(split)


def double_label_scope(
    agreements: list[dict],
    items: list[dict],
    questions: Path,
    cands: list[dict],
    cand_shas: set[str],
) -> tuple[str, set[str]]:
    """agreement 결과(예비·재확인)의 phase·pass로 이중 표시 검사 범위를 정한다 — 사람이 옵션을 빠뜨려 한 사람 표시로
    정식 점수가 나오지 않게(PR #72 Codex 2da97c4·7301978). 안내서 4절: 예비 합격 → 없음, 예비 미달 → 재확인 3문항을 두 사람이,
    재확인도 미달 → 본 평가 전 문항을 두 사람이."""
    by_phase: dict[str, list[dict]] = {}
    for g in agreements:
        if g.get("phase") not in ("pilot", "recheck") or not isinstance(g.get("pass"), bool):
            sys.exit(
                "agreement 결과 파일에 phase(pilot/recheck)·pass가 없다 — agreement 출력 그대로 저장한 파일을 넘긴다"
            )
        if (g.get("inputs") or {}).get("questions", {}).get("sha256") != sha256_of(questions):
            sys.exit(
                "agreement 결과가 이 질문 파일(--questions)로 만든 것이 아니다 — 같은 질문 파일로 다시 낸다"
            )
        used = (g.get("inputs") or {}).get("candidates") or {}
        if diff := build_diff(cands[0], used):
            sys.exit(
                f"agreement 결과의 후보 판본이 지금 채점하는 후보와 {diff}가 다르거나 없다 — 같은 데이터·스크립트·모델로 다시 낸다(DEC-037 ⑦(c))"
            )
        if g["phase"] == "recheck" and used.get("sha256") not in cand_shas:
            sys.exit(
                "재확인 agreement 결과가 지금 채점하는 본 평가 후보 파일로 만든 것이 아니다(안내서 4절 3항)"
            )
        by_phase.setdefault(g["phase"], []).append(g)
    if len(by_phase.get("pilot", [])) != 1 or len(by_phase.get("recheck", [])) > 1:
        sys.exit(
            "agreement 결과는 예비(pilot) 하나와, 예비가 미달일 때만 재확인(recheck) 하나를 넘긴다"
        )
    pilot, recheck = by_phase["pilot"][0], (by_phase.get("recheck") or [None])[0]
    if pilot["pass"]:
        require_resolved(pilot, "예비")
        if recheck is not None:
            sys.exit(
                "예비가 합격인데 재확인 결과가 있다 — 어느 절차를 따랐는지 확인한다(안내서 4절)"
            )
        return "없음(예비 합격)", set()
    if recheck is None:
        sys.exit(
            "예비가 미달이다 — 재확인 3문항 agreement 결과(phase recheck)를 함께 넘긴다(안내서 4절 3항)"
        )
    if recheck["pass"]:
        # 재확인도 같은 합격선이라 합의 해소도 같다 — 해소 전에 본 평가를 나누면 서로 다른 기준이 섞인다(PR #72 Codex f755b62)
        require_resolved(recheck, "재확인")
        return "재확인 3문항(예비 미달·재확인 합격)", phase_actions("recheck", questions)
    return "본 평가 전 문항(재확인도 미달)", {it["action_no"] for it in items}


def agreement(
    sheet_a: list[dict],
    sheet_b: list[dict],
    expected: set[str],
    candidates: set[tuple[str, str]] | None = None,
) -> dict:
    """예비 합격선(안내서 4절) — 합의 전 표시(label)로 계산. agreed_label은 쓰지 않는다.
    expected = 함께 표시하기로 정해진 문항 번호(`phase_actions`) — 덜 표시했거나 다른 문항을 고른 시트로 합격이 나오지 않게."""
    for name, sheet in (("첫째", sheet_a), ("둘째", sheet_b)):
        keys = [(r["action_no"], r["campno"]) for r in sheet]
        if len(keys) != len(set(keys)):
            # 덮어쓰면 한 사람의 yes가 조용히 사라져 해소 목록에서 빠진다 — score(merge_labels)처럼 멈춘다
            sys.exit(
                f"{name} 시트에 같은 (문항, 후보) 줄이 두 번 있다 — 한 후보는 한 줄로 표시한다"
            )
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
    if set(actions) != expected:
        sys.exit(
            f"시트의 문항 {actions}이 정해진 문항 {sorted(expected)}과 다르다(--phase, 안내서 4절)"
        )
    if candidates is not None and set(a) != candidates:
        # 두 시트에서 같은 줄이 함께 빠지면(스프레드시트 필터 등) 그 후보의 불일치가 분모에서 사라진다(PR #72 Codex)
        missing, extra = candidates - set(a), set(a) - candidates
        sys.exit(
            f"시트의 후보가 숨긴 후보 파일과 다르다 — 빠짐 {len(missing)}개 {sorted(missing)[:3]}, 남음 {len(extra)}개 {sorted(extra)[:3]}"
        )
    q_same = [
        any(a[k] == "yes" for k in a if k[0] == act) == any(b[k] == "yes" for k in b if k[0] == act)
        for act in actions
    ]
    focus = [k for k in a if a[k] in ("yes", "unsure") or b[k] in ("yes", "unsure")]
    cand_rate = round(sum(a[k] == b[k] for k in focus) / len(focus), 3) if focus else None
    one_sided_yes = sorted(k for k in a if (a[k] == "yes") != (b[k] == "yes"))
    passed = all(q_same) and (cand_rate is None or cand_rate >= 0.8)
    # 합격해도 한 사람만 yes인 후보는 합의로 해소한 뒤 본 평가를 나눈다(안내서 4절 2항) — 두 시트 모두에 같은 agreed_label
    # (yes/no/unsure)이 있고 합의 이유(note)가 어느 시트에든 있어야 해소. 한 시트에만 적은 합의값은 두 사람이 함께 본
    # 근거가 아니라서 받지 않는다(PR #72 리뷰 f755b62). 일치율 계산에는 쓰지 않는다(위 label만).
    agreed_a = {(r["action_no"], r["campno"]): r.get("agreed_label", "").strip() for r in sheet_a}
    agreed_b = {(r["action_no"], r["campno"]): r.get("agreed_label", "").strip() for r in sheet_b}
    noted = {
        (r["action_no"], r["campno"]) for r in [*sheet_a, *sheet_b] if r.get("note", "").strip()
    }
    unresolved = [
        list(k)
        for k in one_sided_yes
        if agreed_a[k] not in LABELS or agreed_a[k] != agreed_b[k] or k not in noted
    ]
    return {
        "questions": len(actions),
        "question_level_same": sum(q_same),
        "candidate_focus_n": len(focus),
        "candidate_agreement": cand_rate,
        "pass": passed,
        "one_sided_yes_to_resolve": [list(k) for k in one_sided_yes],
        "unresolved_one_sided_yes": unresolved,
        "resolution_complete": not unresolved,
    }


# 후보 파일을 합칠 때 같아야 하는 것(DEC-037 ⑦(c) — 같은 데이터·같은 스크립트·같은 모델). 질문 파일 해시는 대체 회차가
# 질문 파일을 갱신해 만들어지므로(⑦(c)) 회차마다 다른 것이 정상이라 비교하지 않는다. 커밋 해시도 squash 병합 뒤 달라질 수 있어 빼고
# 스크립트 내용 해시로 본다.
SAME_BUILD_KEYS = ("data", "model", "top")
# 임베딩은 판본·모델 지문만 본다 — cache·cache_verified는 캐시 파일이 있었는지라 같은 계산이어도 회차마다 다를 수 있다
EMBEDDING_KEYS = ("fastembed", "model_fingerprint")


def build_diff(first: dict, c: dict) -> list[str]:
    """두 후보 파일(또는 agreement 결과에 적힌 후보 판본)이 같은 데이터·스크립트·모델인지 — 다르거나 없는 항목 목록."""
    diff = [k for k in SAME_BUILD_KEYS if k not in first or first.get(k) != c.get(k)]
    diff += [
        f"embedding.{k}"
        for k in EMBEDDING_KEYS
        if (first.get("embedding") or {}).get(k) is None
        or (first.get("embedding") or {}).get(k) != (c.get("embedding") or {}).get(k)
    ]
    script = (first.get("code") or {}).get("script_sha256")
    if script is None or script != (c.get("code") or {}).get("script_sha256"):
        diff.append("code.script_sha256")
    return diff


def check_same_build(cands: list[dict], partial: bool = False) -> None:
    dirty = [c.get("set") for c in cands if (c.get("code") or {}).get("dirty")]
    if dirty and not partial:
        sys.exit(
            f"커밋하지 않은 코드로 만든 후보 파일이다 {dirty} — 정식 채점에 쓰지 않는다(중간 결과는 --partial)"
        )
    if len(cands) < 2:
        return
    first = cands[0]
    for c in cands[1:]:
        if diff := build_diff(first, c):
            sys.exit(
                f"후보 파일 {first.get('set')}·{c.get('set')}의 {diff}가 없거나 다르다 — 같은 데이터·스크립트·모델로 만든 회차만 합친다(DEC-037 ⑦(c))"
            )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ag = sub.add_parser("agreement", help="예비 5문항 두 사람 일치(합격선)")
    ag.add_argument("--sheets", type=Path, nargs=2, required=True)
    ag.add_argument(
        "--phase",
        choices=["pilot", "recheck"],
        required=True,
        help="예비 5문항 / 재확인 3문항(안내서 4절)",
    )
    ag.add_argument("--questions", type=Path, default=QUESTIONS, help="질문 파일(기본: 커밋된 것)")
    ag.add_argument(
        "--candidates",
        type=Path,
        required=True,
        help="그 회차의 숨긴 후보 파일(예비 = candidates_pilot.json, 재확인 = candidates_main.json)",
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
    how = sc.add_mutually_exclusive_group(required=True)
    how.add_argument(
        "--agreement",
        type=Path,
        nargs="+",
        help="agreement 결과 파일 — 예비(pilot), 예비가 미달이면 재확인(recheck)도. 이중 표시 검사 범위를 여기서 정한다",
    )
    how.add_argument(
        "--pilot-agreement-skipped",
        choices=[DEC066],
        help="예비 일치 확인을 하지 않은 회차(DEC-066) — 재확인 3문항만 두 사람 표시를 검사하고 일치율 미측정으로 남긴다",
    )
    sc.add_argument(
        "--questions", type=Path, default=QUESTIONS, help="질문 파일(재확인 문항을 정함)"
    )
    a = p.parse_args(argv)

    if a.cmd == "agreement":
        expected = phase_actions(a.phase, a.questions)
        cand_items = json.loads(a.candidates.read_text(encoding="utf-8"))["items"]
        out = agreement(
            read_sheet(a.sheets[0]),
            read_sheet(a.sheets[1]),
            expected,
            pool_keys(cand_items, expected),
        )
        out["phase"] = a.phase
        cand_meta = json.loads(a.candidates.read_text(encoding="utf-8"))
        # 어느 후보 목록·질문 파일과 대조한 결과인지 되짚을 수 있게(AGENTS.md 2-4, PR #72 Codex)
        out["inputs"] = {
            "sheets": {str(s): sha256_of(s) for s in a.sheets},
            "candidates": {
                "file": str(a.candidates),
                "sha256": sha256_of(a.candidates),
                "set": cand_meta.get("set"),
                "code": cand_meta.get("code"),
                # score가 지금 채점하는 후보와 같은 판본에서 낸 결과인지 대조한다(PR #72 Codex 110cf87)
                **{k: cand_meta.get(k) for k in (*SAME_BUILD_KEYS, "embedding")},
            },
            "questions": {"file": str(a.questions), "sha256": sha256_of(a.questions)},
        }
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    cands = [json.loads(c.read_text(encoding="utf-8")) for c in a.candidates]
    check_same_build(cands, partial=a.partial)
    if any(c["set"] == "pilot" for c in cands):
        sys.exit(
            "예비(pilot) 후보 파일은 점수 분모에 넣지 않는다(DEC-037 ⑦(a)) — 예비 일치는 agreement로 본다"
        )
    items = [it for cand in cands for it in cand["items"]]
    seen: dict[str, int] = {}
    for it in items:
        seen[it["action_no"]] = seen.get(it["action_no"], 0) + 1
    if dup := sorted(k for k, v in seen.items() if v > 1):
        sys.exit(f"후보 파일들에 같은 문항이 두 번 있다 {dup[:3]} — 회차마다 다른 문항이어야 한다")
    merged = merge_labels([read_sheet(s) for s in a.sheets])
    check_against_candidates(merged, items)
    n_split = None
    if a.pilot_agreement_skipped:
        agreements: list[dict] = []
        scope, must_double = DEC066_SCOPE, phase_actions("recheck", a.questions)
        # 재확인 범위는 DEC-066이 고정한 3문항이어야 하고, 질문 파일은 후보를 만든 그 파일이어야 한다(AGENTS.md 2-4)
        if must_double != DEC066_RECHECK:
            sys.exit(
                f"질문 파일 main 앞 3문항 {sorted(must_double)}이 DEC-066 재확인 3문항 {sorted(DEC066_RECHECK)}과 다르다"
            )
        q_sha = sha256_of(a.questions)
        if any(c.get("questions_sha256") != q_sha for c in cands):
            sys.exit(
                "--questions 파일이 후보 파일을 만든 질문 파일(questions_sha256)과 다르다(DEC-066)"
            )
        n_split = check_rechecked_dec066(merged, must_double)
    else:
        agreements = [json.loads(g.read_text(encoding="utf-8")) for g in a.agreement]
        scope, must_double = double_label_scope(
            agreements, items, a.questions, cands, {sha256_of(c) for c in a.candidates}
        )
        if must_double:
            check_rechecked(merged, must_double, f"이중 표시 범위: {scope}")
    questions, skipped = per_question(merged, items, a.partial)
    dirty = [c["set"] for c in cands if (c.get("code") or {}).get("dirty")]
    # 표시가 덜 끝났거나(--partial로 문항 제외) 커밋하지 않은 코드로 만든 후보를 썼으면(--partial일 때만 허용) 중간 결과다 —
    # 빠진 문항이 없어도 dirty 후보면 정식 결과처럼 보이지 않게 방향 문구를 내지 않는다(PR #72 리뷰 cd39286)
    out = summarize(questions, partial=bool(skipped) or bool(dirty))
    if skipped or dirty:
        why = []
        if skipped:
            why.append(f"표시 안 끝난 문항 {len(skipped)}개 제외")
        if dirty:
            why.append(f"커밋하지 않은 코드로 만든 후보 {dirty}")
        out["status"] = f"중간 결과({' · '.join(why)} — 최종 보고에 쓰지 않음)"
        out["skipped"] = skipped
    out["checks"] = {  # 어떤 검사를 거친 결과인지 결과 파일만으로 되짚게(이슈 #77)
        "double_label_scope": scope,
        "agreements": [
            {"file": str(g), "sha256": sha256_of(g), "phase": d["phase"], "pass": d["pass"]}
            for g, d in zip(a.agreement or [], agreements, strict=True)
        ],
        "pilot_agreement": "미측정(DEC-066)"
        if a.pilot_agreement_skipped
        else "agreement 결과로 확인",
        "partial": a.partial,
    }
    if a.pilot_agreement_skipped:
        out["checks"]["recheck_split_candidates"] = n_split
        out["limitations"] = [DEC066_LIMIT.format(n=n_split)]
    out["inputs"] = {
        "candidates": [
            {"file": str(c), "sha256": sha256_of(c), "set": cand["set"], "code": cand.get("code")}
            for c, cand in zip(a.candidates, cands, strict=True)
        ],
        "sheets": {str(s): sha256_of(s) for s in a.sheets},
        "questions": {"file": str(a.questions), "sha256": sha256_of(a.questions)},
        "numpy": version("numpy"),  # 부트스트랩 난수열은 numpy 판본에 따라 달라질 수 있다
    }
    out["note"] = (
        "후보 묶음(BM25 상위 20 + B 상위 20) 안에서만 잰 근사 시점 평가 — 일반적인 과거 선례 찾기 성능이 아니다(DEC-037)"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

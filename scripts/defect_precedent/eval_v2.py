"""평가셋 재설계 도구 — 감사 시트·R2 누출 점검·R1 풀링 시트·지표 함수 (docs/계획_평가셋_재설계.md). 연구용, 서비스 코드가 아니다.

사용법 (환경: EVAL_DATA=<recalls.jsonl·eval.jsonl이 든 폴더>, EVAL_OUT=<시트를 둘 폴더, 커밋하지 않음>):
    uv run python -m scripts.defect_precedent.eval_v2 audit-sheet --n 100 --seed 20261016
    uv run python -m scripts.defect_precedent.eval_v2 audit-score --sheet <표시한 시트>
    uv run python -m scripts.defect_precedent.eval_v2 r2-counts
    RETRIEVAL_CACHE=<벡터 캐시> uv run python -m scripts.defect_precedent.eval_v2 r1-pool --n-queries 40 --seed 20261016

원칙 (평가가 재현율이 높게 나오도록 만들어지지 않게 — 과도학습 방지):
- 질문·후보를 **검색 결과로 고르지 않는다.** 표본은 시드 고정 무작위이고, 고르는 규칙은 질문 글·카드 칸만 쓴다.
- 표시는 사람만 하고(AGENTS.md 5-2) 시스템 이름·순위를 가린다. 시스템 대응표(`pool_key.json`)는 표시자에게 주지 않는다.
- 일부러 틀린 후보(통제 후보)를 섞어 표시가 후한지 확인한다.
- 자명한 기준선(키워드 한 줄)을 같이 재서, 지표가 그것보다 나을 때만 유효로 본다.
- 이 도구는 정답을 만들지 않는다. 시트의 label 칸은 비어 있다.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(os.environ.get("EVAL_DATA", "data/processed/defect_maker_v2"))
OUT = Path(os.environ.get("EVAL_OUT", "data/processed/defect/eval_v2"))
AUDIT_VALUES = {"yes", "no", "unsure"}
REL_VALUES = {"0", "1", "2"}  # 2 = 같은 부품·같은 고장 방식, 1 = 같은 부품·다른 고장, 0 = 다른 부품


# ---------- 지표 (순수 함수) ----------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """비율의 Wilson 95% 구간."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (
        max(0.0, (c - h) / d),
        min(1.0, (c + h) / d),
    )  # 부동소수점 오차로 0~1 밖으로 나가지 않게


def hit_at_k(levels: list[int], k: int, min_level: int = 2) -> bool:
    """순위대로 놓은 관련도(0·1·2)의 상위 k에 min_level 이상이 하나라도 있는가."""
    return any(x >= min_level for x in levels[:k])


def precision_at_k(levels: list[int], k: int, min_level: int = 1) -> float:
    top = levels[:k]
    return sum(x >= min_level for x in top) / len(top) if top else 0.0


def ndcg_at_k(levels: list[int], k: int) -> float:
    def dcg(xs):
        return sum((2**x - 1) / math.log2(i + 2) for i, x in enumerate(xs[:k]))

    ideal = dcg(sorted(levels, reverse=True))
    return dcg(levels) / ideal if ideal else 0.0


def sensitivity_at_specificity(
    pos: list[float], neg: list[float], specificity: float
) -> tuple[float, float]:
    """점수가 높을수록 양성. 음성의 `specificity` 분위수를 임곗값으로 두고 (민감도, 임곗값)을 돌려준다."""
    s = sorted(neg)
    thr = s[min(len(s) - 1, int(math.ceil(specificity * len(s))) - 1)] if s else 0.0
    return (sum(x > thr for x in pos) / len(pos) if pos else 0.0, thr)


def auc(pos: list[float], neg: list[float]) -> float:
    """양성이 음성보다 점수가 높을 확률(동점은 0.5)."""
    if not pos or not neg:
        return 0.5
    ranked = sorted([(x, 1) for x in pos] + [(x, 0) for x in neg])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg = (i + j + 1) / 2  # 1부터 세는 평균 순위
        rank_sum += avg * sum(lab for _, lab in ranked[i:j])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def keyword_control(texts_pos: list[str], texts_neg: list[str], pattern: str) -> dict:
    """키워드 한 줄 기준선 — 결과가 요약문에 새어 있는지 보는 자명한 통제."""
    rx = re.compile(pattern, re.I)
    sp = sum(bool(rx.search(t)) for t in texts_pos)
    sn = sum(bool(rx.search(t)) for t in texts_neg)
    return {
        "pattern": pattern,
        "sensitivity": round(sp / len(texts_pos), 3),
        "specificity": round(1 - sn / len(texts_neg), 3),
        "pos_hits": sp,
        "n_pos": len(texts_pos),
        "neg_hits": sn,
        "n_neg": len(texts_neg),
    }


# ---------- 입출력 ----------


def _norm_date(s: str) -> str:
    return re.sub(r"\D", "", s or "")[:8]


def _read_jsonl(p: Path) -> list[dict]:
    with p.open(encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _write_sheet(path: Path, header: list[str], rows: list[dict], meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    meta["sheet_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    meta["rows"] = len(rows)
    Path(str(path) + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def category(card: dict) -> str:
    return card["components"][0].split(":")[0].strip() if card["components"] else "UNKNOWN"


# ---------- 749문항 감사 시트 ----------

AUDIT_BASE = ("audit_id", "question", "gold_defect", "gold_consequence", "gold_n")
AUDIT_HEADER = [*AUDIT_BASE, "row_sha256", "q_answerable", "gold_matches", "labeler_id", "note"]


def _row_hash(base: dict) -> str:
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def audit_rows(qs: list[dict], by_id: dict[str, dict], n: int, seed: int) -> list[dict]:
    pick = random.Random(seed).sample(range(len(qs)), n)
    rows = []
    for i in pick:
        q, g = qs[i], by_id[qs[i]["gold_campnos"][0]]
        base = {
            "audit_id": hashlib.sha256(f"{seed}:{q['action_no']}".encode()).hexdigest()[:8],
            "question": q["question"],
            "gold_defect": g["defect"],
            "gold_consequence": g["consequence"],
            "gold_n": str(len(q["gold_campnos"])),
        }
        rows.append(
            {
                **base,
                "row_sha256": _row_hash(base),
                "q_answerable": "",
                "gold_matches": "",
                "labeler_id": "",
                "note": "",
            }
        )
    random.Random(seed + 1).shuffle(rows)
    return rows


def cmd_audit_sheet(args) -> None:
    cards = _read_jsonl(DATA / "recalls.jsonl")
    qs = _read_jsonl(DATA / "eval.jsonl")
    rows = audit_rows(qs, {c["campno"]: c for c in cards}, args.n, args.seed)
    meta = {
        "kind": "eval_audit",
        "seed": args.seed,
        "n": args.n,
        "eval_sha256": hashlib.sha256((DATA / "eval.jsonl").read_bytes()).hexdigest(),
        "recalls_sha256": hashlib.sha256((DATA / "recalls.jsonl").read_bytes()).hexdigest(),
        "labels": {
            "q_answerable": "질문 글만으로 어떤 부품·고장인지 가릴 수 있는가 (yes/no/unsure) — 정답 카드를 보기 전에 먼저 표시",
            "gold_matches": "정답 카드(gold_defect)가 질문이 말하는 결함과 같은 부품·고장인가 (yes/no/unsure)",
        },
    }
    out = OUT / "audit_sheet.csv"
    _write_sheet(out, AUDIT_HEADER, rows, meta)
    print(
        f"감사 시트 {len(rows)}줄 → {out} (label 칸은 비어 있다 — 사람이 표시한다, AI는 표시하지 않는다)"
    )


def audit_summary(rows: list[dict]) -> dict:
    """표시한 감사 시트의 요약 — 값 검사 + 비율과 Wilson 구간."""
    bad = [
        r["audit_id"]
        for r in rows
        if r["q_answerable"] not in AUDIT_VALUES or r["gold_matches"] not in AUDIT_VALUES
    ]
    if bad:
        raise ValueError(f"허용 값(yes/no/unsure)이 아니거나 빈 줄: {bad[:5]}")
    n = len(rows)
    out = {"n": n, "labelers": sorted({r["labeler_id"] for r in rows})}
    for col in ("q_answerable", "gold_matches"):
        c = Counter(r[col] for r in rows)
        out[col] = {
            "counts": dict(c),
            "no_share": round(c["no"] / n, 3),
            "no_wilson95": tuple(round(x, 3) for x in wilson(c["no"], n)),
        }
    both = sum(r["q_answerable"] == "yes" and r["gold_matches"] == "yes" for r in rows)
    out["valid_both_yes_share"] = round(both / n, 3)
    out["valid_both_yes_wilson95"] = tuple(round(x, 3) for x in wilson(both, n))
    return out


def cmd_audit_score(args) -> None:
    with open(args.sheet, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:  # 원본 칸이 바뀌지 않았는지
        if _row_hash({k: r[k] for k in AUDIT_BASE}) != r["row_sha256"]:
            sys.exit(f"원본 칸이 바뀌었다: {r['audit_id']}")
    print(json.dumps(audit_summary(rows), ensure_ascii=False, indent=1))


# ---------- R2 데이터·누출 점검 ----------


def cmd_r2_counts(args) -> None:
    from scripts.defect_precedent.nhtsa import INV_COLS, RAW_DIR, read_flat

    inv: dict[str, dict] = {}
    for r in read_flat(RAW_DIR / "FLAT_INV.zip", INV_COLS):
        a = r["ACTION"].strip()
        d = inv.setdefault(
            a,
            {
                "o": _norm_date(r["ODATE"]),
                "c": _norm_date(r["CDATE"]),
                "s": r["SUMMARY"].strip(),
                "linked": False,
            },
        )
        d["linked"] = d["linked"] or bool(r["CAMPNO"].strip())
    pe_ea = {a: d for a, d in inv.items() if re.match(r"(PE|EA)\d", a)}
    out = {"investigations": len(inv), "pe_ea": len(pe_ea), "by_era": {}}
    for name, (lo, hi) in {
        "<2010": (0, 2010),
        "2010-2019": (2010, 2020),
        "2020+": (2020, 3000),
    }.items():
        xs = [d for d in pe_ea.values() if d["o"][:4].isdigit() and lo <= int(d["o"][:4]) < hi]
        out["by_era"][name] = {
            "n": len(xs),
            "linked_to_recall": sum(d["linked"] for d in xs),
            "closed_without_recall": sum((not d["linked"]) and bool(d["c"]) for d in xs),
            "still_open_unlinked": sum((not d["linked"]) and not d["c"] for d in xs),
        }
    use = [
        d
        for d in pe_ea.values()
        if d["c"] and len(d["s"]) >= 100 and "no summary" not in d["s"].lower()
    ]
    pos = [d["s"] for d in use if d["linked"]]
    neg = [d["s"] for d in use if not d["linked"]]
    out["closed_with_summary"] = {"pos": len(pos), "neg": len(neg)}
    out["keyword_control"] = [
        keyword_control(pos, neg, p)
        for p in (
            r"\brecall",
            r"\brecall|campaign|573",
            r"conduct a (safety )?recall|initiated a (safety )?recall|recalled|recalling",
        )
    ]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- R1 풀링 시트 ----------


def pick_queries(cards: list[dict], n: int, seed: int, since: str = "20150101") -> list[dict]:
    """검색 결과를 보지 않고 질문 카드를 고른다: 차량 리콜·최근·글 길이 80~600자, 부품 대분류를 돌아가며(분류당 최대 3개), 시드 고정."""
    ok = [
        c
        for c in cards
        if c["recall_type"] == "V"
        and _norm_date(c["received_date"]) >= since
        and 80 <= len(c["defect"]) <= 600
    ]
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in sorted(ok, key=lambda c: c["campno"]):
        by_cat[category(c)].append(c)
    rng = random.Random(seed)
    for lst in by_cat.values():
        rng.shuffle(lst)
    cats = sorted(by_cat, key=lambda k: (-len(by_cat[k]), k))
    picked, used = [], Counter()
    while len(picked) < n and any(by_cat[k] for k in cats if used[k] < 3):
        for k in cats:
            if len(picked) < n and by_cat[k] and used[k] < 3:
                picked.append(by_cat[k].pop())
                used[k] += 1
    return picked


def build_pool(
    query: dict,
    systems: dict[str, list[str]],
    by_id: dict[str, dict],
    all_ids: list[str],
    seed: int,
    depth: int = 10,
) -> tuple[list[dict], dict, dict]:
    """질문 카드 하나의 풀링 후보: 각 시스템의 (질문보다 먼저 접수·다른 중복 묶음인) 상위 depth + 통제 후보. 시스템 이름은 key에만 둔다."""
    qd = _norm_date(query["received_date"])

    def eligible(cid: str) -> bool:
        c = by_id[cid]
        return (
            cid != query["campno"]
            and _norm_date(c["received_date"]) < qd
            and c["dup_group"] != query["dup_group"]
        )

    cand: dict[str, dict[str, int]] = defaultdict(
        dict
    )  # 후보 → {시스템 이름: 순위(1부터, 통제 후보는 0)}
    for name, ranking in systems.items():
        for rank, cid in enumerate([x for x in ranking if eligible(x)][:depth], start=1):
            cand[cid][name] = rank
    rng = random.Random(f"{seed}:{query['campno']}")
    qc = category(query)
    pool = [i for i in all_ids if eligible(i)]
    same = [i for i in pool if category(by_id[i]) == qc and i not in cand]
    other = [i for i in pool if category(by_id[i]) != qc and i not in cand]
    for cid in rng.sample(same, min(5, len(same))):
        cand[cid]["control_same_category"] = 0
    for cid in rng.sample(other, min(3, len(other))):
        cand[cid]["control_other_category"] = 0
    ids = sorted(cand)
    rng.shuffle(ids)
    rows = [
        {
            "candidate_id": hashlib.sha256(f"{seed}:{query['campno']}:{cid}".encode()).hexdigest()[
                :8
            ],
            "candidate_defect": by_id[cid]["defect"],
            "label": "",
            "labeler_id": "",
            "note": "",
        }
        for cid in ids
    ]
    key = {
        r["candidate_id"]: dict(sorted(cand[cid].items())) for r, cid in zip(rows, ids, strict=True)
    }
    idmap = {
        r["candidate_id"]: cid for r, cid in zip(rows, ids, strict=True)
    }  # 표시자에게 주지 않는다 — 누수 진단용
    return rows, key, idmap


def cohen_kappa(a: list[str], b: list[str]) -> float:
    """두 표시자의 일치도(Cohen kappa). 같은 길이의 값 목록."""
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[v] * cb[v] for v in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def r1_score(labels: dict[tuple[str, str], int], key: dict) -> dict:
    """표시된 풀링 시트를 시스템별로 채점한다. labels[(질문, 후보)] = 0·1·2, 없으면 표시 안 됨.
    통제 후보 검사와 표시된 비율(judged coverage)을 함께 낸다 — 표시가 후하거나 비어 있으면 점수를 믿지 않는다."""
    names = {s for q in key.values() for v in q["candidates"].values() for s in v}
    systems = sorted(s for s in names if not s.startswith("control"))
    out: dict = {"systems": {}, "controls": {}}
    for name, thr, limit in (
        ("control_other_category", 1, 0.05),
        ("control_same_category", 2, 0.15),
    ):
        got = [
            labels.get((qid, cid))
            for qid, q in key.items()
            for cid, v in q["candidates"].items()
            if name in v
        ]
        done = [x for x in got if x is not None]
        out["controls"][
            name
        ] = {  # 다른 분류가 관련(≥1), 같은 분류가 같은 고장(2)으로 표시되면 후한 표시
            "labeled": len(done),
            "of": len(got),
            "generous_rate": round(sum(x >= thr for x in done) / len(done), 3) if done else None,
            "limit": limit,
        }
    for name in systems:
        hits, ndcgs, precs, judged, total, nq = 0, [], [], 0, 0, 0
        for qid, q in key.items():
            ranked = sorted((v[name], cid) for cid, v in q["candidates"].items() if name in v)
            if not ranked:
                continue
            nq += 1
            total += len(ranked)
            levels = [labels.get((qid, cid)) for _, cid in ranked]
            judged += sum(x is not None for x in levels)
            lv = [x or 0 for x in levels]
            hits += hit_at_k(lv, 10)
            ndcgs.append(ndcg_at_k(lv, 10))
            precs.append(precision_at_k(lv, 10))
        out["systems"][name] = {
            "queries": nq,
            "hit@10": round(hits / nq, 3) if nq else None,
            "hit@10_wilson95": tuple(round(x, 3) for x in wilson(hits, nq)),
            "ndcg@10": round(sum(ndcgs) / len(ndcgs), 3) if ndcgs else None,
            "precision@10": round(sum(precs) / len(precs), 3) if precs else None,
            "judged_coverage": round(judged / total, 3) if total else None,
        }
    return out


def merge_labels(sheets: list[list[dict]]) -> tuple[dict[tuple[str, str], int], dict]:
    """표시자별 시트를 합친다. 두 표시자가 다르게 표시한 후보는 채점에서 빼고(의견 불일치) 일치도를 낸다."""
    per = []
    for rows in sheets:
        d = {}
        for r in rows:
            if r["label"] != "":
                if r["label"] not in REL_VALUES:
                    raise ValueError(f"허용 값(0/1/2)이 아님: {r['query_id']}/{r['candidate_id']}")
                d[(r["query_id"], r["candidate_id"])] = int(r["label"])
        per.append(d)
    merged: dict[tuple[str, str], int | None] = {}
    for d in per:
        for k, v in d.items():
            merged[k] = v if merged.get(k, v) == v else None
    disputed = sum(v is None for v in merged.values())
    info: dict = {
        "labelers": len(sheets),
        "labeled": [len(d) for d in per],
        "disputed_excluded": disputed,
    }
    if len(per) == 2:
        both = sorted(set(per[0]) & set(per[1]))
        info["overlap"] = len(both)
        info["kappa"] = (
            round(cohen_kappa([str(per[0][k]) for k in both], [str(per[1][k]) for k in both]), 3)
            if both
            else None
        )
    return {k: v for k, v in merged.items() if v is not None}, info


def cmd_r1_score(args) -> None:
    sheets = []
    for path in args.sheet:
        with open(path, encoding="utf-8-sig", newline="") as f:
            sheets.append(list(csv.DictReader(f)))
    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    labels, info = merge_labels(sheets)
    res = {"labeling": info, **r1_score(labels, key)}
    res["valid_gates"] = {
        "kappa_ok": (info.get("kappa") or 0) >= 0.6 if len(sheets) == 2 else None,
        "controls_ok": all(
            c["generous_rate"] is not None and c["generous_rate"] < c["limit"]
            for c in res["controls"].values()
        ),
        "note": "통제 후보 검사나 kappa(두 명일 때)가 미달이면 점수를 쓰지 않는다 — 평가 설계 5절",
    }
    print(json.dumps(res, ensure_ascii=False, indent=1))


STOP = {
    *"the a an of and or to in on for that this is was were be by with as at from it its has have had which not no are than into".split(),
    *"odi nhtsa investigation opened summary complaints reports vehicles vehicle".split(),
}


def question_flags(qs: list[dict], by_id: dict[str, dict], tokenize) -> dict:
    """749문항의 객관 플래그 — 코드로 센 것이고 사람 표시가 아니다(무효 규모의 대략을 보는 용도, 문항을 거르는 데 쓰지 않는다)."""
    flags: Counter = Counter()
    for q in qs:
        words = [
            w for w in tokenize(q["question"]) if w not in STOP and not w.isdigit() and len(w) > 2
        ]
        g = by_id[q["gold_campnos"][0]]
        gwords = set(tokenize(g["defect"] + " " + g["consequence"] + " " + g["remedy"]))
        short, low, zero = len(q["question"]) < 100, len(words) < 8, not (set(words) & gwords)
        flags["short_lt100"] += short
        flags["low_content_lt8_words"] += low
        flags["zero_content_overlap_with_gold"] += zero
        flags["see_attached"] += "attach" in q["question"].lower()
        flags["any_flag"] += short or low or zero
    n = len(qs)
    return {"n": n, **flags, **{f"{k}_share": round(v / n, 3) for k, v in flags.items()}}


def cmd_question_flags(args) -> None:
    from scripts.defect_precedent.bm25_baseline import tokenize

    cards = _read_jsonl(DATA / "recalls.jsonl")
    res = question_flags(
        _read_jsonl(DATA / "eval.jsonl"), {c["campno"]: c for c in cards}, tokenize
    )
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def lcs_run(a: list[str], b: list[str]) -> int:
    """두 단어 목록의 가장 긴 연속 공통 구간(단어 수) — 베껴 쓴 정도."""
    best = 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, start=1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def paraphrase_metrics(src: str, para: str, tokenize, strip_brands) -> dict:
    """바꿔 쓴 예상 질문의 기계 검사. 하드 실패 = 숫자 포함 · 브랜드 포함 · 6단어 미만/45단어 초과 · 원문과 연속 겹침 7단어 이상."""
    cs = {w for w in tokenize(src) if w not in STOP and not w.isdigit() and len(w) > 2}
    cp = {w for w in tokenize(para) if w not in STOP and not w.isdigit() and len(w) > 2}
    words = len(para.split())
    run = lcs_run(tokenize(src), tokenize(para))
    reasons = []
    if re.search(r"\d", para):
        reasons.append("digit")
    if strip_brands(para) != re.sub(r"\s+", " ", para).strip():
        reasons.append("brand")
    if words < 6 or words > 45:
        reasons.append("length")
    if run >= 7:
        reasons.append("copy_run>=7")
    return {
        "words": words,
        "jaccard": round(len(cs & cp) / len(cs | cp), 3) if cs | cp else 0.0,
        "novel_token_share": round(len(cp - cs) / len(cp), 3) if cp else 0.0,
        "longest_copy_run": run,
        "hard_fail": reasons,
    }


def cmd_paraphrase_input(args) -> None:
    cards = {c["campno"]: c for c in _read_jsonl(DATA / "recalls.jsonl")}
    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    rows = [
        {"query_id": q, "source_text": cards[v["query_campno"]]["defect"]} for q, v in key.items()
    ]
    path = OUT / "expected_in.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["query_id", "source_text"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)}개 → {path} (생성 에이전트에는 이 두 열만 준다 — 후보·정답·검색 결과 없음)")


def cmd_paraphrase_check(args) -> None:
    from scripts.defect_precedent.bm25_baseline import tokenize
    from scripts.defect_precedent.retrieval_compare import strip_brands

    with (OUT / "expected_in.csv").open(encoding="utf-8", newline="") as f:
        src = {r["query_id"]: r["source_text"] for r in csv.DictReader(f)}
    got: dict[str, str] = {}
    for p in args.outputs:
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                got[r["query_id"]] = r["question"].strip()
    rows, fails = [], Counter()
    for qid, s in src.items():
        if qid not in got:
            rows.append({"query_id": qid, "question": "", "hard_fail": "missing"})
            fails["missing"] += 1
            continue
        m = paraphrase_metrics(s, got[qid], tokenize, strip_brands)
        for r in m["hard_fail"]:
            fails[r] += 1
        rows.append(
            {"query_id": qid, "question": got[qid], **m, "hard_fail": ";".join(m["hard_fail"])}
        )
    ok = [r for r in rows if not r["hard_fail"]]
    out = OUT / "expected_check.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summ = {
        "n": len(rows),
        "passed": len(ok),
        "failures": dict(fails),
        "failed_ids": [r["query_id"] for r in rows if r["hard_fail"]],
        "mean_jaccard": round(sum(r["jaccard"] for r in ok) / len(ok), 3) if ok else None,
        "mean_novel_token_share": round(sum(r["novel_token_share"] for r in ok) / len(ok), 3)
        if ok
        else None,
        "mean_longest_copy_run": round(sum(r["longest_copy_run"] for r in ok) / len(ok), 2)
        if ok
        else None,
    }
    print(json.dumps(summ, ensure_ascii=False, indent=1))


def leak_diagnostics(key: dict, by_id: dict[str, dict], idmaps: dict[str, dict], tokenize) -> dict:
    """시스템별 상위 10의 같은 제조사 비율과 복사형 후보(질문 글과 내용 단어 Jaccard ≥ 0.6) 수 — 누수 점검."""
    out: dict = {}
    for sysname in ("bm25", "dense", "rrf"):
        same = tot = copy = 0
        for qid, q in key.items():
            qc = by_id[q["query_campno"]]
            qtok = {
                w
                for w in tokenize(qc["defect"])
                if w not in STOP and not w.isdigit() and len(w) > 2
            }
            for cid, v in q["candidates"].items():
                if sysname not in v:
                    continue
                c = by_id[idmaps[qid][cid]]
                tot += 1
                same += c["maker_group"] == qc["maker_group"] or c["maker"] == qc["maker"]
                ctok = {
                    w
                    for w in tokenize(c["defect"])
                    if w not in STOP and not w.isdigit() and len(w) > 2
                }
                copy += bool(qtok | ctok) and len(qtok & ctok) / len(qtok | ctok) >= 0.6
        out[sysname] = {
            "top10_slots": tot,
            "same_maker_share": round(same / tot, 3) if tot else None,
            "copy_like_share": round(copy / tot, 3) if tot else None,
        }
    return out


def cmd_r1_pool(args) -> None:
    import numpy as np

    from scripts.defect_precedent.bm25_baseline import BM25, tokenize
    from scripts.defect_precedent.retrieval_compare import card_text, embed_cards, rrf

    cards = _read_jsonl(DATA / "recalls.jsonl")
    by_id = {c["campno"]: c for c in cards}
    ids = [c["campno"] for c in cards]
    queries = pick_queries(cards, args.n_queries, args.seed)
    override: dict[str, str] = {}
    if (
        args.queries_file
    ):  # 예상 질문: 검색 질의만 바꾸고 관련도 기준(시트의 query_text)은 원문 결함 글로 둔다
        with open(args.queries_file, encoding="utf-8-sig", newline="") as f:
            override = {
                r["query_id"]: r["question"] for r in csv.DictReader(f) if r["question"].strip()
            }
    model, vecs, _, _ = embed_cards("BAAI/bge-small-en-v1.5", [card_text(c) for c in cards])
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    bm = BM25([tokenize(card_text(c)) for c in cards])
    sheet, keys, qrows, idmaps = [], {}, [], {}
    for qi, q in enumerate(queries):
        qid = f"Q{qi + 1:03d}"
        text = q["defect"]
        if args.queries_file and qid not in override:
            continue  # 하드 실패로 빠진 질문
        search_text = override.get(qid, text)
        b = [ids[i] for i in bm.top(tokenize(search_text), 300)]
        v = np.array(list(model.query_embed([search_text])), dtype="float32")[0]
        v /= np.linalg.norm(v)
        d = [ids[i] for i in np.argsort(-(vecs @ v))[:300]]
        rows, key, idmap = build_pool(
            q, {"bm25": b, "dense": d, "rrf": rrf(b[:100], d[:100])}, by_id, ids, args.seed
        )
        for r in rows:
            sheet.append({"query_id": qid, "query_text": text, **r})
        keys[qid] = {"query_campno": q["campno"], "candidates": key}
        idmaps[qid] = idmap
        qrows.append({"query_id": qid, "category": category(q), "n_candidates": len(rows)})
    header = [
        "query_id",
        "query_text",
        "candidate_id",
        "candidate_defect",
        "label",
        "labeler_id",
        "note",
    ]
    meta = {
        "kind": "r1_pool",
        "seed": args.seed,
        "queries": qrows,
        "label_guide": {
            "2": "같은 부품이고 같은 고장 방식",
            "1": "같은 부품이지만 다른 고장",
            "0": "다른 부품",
        },
        "systems_in_pool": ["bm25", "dense", "rrf"],
        "controls": ["control_same_category(5)", "control_other_category(3)"],
        "recalls_sha256": hashlib.sha256((DATA / "recalls.jsonl").read_bytes()).hexdigest(),
    }
    prefix = args.prefix
    (OUT / f"{prefix}pool_ids.json").write_text(json.dumps(idmaps, indent=1), encoding="utf-8")
    meta["search_text"] = "expected_questions" if args.queries_file else "source_defect_text"
    _write_sheet(OUT / f"{prefix}r1_pool_sheet.csv", header, sheet, meta)
    (OUT / f"{prefix}pool_key.json").write_text(
        json.dumps(keys, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"질문 {len(keys)}개, 후보 {len(sheet)}줄 → {OUT}/{prefix}r1_pool_sheet.csv (시스템 대응표 {prefix}pool_key.json은 표시자에게 주지 않는다)"
    )


def cmd_leak_check(args) -> None:
    from scripts.defect_precedent.bm25_baseline import tokenize

    by_id = {c["campno"]: c for c in _read_jsonl(DATA / "recalls.jsonl")}
    res = {}
    for name in args.prefix:
        key = json.loads((OUT / f"{name}pool_key.json").read_text(encoding="utf-8"))
        ids = json.loads((OUT / f"{name}pool_ids.json").read_text(encoding="utf-8"))
        res[name or "source"] = leak_diagnostics(key, by_id, ids, tokenize)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit-sheet")
    a.add_argument("--n", type=int, default=100)
    a.add_argument("--seed", type=int, required=True)
    s = sub.add_parser("audit-score")
    s.add_argument("--sheet", required=True)
    r = sub.add_parser("r2-counts")
    r.add_argument("--out")
    f = sub.add_parser("question-flags")
    f.add_argument("--out")
    sc = sub.add_parser("r1-score")
    sc.add_argument(
        "--sheet", action="append", required=True, help="표시한 시트(표시자마다 하나, 두 번까지)"
    )
    sc.add_argument("--key", required=True, help="pool_key.json (표시자에게는 주지 않은 파일)")
    pi = sub.add_parser("paraphrase-input")
    pi.add_argument("--key", required=True)
    pc = sub.add_parser("paraphrase-check")
    pc.add_argument(
        "--outputs", nargs="+", required=True, help="생성 에이전트 출력 CSV(query_id,question)"
    )
    lk = sub.add_parser("leak-check")
    lk.add_argument(
        "--prefix",
        nargs="+",
        default=[""],
        help="풀 파일 접두사(원문 질문은 빈 문자열, 예상 질문은 exp_)",
    )
    q = sub.add_parser("r1-pool")
    q.add_argument("--n-queries", type=int, default=40)
    q.add_argument("--seed", type=int, required=True)
    q.add_argument("--queries-file", help="예상 질문 CSV(query_id,question) — 검색 질의만 바꾼다")
    q.add_argument("--prefix", default="", help="출력 파일 접두사")
    args = p.parse_args(argv)
    {
        "audit-sheet": cmd_audit_sheet,
        "audit-score": cmd_audit_score,
        "r2-counts": cmd_r2_counts,
        "r1-pool": cmd_r1_pool,
        "r1-score": cmd_r1_score,
        "question-flags": cmd_question_flags,
        "paraphrase-input": cmd_paraphrase_input,
        "paraphrase-check": cmd_paraphrase_check,
        "leak-check": cmd_leak_check,
    }[args.cmd](args)


if __name__ == "__main__":
    main()

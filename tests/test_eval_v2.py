"""평가셋 재설계 도구(eval_v2)의 순수 함수 시험 — 합성 입력만 쓴다."""

import pytest

from scripts.defect_precedent.eval_v2 import (
    AUDIT_BASE,
    _row_hash,
    auc,
    audit_rows,
    audit_summary,
    build_pool,
    hit_at_k,
    keyword_control,
    ndcg_at_k,
    pick_queries,
    precision_at_k,
    sensitivity_at_specificity,
    wilson,
)


def card(i, cat="BRAKES", date="20180101", dup="d", rtype="V", defect="x" * 100):
    return {
        "campno": f"C{i:03d}",
        "defect": defect + str(i),
        "consequence": "c",
        "components": [f"{cat}: SUB"],
        "received_date": date,
        "dup_group": f"{dup}{i}",
        "recall_type": rtype,
    }


def test_wilson_bounds_and_empty():
    lo, hi = wilson(50, 100)
    assert 0.40 < lo < 0.5 < hi < 0.60
    assert wilson(0, 0) == (0.0, 1.0)
    assert wilson(0, 10)[0] == 0.0


def test_ranking_metrics():
    levels = [0, 1, 2, 0]
    assert hit_at_k(levels, 3) and not hit_at_k(levels, 2)
    assert hit_at_k(levels, 2, min_level=1)
    assert precision_at_k(levels, 4) == 0.5
    assert ndcg_at_k([2, 1, 0], 3) == pytest.approx(1.0)
    assert ndcg_at_k([0, 1, 2], 3) < 1.0
    assert ndcg_at_k([0, 0], 2) == 0.0


def test_sensitivity_at_specificity_and_auc():
    pos, neg = [0.9, 0.8, 0.4], [0.1, 0.2, 0.3, 0.5]
    sens, thr = sensitivity_at_specificity(pos, neg, 0.75)
    assert thr == 0.3 and sens == pytest.approx(1.0)
    assert auc([1, 2], [0, 0.5]) == 1.0
    assert auc([0.5], [0.5]) == 0.5  # 동점은 0.5


def test_keyword_control_catches_a_leaky_summary_set():
    pos = ["GM will conduct a safety recall", "recall of 100 vehicles", "ODI opened"]
    neg = [
        "ODI closed without action",
        "complaints reviewed",
        "no defect found",
        "recall words absent",
    ]
    r = keyword_control(pos, neg, r"\brecall")
    assert r["sensitivity"] == pytest.approx(0.667, abs=1e-3)
    assert r["neg_hits"] == 1 and r["specificity"] == 0.75


def test_audit_rows_are_seeded_unlabeled_and_tamper_evident():
    cards = {f"C{i:03d}": card(i) for i in range(10)}
    qs = [
        {"action_no": f"PE{i}", "question": f"q{i}", "gold_campnos": [f"C{i:03d}"]}
        for i in range(10)
    ]
    a = audit_rows(qs, cards, 5, seed=1)
    assert a == audit_rows(qs, cards, 5, seed=1) and a != audit_rows(qs, cards, 5, seed=2)
    assert all(r["q_answerable"] == "" and r["gold_matches"] == "" for r in a)
    assert all(r["row_sha256"] == _row_hash({k: r[k] for k in AUDIT_BASE}) for r in a)


def test_audit_summary_rejects_unlabeled_or_bad_values_and_counts():
    ok = {"audit_id": "a", "q_answerable": "yes", "gold_matches": "yes", "labeler_id": "L-1"}
    bad = {**ok, "audit_id": "b", "gold_matches": ""}
    with pytest.raises(ValueError):
        audit_summary([ok, bad])
    no = {**ok, "audit_id": "c", "q_answerable": "no"}
    s = audit_summary([ok, no])
    assert s["q_answerable"]["no_share"] == 0.5 and s["valid_both_yes_share"] == 0.5


def test_pick_queries_ignores_retrieval_caps_per_category_and_is_seeded():
    cards = [card(i, cat="BRAKES") for i in range(10)] + [
        card(100 + i, cat="TIRES") for i in range(10)
    ]
    cards += [card(200, rtype="E"), card(201, date="20100101"), card(202)]
    cards[-1]["defect"] = "short"
    q = pick_queries(cards, 20, seed=7)
    assert q == pick_queries(cards, 20, seed=7)
    assert len(q) == 6  # 분류당 최대 3개 × 2분류
    assert all(
        c["recall_type"] == "V" and c["received_date"] >= "20150101" and len(c["defect"]) >= 80
        for c in q
    )


def test_build_pool_is_blind_time_valid_and_has_controls():
    cards = [card(i, cat="BRAKES", date=f"2015{(i % 9) + 1:02d}01") for i in range(30)]
    cards += [card(100 + i, cat="TIRES", date="20140101") for i in range(10)]
    query = {**card(999, cat="BRAKES", date="20170101"), "dup_group": "dq"}
    cards.append(query)
    by_id = {c["campno"]: c for c in cards}
    ids = [c["campno"] for c in cards]
    systems = {"bm25": ids[:20], "dense": ids[10:30], "rrf": ids[5:25]}
    rows, key = build_pool(query, systems, by_id, ids, seed=1)
    assert rows and set(rows[0]) == {
        "candidate_id",
        "candidate_defect",
        "label",
        "labeler_id",
        "note",
    }
    assert all(r["label"] == "" for r in rows)
    assert any("control_same_category" in v for v in key.values())
    assert any("control_other_category" in v for v in key.values())
    # 시간 조건: 질문 카드보다 먼저 접수된 카드만, 자기 자신 제외
    cand_ids = {
        cid for cid in ids if any(r["candidate_defect"] == by_id[cid]["defect"] for r in rows)
    }
    assert query["campno"] not in cand_ids
    assert all(by_id[c]["received_date"] < query["received_date"] for c in cand_ids)
    assert rows == build_pool(query, systems, by_id, ids, seed=1)[0]

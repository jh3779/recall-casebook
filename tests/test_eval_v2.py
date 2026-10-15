"""평가셋 재설계 도구(eval_v2)의 순수 함수 시험 — 합성 입력만 쓴다."""

import re

import pytest

from scripts.defect_precedent.eval_v2 import (
    AUDIT_BASE,
    _row_hash,
    agreement_report,
    auc,
    audit_rows,
    audit_summary,
    build_pool,
    cohen_kappa,
    hit_at_k,
    keyword_control,
    lcs_run,
    leak_diagnostics,
    merge_labels,
    ndcg_at_k,
    paraphrase_metrics,
    pick_queries,
    precision_at_k,
    question_flags,
    r1_score,
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
    rows, key, idmap = build_pool(query, systems, by_id, ids, seed=1)
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


def test_cohen_kappa_perfect_chance_and_empty():
    assert cohen_kappa(["2", "1", "0"], ["2", "1", "0"]) == 1.0
    assert cohen_kappa(["1", "1", "0", "0"], ["1", "0", "1", "0"]) == pytest.approx(0.0)
    assert cohen_kappa([], []) == 0.0


def _key():
    return {
        "Q1": {
            "query_campno": "C1",
            "candidates": {
                "a": {"bm25": 1, "rrf": 2},
                "b": {"bm25": 2},
                "c": {"rrf": 1},
                "x": {"control_other_category": 0},
                "y": {"control_same_category": 0},
            },
        }
    }


def test_r1_score_per_system_controls_and_judged_coverage():
    labels = {("Q1", "a"): 2, ("Q1", "b"): 0, ("Q1", "c"): 1, ("Q1", "x"): 0, ("Q1", "y"): 1}
    r = r1_score(labels, _key())
    assert r["systems"]["bm25"]["hit@10"] == 1.0 and r["systems"]["rrf"]["hit@10"] == 1.0
    assert r["systems"]["bm25"]["judged_coverage"] == 1.0
    assert r["controls"]["control_other_category"]["generous_rate"] == 0.0
    # 표시가 후하면(다른 분류 통제 후보를 관련으로 표시) 비율에 드러난다
    generous = {**labels, ("Q1", "x"): 2}
    assert r1_score(generous, _key())["controls"]["control_other_category"]["generous_rate"] == 1.0
    # 표시 안 된 후보는 점수에서 0으로 세되 표시된 비율이 낮아진다 — 빈 시트가 점수를 부풀리지 못한다
    sparse = r1_score({("Q1", "a"): 2}, _key())
    assert sparse["systems"]["bm25"]["judged_coverage"] == 0.5


def test_merge_labels_excludes_disagreement_and_reports_kappa():
    def sheet(vals):
        return [{"query_id": "Q1", "candidate_id": c, "label": v} for c, v in vals.items()]

    merged, info = merge_labels(
        [sheet({"a": "2", "b": "1", "c": "0"}), sheet({"a": "2", "b": "0", "c": "0"})]
    )
    assert ("Q1", "b") not in merged and merged[("Q1", "a")] == 2
    assert info["disputed_excluded"] == 1 and info["overlap"] == 3
    with pytest.raises(ValueError):
        merge_labels([sheet({"a": "3"})])


def test_question_flags_count_objective_properties_only():
    tok = lambda t: t.lower().replace(".", " ").split()  # noqa: E731
    cards = {
        "G": {"defect": "brake hose leaks fluid", "consequence": "crash", "remedy": "replace hose"}
    }
    qs = [
        {"question": "DD", "gold_campnos": ["G"]},
        {
            "question": "brake hose leaks fluid and the driver reported reduced braking performance repeatedly during winter testing",
            "gold_campnos": ["G"],
        },
    ]
    f = question_flags(qs, cards, tok)
    assert (
        f["short_lt100"] == 1
        and f["low_content_lt8_words"] == 1
        and f["zero_content_overlap_with_gold"] == 1
    )
    assert f["any_flag"] == 1 and f["n"] == 2


def test_lcs_run_counts_longest_contiguous_overlap():
    assert lcs_run("a b c d e".split(), "x b c d y".split()) == 3
    assert lcs_run("a b".split(), "c d".split()) == 0


def test_paraphrase_hard_fail_rules():
    tok = lambda t: re.findall(r"[a-z0-9]+", t.lower())  # noqa: E731
    strip = lambda t: re.sub(r"\bford\b", " ", t, flags=re.I).replace("  ", " ").strip()  # noqa: E731
    src = "the front brake caliper may leak fluid because the seal is damaged during assembly"
    good = "brake fluid leaks from a caliper seal that was damaged in production"
    assert paraphrase_metrics(src, good, tok, strip)["hard_fail"] == []
    assert (
        "digit"
        in paraphrase_metrics(
            src, "caliper seal leak after 3 weeks of normal driving here", tok, strip
        )["hard_fail"]
    )
    assert (
        "brand"
        in paraphrase_metrics(
            src, "Ford brake caliper seal leaks fluid after assembly work", tok, strip
        )["hard_fail"]
    )
    assert "length" in paraphrase_metrics(src, "brake leak", tok, strip)["hard_fail"]
    copy = "the front brake caliper may leak fluid because the seal is damaged"
    assert "copy_run>=7" in paraphrase_metrics(src, copy, tok, strip)["hard_fail"]


def test_leak_diagnostics_same_maker_and_copy_like_candidates():
    tok = lambda t: re.findall(r"[a-z0-9]+", t.lower())  # noqa: E731
    q = {
        **card(1, defect="brake caliper seal leak fluid assembly damaged "),
        "maker": "A",
        "maker_group": "A",
    }
    same = {
        **card(2, defect="brake caliper seal leak fluid assembly damaged "),
        "maker": "A",
        "maker_group": "A",
    }
    other = {
        **card(3, defect="airbag inflator rupture shrapnel deployment "),
        "maker": "B",
        "maker_group": "B",
    }
    by_id = {c["campno"]: c for c in (q, same, other)}
    key = {"Q1": {"query_campno": "C001", "candidates": {"h1": {"bm25": 1}, "h2": {"bm25": 2}}}}
    r = leak_diagnostics(key, by_id, {"Q1": {"h1": "C002", "h2": "C003"}}, tok)
    assert r["bm25"]["same_maker_share"] == 0.5 and r["bm25"]["copy_like_share"] == 0.5


def test_paraphrase_rejects_cause_expression_in_the_question():
    tok = lambda t: re.findall(r"[a-z0-9]+", t.lower())  # noqa: E731
    strip = lambda t: t  # noqa: E731
    src = "the caliper seal is damaged and brake fluid leaks out of the front hydraulic assembly"
    ok = "brake fluid leaks near a front caliper and the pedal feels soft under braking"
    bad = "brake fluid leaks near a front caliper because the seal was damaged during assembly work"
    assert paraphrase_metrics(src, ok, tok, strip)["hard_fail"] == []
    assert "cause_expression" in paraphrase_metrics(src, bad, tok, strip)["hard_fail"]


def test_r1_score_reports_level2_precision_separately_from_part_only_precision():
    key = {"Q1": {"query_campno": "C1", "candidates": {"a": {"bm25": 1}, "b": {"bm25": 2}}}}
    r = r1_score({("Q1", "a"): 2, ("Q1", "b"): 1}, key)["systems"]["bm25"]
    assert r["precision@10"] == 1.0 and r["precision@10_level2"] == 0.5


def test_agreement_report_overlap_kappa_and_generosity_direction():
    a = {("Q1", "x"): 2, ("Q1", "y"): 1, ("Q1", "z"): 0, ("Q1", "only_a"): 2}
    b = {("Q1", "x"): 2, ("Q1", "y"): 0, ("Q1", "z"): 0}
    r = agreement_report(a, b)
    assert r["overlap"] == 3 and r["exact_agreement"] == round(2 / 3, 3)
    assert r["a_more_generous"] == round(1 / 3, 3) and r["b_more_generous"] == 0.0
    assert agreement_report({}, b) == {"overlap": 0}

"""scripts/defect_precedent/time_eval_score.py — 시점 평가 채점 규칙(DEC-037 ⑦, 안내서 4·5절) 테스트.

실제 정답 표시는 쓰지 않는다(표시 전 고정). 작은 가짜 시트·후보 파일로 규칙만 시험한다.
"""

import csv
import json

import pytest

from scripts.defect_precedent import time_eval_score as ts

PINNED_BOOTSTRAP = (-0.125, 0.325)  # 아래 부트스트랩 고정 테스트의 기댓값
COLS = ["action_no", "campno", "dup_group", "label", "agreed_label", "labeler_id", "note"]


def write_sheet(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({"agreed_label": "", "labeler_id": "L-A1", "note": "", **r})
    return path


def row(action, campno, label, **kw):
    return {
        "action_no": action,
        "campno": campno,
        "dup_group": kw.pop("dup_group", campno),
        "label": label,
        **kw,
    }


def items(*specs):
    """specs: (action, {campno: {"bm25": r, "b_rrf": r}})"""
    return [
        {"action_no": a, "open_date": "20200101", "n_indexed": 10, "pool": pool}
        for a, pool in specs
    ]


def test_mcnemar_exact_matches_the_thresholds_written_in_dec037():
    # DEC-037 ⑦(e): n≈34~45에서는 불일치가 6:0·8:1 이상이어야 p < 0.05
    assert ts.mcnemar_exact(6, 0) < 0.05 and ts.mcnemar_exact(5, 0) >= 0.05
    assert ts.mcnemar_exact(8, 1) < 0.05 and ts.mcnemar_exact(7, 1) >= 0.05
    assert ts.mcnemar_exact(0, 0) == 1.0


def test_wilson_interval_bounds():
    assert ts.wilson(0, 0) is None
    lo, hi = ts.wilson(17, 34)
    assert lo < 0.5 < hi and 0 <= lo and hi <= 1


def test_score_uses_agreed_label_first_and_counts_both_scores(tmp_path):
    cand = items(
        ("PE1", {"A": {"bm25": 1, "b_rrf": 12}, "B": {"bm25": 15, "b_rrf": 2}}),
        ("PE2", {"C": {"bm25": 3}, "D": {"b_rrf": 4}}),
        ("PE3", {"E": {"bm25": 1, "b_rrf": 1}}),
    )
    sheet = write_sheet(
        tmp_path / "s.csv",
        [
            row("PE1", "A", "no"),
            row("PE1", "B", "no", agreed_label="yes"),  # 합의 결과가 우선
            row("PE2", "C", "no"),
            row("PE2", "D", "no"),
            row("PE3", "E", "unsure", note=ts.NO_PART),
        ],
    )
    # 합의값은 두 사람이 표시한 후보에만 쓴다 — B를 함께 표시한 두 번째 사람(다르게 표시, 같은 합의값)
    second = write_sheet(
        tmp_path / "c.csv", [row("PE1", "B", "yes", labeler_id="L-C1", agreed_label="yes")]
    )
    merged = ts.merge_labels([ts.read_sheet(sheet), ts.read_sheet(second)])
    ts.check_against_candidates(merged, cand)
    qs, skipped = ts.per_question(merged, cand, partial=False)
    out = ts.summarize(qs)
    assert out["answered"] == 1 and out["labeled_questions"] == 3
    assert out["no_answer"] == {ts.NO_PART: 1, "후보에 선례 없음": 1}
    # PE1의 정답 B는 b_rrf 2위·bm25 15위
    assert out["b_rrf"]["hit@3"]["pool"] == 1.0 and out["bm25"]["hit@10"]["pool"] == 0.0
    assert out["b_rrf"]["hit@3"]["lower_bound"] == round(1 / 3, 3)  # 하한은 표시한 전체 문항이 분모
    assert out["status"].startswith("미측정")  # 정답 있는 문항 34개 미만


def test_score_refuses_conflicting_double_labels_without_agreement(tmp_path):
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes")])
    b = write_sheet(tmp_path / "b.csv", [row("PE1", "A", "no", labeler_id="L-C1")])
    with pytest.raises(SystemExit, match="agreed_label"):
        ts.merge_labels([ts.read_sheet(a), ts.read_sheet(b)])
    c = write_sheet(
        tmp_path / "c.csv", [row("PE1", "A", "no", labeler_id="L-C1", agreed_label="yes")]
    )
    assert ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])[("PE1", "A")]["final"] == "yes"


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([row("PE1", "A", "maybe")], "yes/no/unsure"),
        ([row("PE1", "A", "yes", labeler_id="")], "labeler_id"),
    ],
)
def test_score_refuses_bad_labels(tmp_path, rows, message):
    with pytest.raises(SystemExit, match=message):
        ts.merge_labels([ts.read_sheet(write_sheet(tmp_path / "s.csv", rows))])


def test_score_refuses_sheet_that_does_not_match_hidden_candidates_or_splits_dup_group(tmp_path):
    cand = items(("PE1", {"A": {"bm25": 1}, "B": {"b_rrf": 1}}))
    short = ts.merge_labels(
        [ts.read_sheet(write_sheet(tmp_path / "s.csv", [row("PE1", "A", "no")]))]
    )
    with pytest.raises(SystemExit, match="후보가 다르다"):
        ts.check_against_candidates(short, cand)
    split = ts.merge_labels(
        [
            ts.read_sheet(
                write_sheet(
                    tmp_path / "t.csv",
                    [row("PE1", "A", "yes", dup_group="G"), row("PE1", "B", "no", dup_group="G")],
                )
            )
        ]
    )
    with pytest.raises(SystemExit, match="dup_group"):
        ts.check_against_candidates(split, cand)


def test_score_stops_on_unlabeled_rows_unless_partial(tmp_path):
    cand = items(("PE1", {"A": {"bm25": 1}}), ("PE2", {"B": {"bm25": 1}}))
    merged = ts.merge_labels(
        [
            ts.read_sheet(
                write_sheet(
                    tmp_path / "s.csv", [row("PE1", "A", "yes"), row("PE2", "B", "", labeler_id="")]
                )
            )
        ]
    )
    with pytest.raises(SystemExit, match="표시가 빈"):
        ts.per_question(merged, cand, partial=False)
    qs, skipped = ts.per_question(merged, cand, partial=True)
    assert skipped == ["PE2"] and len(qs) == 1


def _q(bm, b):
    return {"answered": True, "bm25": 1 if bm else None, "b_rrf": 1 if b else None}


def test_outcome_needs_both_p_value_and_003_difference():
    many = [_q(True, True)] * 34
    out = ts.summarize(many + [_q(False, True)] * 6)  # 6:0, n=40
    assert out["hit@10_comparison"]["outcome"] == "차이 있음 — B가 높음"
    out = ts.summarize(many + [_q(False, True)] * 5)  # 5:0 — p ≥ 0.05
    assert out["hit@10_comparison"]["outcome"] == "우열 불확실"
    assert out["status"] == "측정"
    # p는 아주 작지만 차이가 0.03 미만(25:5, n=1000 → 0.02) — 0.03 조건만으로 "우열 불확실"
    big = [_q(True, True)] * 970 + [_q(False, True)] * 25 + [_q(True, False)] * 5
    cmp = ts.summarize(big)["hit@10_comparison"]
    assert cmp["mcnemar_exact_p"] < 0.05 and cmp["diff_b_minus_bm25"] == 0.02
    assert cmp["outcome"] == "우열 불확실"


def test_outcome_is_unmeasured_below_34_answered_even_if_lopsided():
    """정답 있는 문항이 34개 미만이면 6:0이어도 방향을 내지 않는다(DEC-037 ⑤) — 발췌 오해 방지."""
    out = ts.summarize([_q(False, True)] * 6)
    assert out["status"].startswith("미측정")
    assert out["hit@10_comparison"]["outcome"] == "미측정"


def test_measured_boundary_is_exactly_34_answered():
    """33개면 미측정(status·outcome 모두), 34개면 측정 — DEC-037 ⑤의 경계를 고정한다."""
    out33 = ts.summarize([_q(True, True)] * 33)
    assert (
        out33["status"].startswith("미측정") and out33["hit@10_comparison"]["outcome"] == "미측정"
    )
    out34 = ts.summarize([_q(True, True)] * 34)
    assert out34["status"] == "측정" and out34["hit@10_comparison"]["outcome"] == "우열 불확실"


def test_hit_at_k_boundary_is_inclusive():
    """정답이 정확히 k위면 Hit@k, k+1위면 아니다."""
    assert ts.hit({"bm25": 10}, "bm25", 10) and not ts.hit({"bm25": 11}, "bm25", 10)
    assert ts.hit({"bm25": 1}, "bm25", 1) and not ts.hit({"bm25": None}, "bm25", 10)


def test_bootstrap_is_pinned_to_dec037_seed_draws_and_percentiles():
    """시드 20261008·10,000회·2.5/97.5 백분위(DEC-037 ⑦(e))가 바뀌면 이 값이 달라진다(2026-10-11 numpy로 고정)."""
    answered = [_q(True, True)] * 20 + [_q(False, True)] * 12 + [_q(True, False)] * 8
    assert ts.BOOT_SEED == 20261008 and ts.BOOT_N == 10_000
    assert ts.bootstrap(answered) == PINNED_BOOTSTRAP


def test_agreement_refuses_two_sheets_from_the_same_labeler():
    rows = [row("PE1", "A", "yes", labeler_id="L-A1")]
    with pytest.raises(SystemExit, match="labeler_id가 같다"):
        ts.agreement(rows, rows, expect=1)


def test_score_lists_questions_labeled_by_two_people(tmp_path):
    cand = items(("PE1", {"A": {"bm25": 1}}), ("PE2", {"B": {"bm25": 1}}))
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes"), row("PE2", "B", "yes")])
    c = write_sheet(tmp_path / "c.csv", [row("PE1", "A", "yes", labeler_id="L-C1")])
    merged = ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])
    qs, _ = ts.per_question(merged, cand, partial=False)
    assert ts.summarize(qs)["multi_labeler_questions"] == ["PE1"]


def test_agreement_uses_raw_labels_and_lists_one_sided_yes(tmp_path):
    rows_a = [
        row("PE1", "A", "yes", labeler_id="L-A1"),
        row("PE1", "B", "no", labeler_id="L-A1"),
        row("PE2", "C", "no", labeler_id="L-A1"),
    ]
    rows_b = [
        row("PE1", "A", "yes", labeler_id="L-C1"),
        row(
            "PE1", "B", "yes", labeler_id="L-C1", agreed_label="no"
        ),  # 합의 결과는 일치율에 쓰지 않는다
        row("PE2", "C", "no", labeler_id="L-C1"),
    ]
    out = ts.agreement(rows_a, rows_b, expect=2)
    assert out["question_level_same"] == 2
    assert out["candidate_focus_n"] == 2 and out["candidate_agreement"] == 0.5
    assert out["pass"] is False
    assert out["one_sided_yes_to_resolve"] == [["PE1", "B"]]


def test_cli_score_prints_inputs_and_note(tmp_path, capsys):
    cand_path = tmp_path / "candidates_main.json"
    cand_path.write_text(
        json.dumps(
            {
                "set": "main",
                "code": {"commit": "abc"},
                "items": items(("PE1", {"A": {"bm25": 1, "b_rrf": 2}})),
            }
        ),
        encoding="utf-8",
    )
    sheet = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes")])
    ts.main(["score", "--candidates", str(cand_path), "--sheets", str(sheet)])
    out = json.loads(capsys.readouterr().out)
    (cand,) = out["inputs"]["candidates"]
    assert cand["set"] == "main" and cand["code"] == {"commit": "abc"} and len(cand["sha256"]) == 64
    assert "근사 시점 평가" in out["note"]
    assert out["inputs"]["numpy"]


def test_agreement_requires_one_labeler_per_sheet_and_expected_question_count():
    a = [row("PE1", "A", "yes", labeler_id="L-A1")]
    c = [row("PE1", "A", "yes", labeler_id="L-C1")]
    blank = [row("PE1", "A", "yes", labeler_id="")]
    mixed = [row("PE1", "A", "yes", labeler_id="L-A1"), row("PE1", "B", "no", labeler_id="L-B1")]
    with pytest.raises(SystemExit, match="한 사람으로"):
        ts.agreement(blank, c, expect=1)  # ID를 비운 시트
    with pytest.raises(SystemExit, match="한 사람으로"):
        ts.agreement(mixed, c, expect=1)  # 한 시트에 두 사람
    with pytest.raises(SystemExit, match="--expect"):
        ts.agreement(a, c, expect=5)  # 1문항짜리 시트로 예비 5문항 합격을 낼 수 없다
    assert ts.agreement(a, c, expect=1)["pass"] is True


def test_agreed_label_needs_two_labelers(tmp_path):
    """합의값은 두 사람 이상이 label을 남긴 후보에만 — 합의값만 있는 줄·한 사람 표시에 붙은 합의값은 멈춘다."""
    only_agreed = write_sheet(
        tmp_path / "a.csv", [row("PE1", "A", "", labeler_id="", agreed_label="yes")]
    )
    with pytest.raises(SystemExit, match="두 사람 이상"):
        ts.merge_labels([ts.read_sheet(only_agreed)])
    one = write_sheet(tmp_path / "b.csv", [row("PE1", "A", "no", agreed_label="yes")])
    with pytest.raises(SystemExit, match="두 사람 이상"):
        ts.merge_labels([ts.read_sheet(one)])


def test_dup_group_must_match_across_sheets(tmp_path):
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes", dup_group="G1")])
    c = write_sheet(tmp_path / "c.csv", [row("PE1", "A", "yes", labeler_id="L-C1", dup_group="G2")])
    with pytest.raises(SystemExit, match="dup_group이 다르다"):
        ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])


def test_partial_result_never_shows_a_direction():
    """표시가 안 끝난 문항을 뺀 중간 결과는 34개 이상·6:0이어도 방향을 내지 않는다."""
    qs = [_q(True, True)] * 34 + [_q(False, True)] * 6
    assert ts.summarize(qs)["hit@10_comparison"]["outcome"] == "차이 있음 — B가 높음"
    assert ts.summarize(qs, partial=True)["hit@10_comparison"]["outcome"] == "미측정(중간 결과)"


def test_no_part_reason_only_when_all_final_labels_are_unsure(tmp_path):
    """합의로 최종이 no가 되면, 합의 전 메모에 "질문 부품 불명"이 있어도 사유는 "후보에 선례 없음"."""
    cand = items(("PE1", {"A": {"bm25": 1}}))
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "unsure", note=ts.NO_PART)])
    c = write_sheet(
        tmp_path / "c.csv", [row("PE1", "A", "no", labeler_id="L-C1", agreed_label="no")]
    )
    merged = ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])
    qs, _ = ts.per_question(merged, cand, partial=False)
    assert qs[0]["reason"] == "후보에 선례 없음"


def test_cli_score_combines_replacement_candidates_and_refuses_overlap(tmp_path, capsys):
    """대체 회차를 더 표시하면 후보 파일 여러 개를 합쳐 한 번에 채점한다 — 문항이 겹치면 멈춘다."""

    def cand_file(name, set_name, action):
        p = tmp_path / name
        p.write_text(
            json.dumps({"set": set_name, "items": items((action, {"A": {"bm25": 1}}))}),
            encoding="utf-8",
        )
        return p

    main = cand_file("candidates_main.json", "main", "PE1")
    repl = cand_file("candidates_r1.json", "r1", "PE2")
    sheet = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes"), row("PE2", "A", "no")])
    ts.main(["score", "--candidates", str(main), str(repl), "--sheets", str(sheet)])
    out = json.loads(capsys.readouterr().out)
    assert out["labeled_questions"] == 2 and [c["set"] for c in out["inputs"]["candidates"]] == [
        "main",
        "r1",
    ]
    overlap = cand_file("candidates_r2.json", "r2", "PE1")
    with pytest.raises(SystemExit, match="같은 문항이 두 번"):
        ts.main(["score", "--candidates", str(main), str(overlap), "--sheets", str(sheet)])


def _agree_rows(labeler, labels):
    """labels: {(문항, 후보): 표시}"""
    return [row(a, c, lab, labeler_id=labeler) for (a, c), lab in labels.items()]


def test_agreement_pass_needs_question_level_agreement_even_with_high_candidate_rate():
    """후보 일치율이 0.975여도 한 문항에서 정답 있음 여부가 갈리면 불합격(안내서 4절 두 조건 모두)."""
    keys = [(f"PE{q}", f"C{q}{i}") for q in range(5) for i in range(8)]
    a = dict.fromkeys(keys, "unsure")
    c = dict(a)
    a[("PE0", "C00")], c[("PE0", "C00")] = "yes", "no"
    out = ts.agreement(_agree_rows("L-A1", a), _agree_rows("L-C1", c), expect=5)
    assert out["candidate_agreement"] == 0.975 and out["question_level_same"] == 4
    assert out["pass"] is False


@pytest.mark.parametrize(("same", "expected"), [(4, True), (3, False)])
def test_agreement_candidate_rate_boundary_is_080(same, expected):
    """yes/unsure 후보 5개 중 4개 일치(0.8)면 합격, 4개 중 3개(0.75)면 불합격 — 문항 단위는 모두 같게 둔다."""
    n = same + 1
    a = {("PE1", f"C{i}"): "unsure" for i in range(n)}
    c = dict(a)
    c[("PE1", f"C{n - 1}")] = "no"  # 하나만 다르게(정답 있음 여부는 둘 다 '없음'으로 같다)
    out = ts.agreement(_agree_rows("L-A1", a), _agree_rows("L-C1", c), expect=1)
    assert out["candidate_agreement"] == round(same / n, 3) and out["pass"] is expected


def test_agreement_refuses_sheets_with_different_candidates():
    a = {("PE1", "A"): "no", ("PE1", "B"): "no"}
    c = {("PE1", "A"): "no"}
    with pytest.raises(SystemExit, match="문항·후보가 다르다"):
        ts.agreement(_agree_rows("L-A1", a), _agree_rows("L-C1", c), expect=1)


def test_agreed_label_conflict_between_sheets_stops(tmp_path):
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes", agreed_label="yes")])
    c = write_sheet(
        tmp_path / "c.csv", [row("PE1", "A", "no", labeler_id="L-C1", agreed_label="no")]
    )
    with pytest.raises(SystemExit, match="agreed_label이 시트마다 다르다"):
        ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])


def test_all_unsure_without_note_is_no_precedent(tmp_path):
    """모두 unsure여도 메모에 "질문 부품 불명"이 없으면 사유는 "후보에 선례 없음"."""
    cand = items(("PE1", {"A": {"bm25": 1}}))
    s = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "unsure")])
    qs, _ = ts.per_question(ts.merge_labels([ts.read_sheet(s)]), cand, partial=False)
    assert qs[0]["reason"] == "후보에 선례 없음"


def _qr(bm, b, answered=True):
    """순위를 직접 주는 문항(None = 후보에 없음)."""
    return {"answered": answered, "bm25": bm, "b_rrf": b}


def test_measured_threshold_counts_answered_questions_not_all_labeled():
    """34개 문턱은 "정답 있는" 문항 수다 — 정답 없는 문항을 섞어도 표시한 수로 세지 않는다(DEC-037 ⑤)."""
    out = ts.summarize([_q(True, True)] * 33 + [_qr(None, None, answered=False)] * 12)
    assert out["status"].startswith("미측정") and out["hit@10_comparison"]["outcome"] == "미측정"
    assert (
        ts.summarize([_q(True, True)] * 34 + [_qr(None, None, answered=False)] * 11)["status"]
        == "측정"
    )


def test_outcome_is_judged_on_hit_at_10_only():
    """B가 7위, BM25가 12위로만 맞히는 문항 — Hit@5로는 둘 다 실패지만 Hit@10 판정은 B가 높다."""
    qs = [_q(True, True)] * 34 + [_qr(12, 7)] * 6
    cmp = ts.summarize(qs)["hit@10_comparison"]
    assert (cmp["b_only"], cmp["bm25_only"]) == (6, 0) and cmp["outcome"] == "차이 있음 — B가 높음"


def test_question_rank_is_the_best_ranked_yes_candidate(tmp_path):
    """정답이 둘(3위·15위)이면 가장 높은 순위(3)로 센다 — 하나라도 상위 k면 Hit(DEC-037 ⑦(g))."""
    cand = items(("PE1", {"A": {"bm25": 3, "b_rrf": 15}, "B": {"bm25": 15, "b_rrf": 3}}))
    s = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes"), row("PE1", "B", "yes")])
    qs, _ = ts.per_question(ts.merge_labels([ts.read_sheet(s)]), cand, partial=False)
    assert (qs[0]["bm25"], qs[0]["b_rrf"]) == (3, 3)


def test_typo_in_agreed_label_stops(tmp_path):
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes", agreed_label="yse")])
    with pytest.raises(SystemExit, match="yes/no/unsure"):
        ts.merge_labels([ts.read_sheet(a)])


def test_agreement_refuses_blank_or_typo_labels():
    good = [row("PE1", "A", "no", labeler_id="L-A1")]
    for bad in ("", "nO!"):
        other = [row("PE1", "A", bad, labeler_id="L-C1")]
        with pytest.raises(SystemExit, match="yes/no/unsure"):
            ts.agreement(good, other, expect=1)


def test_one_sided_yes_list_ignores_disagreements_without_yes():
    """해소 목록은 "한 사람만 yes"인 후보만 — no·unsure 불일치는 넣지 않는다(안내서 4절)."""
    a = [row("PE1", "A", "no", labeler_id="L-A1"), row("PE1", "B", "yes", labeler_id="L-A1")]
    c = [row("PE1", "A", "unsure", labeler_id="L-C1"), row("PE1", "B", "no", labeler_id="L-C1")]
    assert ts.agreement(a, c, expect=1)["one_sided_yes_to_resolve"] == [["PE1", "B"]]


def test_agreement_refuses_duplicate_rows_in_a_sheet():
    a = [row("PE1", "A", "yes", labeler_id="L-A1"), row("PE1", "A", "no", labeler_id="L-A1")]
    c = [row("PE1", "A", "no", labeler_id="L-C1")]
    with pytest.raises(SystemExit, match="두 번"):
        ts.agreement(a, c, expect=1)


def test_wilson_value_and_lower_bound_denominator():
    assert ts.wilson(17, 34) == (0.341, 0.659)
    out = ts.summarize([_q(True, True)] * 34 + [_qr(None, None, answered=False)] * 6)
    assert out["bm25"]["hit@10"]["lower_bound_wilson95"] == ts.wilson(
        34, 40
    )  # 하한은 표시한 전체가 분모


def test_cli_score_refuses_pilot_candidates(tmp_path):
    p = tmp_path / "candidates_pilot.json"
    p.write_text(
        json.dumps({"set": "pilot", "items": items(("PE1", {"A": {"bm25": 1}}))}), encoding="utf-8"
    )
    sheet = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes")])
    with pytest.raises(SystemExit, match="pilot"):
        ts.main(["score", "--candidates", str(p), "--sheets", str(sheet)])

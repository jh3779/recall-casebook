"""scripts/defect_precedent/time_eval_score.py — 시점 평가 채점 규칙(DEC-037 ⑦, 안내서 4·5절) 테스트.

실제 정답 표시는 쓰지 않는다(표시 전 고정). 작은 가짜 시트·후보 파일로 규칙만 시험한다.
"""

import csv
import json
import re
from pathlib import Path

import pytest

from scripts.defect_precedent import time_eval_score as ts
from scripts.defect_precedent.time_eval_candidates import CODE_FILES, ROOT

# 후보 생성기가 기록하는 세 스크립트 경로 — 정식 채점이 받는 판본 정보에는 모두 있어야 한다(이슈 #77)
SCRIPTS = {f: "a" * 64 for f in CODE_FILES}

PINNED_BOOTSTRAP = (-0.125, 0.325)  # 아래 부트스트랩 고정 테스트의 기댓값
COLS = ["action_no", "campno", "dup_group", "label", "agreed_label", "labeler_id", "note"]


def write_sheet(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({"agreed_label": "", "labeler_id": "L-A1", "note": "", **r})
    return path


def agreement_file(tmp_path, phase, passed, questions=None, name=None, cand=None, **extra):
    """agreement 출력 모양 그대로 — score가 phase·pass·합의 해소, 질문 파일 해시, 후보 판본(_cand와 같은 판본)을 본다.
    cand: 재확인 결과가 쓴 후보 파일(score의 본 평가 후보 파일과 해시 대조)."""
    q = questions or ts.QUESTIONS
    p = tmp_path / (name or f"agreement_{phase}.json")
    used = {
        **{k: v for k, v in _cand(phase).items()},
        "sha256": ts.sha256_of(cand) if cand else None,
    }
    out = {
        "phase": phase,
        "pass": passed,
        "resolution_complete": True,
        "inputs": {"questions": {"sha256": ts.sha256_of(q)}, "candidates": used},
        **extra,
    }
    p.write_text(json.dumps(out), encoding="utf-8")
    return str(p)


def _pilot_pass(tmp_path):
    return ["--agreement", agreement_file(tmp_path, "pilot", True, name="agreement_pilot_ok.json")]


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
        tmp_path / "c.csv",
        [  # 두 사람이 표시한 문항은 각자 그 문항의 모든 후보를 표시한다(안내서 4절)
            row("PE1", "A", "no", labeler_id="L-C1"),
            row("PE1", "B", "yes", labeler_id="L-C1", agreed_label="yes"),
        ],
    )
    merged = ts.merge_labels([ts.read_sheet(sheet), ts.read_sheet(second)])
    ts.check_against_candidates(merged, cand)
    qs, skipped = ts.per_question(merged, cand, partial=False)
    out = ts.summarize(qs)
    assert out["answered"] == 1 and out["labeled_questions"] == 3
    assert out["no_answer"] == {ts.NO_PART: 1, ts.UNSURE_ONLY: 0, "후보에 선례 없음": 1}
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
        ts.agreement(rows, rows, expected={"PE1"})


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
    out = ts.agreement(rows_a, rows_b, expected={"PE1", "PE2"})
    assert out["question_level_same"] == 2
    assert out["candidate_focus_n"] == 2 and out["candidate_agreement"] == 0.5
    assert out["pass"] is False
    assert out["one_sided_yes_to_resolve"] == [["PE1", "B"]]


def test_cli_score_prints_inputs_and_note(tmp_path, capsys):
    cand_path = tmp_path / "candidates_main.json"
    cand_path.write_text(
        json.dumps(
            {
                **_cand(
                    "main",
                    code={"dirty": False, "commit": "abc", "script_sha256": SCRIPTS},
                ),
                "items": items(("PE1", {"A": {"bm25": 1, "b_rrf": 2}})),
            }
        ),
        encoding="utf-8",
    )
    sheet = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes")])
    ts.main(
        ["score", *_pilot_pass(tmp_path), "--candidates", str(cand_path), "--sheets", str(sheet)]
    )
    out = json.loads(capsys.readouterr().out)
    (cand,) = out["inputs"]["candidates"]
    assert cand["set"] == "main" and cand["code"]["commit"] == "abc" and len(cand["sha256"]) == 64
    assert "근사 시점 평가" in out["note"]
    assert out["inputs"]["numpy"]


def test_agreement_requires_one_labeler_per_sheet_and_expected_question_count():
    a = [row("PE1", "A", "yes", labeler_id="L-A1")]
    c = [row("PE1", "A", "yes", labeler_id="L-C1")]
    blank = [row("PE1", "A", "yes", labeler_id="")]
    mixed = [row("PE1", "A", "yes", labeler_id="L-A1"), row("PE1", "B", "no", labeler_id="L-B1")]
    with pytest.raises(SystemExit, match="한 사람으로"):
        ts.agreement(blank, c, expected={"PE1"})  # ID를 비운 시트
    with pytest.raises(SystemExit, match="한 사람으로"):
        ts.agreement(mixed, c, expected={"PE1"})  # 한 시트에 두 사람
    with pytest.raises(SystemExit, match="정해진 문항"):
        ts.agreement(a, c, expected={"PE1", "PE2"})  # 덜 표시한 시트로 합격을 낼 수 없다
    with pytest.raises(SystemExit, match="정해진 문항"):
        ts.agreement(a, c, expected={"PE9"})  # 정해진 문항 대신 다른 문항을 고른 시트
    assert ts.agreement(a, c, expected={"PE1"})["pass"] is True


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
            # 합치는 회차는 같은 데이터·스크립트·모델이어야 한다(check_same_build) — 같은 판본 정보를 넣는다
            json.dumps({**_cand(set_name), "items": items((action, {"A": {"bm25": 1}}))}),
            encoding="utf-8",
        )
        return p

    main = cand_file("candidates_main.json", "main", "PE1")
    repl = cand_file("candidates_r1.json", "r1", "PE2")
    sheet = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes"), row("PE2", "A", "no")])
    ts.main(
        [
            "score",
            *_pilot_pass(tmp_path),
            "--candidates",
            str(main),
            str(repl),
            "--sheets",
            str(sheet),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["labeled_questions"] == 2 and [c["set"] for c in out["inputs"]["candidates"]] == [
        "main",
        "r1",
    ]
    overlap = cand_file("candidates_r2.json", "r2", "PE1")
    with pytest.raises(SystemExit, match="같은 문항이 두 번"):
        ts.main(
            [
                "score",
                *_pilot_pass(tmp_path),
                "--candidates",
                str(main),
                str(overlap),
                "--sheets",
                str(sheet),
            ]
        )


def _agree_rows(labeler, labels):
    """labels: {(문항, 후보): 표시}"""
    return [row(a, c, lab, labeler_id=labeler) for (a, c), lab in labels.items()]


def test_agreement_pass_needs_question_level_agreement_even_with_high_candidate_rate():
    """후보 일치율이 0.975여도 한 문항에서 정답 있음 여부가 갈리면 불합격(안내서 4절 두 조건 모두)."""
    keys = [(f"PE{q}", f"C{q}{i}") for q in range(5) for i in range(8)]
    a = dict.fromkeys(keys, "unsure")
    c = dict(a)
    a[("PE0", "C00")], c[("PE0", "C00")] = "yes", "no"
    out = ts.agreement(
        _agree_rows("L-A1", a), _agree_rows("L-C1", c), expected={f"PE{q}" for q in range(5)}
    )
    assert out["candidate_agreement"] == 0.975 and out["question_level_same"] == 4
    assert out["pass"] is False


@pytest.mark.parametrize(("same", "expected"), [(4, True), (3, False)])
def test_agreement_candidate_rate_boundary_is_080(same, expected):
    """yes/unsure 후보 5개 중 4개 일치(0.8)면 합격, 4개 중 3개(0.75)면 불합격 — 문항 단위는 모두 같게 둔다."""
    n = same + 1
    a = {("PE1", f"C{i}"): "unsure" for i in range(n)}
    c = dict(a)
    c[("PE1", f"C{n - 1}")] = "no"  # 하나만 다르게(정답 있음 여부는 둘 다 '없음'으로 같다)
    out = ts.agreement(_agree_rows("L-A1", a), _agree_rows("L-C1", c), expected={"PE1"})
    assert out["candidate_agreement"] == round(same / n, 3) and out["pass"] is expected


def test_agreement_refuses_sheets_with_different_candidates():
    a = {("PE1", "A"): "no", ("PE1", "B"): "no"}
    c = {("PE1", "A"): "no"}
    with pytest.raises(SystemExit, match="문항·후보가 다르다"):
        ts.agreement(_agree_rows("L-A1", a), _agree_rows("L-C1", c), expected={"PE1"})


def test_agreed_label_conflict_between_sheets_stops(tmp_path):
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes", agreed_label="yes")])
    c = write_sheet(
        tmp_path / "c.csv", [row("PE1", "A", "no", labeler_id="L-C1", agreed_label="no")]
    )
    with pytest.raises(SystemExit, match="agreed_label이 시트마다 다르다"):
        ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])


def test_all_unsure_without_note_is_no_precedent(tmp_path):
    """모두 unsure인데 메모에 "질문 부품 불명"이 없으면 "unsure만(판단 불가)"로 따로 센다 — "후보에 선례 없음"에 숨기지 않는다(DEC-037 ⑦(a))."""
    cand = items(("PE1", {"A": {"bm25": 1}}))
    s = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "unsure")])
    qs, _ = ts.per_question(ts.merge_labels([ts.read_sheet(s)]), cand, partial=False)
    assert qs[0]["reason"] == ts.UNSURE_ONLY


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
            ts.agreement(good, other, expected={"PE1"})


def test_one_sided_yes_list_ignores_disagreements_without_yes():
    """해소 목록은 "한 사람만 yes"인 후보만 — no·unsure 불일치는 넣지 않는다(안내서 4절)."""
    a = [row("PE1", "A", "no", labeler_id="L-A1"), row("PE1", "B", "yes", labeler_id="L-A1")]
    c = [row("PE1", "A", "unsure", labeler_id="L-C1"), row("PE1", "B", "no", labeler_id="L-C1")]
    assert ts.agreement(a, c, expected={"PE1"})["one_sided_yes_to_resolve"] == [["PE1", "B"]]


def test_agreement_refuses_duplicate_rows_in_a_sheet():
    a = [row("PE1", "A", "yes", labeler_id="L-A1"), row("PE1", "A", "no", labeler_id="L-A1")]
    c = [row("PE1", "A", "no", labeler_id="L-C1")]
    with pytest.raises(SystemExit, match="두 번"):
        ts.agreement(a, c, expected={"PE1"})


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
        ts.main(["score", *_pilot_pass(tmp_path), "--candidates", str(p), "--sheets", str(sheet)])


def test_phase_actions_are_the_fixed_questions():
    """예비 = 질문 파일 pilot 전부, 재확인 = main 앞 3개(안내서 4절 — PE12017·PE11022·PE18009)."""
    assert ts.phase_actions("recheck") == {"PE12017", "PE11022", "PE18009"}
    assert len(ts.phase_actions("pilot")) == 5


def test_double_labeled_question_needs_every_candidate_from_both(tmp_path):
    """두 사람이 표시한 문항에서 한 사람이 일부 후보만 표시하면 멈춘다 — 나머지가 한 사람 표시로 채점되지 않게."""
    cand = items(("PE1", {"A": {"bm25": 1}, "B": {"bm25": 2}}))
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes"), row("PE1", "B", "no")])
    c = write_sheet(tmp_path / "c.csv", [row("PE1", "A", "yes", labeler_id="L-C1")])
    merged = ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])
    with pytest.raises(SystemExit, match="일부 후보"):
        ts.per_question(merged, cand, partial=False)


def _cand(set_name, **kw):
    base = {
        "set": set_name,
        "data": {"recalls_sha256_full": "r", "eval_sha256": "e", "causes_sha256": "c"},
        "code": {"dirty": False, "script_sha256": SCRIPTS},
        "model": "m",
        "embedding": {"fastembed": "0.9.0", "model_fingerprint": "f", "cache_verified": True},
        "top": 20,
    }
    return {**base, **kw}


def test_candidate_files_must_share_data_code_and_model():
    ts.check_same_build([_cand("main"), _cand("r1")])  # 같으면 통과
    # 캐시가 있었는지(cache_verified)만 다르면 같은 계산이다 — 막지 않는다
    ts.check_same_build(
        [
            _cand("main"),
            _cand(
                "r1",
                embedding={"fastembed": "0.9.0", "model_fingerprint": "f", "cache_verified": False},
            ),
        ]
    )
    with pytest.raises(SystemExit, match="r2"):  # 세 번째 파일만 달라도 잡는다
        ts.check_same_build([_cand("main"), _cand("r1"), _cand("r2", model="other")])
    for change in (
        {"data": {"recalls_sha256_full": "other"}},
        {"code": {"dirty": False, "script_sha256": {**SCRIPTS, CODE_FILES[0]: "other"}}},
        {"model": "other"},
        {"top": 30},
        {"embedding": {"fastembed": "0.9.0", "model_fingerprint": "other", "cache_verified": True}},
    ):
        with pytest.raises(SystemExit, match="같은 데이터"):
            ts.check_same_build([_cand("main"), _cand("r1", **change)])
    with pytest.raises(SystemExit, match="같은 데이터"):
        ts.check_same_build(
            [{"set": "main"}, {"set": "r1"}]
        )  # 판본 정보 없는 파일끼리는 합치지 않는다


def test_dirty_candidates_are_refused_unless_partial():
    dirty = _cand("main", code={"dirty": True, "script_sha256": SCRIPTS})
    with pytest.raises(SystemExit, match="커밋하지 않은"):
        ts.check_same_build([dirty])
    ts.check_same_build([dirty], partial=True)


def test_cli_score_refuses_candidate_files_from_different_builds(tmp_path):
    files = []
    for name, model, action in (
        ("candidates_main.json", "m", "PE1"),
        ("candidates_r1.json", "other", "PE2"),
    ):
        p = tmp_path / name
        p.write_text(
            json.dumps(
                {**_cand(name[11:-5], model=model), "items": items((action, {"A": {"bm25": 1}}))}
            ),
            encoding="utf-8",
        )
        files.append(str(p))
    sheet = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes"), row("PE2", "A", "no")])
    with pytest.raises(SystemExit, match="같은 데이터"):
        ts.main(["score", *_pilot_pass(tmp_path), "--candidates", *files, "--sheets", str(sheet)])


def _cand_file(tmp_path, name, set_name, action, **kw):
    p = tmp_path / name
    p.write_text(
        json.dumps({**_cand(set_name, **kw), "items": items((action, {"A": {"bm25": 1}}))}),
        encoding="utf-8",
    )
    return str(p)


def test_cli_score_refuses_dirty_candidates_unless_partial(tmp_path, capsys):
    """--partial이 실행 명령에서 check_same_build로 전달되는지(연결부) — 정식 채점은 dirty 후보를 거부한다."""
    dirty = {"code": {"dirty": True, "script_sha256": SCRIPTS}}
    cand = _cand_file(tmp_path, "candidates_main.json", "main", "PE1", **dirty)
    sheet = write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes")])
    with pytest.raises(SystemExit, match="커밋하지 않은"):
        ts.main(["score", *_pilot_pass(tmp_path), "--candidates", cand, "--sheets", str(sheet)])
    ts.main(
        ["score", *_pilot_pass(tmp_path), "--candidates", cand, "--sheets", str(sheet), "--partial"]
    )
    capsys.readouterr()


def test_cli_partial_score_hides_direction(tmp_path, capsys):
    """--partial로 표시 안 끝난 문항을 빼면, 34문항 이상·6:0이어도 outcome은 "미측정(중간 결과)"(연결부)."""
    pool = {f"PE{i}": {"A": {"bm25": 1, "b_rrf": 1}} for i in range(34)}
    pool.update({f"PB{i}": {"A": {"b_rrf": 1}} for i in range(6)})
    pool["PX"] = {"A": {"bm25": 1}}
    p = tmp_path / "candidates_main.json"
    p.write_text(json.dumps({**_cand("main"), "items": items(*pool.items())}), encoding="utf-8")
    rows = [row(a, "A", "yes") for a in pool if a != "PX"] + [row("PX", "A", "", labeler_id="")]
    sheet = write_sheet(tmp_path / "s.csv", rows)
    ts.main(
        [
            "score",
            *_pilot_pass(tmp_path),
            "--candidates",
            str(p),
            "--sheets",
            str(sheet),
            "--partial",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] == ["PX"] and out["hit@10_comparison"]["outcome"] == "미측정(중간 결과)"


def test_cli_agreement_uses_the_phase_and_questions_file(tmp_path, capsys):
    """--phase·--questions가 실행 명령에서 정해진 문항 집합으로 이어지는지(연결부)."""
    q = tmp_path / "questions.json"
    q.write_text(
        json.dumps(
            {
                "pilot": [{"action_no": a} for a in ("P1", "P2")],
                "main": [{"action_no": a} for a in ("M1", "M2", "M3", "M4")],
            }
        ),
        encoding="utf-8",
    )

    def sheets_missing_candidate():
        rows = [row(x, "A", "no") for x in ("M1", "M2", "M3")]
        rows_c = [row(x, "A", "no", labeler_id="L-C1") for x in ("M1", "M2", "M3")]
        return [
            str(write_sheet(tmp_path / "a2.csv", rows[:2] + [row("M3", "Z", "no")])),
            str(
                write_sheet(
                    tmp_path / "c2.csv", rows_c[:2] + [row("M3", "Z", "no", labeler_id="L-C1")]
                )
            ),
        ]

    def sheets(actions):
        a = write_sheet(tmp_path / "a.csv", [row(x, "A", "no") for x in actions])
        c = write_sheet(tmp_path / "c.csv", [row(x, "A", "no", labeler_id="L-C1") for x in actions])
        return [str(a), str(c)]

    cand = tmp_path / "candidates_main.json"  # 정해진 문항의 후보 목록과 시트를 대조한다
    cand.write_text(
        json.dumps(
            {
                "set": "main",
                "items": items(*((m, {"A": {"bm25": 1}}) for m in ("M1", "M2", "M3", "M4"))),
            }
        ),
        encoding="utf-8",
    )
    ts.main(
        [
            "agreement",
            "--phase",
            "recheck",
            "--questions",
            str(q),
            "--candidates",
            str(cand),
            "--sheets",
            *sheets(["M1", "M2", "M3"]),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["phase"] == "recheck" and out["questions"] == 3
    with pytest.raises(
        SystemExit, match="숨긴 후보 파일과 다르다"
    ):  # 후보 파일 대조가 실행 명령에 이어져 있다
        ts.main(
            [
                "agreement", "--phase", "recheck", "--questions", str(q), "--candidates", str(cand),
                "--sheets", *sheets_missing_candidate(),
            ]
        )  # fmt: skip
    with pytest.raises(SystemExit, match="정해진 문항"):
        ts.main(
            [
                "agreement",
                "--phase",
                "pilot",
                "--questions",
                str(q),
                "--candidates",
                str(cand),
                "--sheets",
                *sheets(["M1", "M2", "M3"]),
            ]
        )


def test_agreement_refuses_sheets_missing_candidates_from_the_hidden_file():
    """두 시트에서 같은 후보 줄이 함께 빠져도(스프레드시트 필터 등) 숨긴 후보 파일과 대조해 멈춘다(PR #72 Codex)."""
    a = [row("PE1", "A", "no", labeler_id="L-A1")]
    c = [row("PE1", "A", "no", labeler_id="L-C1")]
    pool = ts.pool_keys(items(("PE1", {"A": {"bm25": 1}, "B": {"bm25": 2}})), {"PE1"})
    with pytest.raises(SystemExit, match="숨긴 후보 파일과 다르다"):
        ts.agreement(a, c, expected={"PE1"}, candidates=pool)
    full = [row("PE1", "A", "no", labeler_id="L-A1"), row("PE1", "B", "no", labeler_id="L-A1")]
    full_c = [row("PE1", "A", "no", labeler_id="L-C1"), row("PE1", "B", "no", labeler_id="L-C1")]
    assert ts.agreement(full, full_c, expected={"PE1"}, candidates=pool)["pass"] is True


def test_rechecked_questions_need_two_labelers_and_agreed_label_on_every_candidate(tmp_path):
    """재확인을 했다면 그 문항은 두 사람 표시 + 합의값으로만 채점 — 한 사람 시트만 넘기거나 합의값을 빠뜨리면 멈춘다(PR #72 Codex)."""
    one = write_sheet(tmp_path / "a.csv", [row("R1", "A", "yes")])
    with pytest.raises(SystemExit, match="두 사람의 label 또는 agreed_label"):
        ts.check_rechecked(ts.merge_labels([ts.read_sheet(one)]), {"R1"})
    a = write_sheet(tmp_path / "a2.csv", [row("R1", "A", "yes")])
    c = write_sheet(tmp_path / "c2.csv", [row("R1", "A", "yes", labeler_id="L-C1")])
    with pytest.raises(
        SystemExit, match="agreed_label"
    ):  # 두 사람이 같게 표시했어도 합의값이 없으면
        ts.check_rechecked(ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)]), {"R1"})
    c_ok = write_sheet(
        tmp_path / "c3.csv", [row("R1", "A", "yes", labeler_id="L-C1", agreed_label="yes")]
    )
    with pytest.raises(
        SystemExit, match="한 사람 시트에만"
    ):  # 합의값이 C 시트에만(PR #72 Codex 38dd135)
        ts.check_rechecked(ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c_ok)]), {"R1"})
    a_ok = write_sheet(tmp_path / "a3.csv", [row("R1", "A", "yes", agreed_label="yes")])
    ts.check_rechecked(ts.merge_labels([ts.read_sheet(a_ok), ts.read_sheet(c_ok)]), {"R1"})
    with pytest.raises(SystemExit, match="시트에 없다"):
        ts.check_rechecked(ts.merge_labels([ts.read_sheet(a)]), {"R1", "R2"})


def _recheck_setup(tmp_path, agreed=()):
    """질문 파일 main 앞 3문항(R1~R3) + 그 밖의 Q4, 모두 한 사람(L-A1) 표시. agreed: A 시트에도 합의값(yes)을 적을 문항."""
    q = tmp_path / "questions.json"
    q.write_text(
        json.dumps({"pilot": [], "main": [{"action_no": a} for a in ("R1", "R2", "R3", "Q4")]}),
        encoding="utf-8",
    )
    p = tmp_path / "candidates_main.json"
    acts = ("R1", "R2", "R3", "Q4")
    p.write_text(
        json.dumps({**_cand("main"), "items": items(*((r, {"A": {"bm25": 1}}) for r in acts))}),
        encoding="utf-8",
    )
    sheet = write_sheet(
        tmp_path / "s.csv",
        [row(r, "A", "yes", agreed_label="yes" if r in agreed else "") for r in acts],
    )
    return q, ["score", "--candidates", str(p), "--questions", str(q), "--sheets", str(sheet)]


def test_cli_score_takes_double_label_scope_from_agreement_results(tmp_path, capsys):
    """이중 표시 범위를 옵션이 아니라 agreement 결과의 phase·pass로 정한다(안내서 4절, PR #72 Codex 7301978)."""
    q, args = _recheck_setup(tmp_path)
    pilot_ok = agreement_file(tmp_path, "pilot", True, q, "p_ok.json")
    pilot_bad = agreement_file(tmp_path, "pilot", False, q, "p_bad.json")
    recheck_ok = agreement_file(
        tmp_path, "recheck", True, q, "r_ok.json", cand=tmp_path / "candidates_main.json"
    )
    recheck_bad = agreement_file(
        tmp_path, "recheck", False, q, "r_bad.json", cand=tmp_path / "candidates_main.json"
    )
    ts.main([*args, "--agreement", pilot_ok])  # 예비 합격 — 한 사람 표시로 채점
    checks = json.loads(capsys.readouterr().out)["checks"]
    assert checks["double_label_scope"].startswith("없음") and checks["agreements"][0]["pass"]
    with pytest.raises(SystemExit, match="재확인 3문항 agreement 결과"):
        ts.main([*args, "--agreement", pilot_bad])  # 예비 미달인데 재확인 결과를 빠뜨림
    with pytest.raises(SystemExit, match="두 사람의 label 또는 agreed_label"):
        ts.main([*args, "--agreement", pilot_bad, recheck_ok])  # R1~R3이 한 사람 표시
    with pytest.raises(SystemExit, match="두 사람의 label 또는 agreed_label"):
        ts.main([*args, "--agreement", pilot_bad, recheck_bad])  # 전 문항이 한 사람 표시
    with pytest.raises(SystemExit, match="예비가 합격인데"):
        ts.main([*args, "--agreement", pilot_ok, recheck_ok])
    with pytest.raises(SystemExit, match="예비\\(pilot\\) 하나"):
        ts.main([*args, "--agreement", recheck_ok])
    other_q = tmp_path / "other_questions.json"
    other_q.write_text(json.dumps({"pilot": [], "main": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="이 질문 파일"):
        ts.main([*args, "--agreement", agreement_file(tmp_path, "pilot", True, other_q, "x.json")])
    no_phase = tmp_path / "no_phase.json"
    no_phase.write_text(json.dumps({"pass": True}), encoding="utf-8")
    with pytest.raises(SystemExit, match="phase"):
        ts.main([*args, "--agreement", str(no_phase)])


def test_cli_score_recheck_scope_needs_two_people_only_on_recheck_questions(tmp_path, capsys):
    q, args = _recheck_setup(tmp_path, agreed=("R1", "R2", "R3"))
    c = write_sheet(
        tmp_path / "c.csv",
        [row(r, "A", "yes", labeler_id="L-C1", agreed_label="yes") for r in ("R1", "R2", "R3")],
    )
    agr = [
        agreement_file(tmp_path, "pilot", False, q),
        agreement_file(tmp_path, "recheck", True, q, cand=tmp_path / "candidates_main.json"),
    ]
    ts.main([*args, str(c), "--agreement", *agr])  # Q4는 한 사람 표시여도 된다
    out = json.loads(capsys.readouterr().out)
    assert out["labeled_questions"] == 4 and out["checks"]["double_label_scope"].startswith(
        "재확인 3문항"
    )


def test_cli_partial_with_dirty_candidates_is_interim_even_without_skipped(tmp_path, capsys):
    """--partial로 dirty 후보를 쓰면 빠진 문항이 없어도 중간 결과 — status·outcome이 정식 결과처럼 보이지 않는다(리뷰 cd39286)."""
    pool = {f"PE{i}": {"A": {"bm25": 1, "b_rrf": 1}} for i in range(34)}
    pool.update({f"PB{i}": {"A": {"b_rrf": 1}} for i in range(6)})
    p = tmp_path / "candidates_main.json"
    dirty = {"code": {"dirty": True, "script_sha256": SCRIPTS}}
    p.write_text(
        json.dumps({**_cand("main", **dirty), "items": items(*pool.items())}), encoding="utf-8"
    )
    sheet = write_sheet(tmp_path / "s.csv", [row(a, "A", "yes") for a in pool])
    ts.main(
        [
            "score",
            *_pilot_pass(tmp_path),
            "--candidates",
            str(p),
            "--sheets",
            str(sheet),
            "--partial",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["status"].startswith("중간 결과") and "커밋하지 않은" in out["status"]
    assert out["hit@10_comparison"]["outcome"] == "미측정(중간 결과)"


def test_double_label_check_needs_a_note_when_the_two_labels_differed(tmp_path):
    """두 사람 표시가 달랐던 후보는 합의 이유(note)가 있어야 한다(안내서 4절, PR #72 Codex 7301978)."""
    a = write_sheet(tmp_path / "a.csv", [row("R1", "A", "yes", agreed_label="no")])
    c = write_sheet(
        tmp_path / "c.csv", [row("R1", "A", "no", labeler_id="L-C1", agreed_label="no")]
    )
    with pytest.raises(SystemExit, match="합의 이유"):
        ts.check_rechecked(ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)]), {"R1"})
    a_note = write_sheet(
        tmp_path / "a2.csv",
        [row("R1", "A", "yes", agreed_label="no", note="생산 기간이 겹치지 않음")],
    )
    ts.check_rechecked(ts.merge_labels([ts.read_sheet(a_note), ts.read_sheet(c)]), {"R1"})


def test_no_answer_reasons_are_reported_separately(tmp_path):
    """정답 없음 사유 세 칸: 모두 unsure(메모 없음) / 모두 no / no+unsure — 섞이지 않는다(리뷰 2da97c4)."""
    cand = items(*((q, {"A": {"bm25": 1}, "B": {"bm25": 2}}) for q in ("Q1", "Q2", "Q3")))
    s = write_sheet(
        tmp_path / "s.csv",
        [
            row("Q1", "A", "unsure"), row("Q1", "B", "unsure"),
            row("Q2", "A", "no"), row("Q2", "B", "no"),
            row("Q3", "A", "no"), row("Q3", "B", "unsure"),
        ],
    )  # fmt: skip
    qs, _ = ts.per_question(ts.merge_labels([ts.read_sheet(s)]), cand, partial=False)
    assert ts.summarize(qs)["no_answer"] == {
        ts.NO_PART: 0,
        ts.UNSURE_ONLY: 1,
        "후보에 선례 없음": 2,
    }


def test_bm25_higher_direction_uses_hit_at_10():
    """BM25만 7위로 맞히는 문항 6개 — BM25 쪽도 Hit@10 기준으로 센다(리뷰 2da97c4 🟢2)."""
    qs = [_q(True, True)] * 34 + [_qr(7, None)] * 6
    cmp = ts.summarize(qs)["hit@10_comparison"]
    assert (cmp["b_only"], cmp["bm25_only"]) == (0, 6) and cmp[
        "outcome"
    ] == "차이 있음 — BM25가 높음"


def test_cli_score_failed_recheck_requires_every_question_from_two_people(tmp_path, capsys):
    """재확인도 미달하면 본 평가 전체를 두 사람이 표시한다(안내서 4절 3항) — 한 문항이라도 한 사람 표시면 멈춘다(PR #72 Codex)."""
    q, args = _recheck_setup(tmp_path, agreed=("R1", "R2", "R3"))
    acts = ("R1", "R2", "R3", "Q4")
    agr = [
        agreement_file(tmp_path, "pilot", False, q),
        agreement_file(tmp_path, "recheck", False, q, cand=tmp_path / "candidates_main.json"),
    ]
    c_part = write_sheet(
        tmp_path / "c.csv",
        [row(r, "A", "yes", labeler_id="L-C1", agreed_label="yes") for r in acts[:3]],
    )
    with pytest.raises(SystemExit, match="본 평가 전 문항"):  # Q4가 한 사람 표시
        ts.main([*args, str(c_part), "--agreement", *agr])
    c_all = write_sheet(
        tmp_path / "c2.csv",
        [row(r, "A", "yes", labeler_id="L-C1", agreed_label="yes") for r in acts],
    )
    q, args = _recheck_setup(tmp_path, agreed=acts)  # A 시트에도 전 문항 합의값
    ts.main([*args, str(c_all), "--agreement", *agr])
    out = json.loads(capsys.readouterr().out)
    assert out["labeled_questions"] == 4 and out["checks"]["double_label_scope"].startswith(
        "본 평가"
    )


def test_cli_agreement_records_candidates_and_questions_files(tmp_path, capsys):
    q = tmp_path / "questions.json"
    q.write_text(json.dumps({"pilot": [{"action_no": "P1"}], "main": []}), encoding="utf-8")
    cand = tmp_path / "candidates_pilot.json"
    cand.write_text(
        json.dumps({**_cand("pilot"), "items": items(("P1", {"A": {"bm25": 1}}))}), encoding="utf-8"
    )
    a = write_sheet(tmp_path / "a.csv", [row("P1", "A", "no")])
    c = write_sheet(tmp_path / "c.csv", [row("P1", "A", "no", labeler_id="L-C1")])
    ts.main(
        [
            "agreement",
            "--phase",
            "pilot",
            "--questions",
            str(q),
            "--candidates",
            str(cand),
            "--sheets",
            str(a),
            str(c),
        ]
    )
    out = json.loads(capsys.readouterr().out)["inputs"]
    assert out["candidates"]["set"] == "pilot" and len(out["candidates"]["sha256"]) == 64
    assert {"data", "model", "top", "embedding", "code"} <= set(
        out["candidates"]
    )  # score가 판본을 대조한다
    assert len(out["questions"]["sha256"]) == 64 and len(out["sheets"]) == 2


def test_agreement_reports_whether_one_sided_yes_was_resolved():
    """합격해도 한 사람만 yes인 후보는 두 시트의 같은 agreed_label + 합의 이유(note)가 있어야 해소(안내서 4절 2항, PR #72 Codex 110cf87)."""
    keys = [("PE1", f"C{i}") for i in range(5)]
    a = dict.fromkeys(keys, "unsure")
    a[("PE1", "C0")] = "yes"
    c = {
        **a,
        ("PE1", "C0"): "unsure",
        ("PE1", "C1"): "yes",
    }  # 둘 다 정답 있음이지만 다른 후보를 yes로
    rows_a, rows_c = _agree_rows("L-A1", a), _agree_rows("L-C1", c)
    out = ts.agreement(rows_a, rows_c, expected={"PE1"})
    assert out["resolution_complete"] is False
    assert out["unresolved_one_sided_yes"] == [["PE1", "C0"], ["PE1", "C1"]]
    for r in [*rows_a, *rows_c]:
        if r["campno"] in ("C0", "C1"):
            r["agreed_label"] = "yes"
    assert (
        ts.agreement(rows_a, rows_c, expected={"PE1"})["resolution_complete"] is False
    )  # 이유 없음
    rows_a[0]["note"] = "같은 부품·같은 원인 서술"
    rows_a[1]["note"] = "같은 부품"
    out = ts.agreement(rows_a, rows_c, expected={"PE1"})
    assert out["resolution_complete"] is True and out["unresolved_one_sided_yes"] == []
    typo = [dict(r, agreed_label="yse") if r["campno"] == "C0" else r for r in rows_a]
    typo_c = [dict(r, agreed_label="yse") if r["campno"] == "C0" else r for r in rows_c]
    assert ts.agreement(typo, typo_c, expected={"PE1"})["resolution_complete"] is False  # 오타
    one_sheet = [dict(r, agreed_label="") if r["campno"] == "C0" else r for r in rows_c]
    assert (
        ts.agreement(rows_a, one_sheet, expected={"PE1"})["resolution_complete"] is False
    )  # 한 시트에만 합의값
    rows_c[1]["agreed_label"] = "no"  # 두 시트의 합의값이 다르면 해소 아님
    assert ts.agreement(rows_a, rows_c, expected={"PE1"})["resolution_complete"] is False


def test_cli_score_refuses_pilot_pass_with_unresolved_one_sided_yes(tmp_path):
    q, args = _recheck_setup(tmp_path)
    unresolved = agreement_file(
        tmp_path,
        "pilot",
        True,
        q,
        "p.json",
        resolution_complete=False,
        unresolved_one_sided_yes=[["PE1", "C0"]],
    )
    with pytest.raises(SystemExit, match="합의로 해소되지 않았다"):
        ts.main([*args, "--agreement", unresolved])
    old = tmp_path / "old.json"  # 해소 여부를 기록하지 않은 옛 결과도 받지 않는다
    d = json.loads(Path(agreement_file(tmp_path, "pilot", True, q, "o.json")).read_text("utf-8"))
    del d["resolution_complete"]
    old.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SystemExit, match="합의로 해소되지 않았다"):
        ts.main([*args, "--agreement", str(old)])


def test_cli_score_refuses_agreement_from_another_candidate_build(tmp_path):
    """다른 데이터·스크립트·모델로 만든 후보의 agreement 결과는 받지 않는다(DEC-037 ⑦(c), PR #72 Codex 110cf87)."""
    q, args = _recheck_setup(tmp_path)
    other_model = agreement_file(tmp_path, "pilot", True, q, "m.json")
    d = json.loads(Path(other_model).read_text("utf-8"))
    d["inputs"]["candidates"]["model"] = "m2"
    Path(other_model).write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SystemExit, match=r"후보 판본.*model"):
        ts.main([*args, "--agreement", other_model])
    d["inputs"].pop("candidates")  # 판본 정보가 없는 결과
    Path(other_model).write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SystemExit, match="후보 판본"):
        ts.main([*args, "--agreement", other_model])
    # 재확인 결과는 지금 채점하는 본 평가 후보 파일 그 자체로 만든 것이어야 한다
    elsewhere = tmp_path / "candidates_other.json"
    elsewhere.write_text(json.dumps({**_cand("main"), "items": []}), encoding="utf-8")
    agr = [
        agreement_file(tmp_path, "pilot", False, q),
        agreement_file(tmp_path, "recheck", True, q, cand=elsewhere),
    ]
    with pytest.raises(SystemExit, match="본 평가 후보 파일로 만든 것이 아니다"):
        ts.main([*args, "--agreement", *agr])


def test_cli_score_refuses_recheck_pass_with_unresolved_one_sided_yes(tmp_path):
    """재확인이 합격해도 한 사람만 yes인 후보가 미해소면 본 평가를 나눈 근거가 되지 않는다(PR #72 Codex f755b62)."""
    q, args = _recheck_setup(tmp_path, agreed=("R1", "R2", "R3"))
    cand = tmp_path / "candidates_main.json"
    c = write_sheet(
        tmp_path / "c.csv",
        [row(r, "A", "yes", labeler_id="L-C1", agreed_label="yes") for r in ("R1", "R2", "R3")],
    )
    pilot_bad = agreement_file(tmp_path, "pilot", False, q)
    unresolved = agreement_file(
        tmp_path, "recheck", True, q, "r.json", cand=cand, resolution_complete=False
    )
    with pytest.raises(SystemExit, match="재확인 결과가 합격했지만"):
        ts.main([*args, str(c), "--agreement", pilot_bad, unresolved])
    resolved = agreement_file(tmp_path, "recheck", True, q, "r2.json", cand=cand)
    ts.main([*args, str(c), "--agreement", pilot_bad, resolved])


def test_cli_score_refuses_recheck_sheets_with_agreed_label_on_one_side_only(tmp_path):
    """재확인 합격 결과는 정상이어도 채점 시트 한쪽에만 합의값이 있으면 공식 점수를 내지 않는다(PR #72 Codex 38dd135)."""
    q, args = _recheck_setup(tmp_path)  # A 시트에는 합의값 없음
    c = write_sheet(
        tmp_path / "c.csv",
        [row(r, "A", "yes", labeler_id="L-C1", agreed_label="yes") for r in ("R1", "R2", "R3")],
    )
    agr = [
        agreement_file(tmp_path, "pilot", False, q),
        agreement_file(tmp_path, "recheck", True, q, cand=tmp_path / "candidates_main.json"),
    ]
    with pytest.raises(SystemExit, match="한 사람 시트에만"):
        ts.main([*args, str(c), "--agreement", *agr])


@pytest.fixture
def dec066(monkeypatch):
    """합성 질문 파일의 재확인 3문항(R1~R3)을 DEC-066 고정 집합으로 본다 — 실제 고정 집합은 따로 시험한다."""
    monkeypatch.setattr(ts, "DEC066_RECHECK", frozenset({"R1", "R2", "R3"}))


def _dec066_files(tmp_path, a_rows, c_rows, a_extra=None, c_extra=None):
    """DEC-066 회차: 재확인 R1~R3은 A(L-A1)·C(L-C1) 둘 다, Q4는 A 한 사람. 후보 파일에 질문 파일 해시를 넣는다."""
    q, base = _recheck_setup(tmp_path)
    cand = tmp_path / "candidates_main.json"
    meta = json.loads(cand.read_text(encoding="utf-8"))
    cand.write_text(json.dumps({**meta, "questions_sha256": ts.sha256_of(q)}), encoding="utf-8")
    a = write_sheet(tmp_path / "a066.csv", [*a_rows, *(a_extra or [row("Q4", "A", "yes")])])
    c = write_sheet(
        tmp_path / "c066.csv", [{**r, "labeler_id": "L-C1"} for r in [*c_rows, *(c_extra or [])]]
    )
    head = base[: base.index("--sheets")]
    return q, cand, [*head, "--sheets", str(a), str(c), "--pilot-agreement-skipped", "DEC-066"]


def _dec066_args(tmp_path, a_rows, c_rows, **kw):
    return _dec066_files(tmp_path, a_rows, c_rows, **kw)[2]


def test_cli_score_dec066_same_labels_need_no_agreed_label(tmp_path, capsys, dec066):
    """DEC-066: 재확인 3문항에서 두 사람의 label이 같으면 agreed_label 없이 그 label을 쓴다 — 일치율 미측정을 남긴다."""
    same = [row(r, "A", "yes") for r in ("R1", "R2", "R3")]
    q, _, args = _dec066_files(tmp_path, same, same)
    ts.main(args)
    out = json.loads(capsys.readouterr().out)
    checks = out["checks"]
    assert checks["double_label_scope"] == ts.DEC066_SCOPE and checks["agreements"] == []
    assert (
        checks["pilot_agreement"] == "미측정(DEC-066)" and checks["recheck_split_candidates"] == 0
    )
    assert out["limitations"] == [ts.DEC066_LIMIT.format(n=0)] and out["labeled_questions"] == 4
    assert out["inputs"]["questions"]["sha256"] == ts.sha256_of(q)


def test_cli_score_dec066_split_candidate_needs_agreed_label_on_both_sheets_and_a_reason(
    tmp_path, capsys, dec066
):
    """갈린 후보는 합의값(우지훈 결정)이 두 시트 모두에 같게, 결정 메모와 정확히 같은 note와 함께 있어야 한다(DEC-066 ③)."""
    a_rows = [row("R1", "A", "yes"), row("R2", "A", "yes"), row("R3", "A", "yes")]
    c_rows = [row("R1", "A", "no"), row("R2", "A", "yes"), row("R3", "A", "yes")]
    with pytest.raises(SystemExit, match="표시가 서로 다르다"):
        ts.main(_dec066_args(tmp_path, a_rows, c_rows))
    one_side = [row("R1", "A", "no", agreed_label="yes", note=ts.DEC066_NOTE), *c_rows[1:]]
    with pytest.raises(SystemExit, match="한 사람 시트에만"):
        ts.main(_dec066_args(tmp_path, a_rows, one_side))
    a_ok = [row("R1", "A", "yes", agreed_label="yes"), *a_rows[1:]]
    for bad_note in (
        "",
        "생산 기간이 겹침",
        ts.DEC066_NOTE + " 대기",
    ):  # 일반 메모·덧붙인 문구는 결정 기록이 아니다
        bad = [row("R1", "A", "no", agreed_label="yes", note=bad_note), *c_rows[1:]]
        with pytest.raises(SystemExit, match="합의 이유"):
            ts.main(_dec066_args(tmp_path, a_ok, bad))
    ts.main(_dec066_args(tmp_path, a_ok, one_side))
    out = json.loads(capsys.readouterr().out)
    assert out["checks"]["recheck_split_candidates"] == 1 and out["answered"] == 4
    assert out["limitations"] == [ts.DEC066_LIMIT.format(n=1)]
    # 합의값이 점수에 실제로 쓰인다 — 갈린 R1을 no로 정하면 정답 있는 문항이 하나 준다
    a_no = [row("R1", "A", "yes", agreed_label="no"), *a_rows[1:]]
    c_no = [row("R1", "A", "no", agreed_label="no", note=ts.DEC066_NOTE), *c_rows[1:]]
    ts.main(_dec066_args(tmp_path, a_no, c_no))
    assert json.loads(capsys.readouterr().out)["answered"] == 3


def test_cli_score_dec066_recheck_questions_need_two_labelers(tmp_path, dec066):
    """재확인 문항을 한 사람만 표시했으면 멈춘다(DEC-066 ②) — 시트에 아예 없어도 멈춘다."""
    same = [row(r, "A", "yes") for r in ("R1", "R2", "R3")]
    with pytest.raises(SystemExit, match="두 사람의 label이 없다"):
        ts.main(_dec066_args(tmp_path, same, same[:2]))


def test_cli_score_dec066_refuses_agreed_label_on_matching_labels(tmp_path, dec066):
    """두 사람의 label이 같은 후보에는 합의값을 적지 않는다 — 같은 값이어도 멈춘다(DEC-066 ③, 예전 절차 시트 거르기)."""
    for agreed in ("no", "yes"):
        rows = [
            row("R1", "A", "yes", agreed_label=agreed),
            row("R2", "A", "yes"),
            row("R3", "A", "yes"),
        ]
        with pytest.raises(SystemExit, match="합의값은 갈린 후보에만"):
            ts.main(_dec066_args(tmp_path, rows, rows))


def test_cli_score_dec066_refuses_agreed_label_or_two_labelers_outside_recheck(tmp_path, dec066):
    """재확인 3문항 밖은 한 사람만 — 한쪽에 합의값을 적거나, 둘이 같은 값으로 표시해도 멈춘다(DEC-066 ②)."""
    same = [row(r, "A", "yes") for r in ("R1", "R2", "R3")]
    with pytest.raises(SystemExit, match="재확인 3문항 밖"):
        ts.main(
            _dec066_args(
                tmp_path,
                same,
                same,
                a_extra=[row("Q4", "A", "yes", agreed_label="no")],
                c_extra=[row("Q4", "A", "no")],
            )
        )
    with pytest.raises(SystemExit, match="두 사람 이상이 표시"):
        ts.main(_dec066_args(tmp_path, same, same, c_extra=[row("Q4", "A", "yes")]))


def test_cli_score_dec066_checks_fixed_recheck_set_and_questions_file(tmp_path, dec066):
    """재확인 범위는 DEC-066 고정 3문항이고 질문 파일은 후보를 만든 그 파일이어야 한다(AGENTS.md 2-4)."""
    same = [row(r, "A", "yes") for r in ("R1", "R2", "R3")]
    q, _, args = _dec066_files(tmp_path, same, same)
    main_rows = [
        {"action_no": a} for a in ("Q4", "R1", "R2", "R3")
    ]  # 같은 문항, 순서만 바뀐 질문 파일
    q.write_text(json.dumps({"pilot": [], "main": main_rows}), encoding="utf-8")
    with pytest.raises(SystemExit, match="DEC-066 재확인 3문항"):
        ts.main(args)
    main_rows = [{"action_no": a} for a in ("R1", "R2", "R3", "Q4")]
    q.write_text(json.dumps({"pilot": [], "main": main_rows}) + "\n", encoding="utf-8")
    with pytest.raises(
        SystemExit, match="questions_sha256"
    ):  # 범위는 같지만 후보를 만든 파일과 다르다
        ts.main(args)


def test_dec066_recheck_set_matches_the_committed_questions_file():
    """고정 3문항은 커밋된 질문 파일의 main 앞 3문항과 같다(안내서 4절)."""
    assert ts.phase_actions("recheck") == ts.DEC066_RECHECK == {"PE12017", "PE11022", "PE18009"}


def test_cli_score_needs_exactly_one_of_agreement_or_dec066(tmp_path, dec066):
    """--agreement와 --pilot-agreement-skipped는 하나만 — 둘 다 없거나 둘 다 주면 멈춘다. 사유 값은 DEC-066만 받는다."""
    same = [row(r, "A", "yes") for r in ("R1", "R2", "R3")]
    args = _dec066_args(tmp_path, same, same)
    without = args[: args.index("--pilot-agreement-skipped")]
    with pytest.raises(SystemExit):
        ts.main(without)
    with pytest.raises(SystemExit):
        ts.main([*args, "--agreement", agreement_file(tmp_path, "pilot", True)])
    with pytest.raises(SystemExit):
        ts.main([*without, "--pilot-agreement-skipped", "other"])


def test_cli_score_dec066_accepts_replacement_round_built_from_an_updated_questions_file(
    tmp_path, capsys, dec066
):
    """대체 회차 후보는 질문 파일을 갱신해 만들어져 해시가 다르다 — 본 회차(main) 후보만 --questions와 대조한다(DEC-037 ⑦(b)(c))."""
    same = [row(r, "A", "yes") for r in ("R1", "R2", "R3")]
    extra = [row("Q4", "A", "yes"), row("X1", "A", "yes")]
    _, _, args = _dec066_files(tmp_path, same, same, a_extra=extra)
    alt = tmp_path / "candidates_alt1.json"
    alt_items = items(("X1", {"A": {"bm25": 1}}))
    alt.write_text(
        json.dumps({**_cand("alt1"), "questions_sha256": "갱신본", "items": alt_items}),
        encoding="utf-8",
    )
    i = args.index("--questions")
    ts.main([*args[:i], str(alt), *args[i:]])  # --candidates main alt1
    assert json.loads(capsys.readouterr().out)["labeled_questions"] == 5
    cand = tmp_path / "candidates_main.json"
    meta = json.loads(cand.read_text(encoding="utf-8"))
    cand.write_text(json.dumps({**meta, "set": "alt0"}), encoding="utf-8")
    with pytest.raises(
        SystemExit, match="main 후보가 없다"
    ):  # 본 회차(main) 후보가 없으면 대조할 판본이 없다
        ts.main([*args[:i], str(alt), *args[i:]])


# 아래는 이슈 #77(PR #72 리뷰 후속) 시험 — 규칙은 그대로이고 거부 조건을 고정한다.


def test_score_refuses_a_sheet_with_extra_lines_the_candidates_do_not_have(tmp_path):
    """시트에 후보 파일에 없는 줄이 더 있어도 멈춘다 — 빠진 줄(시트에 없음)과 따로 센다(`check_against_candidates`)."""
    cand = items(("PE1", {"A": {"bm25": 1}}))
    extra = ts.merge_labels(
        [
            ts.read_sheet(
                write_sheet(tmp_path / "s.csv", [row("PE1", "A", "yes"), row("PE1", "B", "no")])
            )
        ]
    )
    with pytest.raises(SystemExit, match=r"시트에 없음 0개.*후보 파일에 없음 1개"):
        ts.check_against_candidates(extra, cand)


def test_candidate_files_need_build_info_present_not_just_equal():
    """같아 보여도 비교할 값이 없으면 거부한다 — 임베딩 판본·모델 지문·스크립트 해시·데이터·모델·상위 개수(DEC-037 ⑦(c))."""
    with pytest.raises(SystemExit, match=r"embedding\.fastembed"):  # fastembed 판본만 다르다
        ts.check_same_build(
            [
                _cand("main"),
                _cand("r1", embedding={"fastembed": "9.9.9", "model_fingerprint": "f"}),
            ]
        )
    with pytest.raises(SystemExit, match=r"embedding\.model_fingerprint"):  # 모델 지문만 다르다
        ts.check_same_build(
            [
                _cand("main"),
                _cand("r1", embedding={"fastembed": "0.9.0", "model_fingerprint": "other"}),
            ]
        )
    for emb in ({}, None):  # 둘 다 임베딩 정보가 없다 — 서로 같지만 비교할 수 없다
        with pytest.raises(SystemExit, match=r"embedding\.fastembed"):
            ts.check_same_build([_cand("main", embedding=emb), _cand("r1", embedding=emb)])
    no_script = {"code": {"dirty": False}}
    with pytest.raises(SystemExit, match=r"code\.script_sha256"):
        ts.check_same_build([_cand("main", **no_script), _cand("r1", **no_script)])
    for key in ts.SAME_BUILD_KEYS:  # 둘 다 이 칸이 아예 없다
        a, b = _cand("main"), _cand("r1")
        del a[key], b[key]
        with pytest.raises(SystemExit, match=rf"'{key}'"):
            ts.check_same_build([a, b])


def test_single_candidate_file_needs_build_info_unless_partial():
    """후보 파일이 하나뿐인 정식 채점도 판본 정보가 적힌 파일만 받는다(Codex 선택 개선, 이슈 #77)."""
    ts.check_same_build([_cand("main")])
    for broken in (
        {"set": "main"},
        {k: v for k, v in _cand("main").items() if k != "model"},
        _cand("main", embedding={}),
        _cand("main", code={"dirty": False}),
        # 칸만 있고 값이 비었거나 형식이 틀린 파일도 거부한다 — 어느 데이터·모델·코드로 만든 점수인지 알 수 없다
        _cand("main", data={}),
        _cand("main", data=None),
        _cand("main", model=None),
        _cand("main", model="  "),
        _cand("main", top=None),
        _cand("main", top=0),
        _cand("main", top=True),
        _cand("main", embedding={"fastembed": "", "model_fingerprint": "f"}),
        _cand("main", embedding={"fastembed": "0.9.0", "model_fingerprint": None}),
        _cand("main", code={"script_sha256": SCRIPTS}),  # dirty 칸 없음
        _cand("main", code={"dirty": 0, "script_sha256": SCRIPTS}),
        _cand("main", code={"dirty": False, "script_sha256": {}}),
        # 이름은 있지만 지문 값이 비었거나 SHA-256 형식이 아닌 파일도 거부한다
        _cand("main", data={"recalls_sha256_full": "", "eval_sha256": "e", "causes_sha256": "c"}),
        _cand("main", data={"recalls_sha256_full": "r", "eval_sha256": "e"}),  # 필수 지문 누락
        _cand("main", code={"dirty": False, "script_sha256": {**SCRIPTS, CODE_FILES[0]: ""}}),
        _cand(
            "main", code={"dirty": False, "script_sha256": {**SCRIPTS, CODE_FILES[0]: "not-a-sha"}}
        ),
        _cand("main", code={"dirty": False, "script_sha256": {**SCRIPTS, "y.py": None}}),
        _cand("main", code={"dirty": False, "script_sha256": None}),
    ):
        with pytest.raises(SystemExit, match="판본 정보가 없는"):
            ts.check_same_build([broken])
        ts.check_same_build([broken], partial=True)  # 중간 결과는 막지 않는다


def test_required_script_paths_are_the_three_scripts_the_candidate_builder_hashes():
    """채점 도구가 요구하는 스크립트 경로는 후보 생성기가 해시하는 세 파일과 같다 — 어느 쪽이 바뀌면 이 시험이 먼저 깨진다."""
    assert ts.CODE_FILES is CODE_FILES  # 한 곳(time_eval_candidates.CODE_FILES)에서 가져온다
    assert list(CODE_FILES) == [
        "scripts/defect_precedent/time_eval_candidates.py",
        "scripts/defect_precedent/retrieval_compare.py",
        "scripts/defect_precedent/bm25_baseline.py",
    ]
    assert all(
        (ROOT / f).is_file() for f in CODE_FILES
    )  # 실제 경로라서 후보 생성기가 해시할 수 있다


@pytest.mark.parametrize("missing", CODE_FILES)
def test_formal_scoring_refuses_a_candidate_file_missing_one_required_script(missing):
    """세 스크립트 중 하나라도 `code.script_sha256`에 없으면 정식 채점은 거부하고, 중간 결과(--partial)는 막지 않는다(이슈 #77)."""
    partial_scripts = {f: h for f, h in SCRIPTS.items() if f != missing}
    broken = _cand("main", code={"dirty": False, "script_sha256": partial_scripts})
    with pytest.raises(SystemExit, match=re.escape(f"code.script_sha256.{missing}")):
        ts.check_same_build([broken])
    # 두 파일이 서로 같아도(둘 다 같은 것이 빠져도) 통과시키지 않는다
    with pytest.raises(SystemExit, match="판본 정보가 없는"):
        ts.check_same_build(
            [broken, _cand("r1", code={"dirty": False, "script_sha256": partial_scripts})]
        )
    ts.check_same_build([broken], partial=True)


def test_candidate_files_pair_with_empty_build_info_is_refused_too():
    """두 파일이 같은 빈 판본 정보를 가져도 '같다'고 통과시키지 않는다."""
    empty = {
        "data": {},
        "model": None,
        "top": None,
    }  # 임베딩·코드 칸은 정상이라 두 파일이 서로 같다
    with pytest.raises(SystemExit, match="판본 정보가 없는"):
        ts.check_same_build([_cand("main", **empty), _cand("r1", **empty)])
    ts.check_same_build([_cand("main", **empty), _cand("r1", **empty)], partial=True)


def test_labeler_id_with_stray_spaces_is_still_one_person(tmp_path):
    """ "L-A1 "와 "L-A1"은 같은 사람이다 — 두 사람으로 세어져 합의·일치 검사를 통과하면 안 된다."""
    a = write_sheet(tmp_path / "a.csv", [row("PE1", "A", "yes", labeler_id="L-A1 ")])
    c = write_sheet(tmp_path / "c.csv", [row("PE1", "A", "yes", agreed_label="yes")])
    with pytest.raises(SystemExit, match="두 사람 이상"):
        ts.merge_labels([ts.read_sheet(a), ts.read_sheet(c)])
    with pytest.raises(SystemExit, match="labeler_id가 같다"):
        ts.agreement(
            [row("PE1", "A", "yes", labeler_id="L-A1 ")],
            [row("PE1", "A", "yes", labeler_id=" L-A1")],
            expected={"PE1"},
        )


def test_rechecked_agreed_label_on_the_first_sheet_only_is_refused_too(tmp_path):
    """반대 방향(A 시트에만 합의값, C 시트에는 없음)도 멈춘다 — 이슈 #77, PR #72 Codex 642daf5."""
    a_ok = write_sheet(tmp_path / "a.csv", [row("R1", "A", "yes", agreed_label="yes")])
    c = write_sheet(tmp_path / "c.csv", [row("R1", "A", "yes", labeler_id="L-C1")])
    with pytest.raises(SystemExit, match="한 사람 시트에만"):
        ts.check_rechecked(ts.merge_labels([ts.read_sheet(a_ok), ts.read_sheet(c)]), {"R1"})


def test_cli_score_refuses_recheck_result_without_resolution_complete(tmp_path):
    """재확인 결과에 `resolution_complete` 키가 없는 옛 결과도 받지 않는다 — 예비 결과의 같은 시험의 재확인판(이슈 #77)."""
    q, args = _recheck_setup(tmp_path, agreed=("R1", "R2", "R3"))
    c = write_sheet(
        tmp_path / "c.csv",
        [row(r, "A", "yes", labeler_id="L-C1", agreed_label="yes") for r in ("R1", "R2", "R3")],
    )
    pilot_bad = agreement_file(tmp_path, "pilot", False, q)
    old = Path(
        agreement_file(
            tmp_path, "recheck", True, q, "r_old.json", cand=tmp_path / "candidates_main.json"
        )
    )
    d = json.loads(old.read_text("utf-8"))
    del d["resolution_complete"]
    old.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SystemExit, match="재확인 결과가 합격했지만"):
        ts.main([*args, str(c), "--agreement", pilot_bad, str(old)])


def test_resolution_message_says_note_may_be_on_either_sheet():
    """합의 이유(note)는 두 시트 중 한 곳 이상이면 된다 — 안내 문구가 "두 시트 모두"로 읽히지 않는다(이슈 #77, PR #81 🟢1)."""
    with pytest.raises(SystemExit) as e:
        ts.require_resolved({"resolution_complete": False}, "예비")
    msg = str(e.value)
    assert (
        "두 시트 중 한 곳 이상" in msg and "두 시트 모두에 같은 agreed_label과 합의 이유" not in msg
    )

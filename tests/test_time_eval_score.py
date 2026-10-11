"""scripts/defect_precedent/time_eval_score.py — 시점 평가 채점 규칙(DEC-037 ⑦, 안내서 4·5절) 테스트.

실제 정답 표시는 쓰지 않는다(표시 전 고정). 작은 가짜 시트·후보 파일로 규칙만 시험한다.
"""

import csv
import json

import pytest

from scripts.defect_precedent import time_eval_score as ts

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
    merged = ts.merge_labels([ts.read_sheet(sheet)])
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


def test_verdict_needs_both_p_value_and_003_difference():
    def q(bm, b):
        return {"answered": True, "bm25": 1 if bm else None, "b_rrf": 1 if b else None}

    many = [q(True, True)] * 34
    out = ts.summarize(many + [q(False, True)] * 6)  # 6:0, n=40
    assert out["hit@10_comparison"]["verdict"] == "차이 있음 — B가 높음"
    out = ts.summarize(many + [q(False, True)] * 5)  # 5:0 — p ≥ 0.05
    assert out["hit@10_comparison"]["verdict"] == "우열 불확실"
    assert out["status"] == "측정"


def test_agreement_uses_raw_labels_and_lists_one_sided_yes(tmp_path):
    rows_a = [row("PE1", "A", "yes"), row("PE1", "B", "no"), row("PE2", "C", "no")]
    rows_b = [
        row("PE1", "A", "yes", labeler_id="L-C1"),
        row(
            "PE1", "B", "yes", labeler_id="L-C1", agreed_label="no"
        ),  # 합의 결과는 일치율에 쓰지 않는다
        row("PE2", "C", "no", labeler_id="L-C1"),
    ]
    out = ts.agreement(rows_a, rows_b)
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
    assert out["inputs"]["candidates"]["set"] == "main" and out["inputs"]["candidates_code"] == {
        "commit": "abc"
    }
    assert "근사 시점 평가" in out["note"]

import json

import pytest

from scripts.defect_precedent import time_eval_draw as td


def questions(n=80, start="20070101"):
    return [
        {
            "action_no": f"PE{i:05d}",
            "open_date": f"{int(start[:4]) + i % 15}0615",
            "question": "q",
            "gold_campnos": [],
        }
        for i in range(n)
    ]


def test_the_draw_is_deterministic_and_does_not_depend_on_input_order():
    qs = questions()
    assert td.draw(qs) == td.draw(list(reversed(qs)))
    assert td.draw(qs, seed=1) != td.draw(qs, seed=2)


def test_the_draw_splits_pilot_and_main_without_overlap():
    r = td.draw(questions())
    pilot = {row["action_no"] for row in r["pilot"]}
    main = {row["action_no"] for row in r["main"]}
    assert (len(pilot), len(main)) == (td.PILOT, td.MAIN)
    assert not pilot & main


def test_the_draw_only_takes_investigations_opened_since_the_cutoff():
    qs = questions(100) + [{"action_no": "PE99999", "open_date": "20061231"}]
    r = td.draw(qs)
    assert all(row["open_date"] >= td.CUTOFF for row in r["pilot"] + r["main"])
    assert "PE99999" not in {row["action_no"] for row in r["pilot"] + r["main"]}
    assert r["pool_size"] == 100


def test_the_draw_stops_when_the_pool_is_too_small():
    with pytest.raises(ValueError):
        td.draw(questions(td.PILOT + td.MAIN + td.RESERVE - 1))


def test_the_draw_result_never_carries_question_text_or_gold():
    r = td.draw(questions())
    assert set(r["pilot"][0]) == {"action_no", "open_date"}
    assert "question" not in json.dumps(r) and "gold" not in json.dumps(r)


@pytest.mark.skipif(
    not td.EVAL.exists(), reason="시험지(eval.jsonl)가 없다 (data/는 커밋하지 않는다)"
)
def test_the_committed_draw_matches_the_current_rules_and_exam():
    assert (
        td.OUT.read_text(encoding="utf-8")
        == json.dumps(td.build(), ensure_ascii=False, indent=1) + "\n"
    )


def test_the_reserve_follows_the_main_set_in_rank_order_without_overlap():
    r = td.draw(questions())
    ranks = [row["action_no"] for row in r["pilot"] + r["main"] + r["reserve"]]
    assert len(ranks) == len(set(ranks)) == td.PILOT + td.MAIN + td.RESERVE
    assert ranks == sorted(ranks, key=td.rank)

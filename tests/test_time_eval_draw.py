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


def committed():
    return json.loads(td.OUT.read_text(encoding="utf-8"))


def test_the_committed_draw_can_be_redrawn_from_its_own_pool_without_the_exam():
    # 시험지(eval.jsonl)가 없는 깨끗한 환경에서도 고정한 결과가 같은 규칙에서 나오는지 본다
    c = committed()
    redrawn = td.draw([{"action_no": a, "open_date": d} for a, d in c["pool"]], seed=c["seed"])
    assert {k: c[k] for k in redrawn} == redrawn


def test_the_committed_draw_keeps_the_agreed_conditions():
    c = committed()
    assert (c["seed"], c["cutoff_open_date"]) == (20261008, "20070101") == (td.SEED, td.CUTOFF)
    assert (len(c["pilot"]), len(c["main"]), len(c["reserve"])) == (5, 45, 30)
    rows = c["pilot"] + c["main"] + c["reserve"]
    assert len({r["action_no"] for r in rows}) == 80
    assert all(set(r) == {"action_no", "open_date"} and r["open_date"] >= td.CUTOFF for r in rows)
    assert [r["action_no"] for r in rows] == sorted((r["action_no"] for r in rows), key=td.rank)
    assert c["pool_size"] == len(c["pool"]) == 333
    pool = dict(map(tuple, c["pool"]))
    assert all(pool[r["action_no"]] == r["open_date"] for r in rows)
    # 후보 333개 중 순위가 가장 앞선 80개가 정확히 이 목록이다
    assert [r["action_no"] for r in rows] == sorted(pool, key=td.rank)[:80]
    base = json.loads(td.BASELINE.read_text(encoding="utf-8"))["build"]["eval_sha256"]
    assert c["eval_sha256"] == base

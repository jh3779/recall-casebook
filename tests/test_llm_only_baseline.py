"""LLM 단독 기준선(`llm_only_baseline`) — API 없이 번호 가리기·번호 정리·채점 규칙만 본다."""

import pytest

from scripts.defect_precedent import llm_only_baseline as lb


def test_mask_hides_recall_numbers_in_common_spellings():
    q = "GM WILL RECALL 00V057000 AND 00V-058; SEE ALSO 02E 012. PE99-076 STAYS."
    got = lb.mask_ids(q)
    assert "00V057000" not in got and "00V-058" not in got and "02E 012" not in got
    assert got.count(lb.MASK) == 3
    assert "PE99-076" in got  # 조사 번호(PE·EA)는 리콜 번호 모양이 아니다


def test_mask_catches_number_glued_to_next_word():
    assert (
        lb.mask_ids("FILED DEFECT REPORT 06V-213THAT DIRECTS")
        == f"FILED DEFECT REPORT {lb.MASK}THAT DIRECTS"
    )


def test_mask_leaves_years_and_counts_alone():
    q = "85,253 MODEL YEAR 1995 VEHICLES, LETTER DATED FEBRUARY 25, 2000"
    assert lb.mask_ids(q) == q


def test_norm_campno_accepts_spacing_and_hyphens_only():
    assert lb.norm_campno("00v-057000") == "00V057000"
    assert lb.norm_campno(" 00 V 057 ") == "00V057"
    assert lb.norm_campno("RCL-00V057") is None
    assert lb.norm_campno("00V05") is None


def _q(action, gold):
    return {"action_no": action, "question": "q", "gold_campnos": gold}


def _cause(text, status="filled"):
    return {"cause_status": status, "cause_text": text}


def test_score_counts_fabricated_hits_and_cause_categories():
    campaigns = {"00V057", "01V001", "02V002", "03V003"}
    causes = {
        "00V057": _cause("The  retractor spring\nwas undersized."),
        "02V002": _cause("NR - still under investigation", "stated_unknown"),
        "03V003": _cause("", "empty"),
    }
    rows = [
        {
            "action_no": "A",
            "recalls": [
                {"campno": "99V999000", "cause": "made up"},  # 없는 캠페인 + 원인
                {"campno": "00V-057", "cause": "retractor spring was undersized."},  # 원문 그대로
            ],
        },
        {"action_no": "B", "recalls": [{"campno": "01V001000", "cause": "x"}]},  # 573 보고서 없음
        {"action_no": "C", "recalls": []},  # 모른다고 함
        {"action_no": "D", "error": "RateLimitError: x"},
        {"action_no": "E", "recalls": [{"campno": "not a number", "cause": ""}]},
        {
            "action_no": "F",
            "recalls": [
                {
                    "campno": "02V002000",
                    "cause": "still under investigation",
                },  # stated_unknown도 대조
                {"campno": "03V003000", "cause": "y"},  # 573 원인 칸이 빔
            ],
        },
    ]
    qs = [
        _q("A", ["00V057000"]),
        _q("B", ["05V100000"]),
        _q("C", ["00V057000"]),
        _q("D", ["00V057000"]),
        _q("E", ["00V057000"]),
        _q("F", ["09V000000"]),
    ]
    s = lb.score_llm(rows, qs, campaigns, causes)
    assert s["n"] == 6
    assert s["hit@1"] == 0.0 and s["hit@3"] == round(1 / 6, 3)  # A만 2위에서 맞힘
    assert (s["ids"], s["bad_format"], s["fabricated"], s["q_with_fabricated"]) == (5, 1, 1, 1)
    assert s["fabricated_rate"] == 0.2
    assert s["ids_gold"] == 1  # A의 00V057만 정답
    got = {
        k: s[k]
        for k in (
            "causes_given",
            "cause_on_fabricated",
            "cause_no_573_report",
            "cause_573_empty",
            "cause_checked",
            "cause_verbatim",
        )
    }
    assert got == {
        "causes_given": 5,
        "cause_on_fabricated": 1,
        "cause_no_573_report": 1,
        "cause_573_empty": 1,
        "cause_checked": 2,
        "cause_verbatim": 2,
    }
    assert (s["answered"], s["abstained"], s["errors"]) == (4, 1, 1)


def test_score_cause_checked_but_not_verbatim():
    s = lb.score_llm(
        [{"action_no": "A", "recalls": [{"campno": "00V057000", "cause": "spring too small"}]}],
        [_q("A", ["00V057000"])],
        {"00V057"},
        {"00V057": _cause("The retractor spring was undersized.")},
    )
    assert (s["cause_checked"], s["cause_verbatim"], s["fabricated"]) == (1, 0, 0)


def _meta(n=1, inputs=None):
    return {"n": n, "mask_re": lb.ID_RE.pattern, "inputs": inputs or {"eval_sha256": "e"}}


def test_check_result_accepts_matching_result():
    qs = {"A": {"question": "RECALL 00V057000 SEAT"}}
    rows = [{"action_no": "A", "masked_question": f"RECALL {lb.MASK} SEAT"}]
    lb.check_result(rows, _meta(), qs, {"eval_sha256": "e"})


@pytest.mark.parametrize(
    "rows,meta,inputs",
    [
        (
            [{"action_no": "A", "masked_question": "Q"}],
            _meta(),
            {"eval_sha256": "other"},
        ),  # 판본 다름
        ([{"action_no": "A", "masked_question": "Q"}] * 2, _meta(2), {"eval_sha256": "e"}),  # 중복
        ([{"action_no": "A", "masked_question": "Q"}], _meta(3), {"eval_sha256": "e"}),  # 줄 수
        ([{"action_no": "A", "masked_question": "changed"}], _meta(), {"eval_sha256": "e"}),  # 질문
    ],
)
def test_check_result_rejects_mismatch(rows, meta, inputs):
    with pytest.raises(SystemExit):
        lb.check_result(rows, meta, {"A": {"question": "Q"}}, inputs)


def test_hit_rates_use_campaign_prefix():
    got = lb.hit_rates(
        [_q("A", ["00V057000"]), _q("B", ["05V100000"])],
        [["00V057001", "x"], ["y"] * 3 + ["05V100000"]],
    )
    assert (got["hit@1"], got["hit@3"], got["hit@5"], got["fabricated"]) == (0.5, 0.5, 1.0, 0)
    assert (got["ids"], got["ids_gold"]) == (6, 2)

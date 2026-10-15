"""LLM 단독 기준선(`llm_only_baseline`) — API 없이 번호 가리기·번호 정리·채점 규칙만 본다."""

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


def test_score_counts_fabricated_hits_and_verbatim_causes():
    campaigns = {"00V057", "01V001"}
    causes = {"00V057": "The  retractor spring\nwas undersized."}
    rows = [
        {
            "action_no": "A",
            "recalls": [
                {"campno": "99V999000", "cause": "made up"},  # 데이터에 없는 캠페인 = 지어낸 번호
                {
                    "campno": "00V-057",
                    "cause": "retractor spring was undersized.",
                },  # 공백 정리 뒤 원문 그대로
            ],
        },
        {
            "action_no": "B",
            "recalls": [{"campno": "01V001000", "cause": "paraphrased cause"}],
        },  # 573 원인 칸 없음
        {"action_no": "C", "recalls": []},  # 모른다고 함
        {"action_no": "D", "error": "RateLimitError: x"},
        {"action_no": "E", "recalls": [{"campno": "not a number", "cause": ""}]},
    ]
    qs = [
        _q("A", ["00V057000"]),
        _q("B", ["05V100000"]),
        _q("C", ["00V057000"]),
        _q("D", ["00V057000"]),
        _q("E", ["00V057000"]),
    ]
    s = lb.score_llm(rows, qs, campaigns, causes)
    assert s["n"] == 5
    assert s["hit@1"] == 0.0 and s["hit@3"] == 0.2  # A만 2위에서 맞힘
    assert (s["ids"], s["bad_format"], s["fabricated"], s["q_with_fabricated"]) == (3, 1, 1, 1)
    assert s["fabricated_rate"] == round(1 / 3, 3)
    assert (s["causes_given"], s["cause_verbatim"], s["cause_no_573"], s["cause_not_in_573"]) == (
        3,
        1,
        2,
        0,
    )
    assert (s["answered"], s["abstained"], s["errors"]) == (3, 1, 1)


def test_score_cause_not_in_573_when_text_differs():
    s = lb.score_llm(
        [{"action_no": "A", "recalls": [{"campno": "00V057000", "cause": "spring too small"}]}],
        [_q("A", ["00V057000"])],
        {"00V057"},
        {"00V057": "The retractor spring was undersized."},
    )
    assert (s["cause_verbatim"], s["cause_not_in_573"], s["fabricated"]) == (0, 1, 0)


def test_hit_rates_use_campaign_prefix():
    got = lb.hit_rates(
        [_q("A", ["00V057000"]), _q("B", ["05V100000"])],
        [["00V057001", "x"], ["y"] * 3 + ["05V100000"]],
    )
    assert (got["hit@1"], got["hit@3"], got["hit@5"], got["fabricated"]) == (0.5, 0.5, 1.0, 0)

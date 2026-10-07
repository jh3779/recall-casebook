import pytest

from scripts.defect_precedent import nhtsa, why_stats


def recall(campno, defect, received="20200101"):
    return {"campno": campno, "defect": defect, "received_date": received}


def inv(campno, summary):
    return {"CAMPNO": campno, "SUMMARY": summary}


def test_pattern_is_case_insensitive_and_needs_a_cause_word():
    assert why_stats.PATTERN.search("The crack is DUE TO fatigue")
    assert why_stats.PATTERN.search("improperly welded")
    assert not why_stats.PATTERN.search("The brake may fail")


def test_linked_campnos_skip_placeholder_empty_and_unknown_campaigns():
    rows = [
        inv("A", "Brake hoses leak"),
        inv("B", "There is no summary currently available"),
        inv("C", "====="),
        inv("D", "   "),
        inv("Z", "not a card"),
    ]
    assert why_stats.linked_campnos(rows, {"A", "B", "C", "D"}) == {"A"}


def test_maker_overlap_counts_core_words_and_full_names_and_any_gold_recall():
    recalls = [
        {"campno": "A1", "maker": "Ford Motor Company"},
        {"campno": "A2", "maker": "Toyota Motor Co., Ltd."},
        {"campno": "A3", "maker": "General Motors LLC"},
    ]
    questions = [
        {
            "question": "Ford F-150 rear axle bolt may fracture",
            "gold_campnos": ["A1"],
        },  # 핵심 단어 FORD
        {
            "question": "Motor mount failure in the company vehicle",
            "gold_campnos": ["A1"],
        },  # 일반어만 겹침 → 아님
        {"question": "Seat belt buckle issue", "gold_campnos": ["A1", "A2"]},  # 겹침 없음
        {
            "question": "Toyota Motor Co., Ltd. airbag inflator",
            "gold_campnos": ["A3", "A2"],
        },  # 둘째 정답이 맞음 + 전체 이름
        {"question": "gm", "gold_campnos": ["A3"]},  # 길이 3 미만 단어는 세지 않는다
    ]
    s = why_stats.maker_overlap(questions, recalls)
    assert s == {"questions": 5, "overlap": 2, "full_name": 1}


def test_compute_counts_each_basis_and_the_union():
    recalls = [
        recall("20V001000", "Crack due to fatigue"),  # 표현
        recall("20V002000", "Brake may fail"),  # 조사 요약
        recall("20V003000", "Brake may fail"),  # 없음
        recall("10V004000", "caused by a weld", received="20100101"),  # 이전 + 표현
    ]
    s = why_stats.compute(recalls, [inv("20V002000", "Steering fault")], [])
    assert (s["recalls"], s["expressed"], s["linked"], s["either"]) == (4, 2, 1, 3)
    assert (s["post_recalls"], s["post_either"], s["pre_recalls"], s["pre_either"]) == (3, 2, 1, 1)


def test_compute_estimate_uses_the_sample_rate_only_for_post_2014_recalls():
    recalls = [
        recall("20V001000", "Crack due to fatigue"),  # 표본 캠페인, 기존 방식 근거 있음
        recall("20V002000", "Brake may fail"),  # 표본 캠페인, 573 칸만 채워짐
        recall("20V003000", "Brake may fail"),  # 표본 캠페인, 둘 다 없음
        recall("20V004000", "Brake may fail"),  # 표본 아님
        recall("10V005000", "caused by a weld", received="20100101"),  # 이전: 기존 방식 그대로
    ]
    sample = [
        {"campaign": "20V001", "cause_status": "empty"},
        {"campaign": "20V002", "cause_status": "filled"},
        {"campaign": "20V003", "cause_status": "empty"},
    ]
    s = why_stats.compute(recalls, [], sample)
    assert (s["sample"], s["sample_old"], s["sample_filled"], s["sample_union"]) == (3, 1, 1, 2)
    assert s["sample_union_rate"] == pytest.approx(2 / 3)
    # 이전 1건(근거 있음) + 이후 4건 × 2/3
    assert s["estimate"] == pytest.approx(1 + 4 * 2 / 3)


def test_compute_counts_a_campaign_with_several_recalls_once_per_sample_row():
    recalls = [recall("20V001000", "Brake may fail"), recall("20V001001", "caused by a weld")]
    s = why_stats.compute(recalls, [], [{"campaign": "20V001", "cause_status": "empty"}])
    assert s["sample_old"] == 1 and s["sample"] == 1


@pytest.mark.skipif(
    not (nhtsa.OUT_DIR / "recalls.jsonl").exists()
    or not (nhtsa.OUT_DIR / "causes_sample.jsonl").exists()
    or not (nhtsa.RAW_DIR / "FLAT_INV.zip").exists(),
    reason="내려받은 원본·기준 데이터가 없다 (data/raw, data/processed는 커밋하지 않는다)",
)
def test_reproduces_the_numbers_of_the_2026_10_06_snapshot():
    s = why_stats.compute(
        why_stats.read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl"),
        nhtsa.read_flat(nhtsa.RAW_DIR / "FLAT_INV.zip", nhtsa.INV_COLS),
        why_stats.read_jsonl(nhtsa.OUT_DIR / "causes_sample.jsonl"),
    )
    assert (s["recalls"], s["expressed"], s["linked"], s["either"]) == (30350, 7775, 1870, 9330)
    assert (s["sample"], s["sample_old"], s["sample_filled"], s["sample_union"]) == (
        300,
        89,
        205,
        232,
    )
    overlap = why_stats.maker_overlap(
        why_stats.read_jsonl(nhtsa.OUT_DIR / "eval.jsonl"),
        why_stats.read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl"),
    )
    assert overlap == {"questions": 749, "overlap": 364, "full_name": 73}  # 이슈 #24 B 파트의 값

"""P2 실험 스크립트의 순수 함수 — 보고서 수치의 기반이라 데이터·외부 패키지 없이 검사한다."""

import pytest

from scripts.defect_precedent import engine2_trial as e2
from scripts.defect_precedent import retrieval_compare as rc


def test_drop_brands_removes_brand_tokens_and_phrases_only():
    toks = "general motors stated that the buick brake hose on ford and land rover vehicles may leak".split()
    assert rc.drop_brands(toks) == "stated that the brake hose on and vehicles may leak".split()
    # 구절의 앞 단어만 있으면 지우지 않는다 (general은 일반어)
    assert rc.drop_brands(["general", "wear"]) == ["general", "wear"]


def test_strip_brands_matches_drop_brands_on_raw_text():
    text = "IN ITS LETTER, GENERAL MOTORS STATED THE BUICK BRAKE HOSE (FORD-BUILT) MAY LEAK; Land  Rover too"
    assert rc.tokenize(rc.strip_brands(text)) == rc.drop_brands(rc.tokenize(text))


def test_score_reports_all_and_post2014_subsets():
    qs = [
        {"gold_campnos": ["A"], "_post": True},
        {"gold_campnos": ["B", "C"], "_post": False},
        {"gold_campnos": ["D"], "_post": True},
    ]
    ranks = [["A"] + ["x"] * 9, ["x", "x", "C"] + ["x"] * 7, ["x"] * 10]
    out = rc.score(ranks, qs)
    assert out["all"]["n"] == 3 and out["post2014"]["n"] == 2
    assert out["all"]["any@1"] == round(1 / 3, 3)
    assert out["all"]["any@3"] == round(2 / 3, 3)  # 두 번째 문항은 연결 리콜 C가 3위
    assert out["all"]["first@3"] == round(1 / 3, 3)  # 첫 연결 리콜 B는 없음
    assert out["post2014"]["any@10"] == 0.5


def test_rrf_sums_reciprocal_ranks():
    fused = rc.rrf(["a", "b", "c"], ["c", "a"])
    # a: 1/61 + 1/62, c: 1/63 + 1/61, b: 1/62
    assert fused == ["a", "c", "b"]


def test_engine2_check_requires_exact_substring():
    src = "The brake  hose was routed near the exhaust. Unknown otherwise."
    ok = e2.check(src, ["The brake  hose was routed near the exhaust."])
    assert ok["dropped"] == [] and ok["spans"][0]["start"] == 0
    assert ok["spans"][0]["text"] == src[: ok["spans"][0]["end"]]
    # 공백 한 칸만 달라도 버린다 (정규화하지 않는다)
    assert e2.check(src, ["The brake hose was routed near the exhaust."])["dropped"]
    # 한 글자 바뀌면 버린다
    assert e2.check(src, ["The brake  hose was routed near the exhaust!"])["dropped"]
    # 5단어 미만 조각은 따로 센다
    assert e2.check(src, ["Unknown otherwise."])["short_fragments"] == 1


def test_cause_trials_rule_and_confusion():
    from scripts.defect_precedent import cause_trials as ct

    assert ct.rule_unknown("The root cause has not been determined.")
    assert ct.rule_unknown("Supplier continues to investigate.")
    assert not ct.rule_unknown("Manufacturing error.")
    out = ct.confusion([True, True, False, False], [True, False, True, False])
    assert out == {"accuracy": 0.5, "tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5}


def test_time_eval_candidates_only_before_open_date():
    np = pytest.importorskip("numpy")
    from scripts.defect_precedent import time_eval_candidates as te

    cards = [
        {"campno": "OLD1", "received_date": "20100101"},
        {"campno": "NEW1", "received_date": "20150324"},  # 기준일 당일 — 빼야 한다
        {"campno": "OLD2", "received_date": "20120505"},
    ]
    toks = [["brake", "hose"], ["brake", "hose"], ["seat", "belt"]]
    vecs = np.eye(3, dtype="float32")
    out = te.candidates_for(
        {"open_date": "20150324", "question": "brake hose"}, cards, toks, vecs, vecs[1]
    )
    assert out["n_indexed"] == 2 and set(out["pool"]) == {"OLD1", "OLD2"}
    assert out["pool"]["OLD1"]["bm25"] == 1


def test_storage_bench_latency_uses_p95_only_with_100_samples():
    from scripts.defect_precedent import storage_bench as sb

    small = sb.lat([0.001 * i for i in range(1, 11)])
    assert small == {"n": 10, "p50_ms": 5.5, "max_ms": 10.0}
    big = sb.lat([0.001 * i for i in range(1, 101)])
    assert big["p95_ms"] == 95.0 and "max_ms" not in big

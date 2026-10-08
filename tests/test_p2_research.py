"""P2 실험 스크립트의 순수 함수 — 보고서 수치의 기반이라 데이터·외부 패키지 없이 검사한다."""

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

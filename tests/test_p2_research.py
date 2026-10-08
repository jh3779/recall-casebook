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
    assert out == {
        "n": 4,
        "accuracy": 0.5,
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "precision": 0.5,
        "recall": 0.5,
    }


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


def test_time_eval_indexed_before_excludes_open_date_itself():
    from scripts.defect_precedent import time_eval_candidates as te

    cards = [
        {"received_date": "20150323"},
        {"received_date": "20150324"},  # 기준일 당일
        {"received_date": "20150325"},
        {"received_date": "19991231"},
    ]
    assert te.indexed_before(cards, "20150324") == [0, 3]


def test_cause_trials_score_counts_only_real_empty_lists_as_llm_unknown():
    from scripts.defect_precedent import cause_trials as ct

    labels = {"a": "unknown", "b": "stated", "c": "mixed", "d": "stated"}
    rows = [
        {"campaign": "a", "returned": [], "spans": [], "rule_unknown": True},
        # 원인을 돌려줬지만 글자를 바꿔 대조에서 버려짐 — LLM의 "미확인" 예측이 아니다
        {"campaign": "b", "returned": ["x"], "spans": [], "rule_unknown": False},
        {"campaign": "c", "returned": ["y"], "spans": [{"text": "y"}], "rule_unknown": True},
        {"campaign": "d", "returned": [], "spans": [], "rule_unknown": False, "parse_failed": True},
    ]
    out = ct.score_rows(rows, labels)
    assert out["llm_empty"]["tp"] == 1 and out["llm_empty"]["fp"] == 0
    assert out["parse_failed"] == 1 and out["returned_but_all_dropped"] == 1
    assert out["rule"]["fp"] == 1  # mixed에 걸림
    assert out["rule_vs_unknown_or_mixed"]["fp"] == 0


def test_unknown_rule_does_not_match_north_america_na():
    from scripts.defect_precedent import cause_trials as ct

    assert not ct.rule_unknown("Parts supplied by Toyota Motor Sales NA.")
    assert ct.rule_unknown("N/A")


def test_cause_trials_score_rejects_edited_sheet_text_and_missing_labeler(tmp_path):
    import csv

    from scripts.defect_precedent import cause_trials as ct

    def sheet(rows):
        path = tmp_path / "s.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["campaign", "cause_text", "text_sha256", "label", "labeler_id", "note"])
            w.writerows(rows)
        return path

    text = "Manufacturing error."
    # 표시자가 본 원문 셀이 해시와 다르면(스프레드시트가 자름 등) 채점하지 않는다
    with pytest.raises(SystemExit, match="cause_text"):
        ct.score(sheet([["A", "Manufacturing", ct.text_sha(text), "stated", "L1", ""]]), [])
    with pytest.raises(SystemExit, match="labeler_id"):
        ct.score(sheet([["A", text, ct.text_sha(text), "stated", "", ""]]), [])


def test_engine2_recheck_requires_meta(tmp_path):
    from scripts.defect_precedent import engine2_trial as e2

    res = tmp_path / "r.jsonl"
    res.write_text('{"cause_text": "x y", "returned": ["x y"]}\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="meta"):
        e2.main(["--recheck", str(res)])
    assert not (tmp_path / "r.recheck.jsonl").exists()


def test_cause_trials_score_checks_sheet_meta_and_result_version(tmp_path):
    import csv
    import json

    from scripts.defect_precedent import cause_trials as ct

    text = "Manufacturing error."
    sheet = tmp_path / "u.csv"
    with sheet.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["campaign", "cause_text", "text_sha256", "label", "labeler_id", "note"])
        w.writerow(["A", text, ct.text_sha(text), "stated", "L1", ""])
    # 시트 메타가 결과 메타(u.meta.json)와 다른 이름이다
    assert ct.sheet_meta_path(sheet).name == "u.csv.meta.json"
    with pytest.raises(SystemExit, match="meta.json이 없다"):
        ct.score(sheet, [])

    meta = {"causes_sha256": "c1", "sample_sha256": ct.sample_sha([("A", ct.text_sha(text))])}
    ct.sheet_meta_path(sheet).write_text(json.dumps(meta), encoding="utf-8")
    res = tmp_path / "u.jsonl"
    res.write_text(
        json.dumps(
            {"campaign": "A", "text": text, "returned": [], "spans": [], "rule_unknown": False}
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "u.meta.json").write_text(json.dumps({"data": {"causes_sha256": "c2"}}), "utf-8")
    with pytest.raises(SystemExit, match="다른 causes.jsonl 판본"):
        ct.score(sheet, [res])

    (tmp_path / "u.meta.json").write_text(json.dumps({"data": {"causes_sha256": "c1"}}), "utf-8")
    ct.score(sheet, [res])  # 같은 판본이면 채점한다

    meta["sample_sha256"] = "다른표본"
    ct.sheet_meta_path(sheet).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(SystemExit, match="표본이 바뀐"):
        ct.score(sheet, [res])

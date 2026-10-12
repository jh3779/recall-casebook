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


def test_time_eval_unusable_questions_follow_dec037_rule6():
    from scripts.defect_precedent import time_eval_candidates as te

    ok = {
        "action_no": "A",
        "check": "통과",
        "status": "확보",
        "pdf_mod_gap_days": 3,
        "open_date": "20150324",
        "question": "Reports dated 03/01/2015 allege a failure.",
    }
    qs = [
        ok,
        ok | {"action_no": "B", "pdf_mod_gap_days": 4},  # 3일 초과
        ok | {"action_no": "C", "pdf_mod_gap_days": None},  # 수정일 없음
        ok | {"action_no": "D", "status": "문서 없음"},
        ok | {"action_no": "E", "check": "실패"},
        ok
        | {"action_no": "F", "question": "A recall was filed on April 2, 2015."},  # 개시일 뒤 날짜
    ]
    assert te.unusable_questions(qs) == ["B", "C", "D", "E", "F"]


def test_time_eval_questions_file_passes_rule6():
    import json
    from pathlib import Path

    from scripts.defect_precedent import time_eval_candidates as te

    d = json.loads(Path("scripts/defect_precedent/time_eval_questions.json").read_text("utf-8"))
    assert te.unusable_questions(d["pilot"]) == [] and te.unusable_questions(d["main"]) == []


def _fake_git(outputs: dict, returncode: int = 0, missing: bool = False):
    """`code_provenance`가 부르는 git 명령을 흉내 낸다 — git 상태와 무관하게 분기를 시험한다(#53 a).

    진짜 `subprocess.run`처럼 `check=True`일 때만 0이 아닌 종료 코드를 예외로 바꾼다 — `check=True`가 빠지면 실패가
    조용히 "깨끗함"으로 기록되므로 그 회귀를 잡기 위해서다. 명령 인자도 그대로인지 본다."""
    import subprocess

    expected = {
        "status": ["git", "status", "--porcelain", "--", "scripts/"],
        "rev-parse": ["git", "rev-parse", "HEAD"],
    }

    from scripts.defect_precedent.time_eval_candidates import ROOT

    def run(cmd, **kw):
        assert cmd == expected[cmd[1]], cmd
        assert kw.get("cwd") == ROOT  # 다른 폴더(다른 저장소)의 상태를 기록하지 않게
        if missing:
            raise FileNotFoundError("git")
        done = subprocess.CompletedProcess(
            cmd, returncode, stdout=outputs.get(cmd[1], ""), stderr=""
        )
        if kw.get("check"):
            done.check_returncode()
        return done

    return run


def test_time_eval_code_provenance_records_clean_and_dirty_scripts(monkeypatch):
    import subprocess

    from scripts.defect_precedent import time_eval_candidates as tec

    monkeypatch.setattr(subprocess, "run", _fake_git({"status": "", "rev-parse": "abc123"}))
    clean = tec.code_provenance(allow_dirty=False)  # 깨끗하면 허용 없이 통과
    assert clean["commit"] == "abc123" and clean["dirty"] is False
    import hashlib

    # 시트를 만든 코드 — 운영 목록(CODE_FILES)에서 빠지면 실패하도록 따로 적는다
    expected_files = [
        "scripts/defect_precedent/time_eval_candidates.py",
        "scripts/defect_precedent/retrieval_compare.py",
        "scripts/defect_precedent/bm25_baseline.py",
    ]
    # 스크립트 해시는 파일 내용의 sha256이어야 한다(빈 값·다른 파일이면 실패)
    want = {f: hashlib.sha256((tec.ROOT / f).read_bytes()).hexdigest() for f in expected_files}
    assert clean["script_sha256"] == want

    monkeypatch.setattr(
        subprocess, "run", _fake_git({"status": " M scripts/x.py", "rev-parse": "abc123"})
    )
    with pytest.raises(SystemExit, match="커밋하지 않은 변경"):
        tec.code_provenance(allow_dirty=False)
    assert tec.code_provenance(allow_dirty=True)["dirty"] is True


@pytest.mark.parametrize("kind", ["exit_code", "git_missing"])
def test_time_eval_code_provenance_stops_when_git_fails(monkeypatch, kind):
    import subprocess

    from scripts.defect_precedent import time_eval_candidates as tec

    fake = _fake_git({}, returncode=128) if kind == "exit_code" else _fake_git({}, missing=True)
    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(SystemExit, match="코드 판본을 기록할 수 없어"):
        tec.code_provenance(allow_dirty=True)


def _fake_openai(monkeypatch, calls):
    """openai는 `uv run --with openai`로만 쓰는 연구 의존성이라, 호출 인자만 확인하는 가짜 모듈을 끼운다."""
    import sys
    from types import SimpleNamespace

    def parse(**kw):
        calls.append(kw)
        parsed = kw["text_format"](cause_sentences=["x"])
        return SimpleNamespace(
            output_parsed=parsed, usage=SimpleNamespace(input_tokens=3, output_tokens=1)
        )

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda: client))


def test_cause_trials_llm_passes_reasoning_effort_only_when_given(monkeypatch):
    from scripts.defect_precedent import cause_trials as ct

    calls = []
    _fake_openai(monkeypatch, calls)
    ct.llm("gpt-4o-mini", "i", "t")
    ct.llm("gpt-6-luna", "i", "t", reasoning_effort="none")
    assert (
        "reasoning" not in calls[0]
    )  # 추론 모델이 아닌 4o-mini에는 보내지 않는다(10/8 시험과 같은 요청)
    assert calls[1]["reasoning"] == {"effort": "none"} and calls[1]["model"] == "gpt-6-luna"


def test_trial_clis_accept_reasoning_effort():
    from scripts.defect_precedent import cause_trials as ct
    from scripts.defect_precedent import engine2_trial as e2

    for mod in (ct, e2):
        p = mod.parser()
        args = ["--model", "gpt-6-luna", "--reasoning-effort", "none"]
        a = p.parse_args((["unknown"] if mod is ct else []) + args)
        assert a.reasoning_effort == "none"
        with pytest.raises(SystemExit):
            p.parse_args((["unknown"] if mod is ct else []) + ["--reasoning-effort", "minimal"])


def test_trials_default_to_luna_with_no_reasoning_but_keep_explicit_models(monkeypatch, tmp_path):
    from scripts.defect_precedent import cause_trials as ct

    assert ct.model_and_effort(None, None) == ("gpt-6-luna", "none")  # 사용자 지정 2026-10-12
    assert ct.model_and_effort(None, "low") == ("gpt-6-luna", "low")
    assert ct.model_and_effort("gpt-4o-mini", None) == (
        "gpt-4o-mini",
        None,
    )  # 추론 설정을 보내지 않는다
    got = []
    monkeypatch.setattr(ct, "run", lambda *a: got.append(a))
    ct.main(["unknown", "--out", str(tmp_path / "r.jsonl")])
    assert got[0][1] == "gpt-6-luna" and got[0][-1] == "none"


def test_engine2_cli_defaults_to_luna(monkeypatch, tmp_path):
    from scripts.defect_precedent import cause_trials as ct
    from scripts.defect_precedent import engine2_trial as e2

    seen = []
    real = ct.model_and_effort

    def spy(model, effort):
        seen.append(real(model, effort))
        return seen[-1]

    monkeypatch.setattr(ct, "model_and_effort", spy)
    _fake_openai(monkeypatch, [])

    class Stop(Exception):
        pass

    def stop():
        raise Stop

    monkeypatch.setattr(e2, "provenance", stop)  # 모델을 고른 뒤 데이터를 읽기 전에 멈춘다
    with pytest.raises(Stop):
        e2.main(["--n", "1", "--out", str(tmp_path / "r.jsonl")])
    assert seen == [("gpt-6-luna", "none")]


def test_naming_the_default_model_keeps_the_compared_effort():
    from scripts.defect_precedent import cause_trials as ct

    assert ct.model_and_effort("gpt-6-luna", None) == (
        "gpt-6-luna",
        "none",
    )  # 문서 기본값 medium이 아니라


def test_cause_trials_run_sends_the_effort_and_records_it(monkeypatch, tmp_path):
    import json

    from scripts.defect_precedent import cause_trials as ct

    calls = []
    _fake_openai(monkeypatch, calls)
    monkeypatch.setattr(ct, "provenance", lambda: {"causes_sha256": "x"})
    monkeypatch.setattr(ct, "pick_unknown", lambda n: [{"campaign": "24V001", "text": "x"}])
    out = tmp_path / "o.jsonl"
    ct.main(["unknown", "--n", "1", "--out", str(out)])  # 기본 모델 → Luna·none이 요청까지
    assert calls[0]["model"] == "gpt-6-luna" and calls[0]["reasoning"] == {"effort": "none"}
    meta = json.loads(out.with_suffix(".meta.json").read_text())
    assert (meta["model"], meta["reasoning_effort"]) == ("gpt-6-luna", "none")


def test_engine2_run_sends_the_effort_and_records_it(monkeypatch, tmp_path):
    import json

    from scripts.defect_precedent import engine2_trial as e2
    from scripts.defect_precedent.retrieval_compare import card_text
    from tests.test_rag_server import CARDS

    calls = []
    _fake_openai(monkeypatch, calls)
    files = {
        "recalls.jsonl": CARDS,
        "eval.jsonl": [{"question": card_text(CARDS[0]), "action_no": "PE1"}],
        "causes.jsonl": [
            {"campaign": CARDS[0]["campno"][:6], "cause_status": "filled", "cause_text": "x"}
        ],
    }
    monkeypatch.setattr(e2, "provenance", lambda: {"causes_sha256": "x"})
    monkeypatch.setattr(e2, "read_jsonl", lambda path: files[path.name])
    out = tmp_path / "e.jsonl"
    e2.main(["--n", "1", "--out", str(out)])
    assert calls[0]["model"] == "gpt-6-luna" and calls[0]["reasoning"] == {"effort": "none"}
    meta = json.loads(out.with_suffix(".meta.json").read_text())
    assert (meta["model"], meta["reasoning_effort"]) == ("gpt-6-luna", "none")

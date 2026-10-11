import hashlib
import json

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


def test_compute_converts_the_sample_rate_by_campaigns_and_flags_when_recalls_are_not_one_to_one():
    # 이후 리콜 3건이 캠페인 2개에 걸려 있다 — 표본 비율(캠페인 단위)은 캠페인 수에 곱한다
    recalls = [
        recall("20V001000", "Crack due to fatigue"),
        recall("20V001001", "Brake may fail"),
        recall("20V002000", "Brake may fail"),
    ]
    sample = [
        {"campaign": "20V001", "cause_status": "empty"},
        {"campaign": "20V002", "cause_status": "empty"},
    ]
    s = why_stats.compute(recalls, [], sample)
    assert (s["post_recalls"], s["post_campaigns"], s["post_one_to_one"]) == (3, 2, False)
    assert s["sample_union_rate"] == pytest.approx(0.5)
    assert s["estimate"] == pytest.approx(2 * 0.5)  # 리콜 수(3)가 아니라 캠페인 수(2)에 곱함
    one = why_stats.compute(
        [recall("20V003000", "x")], [], [{"campaign": "20V003", "cause_status": "filled"}]
    )
    assert one["post_one_to_one"] is True


def sample_row(campaign, status="filled", resolution="auto", pdf_sha="aa"):
    return {
        "campaign": campaign,
        "cause_status": status,
        "resolution": resolution,
        "submission_date": "20240101",
        "pdfs": {f"odi/rcl/2024/RCLRPT-{campaign}-0001.PDF": pdf_sha},
    }


def make_base(sample, with_digest=True):
    base = {
        "build": {"raw_manifest_sha256": "r", "recalls_sha256": "c", "eval_sha256": "e"},
        "rclrpt_sample": [{"campaign": r["campaign"], "pdfs": r["pdfs"]} for r in sample],
        "expected": {
            "rclrpt_sample_filled": sum(r["cause_status"] == "filled" for r in sample),
            "rclrpt_sample_empty": sum(r["cause_status"] == "empty" for r in sample),
            "rclrpt_sample_unresolved": sum(r["resolution"] == "unresolved" for r in sample),
        },
    }
    if with_digest:
        base["causes_sample"] = {
            "rows": len(sample),
            "content_sha256": why_stats.sample_digest(sample),
        }
    return base


SAME = {"raw_manifest_sha256": "r", "recalls_sha256": "c", "eval_sha256": "e"}


def test_full_coverage_separates_confirmed_unknown_and_missing_and_gives_a_range():
    recalls = [
        recall("20V001000", "Crack due to fatigue"),  # 기존 방식(표현) + 573 채움
        recall("20V002000", "Brake may fail"),  # 573만 채움(확인)
        recall("20V003000", "Brake may fail"),  # 573 원인 칸 비어 있음(확인)
        recall("20V004000", "Brake may fail"),  # 최신판 미확정 → 확인 불가
        recall("20V005000", "Brake may fail"),  # 읽지 못해 수용한 실패 → 확인 불가
        recall("20V006000", "Brake may fail"),  # 573 보고서가 없음 → 근거 없음 확정
        recall("20V007000", "caused by a weld"),  # 확인 불가이지만 기존 방식 근거가 이미 있음
        recall("10V008000", "caused by a weld", received="20100101"),  # 이전 리콜: 기존 방식만
    ]
    causes = [
        {"campaign": "20V001", "cause_status": "filled", "resolution": "auto"},
        {"campaign": "20V002", "cause_status": "filled", "resolution": "auto"},
        {"campaign": "20V003", "cause_status": "empty", "resolution": "auto"},
        {"campaign": "20V004", "cause_status": "filled", "resolution": "unresolved"},
        {"campaign": "20V007", "cause_status": "empty", "resolution": "unresolved"},
    ]
    s = why_stats.full_coverage(recalls, [], causes, ["20V005"])
    assert (s["post_recalls"], s["post_campaigns"], s["post_with_report"]) == (7, 7, 5)
    assert (s["unresolved_campaigns"], s["failed_campaigns"], s["unknown_recalls"]) == (2, 1, 3)
    assert (s["post_either"], s["post_filled"]) == (
        2,
        2,
    )  # 표현 2건(001·007), 확인된 채움 2건(001·002)
    assert s["post_union"] == 3  # 001·002·007
    # 상한: 확인 불가 3건(004·005·007) 중 아직 근거가 없는 004·005를 더함
    assert s["post_union_upper"] == 5
    assert (s["pre_either"], s["total_union"], s["total_union_upper"]) == (1, 4, 6)


def test_verify_causes_stops_when_the_file_does_not_match_the_manifest(tmp_path):
    rows = [{"campaign": "20V001"}, {"campaign": "20V002"}]
    path = tmp_path / "causes.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    manifest_path = tmp_path / "causes.manifest.json"
    good = {
        "kind": "full",
        "rows": 2,
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "failed_campaigns": ["20V003"],
        "expect_campaigns": 3,
        "expected_campaigns_sha256": why_stats._digest(["20V001", "20V002", "20V003"]),
    }
    manifest_path.write_text(json.dumps(good), encoding="utf-8")
    assert why_stats.verify_causes(path, manifest_path, rows)["rows"] == 2
    for bad, message in (
        ({**good, "file_sha256": "00" * 32}, "sha256"),
        ({**good, "rows": 3}, "줄 수"),
        ({**good, "kind": "sample"}, "full이 아니다"),
        # 대상이 빠진 파일 — 파일과 명세가 서로 맞아도 기대 수·목록과 다르면 통과하지 못한다
        ({**good, "expect_campaigns": 10}, "전체 수집이 아니다"),
        ({**good, "expected_campaigns_sha256": "00" * 32}, "기대 목록과 다르다"),
        ({**good, "failed_campaigns": ["20V001"]}, "겹치거나"),
        ({**good, "failed_campaigns": ["20V003", "20V003"], "expect_campaigns": 4}, "겹치거나"),
    ):
        manifest_path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            why_stats.verify_causes(path, manifest_path, rows)
        assert message in str(e.value), message
    manifest_path.write_text(json.dumps(good), encoding="utf-8")
    with pytest.raises(SystemExit):  # 같은 캠페인이 겹침
        why_stats.verify_causes(path, manifest_path, [rows[0], rows[0]])
    manifest_path.unlink()
    with pytest.raises(SystemExit):  # 명세가 없으면 쓰지 않는다
        why_stats.verify_causes(path, manifest_path, rows)


def test_full_baseline_check_pins_the_target_list_and_stops_for_a_partial_collection():
    pinned = {
        "rows": 11719,
        "failures": 18,
        "expect_campaigns": 11737,
        "causes_sha256": "c" * 64,
        "expected_campaigns_sha256": "e" * 64,
        "failed_campaigns_sha256": why_stats._digest(["20V001", "20V002"]),
        "manifest_sha256": "m" * 64,
    }
    base = {"causes_full": pinned}
    manifest = {
        "rows": 11719,
        "failures": 18,
        "expect_campaigns": 11737,
        "file_sha256": "c" * 64,
        "expected_campaigns_sha256": "e" * 64,
        "failed_campaigns": ["20V002", "20V001"],
    }
    assert "일치" in why_stats.full_baseline_check(base, manifest, "m" * 64, False)
    # 10,000개만 모은 파일과 그에 맞춰 만든 명세 — 명세 안의 숫자끼리는 맞지만 기준 파일의 고정값과 달라 멈춘다
    partial = {
        "rows": 9990,
        "failures": 10,
        "expect_campaigns": 10000,
        "file_sha256": "p" * 64,
        "expected_campaigns_sha256": "q" * 64,
        "failed_campaigns": ["20V001"],
    }
    with pytest.raises(SystemExit) as e:
        why_stats.full_baseline_check(base, partial, "x" * 64, False)
    assert "expected_campaigns_sha256" in str(e.value) and "expect_campaigns" in str(e.value)
    # 실패 목록만 다른 캠페인으로 바꾸고 명세 지문을 갱신해도, 원인 파일 해시가 같아도 멈춘다
    swapped = {**manifest, "failed_campaigns": ["20V009", "20V010"]}
    with pytest.raises(SystemExit) as e:
        why_stats.full_baseline_check(base, swapped, "m" * 64, False)
    assert "failed_campaigns_sha256" in str(e.value)
    # 명세 파일 자체가 달라진 경우
    with pytest.raises(SystemExit) as e:
        why_stats.full_baseline_check(base, manifest, "z" * 64, False)
    assert "manifest_sha256" in str(e.value)
    # --allow-drift면 재계산이라고 표시하고, 기준에 고정값이 없으면 대조하지 않았다고 알린다
    assert "재계산" in why_stats.full_baseline_check(base, partial, "x" * 64, True)
    # 기준 파일에 고정값이 없으면 멈추고, --allow-drift일 때만 대조 없이 재계산한다
    with pytest.raises(SystemExit) as e:
        why_stats.full_baseline_check({}, manifest, "m" * 64, False)
    assert "causes_full" in str(e.value)
    assert "재현 아님" in why_stats.full_baseline_check({}, manifest, "m" * 64, True)


def test_full_requires_a_baseline_file_on_the_command_line_and_in_the_function(
    monkeypatch, tmp_path
):
    import runpy
    import sys

    # 데이터가 없는 환경(CI)에서도 파일을 읽기 전에 먼저 막힌다
    monkeypatch.setattr(nhtsa, "OUT_DIR", tmp_path)
    # 함수: 기준 파일 없이는 일부만 수집한 자료도 계산되므로 시작 전에 멈춘다
    with pytest.raises(SystemExit) as e:
        why_stats.main_full(None)
    assert "--baseline이 필요하다" in str(e.value)
    # 명령줄: `--full`만 주면 argparse 오류(종료 코드 2)
    monkeypatch.setattr(sys, "argv", ["why_stats", "--full"])
    with pytest.raises(SystemExit) as e:
        runpy.run_module("scripts.defect_precedent.why_stats", run_name="__main__")
    assert e.value.code == 2


def test_the_committed_baseline_file_has_no_duplicate_json_keys():
    # 같은 이름의 키가 두 번 있으면 읽는 프로그램마다 앞쪽·뒤쪽 값을 달리 골라 기준이 모호해진다
    def refuse_duplicates(pairs):
        keys = [k for k, _ in pairs]
        duplicated = {k for k in keys if keys.count(k) > 1}
        assert not duplicated, f"중복된 키: {sorted(duplicated)}"
        return dict(pairs)

    for name in ("baseline_2026-10-06.json", "baseline_2026-10-06_maker-aliases.json"):
        path = nhtsa.REPO_ROOT / "scripts/defect_precedent" / name
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=refuse_duplicates)


def test_input_label_for_the_full_mode_does_not_claim_to_reproduce_the_full_result():
    base = make_base([sample_row("20V001")])
    label = why_stats.input_label("b.json", base, SAME, None, False)
    assert "원본·카드·시험지" in label  # 전수 모드에서는 표본을 보지 않는다
    drift = {**SAME, "recalls_sha256": "x"}
    with pytest.raises(SystemExit):
        why_stats.input_label("b.json", base, drift, None, False)


def test_input_label_says_reproduction_only_when_the_inputs_match_the_baseline():
    sample = [sample_row("20V001"), sample_row("20V002", "empty")]
    base = make_base(sample)
    assert "재현" in why_stats.input_label("b.json", base, SAME, sample, False)
    # 카드가 다르면 멈추고, --allow-drift를 주면 재계산이라고 표시한다
    drift = {**SAME, "recalls_sha256": "x"}
    with pytest.raises(SystemExit) as e:
        why_stats.input_label("b.json", base, drift, sample, False)
    assert "원본·카드·시험지 sha256" in str(e.value)
    assert "재현 아님" in why_stats.input_label("b.json", base, drift, sample, True)
    # 573 표본 캠페인 목록이 다르면 입력이 같아 보여도 멈춘다
    with pytest.raises(SystemExit) as e:
        why_stats.input_label("b.json", base, SAME, [sample_row("99V999")], False)
    assert "573 표본 캠페인·원인 칸 내용" in str(e.value)


def test_input_label_stops_when_only_the_cause_status_or_row_count_of_the_sample_changed():
    sample = [sample_row("20V001"), sample_row("20V002", "empty")]
    base = make_base(sample)
    # 같은 캠페인인데 원인 칸 판독 결과만 바뀜 — 205/95 같은 숫자가 달라지는데 캠페인 목록은 같다
    changed = [sample_row("20V001", "empty"), sample_row("20V002", "empty")]
    with pytest.raises(SystemExit):
        why_stats.input_label("b.json", base, SAME, changed, False)
    # 판본 sha256이 바뀜
    with pytest.raises(SystemExit):
        why_stats.input_label(
            "b.json", base, SAME, [sample[0], sample_row("20V002", "empty", pdf_sha="bb")], False
        )
    # 같은 캠페인을 한 줄 더 넣음(중복)
    with pytest.raises(SystemExit):
        why_stats.input_label("b.json", base, SAME, [*sample, sample_row("20V002", "empty")], False)
    # 내용 지문이 없는 옛 형식의 기준 파일이면 건수와 판본 sha256만 대조한다
    old = make_base(sample, with_digest=False)
    assert "재현" in why_stats.input_label("b.json", old, SAME, sample, False)
    with pytest.raises(SystemExit):
        why_stats.input_label("b.json", old, SAME, changed, False)


def test_sample_digest_ignores_row_order_and_dict_order():
    a, b = sample_row("20V001"), sample_row("20V002", "empty")
    assert why_stats.sample_digest([a, b]) == why_stats.sample_digest([b, a])
    assert why_stats.sample_digest([a, b]) != why_stats.sample_digest(
        [a, {**b, "cause_status": "filled"}]
    )


def test_main_stops_instead_of_printing_a_mixed_unit_estimate_when_recalls_are_not_one_to_one(
    monkeypatch,
):
    recalls = [
        recall("20V001000", "Brake may fail"),
        recall("20V001001", "Brake may fail"),  # 같은 캠페인에 리콜 2건
        recall("20V002000", "Brake may fail"),
    ]
    data = {
        "recalls.jsonl": recalls,
        "causes_sample.jsonl": [sample_row("20V001"), sample_row("20V002")],
        "eval.jsonl": [],
    }
    monkeypatch.setattr(why_stats, "read_jsonl", lambda path: data[path.name])
    monkeypatch.setattr(why_stats.nhtsa, "read_flat", lambda *a, **k: [])
    with pytest.raises(SystemExit) as e:
        why_stats.main()
    assert "단위가 섞여서" in str(e.value)


def test_compute_counts_a_campaign_with_several_recalls_once_per_sample_row():
    recalls = [recall("20V001000", "Brake may fail"), recall("20V001001", "caused by a weld")]
    s = why_stats.compute(recalls, [], [{"campaign": "20V001", "cause_status": "empty"}])
    assert s["sample_old"] == 1 and s["sample"] == 1


@pytest.mark.skipif(
    not (nhtsa.OUT_DIR / "recalls.jsonl").exists()
    or not (nhtsa.OUT_DIR / "causes_sample.jsonl").exists()
    or not (nhtsa.OUT_DIR / "eval.jsonl").exists()
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
    assert (s["post_recalls"], s["post_campaigns"], s["post_one_to_one"]) == (12011, 12011, True)
    overlap = why_stats.maker_overlap(
        why_stats.read_jsonl(nhtsa.OUT_DIR / "eval.jsonl"),
        why_stats.read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl"),
    )
    # 이슈 #24 B 파트의 값은 364 / 73(회사명 정리 전 카드). 회사명 대응표를 반영한 카드(DEC-036)에서는 이름이 정리돼
    # 회사 이름 전체가 질문에 그대로 든 문항만 73 → 67로 줄고, 핵심 단어가 겹치는 문항(364)은 그대로다
    info = json.loads((nhtsa.OUT_DIR / "build.json").read_text(encoding="utf-8"))
    # 옛 카드(build.json에 maker_aliases_sha256 없음)는 73, 회사명 대응표를 반영한 카드는 67 — 사본 버전에 따라 기대값이 다르다
    full_name = 67 if "maker_aliases_sha256" in info else 73
    assert overlap == {"questions": 749, "overlap": 364, "full_name": full_name}


@pytest.mark.skipif(
    not (nhtsa.OUT_DIR / "causes.jsonl").exists()
    or not (nhtsa.OUT_DIR / "causes.manifest.json").exists()
    or not (nhtsa.OUT_DIR / "recalls.jsonl").exists()
    or not (nhtsa.RAW_DIR / "FLAT_INV.zip").exists(),
    reason="573 전체 수집 결과(causes.jsonl·명세)나 원본이 없다 (data/는 커밋하지 않는다)",
)
def test_reproduces_the_full_573_numbers():
    causes_path = nhtsa.OUT_DIR / "causes.jsonl"
    causes = why_stats.read_jsonl(causes_path)
    manifest = why_stats.verify_causes(causes_path, nhtsa.OUT_DIR / "causes.manifest.json", causes)
    # 2026-10-11 재수집 완성본(DEC-047 — stated_unknown 원문 보존). 10/7 완성본 d215ff583281…과 filled·실패·줄 수가 같아 수치는 그대로다
    assert manifest["file_sha256"].startswith("6089505793dd")
    # 기준 파일에 고정한 전수 결과의 값(대상 목록·실패 목록·원인 파일·명세 파일 지문)과 같다
    base_path = nhtsa.REPO_ROOT / "scripts/defect_precedent/baseline_2026-10-06.json"
    base = json.loads(base_path.read_text(encoding="utf-8"))
    manifest_sha = hashlib.sha256((nhtsa.OUT_DIR / "causes.manifest.json").read_bytes()).hexdigest()
    assert "일치" in why_stats.full_baseline_check(base, manifest, manifest_sha, False)
    s = why_stats.full_coverage(
        why_stats.read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl"),
        nhtsa.read_flat(nhtsa.RAW_DIR / "FLAT_INV.zip", nhtsa.INV_COLS),
        causes,
        manifest["failed_campaigns"],
    )
    assert (s["causes_rows"], manifest["failures"]) == (11719, 18)
    assert (s["post_recalls"], s["post_campaigns"], s["post_with_report"]) == (12011, 12011, 11719)
    assert (s["post_either"], s["post_filled"]) == (3719, 8160)
    assert (s["unresolved_campaigns"], s["failed_campaigns"], s["unknown_recalls"]) == (23, 18, 41)
    assert (s["post_union"], s["post_union_upper"]) == (9307, 9334)
    assert (s["total_union"], s["total_union_upper"]) == (14918, 14945)


def test_the_maker_aliases_baseline_differs_from_the_old_one_only_in_the_cards():
    # 새 기준(DEC-036)은 같은 2026-10-06 원본·시험지·573 표본·전수 결과 고정값 위에서 카드만 달라진다
    folder = nhtsa.REPO_ROOT / "scripts/defect_precedent"
    old = json.loads((folder / "baseline_2026-10-06.json").read_text(encoding="utf-8"))
    new = json.loads(
        (folder / "baseline_2026-10-06_maker-aliases.json").read_text(encoding="utf-8")
    )
    for key in (
        "raw",
        "eval_action_nos",
        "rclrpt_sample",
        "causes_sample",
        "causes_full",
        "expected",
    ):
        assert new[key] == old[key], key
    assert new["build"]["raw_manifest_sha256"] == old["build"]["raw_manifest_sha256"]
    assert new["build"]["eval_sha256"] == old["build"]["eval_sha256"]
    assert new["build"]["recalls_sha256"] != old["build"]["recalls_sha256"]  # 카드가 달라졌다
    assert len(new["build"]["maker_aliases_sha256"]) == 64  # 어느 대응표로 만든 카드인지
    assert "maker_aliases_sha256" not in old["build"]
    # 대응표 확인본(main)의 해시가 새 기준에 적힌 값과 같다
    assert new["build"]["maker_aliases_sha256"] == nhtsa.sha256_aliases(nhtsa.MAKER_ALIASES)
    # 대조한 초안의 해시도 새 기준에 같은 값으로 남는다(#45 — 손으로 넣은 값이 맞는지)
    assert new["build"]["maker_aliases_draft_sha256"] == nhtsa.sha256_aliases(
        nhtsa.MAKER_ALIASES_DRAFT
    )

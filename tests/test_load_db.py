"""scripts/defect_precedent/load_db.py 테스트.

DB 없이 도는 테스트가 기본이다. `@pg` 테스트는 Postgres가 있을 때 돈다:
    docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=localtest -p 54329:5432 pgvector/pgvector:pg17
    TEST_DATABASE_URL=postgresql://postgres:localtest@localhost:54329/postgres uv run pytest tests/test_load_db.py
주소가 localhost가 아니면 실행하지 않는다 (테스트가 public 스키마를 통째로 지우므로 Supabase에 향하면 안 된다).
CI는 REQUIRE_DB_TESTS=1로 돌려서 DB 테스트가 조용히 건너뛰어지지 않게 한다 (DB가 없으면 실패).
"""

import hashlib
import json
import os
import re
from datetime import date

import pytest

from scripts.ci.db_guard import is_local_test_db
from scripts.defect_precedent import load_db

# ---------------------------------------------------------------------------
# 작은 가짜 데이터 폴더


def recall(campno, defect="Brake line may leak.", **kw):
    return {
        "campno": campno,
        "maker": "Ford Motor Company",
        "maker_group": "Ford",
        "raw_maker": "FORD MOTOR COMPANY",
        "components": ["SERVICE BRAKES"],
        "defect": defect,
        "consequence": "",
        "remedy": "Dealers will replace the line.",
        "received_date": "20230130",
        "recall_type": "V",
        "influenced_by": "MFR",
        "dup_group": campno,
        "snapshot_date": kw.pop("snapshot_date", "2026-10-06"),
        **kw,
    }


def cause(campaign, text="The gauge of the tube is insufficient.", **kw):
    return {
        "campaign": campaign,
        "versions": 1,
        "source_file": f"odi/rcl/2023/RCLRPT-{campaign}-0001.PDF",
        "submission_date": "20230201",
        "cause_text": text,
        "cause_status": "filled",
        "supplier_names": ["Alliance Aluminum"],
        "supplier_countries": ["United States"],
        "new_form": False,
        "pdfs": {"odi/rcl/2023/RCLRPT-x.PDF": "ab" * 32},
        "resolution": "auto",
        "unresolved_reasons": [],
        **kw,
    }


QUESTION = {
    "action_no": "PE23001",
    "question": "Brake line leak reports.",
    "open_date": "20230115",
    "gold_campnos": ["23V002000"],
    "set": ["all"],
}


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_baseline(tmp_path, campaigns=("24V001",)):
    """표본 원인 파일의 기대 캠페인 목록이 든 가짜 기준 파일 (실제 파일은 300개)."""
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"rclrpt_sample": [{"campaign": c} for c in campaigns]}), encoding="utf-8"
    )
    return path


def make_data_dir(
    tmp_path, snapshot="2026-10-06", recalls=None, causes=None, questions=None, manifest="a1" * 32
):
    """load_db가 읽는 파일(recalls·eval·causes_sample·build.json)을 만든다. build.json의 해시는 실제 파일에서 계산한다."""
    d = tmp_path / snapshot
    d.mkdir(parents=True)
    recalls = recalls or [
        recall("24V001000", snapshot_date=snapshot),
        recall("23V002000", snapshot_date=snapshot),
    ]
    write_jsonl(d / "recalls.jsonl", recalls)
    write_jsonl(d / "eval.jsonl", questions or [QUESTION])
    write_jsonl(d / "causes_sample.jsonl", causes or [cause("24V001")])
    (d / "build.json").write_text(
        json.dumps(
            {
                "raw_manifest_sha256": manifest,
                "recalls_sha256": sha(d / "recalls.jsonl"),
                "eval_sha256": sha(d / "eval.jsonl"),
                "snapshot_date": snapshot,
            }
        ),
        encoding="utf-8",
    )
    return d


def write_full(d, cause_rows, **override):
    """`rclrpt all`이 남기는 것과 같은 모양의 완성본 causes.jsonl + 명세를 쓴다."""
    write_jsonl(d / "causes.jsonl", cause_rows)
    manifest = {
        "kind": "full",
        "rows": len(cause_rows),
        "file_sha256": sha(d / "causes.jsonl"),
        "campaigns_sha256": load_db.campaigns_digest(r["campaign"] for r in cause_rows),
        "expected_campaigns_sha256": load_db.campaigns_digest(
            [r["campaign"] for r in cause_rows] + list(override.get("failed_campaigns", []))
        ),
        "failures": 0,
        "failed_campaigns": [],
        "failures_sha256": None,
        "expect_campaigns": len(cause_rows),
        "listing_campaigns": len(cause_rows),
        "pdftotext": "pdftotext version 25.07.0",
        "generated_at": "2026-10-07T00:00:00+00:00",
        **override,
    }
    (d / "causes.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


# ---------------------------------------------------------------------------
# 날짜


def test_parse_functions_accept_only_their_own_format():
    assert load_db.parse_compact("20230130", "x") == date(2023, 1, 30)
    assert load_db.parse_iso("2026-10-06", "x") == date(2026, 10, 6)
    # 칸마다 약속한 형식이 아니면 날짜 값이 같아도 중단한다 (입력 형식이 바뀐 신호를 놓치지 않는다)
    with pytest.raises(SystemExit):
        load_db.parse_compact("2026-10-01", "recalls.jsonl 1번째 줄 received_date")
    with pytest.raises(SystemExit):
        load_db.parse_iso("20261001", "build.json snapshot_date")


@pytest.mark.parametrize(
    "bad", ["", "2023013", "20231301", "20230230", "2023-1-5", "Jan 30, 2023", "20230130 ", None]
)
def test_parse_compact_stops_instead_of_guessing(bad):
    with pytest.raises(SystemExit) as e:
        load_db.parse_compact(bad, "recalls.jsonl 3번째 줄 received_date")
    assert "recalls.jsonl 3번째 줄 received_date" in str(e.value)  # 어디의 어떤 값인지 알려 준다


# ---------------------------------------------------------------------------
# 파일 검증


def test_load_files_reads_and_seals_rows(tmp_path):
    data = load_db.load_files(make_data_dir(tmp_path), "sample", make_baseline(tmp_path))
    assert [len(data[t]) for t in load_db.TABLES] == [2, 1, 1]
    r = data["recalls"][0]
    assert r["snapshot_date"] == date(2026, 10, 6) and r["received_date"] == date(2023, 1, 30)
    assert (
        r["defect"] == "Brake line may leak." and r["consequence"] == ""
    )  # 빈 문자열은 NULL로 바꾸지 않는다
    assert re.fullmatch(r"[0-9a-f]{64}", r["row_sha256"])
    build = data["build"]
    assert re.fullmatch(r"[0-9a-f]{16}", build["build_id"]) and r["build_id"] == build["build_id"]
    assert (
        build["causes_kind"] == "sample"
        and build["causes_rows"] == 1
        and build["causes_expected_rows"] == 1
    )
    assert build["causes_sha256"] == sha(tmp_path / "2026-10-06" / "causes_sample.jsonl")
    assert (
        build["causes_spec"]["source"] == "baseline.json"
        and "campaigns" not in build["causes_spec"]
    )


def test_row_sha256_changes_with_content_not_with_key_order():
    cols = load_db.TABLES["eval_questions"]["cols"]
    row = {
        "action_no": "A",
        "question": "q",
        "open_date": date(2023, 1, 1),
        "gold_campnos": ["x"],
        "sets": ["all"],
    }
    shuffled = dict(reversed(list(row.items())))
    assert load_db.row_sha256(row, cols) == load_db.row_sha256(shuffled, cols)
    assert load_db.row_sha256(row, cols) != load_db.row_sha256({**row, "question": "q2"}, cols)


def test_build_id_is_determined_by_all_four_input_hashes():
    base = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
    same = load_db.build_id_of(*base)
    assert same == load_db.build_id_of(*base)  # 같은 입력 → 같은 build
    for i in range(4):  # 어느 하나라도 다르면 다른 build
        changed = list(base)
        changed[i] = "e" * 64
        assert load_db.build_id_of(*changed) != same


def test_campaigns_digest_is_order_independent_and_pinned():
    # rclrpt.campaigns_digest와 같은 값이어야 한다 (두 모듈의 골든 값이 같다)
    assert load_db.campaigns_digest(["24V002", "24V001"]) == load_db.campaigns_digest(
        ["24V001", "24V002"]
    )
    assert load_db.campaigns_digest(["24V001", "24V002"]) == (
        "7d8d70be5ca2cbddacab9b80813f827e412aca999b939a204b31b10ada753aff"
    )


def test_load_files_stops_on_tampered_file(tmp_path):
    d = make_data_dir(tmp_path)
    (d / "recalls.jsonl").write_text(
        (d / "recalls.jsonl").read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "sample", make_baseline(tmp_path))
    assert "build.json과 다르다" in str(e.value)


def test_load_files_stops_when_gold_recall_or_campaign_is_missing(tmp_path):
    bad_q = make_data_dir(tmp_path / "a", questions=[{**QUESTION, "gold_campnos": ["99V999000"]}])
    with pytest.raises(SystemExit) as e:
        load_db.load_files(bad_q, "sample", make_baseline(tmp_path))
    assert "정답 리콜이 recalls에 없다" in str(e.value)
    bad_c = make_data_dir(tmp_path / "b", causes=[cause("99V999")])
    with pytest.raises(SystemExit) as e:
        load_db.load_files(bad_c, "sample", make_baseline(tmp_path, ["99V999"]))
    assert "앞 6자리와도 맞지 않는다" in str(e.value)


def test_load_files_stops_when_snapshot_date_differs_from_build(tmp_path):
    d = make_data_dir(tmp_path, recalls=[recall("24V001000", snapshot_date="2026-10-05")])
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "sample", make_baseline(tmp_path))
    assert "snapshot_date가 build.json과 다르다" in str(e.value)


# ---------------------------------------------------------------------------
# 원인 파일 완전성 — 사람이 입력한 숫자가 아니라 독립된 명세와 대조


def test_sample_must_match_the_baseline_campaign_list_exactly(tmp_path):
    recalls = [recall(f"{c}000") for c in ("24V001", "23V002", "25V003")]
    # 기준 파일은 2개 캠페인인데 표본 파일이 1개뿐 (중간까지만 만들어짐)
    short = make_data_dir(tmp_path / "a", recalls=recalls, causes=[cause("24V001")])
    with pytest.raises(SystemExit) as e:
        load_db.load_files(short, "sample", make_baseline(tmp_path, ["24V001", "23V002"]))
    assert "명세(baseline.json)의 2줄과 다르다" in str(e.value)
    # 줄 수는 같지만 다른 캠페인 (기준 파일에 없는 캠페인이 섞임)
    wrong = make_data_dir(
        tmp_path / "b", recalls=recalls, causes=[cause("24V001"), cause("25V003")]
    )
    with pytest.raises(SystemExit) as e:
        load_db.load_files(wrong, "sample", make_baseline(tmp_path, ["24V001", "23V002"]))
    assert (
        "표본 목록과 다르다" in str(e.value)
        and "23V002" in str(e.value)
        and "25V003" in str(e.value)
    )
    # 기준 파일과 정확히 같으면 통과
    ok = make_data_dir(tmp_path / "c", recalls=recalls, causes=[cause("24V001"), cause("23V002")])
    assert (
        load_db.load_files(ok, "sample", make_baseline(tmp_path, ["24V001", "23V002"]))["build"][
            "causes_expected_rows"
        ]
        == 2
    )


def test_the_committed_baseline_lists_the_300_sample_campaigns():
    spec = load_db.causes_spec(load_db.PROCESSED, "sample", load_db.BASELINE)
    assert spec["rows"] == 300 and len(set(spec["campaigns"])) == 300
    assert spec["campaigns_sha256"] == load_db.campaigns_digest(spec["campaigns"])


def test_full_requires_a_manifest_that_matches_the_file(tmp_path):
    d = make_data_dir(tmp_path)
    write_full(d, [cause("24V001"), cause("23V002")])
    baseline = make_baseline(tmp_path)
    full = load_db.load_files(d, "full", baseline)
    assert full["build"]["causes_kind"] == "full" and full["build"]["causes_expected_rows"] == 2
    assert full["build"]["causes_spec"]["source"] == "causes.manifest.json"
    assert full["build"]["causes_spec"]["file_sha256"] == sha(d / "causes.jsonl")

    # 명세가 없으면 올리지 않는다 (중간까지만 만든 파일에는 명세가 없다)
    (d / "causes.manifest.json").unlink()
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", baseline)
    assert "causes.manifest.json이 없다" in str(e.value)


@pytest.mark.parametrize(
    "tamper, message",
    [
        (
            {"rows": 5, "expect_campaigns": 5},
            "명세(causes.manifest.json)의 5줄과 다르다",
        ),  # 파일이 명세보다 짧음
        ({"expect_campaigns": 3}, "완성본이 아니다"),  # 기대 캠페인 수와 줄 수가 다름
        ({"file_sha256": "00" * 32}, "sha256이"),  # 명세를 만든 뒤 파일이 바뀜
        ({"campaigns_sha256": "00" * 32}, "campaigns_sha256과 다르다"),  # 캠페인 목록이 다름
        ({"kind": "sample"}, "종류가 full이 아니다"),
        (
            {"failures": 1, "failed_campaigns": []},
            "실패 캠페인 목록은 0개다",
        ),  # 실패 건수와 목록이 다름
        ({"failures": 1, "failed_campaigns": ["25V003"]}, "완성본이 아니다"),  # 2 + 1 != 기대 2
        (
            {"expect_campaigns": 3, "failures": 1, "failed_campaigns": ["24V001"]},
            "실패로 기록한 캠페인이 들어 있다",
        ),
    ],
)
def test_full_stops_when_the_file_does_not_match_the_manifest(tmp_path, tamper, message):
    d = make_data_dir(tmp_path)
    write_full(d, [cause("24V001"), cause("23V002")], **tamper)
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", make_baseline(tmp_path))
    assert message in str(e.value)


def test_full_accepts_recorded_failures_only_when_rows_plus_failures_match(tmp_path):
    d = make_data_dir(tmp_path)
    write_full(
        d,
        [cause("24V001"), cause("23V002")],
        expect_campaigns=3,
        failures=1,
        failed_campaigns=["25V003"],
    )
    build = load_db.load_files(d, "full", make_baseline(tmp_path))["build"]
    assert build["causes_rows"] == 2 and build["causes_expected_rows"] == 2
    # 원본 결함으로 읽지 못해 수용한 캠페인 목록이 명세(causes_spec)에 그대로 남는다
    assert (
        build["causes_spec"]["failed_campaigns"] == ["25V003"]
        and build["causes_spec"]["failures"] == 1
    )
    assert build["causes_spec"]["expect_campaigns"] == 3


def test_full_requires_success_plus_failed_to_equal_the_expected_campaign_list(tmp_path):
    expected = load_db.campaigns_digest(["24V001", "23V002", "25V003"])
    # 실제 기대 목록은 24V001·23V002·25V003인데 파일에는 앞 둘뿐이고 명세가 실패를 25V099라고 잘못 기록함 — 줄 수는 맞는다
    d = make_data_dir(tmp_path / "a")
    write_full(
        d,
        [cause("24V001"), cause("23V002")],
        expect_campaigns=3,
        failures=1,
        failed_campaigns=["25V099"],
        expected_campaigns_sha256=expected,
    )
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", make_baseline(tmp_path))
    assert "기대 캠페인 목록" in str(e.value)
    # 실패 번호가 맞으면 통과한다
    d = make_data_dir(tmp_path / "b")
    write_full(
        d,
        [cause("24V001"), cause("23V002")],
        expect_campaigns=3,
        failures=1,
        failed_campaigns=["25V003"],
        expected_campaigns_sha256=expected,
    )
    assert load_db.load_files(d, "full", make_baseline(tmp_path))["build"]["causes_rows"] == 2
    # 같은 실패 번호를 두 번 적어 줄 수를 맞추는 경우
    d = make_data_dir(tmp_path / "c")
    write_full(
        d,
        [cause("24V001"), cause("23V002")],
        expect_campaigns=4,
        failures=2,
        failed_campaigns=["25V003", "25V003"],
    )
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", make_baseline(tmp_path))
    assert "겹친다" in str(e.value)
    # 기대 목록 지문이 명세에 없으면 중단
    d = make_data_dir(tmp_path / "d")
    write_full(d, [cause("24V001"), cause("23V002")])
    m = json.loads((d / "causes.manifest.json").read_text(encoding="utf-8"))
    del m["expected_campaigns_sha256"]
    (d / "causes.manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", make_baseline(tmp_path))
    assert "expected_campaigns_sha256 칸이 없다" in str(e.value)


def test_full_stops_when_the_file_was_edited_after_the_manifest(tmp_path):
    d = make_data_dir(tmp_path)
    write_full(d, [cause("24V001"), cause("23V002")])
    (d / "causes.jsonl").write_text(
        (d / "causes.jsonl").read_text(encoding="utf-8").replace("insufficient", "ok"),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", make_baseline(tmp_path))
    assert "sha256이 causes.manifest.json과 다르다" in str(e.value)


def test_causes_kind_is_never_chosen_automatically(tmp_path):
    d = make_data_dir(tmp_path)
    write_full(d, [cause("24V001")])  # 전체 파일이 있어도 sample을 고르면 표본을 쓴다
    baseline = make_baseline(tmp_path)
    assert (
        load_db.load_files(d, "sample", baseline)["build"]["causes_file"] == "causes_sample.jsonl"
    )
    assert load_db.load_files(d, "full", baseline)["build"]["causes_file"] == "causes.jsonl"
    with pytest.raises(SystemExit) as e:  # --causes를 생략하면 argparse가 막는다
        load_db.main(["check", "--data-dir", str(d)])
    assert e.value.code == 2


def test_the_human_typed_expect_rows_option_no_longer_exists(tmp_path):
    d = make_data_dir(tmp_path)
    with pytest.raises(SystemExit) as e:
        load_db.main(["check", "--causes", "sample", "--expect-rows", "1", "--data-dir", str(d)])
    assert e.value.code == 2


def test_check_command_reports_the_build_and_the_spec(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        load_db, "BASELINE", make_baseline(tmp_path)
    )  # 명령에는 기준 파일을 바꾸는 옵션이 없다
    d = make_data_dir(tmp_path)
    load_db.main(
        [
            "check",
            "--causes",
            "sample",
            "--data-dir",
            str(d),
        ]
    )
    out = capsys.readouterr().out
    assert "검증 통과" in out and "baseline.json" in out and re.search(r"build [0-9a-f]{16}", out)


# ---------------------------------------------------------------------------
# build 비교


def test_describe_changes_names_the_build_the_causes_were_compared_with():
    counts = {"new": 0, "changed": 0, "removed": 0, "unchanged": 2, "changed_columns": {}}
    summary = {
        "vs": "2026-10-06",
        "vs_build": "bbbb",
        "recalls": counts,
        "eval_questions": counts,
        # 10/5 전체본 → 10/6 표본 → 10/7 전체본: 리콜은 10/6과, 원인은 같은 종류인 10/5 전체본과 비교한다
        "causes": {**counts, "vs": "2026-10-05", "vs_build": "aaaa"},
    }
    lines = load_db.describe_changes(summary)
    assert lines[0].startswith("직전 날짜(2026-10-06, build bbbb)")
    assert "  recalls: 새로 생김" in lines[1]  # 직전 날짜와 같은 기준이면 따로 적지 않는다
    assert any(x.startswith("  causes [2026-10-05, build aaaa 대비]:") for x in lines)
    # 같은 build와 비교했다면 따로 적지 않는다
    same = {**summary, "causes": {**counts, "vs": "2026-10-06", "vs_build": "bbbb"}}
    assert any(x.startswith("  causes: 새로 생김") for x in load_db.describe_changes(same))


def test_diff_rows_counts_new_changed_removed_unchanged_and_columns():
    cols = ["campno", "defect", "remedy"]

    def seal(rows):
        return {r["campno"]: {**r, "row_sha256": load_db.row_sha256(r, cols)} for r in rows}

    prev = seal(
        [
            {"campno": "A", "defect": "d", "remedy": "r"},
            {"campno": "B", "defect": "d", "remedy": "r"},
            {"campno": "C", "defect": "d", "remedy": "r"},
        ]
    )
    new = seal(
        [
            {"campno": "A", "defect": "d", "remedy": "r"},  # 그대로
            {"campno": "B", "defect": "d2", "remedy": "r2"},  # 바뀜 (두 칸)
            {"campno": "D", "defect": "d", "remedy": "r"},  # 새로 생김 (C는 사라짐)
        ]
    )
    assert load_db.diff_rows(prev, new, cols) == {
        "new": 1,
        "changed": 1,
        "removed": 1,
        "unchanged": 1,
        "changed_columns": {"defect": 1, "remedy": 1},
    }


# ---------------------------------------------------------------------------
# 스키마와 스크립트가 같은 칸을 쓰는가


def _schema_columns() -> dict[str, list[str]]:
    """schema.sql의 create table에서 칸 이름을 읽는다 (생성 칸 campaign6은 DB가 채우므로 뺀다)."""
    text = load_db.SCHEMA.read_text(encoding="utf-8")
    tables = {}
    for name, body in re.findall(r"create table if not exists (\w+) \((.*?)\n\);", text, re.S):
        cols = []
        for line in body.splitlines():
            line = line.split("--")[0].strip()
            if not line or line.startswith(("primary key", "check", "constraint")):
                continue
            if "generated always" not in line:
                cols.append(line.split()[0])
        tables[name] = cols
    return tables


def test_load_files_stops_with_a_clear_message_when_recalls_have_no_maker_group(tmp_path):
    old_cards = [
        {k: v for k, v in recall(c, snapshot_date="2026-10-06").items() if k != "maker_group"}
        for c in ("24V001000", "23V002000")
    ]
    d = make_data_dir(tmp_path, recalls=old_cards)
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "sample", make_baseline(tmp_path))
    assert "maker_group 칸이 없다" in str(e.value) and "nhtsa build" in str(e.value)


def test_load_files_carries_maker_group_into_the_recalls_rows(tmp_path):
    d = make_data_dir(tmp_path)
    data = load_db.load_files(d, "sample", make_baseline(tmp_path))
    assert {r["maker_group"] for r in data["recalls"]} == {"Ford"}
    # maker_group이 바뀌면 행 해시도 달라져 변경 요약(바뀐 칸)에 잡힌다
    a = {**data["recalls"][0]}
    b = {**a, "maker_group": "Other"}
    cols = load_db.TABLES["recalls"]["cols"]
    assert load_db.row_sha256(a, cols) != load_db.row_sha256(b, cols)


def test_loader_columns_match_schema():
    schema = _schema_columns()
    assert set(schema) == {"data_builds", *load_db.TABLES}
    for table in load_db.TABLES:
        assert set(load_db.db_columns(table)) == set(schema[table]), table
    # loaded_at처럼 DB가 기본값으로 채우는 칸만 적재 칸에 없다
    assert set(schema["data_builds"]) - set(load_db.BUILD_COLS) == {"loaded_at"}


def test_sql_helpers():
    sql = load_db.insert_sql("eval_questions")
    assert sql.startswith(
        "insert into eval_questions (build_id, snapshot_date, action_no, question, open_date, gold_campnos, sets, row_sha256) values"
    )
    # 이미 있는 build를 고쳐 쓰는 SQL은 없다
    assert "on conflict" not in load_db.insert_build_sql()


def test_the_official_sample_baseline_cannot_be_replaced_from_the_command_line(tmp_path):
    # 임의의 기준 파일로 300건 미만의 불완전한 표본이 정상 데이터로 올라가는 것을 막는다
    for command in ("check", "load"):
        with pytest.raises(SystemExit) as e:
            load_db.main(
                [command, "--causes", "sample", "--baseline", str(make_baseline(tmp_path))]
            )
        assert e.value.code == 2


def test_schema_has_build_keys_join_column_views_and_row_level_security():
    text = load_db.SCHEMA.read_text(encoding="utf-8")
    assert "generated always as (left(campno, 6)) stored" in text
    for pk in (
        "primary key (build_id, campno)",
        "primary key (build_id, action_no)",
        "primary key (build_id, campaign)",
    ):
        assert pk in text
    assert "build_id             text primary key" in text and "pruned_at" not in text
    assert re.search(r"create or replace view latest_build with \(security_invoker = true\)", text)
    for table in load_db.TABLES:
        assert f"alter table {table}" in text
        # 뷰는 기본이 만든 사람 권한으로 읽어 RLS를 우회하므로 security_invoker가 반드시 필요하다
        assert re.search(
            rf"create or replace view {table}_latest with \(security_invoker = true\)", text
        )
    assert "alter table data_builds" in text and "enable row level security" in text
    # 표본 전용 뷰도 같은 보호(security_invoker)를 받는다
    for view in (
        "latest_sample_build",
        "recalls_latest_sample",
        "eval_questions_latest_sample",
        "causes_latest_sample",
    ):
        assert re.search(rf"create or replace view {view} with \(security_invoker = true\)", text)
    assert (
        "order by (causes_kind = 'full') desc, snapshot_date desc" in text
    )  # 날짜보다 종류가 먼저


# ---------------------------------------------------------------------------
# Postgres (TEST_DATABASE_URL이 있을 때만, CI는 항상)

PG_URL = os.environ.get("TEST_DATABASE_URL", "")
PG_USABLE = bool(PG_URL) and is_local_test_db(
    PG_URL
)  # host·hostaddr까지 본다(scripts/ci/db_guard.py)
REQUIRE_DB = os.environ.get("REQUIRE_DB_TESTS") == "1"
pg = pytest.mark.skipif(
    not PG_USABLE and not REQUIRE_DB, reason="TEST_DATABASE_URL이 없거나 localhost가 아니다"
)


@pytest.fixture
def pgconn(monkeypatch):
    import psycopg

    if not PG_USABLE:
        pytest.fail(
            "REQUIRE_DB_TESTS=1인데 TEST_DATABASE_URL이 없거나 localhost가 아니다 — DB 테스트를 건너뛸 수 없다"
        )
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute("drop schema public cascade; create schema public;")
        load_db.main(["schema"])
        load_db.main(["schema"])  # 여러 번 적용해도 된다
        yield conn


def load(d, kind="sample", baseline=None):
    argv = ["load", "--causes", kind, "--data-dir", str(d)]
    old = load_db.BASELINE
    if baseline:
        load_db.BASELINE = (
            baseline  # 운영 명령에는 기준 파일을 바꾸는 옵션이 없다 — 테스트만 상수를 바꾼다
        )
    try:
        load_db.main(argv)
    finally:
        load_db.BASELINE = old


def counts(conn, table, build_id):
    return conn.execute(
        f"select count(*) from {table} where build_id = %s", (build_id,)
    ).fetchone()[0]


def build_ids(conn):
    return [
        r[0]
        for r in conn.execute(
            "select build_id from data_builds order by snapshot_date, loaded_at"
        ).fetchall()
    ]


def latest(conn):
    return conn.execute("select build_id from latest_build").fetchone()[0]


@pg
def test_pg_builds_on_different_dates_are_kept_and_compared(pgconn, tmp_path):
    baseline = make_baseline(tmp_path)
    s1 = make_data_dir(
        tmp_path / "x",
        "2026-10-06",
        recalls=[
            recall("24V001000", snapshot_date="2026-10-06"),
            recall("24V001001", snapshot_date="2026-10-06"),  # 같은 캠페인(24V001)에 리콜 2건
            recall("23V002000", snapshot_date="2026-10-06"),
        ],
        manifest="a1" * 32,
    )
    load(s1, baseline=baseline)
    load(s1, baseline=baseline)  # 같은 build를 다시 올려도 줄 수는 그대로
    (b1,) = build_ids(pgconn)
    assert [counts(pgconn, t, b1) for t in load_db.TABLES] == [3, 1, 1]
    assert (
        pgconn.execute("select change_summary->>'vs' from data_builds").fetchone()[0] is None
    )  # 첫 build
    # campaign6 조인: 원인 1건이 카드 2건에 붙는다 (일대다)
    n = pgconn.execute(
        "select count(*), count(distinct r.campno) from recalls r join causes c "
        "on c.build_id = r.build_id and c.campaign = r.campaign6 where r.build_id = %s",
        (b1,),
    ).fetchone()
    assert n == (2, 2)

    s2 = make_data_dir(
        tmp_path / "y",
        "2026-10-07",
        recalls=[
            recall("24V001000", snapshot_date="2026-10-07"),  # 그대로
            recall(
                "23V002000", "Brake line may rupture.", snapshot_date="2026-10-07"
            ),  # 바뀜(defect)
            recall("25V003000", snapshot_date="2026-10-07"),  # 새로 생김 (24V001001은 사라짐)
        ],
        manifest="b2" * 32,
    )
    load(s2, baseline=baseline)
    b1, b2 = build_ids(pgconn)
    assert b1 != b2
    # 두 build가 모두 남는다
    assert [counts(pgconn, t, b1) for t in load_db.TABLES] == [3, 1, 1]
    assert [counts(pgconn, t, b2) for t in load_db.TABLES] == [3, 1, 1]
    s = pgconn.execute(
        "select change_summary from data_builds where build_id = %s", (b2,)
    ).fetchone()[0]
    assert s["vs"] == "2026-10-06" and s["vs_build"] == b1
    assert s["recalls"] == {
        "new": 1,
        "changed": 1,
        "removed": 1,
        "unchanged": 1,
        "changed_columns": {"defect": 1},
    }
    assert s["eval_questions"]["unchanged"] == 1 and s["causes"]["unchanged"] == 1
    # *_latest 뷰는 최신 build만 보여 준다
    assert latest(pgconn) == b2
    assert pgconn.execute(
        "select build_id, count(*) from recalls_latest group by 1"
    ).fetchall() == [(b2, 3)]


@pg
def test_pg_a_sample_is_never_compared_with_a_full_build_so_nothing_is_reported_as_removed(
    pgconn, tmp_path
):
    baseline = make_baseline(tmp_path)
    day1 = make_data_dir(tmp_path / "d1", "2026-10-06", manifest="a1" * 32)
    load(day1, "sample", baseline)  # 표본 원인 1건
    write_full(day1, [cause("24V001"), cause("23V002")])
    load(day1, "full", baseline)  # 같은 날짜의 전체본 원인 2건
    day2 = make_data_dir(tmp_path / "d2", "2026-10-07", manifest="b2" * 32)
    load(day2, "sample", baseline)  # 다음 날짜의 표본 원인 1건
    summary = pgconn.execute(
        "select change_summary from data_builds where snapshot_date = '2026-10-07'"
    ).fetchone()[0]
    # 원인은 직전 표본과만 비교한다: 전체본(2건)과 비교했다면 1건이 사라졌다고 잘못 기록됐을 것이다
    assert summary["causes"]["removed"] == 0 and summary["causes"]["unchanged"] == 1
    sample_day1 = pgconn.execute(
        "select build_id from data_builds where snapshot_date = '2026-10-06' and causes_kind = 'sample'"
    ).fetchone()[0]
    assert summary["causes"]["vs_build"] == sample_day1
    # 전체본은 직전 날짜의 표본이 아니라 직전 전체본(10/6)과 비교한다
    day3 = make_data_dir(tmp_path / "d3", "2026-10-08", manifest="c3" * 32)
    write_full(day3, [cause("24V001"), cause("23V002")])
    load(day3, "full", baseline)
    full3 = pgconn.execute(
        "select change_summary from data_builds where snapshot_date = '2026-10-08'"
    ).fetchone()[0]
    assert full3["causes"]["vs_build"] is not None  # 10/6 전체본과 비교한다
    assert full3["causes"]["removed"] == 0


@pg
def test_pg_the_first_full_build_is_not_compared_with_an_earlier_sample(pgconn, tmp_path):
    baseline = make_baseline(tmp_path)
    load(make_data_dir(tmp_path / "d1", "2026-10-06", manifest="a1" * 32), "sample", baseline)
    day2 = make_data_dir(tmp_path / "d2", "2026-10-07", manifest="b2" * 32)
    write_full(day2, [cause("24V001"), cause("23V002")])
    load(day2, "full", baseline)
    summary = pgconn.execute(
        "select change_summary from data_builds where snapshot_date = '2026-10-07'"
    ).fetchone()[0]
    # 같은 종류의 이전 build가 없으면 비교하지 않고 그렇게 적는다 (표본과 비교하면 '새로 생김'이 부풀려진다)
    assert "같은 종류(full)의 이전 build가 없어" in summary["causes"]["skipped"]
    # 리콜·시험지는 종류와 무관하게 직전 날짜와 비교한다
    assert summary["recalls"]["unchanged"] == 2 and summary["vs"] == "2026-10-06"


@pg
def test_pg_same_date_different_content_is_a_separate_build_and_nothing_is_overwritten(
    pgconn, tmp_path
):
    baseline = make_baseline(tmp_path)
    load(make_data_dir(tmp_path / "a", "2026-10-06", manifest="a1" * 32), baseline=baseline)
    other = make_data_dir(
        tmp_path / "b",
        "2026-10-06",
        recalls=[
            recall("24V001000", "Different text.", snapshot_date="2026-10-06"),
            recall("23V002000", snapshot_date="2026-10-06"),
        ],
        manifest="c3" * 32,
    )
    load(other, baseline=baseline)
    first, second = build_ids(pgconn)
    assert first != second  # 같은 날짜라도 내용이 다르면 다른 build
    defects = dict(
        pgconn.execute("select build_id, defect from recalls where campno = '24V001000'").fetchall()
    )
    assert defects == {
        first: "Brake line may leak.",
        second: "Different text.",
    }  # 첫 build는 그대로 남는다
    assert latest(pgconn) == second  # 같은 날짜·같은 종류면 나중에 올린 것


@pg
def test_pg_same_date_sample_and_full_are_both_kept_and_full_wins_for_queries(pgconn, tmp_path):
    baseline = make_baseline(tmp_path)
    d = make_data_dir(tmp_path / "s", "2026-10-06")
    load(d, "sample", baseline)
    (sample_build,) = build_ids(pgconn)
    write_full(d, [cause("24V001", "Different text."), cause("23V002")])
    load(d, "full", baseline)
    ids = build_ids(pgconn)
    full_build = next(b for b in ids if b != sample_build)
    # 표본 build의 원인 문장은 교체되지 않고 그대로 남는다 — 같은 날짜가 다른 내용을 가리키게 되지 않는다
    assert (
        pgconn.execute(
            "select cause_text from causes where build_id = %s", (sample_build,)
        ).fetchone()[0]
        == "The gauge of the tube is insufficient."
    )
    assert counts(pgconn, "causes", full_build) == 2 and counts(pgconn, "causes", sample_build) == 1
    kinds = dict(pgconn.execute("select build_id, causes_kind from data_builds").fetchall())
    assert kinds == {sample_build: "sample", full_build: "full"}
    spec = pgconn.execute(
        "select causes_spec from data_builds where build_id = %s", (full_build,)
    ).fetchone()[0]
    assert spec["source"] == "causes.manifest.json" and spec["rows"] == 2
    # 조회는 전체본을 쓴다. 표본 build를 나중에 다시 올려도 조회가 표본으로 돌아가지 않는다
    assert latest(pgconn) == full_build
    load(d, "sample", baseline)
    assert latest(pgconn) == full_build
    assert pgconn.execute("select count(*) from causes_latest").fetchone()[0] == 2


@pg
def test_pg_has_no_command_that_deletes_builds(pgconn, tmp_path):
    baseline = make_baseline(tmp_path)
    for day, manifest in (("2026-10-06", "a1" * 32), ("2026-10-07", "b2" * 32)):
        load(make_data_dir(tmp_path, day, manifest=manifest), baseline=baseline)
    with pytest.raises(
        SystemExit
    ):  # prune 같은 삭제 명령은 없다 — 지운 데이터를 되살릴 보관소가 생기기 전에는 두지 않는다
        load_db.main(["prune", "--keep", "1", "--apply"])
    assert (
        pgconn.execute("select count(*) from recalls").fetchone()[0] == 4
    )  # 두 build가 그대로 남는다
    assert "pruned_at" not in [
        r[0]
        for r in pgconn.execute(
            "select column_name from information_schema.columns where table_name = 'data_builds'"
        ).fetchall()
    ]


@pg
def test_pg_schema_adds_maker_group_to_a_recalls_table_created_before_it_existed(pgconn):
    # 대응표를 반영하기 전 스키마로 이미 만들어진 DB를 흉내 낸다 (칸과, 그 칸을 쓰는 뷰를 함께 지운다)
    pgconn.execute("alter table recalls drop column maker_group cascade")
    cols = lambda: {  # noqa: E731
        r[0]
        for r in pgconn.execute(
            "select column_name from information_schema.columns where table_name = 'recalls'"
        ).fetchall()
    }
    assert "maker_group" not in cols()
    load_db.main(["schema"])  # 다시 적용하면 칸이 더해지고 뷰도 다시 만들어진다
    assert "maker_group" in cols()
    assert pgconn.execute("select maker_group from recalls_latest limit 1").fetchall() == []
    load_db.main(["schema"])  # 여러 번 적용해도 된다


@pg
def test_pg_a_newer_sample_never_hides_an_older_full_build_from_the_default_views(pgconn, tmp_path):
    baseline = make_baseline(tmp_path)
    old = make_data_dir(tmp_path / "old", "2026-10-06", manifest="a1" * 32)
    write_full(old, [cause("24V001"), cause("23V002")])
    load(old, "full", baseline)
    (full_build,) = build_ids(pgconn)
    # 이후 날짜의 표본(원인 1건)을 올려도 평소 조회는 전체본(원인 2건)을 그대로 보여 준다
    new = make_data_dir(tmp_path / "new", "2026-10-07", manifest="b2" * 32)
    load(new, "sample", baseline)
    sample_build = next(b for b in build_ids(pgconn) if b != full_build)
    assert latest(pgconn) == full_build
    assert pgconn.execute("select count(*) from causes_latest").fetchone()[0] == 2
    # 표본만 보는 뷰는 가장 최근 표본을 보여 준다
    assert pgconn.execute("select build_id from latest_sample_build").fetchone()[0] == sample_build
    assert pgconn.execute("select count(*) from causes_latest_sample").fetchone()[0] == 1
    assert pgconn.execute("select count(*) from recalls_latest_sample").fetchone()[0] == 2
    # 전체본이 아직 없을 때는 표본이 기본 조회가 된다
    pgconn.execute("delete from causes where build_id = %s", (full_build,))
    pgconn.execute("delete from eval_questions where build_id = %s", (full_build,))
    pgconn.execute("delete from recalls where build_id = %s", (full_build,))
    pgconn.execute("delete from data_builds where build_id = %s", (full_build,))
    assert latest(pgconn) == sample_build


@pg
def test_pg_rls_blocks_api_roles_even_through_views(pgconn, tmp_path):
    load(make_data_dir(tmp_path), baseline=make_baseline(tmp_path))
    pgconn.execute("drop role if exists api_user")
    pgconn.execute("create role api_user nologin")
    pgconn.execute("grant usage on schema public to api_user")
    pgconn.execute("grant select on all tables in schema public to api_user")
    pgconn.execute("set role api_user")
    try:
        # 정책이 없어서 테이블도, security_invoker 뷰도 한 줄도 보이지 않는다
        for relation in (
            "recalls",
            "recalls_latest",
            "causes_latest",
            "eval_questions_latest",
            "latest_build",
            "recalls_latest_sample",
            "causes_latest_sample",
            "eval_questions_latest_sample",
            "latest_sample_build",
            "data_builds",
        ):
            assert pgconn.execute(f"select count(*) from {relation}").fetchone()[0] == 0, relation
    finally:
        pgconn.execute("reset role")
    assert pgconn.execute("select count(*) from recalls_latest").fetchone()[0] == 2


@pg
def test_pg_reloading_an_existing_build_never_rewrites_it(pgconn, tmp_path, capsys):
    baseline = make_baseline(tmp_path)
    d = make_data_dir(tmp_path / "x", "2026-10-06")
    load(d, baseline=baseline)
    (b1,) = build_ids(pgconn)
    before = pgconn.execute(
        "select loaded_at, change_summary::text from data_builds where build_id = %s", (b1,)
    ).fetchone()
    capsys.readouterr()
    load(d, baseline=baseline)  # 같은 내용 — 아무것도 바꾸지 않고 성공한다
    assert "아무것도 바꾸지 않았다" in capsys.readouterr().out
    assert (
        pgconn.execute(
            "select loaded_at, change_summary::text from data_builds where build_id = %s", (b1,)
        ).fetchone()
        == before
    )
    # 같은 build_id인데 저장된 행의 내용이 다르면(적재 코드가 바뀐 경우 등) 덮어쓰지 않고 중단한다
    pgconn.execute("update recalls set row_sha256 = repeat('0', 64) where build_id = %s", (b1,))
    with pytest.raises(SystemExit) as e:
        load(d, baseline=baseline)
    assert "recalls 행" in str(e.value) and "덮어쓰지 않는다" in str(e.value)
    assert (
        pgconn.execute(
            "select count(*) from recalls where build_id = %s and row_sha256 = repeat('0', 64)",
            (b1,),
        ).fetchone()[0]
        == 2
    )  # 고쳐 쓰지 않았다
    # 원인 명세만 다른 경우도 마찬가지
    pgconn.execute("update data_builds set causes_spec = '{}'::jsonb where build_id = %s", (b1,))
    with pytest.raises(SystemExit) as e:
        load(d, baseline=baseline)
    assert "원인 명세" in str(e.value)


@pg
def test_pg_failed_load_rolls_back_everything(pgconn, tmp_path):
    import psycopg

    baseline = make_baseline(tmp_path)
    load(make_data_dir(tmp_path / "ok", "2026-10-06"), baseline=baseline)
    # 둘째 build의 마지막 테이블(causes)에서 제약 위반이 나게 한다 — 앞서 올린 recalls·eval·data_builds도 함께 되돌아가야 한다
    broken = make_data_dir(
        tmp_path / "bad",
        "2026-10-07",
        causes=[cause("24V001", cause_status="bogus")],
        manifest="b2" * 32,
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        load(broken, baseline=baseline)
    (only,) = build_ids(pgconn)
    assert [counts(pgconn, t, only) for t in load_db.TABLES] == [2, 1, 1]  # 이전 build는 그대로
    assert (
        pgconn.execute("select count(*) from recalls").fetchone()[0] == 2
    )  # 실패한 build의 줄은 남지 않는다

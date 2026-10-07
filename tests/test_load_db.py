"""scripts/defect_precedent/load_db.py 테스트.

DB 없이 도는 테스트가 기본이다. 맨 아래 `pg_` 테스트는 로컬 Postgres가 있을 때만 돈다:
    docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=localtest -p 54329:5432 postgres:17
    TEST_DATABASE_URL=postgresql://postgres:localtest@localhost:54329/postgres uv run pytest tests/test_load_db.py
주소가 localhost가 아니면 실행하지 않는다 (테스트가 public 스키마를 통째로 지우므로 Supabase에 향하면 안 된다).
"""

import hashlib
import json
import os
import re
from datetime import date
from urllib.parse import urlparse

import pytest

from scripts.defect_precedent import load_db

# ---------------------------------------------------------------------------
# 작은 가짜 데이터 폴더


def recall(campno, defect="Brake line may leak.", **kw):
    return {
        "campno": campno,
        "maker": "Ford Motor Company",
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


def make_data_dir(
    tmp_path, snapshot="2026-10-06", recalls=None, causes=None, questions=None, manifest="a1" * 32
):
    """load_db가 읽는 파일 4개(recalls·eval·causes_sample·build.json)를 만든다. build.json의 해시는 실제 파일에서 계산한다."""
    d = tmp_path / snapshot
    d.mkdir(parents=True)
    recalls = recalls or [
        recall("24V001000", snapshot_date=snapshot),
        recall("23V002000", snapshot_date=snapshot),
    ]
    write_jsonl(d / "recalls.jsonl", recalls)
    write_jsonl(d / "eval.jsonl", questions or [QUESTION])
    write_jsonl(d / "causes_sample.jsonl", causes or [cause("24V001")])
    sha = lambda name: hashlib.sha256((d / name).read_bytes()).hexdigest()  # noqa: E731
    (d / "build.json").write_text(
        json.dumps(
            {
                "raw_manifest_sha256": manifest,
                "recalls_sha256": sha("recalls.jsonl"),
                "eval_sha256": sha("eval.jsonl"),
                "snapshot_date": snapshot,
            }
        ),
        encoding="utf-8",
    )
    return d


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
    data = load_db.load_files(make_data_dir(tmp_path), "sample")
    assert [len(data[t]) for t in load_db.TABLES] == [2, 1, 1]
    r = data["recalls"][0]
    assert r["snapshot_date"] == date(2026, 10, 6) and r["received_date"] == date(2023, 1, 30)
    assert (
        r["defect"] == "Brake line may leak." and r["consequence"] == ""
    )  # 빈 문자열은 NULL로 바꾸지 않는다
    assert re.fullmatch(r"[0-9a-f]{64}", r["row_sha256"])
    assert data["build"]["causes_kind"] == "sample" and data["build"]["causes_rows"] == 1
    assert (
        data["build"]["causes_sha256"]
        == hashlib.sha256(
            (tmp_path / "2026-10-06" / "causes_sample.jsonl").read_bytes()
        ).hexdigest()
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


def test_load_files_stops_on_tampered_file(tmp_path):
    d = make_data_dir(tmp_path)
    (d / "recalls.jsonl").write_text(
        (d / "recalls.jsonl").read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "sample")
    assert "build.json과 다르다" in str(e.value)


def test_load_files_stops_when_gold_recall_or_campaign_is_missing(tmp_path):
    bad_q = make_data_dir(tmp_path / "a", questions=[{**QUESTION, "gold_campnos": ["99V999000"]}])
    with pytest.raises(SystemExit) as e:
        load_db.load_files(bad_q, "sample")
    assert "정답 리콜이 recalls에 없다" in str(e.value)
    bad_c = make_data_dir(tmp_path / "b", causes=[cause("99V999")])
    with pytest.raises(SystemExit) as e:
        load_db.load_files(bad_c, "sample")
    assert "앞 6자리와도 맞지 않는다" in str(e.value)


def test_load_files_stops_when_snapshot_date_differs_from_build(tmp_path):
    d = make_data_dir(tmp_path, recalls=[recall("24V001000", snapshot_date="2026-10-05")])
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "sample")
    assert "snapshot_date가 build.json과 다르다" in str(e.value)


def test_causes_file_is_never_chosen_automatically(tmp_path):
    d = make_data_dir(tmp_path)
    write_jsonl(
        d / "causes.jsonl", [cause("24V001")]
    )  # 전체 파일이 있어도 sample을 고르면 표본을 쓴다
    assert load_db.load_files(d, "sample")["build"]["causes_file"] == "causes_sample.jsonl"
    # full은 기대 건수가 필요하고, 파일이 그보다 짧으면(중간까지만 만들어짐) 올리지 않는다
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full")
    assert "--expect-rows" in str(e.value)
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", expect_rows=1000)
    assert "기대 건수 1,000줄과 다르다" in str(e.value)
    full = load_db.load_files(d, "full", expect_rows=1)
    assert full["build"]["causes_kind"] == "full" and full["build"]["causes_expected_rows"] == 1
    with pytest.raises(SystemExit):  # sample에는 기대 건수를 쓰지 않는다
        load_db.load_files(d, "sample", expect_rows=1)


# ---------------------------------------------------------------------------
# 스냅샷 비교


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


def test_loader_columns_match_schema():
    schema = _schema_columns()
    assert set(schema) == {"data_builds", *load_db.TABLES}
    for table in load_db.TABLES:
        assert set(load_db.db_columns(table)) == set(schema[table]), table
    # loaded_at·pruned_at처럼 DB가 기본값으로 채우거나 prune이 쓰는 칸만 적재 칸에 없다
    assert set(schema["data_builds"]) - set(load_db.BUILD_COLS) == {"loaded_at", "pruned_at"}


def test_sql_helpers():
    sql = load_db.insert_sql("eval_questions")
    assert sql.startswith(
        "insert into eval_questions (snapshot_date, action_no, question, open_date, gold_campnos, sets, row_sha256) values"
    )
    build_sql = load_db.upsert_build_sql()
    assert (
        "on conflict (snapshot_date) do update set" in build_sql and "pruned_at = null" in build_sql
    )


def test_schema_has_snapshot_keys_join_column_views_and_row_level_security():
    text = load_db.SCHEMA.read_text(encoding="utf-8")
    assert "generated always as (left(campno, 6)) stored" in text
    for pk in (
        "primary key (snapshot_date, campno)",
        "primary key (snapshot_date, action_no)",
        "primary key (snapshot_date, campaign)",
    ):
        assert pk in text
    for table in load_db.TABLES:
        assert f"alter table {table}" in text
        # 뷰는 기본이 만든 사람 권한으로 읽어 RLS를 우회하므로 security_invoker가 반드시 필요하다
        assert re.search(
            rf"create or replace view {table}_latest with \(security_invoker = true\)", text
        )
    assert "alter table data_builds" in text and "enable row level security" in text


# ---------------------------------------------------------------------------
# 로컬 Postgres (TEST_DATABASE_URL이 있을 때만)

PG_URL = os.environ.get("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(
    not PG_URL or urlparse(PG_URL).hostname not in ("localhost", "127.0.0.1"),
    reason="TEST_DATABASE_URL이 없거나 localhost가 아니다",
)


@pytest.fixture
def pgconn(monkeypatch):
    import psycopg

    monkeypatch.setenv("DATABASE_URL", PG_URL)
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute("drop schema public cascade; create schema public;")
        load_db.main(["schema"])
        load_db.main(["schema"])  # 여러 번 적용해도 된다
        yield conn


def counts(conn, table, snap):
    return conn.execute(
        f"select count(*) from {table} where snapshot_date = %s", (snap,)
    ).fetchone()[0]


def summary_of(conn, snap):
    return conn.execute(
        "select change_summary from data_builds where snapshot_date = %s", (snap,)
    ).fetchone()[0]


@pg
def test_pg_two_snapshots_are_kept_and_compared(pgconn, tmp_path):
    s1 = make_data_dir(
        tmp_path,
        "2026-10-06",
        recalls=[
            recall("24V001000", snapshot_date="2026-10-06"),
            recall("24V001001", snapshot_date="2026-10-06"),  # 같은 캠페인(24V001)에 리콜 2건
            recall("23V002000", snapshot_date="2026-10-06"),
        ],
        manifest="a1" * 32,
    )
    load_db.main(["load", "--causes", "sample", "--data-dir", str(s1)])
    load_db.main(
        ["load", "--causes", "sample", "--data-dir", str(s1)]
    )  # 같은 스냅샷을 다시 올려도 줄 수는 그대로
    d1, d2 = date(2026, 10, 6), date(2026, 10, 7)
    assert [counts(pgconn, t, d1) for t in load_db.TABLES] == [3, 1, 1]
    assert summary_of(pgconn, d1)["vs"] is None  # 첫 스냅샷
    # campaign6 조인: 원인 1건이 카드 2건에 붙는다 (일대다)
    n = pgconn.execute(
        "select count(*), count(distinct r.campno) from recalls r join causes c "
        "on c.snapshot_date = r.snapshot_date and c.campaign = r.campaign6 where r.snapshot_date = %s",
        (d1,),
    ).fetchone()
    assert n == (2, 2)

    s2 = make_data_dir(
        tmp_path,
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
    load_db.main(["load", "--causes", "sample", "--data-dir", str(s2)])
    # 두 스냅샷이 모두 남는다
    assert [counts(pgconn, t, d1) for t in load_db.TABLES] == [3, 1, 1]
    assert [counts(pgconn, t, d2) for t in load_db.TABLES] == [3, 1, 1]
    s = summary_of(pgconn, d2)
    assert s["vs"] == "2026-10-06"
    assert s["recalls"] == {
        "new": 1,
        "changed": 1,
        "removed": 1,
        "unchanged": 1,
        "changed_columns": {"defect": 1},
    }
    assert s["eval_questions"]["unchanged"] == 1 and s["causes"]["unchanged"] == 1
    # *_latest 뷰는 최신 스냅샷만 보여 준다
    assert pgconn.execute(
        "select snapshot_date, count(*) from recalls_latest group by 1"
    ).fetchall() == [(d2, 3)]
    # 어느 원인 파일을 올렸는지 남는다
    kind, rows = pgconn.execute(
        "select causes_kind, causes_rows from data_builds where snapshot_date = %s", (d2,)
    ).fetchone()
    assert (kind, rows) == ("sample", 1)


@pg
def test_pg_same_date_different_build_is_not_overwritten(pgconn, tmp_path):
    load_db.main(
        [
            "load",
            "--causes",
            "sample",
            "--data-dir",
            str(make_data_dir(tmp_path / "a", "2026-10-06", manifest="a1" * 32)),
        ]
    )
    other = make_data_dir(
        tmp_path / "b",
        "2026-10-06",
        recalls=[
            recall("24V001000", "Different text.", snapshot_date="2026-10-06"),
            recall("23V002000", snapshot_date="2026-10-06"),
        ],
    )
    with pytest.raises(SystemExit) as e:
        load_db.main(["load", "--causes", "sample", "--data-dir", str(other)])
    assert "덮어쓰지 않는다" in str(e.value)
    assert (
        pgconn.execute("select defect from recalls where campno = '24V001000'").fetchone()[0]
        == "Brake line may leak."
    )


@pg
def test_pg_prune_keeps_latest_and_marks_old_builds(pgconn, tmp_path, capsys):
    for day, manifest in (("2026-10-06", "a1" * 32), ("2026-10-07", "b2" * 32)):
        load_db.main(
            [
                "load",
                "--causes",
                "sample",
                "--data-dir",
                str(
                    make_data_dir(
                        tmp_path,
                        day,
                        manifest=manifest,
                        recalls=[
                            recall("24V001000", snapshot_date=day),
                            recall("23V002000", snapshot_date=day),
                        ],
                    )
                ),
            ]
        )
    d1, d2 = date(2026, 10, 6), date(2026, 10, 7)
    load_db.main(["prune", "--keep", "1"])  # --apply 없이는 지우지 않는다
    assert counts(pgconn, "recalls", d1) == 2
    load_db.main(["prune", "--keep", "1", "--apply"])
    assert counts(pgconn, "recalls", d1) == 0 and counts(pgconn, "recalls", d2) == 2
    pruned = dict(
        pgconn.execute("select snapshot_date, pruned_at is not null from data_builds").fetchall()
    )
    assert pruned == {d1: True, d2: False}  # data_builds 줄은 남는다
    with pytest.raises(SystemExit):
        load_db.main(["prune", "--keep", "0"])


@pg
def test_pg_rls_blocks_api_roles_even_through_views(pgconn, tmp_path):
    load_db.main(["load", "--causes", "sample", "--data-dir", str(make_data_dir(tmp_path))])
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
            "data_builds",
        ):
            assert pgconn.execute(f"select count(*) from {relation}").fetchone()[0] == 0, relation
    finally:
        pgconn.execute("reset role")
    assert pgconn.execute("select count(*) from recalls_latest").fetchone()[0] == 2


@pg
def test_pg_failed_load_rolls_back_everything(pgconn, tmp_path):
    import psycopg

    load_db.main(
        ["load", "--causes", "sample", "--data-dir", str(make_data_dir(tmp_path, "2026-10-06"))]
    )
    # 둘째 스냅샷의 마지막 테이블(causes)에서 제약 위반이 나게 한다 — 앞서 올린 recalls·eval·data_builds도 함께 되돌아가야 한다
    broken = make_data_dir(
        tmp_path, "2026-10-07", causes=[cause("24V001", cause_status="bogus")], manifest="b2" * 32
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        load_db.main(["load", "--causes", "sample", "--data-dir", str(broken)])
    d1, d2 = date(2026, 10, 6), date(2026, 10, 7)
    assert pgconn.execute("select snapshot_date from data_builds").fetchall() == [(d1,)]
    assert [counts(pgconn, t, d2) for t in load_db.TABLES] == [0, 0, 0]
    assert [counts(pgconn, t, d1) for t in load_db.TABLES] == [2, 1, 1]  # 이전 스냅샷은 그대로

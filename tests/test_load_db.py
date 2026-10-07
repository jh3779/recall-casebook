"""scripts/defect_precedent/load_db.py 테스트 — DB·원본 데이터 없이 확인한다."""

import re
from datetime import date

import pytest

from scripts.defect_precedent import load_db


def test_parse_date_reads_compact_and_iso():
    assert load_db.parse_date("20230130", "x") == date(2023, 1, 30)
    assert load_db.parse_date("2026-10-06", "x") == date(2026, 10, 6)


@pytest.mark.parametrize(
    "bad", ["", "2023013", "20231301", "20230230", "2023-1-5", "Jan 30, 2023", "20230130 "]
)
def test_parse_date_stops_instead_of_guessing(bad):
    with pytest.raises(SystemExit) as e:
        load_db.parse_date(bad, "recalls.jsonl 3번째 줄 received_date")
    # 어디의 어떤 값인지 알려 준다
    assert "recalls.jsonl 3번째 줄 received_date" in str(e.value)


def test_upsert_sql_updates_every_column_but_the_key():
    sql = load_db.upsert_sql("eval_questions")
    assert sql.startswith(
        "insert into eval_questions (action_no, question, open_date, gold_campnos, sets) values"
    )
    assert "on conflict (action_no) do update set" in sql
    assert "question = excluded.question" in sql
    assert "action_no = excluded.action_no" not in sql


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
            col = line.split()[0]
            if "generated always" not in line:
                cols.append(col)
        tables[name] = cols
    return tables


def test_loader_columns_match_schema():
    schema = _schema_columns()
    # loaded_at처럼 DB가 기본값으로 채우는 칸만 스크립트에 없어도 된다
    db_filled = {"data_builds": {"loaded_at"}}
    assert set(schema) == set(load_db.TABLES)
    for table, (cols, key) in load_db.TABLES.items():
        assert key in cols
        assert set(cols) == set(schema[table]) - db_filled.get(table, set()), table


def test_schema_has_join_column_and_row_level_security():
    text = load_db.SCHEMA.read_text(encoding="utf-8")
    assert "campaign6" in text and "generated always as (left(campno, 6)) stored" in text
    for table in load_db.TABLES:
        assert f"alter table {table}" in text and "enable row level security" in text

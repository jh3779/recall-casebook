"""scripts/ci/test_db_guard.py — DB 테스트 대상이 로컬인지 libpq가 실제로 접속할 곳으로 본다(PR #74 리뷰)."""

import pytest

from scripts.ci.test_db_guard import is_local_test_db


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:localtest@localhost:54331/postgres",
        "postgresql://x@127.0.0.1/db",
        "host=localhost dbname=x",
    ],
)
def test_local_urls_pass(url):
    assert is_local_test_db(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://x:y@db.example.com:5432/postgres",
        "postgresql://postgres:pw@localhost:54331/postgres?host=prod.example.com",  # 겉은 localhost
        "postgresql://a@localhost/db?hostaddr=10.1.2.3",  # 실제 접속 주소는 hostaddr
        "postgresql://a@localhost,prod.example.com/db",  # 여러 호스트 중 하나라도 밖
        "postgresql:///db",  # 호스트 없음 — PGHOST·소켓에 따라 달라짐
        "not a url",
    ],
)
def test_remote_or_ambiguous_urls_fail(url):
    assert not is_local_test_db(url)

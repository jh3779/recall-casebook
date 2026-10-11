"""scripts/ci/db_guard.py — DB 테스트 대상이 로컬인지 libpq가 실제로 접속할 곳으로 본다(PR #74 리뷰)."""

import pytest

from scripts.ci.db_guard import is_local_test_db


@pytest.fixture(autouse=True)
def _clean_libpq_env(monkeypatch):
    """개발자 셸의 libpq 환경변수에 따라 결과가 달라지지 않게 비운다(PR #74 리뷰)."""
    for name in ("PGSERVICE", "PGHOSTADDR", "PGHOST", "PGDATABASE"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:localtest@localhost:54331/lgcns_test",
        "postgresql://x@127.0.0.1/lgcns_test",
        "host=localhost dbname=lgcns_test",
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


def test_pghostaddr_env_is_checked(monkeypatch):
    """URL에 hostaddr가 없으면 libpq는 PGHOSTADDR로 접속한다 — 그 값도 로컬이어야 한다."""
    url = "postgresql://postgres:x@localhost:54331/lgcns_test"
    monkeypatch.setenv("PGHOSTADDR", "10.1.2.3")
    assert not is_local_test_db(url)
    monkeypatch.setenv("PGHOSTADDR", "127.0.0.1")
    assert is_local_test_db(url)


def test_pgservice_is_refused(monkeypatch):
    monkeypatch.setenv("PGSERVICE", "prod")
    assert not is_local_test_db("postgresql://postgres:x@localhost:54331/lgcns_test")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:x@localhost:5432/postgres",  # 평소 쓰는 로컬 DB
        "postgresql://postgres:x@localhost:5432/prod",
        "postgresql://postgres:x@localhost:5432",  # DB 이름 없음 — PGDATABASE·사용자 이름에 따라 달라짐
    ],
)
def test_local_but_not_the_dedicated_test_db_fails(url):
    """로컬이어도 전용 시험 DB 이름(lgcns_test)이 아니면 받지 않는다(PR #74 Codex 상 — 업무용 로컬 DB 보호)."""
    assert not is_local_test_db(url)

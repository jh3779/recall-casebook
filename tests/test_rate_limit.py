"""server/ratelimit.py — IP별 호출 상한 (이슈 #63).

가짜 시계와 가짜 임베딩 모델로 DB·모델 없이 돈다. 앱은 실제 `create_app`을 쓴다 — 미들웨어 순서(CORS가 바깥)와
429 응답의 CORS 머리글을 같이 확인하려는 것이다.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from server import ratelimit
from server.api import RagState, create_app
from server.rag.build import load_build
from server.rag.search import Searcher
from server.ratelimit import RateLimiter, limit_from_env
from tests.test_load_db import cause
from tests.test_rag_server import CARDS, FakeModel, full_data_dir

ORIGIN = "http://localhost:5173"  # 서버의 기본 CORS 허용 주소
QUESTION = {"question": "airbag inflator rupture"}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make_state(tmp_path):
    d = full_data_dir(
        tmp_path, CARDS, [cause("24V001", pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32})]
    )
    b = load_build(d)
    model = FakeModel()
    vecs = np.array(model.passage_embed([c["defect"] for c in b.cards]))
    return RagState(b, Searcher(b.cards, vecs, model), "fake")


def client_with(tmp_path, limit, clock=None):
    state = make_state(tmp_path)
    limiter = RateLimiter(limit, clock=clock or Clock())
    return TestClient(create_app(lambda: state, limiter))


def test_limiter_counts_per_key_and_frees_a_slot_when_the_window_passes():
    clock = Clock()
    lim = RateLimiter(2, window=60, clock=clock)
    assert lim.hit("a") == 0
    clock.t += 10
    assert lim.hit("a") == 0
    assert lim.hit("b") == 0  # 다른 IP는 따로 센다
    assert lim.hit("a") == 50  # 첫 호출이 풀리기까지 60 - 10 = 50초
    clock.t += 49
    assert lim.hit("a") == 1  # 막힌 호출은 세지 않아 대기 시간이 늘지 않는다
    clock.t += 1
    assert lim.hit("a") == 0  # 첫 호출이 창 밖으로 나가 한 칸이 비었다


def test_limiter_drops_quiet_keys_beyond_max_keys(monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_KEYS", 3)
    clock = Clock()
    lim = RateLimiter(5, clock=clock)
    for i in range(6):
        lim.hit(f"ip{i}")
        clock.t += 1
    assert len(lim._hits) <= 3
    assert "ip5" in lim._hits  # 가장 최근 IP는 남는다


def test_limit_from_env_defaults_and_refuses_bad_values(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
    assert limit_from_env() == 60
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "")  # .env.example를 복사한 빈 값
    assert limit_from_env() == 60
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "30")
    assert limit_from_env() == 30
    for bad in ("0", "-1", "abc", "1.5"):
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", bad)
        with pytest.raises(RuntimeError, match="RATE_LIMIT_PER_MINUTE"):
            limit_from_env()


def test_search_over_the_limit_gets_429_with_retry_after_and_cors_headers(tmp_path):
    clock = Clock()
    with client_with(tmp_path, 2, clock) as client:
        for _ in range(2):
            assert (
                client.post("/search", json=QUESTION, headers={"Origin": ORIGIN}).status_code == 200
            )
        res = client.post("/search", json=QUESTION, headers={"Origin": ORIGIN})
        assert res.status_code == 429
        assert res.headers["retry-after"] == "60"
        # CORS 미들웨어가 바깥이라 429에도 붙는다 — 없으면 브라우저가 '연결 실패(CORS)'로 잘못 안내한다
        assert res.headers["access-control-allow-origin"] == ORIGIN
        assert "Retry-After" in res.headers["access-control-expose-headers"]
        assert "60초" in res.json()["detail"]
        clock.t += 60
        assert client.post("/search", json=QUESTION).status_code == 200


def test_health_and_cors_preflight_are_not_counted(tmp_path):
    with client_with(tmp_path, 1) as client:
        preflight = {
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        }
        for _ in range(5):
            assert client.get("/health").status_code == 200
            assert client.options("/search", headers=preflight).status_code == 200
        assert client.post("/search", json=QUESTION).status_code == 200
        assert client.post("/search", json=QUESTION).status_code == 429


def test_rejected_requests_count_too(tmp_path):
    with client_with(tmp_path, 2) as client:
        assert client.post("/search", json={"question": "123"}).status_code == 422
        assert client.post("/search", json={"question": ""}).status_code == 422
        assert client.post("/search", json=QUESTION).status_code == 429


def test_on_vercel_each_forwarded_ip_has_its_own_bucket(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with client_with(tmp_path, 1) as client:
        assert (
            client.post(
                "/search", json=QUESTION, headers={"x-forwarded-for": "1.1.1.1"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/search", json=QUESTION, headers={"x-forwarded-for": "1.1.1.1"}
            ).status_code
            == 429
        )
        assert (
            client.post(
                "/search", json=QUESTION, headers={"x-forwarded-for": "2.2.2.2"}
            ).status_code
            == 200
        )
        # 목록이면 첫 주소가 클라이언트다
        list_header = {"x-forwarded-for": "3.3.3.3, 9.9.9.9"}
        assert client.post("/search", json=QUESTION, headers=list_header).status_code == 200
        assert (
            client.post(
                "/search", json=QUESTION, headers={"x-forwarded-for": "3.3.3.3"}
            ).status_code
            == 429
        )


def test_off_vercel_a_forged_forwarded_header_does_not_buy_a_new_bucket(tmp_path, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    with client_with(tmp_path, 1) as client:
        assert (
            client.post(
                "/search", json=QUESTION, headers={"x-forwarded-for": "1.1.1.1"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/search", json=QUESTION, headers={"x-forwarded-for": "2.2.2.2"}
            ).status_code
            == 429
        )


def test_limit_follows_the_router_path_when_the_app_runs_under_a_root_path(tmp_path):
    """서버가 root_path 아래에서 돌면 scope["path"]에는 접두어가 남는다 — 라우터가 보는 경로로 비교하지 않으면 상한이 꺼진다."""
    state = make_state(tmp_path)
    app = create_app(lambda: state, RateLimiter(1, clock=Clock()))
    with TestClient(app, root_path="/api") as client:
        assert client.post("/api/search", json=QUESTION).status_code == 200
        assert client.post("/api/search", json=QUESTION).status_code == 429


def test_route_path_strips_only_a_whole_root_path_segment():
    scope = {"path": "/api/search", "root_path": "/api"}
    assert ratelimit.route_path(scope) == "/search"
    assert ratelimit.route_path({"path": "/search"}) == "/search"  # root_path 없음
    assert ratelimit.route_path({"path": "/search", "root_path": "/api"}) == "/search"
    assert ratelimit.route_path({"path": "/apix/search", "root_path": "/api"}) == "/apix/search"
    assert ratelimit.route_path({"path": "/api", "root_path": "/api"}) == ""
    assert ratelimit.route_path({"path": "/s", "root_path": "/api"}) == "/s"  # 접두어보다 짧은 경로


def test_create_app_without_a_limiter_uses_the_env_limit(tmp_path, monkeypatch):
    # 배포는 `app = create_app()`라 상한이 환경변수에서 와야 한다 — 이 연결이 빠지면 설정이 말없이 무시된다
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    state = make_state(tmp_path)
    with TestClient(create_app(lambda: state)) as client:
        assert client.post("/search", json=QUESTION).status_code == 200
        assert client.post("/search", json=QUESTION).status_code == 429

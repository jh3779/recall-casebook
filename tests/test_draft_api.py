"""POST /draft (DEC-065) — 실제 `create_app`에 가짜 임베딩·가짜 LLM을 꽂아 DB·모델·네트워크 없이 돈다."""

import json

import numpy as np
import pytest
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient

from server import api as api_mod
from server.api import RagState, create_app
from server.rag import draft
from server.rag.build import load_build
from server.rag.draft import DraftConfig, LlmError, LlmResult
from server.rag.search import Searcher
from server.ratelimit import RateLimiter
from tests.test_load_db import cause, recall
from tests.test_rag_server import FakeModel, full_data_dir

QUESTION = "airbag inflator rupture"
CARDS = [
    recall(
        "24V001000",
        defect="Airbag inflator may rupture.  Metal fragments may be projected.",
        consequence="Fragments can injure occupants.",
        maker_group="Kia",
    ),
    recall("23V002000", defect="Brake line may leak.", consequence="A leak can reduce braking."),
    recall(
        "22V003000",
        defect="Airbag inflator housing may crack.",
        consequence="",
        maker_group="Hyundai Translead",
    ),
]
FORBIDDEN_KEYS = {"applies", "verdict", "is_applicable", "recall_required"}


def make_state(tmp_path):
    d = full_data_dir(
        tmp_path,
        CARDS,
        [
            cause(
                "24V001",
                text="The weld was incomplete.",
                pdfs={"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32},
            )
        ],
    )
    b = load_build(d)
    model = FakeModel()
    vecs = np.array(model.passage_embed([c["defect"] for c in b.cards]))
    return RagState(b, Searcher(b.cards, vecs, model), "fake")


def llm_returning(payload):
    calls = []

    def llm(instructions, text):
        calls.append(text)
        return LlmResult(json.dumps(payload), "gpt-6-luna", 10, 5, 0.01)

    llm.calls = calls
    return llm


def client(tmp_path, llm=None, config=None, **kw):
    state = make_state(tmp_path)
    return TestClient(
        create_app(lambda: state, draft_config=config or DraftConfig(), draft_llm=llm, **kw)
    )


def body(campnos=("24V001000",), step="d2", question=QUESTION):
    return {"question": question, "campnos": list(campnos), "step": step}


def keys(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from keys(v)
    elif isinstance(x, list):
        for v in x:
            yield from keys(v)


def test_draft_is_off_by_default_and_returns_the_plain_source_list_without_calling_anyone(tmp_path):
    with client(tmp_path) as c:
        r = c.post("/draft", json=body(("24V001000", "22V003000")))
    assert r.status_code == 200
    j = r.json()
    assert (j["degraded"], j["groups"], j["model"], j["titles_generated"]) == (
        "disabled",
        [],
        None,
        True,
    )
    got = [(u["campno"], u["field"], u["quote"]) for u in j["ungrouped"]]
    assert got == [
        (
            "24V001000",
            "defect",
            "Airbag inflator may rupture.  Metal fragments may be projected.",
        ),  # 이중 공백까지 원문 그대로
        ("24V001000", "consequence", "Fragments can injure occupants."),
        ("22V003000", "defect", "Airbag inflator housing may crack."),  # 빈 결과 칸은 싣지 않는다
    ]
    assert (
        j["ungrouped"][0]["speaker"].startswith("NHTSA 리콜 기록 요약")
        and j["ungrouped"][0]["dataset"] == "NHTSA FLAT_RCL"
    )
    assert j["questions"] == draft.QUESTIONS["d2"] and j["build_id"] and j["snapshot_date"]
    assert FORBIDDEN_KEYS.isdisjoint(set(keys(j)))


def test_enabled_draft_groups_d2_quotes_cut_from_the_source_text(tmp_path):
    llm = llm_returning(
        {
            "groups": [
                {
                    "title": "파열 위험을 적은 선례",
                    "quotes": [
                        {
                            "source_id": "S1",
                            "text": "Airbag inflator may rupture. Metal fragments may be projected.",
                        }
                    ],
                }
            ],
            "ungrouped": [],
        }
    )
    with client(tmp_path, llm=llm) as c:
        j = c.post("/draft", json=body()).json()
    (g,) = j["groups"]
    assert (
        g["title"] == "파열 위험을 적은 선례"
        and j["model"] == "gpt-6-luna"
        and j["degraded"] is None
    )
    it = g["items"][0]
    assert (
        it["quote"] == "Airbag inflator may rupture.  Metal fragments may be projected."
    )  # LLM이 줄인 공백이 아니라 원문 글자
    assert (it["start"], it["end"]) == (0, len(it["quote"]))
    assert [u["field"] for u in j["ungrouped"]] == ["consequence"]
    assert "Sources:" in llm.calls[0] and "campno=24V001000 field=defect" in llm.calls[0]


def test_d4_quotes_carry_the_cause_speaker_status_and_573_source(tmp_path):
    llm = llm_returning(
        {
            "groups": [
                {
                    "title": "용접 관련 서술",
                    "quotes": [{"source_id": "S1", "text": "The weld was incomplete."}],
                }
            ],
            "ungrouped": [],
        }
    )
    with client(tmp_path, llm=llm) as c:
        j = c.post("/draft", json=body(("24V001000", "23V002000"), "d4")).json()
    it = j["groups"][0]["items"][0]
    assert (
        it["field"] == "cause"
        and it["cause_status"] == "filled"
        and it["speaker"].startswith("리콜 제조사")
    )
    assert (
        it["cause_source"]["file"].endswith("RCLRPT-24V001-0001.PDF")
        and it["cause_source"]["pdf_sha256"] == "cd" * 32
    )
    assert j["ungrouped"] == []  # 원인 글이 없는 23V002000은 D4 원문에 들어가지 않는다


def test_quotes_the_llm_altered_are_dropped_not_shown(tmp_path):
    llm = llm_returning(
        {
            "groups": [
                {
                    "title": "t",
                    "quotes": [{"source_id": "S1", "text": "The weld was incomplete and unsafe."}],
                }
            ],
            "ungrouped": [],
        }
    )
    with client(tmp_path, llm=llm) as c:
        j = c.post("/draft", json=body(step="d4")).json()
    assert j["groups"] == [] and j["rejected"]["not_in_source"] == 1
    assert [u["quote"] for u in j["ungrouped"]] == ["The weld was incomplete."]


def test_llm_failure_degrades_to_the_source_list_with_the_reason_only(tmp_path):
    def boom(*_):
        raise LlmError("http", "status 401")

    with client(tmp_path, llm=boom) as c:
        j = c.post("/draft", json=body()).json()
    assert (j["degraded"], j["reason"], j["groups"]) == ("llm_failed", "http", [])
    assert len(j["ungrouped"]) == 2 and "status 401" not in json.dumps(j)


def test_campnos_outside_this_questions_search_result_are_refused(tmp_path):
    with client(tmp_path) as c:
        r = c.post("/draft", json=body(("24V001000", "99V999000")))
    assert r.status_code == 422 and "99V999000" in r.json()["detail"]


@pytest.mark.parametrize(
    "bad",
    [
        {"campnos": [], "step": "d2"},
        {"campnos": ["24V001000"] * 7, "step": "d2"},
        {"campnos": ["24v001000"], "step": "d2"},  # 형식(대문자 3번째 칸)이 아니다
        {"campnos": ["24V001"], "step": "d2"},
        {"campnos": ["24V001000"], "step": "d3"},  # D2·D4만
        {"campnos": ["24V001000"]},
        {"campnos": ["24V001000"], "step": "d2", "extra": 1},
        {"campnos": ["24V001000"], "step": "d2", "question": "에어백"},
    ],
)
def test_invalid_requests_are_422(tmp_path, bad):
    with client(tmp_path) as c:
        assert c.post("/draft", json={"question": QUESTION, **bad}).status_code == 422


def test_duplicate_campnos_are_quoted_once(tmp_path):
    with client(tmp_path) as c:
        j = c.post("/draft", json=body(("24V001000", "24V001000"))).json()
    assert len(j["ungrouped"]) == 2


def test_d4_returns_the_questions_the_llm_picked_by_id_with_the_fixed_pool_sentence(tmp_path):
    llm = llm_returning({"groups": [], "ungrouped": [], "question_ids": ["P2", "P99", "P2", "P7"]})
    with client(tmp_path, llm=llm) as c:
        j = c.post("/draft", json=body(("24V001000",), "d4")).json()
    assert j["picked_questions"] == [
        {"id": "P2", "text": draft.QUESTION_POOL["P2"]},
        {"id": "P7", "text": draft.QUESTION_POOL["P7"]},
    ]
    assert j["questions"][0] == draft.QUESTIONS["d4"][0]  # 기본 문장은 코드가 붙인다
    rej = j["rejected"]
    assert (rej["unknown_question"], rej["duplicate_question"], rej["over_limit_question"]) == (
        1,
        1,
        0,
    )
    assert "P2:" not in llm.calls[0] and all(
        q not in llm.calls[0] for q in draft.QUESTION_POOL.values()
    )  # LLM 입력에는 선례 원문만, 질문 문장은 없다
    assert FORBIDDEN_KEYS.isdisjoint(set(keys(j)))


def test_picked_questions_are_empty_when_off_or_d2_and_never_carry_a_sentence_outside_the_pool(
    tmp_path, monkeypatch
):
    with client(tmp_path / "a") as c:
        assert c.post("/draft", json=body(step="d4")).json()["picked_questions"] == []
    with client(
        tmp_path / "b", llm=llm_returning({"groups": [], "ungrouped": [], "question_ids": ["P1"]})
    ) as c:
        assert c.post("/draft", json=body(step="d2")).json()["picked_questions"] == []
    real = draft.generate

    def forged(step, cards, llm):
        out, used = real(step, cards, llm)
        out["picked_questions"] = [{"id": "P1", "text": "우리 건의 원인은 용접 불량입니다."}]
        return out, used

    monkeypatch.setattr(api_mod.draft, "generate", forged)
    with client(tmp_path / "c") as c, pytest.raises(ResponseValidationError):
        c.post("/draft", json=body(step="d4"))


def test_response_without_speaker_or_source_never_leaves_the_server(tmp_path, monkeypatch):
    real = draft.generate

    def stripped(step, cards, llm):
        out, used = real(step, cards, llm)
        for u in out["ungrouped"]:
            u.pop("speaker", None)
        return out, used

    monkeypatch.setattr(api_mod.draft, "generate", stripped)
    with client(tmp_path / "a") as c, pytest.raises(ResponseValidationError):
        c.post("/draft", json=body())
    monkeypatch.undo()

    def no_source(step, cards, llm):
        out, used = real(step, cards, llm)
        for u in out["ungrouped"]:
            u.pop("snapshot_date", None)
        return out, used

    monkeypatch.setattr(api_mod.draft, "generate", no_source)
    with client(tmp_path / "b") as c, pytest.raises(ResponseValidationError):
        c.post("/draft", json=body())


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def test_draft_has_its_own_lower_rate_limit_that_does_not_touch_search(tmp_path):
    clock = Clock()
    with client(
        tmp_path / "a",
        draft_limiter=RateLimiter(2, clock=clock),
        limiter=RateLimiter(60, clock=clock),
    ) as c:
        assert [c.post("/draft", json=body()).status_code for _ in range(3)] == [200, 200, 429]
        res = c.post("/draft", json=body())
        assert (
            res.status_code == 429
            and res.headers["Retry-After"]
            and "너무 잦습니다" in res.json()["detail"]
        )
        assert (
            c.post("/search", json={"question": QUESTION}).status_code == 200
        )  # /search는 따로 센다
    with client(
        tmp_path / "b",
        draft_limiter=RateLimiter(2, clock=clock),
        limiter=RateLimiter(1, clock=clock),
    ) as c2:
        assert c2.post("/search", json={"question": QUESTION}).status_code == 200
        assert c2.post("/search", json={"question": QUESTION}).status_code == 429
        assert (
            c2.post("/draft", json=body()).status_code == 200
        )  # /draft는 /search 상한을 쓰지 않는다


def test_429_on_draft_still_carries_cors_headers(tmp_path):
    with client(tmp_path, draft_limiter=RateLimiter(1, clock=Clock())) as c:
        h = {"Origin": "http://localhost:5173"}
        c.post("/draft", json=body(), headers=h)
        r = c.post("/draft", json=body(), headers=h)
    assert (
        r.status_code == 429 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
    )


# ---------- DraftConfig ----------
def test_draft_config_defaults_to_off_and_to_the_chosen_model_and_a_low_limit():
    c = DraftConfig.from_env({})
    assert (c.enabled, c.model, c.effort, c.limit, c.llm()) == (
        False,
        "gpt-6-luna",
        "none",
        6,
        None,
    )
    assert (
        DraftConfig.from_env({"OPENAI_API_KEY": "sk-x"}).enabled is False
    )  # 키만 있어도 켜지지 않는다
    assert DraftConfig.from_env({"DRAFT_ENABLED": "true"}).enabled is False  # 정확히 "1"만


def test_draft_config_refuses_to_start_on_unclear_settings():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        DraftConfig.from_env({"DRAFT_ENABLED": "1"})
    with pytest.raises(RuntimeError, match="DRAFT_REASONING_EFFORT"):
        DraftConfig.from_env({"DRAFT_REASONING_EFFORT": "turbo"})
    for raw in ("0", "-1", "abc"):
        with pytest.raises(RuntimeError, match="DRAFT_RATE_LIMIT_PER_MINUTE"):
            DraftConfig.from_env({"DRAFT_RATE_LIMIT_PER_MINUTE": raw})


def test_enabled_config_builds_a_llm_callable_without_exposing_the_key_in_repr_of_errors():
    c = DraftConfig.from_env(
        {
            "DRAFT_ENABLED": "1",
            "OPENAI_API_KEY": "sk-secret",
            "DRAFT_MODEL": "gpt-4o-mini",
            "DRAFT_REASONING_EFFORT": "low",
            "DRAFT_RATE_LIMIT_PER_MINUTE": "3",
        }
    )
    assert (c.model, c.effort, c.limit) == ("gpt-4o-mini", "low", 3) and callable(c.llm())


def test_more_than_the_limit_of_picked_questions_is_refused_by_the_response_model(
    tmp_path, monkeypatch
):
    real = draft.generate

    def too_many(step, cards, llm):
        out, used = real(step, cards, llm)
        out["picked_questions"] = [
            {"id": i, "text": draft.QUESTION_POOL[i]} for i in ("P1", "P2", "P3", "P4")
        ]
        return out, used

    monkeypatch.setattr(api_mod.draft, "generate", too_many)
    with client(tmp_path) as c, pytest.raises(ResponseValidationError):
        c.post("/draft", json=body(step="d4"))

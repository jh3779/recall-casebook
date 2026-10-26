"""scripts/defect_precedent/draft_sample.py — 표본 관찰 스크립트의 기록과 요약 시험 (이슈 #159).

네트워크와 유료 API는 쓰지 않는다 — 검색 응답은 합성 카드로, LLM 호출은 정해진 JSON을 돌려주는 가짜로 바꾼다.
`raw_question_ids` 기록과 이유별 요약(풀 밖·중복·상한 초과)은 다음 유료 재측정 때 처음 실행되지 않도록 여기서 먼저 돈다.
"""

import json

import pytest

from scripts.defect_precedent import draft_sample as ds
from server.rag import draft

QUESTION = "electrical short in the ABS module may cause fire"
DEFECT = "The ABS module may short circuit."
CAUSE = "Water entered the connector."
# LLM이 돌려준 번호 원본 — P1 중복, X9 풀 밖, P4는 상한(3개)을 넘은 유효한 번호
RAW_IDS = ["P1", "P1", "X9", "P2", "P3", "P4"]


def _card(campno: str, rank: int) -> dict:
    return {
        "campno": campno,
        "rank": rank,
        "defect": DEFECT,
        "consequence": "",
        "source": {"speaker": "제조사", "dataset": "recalls", "snapshot_date": "2026-10-01"},
        "cause": {
            "status": "filled",
            "speaker": "제조사",
            "source": "573 report",
            "text": CAUSE,
        },
    }


@pytest.fixture
def fake_service(monkeypatch):
    """검색 응답과 LLM 호출을 합성 값으로 바꾼다. 가짜 LLM이 받은 호출 수를 `calls`에 센다."""
    calls = []
    monkeypatch.setattr(ds, "QUESTIONS", [QUESTION])
    monkeypatch.setattr(ds.time, "sleep", lambda _s: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")

    def search(question, api):
        return {
            "build_id": "b-test",
            "snapshot_date": "2026-10-01",
            "customer_precedents": [_card("21V-001", 1)],
            "precedents": [_card("20V-002", 2)],
        }

    def call_llm(instructions, text, *, api_key, model, effort):
        calls.append(instructions)
        is_d4 = "question_ids" in instructions and "Return an empty list" not in instructions
        return draft.LlmResult(
            text=json.dumps(
                {
                    "groups": [
                        {
                            "title": "전기 단락을 적은 선례",
                            "quotes": [{"source_id": "S1", "text": CAUSE if is_d4 else DEFECT}],
                        }
                    ],
                    "question_ids": RAW_IDS if is_d4 else [],
                }
            ),
            model=model,
            input_tokens=100,
            output_tokens=20,
            seconds=0.123,
        )

    monkeypatch.setattr(ds, "search", search)
    monkeypatch.setattr(draft, "call_llm", call_llm)
    return calls


def _read(path):
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    return lines[0], lines[1:]


def test_run_records_raw_question_ids_and_summarizes_dropped_reasons(
    tmp_path, capsys, fake_service
):
    out = tmp_path / "draft_sample.jsonl"
    ds.run(str(out), "https://api.invalid", "gpt-6-luna", "low", 2, dry_run=False)

    meta, rows = _read(out)
    assert meta["meta"]["steps"] == ["d2", "d4"] and meta["meta"]["questions"] == [QUESTION]
    assert len(fake_service) == 2  # d2·d4 한 번씩 — 합성 LLM만 불렸다
    d2, d4 = rows
    assert (d2["step"], d4["step"]) == ("d2", "d4")
    # LLM이 돌려준 번호 원본이 그대로 남는다 — 풀 밖·중복·초과를 사후에 구분하는 근거(DEC-071)
    assert d4["raw_question_ids"] == RAW_IDS
    assert d2["raw_question_ids"] == []
    assert d4["raw_titles"] == ["전기 단락을 적은 선례"]
    # 서버가 고른 번호는 풀 안·중복 제거·상한 3개, 버린 것은 이유별로 센다
    assert [q["id"] for q in d4["draft"]["picked_questions"]] == ["P1", "P2", "P3"]
    assert d4["draft"]["rejected"]["unknown_question"] == 1
    assert d4["draft"]["rejected"]["duplicate_question"] == 1
    assert d4["draft"]["rejected"]["over_limit_question"] == 1
    assert d4["input_tokens"] == 100 and d4["seconds"] == 0.12

    text = capsys.readouterr().out
    assert "확인 질문 선택(D4 1회)" in text
    assert (
        "서버가 버린 번호 {'unknown_question': 1, 'duplicate_question': 1, 'over_limit_question': 1}"
        in text
    )
    assert "번호별 {'P1': 1, 'P2': 1, 'P3': 1}" in text
    assert "고른 개수 분포 {3: 1}" in text


def test_summary_counts_dropped_question_reasons_across_d4_rows(capsys):
    """합성 행만으로 `summary()`를 부른다 — D4 행 둘의 버린 번호가 이유별로 더해진다."""

    def row(picked, rejected):
        return {
            "question": QUESTION,
            "step": "d4",
            "n_sources": 1,
            "raw_titles": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "draft": {
                "degraded": None,
                "rejected": rejected,
                "relocated": 0,
                "groups": [],
                "ungrouped": [],
                "picked_questions": [{"id": i, "text": ""} for i in picked],
            },
        }

    rows = [
        row(
            ["P2", "P1"], {"unknown_question": 1, "duplicate_question": 0, "over_limit_question": 2}
        ),
        row([], {"unknown_question": 2, "duplicate_question": 1}),  # 키가 없는 이유는 0으로 센다
    ]
    ds.summary(rows, "gpt-6-luna", dry_run=False, steps=("d4",))
    text = capsys.readouterr().out
    assert "확인 질문 선택(D4 2회)" in text
    assert "고른 개수 분포 {0: 1, 2: 1}" in text
    assert "번호별 {'P1': 1, 'P2': 1}" in text
    assert (
        "서버가 버린 번호 {'unknown_question': 3, 'duplicate_question': 1, 'over_limit_question': 2}"
        in text
    )


def test_dry_run_calls_no_llm_and_writes_no_file(tmp_path, capsys, fake_service):
    out = tmp_path / "never.jsonl"
    ds.run(str(out), "https://api.invalid", "gpt-6-luna", "low", 2, dry_run=True)
    assert fake_service == [] and not out.exists()
    text = capsys.readouterr().out
    assert "호출할 행(원문이 있는 것) 2" in text and "비용 상한" in text

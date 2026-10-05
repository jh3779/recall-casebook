"""scripts/sales_support_llm.py 테스트 — 프롬프트·검증·비용·예산. 네트워크 호출 없이 가짜 클라이언트로 돌린다."""

import json
from types import SimpleNamespace

import pytest

from scripts import sales_support_llm as llm
from scripts import sales_support_poc as poc

TEXT = "Request access\nthrough the portal. Managers approve within 3 days."
CHUNKS = poc.chunk_file("sales/a.md", f"## Access\n\n{TEXT}\n") + poc.chunk_file(
    "sales/b.md", "## Other\n\nUnrelated text.\n"
)


def item(**kw):
    base = {
        "item": "Request access",
        "reason": "Needed to start work",
        "criteria": None,
        "check_method": None,
        "chunk_no": 1,
        "evidence_quote": "Request access through the portal.",
    }
    return base | kw


def test_prompt_numbers_excerpts_and_truncates_long_chunks():
    long_chunk = poc.chunk_file("sales/c.md", "## Long\n\n" + "x" * 5000 + "\n")[0]
    prompt = llm.build_prompt("How do I get access?", [CHUNKS[0], long_chunk])
    assert "Question: How do I get access?" in prompt
    assert "[1] Access" in prompt and "[2] Long" in prompt
    assert "x" * 2000 in prompt and "x" * 2001 not in prompt


def test_prompt_instructions_do_not_ask_for_a_verdict():
    text = llm.INSTRUCTIONS.lower()
    for banned in ("applies to you", "verdict", "is_applicable", "적용됩니다"):
        assert banned not in text
    assert "do not decide" in text


def test_schema_is_strict_and_requires_every_field():
    item_schema = llm.OUTPUT_SCHEMA["properties"]["items"]["items"]
    assert set(item_schema["required"]) == set(item_schema["properties"])
    assert item_schema["additionalProperties"] is False
    assert llm.OUTPUT_SCHEMA["additionalProperties"] is False


def test_valid_item_gets_source_and_domains_from_code_not_model():
    valid, removed, flags = llm.validate_items([item()], CHUNKS[:2])
    assert removed == {} and flags["criteria_outside_quote"] == 0
    assert valid[0]["source"] == "sales/a.md#Access"
    assert valid[0]["domains"] == ["sales-support"]
    assert valid[0]["commit_sha"] == poc.COMMIT_SHA


def test_quote_matching_ignores_whitespace_differences():
    valid, removed, _ = llm.validate_items(
        [item(evidence_quote="Request   access\nthrough the portal.")], CHUNKS[:2]
    )
    assert len(valid) == 1 and removed == {}


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (item(chunk_no=3), "bad_chunk_no"),
        (item(chunk_no=0), "bad_chunk_no"),
        (item(evidence_quote="Approvals take 10 days."), "quote_not_in_chunk"),
        (item(evidence_quote=""), "empty_field"),
        (item(item=""), "empty_field"),
        (
            item(evidence_quote="Request access through the portal.", chunk_no=2),
            "quote_not_in_chunk",
        ),
    ],
)
def test_invalid_items_are_removed_with_a_reason(bad, reason):
    valid, removed, _ = llm.validate_items([bad], CHUNKS[:2])
    assert valid == [] and removed == {reason: 1}


def test_criteria_outside_the_quote_is_flagged_but_kept():
    good = item(
        criteria="Managers approve within 3 days.", evidence_quote="Managers approve within 3 days."
    )
    bad = item(criteria="Approval takes a week", check_method="Ask the manager")
    valid, removed, flags = llm.validate_items([good, bad], CHUNKS[:2])
    assert len(valid) == 2 and removed == {}
    assert flags["criteria_outside_quote"] == 1 and flags["check_method_outside_quote"] == 1


def test_verdict_style_wording_is_counted():
    valid, _, flags = llm.validate_items([item(reason="This does not apply to you.")], CHUNKS[:2])
    assert len(valid) == 1 and flags["verdict_wording"] == 1


def test_cost_uses_per_million_token_prices():
    assert llm.cost_usd(1_000_000, 0) == pytest.approx(0.15)
    assert llm.cost_usd(0, 1_000_000) == pytest.approx(0.60)


class FakeClient:
    """responses.create만 흉내 낸다 — 정해 둔 응답 문자열과 토큰 수를 돌려준다."""

    def __init__(self, outputs, tokens=(1000, 500)):
        self.outputs = list(outputs)
        self.tokens = tokens
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        usage = SimpleNamespace(input_tokens=self.tokens[0], output_tokens=self.tokens[1])
        return SimpleNamespace(output_text=out, usage=usage)


def question():
    return poc.EvalQuestion("faq-1", "How do I get access?", ["sales/a.md#Access"])


def test_run_question_records_validation_gold_hit_and_usage():
    client = FakeClient([json.dumps({"items": [item(), item(chunk_no=9)]})])
    rec = llm.run_question(client, question(), CHUNKS[:2])
    assert rec["schema_ok"] is True
    assert rec["n_raw"] == 2 and rec["n_valid"] == 1 and rec["removed"] == {"bad_chunk_no": 1}
    assert rec["gold_cited"] is True
    assert rec["input_tokens"] == 1000 and rec["output_tokens"] == 500
    sent = client.calls[0]
    assert sent["model"] == llm.MODEL and sent["store"] is False
    assert sent["text"]["format"]["strict"] is True


def test_run_question_marks_invalid_json_and_api_errors_without_crashing():
    bad_json = llm.run_question(FakeClient(["not json"]), question(), CHUNKS[:2])
    assert bad_json["schema_ok"] is False and bad_json["n_valid"] == 0
    failed = llm.run_question(FakeClient([RuntimeError("boom")]), question(), CHUNKS[:2])
    assert failed["error"] == "RuntimeError: boom" and failed["schema_ok"] is False


def test_batch_stops_when_budget_is_exceeded():
    outputs = [json.dumps({"items": [item()]})] * 5
    # 호출당 입력 500만·출력 0 토큰 → 약 $0.75, 예산 $1이면 두 번째 호출 뒤 중단
    client = FakeClient(outputs, tokens=(5_000_000, 0))
    jobs = [(question(), CHUNKS[:2])] * 5
    records, stopped = llm.run_batch(client, jobs, budget_usd=1.0)
    assert len(records) == 2 and stopped is True


def test_summary_aggregates_rates_and_cost():
    client = FakeClient([json.dumps({"items": [item()]}), "not json"])
    records, _ = llm.run_batch(client, [(question(), CHUNKS[:2])] * 2, budget_usd=1.0)
    summary = llm.summarize(records)
    assert summary["n_questions"] == 2
    assert summary["schema_ok_rate"] == 0.5
    assert summary["items_valid_rate"] == 1.0  # 구조가 맞은 응답의 항목만 센다
    assert summary["gold_cited_rate"] == 0.5
    assert summary["cost_usd"] > 0

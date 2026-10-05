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
    assert len(valid) == 1 and flags["judgment_wording"] == 1


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


@pytest.mark.parametrize(
    "bad_item",
    [
        {},  # 필수 키가 하나도 없음
        {k: v for k, v in item().items() if k != "reason"},  # 키 하나 빠짐
        item() | {"extra": 1},  # 허용하지 않은 키
        item(chunk_no="1"),  # 타입이 다름
        item(criteria=5),
    ],
)
def test_schema_ok_is_false_when_an_item_breaks_the_fixed_schema(bad_item):
    rec = llm.run_question(FakeClient([json.dumps({"items": [bad_item]})]), question(), CHUNKS[:2])
    assert rec["schema_ok"] is False and rec["n_valid"] == 0


def test_schema_ok_is_true_for_an_empty_item_list_and_for_valid_items():
    empty = llm.run_question(FakeClient([json.dumps({"items": []})]), question(), CHUNKS[:2])
    assert empty["schema_ok"] is True and empty["n_raw"] == 0


def test_budget_check_happens_before_the_call_not_after():
    client = FakeClient([json.dumps({"items": []})])
    # 다음 호출의 최대 비용이 남은 예산보다 크면 호출하지 않는다
    records, stopped = llm.run_batch(client, [(question(), CHUNKS[:2])], budget_usd=0.0001)
    assert client.calls == [] and records == [] and stopped is True


def test_max_call_cost_is_an_upper_bound_of_the_real_cost():
    prompt_cost = llm.max_call_cost(question(), CHUNKS[:2])
    typical = llm.cost_usd(2500, 600)
    assert prompt_cost >= llm.cost_usd(100, llm.MAX_OUTPUT_TOKENS)
    assert prompt_cost >= typical * 0.5  # 보수적으로 잡힌 값이라 현실적 비용보다 작지 않다


def test_overlong_questions_are_recorded_without_calling_the_api():
    long_q = poc.EvalQuestion("faq-9", "x" * (llm.MAX_QUESTION_CHARS + 1), ["sales/a.md#Access"])
    client = FakeClient([json.dumps({"items": []})])
    records, _ = llm.run_batch(client, [(long_q, CHUNKS[:2])], budget_usd=1.0)
    assert client.calls == [] and records[0]["error"] == "question_too_long"


def test_run_config_records_everything_needed_to_reproduce_a_run():
    meta = {"data_commit_sha": "a" * 40, "chunks_digest": "d1", "embedding_model": "m"}
    cfg = llm.build_run_config(meta, "hybrid")
    for key in (
        "model",
        "openai_version",
        "instructions_sha",
        "schema_sha",
        "top_k_chunks",
        "max_chunk_chars_in_prompt",
        "max_output_tokens",
        "temperature",
        "retrieval",
        "data_commit_sha",
        "index_chunks_digest",
        "index_embedding_model",
    ):
        assert key in cfg
    assert cfg["model"] == llm.MODEL and cfg["data_commit_sha"] == "a" * 40
    assert cfg["index_chunks_digest"] == "d1" and cfg["retrieval"] == "hybrid"


def test_run_config_instructions_hash_changes_when_the_prompt_changes(monkeypatch):
    meta = {"data_commit_sha": "a", "chunks_digest": "d", "embedding_model": "m"}
    before = llm.build_run_config(meta, "hybrid")["instructions_sha"]
    monkeypatch.setattr(llm, "INSTRUCTIONS", llm.INSTRUCTIONS + " Be brief.")
    assert llm.build_run_config(meta, "hybrid")["instructions_sha"] != before


def test_schema_ok_is_false_when_top_level_has_extra_keys():
    out = json.dumps({"items": [], "unexpected": True})
    assert llm.run_question(FakeClient([out]), question(), CHUNKS[:2])["schema_ok"] is False
    assert (
        llm.run_question(FakeClient([json.dumps({"other": []})]), question(), CHUNKS[:2])[
            "schema_ok"
        ]
        is False
    )


def test_run_config_has_embedding_file_hash_libraries_retrieval_settings_and_repo_commit(tmp_path):
    emb = tmp_path / "embeddings.npz"
    emb.write_bytes(b"vectors-v1")
    meta_file = tmp_path / "index_meta.json"
    meta_file.write_text("{}", encoding="utf-8")
    meta = {"data_commit_sha": "a", "chunks_digest": "d", "embedding_model": "m"}
    cfg = llm.build_run_config(meta, "hybrid", embeddings_path=emb, index_meta_path=meta_file)
    assert cfg["embeddings_sha256"] == llm.file_sha256(emb)
    assert cfg["index_meta_sha256"] == llm.file_sha256(meta_file)
    for lib in ("fastembed", "rank_bm25", "numpy", "openai"):
        assert lib in cfg["libraries"]
    assert cfg["retrieval_settings"]["rrf_k"] == poc.RRF_K
    assert cfg["retrieval_settings"]["candidates"] == poc.CANDIDATES
    assert "repo_commit" in cfg
    emb.write_bytes(b"vectors-v2")  # 임베딩 파일이 바뀌면 기록된 해시도 달라진다
    assert (
        llm.build_run_config(meta, "hybrid", embeddings_path=emb, index_meta_path=meta_file)[
            "embeddings_sha256"
        ]
        != cfg["embeddings_sha256"]
    )


def test_question_sets_summary_separates_planned_from_processed_and_outcomes():
    qs = [poc.EvalQuestion(str(i), f"q{i}", [f"a.md#{i}"]) for i in range(4)]
    ok = {"question_id": "0", "schema_ok": True, "error": None}
    bad_schema = {"question_id": "1", "schema_ok": False, "error": None}
    api_err = {"question_id": "2", "schema_ok": False, "error": "RuntimeError: boom"}
    rejected = {"question_id": "3", "schema_ok": False, "error": "question_too_long"}
    full = llm.question_sets_summary(qs, [ok, bad_schema, api_err, rejected])
    assert full["all_attempted"] is True and full["all_succeeded"] is False
    assert full["outcomes"] == {
        "success": 1,
        "schema_error": 1,
        "api_error": 1,
        "local_rejected": 1,
    }
    partial = llm.question_sets_summary(qs, [ok, bad_schema])
    assert partial["all_attempted"] is False
    assert partial["planned"]["n"] == 4 and partial["processed"]["n"] == 2
    assert partial["planned"]["digest"] != partial["processed"]["digest"]
    clean = llm.question_sets_summary(qs[:1], [ok])
    assert clean["all_attempted"] is True and clean["all_succeeded"] is True


def test_run_config_records_hashes_of_the_scripts_that_ran(tmp_path):
    meta = {"data_commit_sha": "a", "chunks_digest": "d", "embedding_model": "m"}
    cfg = llm.build_run_config(meta, "hybrid")
    assert set(cfg["code_sha256"]) == {"sales_support_llm.py", "sales_support_poc.py"}
    assert all(len(v) == 64 for v in cfg["code_sha256"].values())
    assert cfg["client_max_retries"] == 0


def test_openai_client_is_created_without_automatic_retries(monkeypatch):
    seen = {}

    class Dummy:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(llm, "make_client", llm.make_client)  # 존재 확인
    import openai

    monkeypatch.setattr(openai, "OpenAI", Dummy)
    llm.make_client()
    assert seen == {"max_retries": 0}


def test_failed_call_without_usage_is_charged_at_worst_case_so_the_budget_still_holds():
    worst = llm.max_call_cost(question(), CHUNKS[:2])
    # 예산이 최악 비용 1.5건어치: 첫 호출이 사용량 없이 실패하면 최악 비용이 누적돼 다음 호출은 하지 않는다
    client = FakeClient([RuntimeError("timeout"), json.dumps({"items": []})])
    records, stopped = llm.run_batch(client, [(question(), CHUNKS[:2])] * 2, budget_usd=worst * 1.5)
    assert len(client.calls) == 1 and len(records) == 1 and stopped is True
    assert records[0]["cost_unknown"] is True


def test_summary_counts_local_rejections_separately_from_api_errors():
    long_q = poc.EvalQuestion("faq-9", "x" * (llm.MAX_QUESTION_CHARS + 1), ["sales/a.md#Access"])
    client = FakeClient([RuntimeError("boom")])
    records, _ = llm.run_batch(
        client, [(long_q, CHUNKS[:2]), (question(), CHUNKS[:2])], budget_usd=1.0
    )
    summary = llm.summarize(records)
    assert summary["n_local_rejected"] == 1 and summary["n_api_errors"] == 1
    assert summary["n_cost_unknown"] == 1


def _auth_error():
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(401, request=request)
    return openai.AuthenticationError("expired key", response=response, body=None)


def test_auth_error_is_not_charged_and_stops_the_batch_immediately():
    client = FakeClient([_auth_error(), json.dumps({"items": []})])
    jobs = [(question(), CHUNKS[:2])] * 3
    records, stopped = llm.run_batch(client, jobs, budget_usd=1.0)
    assert len(client.calls) == 1 and len(records) == 1  # 첫 호출에서 바로 중단
    assert records[0]["cost_unknown"] is False and records[0]["fatal"] is True
    assert stopped is False  # 예산 때문이 아니라 인증 오류로 중단
    summary = llm.summarize(records)
    assert summary["n_cost_unknown"] == 0 and summary["aborted_on_fatal_error"] is True

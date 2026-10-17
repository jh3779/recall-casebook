"""server/rag/draft.py — 근거 연결형 초안 (DEC-065). LLM·네트워크 없이 돈다(가짜 호출·가짜 응답)."""

import io
import json
import urllib.error

import pytest

from server.rag import draft
from server.rag.draft import LlmError, LlmResult, Source

DEFECT = "Hyundai is recalling certain 2024 Tucson vehicles.  The circuit board may short circuit, resulting in a loss of power steering assist."
CONSEQ = "A loss of power steering assist can increase the risk of a crash."
SPEAKER = "NHTSA 리콜 기록 요약(FLAT_RCL 결함·결과·시정 칸) — 원본에 작성 주체 표시 없음"
CAUSE_SRC = {
    "campaign": "24V412",
    "file": "odi/rcl/2024/X.PDF",
    "pdf_sha256": "ab" * 32,
    "submission_date": "20240605",
    "text_basis": "b",
}


def card(campno="24V412000", defect=DEFECT, consequence=CONSEQ, cause=None):
    return {
        "campno": campno,
        "defect": defect,
        "consequence": consequence,
        "source": {"dataset": "NHTSA FLAT_RCL", "snapshot_date": "2026-10-06", "speaker": SPEAKER},
        "cause": cause or {"status": "no_573_report"},
    }


def cause(text, status="filled"):
    return {
        "status": status,
        "text": text,
        "speaker": "리콜 제조사 (Part 573 결함·불합치 보고서)",
        "source": CAUSE_SRC,
        "flags": [],
    }


def fake_llm(payload):
    calls = []

    def llm(instructions, input_text):
        calls.append((instructions, input_text))
        return LlmResult(json.dumps(payload), "gpt-6-luna-x", 100, 50, 0.1)

    llm.calls = calls
    return llm


# ---------- locate ----------
def test_locate_finds_exact_text_and_recovers_the_original_span_when_only_whitespace_differs():
    assert draft.locate(DEFECT, "The circuit board may short circuit") == (
        DEFECT.index("The circuit"),
        DEFECT.index("The circuit") + len("The circuit board may short circuit"),
    )
    # LLM이 마침표 뒤 이중 공백을 한 칸으로 줄여 돌려준 경우 — 원문 구간(이중 공백 포함)으로 되짚는다
    quote = "vehicles. The circuit board may short circuit"
    s, e = draft.locate(DEFECT, quote)
    assert DEFECT[s:e] == "vehicles.  The circuit board may short circuit"
    text = "  leading and  trailing  "
    s2, e2 = draft.locate(text, "leading and trailing")
    assert text[s2:e2] == "leading and  trailing"  # 앞뒤 공백은 빼고, 안쪽 이중 공백은 원문 그대로


def test_locate_rejects_text_that_is_not_in_the_source_even_by_one_letter():
    assert draft.locate(DEFECT, "the circuit board may short circuit") is None  # 대문자 하나
    assert draft.locate(DEFECT, "The circuit board may short-circuit") is None
    assert draft.locate(DEFECT, "") is None
    assert draft.locate(DEFECT, "   ") is None


# ---------- build_sources ----------
def test_d2_sources_are_defect_and_consequence_sentences_with_the_card_speaker():
    srcs = draft.build_sources("d2", [card(), card("24V422000", consequence="  ")])
    assert [(s.id, s.campno, s.field) for s in srcs] == [
        ("S1", "24V412000", "defect"),
        ("S2", "24V412000", "consequence"),
        ("S3", "24V422000", "defect"),
    ]
    assert srcs[0].provenance == {
        "speaker": SPEAKER,
        "dataset": "NHTSA FLAT_RCL",
        "snapshot_date": "2026-10-06",
    }


def test_d4_sources_are_only_cause_texts_with_speaker_and_source_and_skip_cards_without_text():
    cards = [
        card("24V412000", cause=cause("Contaminated flux.")),
        card("23V001000"),
        card("17V159000", cause=cause("N/A", "stated_unknown")),
    ]
    srcs = draft.build_sources("d4", cards)
    assert [(s.campno, s.text) for s in srcs] == [
        ("24V412000", "Contaminated flux."),
        ("17V159000", "N/A"),
    ]
    assert (
        srcs[0].provenance["cause_source"] == CAUSE_SRC
        and srcs[1].provenance["cause_status"] == "stated_unknown"
    )
    assert "cause_status" in srcs[0].provenance and srcs[0].provenance["speaker"].startswith(
        "리콜 제조사"
    )


# ---------- assemble ----------
def srcs2():
    return draft.build_sources("d2", [card()])


def test_assemble_cuts_quotes_from_the_source_and_computes_ungrouped_itself():
    payload = {
        "groups": [
            {
                "title": "회로 단락을 적은 선례",
                "quotes": [
                    {
                        "source_id": "S1",
                        "text": "The circuit board may short circuit, resulting in a loss of power steering assist.",
                    }
                ],
            }
        ],
        "ungrouped": ["S99"],
    }
    out = draft.assemble(srcs2(), payload)
    (g,) = out["groups"]
    it = g["items"][0]
    # 묶음에 넣은 출처의 전체 원문이 원문 글자 그대로 나간다(문장 일부만 인용한 LLM 구간은 "이 출처를 넣는다"는 표시일 뿐)
    assert DEFECT[it["start"] : it["end"]] == it["quote"] == DEFECT
    assert it["campno"] == "24V412000" and it["field"] == "defect" and it["speaker"] == SPEAKER
    # LLM이 말한 ungrouped(S99)는 믿지 않고, 쓰이지 않은 원문(S2)을 서버가 싣는다
    assert [(u["field"], u["quote"]) for u in out["ungrouped"]] == [("consequence", CONSEQ)]


def test_assemble_uses_source_characters_even_when_the_llm_changed_whitespace():
    payload = {
        "groups": [
            {"title": "t", "quotes": [{"source_id": "S1", "text": "vehicles. The circuit board"}]}
        ],
        "ungrouped": [],
    }
    out = draft.assemble(srcs2(), payload)
    # 묶음에 넣은 출처의 전체 원문이 원문 글자 그대로(이중 공백 포함) 나간다 — 부분 인용은 아래 시험
    assert out["groups"][0]["items"][0]["quote"] == DEFECT


@pytest.mark.parametrize(
    "quote",
    [
        "The Circuit board may short circuit",
        "The circuit board might short circuit",
        "The circuit board ... loss of power steering assist.",
    ],
)
def test_assemble_drops_quotes_that_are_not_in_the_source_and_counts_them(quote):
    out = draft.assemble(
        srcs2(),
        {
            "groups": [{"title": "t", "quotes": [{"source_id": "S1", "text": quote}]}],
            "ungrouped": [],
        },
    )
    assert out["groups"] == [] and out["rejected"]["not_in_source"] == 1
    assert len(out["ungrouped"]) == 2  # 버려진 인용의 원문은 목록에 그대로 남는다


def test_assemble_rejects_unknown_sources_and_a_source_used_twice_and_drops_empty_groups():
    payload = {
        "groups": [
            {
                "title": "a를 적은 선례",
                "quotes": [
                    {"source_id": "S1", "text": "The circuit board may short circuit"},
                    {"source_id": "S9", "text": "x"},
                ],
            },
            {
                "title": "b를 적은 선례",
                "quotes": [{"source_id": "S1", "text": "loss of power steering assist"}],
            },
            {"title": "c를 적은 선례", "quotes": []},
        ],
        "ungrouped": [],
    }
    out = draft.assemble(srcs2(), payload)
    assert [g["title"] for g in out["groups"]] == ["a를 적은 선례"]
    assert out["rejected"] == {
        "unknown_source": 1,
        "not_in_source": 0,
        "duplicate_source": 1,
        "bad_title": 0,
    }


@pytest.mark.parametrize(
    "title",
    [
        "리콜 대상입니다",
        "원인은 플럭스 오염입니다",
        "이 선례는 우리 건에 해당합니다",
        "verdict: applies",
        "Root cause is solder flux",
        "x" * 41,
        "",
        "한\n줄",
    ],
)
def test_verdict_or_overlong_titles_are_replaced_with_a_neutral_one(title):
    out = draft.assemble(
        srcs2(),
        {
            "groups": [
                {
                    "title": title,
                    "quotes": [{"source_id": "S1", "text": "The circuit board may short circuit"}],
                }
            ],
            "ungrouped": [],
        },
    )
    assert out["groups"][0]["title"] == "묶음 1" and out["rejected"]["bad_title"] == 1


@pytest.mark.parametrize(
    "title",
    [
        "회로 단락을 적은 선례",
        "납땜 플럭스가 오염됐을 수 있다고 적은 선례",
        "원인을 밝히지 않았다고 적은 선례",
        "파열을 서술한 선례",
    ],
)
def test_neutral_descriptive_titles_pass(title):
    assert draft.title_ok(title)


# ---------- generate ----------
def test_generate_without_llm_degrades_to_the_plain_source_list():
    out, used = draft.generate("d2", [card()], None)
    assert (
        used is None
        and out["degraded"] == "disabled"
        and out["groups"] == []
        and len(out["ungrouped"]) == 2
    )
    assert out["questions"] == draft.QUESTIONS["d2"] and out["model"] is None


def test_generate_degrades_when_the_llm_fails_or_returns_unusable_json():
    def boom(*_):
        raise LlmError("network")

    out, _ = draft.generate("d2", [card()], boom)
    assert (
        out["degraded"] == "llm_failed"
        and out["reason"] == "network"
        and len(out["ungrouped"]) == 2
    )
    bad = lambda *_: LlmResult("not json", "m", 1, 1, 0.1)  # noqa: E731
    assert draft.generate("d2", [card()], bad)[0]["reason"] == "format"
    arr = lambda *_: LlmResult("[1]", "m", 1, 1, 0.1)  # noqa: E731
    assert draft.generate("d2", [card()], arr)[0]["degraded"] == "llm_failed"


def test_generate_does_not_call_the_llm_when_there_is_nothing_to_quote():
    llm = fake_llm({"groups": [], "ungrouped": []})
    out, used = draft.generate("d4", [card()], llm)  # 원인 글이 있는 카드가 없다
    assert (
        llm.calls == []
        and used is None
        and out["groups"] == []
        and out["ungrouped"] == []
        and out["degraded"] is None
    )


def test_generate_d4_groups_cause_quotes_and_adds_the_unknown_question_only_when_needed():
    cards = [
        card("24V412000", cause=cause("Contaminated solder flux used during manufacturing.")),
        card("17V159000", cause=cause("N/A", "stated_unknown")),
    ]
    llm = fake_llm(
        {
            "groups": [
                {
                    "title": "납땜 플럭스 오염을 적은 선례",
                    "quotes": [
                        {
                            "source_id": "S1",
                            "text": "Contaminated solder flux used during manufacturing.",
                        }
                    ],
                },
                {
                    "title": "원인을 밝히지 않았다고 적은 선례",
                    "quotes": [{"source_id": "S2", "text": "N/A"}],
                },
            ],
            "ungrouped": [],
        }
    )
    out, used = draft.generate("d4", cards, llm)
    assert out["model"] == "gpt-6-luna-x" and used.input_tokens == 100
    assert [g["title"] for g in out["groups"]] == [
        "납땜 플럭스 오염을 적은 선례",
        "원인을 밝히지 않았다고 적은 선례",
    ]
    assert (
        out["groups"][1]["items"][0]["cause_status"] == "stated_unknown"
    )  # 2글자 이하 원문도 통째로 인용할 수 있다
    assert draft.QUESTION_UNKNOWN in out["questions"] and out["ungrouped"] == []
    only_filled, _ = draft.generate("d4", cards[:1], llm)
    assert draft.QUESTION_UNKNOWN not in only_filled["questions"]
    instructions, text = llm.calls[0]
    assert (
        "EXACTLY" in instructions
        and "[S1] campno=24V412000 field=cause" in text
        and "[S2] campno=17V159000" in text
    )


def test_generate_rejects_unknown_steps():
    with pytest.raises(ValueError):
        draft.generate("d3", [card()], None)


# ---------- call_llm ----------
class Resp:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def completed(text):
    return {
        "status": "completed",
        "model": "gpt-6-luna-2026",
        "output": [
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 7, "output_tokens": 3},
    }


def test_call_llm_sends_a_strict_json_schema_request_without_storing_and_reads_the_message_text():
    seen = {}

    def opener(req, timeout):
        seen.update(
            body=json.loads(req.data),
            headers=dict(req.header_items()),
            url=req.full_url,
            timeout=timeout,
            method=req.get_method(),
        )
        return Resp(completed('{"groups":[],"ungrouped":[]}'))

    r = draft.call_llm("rules", "input", api_key="sk-test-123", opener=opener)
    b = seen["body"]
    assert seen["url"] == draft.ENDPOINT and seen["method"] == "POST" and seen["timeout"] == 25.0
    assert seen["headers"]["Authorization"] == "Bearer sk-test-123"
    assert (b["model"], b["instructions"], b["input"], b["store"]) == (
        "gpt-6-luna",
        "rules",
        "input",
        False,
    )
    assert (
        b["reasoning"] == {"effort": "none"} and b["max_output_tokens"] == draft.MAX_OUTPUT_TOKENS
    )
    assert b["text"]["format"]["type"] == "json_schema" and b["text"]["format"]["strict"] is True
    assert (r.text, r.model, r.input_tokens, r.output_tokens) == (
        '{"groups":[],"ungrouped":[]}',
        "gpt-6-luna-2026",
        7,
        3,
    )
    draft.call_llm("r", "i", api_key="k", model="gpt-4o-mini", effort=None, opener=opener)
    assert "reasoning" not in seen["body"] and seen["body"]["model"] == "gpt-4o-mini"


@pytest.mark.parametrize(
    ("response", "kind"),
    [
        ({"status": "incomplete", "output": []}, "incomplete"),
        (
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}],
            },
            "refusal",
        ),
        ({"status": "completed", "output": []}, "format"),
        (b"<html>", "format"),
    ],
)
def test_call_llm_turns_unusable_responses_into_typed_errors(response, kind):
    with pytest.raises(LlmError) as e:
        draft.call_llm("r", "i", api_key="sk-secret", opener=lambda req, timeout: Resp(response))
    assert e.value.kind == kind and "sk-secret" not in str(e.value)


def test_call_llm_errors_never_contain_the_key_or_the_http_body():
    def http_error(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"Incorrect API key sk-secret"}'),
        )

    with pytest.raises(LlmError) as e:
        draft.call_llm("r", "i", api_key="sk-secret", opener=http_error)
    assert e.value.kind == "http" and str(e.value) == "http: status 401"

    def down(req, timeout):
        raise urllib.error.URLError("sk-secret in message")

    with pytest.raises(LlmError) as e2:
        draft.call_llm("r", "i", api_key="sk-secret", opener=down)
    assert (
        str(e2.value) == "network" and e2.value.__cause__ is None and e2.value.__suppress_context__
    )


def test_prompt_lists_every_source_with_its_id_and_the_task_for_the_step():
    srcs = [
        Source("S1", "24V412000", "defect", "text one", {}),
        Source("S2", "24V412000", "consequence", "text two", {}),
    ]
    instructions, text = draft.prompt_for("d2", srcs)
    assert draft.TASKS["d2"] in instructions and draft.COMMON_RULES in instructions
    assert (
        text
        == "Sources:\n\n[S1] campno=24V412000 field=defect\ntext one\n\n[S2] campno=24V412000 field=consequence\ntext two"
    )


@pytest.mark.parametrize(
    "title",
    [
        "공급업체 공정 품질 편차로 인한 씰 누유",
        "PCB 제조 중 오염된 플럭스",
        "원인이 보고되지 않음",
        "습기 유입과 ABS 회로 단락 가능성",
    ],
)
def test_titles_without_the_wording_frame_are_replaced_even_if_they_sound_neutral(title):
    """실제 표본(2026-10-16)에서 원문의 "possible"·"could"가 빠진 "~로 인한 ~" 제목이 나왔다 — "~적은 선례" 꼴만 허용한다."""
    assert not draft.title_ok(title)
    out = draft.assemble(
        srcs2(),
        {
            "groups": [
                {
                    "title": title,
                    "quotes": [{"source_id": "S1", "text": "The circuit board may short circuit"}],
                }
            ],
            "ungrouped": [],
        },
    )
    assert out["groups"][0]["title"] == "묶음 1" and out["rejected"]["bad_title"] == 1


def test_assemble_counts_quotes_re_anchored_because_only_whitespace_differed():
    payload = {
        "groups": [
            {
                "title": "t를 적은 선례",
                "quotes": [
                    {"source_id": "S1", "text": "vehicles. The circuit board"},
                    {"source_id": "S2", "text": CONSEQ},
                ],
            }
        ],
        "ungrouped": [],
    }
    assert (
        draft.assemble(srcs2(), payload)["relocated"] == 1
    )  # S1만 이중 공백이 달랐고 S2는 글자 그대로
    assert draft.assemble(srcs2(), {"groups": [], "ungrouped": []})["relocated"] == 0


TEXT = "It was not found. The part may have failed. Then nothing happened."


@pytest.mark.parametrize("quote", ["have failed", "not found", "The part may have failed.", "Then"])
def test_a_partial_quote_puts_the_whole_source_text_so_qualifiers_cannot_be_dropped(quote):
    """리뷰 지적(PR #141) — 글자만 같으면 받던 인용이 "may"·"not" 같은 한정어를 뺀 조각일 수 있었다. 이제 LLM의 구간은
    "이 출처를 묶음에 넣는다"는 표시일 뿐이고 화면에는 그 출처의 전체 원문이 나간다."""
    src = Source("S1", "24V412000", "defect", TEXT, {"speaker": SPEAKER})
    out = draft.assemble(
        [src],
        {"groups": [{"title": "t를 적은 선례", "quotes": [{"source_id": "S1", "text": quote}]}]},
    )
    it = out["groups"][0]["items"][0]
    assert (it["start"], it["end"]) == (0, len(TEXT)) and it["quote"] == TEXT


def test_the_unknown_expression_question_asks_the_user_to_check_instead_of_judging():
    qs = draft.questions_for(
        "d4",
        [
            Source(
                "S1",
                "26V219000",
                "cause",
                "unknown -- axles were received with a bad weld",
                {"speaker": SPEAKER, "cause_status": "stated_unknown"},
            )
        ],
    )
    unknown = qs[-1]
    assert "쓸 수 없" not in unknown and "원문 전체를 확인" in unknown and unknown.endswith("?")


def test_the_key_never_appears_in_repr_of_config_or_llm_callable():
    cfg = draft.DraftConfig(True, "sk-secret", draft.DEFAULT_MODEL, draft.DEFAULT_EFFORT, 6)
    assert "sk-secret" not in repr(cfg)
    assert "sk-secret" not in repr(cfg.llm())


def test_a_connection_cut_while_reading_the_body_degrades_instead_of_failing_the_request():
    import http.client

    class Cut:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            raise http.client.IncompleteRead(b"partial")

    with pytest.raises(LlmError) as e:
        draft.call_llm("r", "i", api_key="sk-secret", opener=lambda req, timeout: Cut())
    assert e.value.kind == "network" and "sk-secret" not in str(e.value)
    out, used = draft.generate(
        "d2", [card()], lambda *_: (_ for _ in ()).throw(LlmError("network"))
    )
    assert out["degraded"] == "llm_failed" and used is None


def test_a_json_response_that_is_not_an_object_is_a_format_error():
    with pytest.raises(LlmError) as e:
        draft.call_llm("r", "i", api_key="k", opener=lambda req, timeout: Resp([1, 2]))
    assert e.value.kind == "format"


# ---------- 확인 질문 풀 — LLM은 번호만 고른다 (DEC-071) ----------
def test_the_question_pool_is_ten_fixed_questions_that_never_judge():
    assert list(draft.QUESTION_POOL) == [f"P{i}" for i in range(1, 11)]
    assert set(draft.QUESTION_TOPICS) == set(draft.QUESTION_POOL)
    for qid, text in draft.QUESTION_POOL.items():
        assert text.endswith("습니까?"), qid  # 질문형이다
        assert not draft.VERDICT_RE.search(text), (
            qid
        )  # principle-ok: 풀 문장에 판정 표현이 없는지 검사
        assert not any(
            w in text for w in ("원인은", "원인입니다", "적용", "다릅니다", "같습니다")
        ), qid
    assert len(set(draft.QUESTION_POOL.values())) == 10


def test_pick_questions_keeps_only_pool_ids_once_in_the_order_given_and_at_most_three():
    none = {"unknown_question": 0, "duplicate_question": 0, "over_limit_question": 0}
    ids, why = draft.pick_questions({"question_ids": ["P3", "P3", "P99", "P1", "x", "P2", "P5"]})
    assert ids == ["P3", "P1", "P2"]
    # 풀 밖 P99·x / 중복 P3 / 상한 3개를 넘은 유효한 P5 — 이유를 따로 센다
    assert why == {"unknown_question": 2, "duplicate_question": 1, "over_limit_question": 1}
    assert draft.pick_questions({"question_ids": []}) == ([], none)
    assert draft.pick_questions({}) == ([], none)
    assert draft.pick_questions({"question_ids": "P1"}) == ([], {**none, "unknown_question": 1})
    assert draft.pick_questions({"question_ids": [1, None, ["P1"], "P4"]}) == (
        ["P4"],
        {**none, "unknown_question": 3},
    )
    more = draft.pick_questions({"question_ids": ["P1", "P2", "P3", "P4", "P5"]})[1]
    assert more == {
        **none,
        "over_limit_question": 2,
    }  # 유효한 번호를 더 준 것과 풀 밖 번호를 준 것이 구분된다


def test_the_d4_prompt_offers_the_topics_by_id_and_d2_asks_for_an_empty_list():
    srcs = [Source("S1", "24V412000", "cause", "text", {})]
    d4, _ = draft.prompt_for("d4", srcs)
    for qid, topic in draft.QUESTION_TOPICS.items():
        assert f"{qid}: {topic}" in d4
    assert "never write" in d4 and "ids" in d4  # 문장을 쓰지 않고 번호만 고른다는 지시
    for text in draft.QUESTION_POOL.values():
        assert text not in d4  # 한국어 문장은 LLM에 보이지 않는다 — 번호와 영어 주제만
    d2, _ = draft.prompt_for("d2", [Source("S1", "24V412000", "defect", "text", {})])
    assert "question_ids" in d2 and "empty" in d2 and "P1:" not in d2


def test_the_schema_requires_question_ids_as_a_strict_string_list():
    assert "question_ids" in draft.SCHEMA["required"]
    assert draft.SCHEMA["properties"]["question_ids"] == {
        "type": "array",
        "items": {"type": "string"},
    }


def test_generate_d4_returns_the_picked_pool_sentences_and_counts_what_it_dropped():
    cards = [card("24V412000", cause=cause("Contaminated solder flux used during manufacturing."))]
    payload = {
        "groups": [],
        "ungrouped": ["S1"],
        "question_ids": ["P5", "P2", "P42", "P5"],
    }
    out, _ = draft.generate("d4", cards, fake_llm(payload))
    assert [q["id"] for q in out["picked_questions"]] == ["P5", "P2"]
    assert [q["text"] for q in out["picked_questions"]] == [
        draft.QUESTION_POOL["P5"],
        draft.QUESTION_POOL["P2"],
    ]  # 문장은 풀에서 가져온 것 — LLM이 돌려준 글자가 아니다
    assert (out["rejected"]["unknown_question"], out["rejected"]["duplicate_question"]) == (
        1,
        1,
    )  # P42는 풀 밖, 두 번째 P5는 중복
    assert out["rejected"]["over_limit_question"] == 0
    assert out["questions"] == draft.questions_for(
        "d4", draft.build_sources("d4", cards)
    )  # 기본 문장은 그대로 코드가 붙인다


def test_generate_without_picks_or_when_off_or_failed_has_no_picked_questions():
    cards = [card("24V412000", cause=cause("Contaminated solder flux used during manufacturing."))]
    ok, _ = draft.generate(
        "d4", cards, fake_llm({"groups": [], "ungrouped": ["S1"]})
    )  # 구 형식 응답(question_ids 없음)
    assert ok["picked_questions"] == [] and all(
        ok["rejected"][k] == 0
        for k in ("unknown_question", "duplicate_question", "over_limit_question")
    )
    off, _ = draft.generate("d4", cards, None)
    assert off["picked_questions"] == [] and off["degraded"] == "disabled"

    def boom(instructions, text):
        raise LlmError("network")

    failed, _ = draft.generate("d4", cards, boom)
    assert failed["picked_questions"] == [] and failed["degraded"] == "llm_failed"


def test_d2_never_picks_questions_even_if_the_model_returns_ids():
    cards = [card("24V412000")]
    out, _ = draft.generate(
        "d2", cards, fake_llm({"groups": [], "ungrouped": [], "question_ids": ["P1"]})
    )
    assert out["picked_questions"] == []  # 풀은 D4 전용이다

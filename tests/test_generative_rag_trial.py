from scripts.defect_precedent.generative_rag_trial import score_rows

CARD = {"campno": "20V001000", "received_date": "20200105"}
BY_CAMPNO = {"20V001000": CARD, "20V002000": {"campno": "20V002000", "received_date": "20200106"}}
CAMPAIGNS = {"20V001": "20200105", "20V002": "20200106"}
CAUSES = {
    "20V001": {
        "campaign": "20V001",
        "resolution": "resolved",
        "cause_status": "filled",
        "cause_text": "The  seal was  misassembled.",
        "source_file": "x.pdf",
        "submission_date": "20200110",
        "pdfs": {"x.pdf": "0" * 64},
        "text_basis": None,
    }
}


def row(answer, citations, given=("20V001000", "20V002000")):
    return {
        "action_no": "A",
        "given": list(given),
        "output": {"answer": answer, "citations": citations},
    }


def score(rows):
    return score_rows(rows, BY_CAMPNO, CAMPAIGNS, CAUSES, {})


def test_clean_answer_has_no_violation():
    r = row(
        "The seal failed (20V001000).",
        [{"campno": "20V001000", "cause_quote": "The seal was misassembled."}],
    )
    c = score([r])
    assert c["questions_with_violation"] == 0
    assert c["quotes_checked"] == c["quotes_verbatim"] == 1  # 공백만 다른 인용은 원문으로 본다


def test_number_outside_given_set_is_counted_in_citations_and_text():
    r = row("See (99V999000).", [{"campno": "99V999000", "cause_quote": ""}])
    c = score([r])
    assert c["cites_out_of_given"] == 1 and c["cites_not_in_data"] == 1
    assert c["answer_ids_out_of_given"] == 1
    assert c["questions_with_violation"] == 1


def test_altered_quote_and_quote_without_cause_text_are_violations():
    altered = row("x (20V001000).", [{"campno": "20V001000", "cause_quote": "The seal was bent."}])
    none_given = row("x (20V002000).", [{"campno": "20V002000", "cause_quote": "Some cause."}])
    c = score([altered, none_given])
    assert c["quotes_verbatim"] == 0
    assert c["quotes_no_cause_given"] == 1
    assert c["questions_with_violation"] == 2


def test_judgment_phrase_and_sentences_without_number():
    r = row("This recall is verdict-like. Another sentence (20V001000).", [])
    c = score([r])
    assert c["answers_with_judgment"] == 1
    assert c["sentences"] == 2 and c["sentences_without_id"] == 1


def test_failed_call_is_counted_as_error_not_scored():
    c = score([{"action_no": "A", "given": [], "error": "boom"}])
    assert c["errors"] == 1 and c["answered"] == 0

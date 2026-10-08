import json
import re

from scripts.defect_precedent import time_eval_questions as tq

ONE_PAGE = """ODI RESUME
Resume Page 1 of 1
Investigation: PE 21-001 Open
Investigation: PE 21-001
Date Opened: 01/08/2021
Subject: Front Roof Panel Detachment
Action: A Preliminary Evaluation has been opened.
Summary:
ODI has received seven complaints alleging roof panel detachment in 2015 Mercedes-
Benz C-Class vehicles.   The detachments occurred at 60 to 65 miles per hour.
The reports cited above can be reviewed at NHTSA.gov.
"""

TWO_PAGES = """ODI RESUME
Resume Page 1 of 2
Investigation: EA 21-003 Open
Date Opened: 12/22/2021
Summary: First part of the summary ends here and
Resume Page 2 of 2
Investigation: EA 21-003 Open
continues on the second page.
"""


def test_extract_copies_the_summary_and_only_normalizes_whitespace():
    r = tq.extract(ONE_PAGE, "20210108")
    assert r["check"] == "통과" and r["doc_date_opened"] == "20210108"
    assert r["question"].startswith("ODI has received seven complaints")
    assert "Mercedes- Benz C-Class" in r["question"]  # 하이픈 줄바꿈은 고치지 않고 그대로 둔다
    assert "  " not in r["question"] and "\n" not in r["question"]
    assert r["hyphen_line_breaks"] == 1


def test_extract_drops_only_page_header_lines_inside_the_summary():
    r = tq.extract(TWO_PAGES, "20211222")
    assert r["check"] == "통과"
    assert r["question"] == "First part of the summary ends here and continues on the second page."
    assert r["removed_header_lines"] == 2


def test_extract_flags_a_date_mismatch_without_fixing_anything():
    r = tq.extract(ONE_PAGE, "20210109")
    assert r["check"].startswith("실패") and "개시일 불일치" in r["check"]
    assert r["question"].startswith("ODI has received")  # 질문은 그대로 두고 실패로만 표시한다


def test_extract_reports_a_document_without_summary_as_failed():
    r = tq.extract("Date Opened: 01/08/2021\nsome text without the section", "20210108")
    assert r["check"].startswith("실패") and "Summary" in r["check"] and r["extractable"]


def test_a_document_without_date_opened_is_not_extractable():
    assert not tq.extract("", "20210108")["extractable"]
    assert not tq.extract("Dear Mr. Qi:\nSummary: a letter", "20090203")["extractable"]


def test_fill_skips_missing_and_unextractable_documents_in_reserve_order():
    draw = {
        "seed": 1,
        "pilot": [{"action_no": "PE00001", "open_date": "20100101"}],
        "main": [
            {"action_no": "PE00002", "open_date": "20100102"},
            {"action_no": "PE00003", "open_date": "20100103"},
        ],
        "reserve": [{"action_no": f"PE0001{i}", "open_date": "20100110"} for i in range(3)],
        "pool": [],
    }
    status = {
        "PE00001": "추출 불가",
        "PE00010": "문서 없음",
        "PE00011": "확보",
        "PE00002": "확보",
        "PE00003": "확보",
        "PE00012": "확보",
    }
    made = []

    def make(a, d):
        made.append(a)
        return {"action_no": a, "open_date": d, "status": status[a], "check": "통과"}

    out = tq.fill(draw, make)
    assert [r["action_no"] for r in out["pilot"]] == ["PE00011"]
    assert [r["action_no"] for r in out["main"]] == ["PE00002", "PE00003"]
    assert [(x["skipped"], x["reason"], x["replaced_by"]) for x in out["replacements"]] == [
        ("PE00001", "추출 불가", "PE00010"),
        ("PE00010", "문서 없음", "PE00011"),
    ]
    assert made == ["PE00001", "PE00010", "PE00011", "PE00002", "PE00003"]


def test_fill_continues_with_the_same_hash_rank_when_the_reserve_runs_out():
    pool = [[f"PE0{i:04d}", "20100101"] for i in range(5)]
    draw = {
        "seed": 7,
        "pilot": [{"action_no": "PE00000", "open_date": "20100101"}],
        "main": [],
        "reserve": [],
        "pool": pool,
    }
    seen = []

    def make(a, d):
        seen.append(a)
        return {
            "action_no": a,
            "open_date": d,
            "status": "추출 불가" if len(seen) < 3 else "확보",
            "check": "통과",
        }

    tq.fill(draw, make)
    assert (
        seen[1:] == sorted((a for a, _ in pool if a != "PE00000"), key=lambda a: tq.rank(a, 7))[:2]
    )


def test_the_committed_questions_are_complete_traceable_and_all_checked():
    q = json.loads(tq.OUT.read_text(encoding="utf-8"))
    assert q["draw_sha256"] == tq.draw_digest()  # 줄바꿈(LF/CRLF)과 무관하게 같은 값
    recs = q["pilot"] + q["main"]
    assert (len(q["pilot"]), len(q["main"])) == (5, 45) and len(
        {r["action_no"] for r in recs}
    ) == 50
    for r in recs:
        assert r["query_source"] == "ODI Resume" and r["status"] == "확보" and r["check"] == "통과"
        assert re.fullmatch(r"[0-9a-f]{64}", r["pdf_sha256"])
        assert re.fullmatch(
            rf"https://static\.nhtsa\.gov/odi/inv/\d{{4}}/INOA-{r['action_no']}-\d+\.pdf",
            r["source_url"],
            re.I,
        )
        assert r["doc_date_opened"] == r["open_date"] and r["question"]
        assert "\n" not in r["question"] and "  " not in r["question"]
    draw = json.loads(tq.DRAW.read_text(encoding="utf-8"))
    allowed = {x["action_no"] for x in draw["pilot"] + draw["main"] + draw["reserve"]} | {
        a for a, _ in draw["pool"]
    }
    assert {r["action_no"] for r in recs} <= allowed
    assert q["counts"]["check_failed"] == 0 and q["counts"]["replacements"] == len(
        q["replacements"]
    )


def test_every_question_line_carries_the_principle_ok_note_and_the_text_is_untouched():
    # 서비스 원칙 검사(applies 등)에 원문 속 일반 영어 낱말이 걸리지 않게 줄마다 표시를 달았다. 글자는 그대로다
    text = tq.OUT.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.lstrip().startswith('"question":')]
    assert len(lines) == 50 and all("principle-ok:" in ln for ln in lines)
    q = json.loads(text)
    assert all(r["question_note"] == tq.QUESTION_NOTE for r in q["pilot"] + q["main"])
    for r in q["pilot"] + q["main"]:
        del r["question_note"]  # 표시는 글을 쓸 때 줄에 붙이는 것이라 읽은 데이터에서 빼고 다시 쓰면 같은 글이 나와야 한다
    assert tq.dumps(q) == text

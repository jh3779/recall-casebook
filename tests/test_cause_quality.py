"""원인 품질 표본 도구(`cause_quality`) — 합성 데이터로 표본 규칙과 채점 거부 조건을 본다."""

import pytest

from scripts.defect_precedent import cause_quality as cq
from scripts.defect_precedent.cause_trials import text_sha


def _card(campno: str) -> dict:
    return {
        "campno": campno,
        "maker": "M",
        "components": ["AIR BAGS"],
        "defect": "d",
        "received_date": "20200101",
    }


def _cause(campaign: str, text: str) -> dict:
    return {
        "campaign": campaign,
        "resolution": "single",
        "cause_status": "filled",
        "cause_text": text,
        "source_file": "a.pdf",
        "pdfs": {"a.pdf": "0" * 64},
        "submission_date": "20200102",
    }


def _inv(action: str, summary: str) -> dict:
    return {"action": action, "subject": "s", "summary": summary, "open_date": "", "close_date": ""}


def test_question_own_investigation_summary_is_excluded():
    """질문의 출처 조사 요약은 질문 문장과 같은 글이라 표본에 넣지 않는다(누수)."""
    card = _card("20V000000")
    invs = {"20V000000": [_inv("EA20001", "own"), _inv("PE19001", "other")]}
    got = cq.cause_texts(card, {}, {}, invs, "EA20001")
    assert [g["cause_ref"] for g in got] == ["PE19001"]


def test_573_cause_only_when_server_would_show_it():
    """573 원인은 서버의 `cause_573`이 filled로 돌려줄 때만 넣는다 — 판본 미확정·빈 칸은 빠진다."""
    card = _card("20V001000")
    filled = {"20V001": _cause("20V001", "The cause was X.")}
    assert [g["cause_source"] for g in cq.cause_texts(card, filled, {}, {}, "")] == ["573"]
    unresolved = {"20V001": {**_cause("20V001", "x"), "resolution": "unresolved"}}
    assert cq.cause_texts(card, unresolved, {}, {}, "") == []


def _setup(n_questions: int = 40):
    cards = [_card(f"20V{i:03d}000") for i in range(15)]
    by_id = {c["campno"]: c for c in cards}
    causes = {c["campno"][:6]: _cause(c["campno"][:6], f"cause {i}") for i, c in enumerate(cards)}
    invs = {c["campno"]: [_inv(f"PE{i:05d}", f"summary {i}")] for i, c in enumerate(cards)}
    questions = [{"action_no": f"EA{i:05d}", "question": f"q{i}"} for i in range(n_questions)]
    ids = list(by_id)
    rankings = {q["action_no"]: ids[i % 5 :] + ids[: i % 5] for i, q in enumerate(questions)}
    return questions, rankings, by_id, causes, invs


def test_draw_is_fixed_by_seed_and_never_repeats_a_recall():
    args = _setup()
    a = cq.draw(*args[:4], {}, args[4])
    b = cq.draw(*args[:4], {}, args[4])
    assert a == b  # 같은 입력이면 같은 표본(시드 고정)
    campnos = [r["campno"] for r in a]
    assert len(campnos) == len(set(campnos))
    assert all(
        r["campno"] in args[1][r["question_action"]][: cq.TOP] for r in a
    )  # 상위 10건 안에서만
    assert all(r["text_sha256"] == text_sha(r["cause_text"]) and r["label"] == "" for r in a)


def test_draw_stops_at_n():
    questions, rankings, _, _, _ = _setup()
    cards = {f"C{i:08d}": _card(f"C{i:08d}") for i in range(100)}
    ids = list(cards)
    rankings = {q["action_no"]: ids[i * 2 : i * 2 + 10] for i, q in enumerate(questions)}
    invs = {c: [_inv("PE00000", "s")] for c in ids}
    assert len(cq.draw(questions, rankings, cards, {}, {}, invs)) == cq.N


def _labeled(label: str = "yes") -> list[dict]:
    rows = cq.draw(*_setup()[:4], {}, _setup()[4])
    return [{**r, "label": label, "labeler_id": "L1"} for r in rows]


def test_score_reports_rate_and_wilson():
    rows = _labeled()
    rows[0]["label"] = "no"
    rows[1]["label"] = "unsure"
    got = cq.score(rows)
    n = len(rows)
    assert got["counts"] == {"yes": n - 2, "no": 1, "unsure": 1}
    assert got["yes_rate"] == round((n - 2) / (n - 1), 3)
    lo, hi = got["yes_rate_wilson95"]
    assert lo < got["yes_rate"] <= hi


@pytest.mark.parametrize(
    "change",
    [
        {"cause_text": "edited"},  # 원문을 고쳤다
        {"label": ""},  # 표시가 빠졌다
        {"label": "maybe"},  # 정한 값이 아니다
        {"labeler_id": " "},  # 표시한 사람이 없다
    ],
)
def test_score_refuses_bad_sheet(change):
    rows = _labeled()
    rows[0] = {**rows[0], **change}
    with pytest.raises(SystemExit):
        cq.score(rows)

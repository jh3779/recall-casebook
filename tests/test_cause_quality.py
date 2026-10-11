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
    invs = {
        c: [_inv("PE00000", f"s {c}")] for c in ids
    }  # 원인 글이 카드마다 다르다(같은 글은 한 번만 뽑힌다)
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


def test_customer_cards_beyond_the_five_shown_are_not_sampled():
    """서버는 고객사 카드를 5건만 보여 준다 — 합친 순위 10위 안이어도 6번째 고객사 카드는 화면에 없어 표본에 넣지 않는다."""
    cards = {f"K{i:08d}": {**_card(f"K{i:08d}"), "maker_group": "Kia"} for i in range(10)}
    invs = {c: [_inv(f"PE{i:05d}", f"s{i}")] for i, c in enumerate(cards)}
    ranking = list(cards)
    questions = [{"action_no": f"EA{i:05d}", "question": "q"} for i in range(40)]
    rows = cq.draw(questions, {q["action_no"]: ranking for q in questions}, cards, {}, {}, invs)
    assert {r["campno"] for r in rows} == set(ranking[:5])


def test_same_cause_text_is_sampled_only_once():
    """앞 6자리가 같은 리콜은 같은 573 보고서를 공유한다 — 같은 원인 글은 한 번만 뽑는다."""
    cards = {c: _card(c) for c in ("20V001000", "20V001001")}
    causes = {"20V001": _cause("20V001", "same cause")}
    questions = [{"action_no": f"EA{i:05d}", "question": "q"} for i in range(5)]
    rows = cq.draw(
        questions, {q["action_no"]: list(cards) for q in questions}, cards, causes, {}, {}
    )
    assert len(rows) == 1


def test_score_refuses_changed_context_but_accepts_sorted_rows_and_capitalized_labels():
    rows = _labeled()
    rows[0] = {**rows[0], "question": "edited question"}
    with pytest.raises(SystemExit, match="질문·카드"):
        cq.score(rows)
    rows = _labeled("Yes")[::-1]  # 정렬·대문자
    assert cq.sample_fingerprint(rows) == cq.sample_fingerprint(_labeled())
    assert cq.score(rows)["counts"]["yes"] == len(rows)


def test_score_reports_rates_by_source():
    rows = _labeled()
    got = cq.score(rows)["by_source"]
    assert set(got) == {"573", "조사 요약"}
    assert all(v["yes_rate"] == 1.0 and v["yes_rate_wilson95"] for v in got.values())


def test_sheet_refuses_to_overwrite_an_existing_sheet(tmp_path):
    """표시한 시트를 빈 시트로 덮어쓰지 않는다 — 데이터를 읽기 전에 멈춘다."""
    (tmp_path / "cause_quality_sheet.csv").write_text("labeled", encoding="utf-8")
    with pytest.raises(SystemExit, match="이미 있다"):
        cq.main(["sheet", "--out", str(tmp_path)])
    assert (tmp_path / "cause_quality_sheet.csv").read_text(encoding="utf-8") == "labeled"


def test_score_refuses_changed_maker_or_components():
    for field in ("maker", "components"):
        rows = _labeled()
        rows[0] = {**rows[0], field: "edited"}
        with pytest.raises(SystemExit, match="질문·카드"):
            cq.score(rows)


def test_573_rows_keep_source_pdf_and_investigation_rows_leave_it_blank():
    """573 원인 글은 어느 판본 PDF에서 왔는지(파일·sha256·제출일)를 시트에 남긴다(AGENTS.md 2-2·2-4)."""
    card = _card("20V001000")
    got = cq.cause_texts(
        card,
        {"20V001": _cause("20V001", "The cause was X.")},
        {},
        {"20V001000": [_inv("PE1", "s")]},
        "",
    )
    by_src = {g["cause_source"]: g for g in got}
    assert (
        by_src["573"]["source_file"],
        by_src["573"]["pdf_sha256"],
        by_src["573"]["submission_date"],
    ) == (
        "a.pdf",
        "0" * 64,
        "20200102",
    )
    assert by_src["조사 요약"]["source_file"] == by_src["조사 요약"]["pdf_sha256"] == ""


def test_score_refuses_changed_sample_no_or_source_file():
    for field in ("sample_no", "source_file"):
        rows = _labeled()
        rows[0] = {**rows[0], field: "edited"}
        with pytest.raises(SystemExit, match="질문·카드"):
            cq.score(rows)


def test_cmd_score_names_the_row_and_field_a_spreadsheet_changed(tmp_path):
    """스프레드시트가 21E027 같은 값을 숫자로 바꾸면 "줄을 뺐다"가 아니라 어느 줄의 어느 칸인지 알려 준다."""
    import csv
    import json

    rows = _labeled()
    meta = {
        "build_id": "b",
        "seed": cq.SEED,
        "sample_sha256": cq.sample_fingerprint(rows),
        "rows": [{k: r[k] for k in ("sample_no", *cq.ROW_FIELDS[1:], "text_sha256")} for r in rows],
    }
    rows[2] = {**rows[2], "cause_ref": "2.1E+28"}
    sheet = tmp_path / "cause_quality_sheet.csv"
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cq.COLS)
        w.writeheader()
        w.writerows(rows)
    (tmp_path / "cause_quality_sheet.csv.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(SystemExit, match=r"3번 cause_ref"):
        cq.main(["score", "--sheet", str(sheet)])

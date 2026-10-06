"""scripts/defect_precedent 의 순수 함수 테스트 — 네트워크·원본 데이터 없이 작은 예시로 확인한다."""

from scripts.defect_precedent import bm25_baseline as bm
from scripts.defect_precedent import nhtsa
from scripts.defect_precedent.rclrpt import parse_report


def test_first_sentence_keeps_decimal_and_abbreviation():
    # EA12006: 마침표마다 자르면 "approximately 2."에서 잘리던 사례
    text = "ODI opened a recall of approximately 2.5 million U.S. vehicles involving airbags. Next."
    assert nhtsa.first_sentence(text) == (
        "ODI opened a recall of approximately 2.5 million U.S. vehicles involving airbags."
    )


def test_first_sentence_splits_missing_space_boundary():
    # 원문에 마침표 뒤 공백이 없는 경우 ("fourteen.During")
    text = "Complaints have risen to fourteen.During the investigation, ODI contacted BMW."
    assert nhtsa.first_sentence(text) == "Complaints have risen to fourteen."


def test_first_sentence_skips_no_and_inc():
    text = "Recall No. 5 by Acme Inc. covers brakes. Second sentence."
    assert nhtsa.first_sentence(text) == "Recall No. 5 by Acme Inc. covers brakes."


def _rcl(campno, maker, defect, comp="BRAKES", rcdate="20200101"):
    row = dict.fromkeys(nhtsa.RCL_COLS, "")
    row.update(CAMPNO=campno, MFGNAME=maker, DESC_DEFECT=defect, COMPNAME=comp, RCDATE=rcdate)
    return row


def test_build_cards_merges_rows_and_groups_copied_text():
    body = "The bolt that attaches the gear assembly may fracture allowing the gear to disengage."
    rows = [
        _rcl("20V001000", "A Corp", f"A Corp is recalling model X. {body}", comp="BRAKES"),
        _rcl("20V001000", "A Corp", f"A Corp is recalling model X. {body}", comp="STEERING"),
        _rcl("20V002000", "B Inc", f"B Inc is recalling model Y. {body}"),
        _rcl("20V003000", "C Ltd", "Short text."),
    ]
    cards = nhtsa.build_cards(rows, "2026-10-06")
    assert list(cards) == ["20V001000", "20V002000", "20V003000"]
    assert cards["20V001000"]["components"] == ["BRAKES", "STEERING"]
    # 첫 문장(회사·차종)만 다르고 본문이 같으면 같은 묶음
    assert cards["20V001000"]["dup_group"] == cards["20V002000"]["dup_group"]
    # 본문이 짧으면 자기 리콜 번호가 곧 묶음
    assert cards["20V003000"]["dup_group"] == "20V003000"


def _inv(action, campno, summary, odate="20150101"):
    row = dict.fromkeys(nhtsa.INV_COLS, "")
    row.update(ACTION=action, CAMPNO=campno, SUMMARY=summary, ODATE=odate)
    return row


def test_build_eval_filters_and_keeps_gold_set():
    cards = nhtsa.build_cards(
        [
            _rcl("15V001000", "A", "x", rcdate="20150301"),
            _rcl("15V002000", "A", "y", rcdate="20150301"),
        ],
        "2026-10-06",
    )
    inv = [
        _inv("PE15001", "15V001000", "Six complaints of leaks. More text."),
        _inv(
            "PE15001", "15V002000", "Six complaints of leaks. More text."
        ),  # 같은 조사의 두 번째 리콜
        _inv("PE15002", "15V001000", "There is no summary currently available"),  # 자리표시 → 제외
        _inv("RQ15003", "15V001000", "Recall query summary."),  # PE·EA가 아님 → 제외
        _inv("EA15004", "99V999000", "Recall not in file."),  # 리콜 파일에 없음 → 제외
        _inv("EA09005", "15V001000", "Old one.", odate="20090101"),
    ]
    questions = {q["action_no"]: q for q in nhtsa.build_eval(inv, cards)}
    assert set(questions) == {"PE15001", "EA09005"}
    assert questions["PE15001"]["gold_campnos"] == ["15V001000", "15V002000"]
    assert questions["PE15001"]["question"] == "Six complaints of leaks."
    assert questions["PE15001"]["set"] == ["all", "since2010", "rclrpt_range"]
    assert questions["EA09005"]["set"] == ["all", "rclrpt_range"]


OLD_FORM = """
            Submission Date : JUN 05, 2024
      Description of the Cause : Contaminated solder flux used during manufacturing of the PCB controller by
                                  the supplier.
  Identification of Any Warning MIL illumination
Supplier Identification :

 Component Manufacturer
     Name : HL Mando America
  Address : 4201 Northpark Drive
  Country : United States
Chronology :
"""

NEW_FORM = """
Submission Date: OCT 01, 2025
Description of the cause:


Identification of any warning that can occur:

Component Manufacturer

          Tier of Supplier:
            Supplier Type:
                    Name: BMW AG
                  Address:
                  Country:

Involved Components
"""


def test_parse_report_old_form():
    r = parse_report(OLD_FORM)
    assert r["submission_date"] == "20240605"
    assert r["cause_status"] == "filled"
    assert r["cause_text"] == (
        "Contaminated solder flux used during manufacturing of the PCB controller by the supplier."
    )
    assert r["supplier_names"] == ["HL Mando America"]
    assert r["supplier_countries"] == ["United States"]
    assert r["new_form"] is False


def test_parse_report_new_form_empty_cause_does_not_take_next_heading():
    # 새 양식에서 원인 칸이 비면 다음 칸 제목을 원인으로 잡던 문제
    r = parse_report(NEW_FORM)
    assert r["cause_status"] == "empty"
    assert r["cause_text"] == ""
    assert r["supplier_names"] == ["BMW AG"]
    assert r["supplier_countries"] == []
    assert r["new_form"] is True


def test_parse_report_nr_cause_is_empty():
    r = parse_report(
        "Description of the Cause : NR\nSupplier Identification :\n Name : NR\nChronology :"
    )
    assert r["cause_status"] == "empty"
    assert r["supplier_names"] == []


def test_bm25_ranks_matching_doc_first_and_hit_counts():
    cards = [
        {"campno": "A", "defect": "brake fluid leak caliper", "consequence": "", "remedy": ""},
        {"campno": "B", "defect": "airbag inflator rupture", "consequence": "", "remedy": ""},
        {"campno": "C", "defect": "seat belt latch", "consequence": "", "remedy": ""},
    ]
    questions = [
        {"question": "fluid leaking from the caliper", "gold_campnos": ["A"]},
        {
            "question": "inflator may rupture",
            "gold_campnos": ["C", "B"],
        },  # 첫 정답은 아니지만 둘째 정답이 1위
    ]
    result = bm.evaluate(cards, questions)
    assert result["any"][1] == 1.0
    assert result["first"][1] == 0.5

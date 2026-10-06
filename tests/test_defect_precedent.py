"""scripts/defect_precedent 의 순수 함수 테스트 — 네트워크·원본 데이터 없이 작은 예시로 확인한다."""

import math
import shutil

import pytest

from scripts.defect_precedent import bm25_baseline as bm
from scripts.defect_precedent import nhtsa, rclrpt
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
    # 회사명에 마침표가 있어도("Inc.", "Co.") 첫 문장 끝을 잘못 잡지 않아야 같은 본문으로 묶인다
    first_a = "Acme Inc. is recalling certain 2020 Ranger trucks."
    rows = [
        _rcl("20V001000", "Acme Inc.", f"{first_a} {body}", comp="BRAKES"),
        _rcl("20V001000", "Acme Inc.", f"{first_a} {body}", comp="STEERING"),
        _rcl("20V002000", "Beta Co.", f"Beta Co. is recalling certain 2021 Pilot SUVs. {body}"),
        _rcl("20V003000", "C Ltd", "Short text."),
    ]
    cards = nhtsa.build_cards(rows, "2026-10-06")
    assert list(cards) == ["20V001000", "20V002000", "20V003000"]
    assert cards["20V001000"]["components"] == ["BRAKES", "STEERING"]
    assert cards["20V001000"]["dup_group"] == cards["20V002000"]["dup_group"]
    # 본문이 짧으면 자기 리콜 번호가 곧 묶음
    assert cards["20V003000"]["dup_group"] == "20V003000"


def test_install_dir_keeps_old_until_swap(tmp_path):
    target = tmp_path / "nhtsa"
    target.mkdir()
    (target / "old.txt").write_text("old")
    new = tmp_path / "nhtsa.partial"
    new.mkdir()
    (new / "new.txt").write_text("new")
    nhtsa.install_dir(new, target)
    assert [p.name for p in target.iterdir()] == ["new.txt"]
    assert not (tmp_path / "nhtsa.old").exists()


def test_write_jsonl_replaces_only_after_complete(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text("old\n")

    def broken_rows():
        yield {"a": 1}
        raise RuntimeError("중간 실패")

    try:
        nhtsa.write_jsonl(path, broken_rows())
    except RuntimeError:
        pass
    assert path.read_text() == "old\n"  # 기존 완성본은 그대로
    assert (tmp_path / "x.jsonl.partial").exists()


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


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext(poppler) 없음")
def test_pdf_read_failure_is_error_not_missing_cause(tmp_path):
    # 깨진 PDF를 "원인 칸 없음"으로 세지 않고 실패로 분리해야 한다
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(rclrpt.ReportError):
        rclrpt._pdf_text(bad)


def test_latest_parsed_skips_image_only_version_and_picks_latest(monkeypatch):
    texts = {
        "a": "Submission Date : JAN 05, 2024\nDescription of the Cause : old cause\nChronology :",
        "b": "",  # 글자 없는 이미지 판본
        "c": "Submission Date : MAR 01, 2024\nDescription of the Cause : new cause\nChronology :",
    }
    monkeypatch.setattr(rclrpt, "_download", lambda key: key)
    monkeypatch.setattr(rclrpt, "_pdf_text", lambda key: texts[key])
    key, parsed = rclrpt.latest_parsed(["a", "b", "c"])
    assert key == "c"
    assert parsed["cause_text"] == "new cause"
    assert parsed["image_only_versions"] == 1


def test_latest_parsed_fails_when_no_readable_version(monkeypatch):
    monkeypatch.setattr(rclrpt, "_download", lambda key: key)
    monkeypatch.setattr(rclrpt, "_pdf_text", lambda key: "")
    with pytest.raises(rclrpt.ReportError):
        rclrpt.latest_parsed(["a"])


def test_first_sentence_abbreviation_before_capital_is_not_a_boundary():
    # 다음 글자가 대문자여야 약어 처리가 실제로 필요하다 ("U.S. The" 는 문장 경계처럼 보임)
    text = "Vehicles sold in the U.S. The agency closed it. Next part."
    assert nhtsa.first_sentence(text) == "Vehicles sold in the U.S. The agency closed it."


def test_first_sentence_splits_uppercase_old_summary():
    # 옛 요약은 전부 대문자이고 마침표 뒤 공백이 없다 ("PE99-076.THE")
    text = "THIS INVESTIGATION WAS UPGRADED FROM PE99-076.THE ALLEGED DEFECT IS A LEAK."
    assert nhtsa.first_sentence(text) == "THIS INVESTIGATION WAS UPGRADED FROM PE99-076."


def test_first_sentence_lowercase_single_letter_is_boundary():
    assert nhtsa.first_sentence("It failed at point a. The agency closed it.") == (
        "It failed at point a."
    )


def test_parse_report_reads_varied_date_formats():
    assert parse_report("Submission Date : NOV 18,2014")["submission_date"] == "20141118"
    assert parse_report("Submission Date : Sep 14, 2015")["submission_date"] == "20150914"
    assert parse_report("Submission Date: OCT 1, 2025")["submission_date"] == "20251001"


def test_parse_report_removes_page_footer_inside_cause():
    text = (
        "Description of the Cause : The seal was installed\n"
        "The information contained in this report was submitted pursuant to 49 CFR §573\n"
        "Part 573 Safety Recall Report 15V-396 Page 4\n"
        "                            in the wrong direction.\n"
        "Identification of Any Warning : none\n"
        "Supplier Identification :\n Name : Acme\n Country : NR\nChronology :"
    )
    r = parse_report(text)
    assert r["cause_text"] == "The seal was installed in the wrong direction."
    # 다른 꼬리말 형식 (16V364): "§ 573 Page 3 of 5 Part 573 Safety Recall Report 16V364"
    other = (
        "Description of the Cause : inflators may experience an\n"
        "The information contained in this report was submitted pursuant to 49 CFR § 573\n"
        "Page 3 of 5 Part 573 Safety Recall Report 16V364\n"
        "alteration over time.\nIdentification of Any Warning : none"
    )
    assert parse_report(other)["cause_text"] == "inflators may experience an alteration over time."
    assert r["supplier_countries"] == []


def test_bm25_negative_idf_uses_floor():
    # 모든 문서에 나오는 단어는 idf가 음수 → rank_bm25처럼 평균 idf × 0.25로 바꾼다
    index = bm.BM25([["x", "a"], ["x", "b"], ["x", "c"]])
    raw = {
        "x": math.log(0.5) - math.log(3.5),
        "a": math.log(2.5) - math.log(1.5),
    }
    mean = (raw["x"] + 3 * raw["a"]) / 4
    assert index.idf["x"] == pytest.approx(bm.EPSILON * mean)
    assert index.idf["a"] == pytest.approx(raw["a"])

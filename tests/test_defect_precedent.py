"""scripts/defect_precedent 의 순수 함수 테스트 — 네트워크·원본 데이터 없이 작은 예시로 확인한다."""

import hashlib
import json
import math
import shutil
import zipfile

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


def _fake_versions(monkeypatch, tmp_path, texts):
    """판본 key → 텍스트. _download는 tmp 파일 경로를, _pdf_text는 그 텍스트를 돌려준다."""
    paths = {}
    for key in texts:
        path = tmp_path / f"{key}.pdf"
        path.write_bytes(f"pdf-{key}".encode())
        paths[key] = path
    monkeypatch.setattr(rclrpt, "_download", lambda key: paths[key])
    monkeypatch.setattr(rclrpt, "_pdf_text", lambda path: texts[path.stem])
    return {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()}


OLD = "Submission Date : JAN 05, 2024\nDescription of the Cause : old cause\nChronology :"
NEW = "Submission Date : MAR 01, 2024\nDescription of the Cause : new cause\nChronology :"


def test_latest_parsed_picks_latest_and_records_hashes(monkeypatch, tmp_path):
    sha = _fake_versions(monkeypatch, tmp_path, {"a": OLD, "c": NEW})
    key, parsed = rclrpt.latest_parsed(["a", "c"])
    assert key == "c"
    assert parsed["cause_text"] == "new cause"
    assert parsed["resolution"] == "auto"
    assert parsed["pdfs"] == sha


def test_image_version_without_checked_date_is_unresolved(monkeypatch, tmp_path):
    # 이미지 판본의 날짜를 모르면 그것이 최신일 수 있다 — 최신판을 짐작하지 않는다
    _fake_versions(monkeypatch, tmp_path, {"a": OLD, "b": "", "c": NEW})
    _, parsed = rclrpt.latest_parsed(["a", "b", "c"])
    assert parsed["resolution"] == "unresolved"


def test_image_version_with_human_checked_older_date_resolves(monkeypatch, tmp_path):
    sha = _fake_versions(monkeypatch, tmp_path, {"a": OLD, "b": "", "c": NEW})
    manual = {"b": {"submission_date": "20240101", "sha256": sha["b"]}}
    key, parsed = rclrpt.latest_parsed(["a", "b", "c"], manual)
    assert key == "c"
    assert parsed["resolution"] == "manual"


def test_human_checked_date_ignored_when_pdf_changed(monkeypatch, tmp_path):
    _fake_versions(monkeypatch, tmp_path, {"a": OLD, "b": "", "c": NEW})
    manual = {"b": {"submission_date": "20240101", "sha256": "다른 파일"}}
    _, parsed = rclrpt.latest_parsed(["a", "b", "c"], manual)
    assert parsed["resolution"] == "unresolved"


def test_latest_image_version_is_unresolved_even_if_date_known(monkeypatch, tmp_path):
    sha = _fake_versions(monkeypatch, tmp_path, {"a": OLD, "b": ""})
    manual = {"b": {"submission_date": "20250101", "sha256": sha["b"]}}
    key, parsed = rclrpt.latest_parsed(["a", "b"], manual)
    assert key == "b"
    assert parsed["resolution"] == "unresolved"  # 가장 늦은 판본의 원인 칸을 읽을 수 없다


def test_version_without_date_is_unresolved(monkeypatch, tmp_path):
    _fake_versions(monkeypatch, tmp_path, {"a": OLD, "b": "Description of the Cause : x"})
    _, parsed = rclrpt.latest_parsed(["a", "b"])
    assert parsed["resolution"] == "unresolved"


def test_latest_parsed_fails_when_no_dated_version(monkeypatch, tmp_path):
    _fake_versions(monkeypatch, tmp_path, {"a": ""})
    with pytest.raises(rclrpt.ReportError):
        rclrpt.latest_parsed(["a"])


def test_read_flat_stops_on_column_count_mismatch(tmp_path):
    zpath = tmp_path / "x.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("x.txt", "a\tb\tc\r\na\tb\r\n")
    with pytest.raises(SystemExit):
        nhtsa.read_flat(zpath, ["A", "B", "C"])


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


def test_install_dir_restores_old_when_swap_fails(tmp_path):
    target = tmp_path / "nhtsa"
    target.mkdir()
    (target / "old.txt").write_text("old")
    with pytest.raises(OSError):
        nhtsa.install_dir(tmp_path / "missing", target)  # 새 폴더가 없어 교체 실패
    assert (target / "old.txt").read_text() == "old"
    assert not (tmp_path / "nhtsa.old").exists()


def test_install_dir_stops_when_only_old_copy_is_left(tmp_path):
    (tmp_path / "nhtsa.old").mkdir()  # 지난 교체가 중간에 멈춘 상태 — 이것이 마지막 사본
    new = tmp_path / "nhtsa.partial"
    new.mkdir()
    with pytest.raises(SystemExit):
        nhtsa.install_dir(new, tmp_path / "nhtsa")
    assert (tmp_path / "nhtsa.old").exists()


def test_install_dir_keeps_old_snapshot_when_asked(tmp_path):
    target = tmp_path / "nhtsa"
    target.mkdir()
    (target / "old.txt").write_text("old")
    new = tmp_path / "nhtsa.partial"
    new.mkdir()
    keep = tmp_path / "nhtsa.2026-10-06"
    nhtsa.install_dir(new, target, keep_old_as=keep)
    assert (keep / "old.txt").read_text() == "old"


def test_first_sentence_model_name_ending_with_capital_is_boundary():
    # EA05021: "MY 2002 V70S." 를 이니셜로 오인해 문단 전체가 질문이 되던 문제
    text = "THE ALLEGED DEFECT AFFECTS MY 2002 V70S. ACCORDING TO VOLVO THE PART FAILED."
    assert nhtsa.first_sentence(text) == "THE ALLEGED DEFECT AFFECTS MY 2002 V70S."


def _fake_build(tmp_path):
    """가짜 원본 폴더(manifest + 파일 1개)와 build 결과 폴더(build.json + 카드·시험지)를 만든다."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    out.mkdir()
    (raw / "a.zip").write_bytes(b"zip")
    manifest = {"files": {"a.zip": {"sha256": hashlib.sha256(b"zip").hexdigest()}}}
    (raw / "manifest.json").write_text(json.dumps(manifest))
    (out / "recalls.jsonl").write_text("{}\n")
    (out / "eval.jsonl").write_text("{}\n")
    info = {
        "raw_manifest_sha256": nhtsa.sha256_file(raw / "manifest.json"),
        "recalls_sha256": nhtsa.sha256_file(out / "recalls.jsonl"),
        "eval_sha256": nhtsa.sha256_file(out / "eval.jsonl"),
    }
    (out / "build.json").write_text(json.dumps(info))
    return raw, out, info


def test_verify_build_accepts_matching_files(tmp_path):
    raw, out, info = _fake_build(tmp_path)
    assert nhtsa.verify_build(raw, out) == info


def test_verify_build_stops_when_eval_changed(tmp_path):
    # 기준과 다른 시험지로 점수를 내면 "재현"이 아니다 — 중단해야 한다
    raw, out, _ = _fake_build(tmp_path)
    (out / "eval.jsonl").write_text('{"changed": true}\n')
    with pytest.raises(SystemExit):
        nhtsa.verify_build(raw, out)


def test_verify_build_stops_when_raw_changed(tmp_path):
    raw, out, _ = _fake_build(tmp_path)
    (raw / "a.zip").write_bytes(b"other day")
    with pytest.raises(SystemExit):
        nhtsa.verify_build(raw, out)


def test_verify_build_stops_when_recalls_changed(tmp_path):
    raw, out, _ = _fake_build(tmp_path)
    (out / "recalls.jsonl").write_text('{"changed": true}\n')
    with pytest.raises(SystemExit):
        nhtsa.verify_build(raw, out)


def test_verify_build_stops_when_manifest_changed(tmp_path):
    # 원본 파일은 그대로여도 manifest가 다른 날 것이면 build.json과 맞지 않는다
    raw, out, _ = _fake_build(tmp_path)
    manifest = json.loads((raw / "manifest.json").read_text())
    manifest["downloaded_at"] = "2026-10-07T00:00:00+00:00"
    (raw / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        nhtsa.verify_build(raw, out)


def test_maker_alias_maker_and_group():
    from collections import Counter

    from scripts.defect_precedent.maker_aliases import build_table

    counts = Counter(
        {
            "FORD MOTOR COMPANY": 986,
            "Ford Motor Company": 758,
            "GENERAL MOTORS CORP.": 1217,
            "General Motors LLC": 276,
            "Hyundai Motor America": 202,
            "Hyundai Motor Company": 35,
            "Hyundai Translead": 10,
            "CHRYSLER CORPORATION": 654,
            "Chrysler Group LLC": 73,
            "Chrysler (FCA US, LLC)": 271,
            "Kia Motors America": 82,
            "KIA MOTORS AMERICA, INC.": 38,
        }
    )
    rows = {r["raw_maker"]: r for r in build_table(counts)}
    # 대소문자 차이는 표기 통일 (소문자가 섞인 표기가 대표)
    assert rows["FORD MOTOR COMPANY"]["maker"] == "Ford Motor Company"
    assert rows["FORD MOTOR COMPANY"]["maker_basis"] == "표기 통일"
    # 법인 형태(Corp ↔ LLC)가 달라도 maker는 한 이름
    assert rows["GENERAL MOTORS CORP."]["maker"] == rows["General Motors LLC"]["maker"]
    assert rows["GENERAL MOTORS CORP."]["maker_basis"] == "법인 형태 통일"
    # 미국 법인과 본사는 maker는 따로, maker_group은 같다
    america, company = rows["Hyundai Motor America"], rows["Hyundai Motor Company"]
    assert america["maker"] != company["maker"]
    assert america["maker_group"] == company["maker_group"]
    assert america["group_basis"] == "자동"
    # 이름이 비슷해도 다른 회사(트레일러 제조사)는 묶지 않는다
    assert rows["Hyundai Translead"]["maker_group"] != america["maker_group"]
    # 후신 관계는 이름 목록으로 묶고 maker는 신고 당시 이름을 유지한다 (초안 → 확인 필요)
    names = ("CHRYSLER CORPORATION", "Chrysler Group LLC", "Chrysler (FCA US, LLC)")
    assert len({rows[n]["maker_group"] for n in names}) == 1
    assert rows["Chrysler Group LLC"]["maker"] == "Chrysler Group LLC"
    assert rows["Chrysler Group LLC"]["review"] == "확인 필요"
    # 목록에 없는 표기도 같은 maker로 합쳐지면 그 maker의 묶음을 따른다
    assert (
        rows["KIA MOTORS AMERICA, INC."]["maker_group"] == rows["Kia Motors America"]["maker_group"]
    )
    # 모든 줄이 maker_group을 가진다
    assert all(r["maker_group"] for r in rows.values())

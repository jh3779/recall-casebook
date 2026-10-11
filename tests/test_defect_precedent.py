"""scripts/defect_precedent 의 순수 함수 테스트 — 네트워크·원본 데이터 없이 작은 예시로 확인한다."""

import csv
import hashlib
import json
import math
import shutil
import zipfile

import pytest

from scripts.defect_precedent import bm25_baseline as bm
from scripts.defect_precedent import maker_aliases, nhtsa, rclrpt
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


def _identity_aliases(rows):
    """회사명 대응표가 없는 것과 같은 효과의 표 — 이름을 그대로 maker·maker_group으로 쓴다."""
    return {r["MFGNAME"]: {"maker": r["MFGNAME"], "maker_group": r["MFGNAME"]} for r in rows}


ALIAS_FIELDS = [
    "raw_maker",
    "maker",
    "maker_group",
    "count",
    "maker_basis",
    "group_basis",
    "review",
    "review_required",
    "review_note",
]


def _alias_row(raw, maker, group, review="", required="", note=""):
    return {
        "raw_maker": raw,
        "maker": maker,
        "maker_group": group,
        "count": "1",
        "maker_basis": "원문",
        "group_basis": "없음",
        "review": review,
        "review_required": required,
        "review_note": note,
    }


def _write_aliases(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ALIAS_FIELDS)
        w.writeheader()
        w.writerows(rows)


def test_build_cards_applies_the_confirmed_aliases_and_keeps_the_raw_name():
    rows = [
        _rcl("20V001000", "FORD MOTOR COMPANY", "Ford is recalling certain trucks."),
        _rcl("20V002000", "Ford Motor Company", "Ford is recalling certain vans."),
        _rcl("20V003000", "Lincoln", "Lincoln is recalling certain cars."),
    ]
    aliases = {
        "FORD MOTOR COMPANY": {"maker": "Ford Motor Company", "maker_group": "Ford"},
        "Ford Motor Company": {"maker": "Ford Motor Company", "maker_group": "Ford"},
        "Lincoln": {
            "maker": "Lincoln",
            "maker_group": "Ford",
        },  # 같은 모회사의 다른 브랜드를 묶은 경우
    }
    cards = nhtsa.build_cards(rows, "2026-10-06", aliases)
    first, second, third = cards["20V001000"], cards["20V002000"], cards["20V003000"]
    # 신고서 원문은 그대로 보존하고, 정리한 이름과 묶음은 확인한 표에서 온다
    assert (first["raw_maker"], first["maker"], first["maker_group"]) == (
        "FORD MOTOR COMPANY",
        "Ford Motor Company",
        "Ford",
    )
    assert second["raw_maker"] == "Ford Motor Company" and second["maker"] == first["maker"]
    assert third["maker"] == "Lincoln" and third["maker_group"] == "Ford"
    assert list(first)[:3] == ["campno", "maker", "maker_group"]  # 칸 순서가 고정이다


def test_build_cards_stops_on_a_maker_missing_from_the_aliases():
    rows = [
        _rcl("20V001000", "KNOWN", "Known is recalling."),
        _rcl("20V002000", "NEW MAKER", "New is recalling."),
    ]
    with pytest.raises(SystemExit) as e:
        nhtsa.build_cards(rows, "2026-10-06", {"KNOWN": {"maker": "Known", "maker_group": "Known"}})
    assert "대응표에 없는 이름 1개" in str(e.value) and "NEW MAKER" in str(e.value)


def test_load_aliases_reads_only_a_fully_confirmed_table(tmp_path):
    draft = tmp_path / "draft.csv"
    confirmed = tmp_path / "confirmed.csv"
    plain = _alias_row("A CO", "A Co", "A Co")
    pending = _alias_row("B CO", "B Co", "B Group", "확인 필요", "필요", "묶음 확인")
    _write_aliases(draft, [plain, pending])
    # 확인본이 없으면 만들 수 없다
    with pytest.raises(SystemExit) as e:
        nhtsa.load_aliases(confirmed, draft)
    assert "확인본이 필요하다" in str(e.value)
    # 미확인 줄이 남았으면 반영하지 않는다
    _write_aliases(confirmed, [plain, pending])
    with pytest.raises(SystemExit) as e:
        nhtsa.load_aliases(confirmed, draft)
    assert "확인이 끝나지 않은 줄 1개" in str(e.value)
    # 확인을 마치면 원문 이름 → (maker, maker_group)
    _write_aliases(confirmed, [plain, {**pending, "review": "확인 완료"}])
    assert nhtsa.load_aliases(confirmed, draft) == {
        "A CO": {"maker": "A Co", "maker_group": "A Co"},
        "B CO": {"maker": "B Co", "maker_group": "B Group"},
    }
    # 같은 maker가 두 묶음으로 갈리면 중단한다 (unreviewed 검사)
    split = [
        {**plain, "raw_maker": "A CO", "maker_group": "A Co"},
        {**plain, "raw_maker": "A CO.", "maker_group": "Other"},
    ]
    _write_aliases(
        draft, split
    )  # 초안이 이미 갈라져 있으면 이유 없는 수정은 아니고, 같은 maker의 분리만 잡힌다
    _write_aliases(confirmed, split)
    with pytest.raises(SystemExit) as e:
        nhtsa.load_aliases(confirmed, draft)
    assert "같은 maker가 서로 다른 maker_group" in str(e.value)


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
    cards = nhtsa.build_cards(rows, "2026-10-06", _identity_aliases(rows))
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
    rows = [
        _rcl("15V001000", "A", "x", rcdate="20150301"),
        _rcl("15V002000", "A", "y", rcdate="20150301"),
    ]
    cards = nhtsa.build_cards(rows, "2026-10-06", _identity_aliases(rows))
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


def test_verify_build_checks_the_alias_table_hash_when_build_json_records_it(tmp_path, monkeypatch):
    raw, out, info = _fake_build(tmp_path)
    aliases = tmp_path / "maker_aliases.csv"
    aliases.write_text("raw_maker,maker\nA,A\n", encoding="utf-8")
    monkeypatch.setattr(nhtsa, "MAKER_ALIASES", aliases)
    info = {**info, "maker_aliases_sha256": nhtsa.sha256_aliases(aliases)}
    (out / "build.json").write_text(json.dumps(info))
    assert nhtsa.verify_build(raw, out) == info
    # 카드를 만든 뒤 대응표를 고쳤으면 그 카드는 이 표로 만든 것이 아니다
    aliases.write_text("raw_maker,maker\nA,B\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        nhtsa.verify_build(raw, out)
    assert "회사명 대응표" in str(e.value)


def test_verify_build_checks_the_alias_draft_hash_when_build_json_records_it(tmp_path, monkeypatch):
    # 확인본과 초안의 "확인 필요" 표시를 함께 지우면 대조 검사는 통과한다 — 어느 초안과 대조했는지 build.json으로 되짚는다(#45)
    raw, out, info = _fake_build(tmp_path)
    draft = tmp_path / "maker_aliases_draft.csv"
    draft.write_text("raw_maker,maker,review_required\nA,A,필요\n", encoding="utf-8")
    monkeypatch.setattr(nhtsa, "MAKER_ALIASES_DRAFT", draft)
    info = {**info, "maker_aliases_draft_sha256": nhtsa.sha256_aliases(draft)}
    (out / "build.json").write_text(json.dumps(info))
    assert nhtsa.verify_build(raw, out) == info
    draft.write_text(
        "raw_maker,maker,review_required\r\nA,A,필요\r\n", encoding="utf-8"
    )  # 줄바꿈만 다르면 같다
    assert nhtsa.verify_build(raw, out) == info
    draft.write_text(
        "raw_maker,maker,review_required\nA,A,\n", encoding="utf-8"
    )  # 확인 필요 표시를 지움
    with pytest.raises(SystemExit, match="초안"):
        nhtsa.verify_build(raw, out)


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


def test_maker_alias_representative_avoids_period_typo():
    from collections import Counter

    from scripts.defect_precedent.maker_aliases import build_table

    # 신고서 원문에 오타(마침표)가 더 많이 쓰여도 대표 이름은 쉼표 표기를 고르고, 사람이 보게 표시한다
    counts = Counter(
        {
            "Piaggio Group Americas. Inc.": 16,
            "Piaggio Group Americas, Inc.": 4,
            "MACK TRUCKS, INC.": 1,
            "Mack Trucks, Inc.": 122,
        }
    )
    rows = {r["raw_maker"]: r for r in build_table(counts)}
    for raw in ("Piaggio Group Americas. Inc.", "Piaggio Group Americas, Inc."):
        assert rows[raw]["maker"] == "Piaggio Group Americas, Inc."
        assert rows[raw]["review"] == "확인 필요"
        assert "마침표 오타" in rows[raw]["review_note"]
    # 오타가 없는 묶음은 표시하지 않는다
    assert rows["MACK TRUCKS, INC."]["review"] == ""
    # 약어 마침표(MFG. CORP.)는 오타로 보지 않는다
    abbr = {r["raw_maker"]: r for r in build_table(Counter({"UTILITY TRAILER MFG. CO.": 14}))}
    assert abbr["UTILITY TRAILER MFG. CO."]["review"] == ""


def test_maker_alias_dotted_abbreviations_join_the_same_company():
    from collections import Counter

    from scripts.defect_precedent.maker_aliases import build_table, strict_key

    assert strict_key("PORSCHE CARS N.A. INC.") == strict_key("Porsche Cars NA, Inc.")
    assert strict_key("Kawasaki Motors Corp., U.S.A.") == strict_key("KAWASAKI MOTORS CORP USA")
    rows = {
        r["raw_maker"]: r
        for r in build_table(
            Counter({"PORSCHE CARS N.A. INC.": 73, "Porsche Cars North America, Inc.": 135})
        )
    }
    # N.A.가 N·A로 갈라지면 핵심 이름이 달라 묶이지 않았다 — 이제 같은 maker_group이다 (maker는 지역 표기가 달라 따로 둔다)
    assert (
        rows["PORSCHE CARS N.A. INC."]["maker_group"]
        == rows["Porsche Cars North America, Inc."]["maker_group"]
    )


def test_maker_alias_automatic_groups_of_customer_makers_need_a_human_check():
    from collections import Counter

    from scripts.defect_precedent.maker_aliases import build_table

    rows = {
        r["raw_maker"]: r
        for r in build_table(
            Counter(
                {
                    "Hyundai Motor America": 202,
                    "Hyundai Motor Company": 35,
                    "Ford Motor Company": 500,
                    "Ford Motor Co": 5,
                }
            )
        )
    }
    # 현대는 두 단어 이상 자동 묶음이어도 확인 대상이다. 같은 방식으로 묶인 비고객사(Ford)는 아니다
    for name in ("Hyundai Motor America", "Hyundai Motor Company"):
        assert rows[name]["review"] == "확인 필요" and "고객사" in rows[name]["review_note"]
    assert rows["Ford Motor Co"]["review"] == "" and rows["Ford Motor Company"]["review"] == ""


def _row(name, review="", required="", **over):
    row = {
        "raw_maker": name,
        "maker": name,
        "maker_group": name,
        "count": "1",
        "maker_basis": "없음",
        "group_basis": "없음",
        "review": review,
        "review_required": required,
        "review_note": "",
    }
    return {**row, **over}


# 스크립트가 만든 초안: A는 볼 필요 없음, B·C·D는 검토가 필요한 줄
DRAFT = [
    _row("A"),
    _row("B", "확인 필요", "필요"),
    _row("C", "확인 필요", "필요"),
    _row("D", "확인 필요", "필요"),
]


def test_maker_alias_unreviewed_blocks_until_every_row_is_confirmed():
    from scripts.defect_precedent.maker_aliases import unreviewed

    rows = [
        _row("A"),
        _row("B", "확인 완료", "필요"),
        _row("C", "보류", "필요"),
        _row("D", "확인 필요", "필요"),
    ]
    assert [r["raw_maker"] for r in unreviewed(rows, DRAFT)] == ["C", "D"]
    done = [
        _row("A"),
        _row("B", "확인 완료", "필요"),
        _row("C", "확인 완료", "필요"),
        _row("D", "확인 완료", "필요"),
    ]
    assert unreviewed(done, DRAFT) == []  # 모든 검토 대상이 확인 완료면 비어 있다


def test_maker_alias_unreviewed_does_not_let_blank_or_typo_pass_as_confirmed():
    from scripts.defect_precedent.maker_aliases import unreviewed

    # 검토가 필요했던 줄의 review를 지우면 통과하지 못하고 미확인으로 남는다
    blanked = [
        _row("A"),
        _row("B", "", "필요"),
        _row("C", "확인 완료", "필요"),
        _row("D", "확인 완료", "필요"),
    ]
    assert [r["raw_maker"] for r in unreviewed(blanked, DRAFT)] == ["B"]
    # 띄어쓰기 오타 `확인완료`는 확인한 것으로 보지 않고 오류로 멈춘다
    typo = [
        _row("A"),
        _row("B", "확인완료", "필요"),
        _row("C", "확인 완료", "필요"),
        _row("D", "확인 완료", "필요"),
    ]
    with pytest.raises(ValueError, match="알 수 없는 검토 상태"):
        unreviewed(typo, DRAFT)


def test_maker_alias_unreviewed_compares_with_the_draft_so_deleted_rows_and_columns_cannot_pass():
    from scripts.defect_precedent.maker_aliases import unreviewed

    full = [
        _row("A"),
        _row("B", "확인 완료", "필요"),
        _row("C", "확인 완료", "필요"),
        _row("D", "확인 완료", "필요"),
    ]
    # 검토 대상 줄을 통째로 지움 — 남은 줄이 모두 완료여도 통과하지 못한다
    with pytest.raises(ValueError, match="사라진 줄 1개"):
        unreviewed([r for r in full if r["raw_maker"] != "C"], DRAFT)
    # review와 review_required를 함께 지움 — 초안의 review_required와 달라져 멈춘다
    both_cleared = [
        _row("A"),
        _row("B", "확인 완료", "필요"),
        _row("C", "", ""),
        _row("D", "확인 완료", "필요"),
    ]
    with pytest.raises(ValueError, match="review_required가 초안과 다르다"):
        unreviewed(both_cleared, DRAFT)
    # review_required를 엉뚱한 값으로 고침
    with pytest.raises(ValueError, match="review_required가 초안과 다르다"):
        unreviewed([*full[:3], _row("D", "확인 완료", "불필요")], DRAFT)
    # 줄을 새로 넣거나 같은 줄을 복사해 붙임
    with pytest.raises(ValueError, match="늘어난 줄 1개"):
        unreviewed([*full, _row("E")], DRAFT)
    with pytest.raises(ValueError, match="겹치는 줄"):
        unreviewed([*full, _row("B", "확인 완료", "필요")], DRAFT)


def test_maker_alias_unreviewed_checks_company_name_columns_against_the_draft():
    from scripts.defect_precedent.maker_aliases import unreviewed

    ok = [
        _row("A"),
        _row("B", "확인 완료", "필요"),
        _row("C", "확인 완료", "필요"),
        _row("D", "확인 완료", "필요"),
    ]

    def with_row(name, **over):
        return [{**r, **over} if r["raw_maker"] == name else r for r in ok]

    # 칸을 지움 (검토가 필요 없던 줄도)
    with pytest.raises(ValueError, match="빈 줄"):
        unreviewed(with_row("A", maker_group=""), DRAFT)
    with pytest.raises(ValueError, match="빈 줄"):
        unreviewed(with_row("B", maker=" "), DRAFT)
    # 열 하나만 정렬이 어긋남 — maker_group이 다른 줄 것으로 바뀌고 count도 어긋난다
    shifted = [{**r, "maker_group": ok[(i + 1) % 4]["maker_group"]} for i, r in enumerate(ok)]
    with pytest.raises(ValueError, match="초안과 다르다|고친 줄"):
        unreviewed(shifted, DRAFT)
    with pytest.raises(ValueError, match="고치지 않는 칸"):
        unreviewed(with_row("C", count="9"), DRAFT)
    # 검토 대상이 아니던 줄을 기록 없이 고침 / 확인 완료만 하고 이유를 안 적음
    with pytest.raises(ValueError, match="이유를 적어야"):
        unreviewed(with_row("A", maker_group="X"), DRAFT)
    with pytest.raises(ValueError, match="이유를 적어야"):
        unreviewed(with_row("B", maker_group="X"), DRAFT)
    # 고치고 확인 완료 + 이유를 적으면 통과
    fixed = with_row("B", maker_group="X", review_note="같은 계열로 확인")
    assert unreviewed(fixed, DRAFT) == []
    fixed_a = with_row("A", maker_group="X", review="확인 완료", review_note="계열사 연결")
    assert unreviewed(fixed_a, DRAFT) == []


def test_maker_alias_unreviewed_needs_a_real_reason_kept_after_the_draft_note():
    from scripts.defect_precedent.maker_aliases import reason_added, unreviewed

    draft = [
        _row("A"),
        _row("B", "확인 필요", "필요", review_note="maker_group: 이름 목록으로 지정한 초안"),
    ]
    note = draft[1]["review_note"]

    def changed(note_value, **over):
        row = _row("B", "확인 완료", "필요", maker_group="X", review_note=note_value, **over)
        return [_row("A"), row]

    # 초안 메모를 지우거나 빈칸·공백·`;`만 덧붙이면 이유를 적은 것으로 보지 않는다
    for bad in ("", "   ", None, note + "; ", note + " ;; ", "다른 설명만 적고 초안 메모는 지움"):
        with pytest.raises(ValueError, match="이유를 적어야"):
            unreviewed(changed(bad), draft)
    # 초안 메모를 그대로 두고 설명을 덧붙이면 통과한다
    assert unreviewed(changed(note + "; 같은 계열로 확인"), draft) == []
    assert reason_added("초안; 설명", "초안") and not reason_added("초안", "초안")
    # 초안 메모가 없던 줄은 설명만 있으면 된다
    assert reason_added("설명", "") and not reason_added(None, None)


def test_maker_alias_unreviewed_blocks_one_maker_split_into_two_groups():
    from scripts.defect_precedent.maker_aliases import unreviewed

    # 같은 maker(Kia Motors America)로 정리되는 원문 두 줄 중 하나만 다른 묶음으로 바꾸고 이유를 적어도 통과하지 못한다
    draft = [
        _row("KIA MOTORS AMERICA, INC.", maker="Kia Motors America", maker_group="Kia"),
        _row("Kia Motors America", maker="Kia Motors America", maker_group="Kia"),
    ]
    split = [
        draft[0],
        {**draft[1], "maker_group": "Kia Group", "review": "확인 완료", "review_note": "묶음 변경"},
    ]
    with pytest.raises(ValueError, match="같은 maker가 서로 다른 maker_group"):
        unreviewed(split, draft)
    # 두 줄을 함께 바꾸면 통과한다
    both = [
        {**r, "maker_group": "Kia Group", "review": "확인 완료", "review_note": "묶음 변경"}
        for r in draft
    ]
    assert unreviewed(both, draft) == []


def test_maker_alias_committed_draft_is_a_valid_input_for_unreviewed():
    from scripts.defect_precedent.maker_aliases import OUT, read_table, unreviewed

    draft = read_table(OUT)
    pending = unreviewed(draft, draft)  # 초안 그대로면 검토 대상 31줄이 모두 미확인이다
    assert pending and all(r["review_required"] == "필요" for r in pending)
    confirmed = [
        {**r, "review": "확인 완료"} if r["review_required"] == "필요" else r for r in draft
    ]
    assert unreviewed(confirmed, draft) == []  # 검토 대상을 모두 확인 완료로 바꾸면 통과한다


def test_maker_alias_every_pending_row_in_the_draft_is_marked_required():
    from collections import Counter

    from scripts.defect_precedent.maker_aliases import build_table

    rows = build_table(
        Counter(
            {
                "Piaggio Group Americas. Inc.": 16,
                "Piaggio Group Americas, Inc.": 4,
                "PIAGGIO USA, INC.": 15,
            }
        )
    )
    pending = [r for r in rows if r["review"] == "확인 필요"]
    assert pending and all(r["review_required"] == "필요" for r in pending)
    assert all(r["review_required"] == "" for r in rows if r["review"] == "")


def test_maker_alias_draft_csv_is_read_with_bom_aware_encoding():
    import csv

    from scripts.defect_precedent.maker_aliases import OUT

    # 엑셀용 BOM이 붙은 파일이라 utf-8-sig로 읽어야 첫 칸 이름이 맞다
    with OUT.open(encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    assert header[0] == "raw_maker"
    assert {"review", "review_required", "review_note"} <= set(header)
    assert OUT.read_bytes().startswith(b"\xef\xbb\xbf")


def test_the_alias_hash_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.csv", tmp_path / "crlf.csv"
    lf.write_bytes(b"a,b" + bytes([10]) + b"1,2" + bytes([10]))
    crlf.write_bytes(b"a,b" + bytes([13, 10]) + b"1,2" + bytes([13, 10]))
    assert nhtsa.sha256_aliases(lf) == nhtsa.sha256_aliases(crlf)
    assert nhtsa.sha256_file(lf) != nhtsa.sha256_file(crlf)  # 파일 해시는 줄바꿈까지 본다


def test_the_committed_confirmed_aliases_pass_the_review_check():
    # 저장소에 커밋된 확인본이 초안과 대조해 모두 확인 완료인지 (데이터 없이 CI에서도 돈다)
    aliases = nhtsa.load_aliases()
    assert aliases
    assert all(v["maker"] and v["maker_group"] for v in aliases.values())


def test_the_chrysler_rows_use_the_plain_company_name_as_group():
    # 이슈 #36 표시 이름 규칙: Chrysler 계열 8줄의 묶음 이름은 설명 없는 `Chrysler`다 (일반 규칙 전체를 검사하는 테스트는 아니다)
    aliases = nhtsa.load_aliases()
    chrysler = [
        "CHRYSLER CORPORATION",
        "Chrysler (FCA US, LLC)",
        "Chrysler (FCA US LLC)",
        "DAIMLERCHRYSLER CORPORATION",
        "Chrysler Group LLC",
        "CHRYSLER GROUP LLC",
        "CHRYSLER LLC",
        "Chrysler (FCA US, LLC) (Stellantis)",
    ]
    assert {aliases[n]["maker_group"] for n in chrysler} == {"Chrysler"}
    assert not [v for v in aliases.values() if "이어짐" in v["maker_group"]]


def test_build_carry_over_keeps_subfolders_and_files_but_not_build_outputs(tmp_path):
    # 출력 폴더에 시트·벡터 사본 같은 하위 폴더가 생긴 뒤에도 build가 멈추지 않고 옮겨야 한다
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "time_eval_2026-10-10").mkdir(parents=True)
    (old / "time_eval_2026-10-10" / "labels_main.csv").write_text("x", encoding="utf-8")
    (old / "causes.jsonl").write_text("{}\n", encoding="utf-8")
    for name in nhtsa.BUILD_OUTPUTS:
        (old / name).write_text("old", encoding="utf-8")
    new.mkdir()
    nhtsa.carry_over(old, new)
    assert (new / "time_eval_2026-10-10" / "labels_main.csv").read_text(encoding="utf-8") == "x"
    assert (new / "causes.jsonl").exists()
    assert not any((new / name).exists() for name in nhtsa.BUILD_OUTPUTS)


def test_committed_alias_draft_keeps_its_31_review_required_rows():
    """초안의 "확인 필요" 줄을 확인본과 함께 지우면 `unreviewed` 대조를 통과한다 — 커밋된 초안의 줄 수를 고정해 막는다(#45).
    초안을 다시 만들어 줄 수가 달라지면 이 숫자와 기준 파일의 `maker_aliases_draft_sha256`을 함께 고치고 `nhtsa build`를 다시 한다."""
    rows = maker_aliases.read_table(nhtsa.MAKER_ALIASES_DRAFT)
    assert sum(r.get("review_required") == "필요" for r in rows) == 31

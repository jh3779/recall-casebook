"""rclrpt의 긴 실행 대비 동작 테스트 — 네트워크·PDF 없이 가짜로 확인한다."""

import hashlib
import http.client
import json
import urllib.error

import pytest

from scripts.defect_precedent import rclrpt


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


@pytest.fixture
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(rclrpt.time, "sleep", sleeps.append)
    return sleeps


def script_urlopen(monkeypatch, outcomes):
    """urlopen이 outcomes를 차례로 돌려주거나(예외면 던지고) 호출 횟수를 센다."""
    calls = []

    def fake(req, timeout=None):
        calls.append(req)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    monkeypatch.setattr(rclrpt.urllib.request, "urlopen", fake)
    return calls


def test_get_retries_transient_errors_with_growing_gaps(monkeypatch, no_sleep):
    calls = script_urlopen(
        monkeypatch,
        [TimeoutError("slow"), http.client.IncompleteRead(b"x"), http_error(503), b"%PDF"],
    )
    assert rclrpt._get("req") == b"%PDF"
    assert len(calls) == 4
    assert no_sleep == [2.0, 4.0, 8.0]  # 2·4·8초


def test_get_does_not_retry_client_errors(monkeypatch, no_sleep):
    calls = script_urlopen(monkeypatch, [http_error(404), b"never"])
    with pytest.raises(urllib.error.HTTPError):
        rclrpt._get("req")
    assert len(calls) == 1 and no_sleep == []  # 다시 해도 같은 404는 바로 실패


def test_get_retries_429_and_gives_up_after_the_limit(monkeypatch, no_sleep):
    calls = script_urlopen(monkeypatch, [http_error(429)])
    with pytest.raises(urllib.error.HTTPError):
        rclrpt._get("req")
    assert len(calls) == rclrpt.RETRIES + 1


def test_download_turns_exhausted_retries_into_report_error(monkeypatch, tmp_path, no_sleep):
    monkeypatch.setattr(rclrpt, "PDF_DIR", tmp_path)
    script_urlopen(monkeypatch, [ConnectionResetError("reset")])
    with pytest.raises(rclrpt.ReportError):
        rclrpt._download("odi/rcl/2024/RCLRPT-24V001-0001.PDF")
    assert list(tmp_path.glob("*.PDF")) == []  # 끊긴 파일이 완성본 이름으로 남지 않는다


def test_download_skips_files_that_already_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(rclrpt, "PDF_DIR", tmp_path)
    (tmp_path / "RCLRPT-24V001-0001.PDF").write_bytes(b"done")
    calls = script_urlopen(monkeypatch, [b"new"])
    assert rclrpt._download("odi/rcl/2024/RCLRPT-24V001-0001.PDF").read_bytes() == b"done"
    assert calls == []  # 이어받기: 받은 것은 다시 받지 않는다


# ---------------------------------------------------------------------------
# run(): 완성본 / 중간 저장 / 실패 / 중단

CAMPAIGNS = [f"24V{n:03d}" for n in range(1, 6)]


def parsed(campaign):
    return {
        "cause_text": "t",
        "cause_status": "filled",
        "submission_date": "20240101",
        "supplier_names": [],
        "supplier_countries": [],
        "new_form": False,
        "pdfs": {f"odi/rcl/2024/RCLRPT-{campaign}-0001.PDF": "ab" * 32},
        "resolution": "auto",
        "unresolved_reasons": [],
    }


@pytest.fixture
def env(monkeypatch, tmp_path):
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "recalls.jsonl").write_text(
        "".join(
            json.dumps({"campno": f"{c}000", "received_date": "20240101"}) + "\n" for c in CAMPAIGNS
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rclrpt, "OUT_DIR", out_dir)
    monkeypatch.setattr(rclrpt, "PDF_DIR", tmp_path / "pdf")
    monkeypatch.setattr(rclrpt.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(rclrpt, "require_poppler", lambda: "pdftotext version 25.07.0")
    monkeypatch.setattr(
        rclrpt,
        "list_reports",
        lambda years: {c: [f"odi/rcl/2024/RCLRPT-{c}-0001.PDF"] for c in CAMPAIGNS},
    )
    monkeypatch.setattr(rclrpt, "PROGRESS_EVERY", 2)
    monkeypatch.setattr(rclrpt, "CHECKPOINT_EVERY", 2)
    return out_dir


def lines(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_run_all_writes_complete_file_and_no_partial(env, monkeypatch, capsys):
    monkeypatch.setattr(
        rclrpt, "latest_parsed", lambda keys, manual=None: (keys[0], parsed(keys[0].split("-")[1]))
    )
    rclrpt.run("all", expect_campaigns=5)
    assert [r["campaign"] for r in lines(env / "causes.jsonl")] == CAMPAIGNS
    assert not (env / "causes.partial.jsonl").exists()
    assert lines(env / "causes_failures.jsonl") == []
    assert "5/5 (100%)" in capsys.readouterr().out  # 진행률


def test_run_all_with_a_failure_never_creates_the_complete_file(env, monkeypatch, capsys):
    def fake(keys, manual=None):
        campaign = keys[0].split("-")[1]
        if campaign == "24V003":
            raise rclrpt.ReportError("다운로드 실패: 24V003")
        return keys[0], parsed(campaign)

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    with pytest.raises(SystemExit) as e:
        rclrpt.run("all", expect_campaigns=5)
    assert e.value.code == 1
    assert not (env / "causes.jsonl").exists()  # 일부만 담긴 파일이 완성본 이름으로 남지 않는다
    assert len(lines(env / "causes.partial.jsonl")) == 4
    assert [f["campaign"] for f in lines(env / "causes_failures.jsonl")] == ["24V003"]
    assert "실패 1건" in capsys.readouterr().out


def test_rerun_after_failure_completes_and_clears_partial(env, monkeypatch):
    broken = {"on": True}

    def fake(keys, manual=None):
        campaign = keys[0].split("-")[1]
        if campaign == "24V003" and broken["on"]:
            raise rclrpt.ReportError("일시 오류")
        return keys[0], parsed(campaign)

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    with pytest.raises(SystemExit):
        rclrpt.run("all", expect_campaigns=5)
    broken["on"] = False  # 원인이 사라진 뒤 같은 명령을 다시 실행
    rclrpt.run("all", expect_campaigns=5)
    assert len(lines(env / "causes.jsonl")) == 5
    assert not (env / "causes.partial.jsonl").exists()
    assert lines(env / "causes_failures.jsonl") == []


def test_unexpected_error_is_recorded_and_the_run_continues(env, monkeypatch):
    def fake(keys, manual=None):
        campaign = keys[0].split("-")[1]
        if campaign == "24V002":
            raise ValueError("이상한 PDF")
        return keys[0], parsed(campaign)

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    with pytest.raises(SystemExit):
        rclrpt.run("all", expect_campaigns=5)
    failure = lines(env / "causes_failures.jsonl")[0]
    assert failure["campaign"] == "24V002" and "ValueError" in failure["error"]
    assert len(lines(env / "causes.partial.jsonl")) == 4  # 나머지는 계속 읽었다


def test_interrupt_keeps_only_a_partial_file(env, monkeypatch):
    seen = []

    def fake(keys, manual=None):
        campaign = keys[0].split("-")[1]
        if campaign == "24V004":
            raise KeyboardInterrupt
        seen.append(campaign)
        return keys[0], parsed(campaign)

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    with pytest.raises(SystemExit) as e:
        rclrpt.run("all", expect_campaigns=5)
    assert e.value.code == 130
    assert not (env / "causes.jsonl").exists()
    assert [r["campaign"] for r in lines(env / "causes.partial.jsonl")] == seen == CAMPAIGNS[:3]


def test_checkpoint_is_written_while_running(env, monkeypatch):
    snapshots = []

    def fake(keys, manual=None):
        campaign = keys[0].split("-")[1]
        partial = env / "causes.partial.jsonl"
        snapshots.append((campaign, len(lines(partial)) if partial.exists() else None))
        return keys[0], parsed(campaign)

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    rclrpt.run("all", expect_campaigns=5)
    # 2건마다 중간 저장 → 3번째 건을 읽을 때 앞의 2건이 이미 저장돼 있다
    assert dict(snapshots)["24V003"] == 2 and dict(snapshots)["24V005"] == 4


def test_sample_mode_with_out_does_not_touch_the_baseline_sample_file(env, monkeypatch):
    baseline = env / "causes_sample.jsonl"
    baseline.write_text("keep\n", encoding="utf-8")
    monkeypatch.setattr(
        rclrpt, "latest_parsed", lambda keys, manual=None: (keys[0], parsed(keys[0].split("-")[1]))
    )
    rclrpt.run("sample", n=3, out=env / "causes_pilot_3.jsonl")
    assert baseline.read_text(encoding="utf-8") == "keep\n"
    assert len(lines(env / "causes_pilot_3.jsonl")) == 3
    assert (env / "causes_pilot_3_failures.jsonl").exists()


def test_out_in_a_folder_that_does_not_exist_yet_is_created_before_the_long_run(env, monkeypatch):
    monkeypatch.setattr(
        rclrpt, "latest_parsed", lambda keys, manual=None: (keys[0], parsed(keys[0].split("-")[1]))
    )
    target = env / "artifacts" / "pilot.jsonl"
    rclrpt.run("sample", n=3, out=target)
    assert len(lines(target)) == 3


class Completed:
    """subprocess.run의 가짜 결과 — 실제처럼 stdout·stderr는 바이트다 (글자 해독은 코드가 직접 UTF-8로 한다)."""

    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_require_poppler_accepts_poppler_and_rejects_other_pdftotext(monkeypatch):
    poppler = "pdftotext version 25.07.0\nCopyright 2005-2025 The Poppler Developers - http://poppler.freedesktop.org"
    monkeypatch.setattr(
        rclrpt.subprocess, "run", lambda *a, **k: Completed(stderr=poppler.encode())
    )
    assert rclrpt.require_poppler() == "pdftotext version 25.07.0"
    xpdf = "pdftotext version 4.06 [www.xpdfreader.com]\nCopyright 1996-2025 Glyph & Cog, LLC"
    monkeypatch.setattr(rclrpt.subprocess, "run", lambda *a, **k: Completed(stderr=xpdf.encode()))
    with pytest.raises(SystemExit) as e:
        rclrpt.require_poppler()
    assert "poppler가 아니다" in str(e.value) and "4.06" in str(e.value)


def _fail_on(campaign):
    def fake(keys, manual=None):
        name = keys[0].split("-")[1]
        if name == campaign:  # 원본 자체의 결함: 다시 해도 같다
            raise rclrpt.ReportError("PDF가 아닌 응답: Artemis Login Page")
        return keys[0], parsed(name)

    return fake


def test_accepting_persistent_failures_makes_the_complete_file_with_the_failed_list_in_the_manifest(
    env, monkeypatch
):
    monkeypatch.setattr(rclrpt, "latest_parsed", _fail_on("24V003"))
    with pytest.raises(SystemExit):  # 수용하지 않으면 완성본이 없다
        rclrpt.run("all", expect_campaigns=5)
    assert not (env / "causes.jsonl").exists()
    # 실패 목록을 확인한 뒤 건수를 정확히 적어 수용하면 완성본과 명세가 생긴다
    rclrpt.run("all", expect_campaigns=5, accept_failures=1)
    assert [r["campaign"] for r in lines(env / "causes.jsonl")] == [
        c for c in CAMPAIGNS if c != "24V003"
    ]
    assert not (env / "causes.partial.jsonl").exists()
    failures = lines(env / "causes_failures.jsonl")
    assert [f["campaign"] for f in failures] == ["24V003"]
    manifest = json.loads((env / "causes.manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["rows"] == 4
        and manifest["failures"] == 1
        and manifest["failed_campaigns"] == ["24V003"]
    )
    assert (
        manifest["rows"] + manifest["failures"] == manifest["expect_campaigns"] == 5
    )  # 빠진 캠페인이 없다
    assert (
        manifest["failures_sha256"]
        == hashlib.sha256((env / "causes_failures.jsonl").read_bytes()).hexdigest()
    )
    assert manifest["campaigns_sha256"] == rclrpt.campaigns_digest(
        c for c in CAMPAIGNS if c != "24V003"
    )


def test_accept_failures_must_equal_the_actual_failure_count(env, monkeypatch, capsys):
    monkeypatch.setattr(rclrpt, "latest_parsed", _fail_on("24V003"))
    with pytest.raises(
        SystemExit
    ) as e:  # 실패는 1건인데 2건이라고 적음 — 목록을 안 보고 숫자만 키운 경우
        rclrpt.run("all", expect_campaigns=5, accept_failures=2)
    assert e.value.code == 1
    assert not (env / "causes.jsonl").exists() and not (env / "causes.manifest.json").exists()
    out = capsys.readouterr().out
    assert "--accept-failures 1로 다시 실행한다" in out and "실제 실패 1건과 다르다" in out


def test_no_failures_manifest_records_zero_failures(env, monkeypatch):
    monkeypatch.setattr(
        rclrpt, "latest_parsed", lambda keys, manual=None: (keys[0], parsed(keys[0].split("-")[1]))
    )
    rclrpt.run("all", expect_campaigns=5)
    manifest = json.loads((env / "causes.manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["failures"] == 0
        and manifest["failed_campaigns"] == []
        and manifest["failures_sha256"] is None
    )


def test_run_stops_before_reading_anything_when_pdftotext_is_not_poppler(env, monkeypatch):
    monkeypatch.undo()  # require_poppler를 가짜로 바꾼 설정을 되돌려 실제 검사를 쓴다
    monkeypatch.setattr(rclrpt.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(
        rclrpt.subprocess,
        "run",
        lambda *a, **k: Completed(stderr=b"pdftotext version 4.06 [www.xpdfreader.com]"),
    )
    with pytest.raises(SystemExit) as e:
        rclrpt.run("all", expect_campaigns=5)
    assert "poppler가 아니다" in str(e.value)


def test_pdf_text_decodes_utf8_itself_regardless_of_the_computer_encoding(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return Completed(stdout="결함 원인: 실링 재질".encode())

    monkeypatch.setattr(rclrpt.subprocess, "run", fake_run)
    assert rclrpt._pdf_text(tmp_path / "x.PDF") == "결함 원인: 실링 재질"
    cmd, kwargs = calls[0]
    assert cmd[:3] == ["pdftotext", "-enc", "UTF-8"]  # poppler 출력 인코딩을 UTF-8로 고정
    assert (
        "text" not in kwargs and "encoding" not in kwargs
    )  # 컴퓨터 기본 인코딩(cp949 등)으로 읽지 않는다


def test_pdf_text_turns_invalid_utf8_into_a_report_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rclrpt.subprocess, "run", lambda *a, **k: Completed(stdout=b"ok \xa7 broken")
    )
    with pytest.raises(rclrpt.ReportError, match="UTF-8로 읽지 못함"):
        rclrpt._pdf_text(tmp_path / "x.PDF")


def test_pdf_text_failure_quarantines_the_file_so_the_next_run_downloads_it_again(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(rclrpt, "PDF_DIR", tmp_path)
    monkeypatch.setattr(rclrpt.time, "sleep", lambda s: None)
    bad = tmp_path / "RCLRPT-24V001-0001.PDF"
    bad.write_bytes(b"%PDF-1.4 truncated")
    monkeypatch.setattr(rclrpt.subprocess, "run", lambda *a, **k: Completed(returncode=1))
    with pytest.raises(rclrpt.ReportError):
        rclrpt._pdf_text(bad)
    assert not bad.exists() and (tmp_path / "RCLRPT-24V001-0001.PDF.bad").exists()
    # 다음 실행: 파일이 없으므로 _download가 다시 받는다
    calls = script_urlopen(monkeypatch, [b"%PDF-1.4 good"])
    assert rclrpt._download("odi/rcl/2024/RCLRPT-24V001-0001.PDF").read_bytes() == b"%PDF-1.4 good"
    assert len(calls) == 1


def test_download_rejects_a_non_pdf_response_instead_of_saving_it(monkeypatch, tmp_path, no_sleep):
    monkeypatch.setattr(rclrpt, "PDF_DIR", tmp_path)
    script_urlopen(
        monkeypatch, [b"<html>Service Unavailable</html>"]
    )  # HTTP 200으로 오류 문서가 오는 경우
    with pytest.raises(rclrpt.ReportError, match="PDF가 아닌 응답"):
        rclrpt._download("odi/rcl/2024/RCLRPT-24V001-0001.PDF")
    assert list(tmp_path.iterdir()) == []  # PDF 이름으로도 .part로도 남지 않는다


# ---------------------------------------------------------------------------
# all 모드: 기대 캠페인 수


def test_all_requires_expected_campaign_count_before_touching_the_network(env, monkeypatch):
    monkeypatch.setattr(
        rclrpt, "list_reports", lambda years: pytest.fail("목록을 조회하면 안 된다")
    )
    with pytest.raises(SystemExit) as e:
        rclrpt.run("all")
    assert "--expect-campaigns" in str(e.value)


def test_all_stops_before_any_pdf_when_the_list_is_shorter_than_expected(env, monkeypatch):
    monkeypatch.setattr(
        rclrpt, "latest_parsed", lambda *a, **k: pytest.fail("PDF를 처리하면 안 된다")
    )
    with pytest.raises(
        SystemExit
    ) as e:  # 서버가 일부 연도만 돌려준 경우 (5개 중 5개가 기대인데 목록이 줄어듦)
        rclrpt.run("all", expect_campaigns=6)
    assert "5개 캠페인이다" in str(e.value) and "기대 6개" in str(e.value)
    assert not (env / "causes.jsonl").exists() and not (env / "causes.partial.jsonl").exists()


def test_all_stops_when_the_server_returns_an_empty_list(env, monkeypatch):
    monkeypatch.setattr(rclrpt, "list_reports", lambda years: {})
    with pytest.raises(SystemExit) as e:
        rclrpt.run("all", expect_campaigns=0)
    assert "목록이 비어 있다" in str(e.value)


def test_failed_rerun_says_the_old_complete_file_is_not_this_runs_result(env, monkeypatch, capsys):
    (env / "causes.jsonl").write_text(
        '{"campaign": "old"}\n', encoding="utf-8"
    )  # 이전 실행의 완성본

    def fake(keys, manual=None):
        raise rclrpt.ReportError("일시 오류")

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    with pytest.raises(SystemExit):
        rclrpt.run("all", expect_campaigns=5)
    assert (env / "causes.jsonl").read_text(
        encoding="utf-8"
    ) == '{"campaign": "old"}\n'  # 지우지는 않는다
    assert "이전 실행의 causes.jsonl이 그대로 남아 있다" in capsys.readouterr().out


def test_campaigns_digest_is_order_independent_and_pinned():
    # load_db.campaigns_digest와 같은 값이어야 한다 (두 모듈의 골든 값이 같다)
    assert rclrpt.campaigns_digest(["24V002", "24V001"]) == rclrpt.campaigns_digest(
        ["24V001", "24V002"]
    )
    assert rclrpt.campaigns_digest(["24V001", "24V002"]) == (
        "7d8d70be5ca2cbddacab9b80813f827e412aca999b939a204b31b10ada753aff"
    )
    assert rclrpt.campaigns_digest(["24V001"]) != rclrpt.campaigns_digest(["24V001", "24V002"])


def test_all_success_writes_a_manifest_that_matches_the_complete_file(env, monkeypatch):
    monkeypatch.setattr(
        rclrpt, "latest_parsed", lambda keys, manual=None: (keys[0], parsed(keys[0].split("-")[1]))
    )
    rclrpt.run("all", expect_campaigns=5)
    manifest = json.loads((env / "causes.manifest.json").read_text(encoding="utf-8"))
    complete = env / "causes.jsonl"
    assert manifest["kind"] == "full" and manifest["rows"] == 5 == len(lines(complete))
    assert manifest["file_sha256"] == hashlib.sha256(complete.read_bytes()).hexdigest()
    assert manifest["campaigns_sha256"] == rclrpt.campaigns_digest(CAMPAIGNS)
    assert manifest["expect_campaigns"] == 5 and manifest["listing_campaigns"] == 5
    assert manifest["pdftotext"] == "pdftotext version 25.07.0" and manifest["generated_at"]


def test_failed_run_never_writes_or_touches_a_manifest(env, monkeypatch):
    def fake(keys, manual=None):
        raise rclrpt.ReportError("일시 오류")

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    with pytest.raises(SystemExit):
        rclrpt.run("all", expect_campaigns=5)
    assert not (env / "causes.manifest.json").exists()  # 명세는 완성본과 함께만 생긴다


def test_all_success_prints_the_row_count_to_use_for_loading(env, monkeypatch, capsys):
    monkeypatch.setattr(
        rclrpt, "latest_parsed", lambda keys, manual=None: (keys[0], parsed(keys[0].split("-")[1]))
    )
    rclrpt.run("all", expect_campaigns=5)
    assert "causes.manifest.json" in capsys.readouterr().out


def test_write_jsonl_always_uses_lf_so_file_hashes_match_across_platforms(tmp_path):
    from scripts.defect_precedent import nhtsa

    path = tmp_path / "out.jsonl"
    nhtsa.write_jsonl(path, [{"a": "가"}, {"a": "b"}])
    data = path.read_bytes()
    assert data == '{"a": "가"}\n{"a": "b"}\n'.encode()
    # Windows에서 CRLF가 되면 recalls_sha256·causes_sha256이 Mac·Linux에서 만든 값과 달라진다
    assert b"\r" not in data

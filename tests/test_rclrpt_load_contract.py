"""`rclrpt all`이 만드는 완성본·명세를 `load_db`의 전체(full) 검증이 받아들이는지 — 두 스크립트 사이의 계약 테스트.

PR #32(수집)와 #30(적재)가 따로 만들어졌으므로, 한쪽만 바뀌어 명세 형식이 어긋나면 여기서 잡는다.
"""

import json

import pytest
import test_load_db as L
import test_rclrpt_run as T

from scripts.defect_precedent import load_db, rclrpt


def _run_all_with_one_accepted_failure(monkeypatch, tmp_path):
    env = tmp_path / "processed"
    env.mkdir()
    campaigns = T.CAMPAIGNS
    (env / "recalls.jsonl").write_text(
        "".join(
            json.dumps({"campno": f"{c}000", "received_date": "20240101"}) + "\n" for c in campaigns
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rclrpt, "OUT_DIR", env)
    monkeypatch.setattr(rclrpt, "PDF_DIR", tmp_path / "pdf")
    monkeypatch.setattr(rclrpt, "require_poppler", lambda: "pdftotext version 25.07.0")
    monkeypatch.setattr(rclrpt.shutil, "which", lambda name: "/x/pdftotext")
    monkeypatch.setattr(
        rclrpt,
        "list_reports",
        lambda years: {c: [f"odi/rcl/2024/RCLRPT-{c}-0001.PDF"] for c in campaigns},
    )
    bad = "odi/rcl/2024/RCLRPT-24V003-0001.PDF"
    sha = {bad.split("/")[-1]: "aa" * 32}

    def fake(keys, manual=None):
        name = keys[0].split("-")[1]
        if name == "24V003":
            raise rclrpt.ReportError(f"PDF가 아닌 응답: {bad} (4,628바이트)", [bad], sha)
        return keys[0], T.parsed(name)

    monkeypatch.setattr(rclrpt, "latest_parsed", fake)
    token = rclrpt.failure_token(
        {
            "campaign": "24V003",
            "keys": [bad],
            "source_files": [bad],
            "source_sha256": sha,
            "error": "PDF가 아닌 응답: x",
        }
    )
    rclrpt.run("all", expect_campaigns=5, accept_failures=[token])
    return env


def test_the_manifest_rclrpt_writes_is_accepted_by_load_db_full(monkeypatch, tmp_path):
    env = _run_all_with_one_accepted_failure(monkeypatch, tmp_path)
    # load_db가 읽는 폴더: rclrpt가 만든 완성본·명세 + 카드·시험지·build.json
    recalls = [L.recall(f"{c}000", snapshot_date="2026-10-06") for c in T.CAMPAIGNS]
    recalls.append(L.recall("23V002000", snapshot_date="2026-10-06"))  # 시험지의 정답 리콜
    d = L.make_data_dir(tmp_path / "ld", recalls=recalls)
    (d / "causes.jsonl").write_bytes((env / "causes.jsonl").read_bytes())
    (d / "causes.manifest.json").write_bytes((env / "causes.manifest.json").read_bytes())
    build = load_db.load_files(d, "full", L.make_baseline(tmp_path))["build"]
    assert build["causes_rows"] == 4  # 5개 캠페인 중 수용한 실패 1개를 뺀 성공분
    assert build["causes_spec"]["failed_campaigns"] == ["24V003"]
    # 명세는 줄 수 + 실패 = 기대 캠페인 수, 성공 ∪ 실패 = 기대 목록을 모두 만족한다
    spec = build["causes_spec"]
    assert spec["rows"] + spec["failures"] == spec["expect_campaigns"] == 5


def test_load_db_stops_when_the_rclrpt_manifest_is_missing_the_expected_list(monkeypatch, tmp_path):
    env = _run_all_with_one_accepted_failure(monkeypatch, tmp_path)
    manifest = json.loads((env / "causes.manifest.json").read_text(encoding="utf-8"))
    del manifest["expected_campaigns_sha256"]
    recalls = [L.recall(f"{c}000", snapshot_date="2026-10-06") for c in T.CAMPAIGNS]
    recalls.append(L.recall("23V002000", snapshot_date="2026-10-06"))
    d = L.make_data_dir(tmp_path / "ld", recalls=recalls)
    (d / "causes.jsonl").write_bytes((env / "causes.jsonl").read_bytes())
    (d / "causes.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", L.make_baseline(tmp_path))
    assert "expected_campaigns_sha256" in str(e.value)

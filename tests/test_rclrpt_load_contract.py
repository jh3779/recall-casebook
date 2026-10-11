"""`rclrpt all`이 만드는 완성본·명세를 `load_db`의 전체(full) 검증이 받아들이는지 — 두 스크립트 사이의 계약 테스트.

PR #32(수집)와 #30(적재)가 따로 만들어졌으므로, 한쪽만 바뀌어 명세 형식이 어긋나면 여기서 잡는다.
"""

import json

import pytest
import test_load_db as L
import test_rclrpt_run as T

from scripts.defect_precedent import load_db, rclrpt


def _load_dir(tmp_path):
    """load_db가 읽는 폴더(카드·시험지·build.json). rclrpt도 이 카드 파일로 수집 대상을 정한다 — 같은 카드 스냅샷."""
    recalls = [L.recall(f"{c}000", snapshot_date="2026-10-06") for c in T.CAMPAIGNS]
    recalls.append(L.recall("23V002000", snapshot_date="2026-10-06"))  # 시험지의 정답 리콜
    return L.make_data_dir(tmp_path / "ld", recalls=recalls)


def _run_all_with_one_accepted_failure(monkeypatch, tmp_path, d):
    env = tmp_path / "processed"
    env.mkdir()
    campaigns = T.CAMPAIGNS
    (env / "recalls.jsonl").write_bytes((d / "recalls.jsonl").read_bytes())
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
    d = _load_dir(tmp_path)
    env = _run_all_with_one_accepted_failure(monkeypatch, tmp_path, d)
    # load_db가 읽는 폴더: rclrpt가 만든 완성본·명세 + 카드·시험지·build.json
    (d / "causes.jsonl").write_bytes((env / "causes.jsonl").read_bytes())
    (d / "causes.manifest.json").write_bytes((env / "causes.manifest.json").read_bytes())
    build = load_db.load_files(d, "full", L.make_baseline(tmp_path))["build"]
    assert build["causes_rows"] == 4  # 5개 캠페인 중 수용한 실패 1개를 뺀 성공분
    assert build["causes_spec"]["failed_campaigns"] == ["24V003"]
    # 명세는 줄 수 + 실패 = 기대 캠페인 수, 성공 ∪ 실패 = 기대 목록을 모두 만족한다
    spec = build["causes_spec"]
    assert spec["rows"] + spec["failures"] == spec["expect_campaigns"] == 5
    # 명세에는 수집 대상을 정한 카드 파일의 지문이 남고, 적재할 build의 카드와 같아야 통과한다
    assert spec["recalls_sha256"] == L.sha(d / "recalls.jsonl")


def test_load_db_stops_when_causes_were_collected_from_another_card_snapshot(monkeypatch, tmp_path):
    d = _load_dir(tmp_path)
    env = _run_all_with_one_accepted_failure(monkeypatch, tmp_path, d)
    other = L.make_data_dir(
        tmp_path / "other", recalls=[L.recall("24V001000", snapshot_date="2026-10-06")]
    )
    (other / "causes.jsonl").write_bytes((env / "causes.jsonl").read_bytes())
    (other / "causes.manifest.json").write_bytes((env / "causes.manifest.json").read_bytes())
    with pytest.raises(SystemExit) as e:
        load_db.load_files(other, "full", L.make_baseline(tmp_path))
    assert "recalls_sha256이 build.json과 다르다" in str(e.value)


def test_load_db_stops_when_the_rclrpt_manifest_is_missing_the_expected_list(monkeypatch, tmp_path):
    d = _load_dir(tmp_path)
    env = _run_all_with_one_accepted_failure(monkeypatch, tmp_path, d)
    manifest = json.loads((env / "causes.manifest.json").read_text(encoding="utf-8"))
    del manifest["expected_campaigns_sha256"]
    (d / "causes.jsonl").write_bytes((env / "causes.jsonl").read_bytes())
    (d / "causes.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_db.load_files(d, "full", L.make_baseline(tmp_path))
    assert "expected_campaigns_sha256" in str(e.value)

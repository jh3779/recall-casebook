"""쇼룸 데모 생성기가 build.json 판본과 다른 입력을 거부하는지 (데이터 없이 도는 시험)."""

import hashlib
import json

import pytest

from scripts.build_showroom_demo import FLAT, verify_inputs


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def inputs(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / FLAT).write_bytes(b"flat")
    manifest = json.dumps({"files": {FLAT: {"sha256": _sha(b"flat")}}}).encode()
    (raw / "manifest.json").write_bytes(manifest)
    cards = tmp_path / "recalls.jsonl"
    cards.write_bytes(b'{"campno": "X"}\n')
    build = tmp_path / "build.json"
    build.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-10-06",
                "raw_manifest_sha256": _sha(manifest),
                "recalls_sha256": _sha(b'{"campno": "X"}\n'),
            }
        )
    )
    return raw, cards, build


def test_matching_inputs_return_version(inputs):
    raw, cards, build = inputs
    version = verify_inputs(raw, cards, build)
    assert version["snapshot_date"] == "2026-10-06"
    assert version["flat_sha256"] == _sha(b"flat")


@pytest.mark.parametrize("target", ["flat", "cards", "manifest"])
def test_mismatched_input_is_rejected(inputs, target):
    raw, cards, build = inputs
    path = {"flat": raw / FLAT, "cards": cards, "manifest": raw / "manifest.json"}[target]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SystemExit, match="build.json 판본과 다르다"):
        verify_inputs(raw, cards, build)

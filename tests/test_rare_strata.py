"""scripts/defect_precedent/rare_strata.py의 순수 함수 시험 — 데이터·임베딩 없이 도는 부분만."""

import collections
import json

import pytest

from scripts.defect_precedent.rare_strata import (
    BOUNDS,
    EXPECTED_ALL,
    EXPECTED_MODEL_FINGERPRINT,
    build_result_record,
    check_inputs,
    compare_expected,
    ensure_reproduced,
    model_record,
    rarity,
    stratum_of,
    wilson,
)


def test_wilson은_알려진_값과_맞다():
    lo, hi = wilson(12, 24)  # 문서 표의 가장 드문 24문항 (0.31–0.69)
    assert (round(lo, 2), round(hi, 2)) == (0.31, 0.69)
    lo, hi = wilson(92, 150)
    assert (round(lo, 2), round(hi, 2)) == (0.53, 0.69)


def test_wilson은_0과_전부에서도_구간이_범위_안이다():
    for k in (0, 5):
        lo, hi = wilson(k, 5)
        assert 0 <= lo <= hi <= 1


def test_wilson은_표본이_없으면_거부한다():
    with pytest.raises(ValueError):
        wilson(0, 0)


def test_구간_경계는_포함_규칙이_고정돼_있다():
    lo, hi = BOUNDS
    assert stratum_of(lo).startswith("드묾")
    assert stratum_of(lo + 1).startswith("중간")
    assert stratum_of(hi).startswith("중간")
    assert stratum_of(hi + 1).startswith("흔함")


def test_희소성은_정답_중_가장_작은_라벨_카드_수다():
    cards = {
        "A": {"components": ["X", "Y"]},
        "B": {"components": ["Z"]},
    }
    count = collections.Counter({"X": 100, "Y": 7, "Z": 30})
    # 한 카드에 라벨이 여럿이면 최솟값(Y=7), 정답이 여럿이면 그 중 최솟값
    assert rarity({"gold_campnos": ["A"]}, cards, count) == 7
    assert rarity({"gold_campnos": ["A", "B"]}, cards, count) == 7
    assert rarity({"gold_campnos": ["B", "없는번호"]}, cards, count) == 30


def test_희소성은_라벨이_있는_정답이_없으면_거부한다():
    cards = {"A": {"components": []}}
    with pytest.raises(ValueError):
        rarity(
            {"action_no": "EA1", "gold_campnos": ["A", "없는번호"]}, cards, collections.Counter()
        )


def _fake_inputs(tmp_path, recalls=b"r\n", eval_=b"e\n", raw="r" * 64):
    from scripts.defect_precedent.nhtsa import sha256_file

    out = tmp_path / "out"
    out.mkdir()
    (out / "recalls.jsonl").write_bytes(recalls)
    (out / "eval.jsonl").write_bytes(eval_)
    (out / "build.json").write_text(json.dumps({"raw_manifest_sha256": raw}), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "build": {
                    "raw_manifest_sha256": "r" * 64,
                    "recalls_sha256": sha256_file(out / "recalls.jsonl"),
                    "eval_sha256": sha256_file(out / "eval.jsonl"),
                }
            }
        ),
        encoding="utf-8",
    )
    return out, baseline


def test_입력_지문이_기준_파일과_같으면_통과한다(tmp_path):
    out, baseline = _fake_inputs(tmp_path)
    got = check_inputs(out, baseline)
    assert set(got) == {"raw_manifest_sha256", "recalls_sha256", "eval_sha256"}


@pytest.mark.parametrize(
    "kwargs, field",
    [
        ({"recalls": b"changed\n"}, "recalls_sha256"),
        ({"eval_": b"changed\n"}, "eval_sha256"),
        ({"raw": "x" * 64}, "raw_manifest_sha256"),
    ],
)
def test_입력_지문이_다르면_재현이_아니라_재평가로_멈춘다(tmp_path, kwargs, field):
    out, baseline = _fake_inputs(tmp_path)
    # 기준 파일은 원래 입력으로 만들고, 현재 입력만 바꾼다
    if "recalls" in kwargs:
        (out / "recalls.jsonl").write_bytes(kwargs["recalls"])
    if "eval_" in kwargs:
        (out / "eval.jsonl").write_bytes(kwargs["eval_"])
    if "raw" in kwargs:
        (out / "build.json").write_text(
            json.dumps({"raw_manifest_sha256": kwargs["raw"]}), encoding="utf-8"
        )
    with pytest.raises(SystemExit) as stop:
        check_inputs(out, baseline)
    assert "재평가" in str(stop.value)
    assert field in str(stop.value)  # 어느 지문이 다른지 메시지에 나온다


def _overall(**override):
    rates = {**EXPECTED_ALL, **override}
    return {k: {"rate": v} for k, v in rates.items()}


def test_기준과_점수_모델_지문이_모두_같으면_전부_참이다():
    matches = compare_expected(_overall(), EXPECTED_MODEL_FINGERPRINT)
    assert set(matches) == {*EXPECTED_ALL, "모델 지문"}
    assert all(matches.values())


def test_모델_지문이_다르면_모델_지문만_거짓이다():
    matches = compare_expected(_overall(), "0" * 16)
    assert matches.pop("모델 지문") is False
    assert all(matches.values())


def test_전체_점수가_기준과_다르면_그_항목만_거짓이다():
    matches = compare_expected(_overall(**{"RRF·원래": 0.543}), EXPECTED_MODEL_FINGERPRINT)
    assert matches["RRF·원래"] is False
    assert matches["BM25·원래"] is True
    assert matches["모델 지문"] is True


def test_결과_파일의_모델_추적_정보가_빠지지_않는다():
    info = {
        "fastembed": "0.9.0",
        "model_fingerprint": "abc",
        "cache": "x.npy",
        "cache_verified": True,
    }
    record = model_record(info, "f" * 64)
    assert record["model_fingerprint"] == "abc"
    assert record["expected_model_fingerprint"] == EXPECTED_MODEL_FINGERPRINT
    assert record["cache_verified"] is True
    assert record["cache_sha256"] == "f" * 64
    assert {"name", "fastembed", "cache"} <= set(record)


def test_기준과_다르면_비정상_종료한다():
    ensure_reproduced({"BM25·원래": True, "모델 지문": True})  # 전부 같으면 아무 일 없다
    with pytest.raises(SystemExit) as stop:
        ensure_reproduced({"BM25·원래": True, "모델 지문": False})
    assert stop.value.code == 1


def test_대조한_항목이_하나도_없으면_재현이_아니라_비정상_종료한다():
    """빈 입력은 `all({}.values())`가 참이라 통과하던 틈(이슈 #180) — 아무것도 대조하지 않았으면 재현했다고 하지 않는다."""
    with pytest.raises(SystemExit) as stop:
        ensure_reproduced({})
    assert stop.value.code == 1


def test_결과_레코드에_추적_정보가_모두_들어간다():
    model = model_record(
        {
            "fastembed": "0.9.0",
            "model_fingerprint": "abc",
            "cache": "x.npy",
            "cache_verified": True,
        },
        "f" * 64,
    )
    matches = {"모델 지문": False}
    record = build_result_record(
        fingerprints={"raw_manifest_sha256": "a", "recalls_sha256": "b", "eval_sha256": "c"},
        build_info={"recalls_sha256": "b", "snapshot_date": "2026-10-06", "ignored": 1},
        snapshot_date="2026-10-06",
        model=model,
        rarest_detail=[{"action_no": "PE1"}],
        matches=matches,
        strata={"전체": {"n": 749}},
    )
    assert record["inputs"]["eval_sha256"] == "c"
    assert record["build_json"] == {"recalls_sha256": "b", "snapshot_date": "2026-10-06"}
    assert record["model"]["expected_model_fingerprint"] == EXPECTED_MODEL_FINGERPRINT
    assert record["model"]["cache_sha256"] == "f" * 64
    assert record["matches_expected"] == matches
    assert record["rarest_label_cards_le10"]["n"] == 1
    assert record["bounds"] == BOUNDS
    assert record["strata"]["전체"]["n"] == 749

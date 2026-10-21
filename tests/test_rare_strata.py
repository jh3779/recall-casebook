"""scripts/defect_precedent/rare_strata.py의 순수 함수 시험 — 데이터·임베딩 없이 도는 부분만."""

import collections
import json

import pytest

from scripts.defect_precedent.rare_strata import BOUNDS, check_inputs, rarity, stratum_of, wilson


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

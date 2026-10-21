"""scripts/defect_precedent/rare_strata.py의 순수 함수 시험 — 데이터·임베딩 없이 도는 부분만."""

import collections

import pytest

from scripts.defect_precedent.rare_strata import BOUNDS, rarity, stratum_of, wilson


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

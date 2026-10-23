"""scripts/defect_precedent/significance.py 시험 — 정답은 손계산(아래 주석)과 `math.comb`·`itertools`로 따로 구한 값이다.

함수 안의 수식을 그대로 베끼지 않았다. 각 기대값에 계산 과정을 적었다(PR #133 원본 시험의 몇 줄만 같은 값이다).
"""

import itertools
import math

import numpy as np
import pytest

from scripts.defect_precedent.significance import exact_mcnemar, holm_adjust, paired_permutation_p

# ---------- exact McNemar ----------


def test_mcnemar_불일치쌍이_없으면_1이다():
    assert exact_mcnemar(0, 0) == 1.0


def test_mcnemar_b7_c1은_손계산_18_256이다():
    # n=8. 작은 쪽 1 이하 = C(8,0)+C(8,1) = 1+8 = 9 → 한쪽 꼬리 9/2^8 = 9/256, 양측 18/256 = 0.0703125
    assert exact_mcnemar(7, 1) == pytest.approx(18 / 256)
    assert exact_mcnemar(7, 1) == pytest.approx(0.0703125)


def test_mcnemar_한쪽만_이기면_2_나누기_2의_n제곱이다():
    # (3,0): 꼬리 1/2^3 → 양측 1/4. (10,0): 꼬리 1/2^10 → 양측 2/1024 = 0.001953125
    assert exact_mcnemar(3, 0) == 0.25
    assert exact_mcnemar(10, 0) == pytest.approx(2 / 1024)


def test_mcnemar_양쪽이_같으면_1로_잘린다():
    # (5,5): n=10, Σ_{i<=5} C(10,i) = 1+10+45+120+210+252 = 638 → 638/1024 ≈ 0.623, 두 배는 1.246 → 1.0
    assert exact_mcnemar(5, 5) == 1.0
    # (1,1): n=2, 꼬리 (1+2)/4 = 0.75 → 1.5 → 1.0
    assert exact_mcnemar(1, 1) == 1.0


def test_mcnemar_a와_b를_바꿔도_같다():
    assert exact_mcnemar(7, 1) == exact_mcnemar(1, 7)


def test_mcnemar_작은_쪽_합을_comb으로_직접_센_값과_같다():
    # (12,4): n=16, Σ_{i<=4} C(16,i) = 1+16+120+560+1820 = 2517 → 2*2517/65536
    assert sum(math.comb(16, i) for i in range(5)) == 2517
    assert exact_mcnemar(12, 4) == pytest.approx(2 * 2517 / 65536)
    assert exact_mcnemar(12, 4) == pytest.approx(0.0768, abs=5e-5)  # 5034/65536


# ---------- paired permutation ----------


def test_permutation_차이가_전부_0이거나_비면_1이다():
    assert paired_permutation_p([0.0, 0.0, 0.0], seed=7) == 1.0
    assert paired_permutation_p([], seed=7) == 1.0


def test_permutation_부호가_상쇄되는_관측은_1이다():
    # [1,-1]: 관측 평균 0. 부호 조합 4개 평균은 모두 |평균|>=0 → 4/4
    assert paired_permutation_p([1.0, -1.0], seed=0) == 1.0


def test_permutation_같은_부호_n개는_2_나누기_2의_n제곱이다():
    # [1]*3: 평균 1이 되는 것은 전부 + 또는 전부 − 두 조합뿐 → 2/8
    assert paired_permutation_p([1.0] * 3, seed=0) == 0.25
    # [1]*5 → 2/32
    assert paired_permutation_p([1.0] * 5, seed=0) == 0.0625


def test_permutation_손으로_센_부호_조합():
    # [1,2,3]: 합 s1+2s2+3s3 8가지 = 6, 0, 2, -4, 4, -2, 0, -6. 관측 |합|=6 이상은 6과 -6 → 2/8
    assert paired_permutation_p([1.0, 2.0, 3.0], seed=0) == 0.25
    # [2,2,1,1,-1]: 부호를 뒤집어도 분포가 같으니 크기 {2,2,1,1,1}로 센다. 관측 합 5.
    #   A = 2s1+2s2 ∈ {4(1가지), 0(2가지), -4(1가지)}, B = s3+s4+s5 ∈ {3(1), 1(3), -1(3), -3(1)}
    #   |A+B|>=5: A=4일 때 B∈{1,3} → 3+1=4가지, A=-4일 때 B∈{-1,-3} → 3+1=4가지, A=0은 최대 3이라 없음
    #   → 8/32
    assert paired_permutation_p([2.0, 2.0, 1.0, 1.0, -1.0], seed=0) == 0.25


def test_permutation_열거_결과가_itertools_전수와_같다():
    diffs = [0.5, -0.25, 0.75, 0.1, -0.3, 0.6]
    n = len(diffs)
    observed = abs(sum(diffs)) / n
    count = sum(
        abs(sum(s * d for s, d in zip(signs, diffs, strict=True))) / n >= observed - 1e-12
        for signs in itertools.product((1, -1), repeat=n)
    )
    assert paired_permutation_p(diffs, seed=0) == pytest.approx(count / 2**n)


def test_permutation_0인_차이는_결과를_바꾸지_않는다():
    assert paired_permutation_p([1.0, 2.0, 3.0, 0.0, 0.0], seed=0) == 0.25


def test_permutation_부호를_모두_뒤집어도_같다():
    diffs = [2.0, 2.0, 1.0, 1.0, -1.0]
    assert paired_permutation_p(diffs, seed=0) == paired_permutation_p([-x for x in diffs], seed=0)


def test_permutation_21개_이상은_시드가_같으면_같은_값이고_최솟값은_1_나누기_samples_더하기_1이다():
    first = paired_permutation_p([1.0] * 21, seed=7, samples=2000)
    assert first == paired_permutation_p([1.0] * 21, seed=7, samples=2000)
    # 참값 2/2^21 ≈ 1e-6이라 극단 표본이 안 나온다 → (0+1)/(2000+1)
    assert first == pytest.approx(1 / 2001)


def test_permutation_몬테카를로는_정확값_근처다():
    # [1]*14 + [-1]*7: 합 7. 양의 부호가 k개일 때 합 = 2k-21, |합|>=7 ↔ k>=14 또는 k<=7. 대칭이라 2*Σ_{k>=14} C(21,k)/2^21
    exact = 2 * sum(math.comb(21, k) for k in range(14, 22)) / 2**21
    assert exact == pytest.approx(0.18925, abs=1e-5)
    got = paired_permutation_p([1.0] * 14 + [-1.0] * 7, seed=7, samples=20_000)
    assert got == pytest.approx(exact, abs=0.01)


def test_permutation_상쇄되는_21개_이상은_몬테카를로에서도_1이다():
    # [1]*11 + [-1]*11: 관측 평균 0 → 모든 표본이 극단 → (S+1)/(S+1)
    assert paired_permutation_p([1.0] * 11 + [-1.0] * 11, seed=3, samples=500) == 1.0


# ---------- Holm ----------


def test_holm_손계산과_같다():
    # m=3: 0.01*3=0.03, 0.03*2=0.06, 0.04*1=0.04 → 누적 최댓값으로 0.06
    out = holm_adjust({"a": 0.01, "b": 0.03, "c": 0.04})
    assert out == pytest.approx({"a": 0.03, "b": 0.06, "c": 0.06})


def test_holm_입력_순서와_상관없이_이름에_맞게_돌려준다():
    # 오름차순 0.001(x4=0.004), 0.02(x3=0.06), 0.04(x2=0.08), 0.5(x1=0.5)
    out = holm_adjust({"d": 0.5, "b": 0.02, "a": 0.001, "c": 0.04})
    assert out == pytest.approx({"a": 0.004, "b": 0.06, "c": 0.08, "d": 0.5})


def test_holm_1을_넘지_않고_뒤쪽도_앞보다_작아지지_않는다():
    # m=2: 0.5*2=1.0, 0.6*1=0.6 → 누적 최댓값 1.0
    assert holm_adjust({"a": 0.5, "b": 0.6}) == {"a": 1.0, "b": 1.0}
    # 0.9*2=1.8 → 1로 잘림
    assert holm_adjust({"a": 0.9, "b": 0.95})["a"] == 1.0


def test_holm_하나뿐이면_그대로이고_비면_빈_딕셔너리다():
    assert holm_adjust({"a": 0.04}) == {"a": 0.04}
    assert holm_adjust({}) == {}


def test_holm_반올림하지_않는다():
    # 3*1e-8 = 3e-8 (소수 여섯째 자리로 반올림하면 0이 된다)
    assert holm_adjust({"a": 1e-8, "b": 0.5, "c": 0.7})["a"] == pytest.approx(3e-8)


# ---------- 세 함수를 잇는 예 ----------


def test_세_함수를_이어_쓰는_입력_형식_예():
    # 질문 10개의 Hit@10(1/0). A만 성공한 질문 7개, B만 성공한 질문 1개, 둘 다 성공 1개, 둘 다 실패 1개
    a = [1] * 7 + [0] + [1] + [0]
    b = [0] * 7 + [1] + [1] + [0]
    a_wins = sum(x > y for x, y in zip(a, b, strict=True))
    b_wins = sum(y > x for x, y in zip(a, b, strict=True))
    assert (a_wins, b_wins) == (7, 1)
    p_hit = exact_mcnemar(a_wins, b_wins)
    # 연속 지표의 질문별 차이(A-B)와 Holm으로 두 비교를 한 가족으로 보정
    p_cont = paired_permutation_p([0.1, 0.2, 0.3, 0.4, 0.5], seed=1)
    assert p_cont == 2 / 32  # 전부 양수 → 2/2^5
    adjusted = holm_adjust({"hit": p_hit, "cont": p_cont})
    # 오름차순 cont(0.0625)x2=0.125, hit(0.0703125)x1 → 누적 최댓값 0.125
    assert adjusted == pytest.approx({"cont": 0.125, "hit": 0.125})


# ---------- 축척(단위) 불변과 정확한 비교 ----------


@pytest.mark.parametrize("scale", [1e-16, 2e-15, 1e-3, 1e3, 1e12])
def test_permutation_같은_값을_작거나_큰_단위로_써도_p값이_같다_전수(scale):
    # 원소가 모두 같으면 어떤 단위에서도 부호 조합의 합이 십진수로 정확히 같은 배수다
    assert paired_permutation_p([scale] * 10, seed=0) == 2 / 1024
    assert paired_permutation_p([1.0] * 10, seed=0) == 2 / 1024


@pytest.mark.parametrize("exponent", [-16, -3, 3, 12])
def test_permutation_십진수_단위를_바꿔_쓰면_섞인_값도_p값이_같다(exponent):
    # 정수 값을 "3e-16"처럼 단위만 바꿔 쓴 십진수로 읽는다(곱셈의 부동소수 반올림이 끼지 않게 문자열로 만든다)
    mixed = [1, -2, 3, 1, -1, 2, 4, -1]
    rescaled = [float(f"{x}e{exponent}") for x in mixed]
    assert paired_permutation_p(rescaled, seed=0) == paired_permutation_p(
        [float(x) for x in mixed], seed=0
    )
    big = [1] * 14 + [-1] * 7 + [2]  # 22개라 몬테카를로 경로
    assert paired_permutation_p(
        [float(f"{x}e{exponent}") for x in big], seed=3, samples=2000
    ) == paired_permutation_p([float(x) for x in big], seed=3, samples=2000)


def test_permutation_아주_작은_값도_정확히_0이_아니면_버리지_않는다():
    # 원본은 |x|<=1e-15를 0으로 버려 [1e-16]*10이 1.0이 됐다
    assert paired_permutation_p([1e-16] * 10, seed=0) == 2 / 1024


@pytest.mark.parametrize("small", [1e-10, 2.5e-10, 1e-12, 2.5e-13, 1e-15, 1e-20])
def test_permutation_실제로_더_작은_합을_같다고_묶지_않는다(small):
    # [1, small]: 부호 조합 4개의 합 ±(1+small), ±(1-small). 관측 |1+small| 이상은 두 조합뿐 → 2/4
    assert paired_permutation_p([1.0, small], seed=0) == 0.5


def test_permutation_십진수로는_합이_정확히_0인_입력은_1이다():
    # 이진 부동소수에서는 합이 1e-17대로 남지만 십진수로는 정확히 0 → 모든 부호 조합이 극단이므로 p=1.0
    diffs = [0.9, -0.8, 0.2, -0.2, 0.2, -0.4, 0.4, 0.8, -0.5, -0.6, -0.6, 0.8, -1.0, 0.8]
    assert paired_permutation_p(diffs, seed=0) == 1.0
    assert paired_permutation_p([0.1, 0.2, -0.3], seed=0) == 1.0


def test_permutation_numpy_스칼라도_파이썬_float와_같은_값이다():
    values = [0.1, 0.2, -0.3, 0.45, -0.05]
    expected = paired_permutation_p(values, seed=0)
    assert paired_permutation_p([np.float64(x) for x in values], seed=0) == expected
    assert paired_permutation_p(list(np.array(values)), seed=0) == expected

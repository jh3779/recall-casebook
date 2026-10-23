"""두 시스템의 같은 질문 점수를 짝지어 비교하는 유의성 검정 함수 — 표준 라이브러리만 쓰는 순수 함수. 연구용(research).

원 작성자: powercodingman (PR #133 `scripts/defect_precedent/eval_v2.py`의 `exact_mcnemar`·
`paired_permutation_p`·`holm_adjust`). PR #133은 병합 없이 닫혔고(2026-10-21), 이 파일은 그 세 함수만
이슈 #179 1절에 따라 가져와 독립 모듈로 옮겼다. 출처 커밋은 `93be7082a433b0638c5baa2bf67594b09cd0c3ef`,
원문 위치는 `docs/experiments/실험_자동규칙라벨재감사.md`에 적었다.

원본과 다른 점은 셋이다. (1) `holm_adjust`가 소수 여섯째 자리 반올림을 하지 않는다 — 순수 함수는 값을 그대로
돌려주고 표시용 반올림은 부르는 쪽이 한다. (2) 이 파일은 `eval_v2.py`의 라벨 읽기·지표(Hit@10·nDCG 등)를
가져오지 않는다. 그쪽에는 빈 라벨을 0점으로 치는 등 고쳐야 할 결함이 남아 있어(이슈 #179 1절) 가져오지 않았다.

(3) `paired_permutation_p`의 0 판정·동률 허용오차가 원본의 고정 절댓값(1e-15)이었는데, 모든 차이에 같은 양수를 곱한(단위를 바꾼)
입력에서 결과가 달라지는 결함이라(Codex 리뷰, 예: [1.0]*10 → 0.00195, [2e-15]*10 → 0.109) 허용오차를 없앴다. 입력을 쓰인 그대로의
십진수(repr)로 읽어 정수로 바꾸고 합을 정확히 비교한다(상대 오차 방식은 [1.0, 2.5e-13]처럼 실제로 더 작은 합을 같다고 묶는 결함이
있어 쓰지 않았다). 축척·경계 시험이 `tests/test_significance.py`에 있다.

이 모듈은 아무 곳에서도 import하지 않는다 — 검색·점수·서비스 응답을 바꾸지 않는다. 어떤 평가 점수도 만들지 않으며,
유효한 평가 라벨이 없으면 이 함수들로 성능을 주장하지 않는다(AGENTS.md 5-1·5-2).

입력 형식
- `exact_mcnemar(a_wins, b_wins)` — 짝 이진 결과(예: 질문마다 Hit@10 성공/실패)에서 **불일치 쌍**의 수.
  a_wins = A만 성공·B는 실패한 질문 수, b_wins = 반대. 둘 다 성공/둘 다 실패한 질문은 세지 않는다.
- `paired_permutation_p(differences, seed)` — 질문마다 (A 점수 − B 점수). 평균 차이가 0인지 보는 양측 검정.
- `holm_adjust(pvalues)` — {비교 이름: 원래 p값}. 같은 가족(예: 한 지표의 세 쌍 비교)을 한 번에 넣는다.
"""

import math
import random
from fractions import Fraction


def exact_mcnemar(a_wins: int, b_wins: int) -> float:
    """짝 이진 결과의 exact McNemar 양측 p값(동률 문항 제외).

    귀무가설(두 시스템의 성공률이 같다) 아래에서 불일치 쌍 n = a_wins + b_wins개는 각각 공평한 동전이므로
    작은 쪽 수 이하가 나올 확률 = Σ_{i<=min} C(n,i) / 2^n 이고, 양측은 이것의 두 배(1을 넘지 않게 자른다).
    """
    n = a_wins + b_wins
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(a_wins, b_wins) + 1)) / (2**n)
    return min(1.0, 2 * tail)


def _decimal_ints(values: list[float]) -> list[int]:
    """각 값을 쓰인 그대로의 십진수(`repr`)로 읽어 공통 분모의 정수로 바꾼다 — 합을 정확히 비교하려는 것이다.

    이진 부동소수의 합산 오차로 같은 합이 다르게 나오는 문제(예: 0.1+0.2)와, 이를 가리려고 쓰는 허용오차가 단위(축척)에
    따라 결과를 바꾸는 문제를 함께 피한다. 모든 값에 같은 양수를 곱해도(곱셈이 십진수로 정확할 때) 정수 비율이 같아 p값이 같다.
    """
    fractions = [Fraction(repr(x)) for x in values]
    scale = math.lcm(*(f.denominator for f in fractions))
    return [int(f * scale) for f in fractions]


def paired_permutation_p(differences: list[float], seed: int, samples: int = 100_000) -> float:
    """평균 차이의 양측 paired sign-flip permutation p값.

    귀무가설(차이의 부호는 무작위다) 아래에서 각 차이의 부호를 뒤집은 합(평균과 같은 순서) 가운데, 관측 합의 절댓값 이상인
    것의 비율이다. 차이가 0인 문항은 합을 바꾸지 못하므로 뺀다(전부 0이면 1.0). 비교는 허용오차 없이 **정확히** 한다 —
    입력을 십진수 정수로 바꿔 세므로 합이 십진수로 같으면 같고 조금이라도 다르면 다르다(NaN·무한대는 받지 않는다).
    20개 이하는 부호 조합 분포를 정확히 계산하고, 그보다 크면 고정 시드 Monte Carlo를 쓴다
    (이때 값은 (극단 횟수 + 1) / (samples + 1)이라 0이 되지 않는다).
    """
    diffs = [x for x in differences if x != 0]
    if not diffs:
        return 1.0
    ints = _decimal_ints(diffs)
    observed = abs(sum(ints))
    if len(ints) <= 20:
        dist: dict[int, int] = {0: 1}  # 합 -> 그 합이 되는 부호 조합 수
        for x in ints:
            nxt: dict[int, int] = {}
            for total, count in dist.items():
                nxt[total + x] = nxt.get(total + x, 0) + count
                nxt[total - x] = nxt.get(total - x, 0) + count
            dist = nxt
        extreme = sum(count for total, count in dist.items() if abs(total) >= observed)
        return extreme / (1 << len(ints))
    rng = random.Random(seed)
    extreme = 0
    for _ in range(samples):
        extreme += abs(sum(x if rng.getrandbits(1) else -x for x in ints)) >= observed
    return (extreme + 1) / (samples + 1)


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    """가족 내 다중 비교를 위한 Holm 보정 p값.

    p값을 오름차순으로 놓고 i번째(0부터)에 (m - i)를 곱한 뒤, 앞선 값보다 작아지지 않게(누적 최댓값)
    하고 1로 자른다. 같은 p값끼리는 입력 순서를 따른다.
    """
    ordered = sorted(pvalues, key=pvalues.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    m = len(ordered)
    for i, name in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * pvalues[name]))
        adjusted[name] = running
    return adjusted

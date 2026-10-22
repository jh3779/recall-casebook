"""두 시스템의 같은 질문 점수를 짝지어 비교하는 유의성 검정 함수 — 표준 라이브러리만 쓰는 순수 함수. 연구용(research).

원 작성자: powercodingman (PR #133 `scripts/defect_precedent/eval_v2.py`의 `exact_mcnemar`·
`paired_permutation_p`·`holm_adjust`). PR #133은 병합 없이 닫혔고(2026-10-21), 이 파일은 그 세 함수만
이슈 #179 1절에 따라 가져와 독립 모듈로 옮겼다. 출처 커밋은 `93be7082a433b0638c5baa2bf67594b09cd0c3ef`,
원문 위치는 `docs/experiments/실험_자동규칙라벨재감사.md`에 적었다.

원본과 다른 점은 셋이다. (1) `holm_adjust`가 소수 여섯째 자리 반올림을 하지 않는다 — 순수 함수는 값을 그대로
돌려주고 표시용 반올림은 부르는 쪽이 한다. (2) 이 파일은 `eval_v2.py`의 라벨 읽기·지표(Hit@10·nDCG 등)를
가져오지 않는다. 그쪽에는 빈 라벨을 0점으로 치는 등 고쳐야 할 결함이 남아 있어(이슈 #179 1절) 가져오지 않았다.

(3) `paired_permutation_p`의 0 판정·동률 허용오차가 원본의 고정 절댓값(1e-15)이었는데, 모든 차이에 같은 양수를 곱한(단위를 바꾼)
입력에서 결과가 달라지는 결함이라(Codex 리뷰, 예: [1.0]*10 → 0.00195, [2e-15]*10 → 0.109) 정확히 0만 빼고 합은 math.fsum으로,
동률 비교는 자료의 크기에 비례하는 허용오차(평균 절댓값의 1e-12배)로 바꿨다. 축척 불변 시험이 `tests/test_significance.py`에 있다.

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


def paired_permutation_p(differences: list[float], seed: int, samples: int = 100_000) -> float:
    """평균 차이의 양측 paired sign-flip permutation p값.

    귀무가설(차이의 부호는 무작위다) 아래에서 각 차이의 부호를 뒤집은 평균 가운데, 관측 평균의 절댓값 이상인
    것의 비율이다. 차이가 0인 문항은 평균을 바꾸지 못하므로 뺀다(전부 0이면 1.0).
    20개 이하는 모든 부호 조합을 열거해 정확값을 내고, 그보다 크면 고정 시드 Monte Carlo를 쓴다
    (이때 값은 (극단 횟수 + 1) / (samples + 1)이라 0이 되지 않는다).
    """
    diffs = [
        x for x in differences if x != 0
    ]  # 정확히 0인 값만 뺀다 — 고정 허용오차는 단위(축척)에 따라 결과를 바꾼다
    if not diffs:
        return 1.0
    observed = abs(math.fsum(diffs) / len(diffs))
    # 부동소수 합산 오차로 같은 값이 아주 조금 작게 나오는 경우만 같다고 본다. 허용오차를 자료 자체의 크기(평균 절댓값)에 맞추므로
    # 모든 차이에 같은 양수를 곱하면(단위를 바꾸면) 허용오차도 같은 배율로 변해 판정이 달라지지 않는다. 합이 0으로 상쇄되는
    # 입력과 값의 크기 차이가 큰 입력에서도 정의대로 센다.
    tol = 1e-12 * math.fsum(abs(x) for x in diffs) / len(diffs)
    if len(diffs) <= 20:
        extreme = 0
        total = 1 << len(diffs)
        for mask in range(total):
            mean = math.fsum(x if mask & (1 << i) else -x for i, x in enumerate(diffs)) / len(diffs)
            extreme += abs(mean) >= observed - tol
        return extreme / total
    rng = random.Random(seed)
    extreme = 0
    for _ in range(samples):
        mean = math.fsum(x if rng.getrandbits(1) else -x for x in diffs) / len(diffs)
        extreme += abs(mean) >= observed - tol
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

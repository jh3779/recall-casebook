"""고객사 선례를 먼저 보여 준다 (기획 1절 — 사용자는 현대·기아에 납품하는 부품사 엔지니어).

고객사는 회사명 대응표 확인본의 `maker_group` **허용 목록**으로만 정한다. 이름에 "Hyundai"·"Kia"가 들어간다고 고객사로 보지 않는다
(Hyundai Translead 트레일러, HYUNDAI CARIBBEAN-PUERTO RICO 유통사, Genesis Supreme RV, NOKIAN TYRES는 다른 회사다).
순서를 바꿀 뿐 검색 결과를 걸러내거나 점수를 바꾸지 않는다.
"""

CUSTOMER_GROUPS = frozenset({"Hyundai Motor America", "Kia"})
POOL = 100  # 고객사 선례를 찾는 범위: 합친 순위의 상위 100
CUSTOMER_TOP = 5
OTHERS_TOP = 10


def is_customer(card: dict) -> bool:
    return card.get("maker_group") in CUSTOMER_GROUPS


def split(ranking: list[str], by_id: dict[str, dict]) -> tuple[list[int], list[int]]:
    """(고객사 선례, 같은 부품·다른 회사 선례)를 합친 순위의 위치(0부터)로 돌려준다."""
    customers = [r for r, c in enumerate(ranking[:POOL]) if is_customer(by_id[c])][:CUSTOMER_TOP]
    others = [r for r, c in enumerate(ranking) if not is_customer(by_id[c])][:OTHERS_TOP]
    return customers, others

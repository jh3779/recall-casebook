"""응답을 내보내기 전 검사 (AGENTS.md 2-2).

1. 응답의 모든 리콜 번호가 검색이 넘긴 후보 안에 있어야 한다 — 밖의 번호는 지어낸 것으로 보고 응답을 내보내지 않는다.
2. 원인 문장은 원인 원문에서 글자 그대로 찾아져야 한다(`engine2_trial.check`, 정규화 없음). 지금은 원문을 통째로 옮기므로 항상
   통과해야 하고, 실패하면 그 원인 글을 빼고 상태만 남긴다.
"""

from scripts.defect_precedent.engine2_trial import check


class OutOfCandidates(RuntimeError):
    """검색 후보 밖의 리콜 번호가 응답에 들어갔다."""


def verify(cards: list[dict], candidates: frozenset[str], causes: dict[str, dict]) -> list[dict]:
    for card in cards:
        if card["campno"] not in candidates:
            raise OutOfCandidates(card["campno"])
        cause = card["cause"]
        if cause["status"] == "filled":
            original = causes[cause["source"]["campaign"]]["cause_text"]
            spans = check(original, [cause["text"]])["spans"]
            if not spans or spans[0]["text"] != cause["text"]:
                card["cause"] = {"status": "verify_failed", "campaign": cause["source"]["campaign"]}
    return cards

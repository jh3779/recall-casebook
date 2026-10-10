"""응답을 내보내기 전 검사 (AGENTS.md 2-2).

1. 응답의 모든 리콜 번호가 검색이 넘긴 후보 안에 있어야 한다 — 밖의 번호는 지어낸 것으로 보고 응답을 내보내지 않는다.
2. 원인 문장은 원인 원문에서 글자 그대로 찾아져야 한다(`engine2_trial.check`, 정규화 없음). 지금은 원문을 통째로 옮기므로 항상
   통과해야 하고, 실패하면 그 원인 글을 빼고 상태만 남긴다.
3. 조사 요약은 원본 조사 기록과 글자 그대로 같아야 하고, 표시 꼬리표의 구간은 그 글의 같은 위치에서 같은 글자여야 한다.
   다르면 그 조사 요약(또는 원인 글)을 빼지 않고 응답 자체를 내보내지 않는다 — 원문을 그대로 옮기는 경로라 어긋나면 코드 결함이다.
"""

from scripts.defect_precedent.engine2_trial import check


class OutOfCandidates(RuntimeError):
    """검색 후보 밖의 리콜 번호가 응답에 들어갔다."""


class NotVerbatim(RuntimeError):
    """조사 요약이나 꼬리표 구간이 원문과 글자 그대로 같지 않다."""


def _spans_match(text: str, flag_list: list[dict]) -> bool:
    return all(text[s["start"] : s["end"]] == s["text"] for f in flag_list for s in f["spans"])


def verify(
    cards: list[dict],
    candidates: frozenset[str],
    causes: dict[str, dict],
    investigations: dict[str, list[dict]] | None = None,
) -> list[dict]:
    for card in cards:
        if card["campno"] not in candidates:
            raise OutOfCandidates(card["campno"])
        cause = card["cause"]
        if cause["status"] == "filled":
            original = causes[cause["source"]["campaign"]]["cause_text"]
            spans = check(original, [cause["text"]])["spans"]
            if not spans or spans[0]["text"] != cause["text"]:
                card["cause"] = {"status": "verify_failed", "campaign": cause["source"]["campaign"]}
            elif not _spans_match(cause["text"], cause["flags"]):
                raise NotVerbatim(f"{card['campno']} 원인 글의 꼬리표 구간")
        originals = {
            i["action"]: i["summary"] for i in (investigations or {}).get(card["campno"], [])
        }
        for inv in card.get("investigations", []):
            if originals.get(inv["action"]) != inv["summary"] or not _spans_match(
                inv["summary"], inv["flags"]
            ):
                raise NotVerbatim(f"{card['campno']} 조사 {inv['action']} 요약")
    return cards

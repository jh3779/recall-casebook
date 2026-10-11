"""리콜 카드에 Part 573 보고서의 원인 칸을 원문 그대로 붙인다 (DEC-039 — 원인 칸이 있는 카드는 LLM 없이 원문을 보여 준다).
PDF 글자 추출 뒤 쪽 머리말·꼬리말 제거와 공백 정리만 거치고, 그 정리 방식은 build의 `text_basis`로 밝힌다 (DEC-047).

말한 주체는 리콜한 제조사다(573 보고서는 제조사가 NHTSA에 낸 신고서). 원인 칸이 없거나 비었거나, 어느 판본이 최신인지
정하지 못한 보고서(`resolution = unresolved`)는 글을 싣지 않고 상태만 알린다 — 판본을 짐작하지 않는다(AGENTS.md 2-3).
보고서가 "없다"고 말할 수 있는 것은 573 원문 수집 범위(접수일 2014-08-20 이전) 밖의 리콜뿐이다. 범위 안인데 원문 목록에도
실패 목록에도 없는 리콜은 이유를 모르므로 `report_status_unknown`으로 따로 알린다.
"""

from scripts.defect_precedent.nhtsa import RCLRPT_FROM
from server.rag.flags import flags

SPEAKER_573 = "리콜 제조사 (Part 573 결함·불합치 보고서)"


def cause_573(
    card: dict, causes: dict[str, dict], unreadable: dict[str, str] | None = None
) -> dict:
    campaign = card["campno"][:6]
    row = causes.get(campaign)
    if row is None and campaign in (unreadable or {}):
        # 보고서는 있는데 우리 쪽에서 읽지 못했다 — "보고서 없음"으로 보이지 않게 따로 알린다
        return {"status": "report_unreadable", "campaign": campaign, "reason": unreadable[campaign]}
    if row is None and card["received_date"] < RCLRPT_FROM:
        return {"status": "no_573_report"}  # 573 원문 수집 범위 밖 (접수일 2014-08-20 이전)
    if row is None:
        return {"status": "report_status_unknown", "campaign": campaign}
    if row["resolution"] == "unresolved":
        return {"status": "version_unresolved", "campaign": row["campaign"]}
    if row["cause_status"] not in ("filled", "stated_unknown"):
        return {"status": f"cause_{row['cause_status']}", "campaign": row["campaign"]}
    # stated_unknown = 제조사가 원인 칸에 원인 대신 "미보고·조사 중"을 적었다 — 그 글도 원문 그대로, 말한 주체와 함께 보여 준다(DEC-047)
    return {
        "status": row["cause_status"],
        "text": row["cause_text"],
        "speaker": SPEAKER_573,
        "flags": flags(row["cause_text"]),
        "source": {
            "campaign": row["campaign"],
            "file": row["source_file"],
            "pdf_sha256": row["pdfs"][row["source_file"]],
            "submission_date": row["submission_date"],
            "text_basis": row[
                "text_basis"
            ],  # 이 build의 판독 규칙이 기록한 정리 방식(DEC-047, 원인 파일 명세)
        },
    }

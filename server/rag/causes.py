"""리콜 카드에 Part 573 보고서의 원인 칸을 원문 그대로 붙인다 (DEC-039 — 원인 칸이 있는 카드는 LLM 없이 원문을 보여 준다).

말한 주체는 리콜한 제조사다(573 보고서는 제조사가 NHTSA에 낸 신고서). 원인 칸이 없거나 비었거나, 어느 판본이 최신인지
정하지 못한 보고서(`resolution = unresolved`)는 글을 싣지 않고 상태만 알린다 — 판본을 짐작하지 않는다(AGENTS.md 2-3).
"""

SPEAKER_573 = "리콜 제조사 (Part 573 결함·불합치 보고서)"


def cause_573(card: dict, causes: dict[str, dict]) -> dict:
    row = causes.get(card["campno"][:6])
    if row is None:
        return {"status": "no_573_report"}  # 2014-08-20 이전 리콜 등 보고서 원문을 받지 않은 캠페인
    if row["resolution"] == "unresolved":
        return {"status": "version_unresolved", "campaign": row["campaign"]}
    if row["cause_status"] != "filled":
        return {"status": f"cause_{row['cause_status']}", "campaign": row["campaign"]}
    return {
        "status": "filled",
        "text": row["cause_text"],
        "speaker": SPEAKER_573,
        "source": {
            "campaign": row["campaign"],
            "file": row["source_file"],
            "pdf_sha256": row["pdfs"][row["source_file"]],
            "submission_date": row["submission_date"],
        },
    }

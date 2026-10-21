"""확인 항목 고정 틀 — 엔지니어가 선례를 자기 결함과 비교할 때 볼 항목과 그 근거 원문 (docs/product/계획_P2_API서버.md 1절).

규칙만 쓰고 LLM은 쓰지 않는다. 항목마다 근거(칸 이름 + 원문 글)를 잇고, 근거가 없으면 그 항목을 싣지 않는다.
같은지 다른지는 판단하지 않는다 — 비교할 근거를 나란히 보여 줄 뿐이다(AGENTS.md 2-1).
생산 기간은 573 보고서의 `Production Dates` 칸(블록마다 한 줄)을 원문 그대로 보여 줄 뿐이다 — 사용자 자신의 생산 기간은
입력으로 받지 않으므로 겹치는지는 서비스가 판단하지 않는다(DEC-059). 날짜까지 읽힌 블록만 싣고, 판본을 정하지 못한 보고서는 쓰지 않는다.
"""

from server.rag.causes import SPEAKER_573
from server.rag.investigations import SPEAKER_INV

PRODUCTION_SHOWN = 5  # 한 항목에 싣는 생산 기간 블록 수 — 나머지는 `omitted`로 알린다(최대 171블록)

ITEMS = (
    ("same_part", "같은 부품"),
    ("production_period", "생산 기간"),
    ("failure_mode", "고장 양상"),
    ("remedy", "시정"),
    ("supplier", "공급사"),
    ("cause_speaker", "원인을 말한 주체"),
)


def production_evidence(cause_row: dict | None) -> tuple[list[dict], int, int, dict | None]:
    """(싣는 근거, 한도 때문에 싣지 못한 블록 수, 날짜를 읽지 못해 싣지 않은 블록 수, 출처).

    블록마다 `머리글 | Production Dates 원문`이고, 머리글이 없으면 원문만이다. 날짜까지 읽힌 블록만 싣되, 읽지 못해 뺀 블록은
    개수를 알려 목록이 전부라고 믿지 않게 한다. 출처는 읽은 573 보고서 판본(파일·sha256·제출일)이다 — 원인 글이 없는
    카드에서도 생산 기간 근거를 되짚을 수 있게 한다(AGENTS.md 2-4).
    """
    if not cause_row or cause_row.get("resolution") == "unresolved":
        return [], 0, 0, None
    every = cause_row.get("production_dates", [])
    blocks = [b for b in every if b["start"] and b["end"]]
    if not blocks:  # 싣을 근거가 없으면 출처도 만들지 않는다 — 생산 기간과 무관한 카드가 출처 칸 때문에 멈추지 않게
        return [], 0, 0, None
    shown = blocks[:PRODUCTION_SHOWN]
    evidence = [
        {
            "field": "573.production_dates",
            "text": f"{b['label']} | {b['raw']}" if b["label"] else b["raw"],
        }
        for b in shown
    ]
    source = {
        "campaign": cause_row["campaign"],
        "file": cause_row["source_file"],
        "pdf_sha256": cause_row["pdfs"][cause_row["source_file"]],
        "submission_date": cause_row["submission_date"],
    }
    return evidence, len(blocks) - len(shown), len(every) - len(blocks), source


def checklist(
    card: dict, cause_row: dict | None, investigations: list[dict], cause: dict
) -> list[dict]:
    production, omitted, unread, source = production_evidence(cause_row)
    evidence: dict[str, list[dict]] = {
        "same_part": [{"field": "components", "text": c} for c in card["components"] if c],
        "production_period": production,
        # 고장 양상 = 결함 원문(무엇이 어떻게 고장 나는가) + 결과 원문(그래서 무슨 일이 생기는가) — 칸 이름으로 구분한다
        "failure_mode": [
            {"field": f, "text": card[f]} for f in ("defect", "consequence") if card[f]
        ],
        "remedy": [{"field": "remedy", "text": card["remedy"]}] if card["remedy"] else [],
        # 판본을 정하지 못한 573 보고서의 칸은 쓰지 않는다 (원인 글과 같은 규칙)
        "supplier": [
            {"field": "573.supplier_names", "text": s}
            for s in (cause_row or {}).get("supplier_names", [])
            if s and cause_row.get("resolution") != "unresolved"
        ],
        "cause_speaker": (
            [{"field": "cause.speaker", "text": SPEAKER_573}]
            if cause["status"] in ("filled", "stated_unknown")
            else []
        )
        + (
            [{"field": "investigations.speaker", "text": SPEAKER_INV}]
            + [{"field": "investigations.action", "text": i["action"]} for i in investigations]
            if investigations
            else []
        ),
    }
    return [
        {"item": key, "label": label, "evidence": evidence[key]}
        | ({"omitted": omitted} if key == "production_period" and omitted else {})
        | ({"unread": unread} if key == "production_period" and unread else {})
        | ({"source": source} if key == "production_period" else {})
        for key, label in ITEMS
        if evidence[key]
    ]

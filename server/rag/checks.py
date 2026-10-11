"""확인 항목 고정 틀 — 엔지니어가 선례를 자기 결함과 비교할 때 볼 항목과 그 근거 원문 (docs/계획_P2_API서버.md 1절).

규칙만 쓰고 LLM은 쓰지 않는다. 항목마다 근거(칸 이름 + 원문 글)를 잇고, 근거가 없으면 그 항목을 싣지 않는다.
같은지 다른지는 판단하지 않는다 — 비교할 근거를 나란히 보여 줄 뿐이다(AGENTS.md 2-1).
생산 기간은 카드에 연식·생산일 칸이 없어 1차에서 뺐다(한계).
"""

from server.rag.causes import SPEAKER_573
from server.rag.investigations import SPEAKER_INV

ITEMS = (
    ("same_part", "같은 부품"),
    ("failure_mode", "고장 양상"),
    ("remedy", "시정"),
    ("supplier", "공급사"),
    ("cause_speaker", "원인을 말한 주체"),
)


def checklist(
    card: dict, cause_row: dict | None, investigations: list[dict], cause: dict
) -> list[dict]:
    evidence: dict[str, list[dict]] = {
        "same_part": [{"field": "components", "text": c} for c in card["components"] if c],
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
        for key, label in ITEMS
        if evidence[key]
    ]

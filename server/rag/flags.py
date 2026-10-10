"""원인 글에 붙이는 표시 꼬리표 — 판정이 아니라 "글에 이 표현이 있다"는 사실만 알린다 (docs/계획_P2_API서버.md 1절).

- `unknown_expression`(원인 미확인 표현 있음): `cause_trials.UNKNOWN_RE` — 원인을 모른다·조사 중·해당 없음 (#53 잠정안).
- `hedge_expression`(추정 표현 있음): 2026-10-10 정답 표시를 보기 전에 고정한 단어 목록. `may`·`could`는 결과를 설명할 때
  ("may result in", "could cause") 흔히 써서 넣지 않았다. 표시 결과를 보고 단어를 고치지 않는다(AGENTS.md 5-2).
꼬리표마다 걸린 원문 구간(시작·끝·글자)을 함께 싣는다 — 응답 검사(`verify.py`)가 원문에서 글자 그대로인지 다시 본다.
"""

import re

from scripts.defect_precedent.cause_trials import UNKNOWN_RE

HEDGE_RE = re.compile(
    r"\b(appear(s|ed)?\s+to|might|possibly|likely|probably|suspect(ed)?|believe(d)?)\b", re.I
)
FLAG_RULES = (
    ("unknown_expression", "원인 미확인 표현 있음", UNKNOWN_RE),
    ("hedge_expression", "추정 표현 있음", HEDGE_RE),
)


def flags(text: str) -> list[dict]:
    out = []
    for kind, label, rule in FLAG_RULES:
        spans = [
            {"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rule.finditer(text)
        ]
        if spans:
            out.append({"kind": kind, "label": label, "spans": spans})
    return out

"""서버와 연구 스크립트가 함께 쓰는 판별 규칙 — 한 곳에만 둔다.

서버(`server/rag/`)가 연구 스크립트 파일을 직접 import하면, 실험을 고치다 서버 동작이 말없이 바뀐다. 그래서 둘이 같이 쓰는
규칙은 여기로 옮겼다. 정규식과 함수는 옮기기 전과 한 글자도 다르지 않다(`tests/test_rules.py`가 글자 그대로 고정한다).
규칙을 바꾸면 그 규칙으로 낸 수치(꼬리표 226·541, 조사 연결 1,870 등)가 바뀌므로 수치를 다시 보고한다(AGENTS.md 5-1).
"""

import re

# 573 원인 칸에서 원인을 모른다·조사 중·해당 없음을 말하는 흔한 표현 — 표본을 보기 전에 정한 규칙 (cause_trials, DEC-044)
UNKNOWN_RE = re.compile(
    r"\b(unknown|not known|under investigation|(continues?|continuing) to investigate|still investigating"
    r"|not (yet )?(been )?(determined|identified|established)|no root cause|root cause (is|has) not"
    r"|not applicable|n/a)\b",  # 'NA'(North America)를 잡지 않게 n/a만 (표본 150건에는 영향 없음)
    re.I,
)

# 결함 조사 요약의 자리표시 글 — 연결 수(1,870)를 낸 why_stats 규칙. nhtsa.PLACEHOLDER(시험지용)보다 넓다
INV_SUMMARY_PLACEHOLDER = re.compile(r"no summary currently available|^=+$", re.I)


def check(cause_text: str, got: list[str]) -> dict:
    """정규화 없이 원문에서 그대로 찾는다. 통과하면 원문 구간을 돌려준다."""
    spans, dropped = [], []
    for g in got:
        i = cause_text.find(g) if g else -1
        if i < 0:
            dropped.append(g)
        else:
            spans.append({"start": i, "end": i + len(g), "text": cause_text[i : i + len(g)]})
    return {
        "spans": spans,
        "dropped": dropped,
        "short_fragments": sum(1 for sp in spans if len(sp["text"].split()) < 5),
    }

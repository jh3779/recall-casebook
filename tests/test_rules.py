"""서버와 연구 스크립트가 함께 쓰는 규칙(rules.py)을 글자 그대로 고정한다.

규칙을 바꾸면 그 규칙으로 낸 수치(꼬리표 226·541, 조사 연결 1,870)가 달라진다 — 이 시험이 실패하면 규칙 변경을
의도한 것인지 확인하고, 수치를 다시 재서 보고한 뒤에 기대값을 고친다(AGENTS.md 3-5·5-1).
"""

import re

from scripts.defect_precedent import cause_trials, engine2_trial, rules, why_stats
from server.rag import flags, investigations, verify


def test_rule_patterns_are_fixed_letter_for_letter():
    assert rules.UNKNOWN_RE.pattern == (
        r"\b(unknown|not known|under investigation|(continues?|continuing) to investigate|still investigating"
        r"|not (yet )?(been )?(determined|identified|established)|no root cause|root cause (is|has) not"
        r"|not applicable|n/a)\b"
    )
    assert rules.INV_SUMMARY_PLACEHOLDER.pattern == r"no summary currently available|^=+$"
    assert rules.UNKNOWN_RE.flags & re.I and rules.INV_SUMMARY_PLACEHOLDER.flags & re.I


def test_server_and_research_scripts_use_the_same_rule_objects():
    assert cause_trials.UNKNOWN_RE is rules.UNKNOWN_RE is flags.UNKNOWN_RE
    assert engine2_trial.check is rules.check is verify.check
    assert why_stats.INV_SUMMARY_PLACEHOLDER is rules.INV_SUMMARY_PLACEHOLDER
    assert investigations.INV_SUMMARY_PLACEHOLDER is rules.INV_SUMMARY_PLACEHOLDER


def test_check_finds_spans_verbatim_without_normalizing():
    got = rules.check("The weld was improperly made.", ["improperly made", "Improperly made", ""])
    assert got["spans"] == [{"start": 13, "end": 28, "text": "improperly made"}]
    assert got["dropped"] == ["Improperly made", ""]
    assert got["short_fragments"] == 1

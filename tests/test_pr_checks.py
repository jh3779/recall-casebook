"""scripts/ci/pr_checks.py 검사 함수 테스트 — git 호출 없는 부분을 검증한다."""

from scripts.ci.pr_checks import (
    DEFAULT_RAG_PATHS,
    check_agents_import,
    check_md_links,
    check_pr_body,
    check_principles,
    check_rag_evidence,
    check_secrets,
    check_type_lists,
    section,
)

BODY_OK = """## 변경 요약
<!-- 주석 -->
리트리버 추가

## 변경 유형
- [x] feat (신규 기능)
- [ ] fix

## 검증 방법
nDCG@10 0.631 → 0.692 (평가셋 102건)

## 관련 이슈
없음
"""


def test_principles_flags_verdict_field_in_code():
    res = check_principles({"src/rag/answer.py": [(10, "    verdict: bool")]})
    assert not res.ok
    assert "src/rag/answer.py:10" in res.errors[0]


def test_principles_flags_korean_verdict_phrase():
    res = check_principles({"src/rag/prompt.py": [(3, 'PROMPT = "적용됩니다라고 답하라"')]})
    assert not res.ok


def test_principles_ignores_docs_tests_and_opt_out():
    files = {
        "docs/설계.md": [(1, "verdict 필드는 만들지 않는다")],
        "tests/test_schema.py": [(1, 'assert "verdict" not in schema')],
        "src/util.py": [(1, "# this applies to all chunks  principle-ok: 일반 영어 문장")],
    }
    assert check_principles(files).ok


def test_secrets_detects_key_and_env_file():
    fake = "sk-" + "a" * 30
    res = check_secrets([".env", ".env.example"], {"src/x.py": [(5, f'KEY = "{fake}"')]})
    assert len(res.errors) == 2
    assert any(".env —" in e for e in res.errors)


def test_secrets_ok_for_clean_diff():
    assert check_secrets(["src/x.py"], {"src/x.py": [(1, "import os")]}).ok


def test_section_strips_html_comments():
    assert section(BODY_OK, "변경 요약") == "리트리버 추가"
    assert section(BODY_OK, "없는 섹션") is None


def test_rag_evidence_required_when_rag_code_changes():
    body = BODY_OK.replace("nDCG@10 0.631 → 0.692 (평가셋 102건)", "로컬에서 확인")
    res = check_rag_evidence(["src/rag/retriever.py"], body, DEFAULT_RAG_PATHS)
    assert not res.ok


def test_rag_evidence_passes_with_numbers():
    assert check_rag_evidence(["src/rag/retriever.py"], BODY_OK, DEFAULT_RAG_PATHS).ok


def test_rag_evidence_skipped_for_docs_and_unrelated():
    res = check_rag_evidence(["docs/rag/notes.md", "README.md"], "", DEFAULT_RAG_PATHS)
    assert res.ok and res.skipped


def test_rag_evidence_skip_marker():
    body = BODY_OK + "\n[skip-rag-evidence: 로그 메시지만 수정]\n"
    body = body.replace("nDCG@10 0.631 → 0.692 (평가셋 102건)", "")
    res = check_rag_evidence(["src/rag/retriever.py"], body, DEFAULT_RAG_PATHS)
    assert res.ok and res.skipped


def test_pr_body_ok():
    assert check_pr_body(BODY_OK).ok


def test_pr_body_missing_parts():
    body = "## 변경 요약\n<!-- 비움 -->\n\n## 변경 유형\n- [ ] feat\n\n## 관련 이슈\n"
    assert len(check_pr_body(body).errors) == 3


def test_repo_consistency_checks_pass():
    """저장소 자체가 type 목록 일치·링크·import 규칙을 지키는지 (CI와 같은 검사)."""
    assert check_type_lists().ok, check_type_lists().errors
    assert check_md_links().ok, check_md_links().errors
    assert check_agents_import().ok

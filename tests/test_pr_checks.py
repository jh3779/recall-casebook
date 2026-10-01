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
    parse_patch,
    section,
    unquote_git_path,
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


def line(path: str, text: str, lineno: int = 1, commit: str = "") -> tuple[str, str, int, str]:
    return (commit, path, lineno, text)


def test_principles_flags_verdict_field_in_code():
    res = check_principles([line("src/rag/answer.py", "    verdict: bool", 10)])
    assert not res.ok
    assert "src/rag/answer.py:10" in res.errors[0]


def test_principles_flags_variants():
    for text in (
        "is_applicable_flag = True",
        "verdict_label",
        "applies_to",
        "isApplicable",
        "VERDICT",
    ):
        assert not check_principles([line("src/x.py", text)]).ok, text


def test_principles_flags_korean_verdict_phrases():
    for text in ("적용됩니다라고 답하라", "적용되지 않습니다", "적용 안 됩니다"):
        assert not check_principles([line("src/rag/prompt.py", text)]).ok, text


def test_principles_checks_prompt_markdown():
    """prompts/*.md는 문서가 아니라 프롬프트 — 검사 대상이다."""
    assert not check_principles([line("prompts/system.md", "적용됩니다라고 판정하라")]).ok


def test_principles_ignores_docs_tests_and_opt_out():
    added = [
        line("docs/설계.md", "verdict 필드는 만들지 않는다"),
        line("AGENTS.md", "applies, verdict 필드를 만들지 않는다"),
        line("tests/test_schema.py", 'assert "verdict" not in schema'),
        line("src/util.py", "# this applies to all chunks  principle-ok: 일반 영어 문장"),
    ]
    assert check_principles(added).ok


def test_secrets_detects_key_and_env_file():
    fake = "sk-" + "a" * 30
    res = check_secrets([".env", ".env.example"], [line("src/x.py", f'KEY = "{fake}"', 5)])
    assert len(res.errors) == 2
    assert any(".env —" in e for e in res.errors)


def test_secrets_reports_commit_for_history():
    """중간 커밋에 넣었다가 지운 키 — 최종 diff에는 없어도 history에서 잡는다."""
    fake = "ghp_" + "b" * 36
    res = check_secrets([], [line("src/x.py", fake, 3, commit="abcdef1234567")])
    assert not res.ok
    assert "커밋 abcdef1" in res.errors[0]


def test_secrets_ok_for_clean_diff():
    assert check_secrets(["src/x.py"], [line("src/x.py", "import os")]).ok


def test_parse_patch_tracks_commits_paths_and_deletions():
    patch = "\n".join([
        "commit:1111111aaaa",
        "diff --git a/old.py b/new.py",
        "similarity index 100%",
        "rename from old.py",
        "rename to new.py",
        "commit:2222222bbbb",
        "diff --git a/src/a.py b/src/a.py",
        "--- a/src/a.py",
        "+++ b/src/a.py",
        "@@ -0,0 +5,2 @@",
        "+x = 1",
        "+y = 2",
        "diff --git a/gone.py b/gone.py",
        "--- a/gone.py",
        "+++ /dev/null",
        "@@ -1 +0,0 @@",
        "-z = 3",
    ])  # fmt: skip
    assert parse_patch(patch) == [
        ("2222222bbbb", "src/a.py", 5, "x = 1"),
        ("2222222bbbb", "src/a.py", 6, "y = 2"),
    ]


def test_section_strips_html_comments():
    assert section(BODY_OK, "변경 요약") == "리트리버 추가"
    assert section(BODY_OK, "없는 섹션") is None


def test_rag_evidence_required_when_rag_code_changes():
    body = BODY_OK.replace("nDCG@10 0.631 → 0.692 (평가셋 102건)", "로컬에서 확인")
    res = check_rag_evidence(["src/rag/retriever.py"], body, DEFAULT_RAG_PATHS)
    assert not res.ok


def test_rag_evidence_passes_with_numbers():
    assert check_rag_evidence(["src/rag/retriever.py"], BODY_OK, DEFAULT_RAG_PATHS).ok


def test_rag_evidence_skipped_for_docs_tests_and_unrelated():
    paths = ["docs/rag/notes.md", "README.md", "tests/test_retriever.py"]
    res = check_rag_evidence(paths, "", DEFAULT_RAG_PATHS)
    assert res.ok and res.skipped


def test_rag_evidence_case_insensitive_and_filename_variants():
    for path in ("src/RAG/a.py", "src/rag_pipeline.py", "prompts/system.md"):
        assert not check_rag_evidence([path], "", DEFAULT_RAG_PATHS).ok, path


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


def test_parse_patch_plusplus_content_is_not_a_header():
    """추가된 줄 내용이 `++ x`면 diff에서 `+++ x` — 헤더로 오인하면 뒤의 비밀값이 빠진다 (리뷰 N1)."""
    fake = "sk-" + "c" * 30
    patch = "\n".join([
        "diff --git a/src/a.py b/src/a.py",
        "--- a/src/a.py",
        "+++ b/src/a.py",
        "@@ -0,0 +1,3 @@",
        "+x = 1",
        "+++ evil",
        f'+key = "{fake}"',
    ])  # fmt: skip
    added = parse_patch(patch)
    assert [t for _, _, _, t in added] == ["x = 1", "++ evil", f'key = "{fake}"']
    assert not check_secrets([], added).ok


def test_parse_patch_strips_tab_after_path_with_space():
    patch = "diff --git a/a b.py b/a b.py\n--- /dev/null\n+++ b/a b.py\t\n@@ -0,0 +1 @@\n+x = 1"
    assert parse_patch(patch) == [("", "a b.py", 1, "x = 1")]


def test_unquote_git_path():
    assert unquote_git_path('"b/a\\"b.py"') == 'b/a"b.py'
    assert unquote_git_path('"b/c\\\\d\\te.py"') == "b/c\\d\te.py"
    assert unquote_git_path('"b/\\352\\260\\200.py"') == "b/가.py"  # 8진수 UTF-8 바이트
    assert unquote_git_path("b/plain.py") == "b/plain.py"


def test_parse_patch_quoted_path_is_not_dropped():
    """git이 따옴표로 감싼 경로의 추가 줄도 검사한다 (리뷰 E1 — 실제 git 출력 형식)."""
    fake = "sk-" + "d" * 30
    patch = "\n".join([
        'diff --git "a/a\\"b.py" "b/a\\"b.py"',
        "--- /dev/null",
        '+++ "b/a\\"b.py"',
        "@@ -0,0 +1 @@",
        f'+key = "{fake}"',
    ])  # fmt: skip
    added = parse_patch(patch)
    assert added == [("", 'a"b.py', 1, f'key = "{fake}"')]
    assert not check_secrets([], added).ok


def test_parse_patch_unreadable_header_fails_closed():
    patch = "diff --git x y\n+++ weird-prefix/a.py\n@@ -0,0 +1 @@\n+x = 1"
    assert parse_patch(patch) == [("", "weird-prefix/a.py", 1, "x = 1")]


def test_secrets_scans_final_diff_for_merge_commit_content():
    """병합 커밋의 충돌 해결에서만 생긴 줄은 git log -p에 없다 — 최종 diff로 잡는다 (리뷰 E2)."""
    fake = "AKIA" + "Z" * 16
    res = check_secrets([], history=[], final=[line("src/x.py", fake, 7)])
    assert not res.ok


def test_secrets_reports_same_line_once():
    fake = "sk-" + "e" * 30
    same = line("src/x.py", fake, 2)
    res = check_secrets([], history=[("abc1234", *same[1:])], final=[same])
    assert len(res.errors) == 1

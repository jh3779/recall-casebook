"""scripts/ci/merge_gate.py 판정 로직 테스트 — GitHub 호출 없이 evaluate()만 검증한다."""

from scripts.ci.merge_gate import evaluate

HEAD = "b86f4ef0efa700cc53388958f6252ec117ed9922"
OLD = "937597a0000000000000000000000000000000000"


def review(sha: str) -> dict:
    return {"body": f"## 🤖 자동 리뷰 (head `{sha[:7]}`)\n\n내용"}


def result(mark: str, sha: str) -> dict:
    return {"body": f"## {mark} 병합 전 검증 결과 (head `{sha[:7]}`)\n\n| 게이트 |"}


def test_success_when_review_and_ok_result_on_head():
    gate = evaluate(HEAD, [], [review(HEAD), result("✅", HEAD)], 0)
    assert gate.state == "success"


def test_pending_without_review():
    gate = evaluate(HEAD, [], [result("✅", HEAD)], 0)
    assert gate.state == "pending"
    assert "자동 리뷰 없음" in gate.description


def test_review_on_old_head_does_not_count():
    gate = evaluate(HEAD, [], [review(OLD), result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_result_on_old_head_does_not_count():
    gate = evaluate(HEAD, [], [review(HEAD), result("✅", OLD)], 0)
    assert gate.state == "pending"
    assert "검증 결과 코멘트 없음" in gate.description


def test_latest_result_wins():
    ok_then_fail = [review(HEAD), result("✅", HEAD), result("❌", HEAD)]
    assert evaluate(HEAD, [], ok_then_fail, 0).state == "failure"
    fail_then_ok = [review(HEAD), result("❌", HEAD), result("✅", HEAD)]
    assert evaluate(HEAD, [], fail_then_ok, 0).state == "success"


def test_unresolved_threads_fail():
    gate = evaluate(HEAD, [], [review(HEAD), result("✅", HEAD)], 2)
    assert gate.state == "failure"
    assert "2개" in gate.description


def test_github_review_on_head_counts():
    gate = evaluate(HEAD, [{"commit": HEAD, "author": "bot"}], [result("✅", HEAD)], 0)
    assert gate.state == "success"


def test_github_review_on_old_commit_does_not_count():
    gate = evaluate(HEAD, [{"commit": OLD, "author": "bot"}], [result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_result_comment_is_not_a_review():
    gate = evaluate(HEAD, [], [result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_too_short_sha_rejected():
    body = {"body": "## 🤖 자동 리뷰 (head `b86f`)"}
    assert evaluate(HEAD, [], [body, result("✅", HEAD)], 0).state == "pending"

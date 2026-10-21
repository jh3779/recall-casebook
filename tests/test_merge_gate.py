"""scripts/ci/merge_gate.py 판정 로직 테스트 — GitHub 호출 없이 evaluate()·split_trusted()와 가짜 gh로 돌린 main()을 검증한다."""

import json

from scripts.ci import merge_gate as mg
from scripts.ci.merge_gate import evaluate, split_trusted

HEAD = "b86f4ef0efa700cc53388958f6252ec117ed9922"
OLD = "937597a0000000000000000000000000000000000"


def review(sha: str, at: str = "") -> dict:
    return {"body": f"## 🤖 자동 리뷰 (head `{sha[:7]}`)\n\n내용", "at": at}


def codex(sha: str, at: str = "") -> dict:
    return {"body": f"### 🤖 자동 리뷰 (Codex) — 커밋 `{sha[:8]}`\n\n## 전체 위험도: 상", "at": at}


def result(mark: str, sha: str, at: str = "") -> dict:
    return {"body": f"## {mark} 병합 전 검증 결과 (head `{sha[:7]}`)\n\n| 게이트 |", "at": at}


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


def gh_review(
    sha: str, state: str = "COMMENTED", body: str = "지적 1건", author: str = "bot"
) -> dict:
    return {"commit": sha, "state": state, "body": body, "author": author}


def test_github_review_on_head_counts():
    gate = evaluate(HEAD, [gh_review(HEAD)], [result("✅", HEAD)], 0)
    assert gate.state == "success"


def test_github_review_on_old_commit_does_not_count():
    gate = evaluate(HEAD, [gh_review(OLD)], [result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_empty_comment_review_from_thread_reply_does_not_count():
    gate = evaluate(HEAD, [gh_review(HEAD, body="")], [result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_retrigger_review_does_not_count():
    gate = evaluate(HEAD, [gh_review(HEAD, body="merge-gate 재판정")], [result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_dismissed_review_does_not_count():
    gate = evaluate(HEAD, [gh_review(HEAD, state="DISMISSED")], [result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_changes_requested_fails_even_with_ok_result():
    reviews = [gh_review(HEAD, state="CHANGES_REQUESTED", author="r1")]
    gate = evaluate(HEAD, reviews, [review(HEAD), result("✅", HEAD)], 0)
    assert gate.state == "failure"
    assert "r1" in gate.description


def test_comment_after_changes_requested_keeps_request_but_approval_clears_it():
    cr = gh_review(HEAD, state="CHANGES_REQUESTED", author="r1")
    comments = [review(HEAD), result("✅", HEAD)]
    assert evaluate(HEAD, [cr, gh_review(HEAD, author="r1")], comments, 0).state == "failure"
    approved = gh_review(HEAD, state="APPROVED", author="r1")
    assert evaluate(HEAD, [cr, approved], comments, 0).state == "success"


def test_result_comment_is_not_a_review():
    gate = evaluate(HEAD, [], [result("✅", HEAD)], 0)
    assert gate.state == "pending"


def test_too_short_sha_rejected():
    body = {"body": "## 🤖 자동 리뷰 (head `b86f`)"}
    assert evaluate(HEAD, [], [body, result("✅", HEAD)], 0).state == "pending"


def test_changes_requested_on_old_commit_still_blocks():
    """변경 요청 뒤 push해도 풀리지 않는다 — GitHub과 같은 동작 (리뷰 N2)."""
    cr_old = gh_review(OLD, state="CHANGES_REQUESTED", author="r1")
    gate = evaluate(HEAD, [cr_old], [review(HEAD), result("✅", HEAD)], 0)
    assert gate.state == "failure"


def test_dismissed_clears_old_changes_request():
    cr_old = gh_review(OLD, state="CHANGES_REQUESTED", author="r1")
    dismissed = gh_review(OLD, state="DISMISSED", author="r1")
    gate = evaluate(HEAD, [cr_old, dismissed], [review(HEAD), result("✅", HEAD)], 0)
    assert gate.state == "success"


def test_codex_review_format_counts_as_review():
    """리뷰봇(Codex) 형식도 자동 리뷰로 인식 (PR #1에서 놓쳤던 형식)."""
    gate = evaluate(HEAD, [], [codex(HEAD), result("✅", HEAD)], 0)
    assert gate.state == "success"
    assert evaluate(HEAD, [], [codex(OLD), result("✅", HEAD)], 0).state == "pending"


def test_review_after_ok_result_invalidates_it():
    """✅ 결과 뒤에 새 리뷰가 오면 그 지적을 처리하기 전이므로 pending (PR #1 실제 사례)."""
    comments = [
        review(HEAD, "2026-10-01T05:45:14Z"),
        result("✅", HEAD, "2026-10-01T05:46:08Z"),
        codex(HEAD, "2026-10-01T05:51:51Z"),
    ]
    gate = evaluate(HEAD, [], comments, 0)
    assert gate.state == "pending"
    assert "결과 코멘트 이후 새 리뷰" in gate.description


def test_result_reposted_after_new_review_passes():
    comments = [
        codex(HEAD, "2026-10-01T05:51:51Z"),
        result("✅", HEAD, "2026-10-01T06:10:00Z"),
    ]
    assert evaluate(HEAD, [], comments, 0).state == "success"


def test_github_review_after_result_invalidates_it():
    reviews = [gh_review(HEAD) | {"at": "2026-10-01T06:00:00Z"}]
    comments = [review(HEAD, "2026-10-01T05:00:00Z"), result("✅", HEAD, "2026-10-01T05:30:00Z")]
    assert evaluate(HEAD, reviews, comments, 0).state == "pending"


def test_review_in_same_second_after_result_invalidates_it():
    """같은 초에 결과 → 리뷰 순으로 올라와도 리뷰가 '이후'로 잡힌다 (리뷰 T1)."""
    same = "2026-10-01T06:00:00Z"
    comments = [review(HEAD, "2026-10-01T05:00:00Z"), result("✅", HEAD, same), codex(HEAD, same)]
    assert evaluate(HEAD, [], comments, 0).state == "pending"


def test_github_review_in_same_second_as_result_is_treated_as_after():
    same = "2026-10-01T06:00:00Z"
    reviews = [gh_review(HEAD) | {"at": same}]
    comments = [review(HEAD, "2026-10-01T05:00:00Z"), result("✅", HEAD, same)]
    assert evaluate(HEAD, reviews, comments, 0).state == "pending"


def test_review_marker_needs_sha_boundary():
    """`커밋 addedfeature`의 앞 7자를 SHA로 읽지 않는다 (리뷰 M1)."""
    head = "addedfe" + "0" * 33
    body = {"body": "## 🤖 자동 리뷰 — 커밋 addedfeature 반영", "at": ""}
    assert evaluate(head, [], [body, result("✅", head)], 0).state == "pending"


def test_review_edited_after_result_invalidates_it():
    """리뷰봇이 ✅ 결과 뒤에 기존 리뷰를 고쳐 새 지적을 넣으면 pending (리뷰봇 88648fa 리뷰)."""
    edited = codex(HEAD, "2026-10-01T14:00:00Z") | {"updated": "2026-10-01T14:20:00Z"}
    comments = [edited, result("✅", HEAD, "2026-10-01T14:10:00Z")]
    gate = evaluate(HEAD, [], comments, 0)
    assert gate.state == "pending"
    assert "결과 이후 수정됨" in "\n".join(gate.lines)


def test_review_edited_before_result_is_fine():
    edited = codex(HEAD, "2026-10-01T14:00:00Z") | {"updated": "2026-10-01T14:05:00Z"}
    comments = [edited, result("✅", HEAD, "2026-10-01T14:10:00Z")]
    assert evaluate(HEAD, [], comments, 0).state == "success"


def test_edited_result_comment_is_not_accepted():
    """❌ 결과를 ✅로 고쳐 쓴 코멘트는 인정하지 않는다 — 결과는 새로 올린다."""
    tampered = result("✅", HEAD, "2026-10-01T14:10:00Z") | {"updated": "2026-10-01T14:30:00Z"}
    gate = evaluate(HEAD, [], [review(HEAD, "2026-10-01T14:00:00Z"), tampered], 0)
    assert gate.state == "pending"
    assert "새 결과 코멘트를 올리세요" in gate.description


def test_edited_latest_result_does_not_revive_earlier_ok():
    """✅(T2) → ❌(T3, 나중에 수정)이면 앞선 ✅가 되살아나면 안 된다 (리뷰 N1)."""
    comments = [
        review(HEAD, "2026-10-01T14:00:00Z"),
        result("✅", HEAD, "2026-10-01T14:10:00Z"),
        result("❌", HEAD, "2026-10-01T14:20:00Z") | {"updated": "2026-10-01T14:25:00Z"},
    ]
    assert evaluate(HEAD, [], comments, 0).state == "pending"


def test_new_result_after_edited_one_counts():
    comments = [
        review(HEAD, "2026-10-01T14:00:00Z"),
        result("❌", HEAD, "2026-10-01T14:10:00Z") | {"updated": "2026-10-01T14:15:00Z"},
        result("✅", HEAD, "2026-10-01T14:20:00Z"),
    ]
    assert evaluate(HEAD, [], comments, 0).state == "success"


def test_changes_requested_beats_edited_result():
    """결과 코멘트가 수정됐어도 변경 요청이 남아 있으면 원인을 가리지 않고 failure로 보인다 (이슈 #3 O1)."""
    tampered = result("✅", HEAD, "2026-10-01T14:10:00Z") | {"updated": "2026-10-01T14:30:00Z"}
    reviews = [gh_review(HEAD, state="CHANGES_REQUESTED", author="bot")]
    gate = evaluate(HEAD, reviews, [review(HEAD, "2026-10-01T14:00:00Z"), tampered], 0)
    assert gate.state == "failure"
    assert "변경 요청" in gate.description


def test_unresolved_threads_beat_edited_result():
    tampered = result("✅", HEAD, "2026-10-01T14:10:00Z") | {"updated": "2026-10-01T14:30:00Z"}
    gate = evaluate(HEAD, [], [review(HEAD, "2026-10-01T14:00:00Z"), tampered], 2)
    assert gate.state == "failure"
    assert "2개" in gate.description


def by(association: str | None, item: dict) -> dict:
    return {**item, "association": association}


def test_split_trusted_keeps_only_collaborators():
    items = [
        by("OWNER", review(HEAD)),
        by("MEMBER", review(HEAD)),
        by("COLLABORATOR", review(HEAD)),
        by("CONTRIBUTOR", review(HEAD)),
        by("NONE", review(HEAD)),
        by("FIRST_TIME_CONTRIBUTOR", review(HEAD)),
        review(HEAD),  # association 없음 — 신뢰하지 않는다
    ]
    kept, dropped = split_trusted(items)
    assert [i["association"] for i in kept] == ["OWNER", "MEMBER", "COLLABORATOR"]
    assert dropped == 4


def test_outsider_result_comment_cannot_pass_the_gate():
    # 협업자의 리뷰만 있고, ✅ 결과 코멘트는 외부 사용자가 올렸다 → 결과 없음으로 본다
    comments, _ = split_trusted([by("OWNER", review(HEAD)), by("NONE", result("✅", HEAD))])
    gate = evaluate(HEAD, [], comments, 0)
    assert gate.state == "pending"
    assert "검증 결과 코멘트 없음" in gate.description


def test_outsider_review_marker_does_not_count_as_review():
    comments, _ = split_trusted([by("NONE", review(HEAD)), by("OWNER", result("✅", HEAD))])
    assert evaluate(HEAD, [], comments, 0).state == "pending"


def test_outsider_fail_result_cannot_block_the_gate():
    comments, _ = split_trusted(
        [by("OWNER", review(HEAD)), by("OWNER", result("✅", HEAD)), by("NONE", result("❌", HEAD))]
    )
    assert evaluate(HEAD, [], comments, 0).state == "success"


def test_outsider_changes_requested_review_is_ignored():
    reviews, dropped = split_trusted(
        [by("NONE", gh_review(HEAD, state="CHANGES_REQUESTED", body="막기", author="stranger"))]
    )
    gate = evaluate(HEAD, reviews, [by("OWNER", review(HEAD)), by("OWNER", result("✅", HEAD))], 0)
    assert dropped == 1
    assert gate.state == "success"


def test_collaborator_changes_requested_still_blocks():
    reviews, _ = split_trusted(
        [by("COLLABORATOR", gh_review(HEAD, state="CHANGES_REQUESTED", author="mate"))]
    )
    gate = evaluate(HEAD, reviews, [by("OWNER", review(HEAD)), by("OWNER", result("✅", HEAD))], 0)
    assert gate.state == "failure"


# --- fetch → main 연결 (가짜 gh) ---------------------------------------------------
def rest_comment(body: str, association: str | None, n: int, author: str = "u") -> dict:
    return {
        "id": n,
        "body": body,
        "user": {"login": author},
        "created_at": f"2026-10-21T00:00:{n:02d}Z",
        "updated_at": f"2026-10-21T00:00:{n:02d}Z",
        "author_association": association,
    }


def rest_review(state: str, body: str, association: str | None, author: str) -> dict:
    return {
        "commit_id": HEAD,
        "user": {"login": author},
        "state": state,
        "body": body,
        "submitted_at": "2026-10-21T00:00:30Z",
        "author_association": association,
    }


def thread(resolved: bool, association: str | None) -> dict:
    return {"isResolved": resolved, "comments": {"nodes": [{"authorAssociation": association}]}}


def run_main(monkeypatch, capsys, comments, reviews, threads):
    def fake_gh(*args):
        if args[:2] == ("api", "graphql"):
            query = next(a for a in args if a.startswith("query="))
            assert (
                "authorAssociation" in query
            )  # 쿼리에서 작성자 권한이 빠지면 스레드 필터가 무력해진다
            data = {"repository": {"pullRequest": {"reviewThreads": {"nodes": threads}}}}
            return json.dumps([{"data": data}])
        path = args[1]
        if path.endswith("/pulls/7"):
            return json.dumps({"state": "open", "head": {"sha": HEAD}})
        if "/pulls/7/reviews" in path:
            return json.dumps([reviews])
        if "/issues/7/comments" in path:
            return json.dumps([comments])
        raise AssertionError(f"예상 밖 호출: {args}")

    monkeypatch.setattr(mg, "gh", fake_gh)
    monkeypatch.setenv("REPO", "o/r")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.delenv("POST_STATUS", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert mg.main() == 0
    return capsys.readouterr().out


def owner_pair() -> list[dict]:
    return [
        rest_comment(review(HEAD)["body"], "OWNER", 1, "owner"),
        rest_comment(result("✅", HEAD)["body"], "OWNER", 2, "owner"),
    ]


def test_main_unknown_thread_starter_is_counted_not_ignored(monkeypatch, capsys):
    # 첫 코멘트 정보가 없는 미해결 스레드는 작성자를 알 수 없으므로 막는 쪽(failure)으로 센다
    out = run_main(monkeypatch, capsys, owner_pair(), [], [{"isResolved": False}])
    assert "`merge-gate`): failure" in out


def test_main_ignores_outsider_noise_end_to_end(monkeypatch, capsys):
    comments = owner_pair() + [rest_comment(result("❌", HEAD)["body"], "NONE", 3, "stranger")]
    reviews = [rest_review("CHANGES_REQUESTED", "막는다", "CONTRIBUTOR", "stranger")]
    out = run_main(monkeypatch, capsys, comments, reviews, [thread(False, "NONE")])
    assert "`merge-gate`): success" in out
    assert "협업자가 아닌 작성자의 리뷰 1개·코멘트 1개·미해결 스레드 1개" in out


def test_main_outsider_only_result_stays_pending(monkeypatch, capsys):
    comments = [
        rest_comment(review(HEAD)["body"], "OWNER", 1, "owner"),
        rest_comment(result("✅", HEAD)["body"], "NONE", 2, "stranger"),
    ]
    out = run_main(monkeypatch, capsys, comments, [], [])
    assert "`merge-gate`): pending" in out


def test_main_collaborator_unresolved_thread_still_fails(monkeypatch, capsys):
    out = run_main(monkeypatch, capsys, owner_pair(), [], [thread(False, "OWNER")])
    assert "`merge-gate`): failure" in out
    assert "미해결 리뷰 스레드 1개" in out


def test_main_collaborator_changes_requested_review_blocks(monkeypatch, capsys):
    reviews = [rest_review("CHANGES_REQUESTED", "고쳐 주세요", "COLLABORATOR", "mate")]
    out = run_main(monkeypatch, capsys, owner_pair(), reviews, [])
    assert "`merge-gate`): failure" in out
    assert "변경 요청 리뷰 남아 있음 (mate)" in out

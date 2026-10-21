"""병합 게이트 — docs/guides/MERGE_PROTOCOL.md의 리뷰 관련 게이트를 CI가 판정해 커밋 상태 `merge-gate`로 남긴다.

판정 (PR의 현재 head 커밋 기준):
  G-03       자동 리뷰가 현재 head 기준으로 있는가 (리뷰가 "누가" 썼는지 = G-02 출처는 판정하지 못한다)
             - GitHub 리뷰: review.commit.oid == head, 상태 COMMENTED/APPROVED, 본문 있음
               (인라인 답글이 만드는 빈 COMMENTED 리뷰·DISMISSED·재판정 트리거 리뷰는 세지 않는다)
             - 리뷰어의 마지막 상태가 CHANGES_REQUESTED면 failure (이전 커밋에서 남긴 것 포함)
             - 코멘트형 리뷰: 첫 줄의 SHA가 head와 일치
               `## 🤖 자동 리뷰 (head <SHA>)` (리뷰 에이전트) 또는
               `### 🤖 자동 리뷰 (Codex) — 커밋 <SHA>` (리뷰봇)
  G-05       미해결 리뷰 스레드가 0개인가 (스레드를 연 첫 코멘트가 협업자의 것인 것만 센다)
  결과 코멘트 현재 head에 대한 가장 최근 `## ✅/❌ 병합 전 검증 결과 (head <SHA>)`가 ✅이고,
             그 **뒤에** 현재 head에 대한 새 자동 리뷰가 없는가 (있으면 그 리뷰를 처리하기 전이므로 pending)

상태: 전부 충족 → success / ❌ 결과·미해결 스레드·변경 요청 → failure /
      리뷰 없음·결과 없음·결과 뒤 새 리뷰 → pending
작성자 제한: 저장소가 공개돼도 리뷰·결과·재판정 코멘트와 GitHub 리뷰는 **협업자(author_association이
OWNER·MEMBER·COLLABORATOR)가 쓴 것만** 센다. 그 밖의 작성자(외부 기여자·익명)가 남긴 "자동 리뷰"·"병합 전 검증
결과"·변경 요청은 판정에 쓰지 않는다 (공개 저장소에서 누구나 코멘트를 달 수 있어 게이트를 통과시키거나 막는 것을 방지).
G-04(지적을 제대로 처리했는가)·G-06(diff를 읽었는가)의 "내용"은 기계가 판정할 수 없다 —
그 판단은 결과 코멘트를 쓴 에이전트와 병합하는 사람의 몫이고, 이 게이트는 그 코멘트가 현재 head에
대해 ✅로 존재하는지까지만 강제한다.

환경변수: GH_TOKEN, REPO(owner/name), PR_NUMBER, POST_STATUS(=1이면 상태 게시)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass

CONTEXT = "merge-gate"
# 판정에 쓰는 작성자 권한 — 이 밖의 작성자가 남긴 리뷰·코멘트는 세지 않는다 (author_association 값이 없으면 제외)
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
# 첫 줄에 SHA는 하나만 쓴다 (MERGE_PROTOCOL 1절). 끝 경계: `커밋 addedfeature` 같은 영단어를 SHA로 읽지 않게
REVIEW_MARKER = re.compile(
    r"^#{2,3}\s*🤖\s*자동 리뷰.*?(?:\(head|커밋)\s*`?([0-9a-f]{7,40})(?![0-9a-zA-Z])`?"
)
RESULT_MARKER = re.compile(r"^##\s*(✅|❌)\s*병합 전 검증 결과\s*\(head\s*`?([0-9a-f]{7,40})`?\)")
# 재판정만을 위해 제출하는 리뷰 (MERGE_PROTOCOL 2-1절) — 리뷰로 세지 않는다
RETRIGGER_MARKER = "merge-gate 재판정"


@dataclass
class Gate:
    state: str  # success | failure | pending
    description: str
    lines: list[str]


def first_line(body: str) -> str:
    return body.strip().split("\n", 1)[0].strip()


def split_trusted(items: list[dict]) -> tuple[list[dict], int]:
    """협업자가 쓴 항목만 남기고, 제외한 개수를 함께 돌려준다. `association`이 없으면 신뢰하지 않는다."""
    kept = [i for i in items if i.get("association") in TRUSTED_ASSOCIATIONS]
    return kept, len(items) - len(kept)


def thread_starter(node: dict) -> str | None:
    """리뷰 스레드를 연 첫 코멘트 작성자의 author_association (없으면 None)."""
    first = (node.get("comments") or {}).get("nodes") or []
    return first[0].get("authorAssociation") if first else None


def same_commit(short: str, head: str) -> bool:
    return len(short) >= 7 and head.startswith(short)


def evaluate(head: str, reviews: list[dict], comments: list[dict], unresolved: int) -> Gate:
    """reviews: [{"commit", "state", "body", "author", "at"}],
    comments: [{"body", "author", "at", "updated"}] — "at"은 작성 시각, "updated"는 마지막 수정 시각.
    (작성자 권한 `association`은 여기서 보지 않는다 — 호출하는 쪽이 `split_trusted`로 먼저 거른다.)

    둘 다 시간순이고 시각은 ISO 8601(초 단위).
    선후 판정: 코멘트끼리는 목록 순서(같은 초도 구분), GitHub 리뷰와 결과 코멘트는 시각으로 비교하되
    같은 초면 보수적으로 "결과 이후"로 본다.
    수정: 결과 뒤에 **수정된** 리뷰 코멘트는 새 리뷰로 본다. 결과는 **목록의 마지막 결과 코멘트만**
    기준으로 하고, 그것이 수정됐으면 pending이다 — ❌를 ✅로 고쳐 쓰거나, 수정을 핑계로 앞선 ✅를
    되살리는 것을 막는다. 결과는 새 코멘트로 다시 올린다.
    """
    on_head = [r for r in reviews if r.get("commit") == head]
    # 리뷰어별 마지막 상태는 커밋과 무관하게 전체 이력으로 본다 — push해도 변경 요청은 풀리지 않는다
    # (GitHub과 같은 동작). COMMENTED는 이전 상태를 지우지 않고, APPROVED·DISMISSED는 지운다.
    latest_state: dict[str, str] = {}
    for r in reviews:
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"):
            if r.get("state") != "COMMENTED" or r.get("author") not in latest_state:
                latest_state[r.get("author") or "?"] = r["state"]
    changes_requested = sorted(a for a, st in latest_state.items() if st == "CHANGES_REQUESTED")

    gh_reviews = [
        (r.get("at") or "", f"GitHub 리뷰 ({r.get('author', '?')})")
        for r in on_head
        if r.get("state") in ("COMMENTED", "APPROVED")
        and (r.get("body") or "").strip()
        and not first_line(r.get("body") or "").startswith(RETRIGGER_MARKER)
    ]
    comment_reviews: list[tuple[int, str, str]] = []  # (목록 순서, 수정 시각 또는 "", 출처)
    last_result_edited = False
    result, result_idx, result_at = None, -1, ""  # 현재 head에 대한 가장 최근 결과
    for idx, c in enumerate(comments):
        line = first_line(c["body"])
        created, updated = c.get("at") or "", c.get("updated") or ""
        edited = updated if updated > created else ""
        if (m := REVIEW_MARKER.match(line)) and same_commit(m.group(1), head):
            comment_reviews.append((idx, edited, f"리뷰 코멘트 ({c.get('author', '?')})"))
        elif (m := RESULT_MARKER.match(line)) and same_commit(m.group(2), head):
            # 마지막 결과가 기준 — 수정된 결과를 건너뛰면 앞선 ✅가 되살아나므로 건너뛰지 않는다
            result, result_idx, result_at = m.group(1), idx, created
            last_result_edited = bool(edited)
    review_sources = [src for _, src in gh_reviews] + [src for _, _, src in comment_reviews]
    # 결과 코멘트보다 나중에 올라오거나 나중에 수정된 리뷰 — 그 지적을 처리하기 전에 쓴 결과이므로 무효
    reviews_after_result = (
        [
            src + (" — 결과 이후 수정됨" if idx < result_idx else "")
            for idx, edited, src in comment_reviews
            if idx > result_idx or (edited and result_at and edited >= result_at)
        ]
        + [src for at, src in gh_reviews if at and result_at and at >= result_at]
        if result
        else []
    )

    short = head[:7]
    lines = [
        f"- head `{short}`",
        f"- 자동 리뷰 (G-03): {', '.join(review_sources) if review_sources else '없음'}",
        f"- 미해결 리뷰 스레드 (G-05): {unresolved}개",
        f"- 병합 전 검증 결과 코멘트: {result or '없음'}{' (수정됨 — 무효)' if last_result_edited else ''}",
        f"- 변경 요청(CHANGES_REQUESTED): {', '.join(changes_requested) or '없음'}",
        f"- 결과 코멘트 이후 새 리뷰: {', '.join(reviews_after_result) or '없음'}",
    ]

    # 변경 요청·미해결 스레드는 결과 코멘트와 무관한 실패 원인이므로 수정된 결과보다 먼저 보여 준다
    if changes_requested:
        return Gate(
            "failure", f"{short}: 변경 요청 리뷰 남아 있음 ({', '.join(changes_requested)})", lines
        )
    if unresolved:
        return Gate("failure", f"{short}: 미해결 리뷰 스레드 {unresolved}개", lines)
    if last_result_edited:
        return Gate(
            "pending",
            f"{short}: 마지막 결과 코멘트가 수정됨 — 고치지 말고 새 결과 코멘트를 올리세요",
            lines,
        )
    if result == "❌":
        return Gate("failure", f"{short}: 병합 전 검증 결과 ❌", lines)
    if not review_sources:
        return Gate(
            "pending", f"{short}: 현재 head 기준 자동 리뷰 없음 (MERGE_PROTOCOL 1절)", lines
        )
    if result is None:
        return Gate(
            "pending", f"{short}: 병합 전 검증 결과 코멘트 없음 (MERGE_PROTOCOL 4절)", lines
        )
    if reviews_after_result:
        return Gate(
            "pending", f"{short}: 결과 코멘트 이후 새 리뷰 — 지적 처리 후 결과 재게시 필요", lines
        )
    return Gate("success", f"{short}: 자동 리뷰·스레드·검증 결과 확인", lines)


# --- GitHub 조회 ------------------------------------------------------------------
def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def gh_pages(path: str) -> list[dict]:
    """REST 목록을 끝까지 받는다 (100개 넘어도 누락 없음)."""
    pages = json.loads(gh("api", path, "--paginate", "--slurp"))
    return [item for page in pages for item in page]


def fetch(repo: str, number: str) -> tuple[str, str, list[dict], list[dict], int]:
    pr = json.loads(gh("api", f"repos/{repo}/pulls/{number}"))
    reviews = [
        {
            "commit": r.get("commit_id"),
            "author": (r.get("user") or {}).get("login"),
            "state": r.get("state"),
            "body": r.get("body") or "",
            "at": r.get("submitted_at") or "",
            "association": r.get("author_association"),
        }
        for r in gh_pages(f"repos/{repo}/pulls/{number}/reviews?per_page=100")
    ]
    # gh pr view의 코멘트에는 수정 시각이 없어 REST로 받는다. 작성 순서로 안정 정렬해 둔다
    # (API 기본 순서가 생성 순이지만, 판정이 순서에 의존하므로 한 번 더 보장한다).
    raw = gh_pages(f"repos/{repo}/issues/{number}/comments?per_page=100")
    comments = [
        {
            "body": c.get("body") or "",
            "author": (c.get("user") or {}).get("login"),
            "at": c.get("created_at") or "",
            "updated": c.get("updated_at") or "",
            "association": c.get("author_association"),
        }
        for c in sorted(raw, key=lambda c: (c.get("created_at") or "", c.get("id") or 0))
    ]
    owner, name = repo.split("/")
    query = (
        "query($o:String!,$r:String!,$n:Int!,$endCursor:String){repository(owner:$o,name:$r){"
        "pullRequest(number:$n){reviewThreads(first:100,after:$endCursor){"
        "nodes{isResolved comments(first:1){nodes{authorAssociation}}} "
        "pageInfo{hasNextPage endCursor}}}}}"
    )
    pages = json.loads(
        gh(
            "api",
            "graphql",
            "--paginate",
            "--slurp",
            "-F",
            f"o={owner}",
            "-F",
            f"r={name}",
            "-F",
            f"n={number}",
            "-f",
            f"query={query}",
        )  # fmt: skip
    )
    # 미해결 스레드도 첫 코멘트를 쓴 사람이 협업자인 것만 센다 — 외부인이 인라인 코멘트로 게이트를 막지 못하게
    unresolved = sum(
        1
        for p in pages
        for n in p["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
        if not n["isResolved"] and thread_starter(n) in TRUSTED_ASSOCIATIONS
    )
    state = "OPEN" if pr["state"] == "open" else pr["state"].upper()
    return state, pr["head"]["sha"], reviews, comments, unresolved


def main() -> int:
    repo, number = os.environ["REPO"], os.environ["PR_NUMBER"]
    state, head, reviews, comments, unresolved = fetch(repo, number)
    if state != "OPEN":
        print(f"PR #{number}은 {state} — 평가하지 않음")
        return 0

    reviews, dropped_reviews = split_trusted(reviews)
    comments, dropped_comments = split_trusted(comments)
    gate = evaluate(head, reviews, comments, unresolved)
    if dropped_reviews or dropped_comments:
        gate.lines.append(
            f"- 협업자가 아닌 작성자의 리뷰 {dropped_reviews}개·코멘트 {dropped_comments}개는 판정에서 뺌"
            "(판정 문구가 들었는지와 무관하게 센 개수)"
        )
    summary = (
        f"## 병합 게이트 (`{CONTEXT}`): {gate.state}\n\n{gate.description}\n\n"
        + "\n".join(gate.lines)
        + "\n"
    )
    print(summary)
    if out := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(out, "a", encoding="utf-8") as f:
            f.write(summary)

    if os.environ.get("POST_STATUS") == "1":
        args = [
            "api", "-X", "POST", f"repos/{repo}/statuses/{head}",
            "-f", f"state={gate.state}",
            "-f", f"context={CONTEXT}",
            "-f", f"description={gate.description[:140]}",
        ]  # fmt: skip
        if run_id := os.environ.get("GITHUB_RUN_ID"):
            server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
            args += ["-f", f"target_url={server}/{repo}/actions/runs/{run_id}"]
        gh(*args)
    # 상태(pending/failure)로 병합을 막는다. 워크플로 자체는 성공으로 끝내 실패 알림이 반복되지 않게 한다.
    return 0


if __name__ == "__main__":
    sys.exit(main())

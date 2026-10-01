"""병합 게이트 — docs/MERGE_PROTOCOL.md의 리뷰 관련 게이트를 CI가 판정해 커밋 상태 `merge-gate`로 남긴다.

판정 (PR의 현재 head 커밋 기준):
  G-02·G-03  자동 리뷰가 현재 head 기준으로 있는가
             - GitHub 리뷰: review.commit.oid == head, 상태 COMMENTED/APPROVED, 본문 있음
               (인라인 답글이 만드는 빈 COMMENTED 리뷰·DISMISSED·재판정 트리거 리뷰는 세지 않는다)
             - 현재 head에 CHANGES_REQUESTED가 남아 있으면 failure
             - 코멘트형 리뷰: 첫 줄 `## 🤖 자동 리뷰 (head <SHA>)`의 SHA가 head와 일치
  G-05       미해결 리뷰 스레드가 0개인가
  결과 코멘트 현재 head에 대한 가장 최근 `## ✅/❌ 병합 전 검증 결과 (head <SHA>)`가 ✅인가

상태: 전부 충족 → success / ❌ 결과 코멘트·미해결 스레드 → failure / 리뷰·결과 코멘트 없음 → pending
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
REVIEW_MARKER = re.compile(r"^##\s*🤖\s*자동 리뷰\s*\(head\s*`?([0-9a-f]{7,40})`?\)")
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


def same_commit(short: str, head: str) -> bool:
    return len(short) >= 7 and head.startswith(short)


def evaluate(head: str, reviews: list[dict], comments: list[dict], unresolved: int) -> Gate:
    """reviews: [{"commit", "state", "body", "author"}], comments: [{"body", "author"}] (둘 다 시간순)."""
    on_head = [r for r in reviews if r.get("commit") == head]
    latest_state: dict[str, str] = {}  # 리뷰어별 현재 head 위의 마지막 상태
    for r in on_head:
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"):
            if r.get("state") != "COMMENTED" or r.get("author") not in latest_state:
                latest_state[r.get("author") or "?"] = r["state"]
    changes_requested = sorted(a for a, st in latest_state.items() if st == "CHANGES_REQUESTED")

    review_sources = [
        f"GitHub 리뷰 ({r.get('author', '?')})"
        for r in on_head
        if r.get("state") in ("COMMENTED", "APPROVED")
        and (r.get("body") or "").strip()
        and not first_line(r.get("body") or "").startswith(RETRIGGER_MARKER)
    ]
    for c in comments:
        m = REVIEW_MARKER.match(first_line(c["body"]))
        if m and same_commit(m.group(1), head):
            review_sources.append(f"리뷰 코멘트 ({c.get('author', '?')})")

    result = None  # 현재 head에 대한 가장 최근 결과
    for c in comments:
        m = RESULT_MARKER.match(first_line(c["body"]))
        if m and same_commit(m.group(2), head):
            result = m.group(1)

    short = head[:7]
    lines = [
        f"- head `{short}`",
        f"- 자동 리뷰 (G-02·G-03): {', '.join(review_sources) if review_sources else '없음'}",
        f"- 미해결 리뷰 스레드 (G-05): {unresolved}개",
        f"- 병합 전 검증 결과 코멘트: {result or '없음'}",
        f"- 변경 요청(CHANGES_REQUESTED): {', '.join(changes_requested) or '없음'}",
    ]

    if changes_requested:
        return Gate(
            "failure", f"{short}: 변경 요청 리뷰 남아 있음 ({', '.join(changes_requested)})", lines
        )
    if result == "❌":
        return Gate("failure", f"{short}: 병합 전 검증 결과 ❌", lines)
    if unresolved:
        return Gate("failure", f"{short}: 미해결 리뷰 스레드 {unresolved}개", lines)
    if not review_sources:
        return Gate(
            "pending", f"{short}: 현재 head 기준 자동 리뷰 없음 (MERGE_PROTOCOL 1절)", lines
        )
    if result is None:
        return Gate(
            "pending", f"{short}: 병합 전 검증 결과 코멘트 없음 (MERGE_PROTOCOL 4절)", lines
        )
    return Gate("success", f"{short}: 자동 리뷰·스레드·검증 결과 확인", lines)


# --- GitHub 조회 ------------------------------------------------------------------
def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def fetch(repo: str, number: str) -> tuple[str, str, list[dict], list[dict], int]:
    pr = json.loads(
        gh("pr", "view", number, "--repo", repo, "--json", "state,headRefOid,reviews,comments")
    )
    reviews = [
        {
            "commit": (r.get("commit") or {}).get("oid"),
            "author": (r.get("author") or {}).get("login"),
            "state": r.get("state"),
            "body": r.get("body") or "",
        }
        for r in pr["reviews"]
    ]
    comments = [
        {"body": c["body"], "author": (c.get("author") or {}).get("login")} for c in pr["comments"]
    ]
    owner, name = repo.split("/")
    query = (
        "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){"
        "reviewThreads(first:100){nodes{isResolved}}}}}"
    )
    threads = json.loads(
        gh(
            "api",
            "graphql",
            "-F",
            f"o={owner}",
            "-F",
            f"r={name}",
            "-F",
            f"n={number}",
            "-f",
            f"query={query}",
        )
    )
    nodes = threads["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    unresolved = sum(1 for n in nodes if not n["isResolved"])
    return pr["state"], pr["headRefOid"], reviews, comments, unresolved


def main() -> int:
    repo, number = os.environ["REPO"], os.environ["PR_NUMBER"]
    state, head, reviews, comments, unresolved = fetch(repo, number)
    if state != "OPEN":
        print(f"PR #{number}은 {state} — 평가하지 않음")
        return 0

    gate = evaluate(head, reviews, comments, unresolved)
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

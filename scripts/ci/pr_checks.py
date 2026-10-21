"""PR 내용 상세 검증 — docs/guides/MERGE_PROTOCOL.md 게이트 중 기계로 판정할 수 있는 것을 CI에서 돌린다.

검사 (실패 시 exit 1):
  principles   G-07  코드에 판정 필드·판정 문구가 새로 들어왔는가
  secrets      G-07  PR의 커밋들이 추가한 줄에 비밀값 패턴·.env 파일이 있는가 (중간 커밋 포함)
  rag-evidence G-08  RAG 코드를 바꿨는데 PR 본문 "검증 방법"에 before → after 수치가 없는가
  pr-body      -     PR 본문 필수 항목(변경 요약·변경 유형·관련 이슈)이 비었는가
  pr-title     -     PR 제목이 `<type>: <대문자로 시작하지 않는 설명>`인가 (pr-title-check와 같은 규칙 — 본문만 고칠 때
                     pr-title-check는 건너뛰므로, 실패한 제목이 '건너뜀=통과'로 덮이지 않게 여기서도 본다)
  type-lists   -     브랜치·커밋 type 목록이 여러 파일에서 서로 같은가
  md-links     -     문서의 상대 경로 링크가 실제 파일을 가리키는가
  agents-import -    CLAUDE.md가 AGENTS.md를 불러오는가

환경변수: BASE_SHA, HEAD_SHA, PR_BODY, PR_TITLE (없으면 diff·본문·제목 검사는 건너뛴다)
로컬 실행: BASE_SHA=$(git merge-base origin/main HEAD) HEAD_SHA=HEAD python3 scripts/ci/pr_checks.py
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- 서비스 원칙 (AGENTS.md 2절) -------------------------------------------------
# 단어 경계 없이·대소문자 무시: applies_to, verdict_label, isApplicable, VERDICT 등 변형까지 잡는다
PRINCIPLE_PATTERN = re.compile(
    r"applies|verdict|is_?applicable|recall[_\s-]?required|적용\s*(됩니다|되지\s*않습니다|안\s*됩니다)"
    r"|리콜\s*대상(입니다|이\s*아닙니다)|원인은\s*이것입니다",
    re.IGNORECASE,
)
# 원칙을 "설명"하는 문서·테스트·CI 자체는 검사하지 않는다.
# .md 전체를 빼면 prompts/*.md 같은 프롬프트 파일이 빠지므로, docs/와 루트 문서만 뺀다.
DOC_EXEMPT = ("docs/*", "tests/*", "scripts/ci/*", ".claude/*", ".github/*")
# 정당한 사용(예: 영어 일반 문장)은 그 줄에 표시를 달아 통과시킨다
PRINCIPLE_OPT_OUT = "principle-ok:"

# --- 비밀값 ---------------------------------------------------------------------
SECRET_PATTERNS = {
    "개인키": re.compile(r"-----BEGIN ([A-Z]+ )?PRIVATE KEY-----"),
    "OpenAI 키": re.compile(r"\bsk-(proj-)?[A-Za-z0-9_-]{20,}"),
    "Anthropic 키": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "AWS 액세스 키": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub 토큰": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack 토큰": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
}

# --- RAG 품질 근거 ----------------------------------------------------------------
DEFAULT_RAG_PATHS = [
    "*rag/*", "*rag_*", "*_rag.*", "*retriev*", "*prompt*", "*chunk*", "*embed*", "*eval/*", "*eval_*",
]  # fmt: skip
# 한 줄 안에 "지표 이름 + 숫자 → 숫자"가 있어야 근거로 본다 — `Python 3.11 → 3.12` 같은 줄은 인정하지 않는다
METRIC_PATTERN = re.compile(
    r"ndcg|hit@|recall|mrr|map@|precision|faithfulness|f1|rouge|bleu|accuracy|judge"
    r"|정확도|적중률|근거율|재현율|정밀도|충실도",
    re.IGNORECASE,
)
EVIDENCE_PATTERN = re.compile(r"\d.*(→|->).*\d")
RAG_SKIP_MARKER = re.compile(r"\[skip-rag-evidence:\s*\S.*\]")
CONFIG_PATH = Path(__file__).with_name("pr_verify.toml")

BRANCH_TYPES_SOURCES = {
    "scripts/check-branch.sh": r'PATTERN="\^\(([a-z|]+)\)/',
    "scripts/check-commit-msg.sh": r'PATTERN="\^\(([a-z|]+)\)\(',
    ".github/workflows/branch-name-check.yml": r'PATTERN="\^\(([a-z|]+)\)/',
}


@dataclass
class Result:
    name: str
    errors: list[str] = field(default_factory=list)
    skipped: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


# --- git 헬퍼 ---------------------------------------------------------------------
def git(*args: str) -> str:
    # quotepath=false: 한글 파일명(docs/기획.md 등)을 이스케이프하지 않고 그대로 받는다
    cmd = ["git", "-c", "core.quotepath=false", *args]
    out = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
    return out.stdout.decode("utf-8", errors="replace")  # 비-UTF8 텍스트 diff에서 멈추지 않게


def changed_files(base: str, head: str) -> list[str]:
    out = git("diff", "--name-only", "--diff-filter=ACMR", f"{base}...{head}")
    return [line for line in out.splitlines() if line]


Added = list[tuple[str, str, int, str]]  # (커밋 또는 "", 경로, 새 파일 기준 줄 번호, 내용)


DIFF_ARGS = (
    "-M",
    "--unified=0",
    "--no-color",
    "--no-ext-diff",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)


GIT_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def unquote_git_path(target: str) -> str:
    """git이 `"`·`\\`·제어문자가 든 경로를 감싸는 C 스타일 인용(`"b/a\\"b.py"`)을 푼다."""
    if not (len(target) >= 2 and target[0] == target[-1] == '"'):
        return target
    raw, out, i = target[1:-1], bytearray(), 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            octal = raw[i + 1 : i + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(int(octal, 8))  # \\NNN 8진수 바이트
                i += 4
                continue
            if nxt in GIT_ESCAPES:
                out.append(GIT_ESCAPES[nxt])
                i += 2
                continue
        out += ch.encode("utf-8")
        i += 1
    return out.decode("utf-8", errors="replace")


def parse_patch(patch: str) -> Added:
    """git diff/log -p --unified=0 출력에서 추가된 줄만 뽑는다. `commit:<sha>` 줄로 커밋을 구분한다.

    파일 헤더(`+++ b/<경로>`)는 `diff --git` 뒤, 첫 `@@` 전에서만 읽는다. hunk 안에서는 `+`로 시작하는
    줄을 전부 내용으로 본다 — 내용이 `++ x`인 추가 줄(`+++ x`)을 헤더로 오인하면 그 뒤가 검사에서 빠진다.
    --unified=0이라 hunk 안의 접두어 없는 줄은 `diff --git`·`commit:` 같은 구조 줄뿐이다.
    """
    result: Added = []
    commit, path, lineno, in_hunk = "", None, 0, False
    for line in patch.splitlines():
        if line.startswith("commit:"):
            commit, path, in_hunk = line[len("commit:") :].strip(), None, False
        elif line.startswith("diff --git "):
            path, in_hunk = None, False
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno, in_hunk = (int(m.group(1)) if m else 0), True
        elif in_hunk:
            if line.startswith("+") and path is not None:
                result.append((commit, path, lineno, line[1:]))
                lineno += 1
        elif line.startswith("+++ "):
            # 공백이 든 경로는 끝에 탭이 붙고, 특수문자가 든 경로는 따옴표로 인용된다
            target = unquote_git_path(line[4:].rstrip("\t"))
            if target == "/dev/null":  # 삭제된 파일
                path = None
            else:
                # 형식을 못 읽어도 줄을 버리지 않는다 (fail-closed) — 원래 문자열을 경로로 쓴다
                path = target[2:] if target.startswith("b/") else target
    return result


def added_lines(base: str, head: str) -> Added:
    """PR 최종 diff의 추가 줄. -M: 이름만 바꾼 파일을 통째로 '추가'로 보지 않는다."""
    return parse_patch(git("diff", *DIFF_ARGS, "--diff-filter=ACMR", f"{base}...{head}"))


def history_added_lines(base: str, head: str) -> Added:
    """PR의 커밋 하나하나가 추가한 줄 — 중간에 넣었다 지운 비밀값도 잡는다."""
    return parse_patch(git("log", "-p", *DIFF_ARGS, "--format=commit:%H", f"{base}..{head}"))


def matches(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path.lower(), p.lower()) for p in patterns)


def is_doc(path: str) -> bool:
    """원칙을 설명하는 문서·테스트·CI 자체 — 루트의 *.md와 DOC_EXEMPT 경로."""
    return ("/" not in path and path.endswith(".md")) or matches(path, DOC_EXEMPT)


# --- 검사 -------------------------------------------------------------------------
def check_principles(added: Added) -> Result:
    r = Result("principles")
    for _, path, lineno, text in added:
        if not is_doc(path):
            if PRINCIPLE_PATTERN.search(text) and PRINCIPLE_OPT_OUT not in text:
                r.errors.append(
                    f"{path}:{lineno} 판정 필드·판정 문구 — AGENTS.md 2절 위반 "
                    f"(정당한 사용이면 줄에 `{PRINCIPLE_OPT_OUT} <이유>` 주석)"
                )
    return r


def check_secrets(paths: list[str], history: Added, final: Added | None = None) -> Result:
    """paths: 최종 diff의 파일, history: 커밋별 추가 줄, final: 최종 diff의 추가 줄.

    history만 보면 병합 커밋(충돌 해결)에서만 생긴 줄을 놓친다 — git log -p는 병합 커밋 diff를
    출력하지 않는다. 그래서 최종 diff도 함께 본다. 같은 줄은 한 번만 보고한다.
    """
    r = Result("secrets")
    for path in sorted(set(paths) | {p for _, p, _, _ in history}):
        name = Path(path).name
        if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
            r.errors.append(f"{path} — .env 파일은 커밋하지 않는다 (이력에 남았으면 키 폐기)")
    seen: set[tuple[str, str]] = set()
    for commit, path, lineno, text in [*history, *(final or [])]:
        if (path, text) in seen:
            continue
        seen.add((path, text))
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                where = f" (커밋 {commit[:7]})" if commit else ""
                r.errors.append(
                    f"{path}:{lineno} {label}로 보이는 값{where} — 지워도 이력에 남는다, 즉시 키 폐기"
                )
    return r


def section(body: str, title: str) -> str | None:
    """`## <title>` 아래 내용 (HTML 주석 제거). 섹션이 없으면 None."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    m = re.search(rf"^##\s*{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", body, flags=re.M | re.S)
    return m.group(1).strip() if m else None


def rag_paths() -> list[str]:
    if not CONFIG_PATH.exists():
        return DEFAULT_RAG_PATHS
    return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8")).get(
        "rag-paths", DEFAULT_RAG_PATHS
    )


def has_metric_evidence(text: str) -> bool:
    return any(
        METRIC_PATTERN.search(ln) and EVIDENCE_PATTERN.search(ln) for ln in text.splitlines()
    )


def check_rag_evidence(paths: list[str], body: str, patterns: list[str]) -> Result:
    r = Result("rag-evidence")
    touched = [p for p in paths if matches(p, patterns) and not is_doc(p)]
    if not touched:
        r.skipped = "RAG 코드 변경 없음"
        return r
    evidence = section(body, "검증 방법") or ""
    # skip 표시는 "검증 방법" 섹션 안에서만 인정한다 — 본문 아무 데나 적어 넘기지 못하게
    if RAG_SKIP_MARKER.search(evidence):
        r.skipped = "'## 검증 방법'에 skip-rag-evidence 사유 명시"
    elif not has_metric_evidence(evidence):
        r.errors.append(
            f"RAG 관련 파일 변경({', '.join(touched[:3])}{' 외' if len(touched) > 3 else ''}) — "
            "PR 본문 '## 검증 방법'에 지표 이름과 같은 평가셋 before → after 수치가 필요하다 "
            "(예: `nDCG@10 0.631 → 0.692 (평가셋 v2 102건)`, G-08)"
        )
    return r


def check_pr_body(body: str) -> Result:
    r = Result("pr-body")
    if not (section(body, "변경 요약") or ""):
        r.errors.append("PR 본문 '## 변경 요약'이 비어 있다")
    kinds = section(body, "변경 유형")
    if kinds is None:
        r.errors.append("PR 본문에 '## 변경 유형' 섹션이 없다 (PR 템플릿 사용)")
    elif not re.search(r"- \[[xX]\]", kinds):
        r.errors.append("PR 본문 '## 변경 유형'에 체크된 항목이 없다")
    if not (section(body, "관련 이슈") or ""):
        r.errors.append("PR 본문 '## 관련 이슈'가 비어 있다 (없으면 \"없음\")")
    return r


def check_pr_title(title: str, types: set[str]) -> Result:
    r = Result("pr-title")
    m = re.match(r"^([a-z]+)(\([^)]*\))?!?: (.+)$", title)
    if not m or m.group(1) not in types:
        r.errors.append(
            f"PR 제목이 `<type>: <설명>` 꼴이 아니거나 type이 허용 목록({' '.join(sorted(types))})에 없다: {title!r}"
        )
    # 설명 첫 글자 규칙 — 첫 글자 대문자(A-Z) 금지 규칙은 .github/workflows/pr-title-check.yml(subjectPattern), scripts/ci/pr_checks.py(check_pr_title), scripts/check-commit-msg.sh(PATTERN) 세 곳에 있다 — 바꿀 때 함께 고친다(#56). 설명 최소 길이는 다르다: yml·py는 2글자(`[^A-Z].+`), 커밋 훅은 1글자(`[^A-Z].*`)
    elif not re.match(r"^[^A-Z].+$", m.group(3)):
        r.errors.append(f"PR 제목의 설명은 대문자(A-Z)로 시작할 수 없다: {title!r}")
    return r


def type_lists() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path, pattern in BRANCH_TYPES_SOURCES.items():
        m = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"))
        found[path] = set(m.group(1).split("|")) if m else set()
    title = (ROOT / ".github/workflows/pr-title-check.yml").read_text(encoding="utf-8")
    m = re.search(r"types: \|-\n((?:[ \t]+[a-z]+\n)+)", title)
    found[".github/workflows/pr-title-check.yml"] = set(m.group(1).split()) if m else set()
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    found["CONTRIBUTING.md"] = set(re.findall(r"^\| `([a-z]+)/` \|", contributing, flags=re.M))
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    m = re.search(r"type: `([a-z ]+)`", agents)
    found["AGENTS.md"] = set(m.group(1).split()) if m else set()
    return found


def check_type_lists() -> Result:
    r = Result("type-lists")
    found = type_lists()
    reference = found["scripts/check-branch.sh"]
    for path, types in found.items():
        if not types:
            r.errors.append(
                f"{path} — type 목록을 찾지 못했다 (형식이 바뀌었으면 scripts/ci/pr_checks.py도 수정)"
            )
        elif types != reference:
            missing, extra = sorted(reference - types), sorted(types - reference)
            r.errors.append(
                f"{path} — scripts/check-branch.sh와 다름 (빠짐 {missing}, 추가 {extra})"
            )
    return r


def check_md_links() -> Result:
    r = Result("md-links")
    link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    for rel in git("ls-files", "*.md").splitlines():
        path = ROOT / rel
        in_code = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                in_code = not in_code
                continue
            if in_code:
                continue
            for target in link.findall(re.sub(r"`[^`]*`", "", line)):
                if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                    continue
                target = target.split("#", 1)[0]
                # /로 시작하면 저장소 루트 기준 (GitHub 렌더링 방식)
                resolved = (
                    ROOT / target.lstrip("/") if target.startswith("/") else path.parent / target
                )
                if target and not resolved.exists():
                    r.errors.append(f"{rel}:{lineno} 깨진 링크 → {target}")
    return r


def check_agents_import() -> Result:
    r = Result("agents-import")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    if not re.search(r"^@AGENTS\.md\s*$", claude, flags=re.M):
        r.errors.append(
            "CLAUDE.md:1 `@AGENTS.md` import 줄이 없다 — 규칙 원본은 AGENTS.md (DEC-005)"
        )
    return r


# --- 출력 -------------------------------------------------------------------------
def report(results: list[Result]) -> int:
    rows = ["| 검사 | 결과 | 내용 |", "|---|---|---|"]
    for res in results:
        if res.skipped:
            rows.append(f"| {res.name} | ⏭️ | {res.skipped} |")
        elif res.ok:
            rows.append(f"| {res.name} | ✅ | |")
        else:
            rows.append(f"| {res.name} | ❌ | {len(res.errors)}건 |")
        for err in res.errors:
            loc = re.match(r"^([^\s:]+):(\d+)", err)
            prefix = f"file={loc.group(1)},line={loc.group(2)}::" if loc else "::"
            print(f"::error {prefix}[{res.name}] {err}")
    summary = "## PR 상세 검증\n\n" + "\n".join(rows) + "\n"
    print(summary)
    if out := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(out, "a", encoding="utf-8") as f:
            f.write(summary)
    return 0 if all(res.ok for res in results) else 1


def main() -> int:
    base, head = os.environ.get("BASE_SHA"), os.environ.get("HEAD_SHA")
    body = os.environ.get("PR_BODY")
    results: list[Result] = []

    if base and head:
        paths = changed_files(base, head)
        final = added_lines(base, head)
        results += [
            check_principles(final),
            check_secrets(paths, history_added_lines(base, head), final),
        ]
        if body is not None:
            results.append(check_rag_evidence(paths, body, rag_paths()))
    else:
        results.append(Result("diff", skipped="BASE_SHA·HEAD_SHA 없음 — diff 검사 건너뜀"))

    if body is not None:
        results.append(check_pr_body(body))
    title = os.environ.get("PR_TITLE")
    if title is not None:
        results.append(check_pr_title(title, type_lists()[".github/workflows/pr-title-check.yml"]))
    results += [check_type_lists(), check_md_links(), check_agents_import()]
    return report(results)


if __name__ == "__main__":
    sys.exit(main())

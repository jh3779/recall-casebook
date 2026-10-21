"""docs/ 문서 이름 규칙 검사 — docs/guides/문서_이름_규칙.md의 기계로 확인할 수 있는 부분(DEC-083).

추적 파일(`git ls-files`)만 본다 — 로컬에만 있는 파일(.gitignore)은 규칙 밖이다.
`archive/`·`design-system/`·`images/`는 이 규칙의 대상이 아니다(문서_이름_규칙.md 1절·5절).
"""

import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_DIRS = {"product", "experiments", "guides", "labeling", "project"}  # 규칙이 적용되는 폴더
OTHER_DIRS = {"design-system", "archive", "images"}  # 규칙 밖(README 지도에는 있다)
# 한글·영문·숫자 단어를 밑줄로 잇는다 — 영문 약어 문서(PRD, MERGE_PROTOCOL)도 이 형식이다
NAME = re.compile(r"^[0-9A-Za-z가-힣]+(?:_[0-9A-Za-z가-힣]+)*\.md$")
# 날짜·판본·상태를 이름에 넣지 않는다(2절 5항)
BAD_PART = re.compile(
    r"(?:^|_)(?:v\d+|초안|최종|수정본|복사본|(?:19|20)\d{6})(?:_|$)", re.IGNORECASE
)
# 접두어는 정해진 폴더에만 둔다(3절 표)
PREFIX_DIR = {
    "기획_": "product",
    "계획_": "product",
    "실험_": "experiments",
    "프런트_": "experiments",
    "D파트_": "labeling",
}


def tracked_docs() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "docs"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    return [Path(p) for p in out.split("\0") if p]


def rule_docs() -> list[Path]:
    """규칙이 적용되는 문서 — docs/<DOC_DIRS>/ 아래 파일."""
    return [p for p in tracked_docs() if len(p.parts) > 2 and p.parts[1] in DOC_DIRS]


def test_docs_바로_아래에는_README만_있다():
    roots = [p.name for p in tracked_docs() if len(p.parts) == 2]
    assert roots == ["README.md"], (
        f"docs/ 바로 아래에는 README.md만 둔다(폴더를 고른다 — 문서_이름_규칙.md 1절): {roots}"
    )


def test_폴더는_정해진_것만_있다():
    dirs = {p.parts[1] for p in tracked_docs() if len(p.parts) > 2}
    assert dirs <= DOC_DIRS | OTHER_DIRS, (
        f"새 폴더는 DEC와 README 폴더 표가 먼저다: {sorted(dirs - DOC_DIRS - OTHER_DIRS)}"
    )


def test_규칙_폴더는_한_단계만_쓴다():
    deep = [str(p) for p in rule_docs() if len(p.parts) != 3]
    assert not deep, f"하위 폴더를 두지 않는다(문서_이름_규칙.md 1절): {deep}"


def test_파일_이름_형식():
    bad = [str(p) for p in rule_docs() if not NAME.match(p.name)]
    assert not bad, (
        f"<접두어>_<주제>.md — 밑줄로 잇고 공백·하이픈·괄호·점·대문자 확장자 금지(2절): {bad}"
    )


def test_한글_이름은_NFC다():
    bad = [str(p) for p in rule_docs() if unicodedata.normalize("NFC", p.name) != p.name]
    assert not bad, f"macOS 분해형(NFD) 이름이다 — 링크가 깨진다: {bad}"


def test_이름에_날짜_판본_상태를_넣지_않는다():
    bad = [str(p) for p in rule_docs() if BAD_PART.search(p.stem)]
    assert not bad, f"날짜·_v2·_초안·_최종 금지 — 이력은 git에 둔다(2절 5항): {bad}"


def test_접두어는_정해진_폴더에_있다():
    bad = [
        str(p)
        for p in rule_docs()
        for prefix, folder in PREFIX_DIR.items()
        if p.name.startswith(prefix) and p.parts[1] != folder
    ]
    assert not bad, f"접두어와 폴더가 맞지 않는다(3절 표): {bad}"


def test_모든_문서가_README에_올라_있다():
    readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    missing = [str(p) for p in rule_docs() if f"]({p.parts[1]}/{p.name})" not in readme]
    assert not missing, f"새 문서는 같은 PR에서 docs/README.md 표에 한 줄을 더한다(4절): {missing}"


def test_README의_폴더_표에_모든_폴더가_있다():
    readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    missing = [
        d
        for d in sorted(DOC_DIRS | OTHER_DIRS)
        if f"`{d}/`" not in readme and f"]({d}/" not in readme
    ]
    assert not missing, f"README 폴더 구조 표에 없는 폴더: {missing}"

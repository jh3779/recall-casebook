"""GitLab 핸드북 데이터셋(docs/handbook/content)을 지정 커밋에서 재현한다.

사용법: uv run python scripts/fetch_handbook_dataset.py

AGENTS.md 7절: 원본 데이터는 커밋하지 않고, 다시 만드는 스크립트를 커밋한다.
docs/기획v1.md 3절의 실측치(34개 핵심 부서·4,612개 md)는 이 스크립트가 만든
결과를 기준으로 한다 — 실행 후 수치가 다르면 스크립트가 실패해야 한다.
"""

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "suuuuuuungho/GitLab_Data"
COMMIT_SHA = "0ab0299"
ZIP_URL = f"https://github.com/{REPO}/archive/{COMMIT_SHA}.zip"

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_CONTENT_DIR = REPO_ROOT / "docs" / "handbook" / "content"

EXPECTED_MD_COUNT = 4612

# 텍스트 RAG 코퍼스에 불필요한 비문서 파일 — 옛 안내서 docs/handbook/README.md "이미 정리한 것"(git 이력 `6d12818`, 지금은 삭제) 참고
NON_DOC_FILES = [
    "handbook.zip",
    "_index.html",
    "featured-background.png",
    "handbook/about/check-files.sh",
    "handbook/engineering/architecture/design-documents/observability_logging/diagrams.drawio",
    "handbook/engineering/architecture/design-documents/runway/img/runway_vault_4_.drawio",
    "handbook/enterprise-data/www-gitlab-com.code-workspace",
    "handbook/marketing/developer-relations/engineering/placeholder.txt",
    "handbook/marketing/developer-relations/programs/placeholder.txt",
    "handbook/marketing/product-and-technical-marketing/product-and-solution-marketing/demo/720p.scpt",
    "teamops/images/teamops-illustration_collaboration_purple.png",
    "teamops/images/teamops-illustration_contribution_purple.png",
    "teamops/images/teamops-illustration_teamwork_purple.png",
]


def download_and_extract(tmp_dir: Path) -> Path:
    zip_path = tmp_dir / "snapshot.zip"
    print(f"다운로드: {ZIP_URL}")
    urllib.request.urlretrieve(ZIP_URL, zip_path)  # noqa: S310 — 고정된 공개 GitHub URL

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp_dir)

    extracted_roots = [p for p in tmp_dir.iterdir() if p.is_dir()]
    if len(extracted_roots) != 1:
        sys.exit(f"압축 해제 결과가 예상과 다르다: {extracted_roots}")

    content_dir = extracted_roots[0] / "handbook" / "content"
    if not content_dir.is_dir():
        sys.exit(f"{content_dir} 가 없다 — 소스 저장소 구조가 바뀌었을 수 있다")
    return content_dir


def remove_non_doc_files(content_dir: Path) -> None:
    for rel_path in NON_DOC_FILES:
        path = content_dir / rel_path
        if path.exists():
            path.unlink()
        else:
            print(f"경고: {rel_path} 가 이미 없다 (소스가 바뀌었을 수 있다)")


def verify(content_dir: Path) -> None:
    all_files = [p for p in content_dir.rglob("*") if p.is_file()]
    md_files = [p for p in all_files if p.suffix == ".md"]

    if len(all_files) != len(md_files):
        non_md = [str(p.relative_to(content_dir)) for p in all_files if p.suffix != ".md"]
        sys.exit(f"md가 아닌 파일이 남아있다({len(non_md)}개): {non_md}")

    if len(md_files) != EXPECTED_MD_COUNT:
        sys.exit(
            f"md 파일 수가 예상과 다르다: {len(md_files)}개 (기대값 {EXPECTED_MD_COUNT}개). "
            "소스 저장소가 갱신됐을 수 있다 — docs/기획v1.md 3절을 다시 실측해 갱신한다."
        )

    print(f"검증 통과: {len(md_files)}개 md 파일 (기대값과 일치)")


def install_content(content_dir: Path, target: Path) -> None:
    """새 데이터를 target에 배치한다. 어느 단계에서 실패해도 기존 target은 남는다.

    같은 상위 경로의 임시 폴더(.new)에 먼저 전부 복사한 뒤, 기존 폴더를 백업(.old)으로
    옮기고 새 폴더를 제자리에 놓는다. 백업은 배치가 끝난 뒤에만 지운다.
    """
    staging = target.parent / f"{target.name}.new"
    backup = target.parent / f"{target.name}.old"
    target.parent.mkdir(parents=True, exist_ok=True)

    # 이전 실행이 교체 도중 중단돼 target은 없고 백업만 남았다면, 지우지 말고 먼저 되돌린다
    if backup.exists() and not target.exists():
        backup.rename(target)

    for leftover in (staging, backup):  # 이전 실행이 남긴 찌꺼기
        if leftover.exists():
            shutil.rmtree(leftover)

    try:
        shutil.copytree(content_dir, staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    had_existing = target.exists()
    if had_existing:
        target.rename(backup)
    try:
        staging.rename(target)
    except BaseException:
        if had_existing:
            backup.rename(target)
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if had_existing:
        shutil.rmtree(backup)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        content_dir = download_and_extract(Path(tmp))
        remove_non_doc_files(content_dir)
        verify(content_dir)  # 기존 로컬 데이터를 건드리기 전에 먼저 검증한다
        install_content(content_dir, TARGET_CONTENT_DIR)

    print(f"완료: {TARGET_CONTENT_DIR} (커밋 {COMMIT_SHA})")


if __name__ == "__main__":
    main()
